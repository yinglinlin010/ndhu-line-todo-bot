# Product

<!-- impeccable:product-schema 1 -->

## Platform
web

## Users
LINE Bot 使用者是需要快速記下課業與生活事項的學生。開發紀錄與簡報的讀者是教師，用來評估課堂第一版與課後改善版。

## Product Purpose
待辦小幫手透過 LINE 接收「記錄：事項」，保存內容並回覆確認。改善版新增「查詢」，讓使用者能回看本人紀錄。

## Operating Context
使用者先交第一版，再交改善版。教師需要查看原本問題、修改內容、前後差異與重新測試結果，以及程式、計畫、至少兩次有意義的 commit。使用者要求以 Impeccable 重新設計排版，並明確選擇先看視覺草稿。

## Capabilities and Constraints
目前程式以 Node.js + JSONL 本機儲存運作，開發紀錄為 GitHub Pages 靜態 HTML。第一版以 classroom-v1-2026-10-05 tag 及 versions/v1/ 保留。改善版查詢只顯示本人最新 10 筆；無查詢身分時拒絕讀取。無刪除、完成狀態、定時提醒或多執行個體支援。

## Evidence on Hand
第一版 6 組本機測試原始輸出保留；改善版 14 組本機測試通過。scripts/compare-versions.mjs 實際執行封存第一版與新程式，產生前後回覆對照。尚無 LINE 真人對話截圖或短影片，不能將本機測試寫成真人測試。

## Brand Commitments
專題名稱「待辦小幫手」已由學生確認。使用者於官方 Impeccable 骰子瀏覽器頁選定「文字風暴」，以黑白字詞變化作為新版視覺方向；已選定 C「前後校訂」草稿，並通過字粒程式呈現的製作確認。以可讀、可核對的事實呈現成果，不能發明成效或完成狀態。

## Product Principles
- 記錄與查詢必須簡單，輸入不完整時明確提示。
- 前後版本可核對，原始紀錄與 commit 保留。
- 測試須列出輸入、預期、實際結果。
- LINE 真人測試未完成時持續明示。
