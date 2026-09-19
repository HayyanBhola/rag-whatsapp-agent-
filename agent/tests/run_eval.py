"""
tests/run_eval.py

The automatic test sheet. Runs every case in tests/eval_cases.json through
the real agent (real database, real knowledge base, and the LLM chosen in .env) and
prints PASS/FAIL for each, with the reason for every failure.

    python -m tests.run_eval                   # all cases
    python -m tests.run_eval kb-uk db-price    # only cases whose id starts with these

Run it after EVERY change (a prompt edit, a new model, a new document).
If a number that used to pass now fails, that change broke something.
Each run is also saved to tests/results/ so runs can be compared later.
"""

import json
import os
import sys
import time
from datetime import datetime

from agent.support_agent import handle_message
from agent import llm_client

CASES_PATH = "tests/eval_cases.json"
RESULTS_DIR = "tests/results"


def check_case(case: dict, result: dict) -> list:
    """Returns the list of reasons this case failed ([] = pass)."""
    problems = []
    answer = (result.get("answer") or "").lower()

    if "route" in case and result["route"] != case["route"]:
        problems.append(f"route was '{result['route']}', expected '{case['route']}'")
    if "escalate" in case and result["escalate"] != case["escalate"]:
        problems.append(f"escalate was {result['escalate']}, expected {case['escalate']}")
    for text in case.get("must_include", []):
        if text.lower() not in answer:
            problems.append(f"missing '{text}'")
    for group in case.get("must_include_any", []):
        if not any(t.lower() in answer for t in group):
            problems.append(f"missing one of {group}")
    for text in case.get("must_not_include", []):
        if text.lower() in answer:
            problems.append(f"contains forbidden '{text}'")
    return problems


def main(filters):
    with open(CASES_PATH, encoding="utf-8") as f:
        cases = json.load(f)["cases"]
    if filters:
        cases = [c for c in cases if any(c["id"].startswith(x) for x in filters)]

    rows, passed = [], 0
    for case in cases:
        start = time.time()
        try:
            result = handle_message(case["question"], verbose=False)
            problems = check_case(case, result)
        except Exception as e:  # a crash is a failure, not a reason to stop
            result = {"route": "ERROR", "answer": f"{type(e).__name__}: {e}",
                      "source": None, "escalate": None, "details": None}
            problems = [f"crashed: {type(e).__name__}: {e}"]
        seconds = time.time() - start
        ok = not problems
        passed += ok

        details = result.get("details") if isinstance(result.get("details"), dict) else {}
        print(f"{'PASS' if ok else 'FAIL'}  {case['id']:<28} ({seconds:4.1f}s)  {case['question']}")
        if not ok:
            print(f"      answer : {result['answer'][:220]!r}")
            for p in problems:
                print(f"      problem: {p}")
            if details.get("problems"):
                print(f"      checker: {'; '.join(details['problems'])}")
        rows.append({"id": case["id"], "question": case["question"], "passed": ok,
                     "problems": problems, "route": result["route"],
                     "source": result.get("source"), "answer": result["answer"],
                     "answer_type": details.get("answer_type"),
                     "llm_answer": details.get("llm_answer"),
                     "checker_problems": details.get("problems"),
                     "seconds": round(seconds, 1)})

    total = len(cases)
    print("-" * 70)
    print(f"{passed}/{total} passed ({passed / total:.0%})" if total else "No cases matched.")
    print(f"Model: {llm_client.LLM_PROVIDER} ({llm_client.MODEL_NAME})", end="")
    cost = llm_client.estimated_cost_usd()
    if cost is not None:
        u = llm_client.usage_totals
        print(f" | {u['calls']} calls, {u['input_tokens']} input + {u['output_tokens']} "
              f"output tokens | est. cost ${cost:.4f}"
              + (" at paid prices ($0 on Gemini's free tier)"
                 if llm_client.LLM_PROVIDER == "gemini" else ""))
    else:
        print()

    os.makedirs(RESULTS_DIR, exist_ok=True)
    path = os.path.join(RESULTS_DIR, datetime.now().strftime("eval_%Y%m%d_%H%M%S.json"))
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"passed": passed, "total": total,
                   "model": f"{llm_client.LLM_PROVIDER}/{llm_client.MODEL_NAME}",
                   "cases": rows}, f, indent=2)
    print(f"Saved full results to {path}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
