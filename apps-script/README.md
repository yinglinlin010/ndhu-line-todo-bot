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

4 項本機測試涵蓋儲存／查詢、事件去重、非 owner／群組／錯誤 key／錯誤 bot 拒絕、長度與數量上限。測試不寫真實雲端，不發送 LINE。

參考：[Google 網頁應用程式](https://developers.google.com/apps-script/guides/web)、[指令碼屬性](https://developers.google.com/apps-script/guides/properties)、[LINE 驗簽](https://developers.line.biz/en/docs/messaging-api/verify-webhook-signature/)。

## 本次部署驗證

2026-10-12 已完成學校帳號部署、匿名 GET／空事件 POST 執行確認、LINE 官方 Webhook 驗證。19:40 正常停止 Python 時，LINE endpoint 已恢復到私密備援；重啟後已切回本機通道，皆讀回一致。雲端新增待辦與查詢仍須手機實測。
