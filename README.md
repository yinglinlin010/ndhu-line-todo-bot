# 待辦小幫手 LINE Bot 第一版

2026-10-05 課堂作業。從零建立的獨立 Node.js 專案，不依賴原有塔羅網頁。

## 第一版範圍

輸入 `記錄：星期五交報告`，保存到本機 JSONL 檔案並回覆 `已記錄：星期五交報告。`。空白內容提醒補充，其他指令提供使用方式。尚未提供查詢、刪除、提醒排程或 AI 生成回覆。

## 啟動與測試

需要 Node.js 20 或以上，無須 npm install。

```sh
cd homework-v1
npm test
```

本機連接 LINE 前，須自行於 LINE Developers 建立 Messaging API channel，將 Channel Secret 與 Channel Access Token 設定為本機環境變數。不要將金鑰貼入 GitHub、開發紀錄網頁或簡報。`.env.example` 僅供參考，本程式不自動讀取 `.env`。

```sh
npm start
```

伺服器預設只在本機 `127.0.0.1:3000` 執行。`POST /webhook` 接收已驗簽事件；`GET /health` 用於健康檢查。LINE 真實測試尚須可由 LINE 連入的 HTTPS endpoint、設定 Webhook URL、啟用 Webhook，並實際加好友傳訊。上線主機的綁定位址需要依平台另行調整。

紀錄預設寫入 `data/todos.jsonl`，可用 `TODO_FILE` 指定本機路徑。內容含待辦文字、LINE userId、eventId 及建立時間。資料夾已被忽略，避免上傳。相同 webhookEventId 不重複保存；發送回覆失敗時可能已完成保存，需於改善版處理狀態追蹤與重試。此版本使用同步檔案 I/O，適合低流量課堂原型，尚未適用多執行個體部署。

## 繳交檔案

- `output/01-專題計畫.pdf`：一頁、六項計畫。
- `output/02-簡報.pdf`：六頁簡報。
- `docs/index.html`：AI 協作開發紀錄網頁。
- `docs/test-log.txt`：本機實際測試原始輸出。
- `test-evidence/test-log.txt`：保留的測試原始紀錄。
- `output/03-繳交文字.txt`：線上繳交文字草稿，上傳與發布後須填入實際連結。

目前尚未建立此新專案的 GitHub 遠端或公開網頁，亦尚未進行 LINE 真人對話測試。勿將本機測試當成 LINE 實測截圖。

## 保留第一版與課後改善

保留本資料夾、PDF、測試紀錄與 `version-manifest.json`。課後另外建立 v2，建議新增「查詢」功能，記錄 v1 / v2 的差異，新增查詢測試並重跑原本三個情境。

## 技術來源

- LINE 驗簽：https://developers.line.biz/en/docs/messaging-api/verify-webhook-signature/
- LINE 回覆訊息：https://developers.line.biz/en/docs/messaging-api/sending-messages/

AI 協助：Codex 整理需求、撰寫程式與測試、執行本機測試、製作文件與紀錄網頁。題目與需求仍由學生確認。
