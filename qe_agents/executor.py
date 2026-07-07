"""Executor agent node (no LLM -- pure mechanics).

Runs the generated pytest file in an isolated tempdir via `subprocess.run`
(no `shell=True`, hard timeout), captures JUnit XML + stdout/stderr, and
applies a simple run-twice flaky-detection heuristic:

    run once -> if it fails, run again -> pass-on-retry means "flaky",
    fail-again means "real failure".

Safety posture (v2, intentionally simplified -- see DESIGN.md):
- subprocess.run with an explicit argv list (never shell=True) prevents
  shell-injection via the command line itself.
- Execution happens in a dedicated tempdir so generated code can't casually
  clobber repo files.
- A hard wall-clock timeout bounds runaway/hanging generated code.
- What this does NOT do: static analysis of the generated code before
  running it (AST allow-list), or OS-level sandboxing/container isolation.
  If the Generator LLM were tricked (via prompt injection in the artifact)
  into emitting malicious Python, this executor would still run it with
  the same OS privileges as the parent process. This is an explicit,
  documented time-boxed tradeoff -- see "What's next" in DESIGN.md.
"""

import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from qe_agents import settings
from qe_agents.state import QEState


def _run_pytest(test_file: Path, junit_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(test_file),
            f"--junitxml={junit_path}",
            "-v",
        ],
        cwd=str(test_file.parent),
        timeout=settings.EXECUTOR_TIMEOUT_SECONDS,
        capture_output=True,
        text=True,
        shell=False,
    )


def _parse_failed_tests(junit_path: Path) -> set:
    """Returns the set of test names (classname::name) that failed/errored."""
    if not junit_path.exists():
        return set()
    tree = ET.parse(junit_path)
    failed = set()
    for testcase in tree.getroot().iter("testcase"):
        name = f"{testcase.get('classname', '')}::{testcase.get('name', '')}"
        if testcase.find("failure") is not None or testcase.find("error") is not None:
            failed.add(name)
    return failed


def _failure_messages(junit_path: Path) -> dict:
    """Maps test name -> failure/error message text."""
    if not junit_path.exists():
        return {}
    tree = ET.parse(junit_path)
    messages = {}
    for testcase in tree.getroot().iter("testcase"):
        name = f"{testcase.get('classname', '')}::{testcase.get('name', '')}"
        node = testcase.find("failure")
        if node is None:
            node = testcase.find("error")
        if node is not None:
            messages[name] = (node.get("message") or "").strip() or (node.text or "").strip()
    return messages


def execute_node(state: QEState) -> QEState:
    code = state["generated_test_code"]

    with tempfile.TemporaryDirectory(prefix="qe_agents_run_") as tmpdir:
        tmp_path = Path(tmpdir)
        test_file = tmp_path / "test_generated.py"
        test_file.write_text(code)

        junit1 = tmp_path / "junit_run1.xml"
        try:
            run1 = _run_pytest(test_file, junit1)
        except subprocess.TimeoutExpired as e:
            return {
                "exit_code": -1,
                "stdout_log": (e.stdout or ""),
                "stderr_log": f"TIMEOUT after {settings.EXECUTOR_TIMEOUT_SECONDS}s: {e}",
                "junit_xml": "",
                "failures": [],
            }

        failed1 = _parse_failed_tests(junit1)
        messages = _failure_messages(junit1)

        failures = []
        if failed1:
            # Manual flaky-detection: rerun once, only for the failing tests.
            junit2 = tmp_path / "junit_run2.xml"
            try:
                run2 = _run_pytest(test_file, junit2)
                failed2 = _parse_failed_tests(junit2)
            except subprocess.TimeoutExpired:
                failed2 = failed1  # treat timeout-on-rerun as still-failing

            for test_name in sorted(failed1):
                status = "real" if test_name in failed2 else "flaky"
                failures.append(
                    {
                        "test_name": test_name,
                        "message": messages.get(test_name, ""),
                        "rerun_status": status,
                    }
                )

        junit_xml_text = junit1.read_text() if junit1.exists() else ""

        return {
            "exit_code": run1.returncode,
            "stdout_log": run1.stdout,
            "stderr_log": run1.stderr,
            "junit_xml": junit_xml_text,
            "failures": failures,
        }
