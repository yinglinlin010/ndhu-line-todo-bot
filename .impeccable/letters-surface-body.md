# 文字風暴開發紀錄

Mode: Read.
Approved comp: .impeccable/mocks/letters-c.png
User approval: 瀏覽器選擇 optionId letters-c；聊天回覆「選好了」。

## Direction contract
THESIS: 以相同輸入的前後回覆為中心，讓文字風暴成為頁框而非干擾正文。
OWN-WORLD: 黑白與銀灰；巨大粗體「記錄／查詢」字詞拆散成小字流，正文保持清晰。細線、開放比較欄、無彩色卡片。
STORY: 看懂指令字詞，直接比較第一版與改善版，再核對四項開發紀錄與本機測試證據。
FIRST VIEWPORT: 精簡頂部導覽；整寬大型字詞頁首，下方正式標題與用途；中央共同輸入「查詢」，左右並排前後回覆；再接左側問題／修改與右側測試表。
FORM: Alphabet Storm；使用者在種子45547134的挑戰者中選定文字風暴，再選C前後校訂，不沿用原B版。
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Requirements
保留第一版tag、原始文件與測試；Bot功能不改。14組本機測試與LINE真人待完成均需明示。圖中「最新1筆」是字樣錯誤；正式功能最多10筆，範例僅存1筆。比較與測試回覆使用實際log。

## Interaction and motion
字詞微粒在頁首輕微流動；正文不動。尊重prefers-reduced-motion，離開視窗停止動畫。所有章節與證據維持原生連結與可選取文字。
