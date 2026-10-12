"""Save the W5 URL locally with hidden input; never send it to LINE or Git."""
import getpass
import os
from pathlib import Path
from urllib.parse import urlsplit
import re

from dotenv import set_key


def main():
    directory = Path(__file__).resolve().parent.parent
    os.chdir(directory)
    value = getpass.getpass("貼上原本 W5 Apps Script Webhook 網址（隱藏输入，不會公開）：").strip()
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or parsed.hostname != "script.google.com"
            or parsed.port not in (None, 443) or parsed.username or parsed.password
            or not re.fullmatch(r"(?:key=[a-f0-9]{64})?", parsed.query) or parsed.fragment
            or not re.fullmatch(r"/macros/s/[^/]+/exec", parsed.path)):
        raise ValueError("Invalid W5 URL")
    set_key(".env", "W5_WEBHOOK_URL", value)
    print("已保存到本機 .env，未更改 LINE Webhook。")
    print("重新啟動 Python bot 後，正常 Ctrl+C 退出會恢復 W5。請確認恢復成功並測試 W5 待辦。")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError):
        raise SystemExit("未能保存：請確認是原本 Apps Script 部署的 HTTPS Webhook 網址。")
