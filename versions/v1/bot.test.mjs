import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createHmac } from 'node:crypto';
import { createServer } from 'node:http';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { replyFor, createStore } from './todo.mjs';
import { createHandler } from './webhook.mjs';

const cases = [
  ['完整待辦成功記錄', '記錄：星期五交報告', '已記錄：星期五交報告。', 1],
  ['空白待辦提醒補充', '記錄：', '請輸入要記錄的待辦事項。', 0],
  ['不支援指令顯示提示', '你好', '使用方式：記錄：待辦事項\n例如：記錄：星期五交報告', 0],
];
for (const [name, input, expected, count] of cases) test(name, () => {
  const records = [];
  const actual = replyFor(input, { add: r => records.push(r) });
  console.log(JSON.stringify({ input, expected, actual, savedRecords: records.length }));
  assert.equal(actual, expected); assert.equal(records.length, count);
  if (count) assert.equal(records[0].content, '星期五交報告');
});

test('檔案持久化及相同事件去重', () => {
  const dir = mkdtempSync(join(tmpdir(), 'todo-v1-'));
  try {
    const path = join(dir, 'todos.jsonl');
    replyFor('記錄：星期五交報告', createStore(path), { eventId: 'evt-1', userId: 'test-user' });
    replyFor('記錄：星期五交報告', createStore(path), { eventId: 'evt-1', userId: 'test-user' });
    const rows = readFileSync(path, 'utf8').trim().split('\n').map(JSON.parse);
    assert.equal(rows.length, 1); assert.equal(rows[0].content, '星期五交報告');
  } finally { rmSync(dir, { recursive: true }); }
});

test('空白、過長內容與寫入錯誤', () => {
  assert.equal(replyFor('記錄：   ', { add() { throw Error(); } }), '請輸入要記錄的待辦事項。');
  assert.equal(replyFor('記錄：' + '字'.repeat(301), { add() { throw Error(); } }), '待辦事項請縮短至 300 字以內。');
  assert.equal(replyFor('記錄：交報告', { add() { throw Error(); } }), '目前無法儲存，請稍後再試。');
});

test('Webhook 本機 HTTP：驗簽、回覆、空事件、錯誤處理', async () => {
  const sent = [], records = [];
  let fail = false;
  const server = createServer(createHandler({ secret: 'test-secret', token: 'fake-test-token', store: { add: r => records.push(r) }, fetchImpl: async (url, options) => {
    assert.equal(url, 'https://api.line.me/v2/bot/message/reply');
    assert.equal(options.headers.Authorization, 'Bearer fake-test-token');
    sent.push(JSON.parse(options.body)); return { ok: !fail };
  } }));
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const url = `http://127.0.0.1:${server.address().port}/webhook`;
  async function post(body, valid = true) {
    const signature = createHmac('sha256', 'test-secret').update(body).digest('base64');
    return fetch(url, { method: 'POST', headers: { 'x-line-signature': valid ? signature : 'wrong' }, body });
  }
  try {
    const body = JSON.stringify({ events: [{ type: 'message', webhookEventId: 'evt-http', replyToken: 'test-reply', source: { userId: 'test-user' }, message: { type: 'text', text: '記錄：星期五交報告' } }] });
    assert.equal((await post(body, false)).status, 401); assert.equal(records.length, 0); assert.equal(sent.length, 0);
    assert.equal((await post(body)).status, 200); assert.equal(records.length, 1);
    assert.equal(sent[0].messages[0].text, '已記錄：星期五交報告。');
    assert.equal((await post('{"events":[]}')).status, 200);
    assert.equal((await post('bad-json')).status, 400);
    assert.equal((await post('{}')).status, 400);
    fail = true; assert.equal((await post(body)).status, 502);
  } finally { await new Promise(resolve => server.close(resolve)); }
});
