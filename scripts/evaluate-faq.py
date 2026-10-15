"""Evaluate FAQ behavior with synthetic LINE events and real local inference/search.
No .env, real LINE sends, Google writes, UI operations, or model weight updates.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import queue
import re
import sys
import tempfile
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import line_bot_local as bot


def answer_text(answer):
    return answer if isinstance(answer, str) else '\n'.join(m.get('text', '') for m in answer if m.get('type') == 'text')


def source_urls(answer):
    found = []
    def walk(item):
        if isinstance(item, dict):
            if item.get('type') == 'uri' and isinstance(item.get('uri'), str):
                found.append(item['uri'])
            for value in item.values():
                walk(value)
        elif isinstance(item, list):
            for value in item:
                walk(value)
    walk(answer)
    return sorted(set(found))


def grade(answer, check):
    """Conservative mechanical checks, not proof of semantic truth or source entailment."""
    from urllib.parse import urlsplit
    text, urls = answer_text(answer), source_urls(answer)
    refusal = bool(re.search(r'沒有找到足以|沒查到可確認|沒有找到.*來源', text))
    error = bool(re.search(r'本機模型暫時無法|本機照片模型暫時|本機模型暫時無法整理|暫時無法下載', text))
    kind = check['kind']
    if error:
        return '執行失敗', False
    if refusal:
        return '查不到', kind == 'refusal'
    if kind == 'refusal':
        return '未符合參考，需複核', False
    matches = all(any(re.search(pattern, text, re.I) for pattern in group) for group in check.get('all_of', []))
    matches = matches and not any(term in text for term in check.get('absent', []))
    if check.get('max_chars'):
        matches = matches and len(text) <= check['max_chars']
    if kind == 'clarification':
        return ('追問', True) if matches else ('未按預期追問', False)
    if kind == 'image':
        ok = isinstance(answer, list) and any(m.get('type') == 'image' for m in answer)
        return ('圖片已產生', True) if ok else ('圖片未產生', False)
    if kind == 'manual':
        hosts = set(check.get('source_hosts', []))
        eligible = len(urls) >= check.get('min_sources', 1) and (not hosts or any(urlsplit(u).hostname in hosts for u in urls))
        return ('待人工核對', None) if eligible else ('來源不足', False)
    if not matches:
        return '未符合參考，需複核', False
    if check.get('sources') and not urls:
        return '缺少來源', False
    return ('主答案字詞符合，需抽查' if kind == 'fact' else '符合預期'), True


def make_event(case):
    # Never pass expected answers/checks, split labels, or evaluator instructions to the bot.
    identity = case.get('conversation', case['id']) + ':' + case.get('user', 'A')
    user = 'synthetic-' + hashlib.sha256(identity.encode()).hexdigest()[:20]
    return dict(type='message', webhookEventId='faq-' + uuid.uuid4().hex, replyToken='synthetic-test-only',
                source=dict(type='user', userId=user), message=dict(type='text', text=case['question']))


class ReplyCapture:
    """One mailbox per event: late responses cannot be graded as a different case."""
    def __init__(self):
        self.boxes, self.lock = {}, threading.RLock()

    def register(self, event_id):
        with self.lock:
            self.boxes[event_id] = queue.Queue()

    def send(self, event, answer):
        with self.lock:
            self.boxes[event['webhookEventId']].put(answer)

    def wait(self, event_id, timeout):
        return self.boxes[event_id].get(timeout=timeout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', default='gemma4:e4b-it-q4_K_M')
    parser.add_argument('--split', choices=['development', 'holdout', 'all'], default='development')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--pause', type=float, default=0.3)
    args = parser.parse_args()
    if not 0 <= args.pause <= 5:
        parser.error('--pause must be between 0 and 5 seconds')
    path = ROOT / 'evaluation/faq-cases.json'
    raw = path.read_bytes()
    cases = [r for r in json.loads(raw)['cases'] if args.split == 'all' or r['split'] == args.split]
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output = args.output or ROOT / 'test-evidence/faq-runs' / (stamp + '-' + uuid.uuid4().hex[:6] + '.json')
    if not output.is_absolute():
        output = ROOT / output
    if not output.resolve().is_relative_to(ROOT) or output.exists():
        parser.error('Choose a new output file inside this repository; previous runs are not overwritten.')
    code_hash = hashlib.sha256((ROOT / 'line_bot_local.py').read_bytes()).hexdigest()
    results, aborted = [], None
    started = time.monotonic()
    def save(complete=False):
        summary = dict(selected=len(cases),completed=len(results),not_run=len(cases)-len(results),
            checks_passed=sum(r['passed'] is True for r in results),checks_failed=sum(r['passed'] is False for r in results),
            manual=sum(r['passed'] is None for r in results),by_status=dict(Counter(r['status'] for r in results)))
        report = dict(method='Synthetic LINE event -> real BotRuntime worker -> live Ollama/search -> captured local reply. No LINE transport, Google writes, or weight training.',
            evaluator_version=2,complete=complete,aborted_reason=aborted,
            model=args.model,split=args.split,pause_seconds=args.pause,started_at_utc=stamp,seconds=round(time.monotonic()-started,2),
            code_sha256=code_hash,bank_sha256=hashlib.sha256(raw).hexdigest(),
            code_unchanged=code_hash==hashlib.sha256((ROOT/'line_bot_local.py').read_bytes()).hexdigest(),expectations_sent_to_bot=False,
            grading_limit='Primary reference word matching and behavior checks only. Source presence is not proof of factual support. Manual checks remain ungraded; pretraining contamination cannot be ruled out.',
            summary=summary,results=results)
        bot.private_json(output,report)
        return report
    save()
    with tempfile.TemporaryDirectory(prefix='faq-eval-') as directory:
        root = Path(directory)
        capture = ReplyCapture()
        memory = root / 'memory.json'
        photos = bot.Photos('https://quality.example', root / 'photos')
        def make_ai():
            return bot.LocalAI(model=args.model, memory_path=memory, photos=photos)
        runtime = bot.BotRuntime('synthetic-secret-only','',bot.TodoStore(root/'todos.jsonl'),make_ai(),photos=photos,sender=capture.send)
        try:
            for case in cases:
                if case.get('action') == 'reload_memory':
                    runtime.ai = make_ai()
                event = make_event(case)
                capture.register(event['webhookEventId'])
                beginning = time.monotonic()
                row = dict(id=case['id'],category=case['category'],question=case['question'],kind=case['check']['kind'])
                try:
                    if not runtime.submit(event):
                        row.update(status='無法排入處理',passed=False)
                    else:
                        answer = capture.wait(event['webhookEventId'],timeout=75)
                        status,passed = grade(answer,case['check'])
                        row.update(status=status,passed=passed,answer=answer_text(answer),sources=source_urls(answer))
                        state = runtime.ai.conversations.get(bot.conversation_key(event),{})
                        row['retrieved_evidence'] = state.get('evidence',[])
                except queue.Empty:
                    row.update(status='回覆逾時',passed=False)
                    aborted = 'Stopped after reply timeout; remaining cases were not run. A late reply will not be paired with another question.'
                except Exception as error:
                    row.update(status='測試執行失敗',passed=False,error_type=type(error).__name__)
                    aborted = 'Stopped after evaluator error; remaining cases were not run.'
                row['seconds'] = round(time.monotonic()-beginning,2)
                results.append(row)
                save()
                print(f"{case['id']}: {row['status']}",flush=True)
                if aborted:
                    break
                time.sleep(args.pause)
        except KeyboardInterrupt:
            aborted = 'Interrupted by operator; partial results retained.'
            save()
        finally:
            runtime.close()
    report = save(complete=not aborted and len(results)==len(cases))
    print(json.dumps(report['summary'],ensure_ascii=False),flush=True)
    print('Report:',output.relative_to(ROOT),flush=True)
    return 0 if report['complete'] and report['summary']['checks_failed']==0 and report['code_unchanged'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
