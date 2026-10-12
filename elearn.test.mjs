import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createElearn, parseCalendar, formatCalendar, validateCalendarURL } from './elearn.mjs';
import { createHandler } from './webhook.mjs';
import { createServer } from 'node:http';
import { createHmac } from 'node:crypto';

const url = 'https://elearn4.ndhu.edu.tw/moodle/calendar/export_execute.php?authtoken=test-only';
const event = { source: { type: 'user', userId: 'alice' } };
const feed = (title = '作業一', at = '20261011T000000Z') => `BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:assignment-1\r\nDTSTART:${at}\r\nDTEND:${at}\r\nSUMMARY:${title}\r\nCATEGORIES:物理課\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n`;

test('課程時間、台灣時區、取消事件、過期事件與折行文字', async () => {
  const text = feed('長名稱\r\n 延續').replace('END:VCALENDAR', 'BEGIN:VEVENT\r\nUID:cancelled\r\nDTSTART:20261012T000000Z\r\nSUMMARY:取消作業\r\nSTATUS:CANCELLED\r\nEND:VEVENT\r\nEND:VCALENDAR');
  const events = await parseCalendar(text);
  assert.equal(events.length, 1);
  assert.equal(events[0].title, '長名稱延續');
  const message = formatCalendar(events, Date.parse('2026-10-10T00:00:00Z'));
  assert.match(message, /10\/11.*08:00/);
  assert.match(message, /未確認繳交狀態/);
  assert.doesNotMatch(formatCalendar(events, Date.parse('2026-10-12T00:00:00Z')), /長名稱/);
  const taipei = await parseCalendar(feed().replaceAll('20261011T000000Z', '20261011T080000').replace('DTSTART:', 'DTSTART;TZID=Asia/Taipei:').replace('DTEND:', 'DTEND;TZID=Asia/Taipei:'));
  assert.equal(taipei[0].at, events[0].at);
});

test('拒絕登入 HTML、無效 ICS 與非東華訂閱網址', async () => {
  await assert.rejects(parseCalendar('<html>登入頁</html>'));
  await assert.rejects(parseCalendar('BEGIN:VCALENDAR\nVERSION:2.0'));
  assert.throws(() => validateCalendarURL('http://127.0.0.1/private?authtoken=x'));
  assert.throws(() => validateCalendarURL('https://elearn4.ndhu.edu.tw/moodle/login/index.php?authtoken=x'));
});

test('私聊綁定、跨使用者與群組隔離、同步更新及重啟保存', async () => {
  const dir = mkdtempSync(join(tmpdir(), 'elearn-test-'));
  const stateFile = join(dir, 'state.json'); let body = feed();
  try {
    const settings = { calendarURL: url, token: 'fake-token', stateFile, bindCode: 'test-bind', now: () => Date.parse('2026-10-10T00:00:00Z'), fetchImpl: async () => new Response(body) };
    const service = createElearn(settings);
    assert.match(await service.handle('e學苑', event), /尚未綁定/);
    assert.match(await service.handle('綁定e學苑 wrong', event), /不正確/);
    assert.match(await service.handle('綁定e學苑 test-bind', { source: { type: 'group', userId: 'alice' } }), /個人聊天/);
    assert.match(await service.handle('綁定e學苑 test-bind', event), /已綁定/);
    assert.match(await service.handle('e學苑', { source: { type: 'user', userId: 'bob' } }), /尚未綁定/);
    assert.match(await service.handle('e學苑', event), /作業一/);
    body = feed('改期作業', '20261012T000000Z');
    const refreshed = await service.handle('同步e學苑', event);
    assert.match(refreshed, /改期作業/); assert.doesNotMatch(refreshed, /作業一/);
    body = '<html>登入</html>';
    assert.match(await service.handle('同步e學苑', event), /暫時無法同步/);
    assert.equal(createElearn(settings).bindCode, null);
    assert.match(await service.handle('關閉提醒', event), /已關閉/);
  } finally { rmSync(dir, { recursive: true }); }
});

test('提醒失敗重試相同 key、成功去重、重啟不重傳、關閉後不推播', async () => {
  const dir = mkdtempSync(join(tmpdir(), 'elearn-reminders-'));
  let clock = Date.parse('2026-10-10T01:00:00Z'), fail = true; const pushes = [];
  const settings = { calendarURL: url, token: 'fake-token', stateFile: join(dir, 'state.json'), bindCode: 'test-bind', now: () => clock,
    fetchImpl: async (target, options) => {
      if (target === url) return new Response(feed());
      pushes.push({ ...JSON.parse(options.body), retryKey: options.headers['X-Line-Retry-Key'] });
      return new Response('{}', { status: fail ? 500 : 200 });
    } };
  try {
    const service = createElearn(settings);
    await service.handle('綁定e學苑 test-bind', event);
    await service.tick(); assert.equal(pushes.length, 1);
    fail = false;
    await service.tick(); assert.equal(pushes.length, 2);
    assert.equal(pushes[0].retryKey, pushes[1].retryKey);
    assert.equal(pushes[1].to, 'alice');
    await service.tick(); assert.equal(pushes.length, 2);
    const reopened = createElearn(settings); await reopened.tick(); assert.equal(pushes.length, 2);
    clock += 1000;
    await reopened.handle('關閉提醒', event); await reopened.tick(); assert.equal(pushes.length, 2);
  } finally { rmSync(dir, { recursive: true }); }
});

test('每天上午八點摘要只傳一次，其他時段不補發', async () => {
  const dir = mkdtempSync(join(tmpdir(), 'elearn-daily-')); const sent = [];
  let clock = Date.parse('2026-10-10T00:05:00Z');
  try {
    const service = createElearn({ calendarURL: url, token: 'fake-token', stateFile: join(dir, 'state.json'), bindCode: 'code', now: () => clock,
      fetchImpl: async (target, options) => target === url ? new Response(feed('下週作業', '20261015T000000Z')) : (sent.push(JSON.parse(options.body)), new Response('{}')) });
    await service.handle('綁定e學苑 code', event);
    await service.tick(); await service.tick(); assert.equal(sent.length, 1);
    clock = Date.parse('2026-10-10T02:00:00Z'); await service.tick(); assert.equal(sent.length, 1);
    clock = Date.parse('2026-10-11T00:05:00Z'); await service.tick(); assert.equal(sent.length, 2);
  } finally { rmSync(dir, { recursive: true }); }
});

test('真實 HTTP Webhook 將 e學苑指令交給同步服務並回覆', async () => {
  const replies = [];
  const server = createServer(createHandler({ secret: 'test-secret', token: 'test-token', store: {}, elearn: { handle: async (command, received) => {
    assert.equal(command, 'e學苑'); assert.equal(received.source.userId, 'alice'); return '同步測試成功';
  } }, fetchImpl: async (_url, options) => { replies.push(JSON.parse(options.body)); return new Response('{}'); } }));
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    const body = JSON.stringify({ events: [{ ...event, type: 'message', message: { type: 'text', text: 'e學苑' }, replyToken: 'test' }] });
    const response = await fetch(`http://127.0.0.1:${server.address().port}/webhook`, { method: 'POST', body, headers: { 'x-line-signature': createHmac('sha256', 'test-secret').update(body).digest('base64') } });
    assert.equal(response.status, 200); assert.equal(replies[0].messages[0].text, '同步測試成功');
  } finally { await new Promise(resolve => server.close(resolve)); }
});
