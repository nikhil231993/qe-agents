"""Triager agent node.

Turns raw execution failures into actionable defects: real vs flaky
(already tagged by the Executor's rerun logic), severity/priority, dedup
via a cheap heuristic signature, and an LLM-produced root-cause hypothesis
+ likely owner per cluster.

Dedup heuristic (deliberately simple, no embeddings): group failures by
(endpoint, http_status_seen, assertion_keyword) extracted from the test
name + failure message with light regex. This is enough to collapse
"same underlying bug, multiple test cases" without a vector DB.
"""

import json
import re

from qe_agents import settings
from qe_agents.github_models import chat
from qe_agents.state import QEState

_STATUS_RE = re.compile(r"\b([1-5]\d{2})\b")
_ENDPOINT_RE = re.compile(r"/(auth|booking(?:/\{?id\}?)?|ping)\b", re.IGNORECASE)


def _signature(failure: dict) -> str:
    msg = failure.get("message", "")
    test_name = failure.get("test_name", "")
    status_match = _STATUS_RE.search(msg)
    endpoint_match = _ENDPOINT_RE.search(msg) or _ENDPOINT_RE.search(test_name)
    status = status_match.group(1) if status_match else "unknown"
    endpoint = endpoint_match.group(1).lower() if endpoint_match else "unknown"
    # crude assertion-type bucket: what kind of assert tripped
    if "assert" in msg.lower() and "==" in msg:
        assertion_kind = "equality"
    elif "status" in msg.lower():
        assertion_kind = "status_code"
    elif "key" in msg.lower() or "keyerror" in msg.lower():
        assertion_kind = "missing_field"
    else:
        assertion_kind = "other"
    return f"{endpoint}|{status}|{assertion_kind}"


def _priority_from_plan(test_name: str, plan_json: dict) -> str:
    """Best-effort: match the test to a plan scenario id mentioned in its
    docstring/name to inherit that scenario's priority; default to P2."""
    for scenario in (plan_json or {}).get("scenarios", []):
        sid = scenario.get("id", "")
        if sid and sid.lower() in test_name.lower():
            return scenario.get("priority", "P2")
    return "P2"


SYSTEM_PROMPT = """You are a QE triage lead. You will be given a JSON list of
defect clusters, each with: signature, priority hint, failing test names, and
one representative failure message. For EACH cluster, produce:
  - severity: "High" | "Medium" | "Low" (based on priority hint + how
    fundamental the failure looks, e.g. 500s / auth failures are High)
  - likely_root_cause: one sentence hypothesis grounded in the failure
    message (don't invent specifics you can't infer)
  - suggested_owner: a plausible team/area name (e.g. "Booking API", "Auth
    Service", "Test Infra" if it looks like a flaky/test-issue rather than
    a product bug)

Respond with ONLY a JSON array, same order as input, each element:
{"signature": "...", "severity": "...", "likely_root_cause": "...", "suggested_owner": "..."}
No markdown fences, no commentary.
"""


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[-1].strip().startswith("```"):
            lines = lines[1:-1]
        else:
            lines = lines[1:]
        text = "\n".join(lines)
    return text.strip()


def render_defects_markdown(defects: list) -> str:
    if not defects:
        return "# Defect Triage Report\n\nNo failures detected in this run. ✅\n"
    lines = ["# Defect Triage Report", ""]
    for d in defects:
        lines.append(f"## {d['signature']} — {d.get('severity', 'Unknown')} severity")
        lines.append(f"- **Status:** {'Real defect' if d.get('is_real') else 'Flaky (not a defect)'}")
        lines.append(f"- **Affected tests:** {', '.join(d.get('test_names', []))}")
        lines.append(f"- **Likely root cause:** {d.get('likely_root_cause', '')}")
        lines.append(f"- **Suggested owner:** {d.get('suggested_owner', '')}")
        lines.append(f"- **Representative message:** `{d.get('representative_message', '')[:300]}`")
        lines.append("")
    return "\n".join(lines)


def triage_node(state: QEState) -> QEState:
    failures = state.get("failures", []) or []
    plan_json = state.get("plan_json", {}) or {}

    if not failures:
        return {"defects_json": [], "defects_markdown": render_defects_markdown([])}

    # --- cluster by heuristic signature ---
    clusters: dict = {}
    for f in failures:
        sig = _signature(f)
        cluster = clusters.setdefault(
            sig,
            {
                "signature": sig,
                "test_names": [],
                "representative_message": f.get("message", ""),
                "is_real": False,
                "priority_hint": "P2",
            },
        )
        cluster["test_names"].append(f["test_name"])
        if f.get("rerun_status") == "real":
            cluster["is_real"] = True
        cluster["priority_hint"] = _priority_from_plan(f["test_name"], plan_json)

    cluster_list = list(clusters.values())

    # --- LLM: severity + root cause + owner per cluster ---
    llm_input = [
        {
            "signature": c["signature"],
            "priority_hint": c["priority_hint"],
            "test_names": c["test_names"],
            "representative_message": c["representative_message"][:500],
        }
        for c in cluster_list
    ]
    raw = chat(
        settings.TRIAGER_MODEL,
        SYSTEM_PROMPT,
        json.dumps(llm_input, indent=2),
        temperature=0.1,
    )
    raw = _strip_code_fence(raw)
    try:
        enrichment = {item["signature"]: item for item in json.loads(raw)}
    except (json.JSONDecodeError, KeyError, TypeError):
        enrichment = {}

    defects = []
    for c in cluster_list:
        e = enrichment.get(c["signature"], {})
        defects.append(
            {
                **c,
                "severity": e.get("severity", "Medium" if c["is_real"] else "Low"),
                "likely_root_cause": e.get("likely_root_cause", "Unable to determine (LLM enrichment unavailable)."),
                "suggested_owner": e.get("suggested_owner", "Unassigned"),
            }
        )

    return {"defects_json": defects, "defects_markdown": render_defects_markdown(defects)}
