"""Isolated HTTP integration checks using real Ollama/search, never LINE sends or Google writes.
Run: .venv/bin/python scripts/check-live-quality.py
"""
import base64
import hashlib
import hmac
import io
import json
from pathlib import Path
import queue
import re
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import requests
from PIL import Image, ImageDraw, ImageFont
from werkzeug.serving import make_server
import line_bot_local as bot


def text(answer):
    return answer if isinstance(answer, str) else '\n'.join(m.get('text', '') for m in answer if m.get('type') == 'text')


def sources(answer):
    return sorted(set(re.findall(r'"uri": "(https://[^" ]+)"', json.dumps(answer, ensure_ascii=False))))


def main():
    rows = []
    with tempfile.TemporaryDirectory(prefix='line-quality-') as folder:
        root = Path(folder)
        replies = queue.Queue()
        ai = bot.LocalAI(memory_path=root / 'memory.json')
        photos = bot.Photos('https://quality.example', root / 'photos')
        ai.photos = photos
        runtime = bot.BotRuntime('synthetic-test-secret', '', bot.TodoStore(root / 'todos.jsonl'), ai,
                                 photos=photos, sender=lambda event, answer: replies.put((event['webhookEventId'], answer)))
        server = make_server('127.0.0.1', 0, bot.create_app(runtime), threaded=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = 'http://127.0.0.1:' + str(server.server_port)
        def post(payload, valid=True):
            raw = json.dumps(payload, ensure_ascii=False).encode()
            signature = base64.b64encode(hmac.new(b'synthetic-test-secret', raw, hashlib.sha256).digest()).decode() if valid else 'invalid'
            return requests.post(base + '/webhook', data=raw, headers={'x-line-signature': signature}, timeout=5)
        def check(name, question, verify, user='synthetic-A', message=None):
            event = dict(type='message', webhookEventId='quality-' + str(len(rows)), replyToken='synthetic-reply',
                         source=dict(type='user', userId=user), message=message or dict(type='text', text=question))
            started = time.monotonic()
            response = post(dict(events=[event]))
            ack = round(time.monotonic() - started, 3)
            try:
                event_id, answer = replies.get(timeout=65)
                passed = response.status_code == 200 and ack < 1 and event_id == event['webhookEventId'] and bool(verify(answer))
                row = dict(case=name, question=question, passed=passed, ack_seconds=ack,
                           total_seconds=round(time.monotonic() - started, 2), answer=text(answer), sources=sources(answer))
            except queue.Empty:
                row = dict(case=name, question=question, passed=False, error='No captured reply before deadline')
            rows.append(row)
            print(name, 'PASS' if row['passed'] else 'FAIL', flush=True)
            return event
        try:
            rows.append(dict(case='invalid_signature', passed=post(dict(events=[]), False).status_code == 401))
            rows.append(dict(case='malformed_events', passed=post(dict(events='invalid')).status_code == 400))
            duplicate = check('greeting', 'hi', lambda a: '你好' in text(a))
            post(dict(events=[duplicate]))
            try:
                replies.get(timeout=0.3)
                dedup = False
            except queue.Empty:
                dedup = True
            rows.append(dict(case='webhook_duplicate', passed=dedup))
            check('todo_add', '記錄：整合測試專用事項', lambda a: '記' in text(a))
            check('todo_isolation', '查詢', lambda a: '整合測試專用事項' not in text(a), user='synthetic-B')
            check('todo_reopen', '查詢', lambda a: '整合測試專用事項' in text(a))
            check('teacher_mountain', '台灣最高的山是哪一座？多高？', lambda a: '玉山' in text(a) and bool(re.search(r'3,?952', text(a))) and bool(sources(a)))
            check('teacher_nobel', '2026 年諾貝爾物理獎得主是誰？', lambda a: '2026' in text(a) and any(urlsplit(u).hostname == 'api.nobelprize.org' for u in sources(a)))
            check('translation', '翻成英文', lambda a: 'Nobel' in text(a) and not re.search(r'[\u4e00-\u9fff]', text(a)) and bool(sources(a)))
            check('new_topic', '解釋牛頓第二定律', lambda a: ('牛頓' in text(a) or 'F' in text(a)) and not sources(a) and 'Nobel' not in text(a))
            check('concise', '簡短一點', lambda a: len(text(a)) <= 100 and '\n' not in text(a) and not sources(a))
            ai = bot.LocalAI(memory_path=root / 'memory.json', photos=photos)
            runtime.ai = ai
            check('persisted_followup', '翻成英文', lambda a: ('force' in text(a).lower() or 'newton' in text(a).lower()) and 'Nobel' not in text(a))
            check('clear', '清除對話', lambda a: '已清除' in text(a))
            check('pronoun_after_clear', '給我他的照片', lambda a: '補上名稱' in text(a))
            check('unknown_factual_search', '搜尋 qzxv847293649不存在的測試獎項得主', lambda a: '沒有找到' in text(a) and not sources(a))
            event = check('public_photo', '給我周星馳的照片', lambda a: isinstance(a, list) and any(m.get('type') == 'image' for m in a))
            images = list((root / 'photos').glob('*.jpg'))
            rows.append(dict(case='public_photo_served', passed=bool(images) and all(requests.get(base + '/photos/' + p.name, timeout=5).status_code == 200 for p in images)))
            if len(sys.argv) == 3 and sys.argv[1] == '--vision-fixture':
                image = Path(sys.argv[2]).read_bytes()
            else:
                fixture = Image.new('RGB', (1000, 450), 'white')
                ImageDraw.Draw(fixture).multiline_text((40, 40),
                    'SYNTHETIC TEST MEETING\nDate: 2026-10-16\nTime: 15:00-16:00\nThis is test data.',
                    font=ImageFont.load_default(size=38), fill='black', spacing=20)
                buffer = io.BytesIO()
                fixture.save(buffer, 'PNG')
                image = buffer.getvalue()
            teacher = bot.TeacherFeatures(ai, enabled=False, sheet_logging=False,
                token='', http=lambda *a, **k: image, state_file=root / 'google.json')
            runtime.teacher = teacher
            check('vision_fixture', 'synthetic image fixture', lambda a: '2026' in text(a) and '無法辨識' not in text(a) and '未上傳 Google Drive' in text(a),
                  message=dict(type='image', id='synthetic-quality-image'))
            check('private_image_time_followup', '那幾點開始？', lambda a: bool(re.search(r'15[:：]00|15點|下午\s*[3三]\s*[點时時]|3\s*p\.?m', text(a), re.I)) and not sources(a))
            check('private_image_date_followup', '圖片上的日期是什麼？', lambda a: ('16' in text(a) or '十六' in text(a)) and not sources(a))
            rows.append(dict(case='no_cloud_write_receipts', passed=not teacher.state['operations']))
        finally:
            server.shutdown()
            runtime.close()
    report = dict(method='Real local HTTP signed webhook + worker + real Ollama/search/photo; captured reply sender and optional local synthetic image fixture, no LINE delivery or Google writes',
                  model=ai.model, results=rows, passed=sum(bool(r['passed']) for r in rows), total=len(rows))
    path = ROOT / 'test-evidence/http-live-quality.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print('RESULT', report['passed'], '/', report['total'], flush=True)
    return 0 if report['passed'] == report['total'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
