"""Generator agent node.

Turns an approved test plan into concrete, executable pytest tests (using
`requests` against the configured SUT) plus any test data fixtures. Favors
a small number of meaningful negative/boundary cases over sheer volume, per
the assignment's guidance.
"""

from qe_agents import settings
from qe_agents.github_models import chat
from qe_agents.state import QEState

SYSTEM_PROMPT = f"""You are a senior SDET writing a pytest test file.

You will be given a JSON test plan (scenarios with priority/area/type). Write
ONE self-contained pytest file that implements 5-10 of the scenarios --
prioritize P0 first, then P1, then at most 1-2 P2s, and make sure you include
at least 2 genuinely meaningful negative or boundary cases (not just happy
path). Do not try to implement every scenario in the plan; pick the most
valuable subset given the limit.

Hard requirements for the generated code:
- Use the `requests` library against base URL `{settings.SUT_BASE_URL}`.
- Define `BASE_URL = "{settings.SUT_BASE_URL}"` at module level.
- Each test must be a standalone `def test_...():` function (no test classes),
  runnable directly with `pytest <file>.py`.
- For any test needing auth, call `POST {{BASE_URL}}/auth` with
  `{{"username": "admin", "password": "password123"}}` and use the returned
  token as `Cookie: token=<token>` header on the write request.
- Do NOT use `os.system`, `subprocess`, `eval`, `exec`, `socket`, or any file
  I/O outside of what pytest itself needs. Only use `requests`, `pytest`,
  standard assertions, and basic stdlib (json, datetime, uuid) as needed for
  building request bodies.
- Include a short docstring per test naming which plan scenario id it covers
  and why (e.g. "Covers TC-04 (P0, negative): totalprice must reject...").
- Because this hits a shared public demo instance, do not assert on exact
  response bodies where the docs said behavior is undocumented/ambiguous --
  assert on status codes and structural invariants instead, and add a code
  comment noting the ambiguity it relates to (link back to the plan's
  ambiguities by question text if applicable).

Respond with ONLY the raw Python source code for the test file. No markdown
fences, no commentary, no explanation before or after the code.
"""


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # drop first fence line (``` or ```python) and last fence line if present
        if lines[-1].strip().startswith("```"):
            lines = lines[1:-1]
        else:
            lines = lines[1:]
        text = "\n".join(lines)
    return text.strip() + "\n"


def generate_node(state: QEState) -> QEState:
    plan_json = state["plan_json"]
    user_prompt = (
        "Test plan (JSON):\n"
        f"{plan_json}\n\n"
        "Write the pytest file now, per the rules in your system prompt."
    )
    raw = chat(settings.GENERATOR_MODEL, SYSTEM_PROMPT, user_prompt, temperature=0.1)
    code = _strip_code_fence(raw)
    return {"generated_test_code": code}
