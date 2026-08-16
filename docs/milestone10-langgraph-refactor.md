# Milestone 10: Orchestrator Refactor — Hand-Rolled State Machine → LangGraph

## Why this milestone exists

architecture.md's tech stack table always planned this two-step path:
build the orchestrator by hand first (Milestone 6) so the tool-calling
loop, retries, and state transitions are fully understood at a low level,
then refactor to LangGraph (Milestone 10) — the framework most companies
actually use in production — once that understanding exists. Adopting a
framework before understanding what it's abstracting away is how you end
up unable to debug it when it breaks.

## What changed, concretely

| | Before (Milestone 6) | After (Milestone 10) |
|---|---|---|
| File | `orchestrator.py` (now frozen as `orchestrator_legacy.py`) | `orchestrator.py` (rewritten) + `orchestrator_types.py` (shared data shapes, extracted) |
| Control flow | Sequential Python `if`/`return` statements | `StateGraph` with explicit nodes + conditional edges |
| State | Local variables passed through the function | A `TypedDict` (`PipelineState`) threaded through the graph |
| Public API | `run_pipeline()`, `PipelineResult`, `AgentInvocationRecord` | **Identical** — same names, same shapes, same call signature |
| Test suite | `tests/agents/test_orchestrator.py` | **Same file**, zero lines changed for the refactor itself (only additive tests from Milestone 9's coverage pass) |

The graph structure is a direct translation of the hand-rolled control
flow — not a redesign:

```
START -> research -[failed]-> END
                  -[ok]-> scoring -[failed]-> END
                                  -[score <= reject]-> reject_lead -> END
                                  -[ok]-> drafting -[failed]-> END
                                                    -[ok]-> guardrail -[failed]-> END (fail closed)
                                                                      -[approved]-> mark_ready -> END
                                                                      -[rejected]-> drafting_revision
                                                                                      -[failed]-> mark_flagged -> END
                                                                                      -[ok]-> guardrail_recheck
                                                                                                -[approved]-> mark_ready -> END
                                                                                                -[else]-> mark_flagged -> END
```

## The single most important verification in this milestone

**All 94 pre-existing tests pass with zero modifications** — including
`tests/agents/test_orchestrator.py`, `tests/services/test_lead_service.py`,
and `tests/api/test_leads.py`. One new test was added
(`test_pipeline_flags_when_recheck_itself_technically_fails`), but it
closes a coverage gap the refactor's structure made obvious, not a
behavior change.

This is the actual proof the refactor is behavior-preserving — a claim in
a docstring is not evidence, a green test suite that was never told about
the refactor is. This only works because `run_pipeline()` kept an
identical public contract; if the function signature or return shape had
changed, every caller (the service layer, every test) would have needed
updating, and a passing suite wouldn't prove much.

## Line count: LangGraph is not shorter

| File | Lines |
|---|---|
| `orchestrator_legacy.py` (frozen hand-rolled version) | 250 |
| `orchestrator.py` (LangGraph version) | 362 |
| `orchestrator_types.py` (shared types, extracted either way) | 103 |

The LangGraph version is **longer**, not shorter — worth being honest
about, since "adopting a framework reduces code" is the common assumption
and it's wrong here. Every node needs its own function (Python's `if`
fallthrough doesn't exist in a graph), and every transition needs an
explicit routing function instead of an inline `if`. What LangGraph buys
isn't fewer lines — it's:

- **A structural vocabulary that transfers.** Anyone who's used LangGraph
  before can read this graph's shape in seconds; the hand-rolled version
  requires reading the whole function top to bottom to reconstruct the
  same mental model.
- **Free visualization** (`compiled_graph.get_graph().draw_mermaid()`) —
  a diagram generated from the actual code, not a hand-drawn one that can
  drift out of sync with reality.
- **A path to features we're not using yet but might need**: checkpointing
  (pause/resume a long-running pipeline), human-in-the-loop interrupts
  (`interrupt_before`), streaming intermediate state to a frontend. Adding
  any of these to the hand-rolled version means building the mechanism
  from scratch; LangGraph has it built in.
- **Industry relevance.** This is genuinely what's asked about in AI
  Engineer interviews right now — being able to say "I built it by hand
  first, understood exactly what LangGraph abstracts, then migrated"
  is a stronger answer than either "I only know the framework" or
  "I don't know the framework at all."

## The one deliberate divergence: retries stay manual

LangGraph's `add_node(..., retry_policy=RetryPolicy(...))` exists and
would look simpler — but it only retries a node when the node's function
**raises an exception**. Every agent function in this project
(`research_company`, `score_lead`, etc.) deliberately never raises on
failure; it returns a `Result` object with `success`/`error`, specifically
so **every attempt — including failed ones — gets logged** to
`AgentInvocationRecord` for the `AgentLog` audit trail. That's not
incidental; it's the explainability requirement from Milestone 1.

Switching to exception-based retries to use `RetryPolicy` natively would
mean either:
1. Losing the per-attempt audit log (RetryPolicy retries silently), or
2. Wrapping every agent call in a `try/except` that re-raises just to
   satisfy RetryPolicy, then logging in the `except` block anyway —
   more code than what we have now, for the same result.

So each node still calls the shared `call_with_retry()` helper internally
(now in `orchestrator_types.py`, used by both the LangGraph version and
the frozen legacy one). LangGraph's job here is graph *structure and
routing* — not retry mechanics.

**When native `RetryPolicy` would be the right call instead:** if the
audit-log requirement didn't exist (e.g. a purely internal batch job where
only the final outcome matters, not the forensic trail of every attempt),
native RetryPolicy would be strictly simpler and the right choice. This
project's requirements point the other way.

## A simplification worth naming

The graph's state (`PipelineState`) carries the live `anthropic.Anthropic`
client, the `ICPConfig`, and tool implementations directly — not through
LangGraph's separate context/config mechanism, which is the "more
correct" way to pass runtime dependencies that shouldn't be part of
checkpointed state. This works because the graph runs entirely in-memory
with **no checkpointer configured** — nothing ever needs to serialize this
state to disk or across a process boundary.

If persistence/checkpointing were added later (e.g. to support pausing a
pipeline run and resuming it after a human review step), these fields
would need to move to context instead, since checkpointed state must be
serializable and a live client object isn't. Flagged here rather than
silently — this is exactly the kind of shortcut that becomes a real bug
report months later if nobody remembers why it was fine at the time.

## Bottom line

The refactor is complete, verified by an unmodified test suite, and the
tradeoffs are documented rather than hidden. The hand-rolled version isn't
deleted — it's frozen at `orchestrator_legacy.py` specifically so this
comparison has two real, runnable implementations to point at, not just
prose.
