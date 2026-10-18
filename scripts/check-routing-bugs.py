"""Isolated bug reproductions: synthetic records, captured lookups, no external IO."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import line_bot_local as bot
from test_teacher_features import FakeAI, FakeGoogle, event
from test_line_bot_local import NOW

rows = []
with tempfile.TemporaryDirectory(prefix='routing-audit-') as directory:
    root = Path(directory)
    google = FakeGoogle()
    google.read_sheet = Mock(return_value=[['時間', '類型', '內容'], ['synthetic-date', '手動', 'SYNTHETIC_OLD_ROW']])
    google.read_calendar = Mock(return_value=[])
    teacher = bot.TeacherFeatures(FakeAI(), google=google, enabled=True, owner_id='alice',
        state_file=root/'actions.json', clock=lambda: NOW, sheet_logging=False)
    q = '存試算表：我今天有哪些行程？'
    answer = teacher.before_text(q, event(q, 'audit-manual'))
    rows.append(dict(case='explicit_save_intercepted_by_read', question=q, expected='one explicit sheet write',
        actual_answer=answer, cloud_writes=len(google.calls), sheet_reads=google.read_sheet.call_count, calendar_reads=google.read_calendar.call_count,
        reproduced=len(google.calls)==0 and google.read_sheet.call_count==1))
    google.read_calendar.reset_mock()
    q = 'show my calendar tomorrow'
    answer = teacher.before_text(q, event(q, 'audit-tomorrow'))
    rows.append(dict(case='english_tomorrow_ignored', question=q, expected='tomorrow only or clarification',
        actual_answer=answer, read_arguments=[dict(start=a.start.isoformat(),end=a.end.isoformat(),label=a.label) if isinstance(a,bot.CalendarPeriod) else a for a in google.read_calendar.call_args.args],
        reproduced=google.read_calendar.call_args.args==(None,)))
    school = Mock(return_value='SYNTHETIC_SCHOOL_REPLY')
    replies=[]
    runtime=bot.BotRuntime('synthetic-secret','',bot.TodoStore(root/'todos.jsonl'),bot.LocalAI(),teacher=teacher,
        elearn=SimpleNamespace(handle=school),sender=lambda e,a:replies.append(a))
    q='我的e學苑待辦有哪些'
    runtime.submit(event(q,'audit-school'));runtime.close()
    rows.append(dict(case='explicit_school_bypassed',question=q,expected='school handler',actual_answer=replies[0],
        school_calls=school.call_count,reproduced=school.call_count==0))
    ai=bot.LocalAI()
    ai.lookup=Mock(return_value=[])
    ai.classify_source=Mock(return_value='private')
    q='查一下今天存在表裡的客戶電話'
    answer=ai.ask(q,'synthetic-private')
    rows.append(dict(case='implicit_personal_current_record_public_search',question=q,
        expected='private clarification',actual_answer=answer,public_lookups=ai.lookup.call_count,
        classifier_calls=ai.classify_source.call_count,reproduced=ai.lookup.call_count==1))
report=dict(method='Synthetic isolated control-flow reproductions; fake Google and school APIs; mocked public lookup; no .env, real LINE, network, or Google writes',cases=rows)
path=ROOT/'test-evidence/ralph-bug-hunt-20261018.json'
path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
for row in rows:
    print(row['case'], 'REPRODUCED' if row['reproduced'] else 'NOT REPRODUCED')
print(path.relative_to(ROOT))
