import assert from 'node:assert/strict';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { replyFor as before, createStore as oldStore } from '../versions/v1/todo.mjs';
import { replyFor as after, createStore } from '../todo.mjs';

const dir = mkdtempSync(join(tmpdir(), 'todo-comparison-'));
try {
  const a = oldStore(join(dir, 'v1.jsonl')), b = createStore(join(dir, 'v2.jsonl'));
  const context = { userId: 'test-user', eventId: 'record-1' };
  before('記錄：星期五交報告', a, context);
  after('記錄：星期五交報告', b, context);
  const inputs = ['查詢', '記錄：星期五交報告', '記錄：', '你好'];
  const rows = inputs.map(input => ({ input, before: before(input, a, context), after: after(input, b, context) }));
  assert.equal(rows[0].before, '使用方式：記錄：待辦事項\n例如：記錄：星期五交報告');
  assert.equal(rows[0].after, '你的待辦事項（共 1 筆，顯示最新 1 筆）：\n1. 星期五交報告');
  const evidence = {
    date: new Date().toISOString(),
    mode: '本機執行第一版封存程式與改善版程式，不是 LINE 客戶端測試',
    baselineTag: 'classroom-v1-2026-10-05', version: '0.2.0', rows,
  };
  writeFileSync(new URL('../test-evidence/v2-comparison.json', import.meta.url), JSON.stringify(evidence, null, 2));
  console.log(JSON.stringify(evidence, null, 2));
} finally { rmSync(dir, { recursive: true }); }
