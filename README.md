# 本機 Ollama LINE Bot — W7 Apps Script 轉接版

公開 repo：https://github.com/yinglinlin010/ndhu-line-todo-bot

本次 W7 版本已完成 Apps Script 固定入口的真實手機搜尋測試：[完整手機問題與來源](test-evidence/w7-submission-20261019/phone.png)、[同次轉接站畫面](test-evidence/w7-submission-20261019/terminal.png)、[交件文字](test-evidence/w7-submission-20261019/SUBMISSION.txt)。W6 關卡 B 舊證據保留於 `test-evidence/submission-20261018/`。

LINE 文字與照片交由自己電腦上的 **Gemma 4 E4B** 處理；需要時搜尋附來源。支援照片存私人 Google Drive、行程確認後寫 Calendar、指定內容寫 Sheets。文字與圖片使用 `gemma4:e4b-it-q4_K_M`，下載約6.6GB；本機已用 Python 3.12 測試。

## W7：固定雲端入口與本機模型

LINE Webhook 固定指向 Apps Script。雲端處理「記錄：事項」與「查詢」，「查 問題」明確進入本機網路查證並附來源；其他 AI 問答、照片與 Google 流程也可交給本機。手機與同時刻轉接站證據見 [W7 驗收](test-evidence/w7-submission-20261019/README.md)。

**相對老師版本的修改**：依使用者選擇保留手動保存，普通聊天不自動記成待辦或寫入試算表；保留一般 AI 聊天與照片等既有功能。老師的轉接站回傳答案給 Apps Script 再回 LINE，本版由 Python 背景佇列直接回 LINE，讓雲端入口不等待模型生成。這些差異不冒充原版逐字實作。

W7 設定順序（從全新安裝開始仍需先完成下方 Python／Ollama 安裝）：

1. 將 `apps-script/Code.gs` 與 `apps-script/appsscript.json` 放入自己的 Apps Script 專案，依 [部署與安全設定](apps-script/README.md) 設定私人指令碼屬性並部署。
2. 本機 `.env` 設定自己的 LINE token／secret、`GOOGLE_OWNER_ID`、`APPS_SCRIPT_BOT_ID`、`W5_WEBHOOK_URL`，以及 `APPS_SCRIPT_RELAY_MODE=1`、`APPS_SCRIPT_RELAY_KEY`。轉送金鑰需為獨立隨機的64位十六進位字串，與指令碼屬性 `LOCAL_RELAY_KEY` 一致；不可使用 LINE secret。
3. 指令碼屬性設 `ENABLE_LOCAL_RELAY=1`。將 LINE Webhook 指向自己的 Apps Script 私密入口，再執行 `python scripts/run-bot.py`。管理程序會核對既有 Webhook、建立 HTTPS 通道並自動同步雲端 `LOCAL_RELAY_BASE`；不需每次重部署或改 LINE 網址。
4. 在 LINE 傳「查 台灣最高的山是哪一座？多高？」；公開查證應回覆並附來源。輸入「記錄：事項」「查詢」測雲端待辦。Google 功能另需下方的私人授權設定，搜尋問答不需 Google Drive／Calendar／Sheets 授權。

金鑰、試算表 ID、通道網址與完整 Apps Script 私密網址均不可提交 repo 或出現在截圖。轉送以時間戳＋HMAC 驗證，僅本人私聊；Apps Script 本身仍無法取得 LINE 原始驗簽標頭，秘密入口網址限制仍是私人原型的限制。本機關機／睡眠後只有雲端待辦可用，不能保證全天 AI 在線。

日常日誌不印問題內容。僅公開題目截圖示範時可用 `LOG_PUBLIC_SEARCH_QUESTIONS=1 python scripts/run-bot.py` 顯示公開搜尋題，完成後以未設定該環境變數的指令重新啟動；不要在這個模式傳私人問題。

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

目前本機設定採 Apps Script 固定入口：雲端「記錄：事項／查詢」獨立運作，其餘 AI 與照片轉交本機 Python。啟動管理程序會同步通道網址；電腦離線時不提供本機 AI。轉送設定與驗收界線見 [Apps Script 說明](apps-script/README.md)。

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

