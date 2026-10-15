"""Live news routing checks: real RSS and local Ollama; no LINE/Google writes or UI."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlsplit
import uuid
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import line_bot_local as bot


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model',default='gemma4:e4b-it-q4_K_M')
    p.add_argument('--output',type=Path)
    a=p.parse_args()
    output=a.output or Path('test-evidence/news-runs')/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6]+'.json')
    if not output.is_absolute():output=ROOT/output
    if not output.resolve().is_relative_to(ROOT) or output.exists():p.error('Choose a new file inside this repo; previous evidence is preserved.')
    code_hash=hashlib.sha256((ROOT/'line_bot_local.py').read_bytes()).hexdigest()
    ai=bot.LocalAI(model=a.model)
    rows=[]
    for i,q in enumerate(['今天有哪些國際新聞？請附來源。','今日世界新聞摘要，請附來源。']):
        start=time.monotonic();reply=ai.ask(q,'news-quality-'+str(i))
        text=reply if isinstance(reply,str) else reply[0]['text']
        evidence=ai.conversations.get('news-quality-'+str(i),{}).get('evidence',[])
        links=[]
        if isinstance(reply,list) and len(reply)>1:
            links=[b['footer']['contents'][0]['action']['uri'] for b in reply[1]['contents']['contents']]
        def scope(row):
            u=urlsplit(row['url'])
            return u.scheme=='https' and not u.username and not u.password and ((u.hostname=='www.cna.com.tw' and u.path.startswith('/news/aopl/')) or (u.hostname=='news.ltn.com.tw' and u.path.startswith('/news/world/')))
        now=time.time();midnight=datetime.fromtimestamp(now,bot.TAIPEI).replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
        numbers=[int(n) for group in re.findall(r'\[([\d,，、\s]+)\]',text) for n in re.findall(r'\d+',group)]
        checks=dict(has_sources=bool(evidence),publisher_world_paths=bool(evidence) and all(scope(e) for e in evidence),
            published_today=bool(evidence) and all(e.get('published') is not None and midnight<=e['published']<=now for e in evidence),
            citation_indices=bool(numbers) and all(1<=n<=len(evidence) for n in numbers),
            source_cards_match_evidence=bool(evidence) and links==[e['url'] for e in evidence],
            model_generated_summary=not text.startswith(('本機模型暫時','本機模型這次未能')))
        row=dict(question=q,answer=text,seconds=round(time.monotonic()-start,2),checks=checks,passed=all(checks.values()),evidence=evidence)
        rows.append(row);print(q,checks,flush=True)
    report=dict(method='Live publisher international RSS + real local model, source scope/date/citation mapping checks; no phone, LINE transport or weight training',
        model=a.model,code_sha256=code_hash,code_unchanged=code_hash==hashlib.sha256((ROOT/'line_bot_local.py').read_bytes()).hexdigest(),
        semantic_limit='These checks do not independently verify every reported event or entailment of every generated sentence. RSS timestamps describe publication, not necessarily event occurrence.',
        passed=sum(r['passed'] for r in rows),total=len(rows),results=rows)
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('Result',report['passed'],'/',report['total'],'Report',output.relative_to(ROOT),flush=True)
    return 0 if report['passed']==report['total'] and report['code_unchanged'] else 1


if __name__=='__main__':raise SystemExit(main())
