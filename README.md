# 本機 Ollama LINE Bot — Python 版 v0.5.0

使用跑在自己電腦上的 Ollama 回答 LINE 訊息；資訊查詢自動搜尋網路，再由本機模型整理，附上可點的來源卡片。主要程式是一支 `line_bot_local.py`，從本專案 Node.js 版移植，並參考老師提供的課堂 Python 程式加入照片辨識、Drive、Calendar 和 Sheets 功能。

Repo：https://github.com/yinglinlin010/ndhu-line-todo-bot

## 怎麼裝

需要 Python **3.11 以上**、Ollama，以及 LINE Messaging API channel。此電腦已用 Python 3.12 安裝並測試。

```sh
git clone https://github.com/yinglinlin010/ndhu-line-todo-bot.git
cd ndhu-line-todo-bot
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-lock.txt
ollama pull qwen2.5:3b
```

若使用 Python 3.11，可將 `python3.12` 換成 `python3.11`。Windows 啟用虛擬環境使用 `.venv\Scripts\Activate.ps1`。`requirements-lock.txt` 固定這次測試的版本；`requirements.txt` 保留允許的更新範圍。

開啟 Ollama 桌面程式；若未啟動，可另開終端執行 `ollama serve`。`ollama list` 應列出選用模型。

## 怎麼跑

1. 已有本機 `.env` 的使用者可直接沿用，不需要重新設定 LINE 或 e學苑綁定。
2. 新安裝時，把 `.env.example` **複製**成 `.env`，只在自己的編輯器內填入設定；不要覆蓋現有 `.env`。
3. 設定 `LINE_CHANNEL_SECRET`、`LINE_CHANNEL_ACCESS_TOKEN`。未設定時，程式啟動會以隱藏輸入詢問，輸入值只留在記憶體。
4. 可選設定 `OLLAMA_MODEL`，預設 `qwen2.5:3b`；`PORT` 預設 3000。`OLLAMA_BASE_URL` 只接受本機位址。
5. 使用以下指令啟動：

```sh
source .venv/bin/activate
python line_bot_local.py
```

`GET http://127.0.0.1:3000/health` 應回覆 `ok`。程式綁定 `127.0.0.1`；需沿用現有 HTTPS 通道，將 `/webhook` 轉送至此連接埠。LINE Webhook 設定須指向通道的 `/webhook`，並啟用 Use webhook。GitHub Pages 只能放說明網頁，不能執行這支 bot。

**切換前先停止 Node.js bot**，不要讓兩版搶同一連接埠或同時寫資料／發提醒。Python 版沿用相同連接埠和通道時，無須更改 LINE Webhook。

照片功能需要 `.env` 的 `PUBLIC_BASE_URL` 為 LINE 可存取的 HTTPS 通道根網址，通道換網址時要更新並重新啟動。

## 你改了什麼

- 將 Node.js 多模組版本改成 Python 單檔；不再需要 Node.js 來執行新版 bot。
- 保留「記錄：事項」「查詢」、本人最新十筆待辦、空白／長度檢查與事件去重。
- 保留 Ollama 本機問答、自動搜尋、來源 Flex 卡片及最近三輪追問。不同使用者／群組的對話隔離；閒置二十分鐘清除，重啟也清除。
- 保留自然語言照片搜尋、來源說明、JPEG 與縮圖快取。只下載公開 HTTPS 位址，逐次重新導向驗證並固定 DNS 位址，限制下載與解碼大小。
- 新增收到 LINE 照片後的本機辨識，使用另一個支援圖片的 `qwen2.5vl:3b`，不把圖片交給雲端模型。
- 新增老師版 Google 功能：照片存 Drive、行程寫 Calendar、問答記 Sheets。需要完成 Google 登入並在本機明確啟用；只允許綁定者的個人聊天。
- 行程先核對日期時間，回覆「確認排程」才建立；Google 寫入結果不明時不自動重複寫入，不冒充成功。Sheets 使用 RAW 避免把使用者文字當公式執行。
- 保留 e學苑行事曆、私聊綁定、今天／明天／本週篩選、每天上午八點摘要及事件前二十四小時提醒。沿用原本綁定狀態與推播 retry key，避免移植後重發。
- 加入安全的終端紀錄：搜尋服務、來源筆數、本機模型名稱、回答耗時、LINE 回覆狀態；不輸出金鑰、私人行事曆網址或使用者訊息。
- 可選設定 `W5_WEBHOOK_URL`，讓正常 Ctrl+C／SIGTERM 退出後恢復 W5 Apps Script。

**沒有自行改寫或覆蓋既有待辦與綁定資料。** Node.js 原始檔與歷史紀錄保留，舊版詳細說明在 [README-nodejs.md](README-nodejs.md)。

