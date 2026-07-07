"""Shared state schema threaded through the LangGraph pipeline."""

from typing import TypedDict


class QEState(TypedDict, total=False):
    # --- input ---
    artifact_text: str  # raw ingested spec/PRD/API-notes text (untrusted!)
    run_id: str

    # --- planner output ---
    plan_markdown: str  # human-readable risk-based test plan
    plan_json: dict  # structured version: scenarios, ambiguities, criteria

    # --- generator output ---
    generated_test_code: str  # full contents of the generated pytest file
    test_data_json: dict  # any fixtures/test data the generator produced

    # --- executor output ---
    junit_xml: str
    stdout_log: str
    stderr_log: str
    failures: list  # list[dict]: {test_name, message, rerun_status: real|flaky}
    exit_code: int

    # --- triager output ---
    defects_markdown: str
    defects_json: list  # list[dict]: clustered, severity-tagged defects
