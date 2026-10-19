# LINE 基本待辦雲端備援

這是新增的 Apps Script 備援，並非找回原先不存在的 W5 部署。只供設定的 LINE 綁定者私聊使用。

- `記錄：事項`：儲存最多 300 字的待辦，最多 100 筆。
- `查詢`：顯示最新 10 筆。
- 其他文字：顯示操作說明。

資料放在該 Apps Script 的指令碼屬性，不會把招呼或查詢寫到 Google Sheets。它不執行 Ollama、不搜尋新聞、不辨識照片、不查 e學苑，也不新增行程；上述功能仍由電腦的 Python bot 提供。雲端待辦與本機 JSONL 是兩份資料，目前不會自動同步，也不匯入私人歷史資料。

## 安裝與部署

1. 在 Apps Script 建立專案，貼入 `Code.gs`。
2. 在專案設定顯示 manifest，使用 `appsscript.json`；只需對外 HTTP 請求權限。
3. 在指令碼屬性設定 `LINE_CHANNEL_ACCESS_TOKEN`、`OWNER_ID`、`BOT_ID`、`WEBHOOK_KEY`。密鑰需為獨立隨機產生的 64 位十六進位字串，不能使用 LINE channel secret。
4. 執行 `checkConfiguration` 檢查，不會發送 LINE 訊息或新增待辦。
5. 新增「網頁應用程式」部署，以本人執行，允許 LINE 不登入 Google 即可呼叫。此步需確認公開入口與執行權限。
6. 部署網址需附上 `?key=` 加上私密 Webhook key，完整網址只能保存於本機與 LINE Console，不得提交 GitHub、貼到聊天或作業截圖。

## 入口保護限制

Apps Script 的 `doPost(e)` 不提供 LINE 的 `x-line-signature` header，所以此直接部署不能完成 LINE 標準驗簽。它改以秘密網址 key、bot ID 與固定私聊 owner 限制處理範圍。網址 key 外洩後，攻擊者可能偽造事件污染待辦；因此此版本只適合私人課堂原型。提供一般使用者服務前，需加上能檢查 LINE 簽章的雲端入口。不要刪掉 key 檢查來圖方便。

正常退出 Python 時切回這個已設定的備援即可讓基本待辦保持運作；重新啟動本機模型時需將 LINE Webhook 切回公開通道。切換前後皆需實際私聊測試，不能將本機測試當成雲端部署成功。

## 驗證

```sh
node --test apps-script/basic.test.mjs
```

原有4項本機測試涵蓋儲存／查詢、事件去重、非 owner／群組／錯誤 key／錯誤 bot 拒絕、長度與數量上限。測試不寫真實雲端，不發送 LINE。