- 問文字問題：概念、推導、翻譯使用本機模型知識；現任人物、最新獎項、新聞與研究論文走網路查證，提供來源。明確規則優先，其餘由本機模型判斷意圖；資訊不足時先釐清。回覆尾端標示實際資料來源；接續改寫會標示沿用先前網路來源。意圖分類失敗時先釐清，不退回公開搜尋。
- 查私人資料：「我的待辦有哪些」讀本機待辦；「查試算表」讀設定的表格，最多檢查前1000筆並顯示最後10筆；「我明天有什麼行程」讀當天Calendar，「查日曆」讀未來14天最多10筆。Google查詢限綁定者私聊，不做公開搜尋，不新增紀錄。支援「查日曆2026-10-25」「我的下週行程有哪些」、本週／上週、中文月日與幾天後；日期以台灣時區解析、結束時間不包含在區間內。不存在或混合多個日期時先釐清，不改查其他期間。未指定資源的「我上次存了什麼」先詢問要查哪裡。
- 「Google試算表是什麼」屬工具知識，不會讀私人表格。諾貝爾研究題使用指定年份官方研究頁面，背景PDF由有大小、頁數與執行時間限制的獨立程序擷取參考文獻；可核對的期刊文獻再向Crossref比對期刊、年份、卷與頁／文章編號，吻合才列題名和DOI。文獻節選不代表唯一得獎論文，也不代表已逐篇閱讀全文。
- ChatGPT／OpenAI價格問題使用官方API計價文件，先區分ChatGPT訂閱與API用量計費，不把兩者的費率混用；模型與用量不明時先釐清，不猜價格。
- 傳照片：本機模型辨識，綁定者私聊的照片存私人Drive；照片有日期時間時先顯示待確認行程。
- 傳「明天下午三點開會」：解析並核對日期，回覆「確認排程」才建立Calendar事件；「取消排程」放棄，20分鐘後失效，不寄邀請。
- 傳「存試算表：要保存的內容」：只將指定內容寫一列到現有私人試算表；保留寫入收據，避免同一事件重送。使用RAW，文字不當作公式。
- 也可使用英文：`save to sheet: content`、`confirm schedule`、`cancel schedule`、`replace schedule`、`keep original schedule`。英文建立行程需明確日期時間，例如 `Schedule W6 phone test on 2026-10-17 at 15:00`；仍只預覽，確認後才寫入，綁定者限制相同。
- 一般聊天、照片及行程的**自動Sheets紀錄維持關閉**（`ENABLE_SHEET_LOGGING=0`），符合使用者不自動保存聊天的設定。手動保存不會改動這個開關。
- 傳「記錄：事項」「查詢」使用本機私人待辦；不等同於雲端Apps Script待辦。傳「清除對話」清掉自己的短期對話記憶，不刪待辦或Google資料。

Google寫入只接受綁定者個人聊天；其他人與群組不會寫入你的Google帳號。回應不明時不自動重試或宣稱成功，需要核對Google實際內容。

一般AI文字與照片回覆附本機模型設定及本題處理時間；時間包含該次處理中的搜尋／模型／Google操作，不包含工作排隊或LINE送出耗時，也不代表每則固定提示都曾呼叫模型。

## 你改了什麼

以既有Node.js專案移植成Python，並對照老師提供的 `line_bot_local.py` 完成課堂功能；不是逐字複製老師程式。

- 使用同一E4B本機模型處理文字與照片；保留短期對話、圖片文字追問及跨重啟記憶，私人圖片描述不送公開搜尋。
- 搜尋使用公開服務、官方頁面及分類RSS；與老師使用Ollama experimental搜尋工具的方式不同。諾貝爾／總統身分題有專用官方查核，並非純模型記憶測驗。
- 新聞依分類與發布日期篩選；導讀只接受完整來源標題或前言句子，引用錯誤或改動事實時改列原始標題。這是來源文字一致性檢查，不能保證發布者報導為真。
- 英文新聞與中文共用分類RSS和日期規則；英文最高山高度題先轉換查詢意圖，不在查詢中插入山名或答案。高度來源需有數字單位，最高山來源以首句主題判斷，排除僅在比較段落提到最高山的其他山岳文章。單純「它的高度」等追問保留原題主題描述，不讓模型改成新名字。
- 同期相同標題採保守去重，保留其他媒體連結；不把僅僅近似的標題任意合併。
- 老師原版自動排日曆；本版增加使用者確認、日期驗算及持久去重。老師原版可記錄所有問答；本版預設不自動記錄，保留指定內容手動保存及可選的自動紀錄能力。
- 管理程序提供通道重建與Webhook安全還原；簽章驗證、使用者隔離、下載大小限制與安全日誌均保留。

## 測試與驗收界線

```sh
python -m unittest test_line_bot_local test_teacher_features test_service test_evaluate_faq test_classroom_check test_reliability test_phone_regressions test_query_sources
python scripts/check-live-quality.py
python scripts/check-news-followups.py
python scripts/check-classroom-google.py
```

