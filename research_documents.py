"""Bounded PDF extraction in a disposable worker; no network or credentials."""
import io
import json
from pathlib import Path
import re
import subprocess
import sys


def extract_references(data, timeout):
    if not data.startswith(b'%PDF-') or len(data) > 5 * 1024 * 1024:
        raise ValueError('Not a bounded PDF')
    process = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--extract'],
        input=data, capture_output=True, timeout=timeout, check=True)
    if len(process.stdout) > 100000:
        raise ValueError('PDF text output too large')
    return json.loads(process.stdout)


def worker(data):
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    if not 1 <= len(reader.pages) <= 60:
        raise ValueError('Unsupported PDF length')
    indexes = sorted(set([0, min(1, len(reader.pages)-1), *range(max(0,len(reader.pages)-6),len(reader.pages))]))
    texts = [(reader.pages[i].extract_text() or '')[:18000] for i in indexes]
    header = '\n'.join(texts[:2])[:4000]
    tail = '\n'.join(texts)
    headings = list(re.finditer(r'(?im)^\s*(?:References|Bibliography)\s*$', tail))
    if not headings:
        return dict(header=header, references=[], pages=len(reader.pages))
    bibliography = tail[headings[-1].end():]
    refs = []
    for match in re.finditer(r'\[(\d{1,3})\]\s*(.*?)(?=\[\d{1,3}\]|\Z)', bibliography, re.S):
        text = re.sub(r'\s+', ' ', match[2]).strip()
        text = re.sub(r'\s+\d+\s*\(\d+\)\s*$', '', text)
        if len(text) >= 15:
            refs.append(dict(number=int(match[1]), text=text[:650]))
    return dict(header=header, references=refs[:60], pages=len(reader.pages))


if __name__ == '__main__':
    payload = sys.stdin.buffer.read(5 * 1024 * 1024 + 1)
    if len(payload) > 5 * 1024 * 1024:
        raise ValueError('PDF too large')
    print(json.dumps(worker(payload), ensure_ascii=False))
