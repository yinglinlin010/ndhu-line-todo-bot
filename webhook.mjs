import { createHmac, timingSafeEqual } from 'node:crypto';
import { replyFor } from './todo.mjs';

export function verifySignature(body, signature, secret) {
  if (!secret || typeof signature !== 'string') return false;
  const expected = createHmac('sha256', secret).update(body).digest('base64');
  const a = Buffer.from(signature), b = Buffer.from(expected);
  return a.length === b.length && timingSafeEqual(a, b);
}

export async function askLocalAI(prompt) {
  try {
    const res = await fetch('http://127.0.0.1:11434/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: 'qwen2.5:3b',
        prompt: `你是一個待辦小幫手裡的 AI 助理，請使用台灣常用的繁體中文簡要親切地回答問題。\n\n問題：${prompt}\n回答：`,
        stream: false,
        options: { num_predict: 260, temperature: 0.7 }
      }),
      signal: AbortSignal.timeout(15000),
    });
    if (!res.ok) return null;
    const data = await res.json();
    return data.response?.trim() || null;
  } catch (err) {
    console.error('Local AI error:', err.message);
    return null;
  }
}

export function createHandler({ secret, token, store, fetchImpl = fetch }) {
  return async (req, res) => {
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
        console.log(`[Event] Received: "${event.message.text}" from ${event.source?.userId}`);

        const rawText = event.message.text.trim();
        const matchTodo = /^[記紀][錄録]\s*[:：]/.test(rawText);
        const isQuery = rawText === '查詢';

        let replyText;
        if (matchTodo || isQuery) {
          replyText = replyFor(rawText, store, { userId: event.source?.userId, eventId: event.webhookEventId });
        } else {
          // 一般問答或以 問： 開頭 -> 呼叫本機 Ollama AI 模型
          const matchAsk = /^(問|AI|ai)\s*[:：]?\s*([\s\S]*)$/.exec(rawText);
          const question = matchAsk ? matchAsk[2].trim() : rawText;

          let aiAnswer = null;
          if (question) {
            aiAnswer = await askLocalAI(question);
          }
          if (aiAnswer) {
            replyText = aiAnswer;
          } else {
            replyText = replyFor(rawText, store, { userId: event.source?.userId, eventId: event.webhookEventId });
          }
        }

        console.log(`[Event] Replying: "${replyText}"`);
        const response = await fetchImpl('https://api.line.me/v2/bot/message/reply', {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
          body: JSON.stringify({ replyToken: event.replyToken, messages: [{ type: 'text', text: replyText }] }),
          signal: AbortSignal.timeout(10000),
        });
        console.log(`[Event] Reply status: ${response.status}`);
        if (!response.ok) return finish(502, 'reply failed');
      }
      finish(200, 'ok');
    } catch { finish(502, 'webhook processing failed'); }
  };
}