最後一個指令預設僅讀取現有測試資料，不寫入Google。`--write-test-row` 是另行批准後才使用的一筆合成Sheets驗收；不會新增照片或行程、不開啟自動紀錄。驗收結果只包含安全布林值，不公開私人ID、網址或表格原內容。

- 既有E4B雲端實測已成功上傳合成圖片、確認私人權限，並建立及讀回Calendar測試行程，見 `test-evidence/e4b-cloud-live-check.json`。
- 既有真實LINE文字測試包括老師玉山與諾貝爾原題、翻譯、換題及重啟接續，見 `test-evidence/line-quality-live.json`。這些不是最新版功能的手機端到端驗證。
- 最新130項自動測試通過，包含英文Google指令的綁定者與確認限制。此前24項本機HTTP整合通過，包含連續傳圖追問、跨使用者處理、排隊逾時、逾時禁止後續寫入及行程取代保護。此前真實E4B行程日期／時間解析紀錄仍保留。
- 最新Google唯讀檢查再次確認既有測試圖片、行程及試算表可讀。經使用者同意，已透過bot流程新增一筆合成Sheets驗收紀錄並讀回，確認只出現一次，見 `test-evidence/classroom-runs/20261015T064615012164Z.json`；自動紀錄仍關閉。未操作手機，不以此冒充手機實測。
- 2026-10-16 03:11–03:14 新增真實手機驗收：手動Sheets寫入後讀回只有一列；Calendar經預覽、兩候選阻擋確認、選擇取代及再次確認後，讀回只有一筆 `W6 PHONE GOOGLE TEST`，時間為2026-10-17 15:30–16:00（台灣時間）。本輪109項單元與24項本機HTTP整合均通過。安全證據見 [手機Google驗收](test-evidence/google-phone-20261016/README.md)。該時段尚未驗收照片手機→Drive與W5新增／查詢；後續完成結果如下。
- 2026-10-16 03:27–03:48 補完真實手機照片與W5驗收：合成圖從手機LINE傳送、下載、本機E4B辨識並存私人Drive，修正前後各一張；照片行程只預覽並取消。修正英文圖片追問後，同一張圖的時間、日期與文字標題可連續詢問，終端沒有公開搜尋。停止Python後，手機W5新增測試待辦並查詢讀回1筆，未修改Apps Script部署。110項單元與24項本機HTTP整合通過。這是指定案例回歸驗收，不代表所有圖片與問法均正確。
- 2026-10-18 來源分流：首次純模型分類8/10；加入私人讀取與穩定知識規則後，針對相同10題重新測試通過。這是調整後定向回歸，不是盲測準確率或模型權重訓練。Google試算表與日曆唯讀API均通過；本輪24項本機HTTP整合亦通過（實際模型與搜尋、攔截送出回覆，無LINE傳送或Google寫入）；這輪尚未宣稱真實手機端到端測試。見 `test-evidence/source-routing-20261018.json` 與 `test-evidence/private-reads-20261018.json`。
- 題庫、歷次失敗與每輪測試範圍見 [evaluation/README.md](evaluation/README.md)。舊版功能說明與歷次紀錄移至 [README-history.md](README-history.md)，Node.js版見 [README-nodejs.md](README-nodejs.md)。

老師三題：`hi`、`台灣最高的山是哪一座？多高？`、`2026 年諾貝爾物理獎得主是誰？`。可用 `python line_bot_local.py --simulate --search` 跑共用處理流程；不讀 `.env`、不改Webhook、不寫Google。參考答案僅用於評估，不傳給bot。

2026-10-18 15:28–15:39 中文手機實測16個案例及1次圖片複測，見 `test-evidence/submission-20261018/validation.json`。已驗證模型／網路／私人資料分流與接續；圖片來源標示錯誤已修正後重測。價格查證未命中、原始論文題名與DOI未核對，均保留限制，不宣稱全功能通過。本輪沒有重做Google寫入或W5手機驗收。

2026-10-18 追加補強：日期／週範圍已接上真正Google唯讀查詢，指定10/17讀回既有測試行程，下週正確使用10/19–10/26。官方PDF參考文獻已擷取，相關原始論文書目與DOI已向Crossref核對，見 `test-evidence/nobel-papers-verified-20261018.json`。計價題已取得官方API文件並區分訂閱，見 `test-evidence/query-gaps-live-20261018.json`。此追加版130單元與24本機HTTP整合通過；20:39–20:41再以中文手機完成指定日期、下週、計價公式、論文與DOI四項複測，見 `test-evidence/submission-20261018/validation.json`，保留先前失敗紀錄。
