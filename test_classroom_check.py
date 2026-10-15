"""Classroom verifier tests use fake Google only; no credentials or network."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("classroom_check", Path(__file__).parent / "scripts/check-classroom-google.py")
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


class GoogleStub:
    sheet_id = "synthetic-sheet"
    calendar_id = "primary"

    def __init__(self):
        self.rows, self.writes = [], 0

    def call(self, *args):
        if args[0] == "sheets":
            return dict(values=self.rows)
        if args[0] == "calendar":
            return dict(items=[dict(summary="W6 E4B 功能測試", start=dict(dateTime="2026-10-16T15:00:00+08:00"), end=dict(dateTime="2026-10-16T16:00:00+08:00"))])
        return dict(mimeType="image/jpeg", shared=False, trashed=False)

    def write_sheet(self, row):
        self.writes += 1
        self.rows.append(row)
        return True


class ClassroomCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "data").mkdir()
        (self.root / "line_bot_local.py").write_text("synthetic code")
        (self.root / "data/google-actions.json").write_text(json.dumps(dict(operations={"drive:test": dict(status="done", result="https://drive.google.com/file/d/test-only/view")})))
        self.google = GoogleStub()
        self.config = dict(GOOGLE_ENABLED="1", GOOGLE_OWNER_ID="synthetic-owner", SHEET_ID="synthetic-sheet", ENABLE_SHEET_LOGGING="0")

    def tearDown(self):
        self.temp.cleanup()

    def run_check(self, write=False):
        argv = ["check"] + (["--write-test-row"] if write else [])
        with patch.object(check, "ROOT", self.root), patch.object(check, "dotenv_values", return_value=self.config), patch.object(check.bot, "GoogleWorkspace", return_value=self.google), patch.object(check.sys, "argv", argv), patch("builtins.print"):
            return check.main()

    def test_default_check_never_writes(self):
        self.assertEqual(self.run_check(), 0)
        self.assertEqual(self.google.writes, 0)

    def test_explicit_test_write_is_read_back_and_not_repeated(self):
        self.assertEqual(self.run_check(write=True), 0)
        self.assertEqual(self.run_check(write=True), 0)
        self.assertEqual(self.google.writes, 1)
        self.assertEqual(self.google.rows[0][2], check.TEST_CONTENT)

    def test_disabled_google_blocks_even_explicit_write(self):
        self.config["GOOGLE_ENABLED"] = "0"
        self.assertEqual(self.run_check(write=True), 1)
        self.assertEqual(self.google.writes, 0)


if __name__ == "__main__":
    unittest.main()
