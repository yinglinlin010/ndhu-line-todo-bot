import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { createHmac } from 'node:crypto';
import { questionMode, parseSearchFeed, parseSearchHTML, createLocalAI } from './local-ai.mjs';
import { createHandler } from './webhook.mjs';

const now = Date.parse('2026-10-12T00:00:00Z');
const rss = `<rss><channel><item><title>新消息</title><link>https://example.org/new</link><description>有新的研究 &amp; 技術</description><pubDate>Sun, 11 Oct 2026 12:00:00 GMT</pubDate></item><item><title>舊消息</title><link>https://example.org/old</link><pubDate>Tue, 01 Sep 2026 12:00:00 GMT</pubDate></item><item><title>未知日期</title><link>https://example.org/undated</link></item></channel></rss>`;

test('最新問題啟用搜尋，一般問答保留本機處理', () => {
  assert.deepEqual(questionMode('最新：AI 新聞'), { question: 'AI 新聞', search: true, recent: true });
  assert.equal(questionMode('今天有什麼新聞').recent, true);
  assert.equal(questionMode('搜尋：東華大學').search, true);
  assert.equal(questionMode('問：解釋牛頓第二定律').search, false);
});

test('近期模式排除舊消息、未標日期與 XML entity 宣告', () => {
  const results = parseSearchFeed(rss, { recent: true, now });
  assert.equal(results.length, 1); assert.equal(results[0].title, '新消息');
  assert.equal(results[0].snippet, '有新的研究 & 技術');
  assert.equal(parseSearchFeed(rss, { now }).length, 3);
  assert.throws(() => parseSearchFeed('<!DOCTYPE rss><rss/>'));
});

test('搜尋先抓近期來源再交本機模型，來源由程式附加', async () => {
  const calls = [];
  const ask = createLocalAI({ now: () => now, fetchImpl: async (url, options) => {
    calls.push({ url: String(url), options });
    if (String(url).startsWith('https://news.google.com')) return new Response(rss);
    return Response.json({ message: { content: '新研究已發布。[1] https://fake.invalid/fabricated' } });
  } });
  const reply = await ask('最新：科學研究新聞');
  assert.equal(calls.length, 2);
  assert.match(calls[0].url, /when%3A7d/);
  assert.match(calls[1].url, /127\.0\.0\.1:11434\/api\/chat/);
  const request = JSON.parse(calls[1].options.body);
  assert.match(request.messages[1].content, /新消息/); assert.doesNotMatch(request.messages[1].content, /舊消息/);
  assert.match(reply, /https:\/\/example.org\/new/); assert.doesNotMatch(reply, /fake.invalid/);
});

test('近期搜尋失敗會改查網頁，仍可提供有用背景但不冒充最新資料', async () => {
  const calls = [];
  const ask = createLocalAI({ now: () => now, fetchImpl: async (url, options) => {
    calls.push(String(url));
    if (String(url).startsWith('https:')) return new Response('blocked', { status: 429 });
    assert.match(JSON.parse(options.body).messages[0].content, /不可猜測/);
    return Response.json({ message: { content: '可以先了解這個領域的基本背景。' } });
  } });
  const reply = await ask('最近有什麼新聞');
  assert.match(reply, /沒查到可確認的最新資料/);
  assert.match(reply, /基本背景/);
  assert.equal(calls.length, 4);
  assert.match(calls[1], /duckduckgo/);
  assert.match(calls[2], /bing/); assert.match(calls[3], /api\/chat/);
});

test('七天沒有消息，擴大至三十天後仍無結果便查一般網頁', async () => {
  const calls = [];
  const ask = createLocalAI({ now: () => now, fetchImpl: async url => {
    calls.push(String(url));
    if (String(url).includes('news.google.com')) return new Response('<rss><channel/></rss>');
    if (String(url).includes('bing.com')) return new Response(rss);
    return Response.json({ message: { content: '這是查到的相關資料。[1]' } });
  } });
  assert.match(await ask('東華最近有什麼消息？'), /相關資料/);
  assert.match(calls[0], /when%3A7d/); assert.match(calls[1], /when%3A30d/); assert.match(calls[2], /duckduckgo/); assert.match(calls[3], /bing/);
});

test('自然語言查老師評價，接續追問保留對話且隔離其他使用者', async () => {
  const requests = [];
  const ask = createLocalAI({ now: () => now, fetchImpl: async (url, options) => {
    if (String(url).startsWith('https:')) return new Response(rss);
    requests.push(JSON.parse(options.body));
    return Response.json({ message: { content: '找到相關資料，但學生心得需要分開看。[1]' } });
  } });
  assert.equal(questionMode('東華大學陳文盛老師的評價').search, true);
  await ask('東華大學陳文盛老師的評價', { conversationId: 'alice' });
  await ask('那詳細說明一下', { conversationId: 'alice' });
  assert.equal(requests[1].messages.length, 4);
  assert.match(requests[1].messages[1].content, /陳文盛/);
  await ask('解釋一下', { conversationId: 'bob' });
  assert.equal(requests[2].messages.length, 2);
});

test('模型失敗仍回傳來源，一般問答不對外搜尋', async () => {
  const ask = createLocalAI({ now: () => now, fetchImpl: async url => String(url).startsWith('https:') ? new Response(rss) : new Response('offline', { status: 503 }) });
  assert.match(await ask('最新：新聞'), /實際搜尋結果/);
  const normal = createLocalAI({ fetchImpl: async url => { assert.match(String(url), /127\.0\.0\.1/); return Response.json({ message: { content: 'F=ma' } }); } });
  assert.equal(await normal('問：牛頓第二定律'), 'F=ma');
});

test('LINE 立即確認 Webhook、背景生成回覆、同事件不重算', async () => {
  let resolveAI, resolveReply; let asks = 0;
  const done = new Promise(resolve => { resolveReply = resolve; });
  const server = createServer(createHandler({ secret: 'secret', token: 'token', store: {}, askAI: async () => { asks++; return new Promise(resolve => { resolveAI = resolve; }); }, fetchImpl: async (_url, options) => { assert.equal(JSON.parse(options.body).messages[0].text, '回答完成'); resolveReply(); return new Response('{}'); } }));
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const body = JSON.stringify({ events: [{ type: 'message', webhookEventId: 'evt-ai', replyToken: 'reply', source: { type: 'user', userId: 'alice' }, message: { type: 'text', text: '最新：新聞' } }] });
  const post = () => fetch(`http://127.0.0.1:${server.address().port}/webhook`, { method: 'POST', body, headers: { 'x-line-signature': createHmac('sha256', 'secret').update(body).digest('base64') } });
  try {
    assert.equal((await post()).status, 200); assert.equal(asks, 1);
    assert.equal((await post()).status, 200); assert.equal(asks, 1);
    resolveAI('回答完成'); await done;
  } finally { await new Promise(resolve => server.close(resolve)); }
});

 test('一般搜尋解析真實網址與摘要，不把搜尋驗證頁當成結果', () => {
  const html = '<table><tr><td><a class="result-link" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.org%2Freview">老師修課心得</a></td></tr><tr><td>學生說明作業偏多</td></tr></table>';
  const result = parseSearchHTML(html);
  assert.equal(result[0].url, 'https://example.org/review');
  assert.equal(result[0].snippet, '學生說明作業偏多');
  assert.deepEqual(parseSearchHTML('<html>驗證頁</html>'), []);
 });
