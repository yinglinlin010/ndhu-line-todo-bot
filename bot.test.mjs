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
  ['不支援指令顯示提示', '你好', '使用方式：\n記錄：待辦事項（例如：記錄：星期五交報告）\n查詢（查看自己的最新 10 筆待辦）', 0],
];
for (const [name, input, expected, count] of cases) test(name, () => {
  const records = [];
  const actual = replyFor(input, { add: r => records.push(r) });
  console.log(JSON.stringify({ input, expected, actual, savedRecords: records.length }));
  assert.equal(actual, expected); assert.equal(records.length, count);
  if (count) assert.equal(records[0].content, '星期五交報告');
});

test('查詢：沒有待辦時提示如何新增', () => {
  const actual = replyFor('查詢', { list: () => [] }, { userId: 'alice' });
  const expected = '目前沒有待辦事項。\n輸入「記錄：待辦事項」新增一筆。';
  console.log(JSON.stringify({ input: '查詢（無紀錄）', expected, actual }));
  assert.equal(actual, expected);
});

test('查詢：最新在前並列出總筆數', () => {
  const actual = replyFor(' 查詢 ', { list: () => [{ content: '交報告' }, { content: '買筆記本' }] }, { userId: 'alice' });
  const expected = '你的待辦事項（共 2 筆，顯示最新 2 筆）：\n1. 買筆記本\n2. 交報告';
  console.log(JSON.stringify({ input: '查詢（已有 2 筆）', expected, actual }));
  assert.equal(actual, expected);
});

test('查詢：超過十筆只顯示最新十筆', () => {
  const actual = replyFor('查詢', { list: () => Array.from({ length: 12 }, (_, i) => ({ content: `任務${i + 1}` })) }, { userId: 'alice' });
  assert.ok(actual.startsWith('你的待辦事項（共 12 筆，顯示最新 10 筆）：'));
  assert.ok(actual.includes('1. 任務12\n')); assert.ok(actual.endsWith('10. 任務3'));
  assert.equal(actual.split('\n').length, 11);
});

test('查詢：缺少使用者身分時不讀取任何資料', () => {
  const actual = replyFor('查詢', { list() { throw Error('must not read'); } });
  assert.equal(actual, '無法辨識使用者，請在 LINE 個人聊天中再試一次。');
});

test('查詢：檔案讀取失敗提供清楚錯誤提示', () => {
  assert.equal(replyFor('查詢', { list() { throw Error('read failed'); } }, { userId: 'alice' }), '目前無法讀取待辦事項，請稍後再試。');
});

test('查詢：重新開啟檔案仍可讀取且隔離不同使用者', () => {
  const dir = mkdtempSync(join(tmpdir(), 'todo-v2-'));
  try {
    const path = join(dir, 'todos.jsonl'), store = createStore(path);
    replyFor('記錄：我的報告', store, { userId: 'alice', eventId: 'a1' });
    replyFor('記錄：別人的事項', store, { userId: 'bob', eventId: 'b1' });
    replyFor('記錄：無身分舊資料', store);
    const reopened = createStore(path);
    const actual = replyFor('查詢', reopened, { userId: 'alice' });
    assert.equal(actual, '你的待辦事項（共 1 筆，顯示最新 1 筆）：\n1. 我的報告');
    assert.equal(reopened.list('bob').length, 1); assert.deepEqual(reopened.list(null), []);
    assert.equal(readFileSync(path, 'utf8').trim().split('\n').length, 3);
  } finally { rmSync(dir, { recursive: true }); }
});

test('記錄：半形冒號與前後空白仍可正確使用', () => {
  const records = [];
  assert.equal(replyFor(' 記錄:  交報告  ', { add: r => records.push(r) }), '已記錄：交報告。');
  assert.equal(records[0].content, '交報告');
});

test('Webhook 本機 HTTP：記錄後查詢只回傳本人待辦', async () => {
  const dir = mkdtempSync(join(tmpdir(), 'todo-v2-http-')), sent = [];
  const store = createStore(join(dir, 'todos.jsonl'));
  store.add({ content: '別人的資料', userId: 'bob', eventId: 'b1' });
  const server = createServer(createHandler({ secret: 'test-secret', token: 'fake-test-token', store, fetchImpl: async (_url, options) => {
    sent.push(JSON.parse(options.body)); return { ok: true };
  } }));
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  async function send(text, eventId) {
    const body = JSON.stringify({ events: [{ type: 'message', webhookEventId: eventId, replyToken: 'fake-reply', source: { userId: 'alice' }, message: { type: 'text', text } }] });
    return fetch(`http://127.0.0.1:${server.address().port}/webhook`, { method: 'POST', headers: { 'x-line-signature': createHmac('sha256', 'test-secret').update(body).digest('base64') }, body });
  }
  try {
    assert.equal((await send('記錄：星期五交報告', 'a1')).status, 200);
    assert.equal((await send('查詢', 'a2')).status, 200);
    const actual = sent[1].messages[0].text;
    const expected = '你的待辦事項（共 1 筆，顯示最新 1 筆）：\n1. 星期五交報告';
    console.log(JSON.stringify({ input: 'Webhook：記錄後查詢', expected, actual }));
    assert.equal(actual, expected); assert.equal(store.list('alice').length, 1);
  } finally { await new Promise(resolve => server.close(resolve)); rmSync(dir, { recursive: true }); }
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
