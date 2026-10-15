# 2026-10-16 真實手機驗收

本輪由iPhone鏡像輸出操作真正LINE聊天室，並從Google API唯讀核對結果；不是合成Webhook冒充手機。鏡像中文輸入不穩定，本輪Google指令使用程式支援的英文別名。

已完成：

- `save to sheet: W6_PHONE_GOOGLE_20261016 - manual save test only`：手機收到成功回覆，Google讀回指定內容恰好一列，自動聊天紀錄關閉。
- `Schedule W6 PHONE GOOGLE TEST on 2026-10-17 at 15:00-15:30`：只預覽，未新增事件。
- 再傳15:30–16:00候選：保留原候選，直接`confirm schedule`會阻擋；`replace schedule`後重新顯示預覽，最後`confirm schedule`才寫入。Google讀回唯一事件時間15:30–16:00，沒有建立15:00的原候選。
- 停止Python後，手機收到W5「雲端基本待辦模式」回覆。後續03:29再次停止Python並確認還原，03:32手機新增 `W6 PHONE FALLBACK TEST` 成功，03:40手機「查詢」讀回同一筆，共1筆。見 `w5-add-query-success.png`。
- `World news`：實際搜尋找到三則來源、實際呼叫E4B。摘要逐句核對未通過，透明改列原始標題，保留來源卡片；不宣稱摘要生成成功或已獨立核實事件。

圖片：`sheets-phone-success.png`、`calendar-confirm-blocked.png`、`calendar-replaced-preview.png`、`news-phone-sources.png`、`news-terminal-same-run.png`。`cloud-readback.json`只含安全布林值，不含Google私人ID或網址。Calendar建立成功的手機訊息含私人事件網址，未將該畫面存入公開證據。

後續03:27、03:42實際從手機Safari下載repo中的合成圖、存入照片，再由LINE相簿送到bot；終端確認真正照片事件及LINE下載，E4B辨識出圖上文字、日期及15:00–16:00，Drive API讀回兩張JPEG且均為私人。兩次照片預覽都取消，沒有確認新日曆事件；自動Sheets仍關閉，Sheets總列數只比驗收前多手動指定的一列。

03:28曾發現英文 `What time is on the image?` 未識別為照片追問，改走一般搜尋且錯稱沒圖片，保留 `photo-english-followup-before-fix.png`。修正明確英文圖片指涉後，重新傳相同合成圖、取消預覽，再傳完全相同問題，03:45正確回覆日期與15:00–16:00（1.06秒），03:46日期追問回覆2026-10-16（0.86秒），03:47標題追問引用「W6 E4B FUNCTION TEST」，同時說明不是明確的活動標題（1.14秒）。沒有把標題判讀成完全確定的活動名稱。三輪終端均只有本機Ollama，沒有Search紀錄，見 `photo-terminal-live.json`、`photo-followups-after-fix.png`。上述英文日期／時間問法在尚無圖片時會要求先上傳，不搜尋。

本輪110項單元測試、24項本機HTTP整合通過。Google API結果見 `cloud-readback.json`，只含安全布林值；私人Drive網址不存入公開截圖。測試圖為合成驗收資料，這些是指定案例重測，不是盲測或所有圖片問法的正確率保證。