## e學苑設定

登入 e學苑，進入行事曆匯出，取得訂閱網址，僅存入本機 `.env` 的 `ELEARN_CALENDAR_URL`；網址包含私人授權碼。只接受東華官方匯出端點，不儲存學校密碼。

既有綁定可直接沿用 `data/elearn.json`。新綁定先啟動 bot，再另開終端：

```sh
source .venv/bin/activate
python line_bot_local.py --bind-code
```

將顯示的「綁定e學苑 綁定碼」傳到 LINE **個人聊天**。綁定碼不要放在作業截圖。可傳「e學苑」「同步e學苑」「我今天有什麼作業」「明天要交什麼」「開啟提醒」「關閉提醒」。其他帳號與群組不能查看私人行事曆。

提醒需要電腦、bot 與通道持續運作；LINE 推播受帳號額度限制。離線不會補發八點摘要。行事曆不等於繳交狀態；未列入行事曆的作業無法取得，重複性事件目前不支援。

## 停止與恢復 W5

如果這次會把 Webhook 從 W5 切到本機，先把原本的 Apps Script `/exec` 網址存入本機 `.env` 的 `W5_WEBHOOK_URL`。**設定此值表示要求程式在退出時呼叫 LINE API 恢復該網址。** 網址不會印到終端。

也可以用隱藏輸入設定，避免網址出現在終端畫面或命令歷史：

```sh
python scripts/configure-w5.py
```

設定後需重新啟動 bot。這支設定程式只寫本機 `.env`，不修改 LINE Webhook。

按 Ctrl+C 後，程式停止收新事件，等已接收的訊息完成，再恢復 W5；看到「已恢復 W5 Apps Script」才算成功。如果未設定或恢復失敗，請到 LINE Console 手動恢復，並實測 W5 待辦。強制關機、kill -9 或網路中斷無法保證自動恢復。

本機實測已將 LINE Webhook 接上 Python bot 的公開通道；原本 `W5_WEBHOOK_URL` 尚待使用者在本機設定，設定前不能宣稱已可自動恢復 W5。

## 測試與作業截圖

```sh
python -m unittest -v test_line_bot_local.py test_teacher_features.py
```

30 項測試通過。測試使用暫存資料與 LINE／Google API 替代函式，不會發送真實訊息或寫入 Google。涵蓋驗簽、立即確認與背景回覆、事件去重、待辦資料隔離、來源附加、搜尋／模型失敗、私聊綁定、時區、同步更新、重試 key、圖片轉檔與路徑限制、W5 恢復後讀回確認、真實本機 HTTP 啟停，以及照片訊息、視覺能力檢查、行程確認／取消、跨帳號隔離、Google 寫入去重、失敗訊息遮蔽與試算表 RAW 寫入。

另已實際呼叫網路搜尋與本機 `qwen2.5:3b`，取得三筆來源並成功生成來源卡片；公開 HTTPS DNS 固定下載也成功。這些本機驗證不等同於手機 LINE 實測。

新增功能另已實測：本機照片模型讀出測試卡的日期與時間；文字模型正確解析「明天下午三點開會」；gws 0.22.5 的 Drive、Calendar、Sheets 指令預演均成功。已完成 Google OAuth 登入，Drive／Calendar API 真實讀取成功；私人紀錄表已建立，透過 bot 的 Sheets 寫入函式追加一列設定驗證並讀回一致。2026-10-12 18:59 的 LINE 照片實測已完成：照片存 Drive、本機視覺模型生成、寫入 Sheets，LINE 回覆 200；確認行程寫 Calendar 的完整 LINE 流程仍待實測。

Python 版已完成 LINE 問答實測；繳交仍須附同次手機與終端截圖，以前 Node.js 的截圖不能當作 Python 版實測。啟動新版後，在手機問「東華大學最近有什麼新聞？」或一題需要即時查證的問題，拍下回答與來源；同時拍終端的 `[Search]`、`[Ollama] ... 回答完成` 及 `[LINE] 回覆狀態：200`。只提供來源但顯示「模型無法整理」不代表本機模型已成功回答。

繳交順序：第一行 repo 連結、兩張真實截圖、最後一句模型／修改／卡關說明。不要宣稱尚未完成的實測。

## 隱私與已知限制

`.env`、`data/`、虛擬環境、client secret 與 credentials 檔案均被 Git 忽略。上傳前仍須檢查程式和 Git 暫存區；截圖不能顯示金鑰、私人授權碼、client_secret.json 內容或 `/exec` 網址。

