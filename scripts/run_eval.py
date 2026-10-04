import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from evals.runner import run_evaluation_suite


def main():
    print("Starting comprehensive voice agent evaluation harness...")
    report = asyncio.run(run_evaluation_suite())

    print("\n========================================================")
    print(f"EVALUATION COMPLETE: {report['passed']}/{report['total_scenarios']} passed ({report['pass_rate_pct']}%)")
    print(f"Total Duration: {report['duration_seconds']}s")
    print("========================================================")
    print("Category Breakdown:")
    for cat, stat in report["categories"].items():
        pct = (stat["passed"] / stat["total"]) * 100 if stat["total"] else 0
        print(f" - {cat:20s}: {stat['passed']}/{stat['total']} ({pct:5.1f}%)")
    print("========================================================")
    print("Reports generated in evals/reports/ (eval_latest.json and eval_latest.md)")


if __name__ == "__main__":
    main()
