"""Smoke test for the full QE Agents pipeline with the LLM boundary mocked.

This does NOT require a GITHUB_TOKEN or network access. It monkeypatches
`qe_agents.github_models.chat` so we can validate the LangGraph wiring,
state threading, executor sandboxing/flaky-detection, and triage
clustering logic end-to-end, independent of any live model.
"""

import json
from pathlib import Path
from unittest.mock import patch

from qe_agents.graph import build_graph

FIXTURE = Path(__file__).resolve().parent.parent / "eval" / "fixtures" / "restful_booker_spec.md"

FAKE_PLAN = {
    "scenarios": [
        {
            "id": "TC-01",
            "title": "Create booking happy path",
            "priority": "P0",
            "area": "Booking Create",
            "type": "positive",
            "description": "POST /booking with valid fields returns 200 and a bookingid",
            "risk_rationale": "Most business-critical path",
        },
        {
            "id": "TC-02",
            "title": "Create booking with negative totalprice",
            "priority": "P1",
            "area": "Booking Create",
            "type": "negative",
            "description": "POST /booking with totalprice=-5 should be rejected or flagged",
            "risk_rationale": "Undocumented validation, boundary risk",
        },
    ],
    "coverage_summary": "Covers booking creation happy path and one boundary case.",
    "entry_criteria": ["SUT reachable via GET /ping"],
    "exit_criteria": ["All P0 scenarios pass"],
    "ambiguities": [
        {
            "question": "Does totalprice validation reject negative values?",
            "why_it_matters": "Could allow negative-cost bookings",
            "assumption_if_unresolved": "Assume no server-side validation; assert structural response only",
        }
    ],
}

# A generated test file with one test that always passes and one that
# always fails, to exercise both the "no defect" and "real defect" triage
# paths deterministically without hitting the network.
FAKE_GENERATED_CODE = '''
def test_TC01_always_passes():
    """Covers TC-01 (P0, positive): sanity check."""
    assert 1 + 1 == 2


def test_TC02_always_fails():
    """Covers TC-02 (P1, negative): deliberately failing for smoke test."""
    assert 1 == 2, "expected 200 status but got 500 from /booking endpoint"
'''

FAKE_TRIAGE_ENRICHMENT = json.dumps(
    [
        {
            # matches the signature the heuristic derives from the failure
            # message "AssertionError: expected 200 status but got 500 from
            # /booking endpoint\nassert 1 == 2" -> endpoint=booking,
            # status=200 (first 3-digit match), assertion_kind=equality
            # (message contains "assert" and "==").
            "signature": "booking|200|equality",
            "severity": "High",
            "likely_root_cause": "Assertion mismatch simulated for smoke test.",
            "suggested_owner": "Booking API",
        }
    ]
)


def fake_chat(model, system_prompt, user_prompt, temperature=0.2):
    if "test architect" in system_prompt.lower() or "risk-based test plan" in system_prompt.lower():
        return json.dumps(FAKE_PLAN)
    if "senior sdet" in system_prompt.lower():
        return FAKE_GENERATED_CODE
    if "triage lead" in system_prompt.lower():
        return FAKE_TRIAGE_ENRICHMENT
    raise AssertionError(f"Unexpected system prompt in fake_chat: {system_prompt[:80]}")


def test_full_pipeline_with_mocked_llm():
    with patch("qe_agents.planner.chat", side_effect=fake_chat), \
         patch("qe_agents.generator.chat", side_effect=fake_chat), \
         patch("qe_agents.triager.chat", side_effect=fake_chat):
        graph = build_graph()
        result = graph.invoke({"artifact_text": FIXTURE.read_text(), "run_id": "smoke-test"})

    # Planner produced a plan
    assert result["plan_json"]["scenarios"][0]["id"] == "TC-01"
    assert "Surfaced ambiguities" in result["plan_markdown"]

    # Generator produced the fake code, executor actually ran it
    assert "def test_TC01_always_passes" in result["generated_test_code"]
    assert result["exit_code"] != 0  # one test failed

    # Executor's rerun logic marked the deterministic failure as "real"
    failures = result["failures"]
    assert len(failures) == 1
    assert failures[0]["rerun_status"] == "real"
    assert "test_TC02_always_fails" in failures[0]["test_name"]

    # Triager clustered + enriched the failure into a defect
    defects = result["defects_json"]
    assert len(defects) == 1
    assert defects[0]["is_real"] is True
    assert defects[0]["severity"] == "High"
    assert "No failures detected" not in result["defects_markdown"]


def test_pipeline_reports_no_defects_when_all_pass():
    all_pass_code = '''
def test_TC01_always_passes():
    """Covers TC-01 (P0, positive)."""
    assert 1 + 1 == 2
'''

    def fake_chat_all_pass(model, system_prompt, user_prompt, temperature=0.2):
        if "risk-based test plan" in system_prompt.lower():
            return json.dumps(FAKE_PLAN)
        if "senior sdet" in system_prompt.lower():
            return all_pass_code
        raise AssertionError("Triager should not be called when there are no failures")

    with patch("qe_agents.planner.chat", side_effect=fake_chat_all_pass), \
         patch("qe_agents.generator.chat", side_effect=fake_chat_all_pass), \
         patch("qe_agents.triager.chat", side_effect=fake_chat_all_pass):
        graph = build_graph()
        result = graph.invoke({"artifact_text": FIXTURE.read_text(), "run_id": "smoke-test-2"})

    assert result["exit_code"] == 0
    assert result["failures"] == []
    assert result["defects_json"] == []
    assert "No failures detected" in result["defects_markdown"]
