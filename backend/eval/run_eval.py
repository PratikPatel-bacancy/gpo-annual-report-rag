"""Validates the RAG pipeline against backend/eval/sample_questions.json.

For each question: retrieves + generates an answer via the real pipeline
(no mocking), then checks it against a simple pass/fail heuristic --
either all of `expect_contains` appear in the answer (case-insensitive),
or, for `expect_refusal` questions, the answer contains a refusal phrase
instead of a fabricated one.

Run with:  python eval/run_eval.py
Requires a populated vector store (run scripts/ingest.py first) and a
filled-in .env (GROQ_API_KEY, COHERE_API_KEY, SUPABASE_*).
"""

import json
import re
import sys
import unicodedata
from pathlib import Path

# LLM output can contain characters (e.g. narrow no-break spaces in numbers)
# that the default Windows console codepage can't encode; fail open instead
# of crashing the whole eval run partway through.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.rag import answer_once  # noqa: E402

REFUSAL_PHRASES = [
    "don't have that information",
    "do not have that information",
    "not in the report",
    "not in my knowledge base",
    "doesn't contain",
    "does not contain",
    "no information",
    "i don't know",
    "unable to find",
    "not mentioned",
]


def _normalize(text: str) -> str:
    """Flattens cosmetic Unicode variation the LLM introduces (curly quotes,
    narrow no-break spaces in numbers, accented letters) so keyword matching
    checks actual content instead of punctuation/spacing style. Observed in
    practice: "don't" vs "don’t", "1.97 billion" vs "1.97 billion",
    "Halpern" vs "Halpérn".
    """
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"')
    text = re.sub(r"[   ​]", " ", text)
    return text.lower()


def _check(answer: str, case: dict) -> tuple[bool, str]:
    normalized = _normalize(answer)
    if case.get("expect_refusal"):
        if any(phrase in normalized for phrase in REFUSAL_PHRASES):
            return True, "declined as expected"
        return False, "expected a refusal, but got a confident answer"

    missing = [kw for kw in case.get("expect_contains", []) if _normalize(kw) not in normalized]
    if missing:
        return False, f"missing expected keyword(s): {missing}"
    return True, "all expected keywords present"


def main():
    cases = json.loads((Path(__file__).parent / "sample_questions.json").read_text(encoding="utf-8"))

    passed = 0
    for i, case in enumerate(cases, start=1):
        result = answer_once(case["question"])
        answer = result["answer"]
        ok, reason = _check(answer, case)
        passed += ok

        print(f"\n[{i}/{len(cases)}] {'PASS' if ok else 'FAIL'} -- {reason}")
        print(f"  Q: {case['question']}")
        print(f"  A: {answer}")
        if result["sources"]:
            top = result["sources"][0]
            print(f"  Top source: {top['title']} (p. {top['page_start']}), score={top['score']}")

    print(f"\n{passed}/{len(cases)} passed.")


if __name__ == "__main__":
    main()