搜尋問題會送到公開搜尋服務；模型生成在本機 Ollama 進行。一般搜尋使用 DuckDuckGo Lite／Bing RSS；新聞優先使用 Google News RSS，依序查七天、三十天，再改查一般網頁。只取得標題與摘要，不讀全文；未取得可靠來源時不把模型記憶當作最新消息。來源卡片是搜尋結果，不保證模型每項推論都正確。

此版是課堂低流量單機原型：四個背景工作執行緒，最多十六筆待處理事件；滿載回 503。LINE reply token 有效時間有限，模型或排隊太慢可能回覆失敗。單檔 JSONL 不適合多執行個體，待辦尚無刪除／完成狀態，照片快取滿時需自行整理。私聊與群組對話暫存在記憶體；群組回覆會被其他群組成員看到。

老師原版會自動開通道並記住啟動前的 Webhook；本專案沿用既有背景通道，退出時恢復明確設定的 `W5_WEBHOOK_URL`。未設定時不會自動找回 W5，不能把目前本機通道誤當成原本 Apps Script。老師原版自動排日曆；本版要求確認，避免辨識或模型解析錯誤直接建立事件。

這次實測使用 `ENABLE_REMINDERS=0 python line_bot_local.py` 暫停定時推播，私人行事曆查詢仍可用，原本提醒設定不會被覆寫。未指定此變數時照既有綁定設定發提醒。

## 本次實測證據

2026-10-12 台灣時間 13:40:40 收到 LINE 文字事件，Google News 搜尋取得三筆來源，`qwen2.5:3b` 於 13:40:43 完成生成，LINE 回覆 API 返回 200。安全終端紀錄在 [test-evidence/python-line-live-log.txt](test-evidence/python-line-live-log.txt)。這能證明程式執行與 API 回覆成功；手機畫面中的問題、回答與來源仍需以同次實測截圖核對。

## 老師版照片與 Google 功能

文字問答維持 `qwen2.5:3b`；它不能看圖。照片使用 `OLLAMA_VISION_MODEL`，預設 `qwen2.5vl:3b`。先安裝照片模型：

```sh
ollama pull qwen2.5vl:3b
```

Google 功能使用 [Google Workspace CLI](https://github.com/googleworkspace/cli)，可安裝在被 Git 忽略的本機工具目錄：

```sh
npm install --prefix .tools @googleworkspace/cli@0.22.5
```

依 CLI 官方說明準備 Google Cloud 專案和 Desktop OAuth client，在本機 `.env` 設定 `GOOGLE_WORKSPACE_CLI_CONFIG_DIR` 為 `data/gws` 的絕對路徑，再把下載的 client 設定存於該目錄的 `client_secret.json`。該目錄被 Git 忽略，**不要上傳或貼出內容**。需要 Drive、Calendar、Sheets API；Google 帳號需加入測試使用者。完成 OAuth 設定後登入這三項服務：

```sh
.tools/node_modules/.bin/gws auth login --scopes https://www.googleapis.com/auth/drive.file,https://www.googleapis.com/auth/calendar.events,https://www.googleapis.com/auth/spreadsheets
python scripts/configure-google.py
```

設定工具隱藏輸入試算表 ID，沿用現有 e學苑綁定者；沒有既有綁定時再詢問 LINE 私聊 userId。輸入 ENABLE 才會寫入本機設定並啟用。需重新啟動 bot。`GOOGLE_ENABLED=0` 預設不寫雲端，但本機照片辨識仍可使用。

- 傳照片：下載 LINE 圖片、移除 metadata 並轉 JPEG，交本機模型描述。Google 啟用後，綁定者照片另存 Drive 的「LINE待辦照片」，不變更分享權限。其他人與群組的照片只在本機處理。
- 傳「明天下午三點開會」：模型解析並核對日期，顯示待確認行程；傳「確認排程」才寫進主日曆，預設三十分鐘，不邀請其他人。傳「取消排程」取消。待確認內容二十分鐘失效。
- 照片出現行程：同樣先顯示辨識結果，確認後才建立。請仔細核對模型讀出的文字。
- 設定 `SHEET_ID` 後：一般問答、行程流程與照片記錄寫入指定試算表，每列為時間、類型、使用者文字、回答摘要、照片連結、日曆結果。打招呼不記錄。原有待辦、e學苑查詢仍走既有私人資料流程，不額外上傳到 Sheets。

Google 寫入先執行再回覆結果。成功才說「已儲存／已記錄」；回應不明時保留本機操作紀錄，避免重送後再次寫入，需自行到 Google 核對。Google 功能只接受綁定者私聊，單個待確認行程和操作紀錄保存在被忽略的 `data/google-actions.json`。

Google 登入狀態、試算表 ID、LINE userId 和 OAuth 憑證都只能保留本機；不得出現在程式、README 或作業截圖。照片暫存上傳後會刪除；Drive 中的照片需由你自行管理。
