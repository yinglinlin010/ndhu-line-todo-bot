"""Configure the teacher's Google workflows locally; no cloud writes here."""
import getpass
import json
import os
from pathlib import Path
import re

from dotenv import dotenv_values, set_key


def main():
    root = Path(__file__).resolve().parent.parent
    os.chdir(root)
    values = dotenv_values(".env")
    owner = values.get("GOOGLE_OWNER_ID")
    state_path = Path(values.get("ELEARN_STATE_FILE") or "data/elearn.json")
    if not owner and state_path.exists():
        owner = json.loads(state_path.read_text()).get("ownerId")
    if not owner:
        owner = getpass.getpass("LINE 私聊使用者 ID（隱藏輸入，只存本機）：").strip()
    if not re.fullmatch(r"U[0-9a-fA-F]{32}", owner or ""):
        raise ValueError("Missing private owner")
    sheet = getpass.getpass("指定試算表 ID（隱藏輸入；不啟用試算表可直接 Enter）：").strip()
    if sheet and not re.fullmatch(r"[A-Za-z0-9_-]{10,200}", sheet):
        raise ValueError("Invalid spreadsheet ID")
    print("啟用後：只在你的 LINE 私聊將照片存 Drive；行程需另在 LINE 確認。試算表自動紀錄預設關閉。")
    consent = input("已完成 gws 登入並同意啟用，請輸入 ENABLE；其他輸入會取消：").strip()
    if consent != "ENABLE":
        print("已取消；未改設定。")
        return
    for key, value in {"GOOGLE_OWNER_ID": owner, "SHEET_ID": sheet, "CALENDAR_ID": "primary",
                       "PHOTO_FOLDER": "LINE待辦照片", "GOOGLE_ENABLED": "1",
                       "OLLAMA_VISION_MODEL": "gemma4:e4b-it-q4_K_M"}.items():
        set_key(".env", key, value)
    print("設定已保存到本機 .env。未上傳憑證、未寫入 Google；重新啟動 bot 後生效。")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError):
        raise SystemExit("未能保存：請確認使用者 ID、試算表 ID 和本機檔案。不要將私人值貼到聊天或截圖。")
