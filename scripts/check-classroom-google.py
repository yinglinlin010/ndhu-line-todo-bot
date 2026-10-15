"""Read-only classroom Google checks; one synthetic Sheets write is opt-in."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import dotenv_values
import line_bot_local as bot

TEST_CONTENT = "W6_CLASSROOM_SHEETS_V1：課堂版 Sheets 功能驗收；非私人對話。"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-test-row", action="store_true", help="Requires user approval: append at most one synthetic row via the bot workflow")
    args = parser.parse_args()
    config = dotenv_values(ROOT / ".env")
    for key in ("GOOGLE_WORKSPACE_CLI_CONFIG_DIR", "GWS_PATH"):
        if config.get(key):
            os.environ[key] = config[key]
    google = bot.GoogleWorkspace(sheet_id=config.get("SHEET_ID"), calendar_id=config.get("CALENDAR_ID", "primary"), folder=config.get("PHOTO_FOLDER", "LINE待辦照片"))
    checks, errors = {}, []
    owner = config.get("GOOGLE_OWNER_ID")
    if not owner:
        binding = ROOT / (config.get("ELEARN_STATE_FILE") or "data/elearn.json")
        if binding.exists():
            owner = json.loads(binding.read_text()).get("ownerId")
    checks["google_enabled"] = config.get("GOOGLE_ENABLED") == "1"
    checks["automatic_sheet_logging_off"] = config.get("ENABLE_SHEET_LOGGING") != "1"
    checks["owner_configured"] = bool(owner)
    sheet_values = []
    try:
        sheet_values = google.call("sheets", "spreadsheets", "values", "get", "--params", json.dumps(dict(spreadsheetId=google.sheet_id, range="A1:F"))).get("values", [])
        checks["sheets_readable"] = True
    except Exception:
        checks["sheets_readable"] = False
        errors.append("sheets_read_failed")
    try:
        events = google.call("calendar", "events", "list", "--params", json.dumps(dict(calendarId=google.calendar_id, q="W6 E4B 功能測試", maxResults=20))).get("items", [])
        checks["previous_calendar_test_readback"] = any(item.get("summary") == "W6 E4B 功能測試" and item.get("start", {}).get("dateTime", "").startswith("2026-10-16T15:00:00") and item.get("end", {}).get("dateTime", "").startswith("2026-10-16T16:00:00") for item in events)
    except Exception:
        checks["previous_calendar_test_readback"] = False
        errors.append("calendar_read_failed")
    try:
        state_path = ROOT / (config.get("GOOGLE_STATE_FILE") or "data/google-actions.json")
        state = json.loads(state_path.read_text())
        links = [receipt.get("result", "") for key, receipt in state.get("operations", {}).items() if key.startswith("drive:") and receipt.get("status") == "done"]
        previous_photos = []
        for link in links:
            match = re.search(r"/file/d/([A-Za-z0-9_-]+)", link)
            if match:
                value = google.call("drive", "files", "get", "--params", json.dumps(dict(fileId=match[1], fields="mimeType,shared,trashed")))
                previous_photos.append(value.get("mimeType", "").startswith("image/") and value.get("shared") is False and not value.get("trashed"))
        checks["previous_drive_test_private"] = bool(previous_photos) and all(previous_photos)
    except Exception:
        checks["previous_drive_test_private"] = False
        errors.append("drive_read_failed")
    write_result = "not_requested"
    if args.write_test_row:
        if not all(checks.get(key) for key in ("google_enabled", "owner_configured", "sheets_readable")):
            write_result = "blocked_by_readiness"
        elif any(len(row) > 2 and row[2] == TEST_CONTENT for row in sheet_values):
            write_result = "existing_test_row_preserved"
        else:
            teacher = bot.TeacherFeatures(None, google, enabled=True, owner_id=owner, sheet_logging=False,
                                          state_file=ROOT / "data/classroom-verification-actions.json")
            event = dict(webhookEventId="classroom-sheet-check-v1", replyToken="synthetic-not-a-line-token",
                         source=dict(type="user", userId=owner), message=dict(type="text", text="存試算表：" + TEST_CONTENT))
            reply = teacher.before_text(event["message"]["text"], event)
            write_result = "bot_reported_success" if reply.startswith("已將指定內容") else "write_uncertain_no_retry"
        if write_result != "blocked_by_readiness":
            try:
                rows = google.call("sheets", "spreadsheets", "values", "get", "--params", json.dumps(dict(spreadsheetId=google.sheet_id, range="A1:F"))).get("values", [])
                checks["one_synthetic_sheet_row_readback"] = sum(len(row) > 2 and row[2] == TEST_CONTENT for row in rows) == 1
            except Exception:
                checks["one_synthetic_sheet_row_readback"] = False
                errors.append("sheet_readback_failed_no_retry")
    now = datetime.now(timezone.utc)
    report = dict(time=now.isoformat(), code_sha256=hashlib.sha256((ROOT / "line_bot_local.py").read_bytes()).hexdigest(),
                  method="Read existing Google test artifacts; optional approved synthetic sheet row via TeacherFeatures, no LINE messages or phone UI",
                  checks=checks, errors=errors, write_requested=args.write_test_row, write_result=write_result,
                  limitations=["No new Drive upload or Calendar event", "Not a phone end-to-end test", "No IDs, credentials or existing cell contents included"])
    output = ROOT / "test-evidence/classroom-runs" / (now.strftime("%Y%m%dT%H%M%S%fZ") + ".json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(dict(checks=checks, errors=errors, write_result=write_result, report=str(output.relative_to(ROOT))), ensure_ascii=False))
    return 0 if all(checks.values()) and not errors and write_result not in ("blocked_by_readiness", "write_uncertain_no_retry") else 1


if __name__ == "__main__":
    raise SystemExit(main())
