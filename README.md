# QE Agents

Agentic system covering the testing lifecycle end-to-end: an ingested API
artifact goes in, a triaged defect report comes out.

```
Artifact (API spec/notes)
  → Planner   (risk-based test plan, surfaces ambiguities)
  → Generator (executable pytest tests + test data)
  → Executor  (sandboxed run, JUnit XML, real-vs-flaky detection)
  → Triager   (dedup, severity, root cause, owner) → defects.md
```

See [`DESIGN.md`](./DESIGN.md) for architecture, model/framework rationale,
evaluation results, safety approach, and what's next.

## Requirements

- Python 3.13, [`uv`](https://docs.astral.sh/uv/)
- A GitHub token with **"models: read"** permission, to call
  [GitHub Models](https://github.com/marketplace/models) (using OpenAI
  GPT-4o/GPT-4o-mini through GitHub's hosted inference API — no OpenAI API
  key required).

## Setup

```bash
git clone <this-repo>
cd qe-agents
uv sync
```

Authenticate with GitHub Models (recommended):

```bash
gh auth login
export GITHUB_TOKEN=$(gh auth token)
```

Or, if you already have a Personal Access Token with `models: read` permission:

```bash
export GITHUB_TOKEN=<your_token>
```

## Run the end-to-end demo

> **Note:** The Planner, Generator, and Triager call GitHub Models and
> therefore require `GITHUB_TOKEN`. If you only want to verify the project
> structure without model inference, run the mocked test suite below.

```bash
uv run python -m qe_agents.run
```

This runs the full pipeline against the bundled [restful-booker](https://restful-booker.herokuapp.com)
API artifact (`eval/fixtures/restful_booker_spec.md`) and writes all
intermediate artifacts to `artifacts/<run_id>/`:

```
artifacts/<run_id>/
  plan.md            # human-readable risk-based test plan
  plan.json          # structured plan (scenarios, priorities, ambiguities)
  generated_test.py  # the pytest file the Generator wrote
  junit.xml          # test execution results
  stdout.log / stderr.log
  failures.json       # per-test real-vs-flaky classification
  defects.md         # final triaged defect report (human-readable)
  defects.json       # same, structured
```

To point it at your own artifact:

```bash
uv run python -m qe_agents.run path/to/your_artifact.md
```

## Run tests

Fast, offline, **no GitHub token required**. These tests mock the LLM
boundary and validate the LangGraph orchestration, executor sandboxing, and
triage logic:

```bash
uv run pytest tests/ -v
```

## Run the evaluation harness

Requires `GITHUB_TOKEN` (calls the real agents against seeded fixtures):

```bash
uv run python -m eval.run_eval
```

Writes results to `eval/results.md`. See `DESIGN.md` for what each of the 4
checks measures and why.

### Latest committed results

A real run against GitHub Models is already checked in at
[`eval/results.md`](./eval/results.md) so you can see actual pass/fail
output without needing a token yourself. Summary as of the last run:

| # | Check | Result |
|---|---|---|
| 1 | Ambiguity surfacing (seeded `totalprice` contradiction) | ✅ PASS |
| 2 | Coverage recall (known restful-booker quirks) | ✅ PASS (5/6 quirks caught) |
| 3 | Triage precision/recall (real vs flaky, labeled set) | ✅ PASS (precision 1.00, recall 1.00) |
| 4 | Prompt-injection resistance | ✅ PASS |

Re-running with your own `GITHUB_TOKEN` will overwrite this file with a
fresh run. Results are model-graded against a live LLM and a shared public
demo API, so minor variation between runs (e.g. exact quirks caught, wording
of root-cause text) is expected — see `DESIGN.md` §7 for methodology
details and caveats.

## Scope note

This is a 1-day design-exercise build: breadth over depth across all four
stages, with several safety/robustness features (AST-gated sandboxing, a
human-in-the-loop approval gate, parallel test execution) deliberately
deferred rather than half-built. These tradeoffs — and what a hardened
version would add — are called out explicitly in `DESIGN.md`.
