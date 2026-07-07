"""Runs all 4 evaluation checks and writes eval/results.md.

Requires GITHUB_TOKEN to be set (these checks call the real LLM agents).

Usage:
    export GITHUB_TOKEN=...   # PAT with "models: read"
    uv run python -m eval.run_eval
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

from eval.checks import (
    check_ambiguity_surfacing,
    check_coverage_recall,
    check_injection_resistance,
    check_triage_precision_recall,
)

RESULTS_PATH = Path(__file__).resolve().parent / "results.md"


def main() -> int:
    checks = [
        check_ambiguity_surfacing,
        check_coverage_recall,
        check_triage_precision_recall,
        check_injection_resistance,
    ]

    results = []
    for check_fn in checks:
        print(f"[eval] running {check_fn.__name__} ...")
        try:
            result = check_fn()
        except Exception as e:  # noqa: BLE001 - surface any failure as a failed check
            result = {"name": check_fn.__name__, "passed": False, "details": f"ERROR: {e}"}
        results.append(result)
        status = "PASS" if result["passed"] else "FAIL"
        print(f"[eval] {status}: {result['name']} -- {result['details']}")

    lines = [
        "# Evaluation Results",
        "",
        f"_Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}_",
        "",
        "**Caveat:** these are small, illustrative checks on hand-picked/seeded",
        "fixtures -- not a statistically rigorous evaluation. They are meant to",
        "demonstrate the evaluation *methodology* the assignment asks for, on a",
        "scale appropriate to a 1-day exercise.",
        "",
        "| # | Check | Result | Details |",
        "|---|---|---|---|",
    ]
    for i, r in enumerate(results, 1):
        status = "✅ PASS" if r["passed"] else "❌ FAIL"
        details = r["details"].replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {i} | {r['name']} | {status} | {details} |")
    lines.append("")

    RESULTS_PATH.write_text("\n".join(lines))
    print(f"\n[eval] results written to {RESULTS_PATH}")

    return 0 if all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
