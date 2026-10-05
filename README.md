# 待辦小幫手 LINE Bot：改善版 v0.2.0

給學生使用的待辦記錄工具。在 LINE 輸入 `記錄：事項` 保存一筆，再輸入 `查詢` 查看自己的最新 10 筆待辦。Bot 以規則回覆，不呼叫生成式 AI；Codex 用於開發、除錯、測試及製作文件。

- 專案：https://github.com/yinglinlin010/ndhu-line-todo-bot
- 開發紀錄：https://yinglinlin010.github.io/ndhu-line-todo-bot/
- 第一版：https://github.com/yinglinlin010/ndhu-line-todo-bot/tree/classroom-v1-2026-10-05

## 為什麼改善

第一版只有記錄功能，輸入「查詢」只會收到使用提示。使用者看不到已保存的事項，降低工具的實用性。改善版新增本人待辦查詢，完成記錄後能回看內容；不改變原先記錄功能的目的。

## 使用方式

| 使用者輸入 | Bot 行為 |
| --- | --- |
| `記錄：星期五交報告` | 保存一筆，回覆「已記錄：星期五交報告。」 |
| `記錄：` | 提醒「請輸入要記錄的待辦事項。」；不保存 |
| `查詢` | 依發訊者 userId 查詢，最新在前，最多 10 筆 |
| `查詢`，本人沒有紀錄 | 提示沒有待辦，並說明新增格式 |
| `你好` 或其他不支援指令 | 提供記錄、查詢兩種使用方式 |

支援全形或半形冒號，會去除指令與內容前後空白。每筆待辦最多 300 個 JavaScript 字串長度單位。查詢不新增紀錄，不列出其他 userId 的資料；缺少 userId 時提示改用 LINE 個人聊天。

## 本機測試

Node.js 20 或以上；沒有第三方套件，不需 npm install。

```sh
npm test
npm run evidence
```

`npm test` 已通過 14 組測試，包含原本三個情境、查詢空狀態、最新排序、十筆上限、身分缺失、讀取失敗、檔案重開後的資料隔離、半形冒號，以及本機 HTTP 的記錄後查詢流程。回覆 API 以替代函式驗證，沒有傳送真正的 LINE 訊息。

`npm run evidence` 實際執行 `versions/v1/todo.mjs` 與目前 `todo.mjs`，產生 `test-evidence/v2-comparison.json`。第一版來源是保留的 Git tag，不是由 AI 猜測舊回覆。

## 設定與啟動

1. 建立 LINE 官方帳號並啟用 Messaging API，確認所屬 channel。
2. 在本機環境設定 `LINE_CHANNEL_SECRET` 與 `LINE_CHANNEL_ACCESS_TOKEN`。請自行於 LINE Console 取得真實值；README 與 `.env.example` 只有佔位說明，不放真實金鑰。勿在聊天、簡報或 GitHub 貼出秘密值。
3. `PORT` 可選，預設 3000；`TODO_FILE` 可選，預設 `./data/todos.jsonl`。
4. 執行 `npm start`。

伺服器只綁定本機 `127.0.0.1`。環境變數需在啟動前設定；程式不自動載入 `.env`。若使用 Node.js 20.6 或以上，可先在本機複製 `.env.example` 為 `.env` 並填入真實值，再用 `node --env-file=.env server.mjs` 啟動。

`GET /health` 回覆 `ok`；`POST /webhook` 驗證原始請求的 LINE HMAC-SHA256 簽章後，解析文字事件並呼叫 reply API。資料寫入本機 JSONL 檔，含事項、userId、eventId、時間；`data/` 與 `.env` 已被 Git 忽略。

## 連接 LINE 與親自測試

GitHub Pages 只提供開發紀錄網頁，**不能執行 Node.js Bot 或作為 Bot Webhook**。真人測試需要另外取得能轉送至本機 `/webhook` 的 HTTPS endpoint，或準備 Bot 主機與持久化儲存。部署到外部主機時須依平台調整綁定位址，目前未部署 Bot。

在 LINE Developers 的 Messaging API 設定中填入 HTTPS Webhook URL，按 Verify 並啟用 Use webhook，加入官方帳號好友。注意 LINE Official Account Manager 的自動回覆設定，以免把預設自動回覆誤認為本程式回覆。操作參照 [LINE 官方設定說明](https://developers.line.biz/en/docs/messaging-api/building-bot/)。

親自在 LINE 個人聊天依序測試並截圖或錄影：

1. `記錄：星期五交報告`：預期成功確認，再輸入 `查詢` 應列出這筆內容。
2. `記錄：`：預期提醒補充，之後查詢不應新增空白紀錄。
3. `你好`：預期顯示記錄與查詢提示，不新增紀錄。

每次記下輸入、預期、實際結果與測試時間，保存能看見 Bot 回覆的截圖或短影片。可使用 `test-evidence/LINE-真人測試紀錄.txt` 記錄；目前實際結果均標示為未執行。**尚未完成 LINE 真人測試，不能把本機 log 或視覺草稿當成 LINE 測試證明。**

## 保留第一版

- Git tag：`classroom-v1-2026-10-05`，commit `078d9ce`。
- `versions/v1/`：由該 tag 封存的程式、原本計畫、簡報、開發紀錄與測試輸出。
- `docs/v1/`：第一版開發紀錄原文與測試 log。
- 原本 `output/01-專題計畫.pdf`、`output/02-簡報.pdf` 與 `test-evidence/test-log.txt` 均保留。
- `version-manifest.json` 是第一版的歷史雜湊清單，對應第一版 tag，不代表改善版現行檔案。

## 改善版繳交

- `output/04-改善版成果簡報.pdf`：8 頁，採用骰子抽出的「問題與解法」敘事。
- `output/05-改善版繳交文字.txt`：專題名稱、GitHub、網頁網址與實測證明段落。
- `docs/improved-slides.pdf`：網頁可下載的同一份改善版 PDF。
- 網頁 `#improvement` 與 `#difference`：原本問題、修改內容與前後差異；`#evidence`：重新測試結果。
- 第一版封存網頁：`docs/v1/index.html`。

## 已知限制

- LINE Channel、公開 HTTPS Bot endpoint 與真人對話證據尚未完成。
- 同步 JSONL 檔案適合課堂低流量原型；讀取會掃描全檔，不支援多執行個體或高流量。
- 沒有查詢身分的舊資料不會公開列出；不支援查詢其他人的紀錄。
- 群組中回覆內容會被群組成員看到，請使用個人聊天記錄私人事項。
- 沒有刪除、完成狀態、定時提醒或生成式 AI 回覆。
- 相同 eventId 不重複寫入；reply API 失敗時，待辦可能已保存，狀態追蹤與重試仍待改善。
- 檔案毀損時提供讀取失敗提示，尚未提供備份與修復介面。

## AI 協助與技術來源

Codex 提出改善步驟、撰寫查詢功能與測試，執行前後版本比較；依使用者要求參考 [Impeccable](https://github.com/pbakaus/impeccable) 製作視覺草稿與排版。

LINE 官方文件：[Webhook 驗簽](https://developers.line.biz/en/docs/messaging-api/verify-webhook-signature/)、[回覆訊息](https://developers.line.biz/en/docs/messaging-api/sending-messages/)、[接收事件](https://developers.line.biz/en/docs/messaging-api/receiving-messages/)。
