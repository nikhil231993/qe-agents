"""CLI entrypoint: artifact in -> triaged defect report out.

Usage:
    uv run python -m qe_agents.run [path/to/artifact.md]

If no artifact path is given, defaults to the bundled restful-booker spec
fixture at eval/fixtures/restful_booker_spec.md.
"""

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from qe_agents import settings
from qe_agents.graph import build_graph

DEFAULT_ARTIFACT = Path(__file__).resolve().parent.parent / "eval" / "fixtures" / "restful_booker_spec.md"


def main() -> int:
    artifact_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_ARTIFACT
    if not artifact_path.exists():
        print(f"Artifact file not found: {artifact_path}", file=sys.stderr)
        return 1

    artifact_text = artifact_path.read_text()
    run_id = f"{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
    run_dir = Path(settings.ARTIFACTS_DIR) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"[qe-agents] run_id={run_id}")
    print(f"[qe-agents] artifact={artifact_path}")
    print(f"[qe-agents] models: planner={settings.PLANNER_MODEL} generator={settings.GENERATOR_MODEL} triager={settings.TRIAGER_MODEL}")

    graph = build_graph()

    print("[qe-agents] running pipeline: planner -> generator -> executor -> triager ...")
    result = graph.invoke({"artifact_text": artifact_text, "run_id": run_id})

    # --- write artifacts ---
    (run_dir / "plan.md").write_text(result.get("plan_markdown", ""))
    (run_dir / "plan.json").write_text(json.dumps(result.get("plan_json", {}), indent=2))
    (run_dir / "generated_test.py").write_text(result.get("generated_test_code", ""))
    (run_dir / "junit.xml").write_text(result.get("junit_xml", ""))
    (run_dir / "stdout.log").write_text(result.get("stdout_log", ""))
    (run_dir / "stderr.log").write_text(result.get("stderr_log", ""))
    (run_dir / "failures.json").write_text(json.dumps(result.get("failures", []), indent=2))
    (run_dir / "defects.md").write_text(result.get("defects_markdown", ""))
    (run_dir / "defects.json").write_text(json.dumps(result.get("defects_json", []), indent=2))

    print(f"[qe-agents] pipeline complete. artifacts written to {run_dir}/")
    print()
    print(result.get("defects_markdown", "(no defects report produced)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
