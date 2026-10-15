"""Real Ollama/RSS news continuity checks; no credentials, LINE calls or UI."""
import hashlib
import json
from pathlib import Path
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import line_bot_local as bot


def main():
    code_hash = hashlib.sha256((ROOT / "line_bot_local.py").read_bytes()).hexdigest()
    ai = bot.LocalAI()
    searches = []
    original_lookup = ai.lookup

    def lookup(*args):
        searches.append(args[0])
        return original_lookup(*args)

    ai.lookup = lookup
    results, original_evidence = [], None
    for question in ["今天有哪些國際新聞？請附來源。", "簡短一點", "詳細一點"]:
        reply = ai.ask(question, "synthetic-news-continuity")
        evidence = ai.conversations.get("synthetic-news-continuity", {}).get("evidence", [])
        if original_evidence is None:
            original_evidence = json.loads(json.dumps(evidence))
        text = reply[0]["text"] if isinstance(reply, list) else reply
        fallback = text == bot.grounded_news_answer("", evidence)[0]
        grounded = bot.grounded_news_answer(text, evidence)[1] == "source_extract"
        links = []
        if isinstance(reply, list):
            links = [button["action"]["uri"] for bubble in reply[1]["contents"]["contents"]
                     for button in bubble["footer"]["contents"]]
        expected_links = [item["url"] for source in evidence
                          for item in [source, *source.get("related_sources", [])[:2]]]
        checks = dict(has_evidence=bool(evidence), evidence_preserved=evidence == original_evidence,
                      source_grounded=bool(evidence) and (grounded or fallback),
                      links_preserved=bool(evidence) and links == expected_links,
                      only_initial_search=len(searches) == 1)
        results.append(dict(question=question, answer=text, checks=checks,
                            answer_mode="headline_fallback" if fallback else "source_extract",
                            evidence=evidence, passed=all(checks.values())))
        print(question, checks, flush=True)
    report = dict(method="Real local Ollama + publisher RSS, synthetic conversation; no LINE transport or phone UI",
                  code_sha256=code_hash, code_unchanged=code_hash == hashlib.sha256((ROOT / "line_bot_local.py").read_bytes()).hexdigest(),
                  passed=sum(row["passed"] for row in results), total=len(results), results=results,
                  limitation="Source consistency and continuity only; publisher truth is not independently verified.")
    output = ROOT / "test-evidence/news-runs" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-followups.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print("Report", output.relative_to(ROOT), flush=True)
    return 0 if report["passed"] == report["total"] and report["code_unchanged"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
