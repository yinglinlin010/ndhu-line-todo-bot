# 本機 Ollama LINE Bot — 課堂版

公開 repo：https://github.com/yinglinlin010/ndhu-line-todo-bot

LINE 文字與照片交由自己電腦上的 **Gemma 4 E4B** 處理；需要時搜尋附來源。支援照片存私人 Google Drive、行程確認後寫 Calendar、指定內容寫 Sheets。文字與圖片使用 `gemma4:e4b-it-q4_K_M`，下載約6.6GB；本機已用 Python 3.12 測試。

## 怎麼裝

需要 Python 3.11以上、Ollama、cloudflared。課堂版的 Google 功能另需 Node.js、Google Workspace CLI（gws），以及你自己的 Google Cloud OAuth 設定與 Drive／Calendar／Sheets API。

```sh
git clone https://github.com/yinglinlin010/ndhu-line-todo-bot.git
cd ndhu-line-todo-bot
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-lock.txt
ollama pull gemma4:e4b-it-q4_K_M
npm install --prefix .tools @googleworkspace/cli@0.22.5
```

macOS 安裝通道工具：`brew install cloudflared`。Windows 可用官方安裝程式；虛擬環境啟用指令為 `.venv\Scripts\Activate.ps1`。

複製 `.env.example` 成 `.env`，只在本機填入 LINE 通行碼、Channel secret、原 W5 Webhook。已有設定時不要覆蓋。程式與範例檔不能放真實金鑰、試算表ID或私人網址；`data/`、`.env`、OAuth憑證已列入 `.gitignore`。

