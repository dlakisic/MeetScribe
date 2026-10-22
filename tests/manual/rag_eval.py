"""Measure RAG retrieval quality against a running backend.

Each case is a question plus what a correct citation must contain, either a text
snippet (`expected_text`, compared without case or accents) or the segment IDs
(`expected_segment_ids`, as shown in the dashboard). Questions the transcripts
can't answer use `"expect_no_answer": true` and pass when nothing is cited; they
measure false positives. See rag_eval.example.json.

Usage:
    uv run python tests/manual/rag_eval.py cases.json --url http://192.168.1.19:8090
    (token read from --token or MEETSCRIBE_API_TOKEN)
"""

import argparse
import json
import os
import sys
import time
import unicodedata
from pathlib import Path

import httpx


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _matches(case: dict, citation: dict) -> bool:
    if expected_ids := case.get("expected_segment_ids"):
        return bool(set(expected_ids) & set(citation.get("segment_ids") or []))
    return _fold(case["expected_text"]) in _fold(citation["text"])


def evaluate(cases: list[dict], url: str, token: str | None, top_k: int) -> int:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    answerable = [c for c in cases if not c.get("expect_no_answer")]
    hits_at_1 = hits_at_k = 0
    false_positives = 0
    reciprocal_ranks: list[float] = []
    fallbacks = 0
    latencies: list[float] = []

    with httpx.Client(base_url=url, headers=headers, timeout=120) as client:
        for case in cases:
            started = time.perf_counter()
            resp = client.post(
                "/api/rag/ask",
                json={
                    "query": case["question"],
                    "meeting_ids": case.get("meeting_ids"),
                    "top_k": top_k,
                },
            )
            latencies.append(time.perf_counter() - started)
            resp.raise_for_status()
            data = resp.json()
            fallbacks += data.get("fallback_used", False)

            if case.get("expect_no_answer"):
                cited = len(data["citations"])
                false_positives += cited > 0
                status = f"FP x{cited}" if cited else "ok none"
                print(f"[{status:>7}] {case['question']}")
                continue

            rank = next(
                (i for i, c in enumerate(data["citations"], start=1) if _matches(case, c)), None
            )
            hits_at_1 += rank == 1
            hits_at_k += rank is not None
            reciprocal_ranks.append(1 / rank if rank else 0.0)
            status = f"rank {rank}" if rank else "MISS"
            print(f"[{status:>7}] {case['question']}")

    n = len(answerable)
    no_answer = len(cases) - n
    print()
    print(f"cases      {len(cases)} ({n} answerable, {no_answer} without answer)")
    if n:
        print(f"hit@1      {hits_at_1 / n:.0%}")
        print(f"hit@{top_k:<6} {hits_at_k / n:.0%}")
        print(f"MRR        {sum(reciprocal_ranks) / n:.3f}")
    if no_answer:
        print(f"false pos. {false_positives}/{no_answer}  (citations for unanswerable questions)")
    print(f"fallbacks  {fallbacks}  (LLM unavailable: extractive answers)")
    print(f"latency    avg {sum(latencies) / len(cases):.2f}s, max {max(latencies):.2f}s")
    return 0 if hits_at_k == n and not false_positives else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("cases", type=Path, help="JSON file with evaluation cases")
    parser.add_argument("--url", default="http://localhost:8090")
    parser.add_argument("--token", default=os.getenv("MEETSCRIBE_API_TOKEN"))
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    cases = json.loads(args.cases.read_text())
    keys = ("expected_text", "expected_segment_ids", "expect_no_answer")
    invalid = [c for c in cases if not any(k in c for k in keys)]
    if invalid:
        print(f"Each case needs one of {', '.join(keys)}: {invalid}")
        return 2
    return evaluate(cases, args.url, args.token, args.top_k)


if __name__ == "__main__":
    sys.exit(main())
