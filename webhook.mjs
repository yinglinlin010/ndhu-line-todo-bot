import { createHmac, timingSafeEqual } from 'node:crypto';
import { replyFor } from './todo.mjs';
import { createLocalAI } from './local-ai.mjs';

export function verifySignature(body, signature, secret) {
  if (!secret || typeof signature !== 'string') return false;
  const expected = createHmac('sha256', secret).update(body).digest('base64');
  const a = Buffer.from(signature), b = Buffer.from(expected);
  return a.length === b.length && timingSafeEqual(a, b);
}

export async function askLocalAI(prompt) {
  return createLocalAI({ model: process.env.OLLAMA_MODEL || 'qwen2.5:3b', baseURL: process.env.OLLAMA_BASE_URL || 'http://127.0.0.1:11434' })(prompt);
}

export function createHandler({ secret, token, store, fetchImpl = fetch, elearn, photos, askAI = askLocalAI }) {
  const aiEvents = new Map();
  async function sendReply(event, replyText) {
    const response = await fetchImpl('https://api.line.me/v2/bot/message/reply', {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ replyToken: event.replyToken, messages: Array.isArray(replyText) ? replyText.slice(0, 5) : [{ type: 'text', text: replyText.slice(0, 4900) }] }),
      signal: AbortSignal.timeout(10000),
    });
    console.log(`[Event] Reply status: ${response.status}`);
    return response.ok;
  }
  return async (req, res) => {
    if (photos?.serve(req, res)) return;
    const finish = (status, text) => { res.writeHead(status, { 'Content-Type': 'text/plain; charset=utf-8' }); res.end(text); };
    if (req.method === 'GET' && req.url === '/health') return finish(200, 'ok');
    if (req.method !== 'POST' || req.url !== '/webhook') return finish(404, 'not found');
    try {
      const chunks = []; let size = 0;
      for await (const chunk of req) {
        size += chunk.length;
        if (size > 1024 * 1024) return finish(413, 'body too large');
        chunks.push(chunk);
      }
      const body = Buffer.concat(chunks);
      if (!verifySignature(body, req.headers['x-line-signature'], secret)) return finish(401, 'invalid signature');
      let data;
      try { data = JSON.parse(body.toString('utf8')); } catch { return finish(400, 'invalid JSON'); }
      if (!Array.isArray(data.events)) return finish(400, 'invalid events');
      for (const event of data.events) {
        if (event.type !== 'message' || event.message?.type !== 'text' || !event.replyToken) continue;
        if (typeof event.message.text !== 'string') return finish(400, 'invalid text');
        if (!token) return finish(503, 'channel token missing');
        console.log('[Event] Received text message');

        const rawText = event.message.text.trim();
        const matchTodo = /^[記紀][錄録]\s*[:：]/.test(rawText);
        const isQuery = rawText === '查詢';

        let replyText = await elearn?.handle(rawText, event);
        if (replyText != null) {
          // Calendar commands bypass AI, including authorization failures.
        } else if (matchTodo || isQuery) {
          replyText = replyFor(rawText, store, { userId: event.source?.userId, eventId: event.webhookEventId });
        } else {
          // Acknowledge LINE immediately; search/model work can take tens of seconds.
          const key = event.webhookEventId || event.replyToken;
          const current = Date.now();
          for (const [id, at] of aiEvents) if (current - at > 600000) aiEvents.delete(id);
          if (aiEvents.has(key)) continue;
          if (aiEvents.size >= 500) return finish(503, 'busy');
          aiEvents.set(key, current);
          void askAI(rawText, { conversationId: `${event.source?.groupId || event.source?.roomId || 'private'}:${event.source?.userId || event.replyToken}` }).then(answer => sendReply(event, answer)).then(ok => {
            if (!ok) console.error('[AI] LINE reply failed');
          }).catch(() => console.error('[AI] Processing failed'));
          continue;
        }

        console.log('[Event] Sending reply');
        if (!await sendReply(event, replyText)) return finish(502, 'reply failed');
      }
      finish(200, 'ok');
    } catch { finish(502, 'webhook processing failed'); }
  };
}
