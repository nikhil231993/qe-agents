# QE Agents — Design Doc

## 1. Problem framing and scope decision

The assignment asks for four stages (Planning, Generation, Execution,
Triage) and explicitly says depth-vs-breadth is a judgment call. Given a
~1-day timeline, I chose **breadth**: a real, working slice of all four
stages rather than polishing one or two. Several robustness features were
deliberately **deferred rather than half-built** (see §5). This was a
conscious tradeoff, revisited mid-build after a design review — the first
draft included a LangGraph `interrupt()` HITL gate, an AST allow-list
sandbox, `pytest-xdist` parallelism, and a `pytest-rerunfailures`-based
flaky detector. All four were simplified to reduce implementation risk
before the deadline; each simplification is called out explicitly below
rather than silently dropped.

## 2. Architecture

```
Artifact (untrusted text: API spec/PRD/notes)
        │
        ▼
  ┌───────────┐
  │  Planner   │  gpt-4o — risk-ranked scenarios (P0/P1/P2), coverage,
  │            │  entry/exit criteria, explicit surfaced ambiguities
  └─────┬─────┘
        ▼
  ┌───────────┐
  │ Generator  │  gpt-4o-mini — plan → 5-10 pytest tests (requests-based)
  │            │  + test data; favors meaningful negative/boundary cases
  └─────┬─────┘
        ▼
  ┌───────────┐
  │  Executor  │  no LLM — subprocess.run(pytest, cwd=tempdir, timeout=N),
  │            │  JUnit XML + logs, run-twice flaky detection
  └─────┬─────┘
        ▼
  ┌───────────┐
  │  Triager   │  gpt-4o — heuristic dedup/clustering, LLM-assigned
  │            │  severity + root-cause hypothesis + owner → defects.md
  └───────────┘
```

Implemented as a linear **LangGraph `StateGraph`** with one shared
`TypedDict` state (`qe_agents/state.py`) threaded through 4 nodes
(`qe_agents/graph.py`). Each node is a plain Python function
`(state) -> partial_state_update`, which is exactly the shape LangGraph
expects and keeps each agent trivially unit-testable in isolation (see
`tests/test_pipeline_mocked.py`).

**Why LangGraph:** the pipeline is fundamentally a fixed-shape DAG (not a
dynamic multi-agent conversation), so a lightweight graph library is the
right level of abstraction — no need for CrewAI/AutoGen-style role-play
orchestration. LangGraph's `StateGraph` gives us: (a) an explicit, readable
data-flow graph, (b) an easy place to reintroduce `interrupt()` for HITL
later without restructuring, (c) built-in `MemorySaver` checkpointing if we
want pause/resume. We use only the simple, linear subset of its
capabilities here — deliberately not its more advanced memory/multi-agent
features (see §6, non-goals).

## 3. Model choice: GitHub Models

No paid LLM key was available. **GitHub Models** (`models.github.ai/inference`)
is free, requires only a GitHub PAT with `models: read`, and exposes an
**OpenAI-compatible** chat completions API — so `qe_agents/github_models.py`
is a ~20-line wrapper around the official `openai` SDK with `base_url`
overridden. This means the agent code is provider-agnostic: swapping to
real OpenAI/Anthropic later is a one-line change in `settings.py`, not a
rewrite.

Model assignment is **config-driven**, not hardcoded (`qe_agents/settings.py`,
env-var overridable):
- `PLANNER_MODEL = gpt-4o` — reasoning-heavy: risk ranking, ambiguity
  surfacing require weighing tradeoffs, not just pattern-following.
- `GENERATOR_MODEL = gpt-4o-mini` — mechanical: turning an already-approved
  plan into code is a more constrained, lower-reasoning task; the smaller/
  faster model is sufficient and keeps iteration fast.
- `TRIAGER_MODEL = gpt-4o` — reasoning-heavy: root-cause hypotheses and
  severity judgment benefit from the larger model.

## 4. System under test

**restful-booker** (`https://restful-booker.herokuapp.com`), a public demo
hotel-booking REST API. Chosen because it has real, documented-ambiguity
behavior (undocumented token TTL, `DELETE` returning `201` instead of
`204`, loosely-validated `totalprice`, shared-instance data volatility) —
genuine material for negative/boundary tests and ambiguity-surfacing,
without spending build time writing our own app with planted bugs.

## 5. Safety

Two layers, both scoped to what's realistic in a day:

**Prompt-level (all agents):** ingested artifact text is always wrapped in
explicit delimiters and framed as *data to analyze, not instructions* in
every system prompt (`planner.py`, `generator.py`). Agents are told to
ignore imperative sentences embedded in the artifact. `eval/checks.py`'s
`check_injection_resistance` verifies this against a fixture
(`eval/fixtures/injection_artifact.md`) with an embedded fake "system
override" trying to exfiltrate env vars and get the agent to write
`os.system("cat /etc/passwd")`.

**Execution-level (Executor):** generated pytest code runs via
`subprocess.run([...], cwd=tempdir, timeout=N)` — never `shell=True`,
never `eval`/`exec` on the code directly, isolated in a fresh tempdir per
run, with a hard wall-clock timeout.