Google 功能使用隔離的本機 `data/gws` 目錄。將 `GOOGLE_WORKSPACE_CLI_CONFIG_DIR` 設為該目錄的絕對路徑，依 [gws 官方說明](https://github.com/googleworkspace/cli) 設定 Desktop OAuth client、測試使用者與API，再登入：

```sh
export GOOGLE_WORKSPACE_CLI_CONFIG_DIR="$PWD/data/gws"
.tools/node_modules/.bin/gws auth login --scopes https://www.googleapis.com/auth/drive.file,https://www.googleapis.com/auth/calendar.events,https://www.googleapis.com/auth/spreadsheets
python scripts/configure-google.py
```

上述export需與gws登入在同一個終端執行；`.env`不會自動被gws CLI讀取。Windows PowerShell可用 `$env:GOOGLE_WORKSPACE_CLI_CONFIG_DIR=(Join-Path $PWD "data/gws")` 指定相同目錄。

設定工具以隱藏輸入接收私人ID，啟用僅限綁定者私聊的Google功能；不會直接寫入雲端。課堂版手動Sheets指令需要設定試算表ID；Google帳號必須有該表的編輯權限。

## 怎麼跑

先開啟 Ollama。macOS／Linux 建議使用通道管理程序：

```sh
source .venv/bin/activate
python scripts/run-bot.py
```

它會檢查模型、建立通道、驗證本機及公開HTTPS，再接上LINE。需要在本機設定 `W5_WEBHOOK_URL`；可執行 `python scripts/configure-w5.py` 以隱藏輸入保存。發現其他程式接管Webhook時會停止，不覆蓋未知路由。通道故障最多嘗試三輪恢復；持續失敗會停止。

Windows 或自行管理通道者可用 `python line_bot_local.py`，自行保持cloudflared執行、設定 `PUBLIC_BASE_URL` 並轉送 `/webhook` 到本機3000埠；LINE後台Use webhook需開啟。不要同時啟動兩支bot。GitHub Pages不能執行此服務。

同一段對話以收到順序處理，文字、圖片及行程共用佇列；不同使用者可並行。排隊與後續工作共用45秒處理預算，網路／Google子步驟使用剩餘時間，另預留回覆時間。過期的排隊訊息不再呼叫模型；逾時後不啟動新的雲端寫入。已送出的雲端操作若結果不明仍需核對，不自動重送。這是合作式時間預算，不會強制終止正在執行的任意本機程式，也不保證網路故障時提示能送達。私聊處理時會嘗試顯示等待動畫；動畫失敗不影響處理，不延長LINE回覆token效期。

電腦、Ollama、bot與通道都要保持運作；睡眠或關機時無本機AI。健康入口 `http://127.0.0.1:3000/health` 應回覆 `ok`。

## 課堂版怎麼用

- 問文字問題：需要時公開搜尋、提供來源卡片；查不到可靠相關來源時說明無法確認。
- 傳照片：本機模型辨識，綁定者私聊的照片存私人Drive；照片有日期時間時先顯示待確認行程。
- 傳「明天下午三點開會」：解析並核對日期，回覆「確認排程」才建立Calendar事件；「取消排程」放棄，20分鐘後失效，不寄邀請。
- 傳「存試算表：要保存的內容」：只將指定內容寫一列到現有私人試算表；保留寫入收據，避免同一事件重送。使用RAW，文字不當作公式。
- 一般聊天、照片及行程的**自動Sheets紀錄維持關閉**（`ENABLE_SHEET_LOGGING=0`），符合使用者不自動保存聊天的設定。手動保存不會改動這個開關。
- 傳「記錄：事項」「查詢」使用本機私人待辦；不等同於雲端Apps Script待辦。傳「清除對話」清掉自己的短期對話記憶，不刪待辦或Google資料。

Google寫入只接受綁定者個人聊天；其他人與群組不會寫入你的Google帳號。回應不明時不自動重試或宣稱成功，需要核對Google實際內容。

一般AI文字與照片回覆附本機模型設定及本題處理時間；時間包含該次處理中的搜尋／模型／Google操作，不包含工作排隊或LINE送出耗時，也不代表每則固定提示都曾呼叫模型。

## 你改了什麼

以既有Node.js專案移植成Python，並對照老師提供的 `line_bot_local.py` 完成課堂功能；不是逐字複製老師程式。

- 使用同一E4B本機模型處理文字與照片；保留短期對話、圖片文字追問及跨重啟記憶，私人圖片描述不送公開搜尋。
- 搜尋使用公開服務、官方頁面及分類RSS；與老師使用Ollama experimental搜尋工具的方式不同。諾貝爾／總統身分題有專用官方查核，並非純模型記憶測驗。
- 新聞依分類與發布日期篩選；導讀只接受完整來源標題或前言句子，引用錯誤或改動事實時改列原始標題。這是來源文字一致性檢查，不能保證發布者報導為真。
- 同期相同標題採保守去重，保留其他媒體連結；不把僅僅近似的標題任意合併。
- 老師原版自動排日曆；本版增加使用者確認、日期驗算及持久去重。老師原版可記錄所有問答；本版預設不自動記錄，保留指定內容手動保存及可選的自動紀錄能力。
- 管理程序提供通道重建與Webhook安全還原；簽章驗證、使用者隔離、下載大小限制與安全日誌均保留。

## 測試與驗收界線

```sh
python -m unittest test_line_bot_local test_teacher_features test_service test_evaluate_faq test_classroom_check test_reliability
python scripts/check-live-quality.py
python scripts/check-news-followups.py
python scripts/check-classroom-google.py
```

最後一個指令預設僅讀取現有測試資料，不寫入Google。`--write-test-row` 是另行批准後才使用的一筆合成Sheets驗收；不會新增照片或行程、不開啟自動紀錄。驗收結果只包含安全布林值，不公開私人ID、網址或表格原內容。

- 既有E4B雲端實測已成功上傳合成圖片、確認私人權限，並建立及讀回Calendar測試行程，見 `test-evidence/e4b-cloud-live-check.json`。
- 既有真實LINE文字測試包括老師玉山與諾貝爾原題、翻譯、換題及重啟接續，見 `test-evidence/line-quality-live.json`。這些不是最新版功能的手機端到端驗證。
- 最新103項自動測試、24項本機HTTP整合通過，包含連續傳圖追問、跨使用者處理、排隊逾時、逾時禁止後續寫入及行程取代保護。此前真實E4B行程日期／時間解析紀錄仍保留。
- 最新Google唯讀檢查再次確認既有測試圖片、行程及試算表可讀。經使用者同意，已透過bot流程新增一筆合成Sheets驗收紀錄並讀回，確認只出現一次，見 `test-evidence/classroom-runs/20261015T064615012164Z.json`；自動紀錄仍關閉。未操作手機，不以此冒充手機實測。
- 題庫、歷次失敗與每輪測試範圍見 [evaluation/README.md](evaluation/README.md)。舊版功能說明與歷次紀錄移至 [README-history.md](README-history.md)，Node.js版見 [README-nodejs.md](README-nodejs.md)。

老師三題：`hi`、`台灣最高的山是哪一座？多高？`、`2026 年諾貝爾物理獎得主是誰？`。可用 `python line_bot_local.py --simulate --search` 跑共用處理流程；不讀 `.env`、不改Webhook、不寫Google。參考答案僅用於評估，不傳給bot。

## 停止與交件

按Ctrl+C，等待「已恢復 W5 Apps Script」及「已停止」。之後應以手機實測雲端待辦；強制關機或斷網不保證還原。備援Apps Script僅提供待辦，不提供本機模型問答。

依原作業採較完整的交件材料：第一行公開repo連結、手機上需要查證且附來源的回答截圖、同次終端可見模型與搜尋的截圖，以及一句模型／硬體／耗時／改動與卡點。截圖不得露出金鑰、憑證內容或Apps Script私人網址。repo名稱不含姓名學號。

換更大模型、加Google功能沒有固定加分保證；真實LINE關卡B與課堂Google功能分開列證據。是否已上傳最新版本、手機端到端是否實測，都必須按實際狀態說明。
