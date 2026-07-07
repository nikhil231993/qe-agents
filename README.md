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
  [GitHub Models](https://github.com/marketplace/models) (free, OpenAI-compatible
  API — no paid LLM key needed).

## Setup

```bash
git clone <this-repo>
cd qe-agents
uv sync
```

Set your token (either via `gh` CLI or a manually-created PAT):

```bash
# Option A: using the GitHub CLI
gh auth login
export GITHUB_TOKEN=$(gh auth token)

# Option B: paste a PAT with "models: read" scope directly
export GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
```

## Run the end-to-end demo

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

Fast, offline, no token required — these mock the LLM boundary and validate
the LangGraph wiring, executor sandboxing, and triage clustering logic:

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

## Scope note

This is a 1-day design-exercise build: breadth over depth across all four
stages, with several safety/robustness features (AST-gated sandboxing, a
human-in-the-loop approval gate, parallel test execution) deliberately
deferred rather than half-built. These tradeoffs — and what a hardened
version would add — are called out explicitly in `DESIGN.md`.