參考：[Google 網頁應用程式](https://developers.google.com/apps-script/guides/web)、[指令碼屬性](https://developers.google.com/apps-script/guides/properties)、[LINE 驗簽](https://developers.line.biz/en/docs/messaging-api/verify-webhook-signature/)。

## 本次部署驗證

2026-10-12 已完成學校帳號部署、匿名 GET／空事件 POST 執行確認、LINE 官方 Webhook 驗證。19:40 正常停止 Python 時，LINE endpoint 已恢復到私密備援；重啟後已切回本機通道，皆讀回一致。2026-10-16 03:29 停止Python並確認還原後，03:32手機傳送「記錄: W6 PHONE FALLBACK TEST」，收到成功回覆；03:40傳送「查詢」，讀回同一筆雲端待辦，共1筆。本輪未修改部署或權限，證據見 `../test-evidence/google-phone-20261016/w5-add-query-success.png`。

## 本機 AI 轉送模式

流程：LINE → 現有私人 Apps Script → HTTPS 通道 → Python `/apps-script` → 原有處理佇列 → 本機 Ollama。Python 仍直接回覆 LINE；Apps Script 不執行模型。不需要付費模型 API，但電腦、Python、Ollama、通道都必須保持開啟。

2026-10-19 經使用者同意更新現有部署並建立專用轉送金鑰。LINE Webhook 固定指向既有 Apps Script，電腦不再接管 LINE Webhook。雲端到本機的簽章探測已真實通過；手機對話驗收另行記錄，不以探測冒充。

核准後配置（值不可提交 repo）：

- 本機 `.env`：`APPS_SCRIPT_RELAY_MODE=1`、`APPS_SCRIPT_RELAY_KEY`（新產生的64位十六進位字串）、`APPS_SCRIPT_BOT_ID`、既有 `GOOGLE_OWNER_ID`。
- Apps Script 指令碼屬性：`ENABLE_LOCAL_RELAY=1`、`LOCAL_RELAY_KEY`（同一轉送金鑰）、`LOCAL_RELAY_BASE`（目前的 HTTPS trycloudflare 通道根網址，不含斜線）。
- 原有 `WEBHOOK_KEY`、LINE token、owner、bot 設定維持。LINE Webhook 指向現有 Apps Script 私密入口。本機轉送模式會核對這一點，不自行切換入口。
- 管理程序在每次啟動及通道重建後，用獨立簽章向 Apps Script 註冊新的 `LOCAL_RELAY_BASE`；註冊未確認則停止本次啟動。手動啟動 Python 而未使用管理程序時，仍需自行更新網址。

只允許設定的本人一對一文字／照片事件。Apps Script 對原始事件以獨立金鑰和時間戳簽章；Python 驗證60秒有效期限、owner、bot和事件ID，再沿用既有去重及功能。這個轉送簽章僅證明事件經過 Apps Script，不能補回原始 LINE 驗簽；原本秘密網址外洩風險仍存在，因此限私人原型。

「記錄：事項」與「查詢」固定由雲端待辦處理，不依賴模型。其他文字／照片在本機離線時收到明確離線提示；本機拒絕排隊時收到忙碌提示。事件已送出但結果不明：不再新增雲端待辦或重複回覆，避免兩份資料及重複寫入；不保證每次故障都能收到提示。雲端與本機待辦仍是兩份資料，不會自動同步。

驗證：`python -m unittest test_apps_script_relay`，`node --test apps-script/basic.test.mjs`。這些是本機測試，不代表真實部署或手機轉送驗收完成。

參考 [W7 觀念教材](https://cwstedctw.github.io/ndhu-ted-course-hub/weekly/11501-ai-coding/w07/concepts.html)：沿用固定雲端 Webhook、待辦獨立、模型在本機的分工。本版額外支援照片、原有私人 Google 流程、簽章轉送與通道自動同步；目前仍非一般使用者用的完整 LINE 驗簽閘道。

2026-10-19 追加驗收：修正中文 payload 的 UTF-8 位元組與簽章不一致（真實雲端健康檢查200但轉送401）。改為明確UTF-8簽章、位元組payload後，真實 Apps Script → Python 收件200，Gemma完成合成慣性題約5.4秒。測試使用無效回覆碼，LINE回400、未送達，不冒充手機驗收。基礎概念誤判搜尋亦已修正，慣性與精簡追問兩項真實模型複測通過；初始失敗保留。137項Python與12項Apps Script本機測試通過。

2026-10-19 10:45:33–10:45:34：使用者確認已由手機傳送訊息後，本機記錄顯示實際收件、model分流、Gemma回答完成約0.7秒、LINE回覆API狀態200。這次不是合成事件；未擷取手機畫面，亦不以API成功代替答案內容正確性驗證。安全紀錄：`../test-evidence/apps-script-relay-phone-20261019.json`。

2026-10-19 10:57:55–10:58:03：已完成真實手機「查 台灣最高的山是哪一座？多高？」；手機同時顯示完整問題、玉山3,952公尺、來源卡與8.61秒，轉接站顯示搜尋、Gemma生成7.1秒與LINE回覆200。[完整原始截圖及測試界線](../test-evidence/w7-submission-20261019/README.md)。最終本機檢查為138項Python、12項Apps Script測試通過；公開題目日誌僅在截圖測試時暫時開啟。
