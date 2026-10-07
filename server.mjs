import { createStore } from './todo.mjs';
import { createServer } from 'node:http';
import { createHandler } from './webhook.mjs';
process.loadEnvFile?.();
const secret = process.env.LINE_CHANNEL_SECRET;
const token = process.env.LINE_CHANNEL_ACCESS_TOKEN;
if (!secret || !token) throw new Error('請先在本機環境設定 LINE_CHANNEL_SECRET 和 LINE_CHANNEL_ACCESS_TOKEN');
createServer(createHandler({ secret, token, store: createStore(process.env.TODO_FILE || './data/todos.jsonl') })).listen(Number(process.env.PORT || 3000), '127.0.0.1', () => console.log('LINE Bot listening on http://127.0.0.1:' + (process.env.PORT || 3000)));
