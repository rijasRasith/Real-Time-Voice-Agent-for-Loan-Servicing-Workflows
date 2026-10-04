from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.data.repository import get_engine
from evals.judges.evaluator import evaluation_judge
from evals.scenarios.catalog import generate_extended_scenarios
from evals.simulator.caller import ScenarioSimulator


async def run_evaluation_suite():
    get_engine()
    scenarios = generate_extended_scenarios()
    simulator = ScenarioSimulator()

    scores = []
    start_time = time.monotonic()

    for sc in scenarios:
        session, responses, history = await simulator.run_scenario(sc)
        score = evaluation_judge.judge_scenario(sc, session, responses, history)
        scores.append(score)

    total = len(scores)
    passed = sum(1 for s in scores if s.passed)
    pass_rate = (passed / total) * 100 if total else 0.0

    categories = {}
    for s in scores:
        if s.category not in categories:
            categories[s.category] = {"total": 0, "passed": 0}
        categories[s.category]["total"] += 1
        if s.passed:
            categories[s.category]["passed"] += 1

    reports_dir = os.path.join(os.path.dirname(__file__), "reports")
    os.makedirs(reports_dir, exist_ok=True)

    report_data = {
        "timestamp": datetime.utcnow().isoformat(),
        "total_scenarios": total,
        "passed": passed,
        "pass_rate_pct": round(pass_rate, 2),
        "duration_seconds": round(time.monotonic() - start_time, 2),
        "categories": categories,
        "scores": [s.dict() for s in scores],
    }

    json_path = os.path.join(reports_dir, "eval_latest.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)

    md_path = os.path.join(reports_dir, "eval_latest.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# Evaluation Suite Results\n\n")
        f.write(f"- **Generated:** {report_data['timestamp']}\n")
        f.write(f"- **Total Scenarios:** {total}\n")
        f.write(f"- **Passed:** {passed} ({pass_rate:.1f}%)\n")
        f.write(f"- **Duration:** {report_data['duration_seconds']}s\n\n")
        f.write("## Category Breakdown\n\n")
        f.write("| Category | Total | Passed | Pass Rate |\n")
        f.write("|---|---|---|---|\n")
        for cat, stat in categories.items():
            rate = (stat["passed"] / stat["total"]) * 100 if stat["total"] else 0
            f.write(f"| {cat} | {stat['total']} | {stat['passed']} | {rate:.1f}% |\n")

    return report_data


if __name__ == "__main__":
    data = asyncio.run(run_evaluation_suite())
    print(
        f"Evaluation finished: {data['passed']}/{data['total_scenarios']} passed ({data['pass_rate_pct']}%)"
    )
