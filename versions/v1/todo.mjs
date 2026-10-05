import { appendFileSync, mkdirSync, readFileSync, existsSync } from 'node:fs';
import { dirname } from 'node:path';

export function createStore(path) {
  return {
    add(record) {
      if (record.eventId && existsSync(path)) {
        const previous = readFileSync(path, 'utf8').split('\n').filter(Boolean).map(JSON.parse);
        if (previous.some(item => item.eventId === record.eventId)) return;
      }
      mkdirSync(dirname(path), { recursive: true });
      appendFileSync(path, JSON.stringify(record) + '\n', { encoding: 'utf8', mode: 0o600 });
    },
  };
}

export function replyFor(text, store, context = {}) {
  const match = /^記錄\s*[:：]([\s\S]*)$/.exec(text.trim());
  if (!match) return '使用方式：記錄：待辦事項\n例如：記錄：星期五交報告';
  const content = match[1].trim();
  if (!content) return '請輸入要記錄的待辦事項。';
  if (content.length > 300) return '待辦事項請縮短至 300 字以內。';
  try {
    store.add({ content, userId: context.userId || null, eventId: context.eventId || null, createdAt: new Date().toISOString() });
    return `已記錄：${content}。`;
  } catch {
    return '目前無法儲存，請稍後再試。';
  }
}
