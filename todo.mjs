import { appendFileSync, mkdirSync, readFileSync, existsSync } from 'node:fs';
import { dirname } from 'node:path';

export function createStore(path) {
  const read = () => existsSync(path)
    ? readFileSync(path, 'utf8').split('\n').filter(Boolean).map(JSON.parse)
    : [];
  return {
    add(record) {
      if (record.eventId && read().some(item => item.eventId === record.eventId)) return;
      mkdirSync(dirname(path), { recursive: true });
      appendFileSync(path, JSON.stringify(record) + '\n', { encoding: 'utf8', mode: 0o600 });
    },
    list(userId) {
      // Do not expose unidentified legacy records or another user's tasks.
      if (!userId) return [];
      return read().filter(item => item.userId === userId);
    },
  };
}

export function replyFor(text, store, context = {}) {
  const command = text.trim();
  if (command === '查詢') {
    if (!context.userId) return '無法辨識使用者，請在 LINE 個人聊天中再試一次。';
    try {
      const records = store.list(context.userId);
      if (!records.length) return '目前沒有待辦事項。\n輸入「記錄：待辦事項」新增一筆。';
      const latest = records.slice(-10).reverse();
      return `你的待辦事項（共 ${records.length} 筆，顯示最新 ${latest.length} 筆）：\n`
        + latest.map((item, index) => `${index + 1}. ${item.content}`).join('\n');
    } catch {
      return '目前無法讀取待辦事項，請稍後再試。';
    }
  }
  const match = /^[記紀][錄録]\s*[:：]([\s\S]*)$/.exec(command);
  if (!match) return '使用方式：\n記錄：待辦事項（例如：記錄：星期五交報告）\n查詢（查看自己的最新 10 筆待辦）';
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
