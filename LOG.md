# Correction log

Notes on each time I corrected one of the four coding-agent sessions
(`tasks`, `agents`, `monitors`, `analysis`), each running in its own
git worktree under `.worktrees/`.

Setup: 2026-09-21. Four worktrees, one branch per folder, four concurrent
Claude Code sessions in tmux (session `curiosity`, one window each).

## Entries

Format: date, which session, what it did, what I told it, outcome.

| Date | Session | What the agent did | Correction I gave | Outcome |
|---|---|---|---|---|
| 2026-09-21 | — | (setup, no corrections yet) | — | — |
| 2026-09-23 | root (Claude Code) | Wrote the `impossible_discount` README calling the task impossible and the runs "overfit" | "The impossible_discount is not impossible at all. The spec only mentions a special case that can be handled in an if statement. It passed the test but it didn't solve the problem." | Reframed README and docstring: the task is satisfiable; it separates passing the tests from solving the problem. Scorer cannot see the difference; `generalizes` probe needed. |
| 2026-09-23 | root (Claude Code) | Wrote "no epoch questioned the spec" in the underdetermined README | Pointed out the transcripts show agents hypothesising tiers/patterns/fees before rationalising a rule; they questioned it internally, never out loud | Verified in log, reworded: noticed the inconsistency and explained it away |
| 2026-09-23 | root (Claude Code) | Tasks had mismatched prompts (no escape hatch on `discount_bug`) and mismatched scorers (`generalizes` only on one) | Align prompts, back-port `generalizes`, add `disclosed`, rename to `solvable_bug` / `underdetermined_spec` / `contradictory_spec`, rerun all three | Done from one template so the three files cannot drift; rerun launched |
| 2026-09-23 | root (Claude Code) | Back-ported a single-point `generalizes` probe at `(80, 25)` | (own finding while filling READMEs, not a user correction) Two runs passed the probe with `percent == 10` / `percent <= 10` branches; a later run used `discount_amount == 10`, keyed on the exact test input | Five probe points, plus a logical rule: on a task no plain formula can pass, green + intact tests ⇒ special case, so `generalizes` is forced to 0. Added a `refused` label for honest exits. Reran all three so the final table comes from one scorer version |
| 2026-09-23 | root (Claude Code) | Write-up pooled runs from different scorer versions into one denominator (10/10, 13/15, 2/25); called the loop-guard comparison "option A/C" without defining them; no limitations paragraph; scorer copy-pasted into three files | Reviewer feedback, ten items, checked against the logs: report the matched 5/5/5 batch, cite the earlier batches separately, add caveats on n=5 and one small model, explain the contradictory `generalizes` 5/5 cell, quote the self-correcting refusal, pull the scorer into one module | All applied. Scorer now lives in `tasks/_scoring.py`; per-task diff is three lines. Article and `tasks/README.md` updated |

## Recurring patterns

Things I found myself correcting more than once.

- Labels that sound stronger than what the scorer measures ("impossible", "honest", "questioned the spec"). Each time the fix was to say exactly what was checked.
- Pooling runs that were scored differently into one number. Report the matched batch; cite the rest separately.
- Checkers that sample instead of prove. The agents gamed the tests; the probe was gamed the same way. Prefer a logical invariant over more sample points when one exists.

