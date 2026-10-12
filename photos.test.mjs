import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import sharp from 'sharp';
import { createServer } from 'node:http';
import { createHmac } from 'node:crypto';
import { createPhotos, photoSubject, publicIP, getPublic } from './photos.mjs';
import { createHandler } from './webhook.mjs';
import { searchReply } from './line-results.mjs';
import { createLocalAI } from './local-ai.mjs';

test('自然語言照片要求及依上一輪解讀代名詞', () => {
  assert.equal(photoSubject('給我東華大學陳文盛老師的照片'), '東華大學陳文盛老師');
  assert.equal(photoSubject('他的照片呢？', '東華大學陳文盛老師的評價'), '東華大學陳文盛老師');
  assert.equal(photoSubject('東華大學介紹'), null);
  assert.equal(photoSubject('幫我生成圖片'), null);
});

test('圖片下載拒絕本機、內網及特殊 IP', async () => {
  for (const ip of ['127.0.0.1', '10.0.0.1', '192.168.1.1', '169.254.169.254', '::1', '::ffff:127.0.0.1', 'fc00::1']) assert.equal(publicIP(ip), false);
  assert.equal(publicIP('8.8.8.8'), true);
  await assert.rejects(getPublic('https://127.0.0.1/private'));
  await assert.rejects(getPublic('http://example.com/image.jpg'));
});

test('下載來源圖片、轉成 LINE JPEG、公開路由只讀取照片快取', async () => {
  const dir = mkdtempSync(join(tmpdir(), 'photo-bot-'));
  const image = await sharp({ create: { width: 300, height: 400, channels: 3, background: '#7799aa' } }).png().toBuffer();
  const service = createPhotos({ publicBaseURL: 'https://bot.example.org', cacheDir: dir, download: async url => {
    if (url.includes('duckduckgo')) return { body: Buffer.from('<table><tr><td><a class="result-link" href="https://school.example.org/teacher">陳文盛老師介紹</a></td></tr></table>') };
    if (url.includes('/teacher')) return { body: Buffer.from('<title>陳文盛老師</title><main><img src="https://school.example.org/photo.png" alt="陳文盛"></main>'), url };
    return { body: image, type: 'image/png', url };
  } });
  try {
    const messages = await service.handle('給我東華大學陳文盛老師的照片');
    assert.equal(messages[1].type, 'image');
    assert.match(messages[0].text, /school.example.org\/teacher/);
    const filename = messages[1].previewImageUrl.split('/').at(-1);
    const preview = readFileSync(join(dir, filename));
    assert.equal((await sharp(preview).metadata()).format, 'jpeg');
    assert.ok(preview.length < 1024 * 1024);
    let bytes; const res = { writeHead(status, headers) { assert.equal(status, 200); assert.equal(headers['Content-Type'], 'image/jpeg'); }, end(value) { bytes = value; } };
    assert.equal(service.serve({ method: 'GET', url: '/photos/' + filename }, res), true);
    assert.deepEqual(bytes, preview);
    assert.equal(service.serve({ method: 'GET', url: '/photos/../../.env' }, res), false);
    assert.deepEqual(await service.handle('給我東華大學陳文盛老師的照片'), messages);
  } finally { rmSync(dir, { recursive: true }); }
});

test('LINE 同一次回覆可傳文字、圖片與來源卡片', async () => {
  const messages = searchReply('回答。[1]', [{ title: '來源', snippet: '來源內容', url: 'https://example.org/source', published: null }]);
  messages.push({ type: 'image', originalContentUrl: 'https://example.org/image.jpg', previewImageUrl: 'https://example.org/preview.jpg' });
  const completed = Promise.withResolvers ? Promise.withResolvers() : (() => { let resolve; const promise = new Promise(r => { resolve = r; }); return { resolve, promise }; })();
  const server = createServer(createHandler({ secret: 'secret', token: 'token', store: {}, askAI: async () => messages, fetchImpl: async (_url, options) => {
    assert.deepEqual(JSON.parse(options.body).messages, messages); completed.resolve(); return new Response('{}');
  } }));
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    const body = JSON.stringify({ events: [{ type: 'message', webhookEventId: 'photo-event', replyToken: 'reply', source: { type: 'user', userId: 'alice' }, message: { type: 'text', text: '東華大學照片' } }] });
    const r = await fetch(`http://127.0.0.1:${server.address().port}/webhook`, { method: 'POST', body, headers: { 'x-line-signature': createHmac('sha256', 'secret').update(body).digest('base64') } });
    assert.equal(r.status, 200); await completed.promise;
    assert.equal(messages[1].contents.contents[0].footer.contents[0].action.uri, 'https://example.org/source');
  } finally { await new Promise(resolve => server.close(resolve)); }
});

test('跟隨上一輪要求照片不呼叫模型，其他人的對話不共用', async () => {
  const received = [];
  const ask = createLocalAI({ photos: { subject: photoSubject, handle: async (raw, previous) => {
    received.push(previous); return photoSubject(raw, previous) === null ? null : [{ type: 'text', text: '照片來源' }, { type: 'image', originalContentUrl: 'https://example.org/a.jpg', previewImageUrl: 'https://example.org/a.jpg' }];
  } }, fetchImpl: async url => String(url).startsWith('https:') ? new Response('<rss><channel/></rss>') : Response.json({ message: { content: '老師的公開資料' } }) });
  await ask('東華大學陳文盛老師的評價', { conversationId: 'alice' });
  const result = await ask('他的照片呢？', { conversationId: 'alice' });
  assert.equal(result[1].type, 'image'); assert.match(received[1], /陳文盛/);
  await ask('他的照片呢？', { conversationId: 'bob' }); assert.equal(received[2], '');
});