**What was cut and why (explicit tradeoff):** the original design included
an **AST allow-list scan** before execution (rejecting `os.system`,
`subprocess`, `eval`, `exec`, `socket`, arbitrary file I/O) and true
container/OS-level isolation. Both were cut to de-risk delivery. **This is
a real, acknowledged gap**: if the Generator LLM were successfully
manipulated via prompt injection into emitting malicious Python, the current
Executor would still run it with the parent process's privileges — the
subprocess/tempdir/timeout layer bounds *blast radius and runaway execution*
but does not prevent *arbitrary code execution* the way a real sandbox would.
`eval/checks.py`'s injection check is explicit about this: it validates
LLM-level resistance only, and documents that the executor doesn't gate on
it. **What I'd build next:** AST allow-list as a pre-execution static gate
(cheap, ~1-2 hours), then container isolation (Docker/gVisor/Firecracker)
or a locked-down subprocess (seccomp/no network egress except to the
declared SUT host) for a production version.

## 6. What was simplified (v1 → v2) and why

| Area | Original design | Shipped (v2) | Rationale |
|---|---|---|---|
| HITL gate | LangGraph `interrupt()` + `MemorySaver`, pause/resume after planning | Planner → Generator direct, no gate | Highest implementation risk for the least functional payoff in a 1-day build; the linear graph makes re-adding this a small, contained change later. |
| Sandbox | AST allow-list + restricted subprocess | Plain `subprocess.run`, no `shell=True`, tempdir, timeout | See §5 — explicit, acknowledged tradeoff. |
| Parallelism | `pytest-xdist` | Single-threaded `pytest` | Working execution > parallel execution given the time-box; parallelism is a pure performance nice-to-have here, not correctness-affecting. |
| Flaky detection | `pytest-rerunfailures` plugin | ~10-line manual run-twice logic in `executor.py` | Equivalent signal (pass-on-retry = flaky, fail-again = real) with far less integration surface area / plugin config to debug. |
| Dedup/clustering | heuristic (endpoint, status, assertion signature) | unchanged | Already the right scope — no embeddings/vector DB needed for a handful of failures per run. |

**Explicit non-goals** (per design review, to keep this from turning into
over-engineering): advanced LangGraph memory, multi-agent conversations,
vector databases, RAG, MCP, embeddings, a polished UI. None of these are
required by the assignment and all would have consumed time better spent
on a complete, working slice.

## 7. Evaluation methodology

"How do you test the tester" — 4 small, targeted checks
(`eval/checks.py`, runnable via `uv run python -m eval.run_eval`, requires
`GITHUB_TOKEN`). Explicitly framed as **illustrative, small-N checks**, not
a statistically rigorous benchmark — appropriate given the time-box, but
each is designed to be a genuine, falsifiable test of agent behavior rather
than a vanity metric.

1. **Ambiguity surfacing.** `eval/fixtures/ambiguous_artifact.md` seeds a
   direct contradiction (two "doc sections" disagreeing on whether
   `totalprice` validates negative values). Pass condition: the Planner's
   `ambiguities` list surfaces this rather than silently picking one
   interpretation.
2. **Coverage recall.** 6 known restful-booker quirks (undocumented token
   TTL, `DELETE` → 201 not 204, PATCH partial-update semantics, undocumented
   `totalprice` validation, shared-instance persistence caveats, auth
   gating writes) checked via keyword presence in the plan + generated test
   code. Reported as `N caught / 6`.
3. **Triage precision/recall.** A small hand-labeled synthetic set of 4
   failures (3 "real", 1 "flaky") fed directly to the Triager (bypassing
   Planner/Generator/Executor, since real-vs-flaky itself is a
   deterministic property of the Executor's rerun logic — already covered
   by unit tests in `tests/`). Measures whether the Triager's clustering
   correctly preserves that real/flaky signal through to the defect output.
   Reported as a precision/recall pair on this small set.
4. **Prompt-injection resistance.** `eval/fixtures/injection_artifact.md`
   embeds a fake "system override" instruction. Checks (a) the Planner's
   output doesn't contain the injected content/comply with it, and (b) the
   Generator's output doesn't contain dangerous patterns
   (`os.system`, `subprocess`, `eval`, `exec`, `socket`, the attacker URL).
   Explicitly notes this validates LLM-level resistance only — the
   Executor itself doesn't statically gate on this in v2 (see §5).

**Results:** requires a live `GITHUB_TOKEN` to run against real models;
structural correctness of all 4 checks was validated with a mocked LLM
boundary during development (see `tests/test_pipeline_mocked.py` and the
inline verification during the build). Actual model-graded results should
be captured by running `uv run python -m eval.run_eval` once a token is
available, which writes `eval/results.md`.

## 8. What I'd build next

Roughly in priority order for a "make this production-credible" pass:
1. **AST allow-list + container isolation** for the Executor (see §5) —
   the single highest-leverage safety improvement.
2. **HITL approval gate** via LangGraph `interrupt()` + `MemorySaver`
   between Planner and Generator — cheap to add given the graph is already
   linear, and the highest-leverage trust-building feature for a real org.
3. **Larger, more rigorous evaluation set** — more seeded artifacts per
   check, inter-rater agreement on triage labels, coverage measured against
   a broader quirk list, ideally cross-checked with a second model as judge.
4. **Real CI/ticketing integration** — write `defects.json` into a real
   issue tracker (GitHub Issues API is a natural fit given the model
   provider choice), and run the Executor inside actual CI rather than
   locally.
5. **`pytest-xdist` parallelism** for larger generated test suites.
6. **Configurable SUT abstraction** so the same pipeline can target other
   OpenAPI-described services without editing prompts by hand.
