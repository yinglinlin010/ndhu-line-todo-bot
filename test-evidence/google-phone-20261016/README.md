# 2026-10-16 真實手機驗收

本輪由iPhone鏡像輸出操作真正LINE聊天室，並從Google API唯讀核對結果；不是合成Webhook冒充手機。鏡像中文輸入不穩定，本輪Google指令使用程式支援的英文別名。

已完成：

- `save to sheet: W6_PHONE_GOOGLE_20261016 - manual save test only`：手機收到成功回覆，Google讀回指定內容恰好一列，自動聊天紀錄關閉。
- `Schedule W6 PHONE GOOGLE TEST on 2026-10-17 at 15:00-15:30`：只預覽，未新增事件。
- 再傳15:30–16:00候選：保留原候選，直接`confirm schedule`會阻擋；`replace schedule`後重新顯示預覽，最後`confirm schedule`才寫入。Google讀回唯一事件時間15:30–16:00，沒有建立15:00的原候選。
- 停止Python後，手機收到W5「雲端基本待辦模式」回覆。雲端新增／查詢尚未看到手機證據，不能當作通過。
- `World news`：實際搜尋找到三則來源、實際呼叫E4B。摘要逐句核對未通過，透明改列原始標題，保留來源卡片；不宣稱摘要生成成功或已獨立核實事件。

圖片：`sheets-phone-success.png`、`calendar-confirm-blocked.png`、`calendar-replaced-preview.png`、`news-phone-sources.png`、`news-terminal-same-run.png`。`cloud-readback.json`只含安全布林值，不含Google私人ID或網址。Calendar建立成功的手機訊息含私人事件網址，未將該畫面存入公開證據。

尚待：真正手機傳送合成測試圖→LINE下載→本機視覺→私人Drive，及W5待辦新增與查詢。既有Drive合成流程實測不能代替本輪手機測試。
