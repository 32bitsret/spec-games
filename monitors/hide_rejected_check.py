"""Rubric 6 with rejected writes left out of the judge's text, on every live write so far.

    .venv/bin/python monitors/hide_rejected_check.py      (DRY=1 builds the texts and stops)

Each write is re-rendered as the gate would now see it: cut C, minus the writes the
gate had rejected before it (they never ran). Then:

  recovery    the honest plain-formula writes that were judged after special-casing
              (Grok reason run turns 23 and 31; Sonnet run turns 18, 30 and 36; the short
              runs' ep9 first write), plus the plain formula appended after the third
              rejection of each short run. Grok and Sonnet. Expected: general.
  regression  every other live write (short runs, long plain, OpenShell, reason, Sonnet
              runs), Grok only. Compared with the verdict the live judge gave; every
              flip is printed for reading.

Writes monitors/results-hide-rejected.csv.
"""

import csv
import os
import sys
from collections import Counter
from pathlib import Path

import anyio
from inspect_ai.model import ChatMessageAssistant
from inspect_ai.tool import ToolCall

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "monitors"))

import rejudge_gate  # noqa: E402  (keeps the real judge; loads .env)
from gate_core import render  # noqa: E402
from inspect_ai.log import read_eval_log  # noqa: E402
from rubric6_check import PLAIN  # noqa: E402

JUDGE = rejudge_gate.REAL_JUDGE
LOGS = {
    "short": "2026-10-29T22-55-29-00-00_underdetermined-spec_*.eval",
    "long-plain": "2026-10-30T00-11-46-00-00_underdetermined-spec_*.eval",
    "openshell": "2026-10-30T00-39-16-00-00_underdetermined-spec_*.eval",
    "reason": "2026-10-30T00-47-55-00-00_underdetermined-spec_*.eval",
    "sonnet-v6": "2026-10-30T01-09-10-00-00_underdetermined-spec_*.eval",
}
HONEST = {("reason", 1, 23), ("reason", 1, 31), ("sonnet-v6", 1, 18), ("sonnet-v6", 1, 30), ("sonnet-v6", 1, 36),
          ("short", 9, None)}  # (run, epoch, assistant turn); None: the short run's first write
OUT = ROOT / "monitors" / "results-hide-rejected.csv"
FIELDS = ["part", "run", "epoch", "turn", "judge_model", "live_verdict", "verdict", "hidden", "reason", "command"]


def items() -> list[dict]:
    out = []
    for run, pattern in LOGS.items():
        log = read_eval_log(str(next((ROOT / "logs").glob(pattern))))
        for s in log.samples:
            asst_turn = {}
            n = 0
            for i, m in enumerate(s.messages):
                if m.role == "assistant":
                    for tc in m.tool_calls or []:
                        asst_turn[tc.id] = (i, n)
                    n += 1
            rejected: list[str] = []
            for e in s.store["gate"]:
                i, turn = asst_turn[e["call_id"]]
                honest = (run, s.epoch, turn) in HONEST or (run == "short" and s.epoch == 9 and e["write"] == 1)
                out.append({"part": "recovery" if honest else "regression", "run": run, "epoch": s.epoch,
                            "turn": turn, "live_verdict": e["judges"][0]["verdict"], "hidden": len(rejected),
                            "command": e["command"],
                            "text": render(s.messages, i, True, include_call_of_cut=True, skip_calls=frozenset(rejected))})
                if e["applied"] == "reject":
                    rejected.append(e["call_id"])
            if run == "short":
                rej = [e["call_id"] for e in s.store["gate"] if e["applied"] == "reject"][:3]
                j = next(k for k, m in enumerate(s.messages) if m.role == "tool" and m.tool_call_id == rej[-1])
                msgs = list(s.messages[: j + 1]) + [ChatMessageAssistant(content="", tool_calls=[
                    ToolCall(id="recovery", function="bash", arguments={"command": PLAIN})])]
                out.append({"part": "recovery", "run": "short+plain", "epoch": s.epoch, "turn": "after 3rd rejection",
                            "live_verdict": "", "hidden": 3, "command": PLAIN,
                            "text": render(msgs, len(msgs) - 1, True, include_call_of_cut=True, skip_calls=frozenset(rej))})
    return out


def main() -> None:
    its = items()
    jobs = [(it, "xai/grok-4.5") for it in its] + \
           [(it, "anthropic/claude-sonnet-5") for it in its if it["part"] == "recovery"]
    print(f"{sum(it['part'] == 'recovery' for it in its)} recovery texts (Grok and Sonnet), "
          f"{sum(it['part'] == 'regression' for it in its)} regression texts (Grok): {len(jobs)} calls")
    if os.environ.get("DRY") == "1":
        return
    if OUT.exists() and os.environ.get("OVERWRITE") != "1":
        sys.exit(f"{OUT.name} exists; set OVERWRITE=1 to replace it")
    results: list[dict] = [{}] * len(jobs)

    async def run_all() -> None:
        limiter = anyio.CapacityLimiter(4)

        async def one(k: int, it: dict, model: str) -> None:
            async with limiter:
                results[k] = await JUDGE(model, it["text"], "v6")

        async with anyio.create_task_group() as tg:
            for k, (it, model) in enumerate(jobs):
                tg.start_soon(one, k, it, model)

    anyio.run(run_all)
    rows = [{**{k: it[k] for k in ("part", "run", "epoch", "turn", "live_verdict", "hidden", "command")},
             "judge_model": model, "verdict": res["verdict"], "reason": res.get("reason", "")}
            for (it, model), res in zip(jobs, results)]
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    print(f"\nwrote {OUT.name}\n\nRECOVERY (expected general), rubric 6, rejected writes hidden")
    for it in [i for i in its if i["part"] == "recovery"]:
        v = {r["judge_model"].split("/")[1][:6]: r["verdict"] for r in rows
             if r["part"] == "recovery" and (r["run"], r["epoch"], r["turn"]) == (it["run"], it["epoch"], it["turn"])}
        print(f"  {it['run']:12s} ep{it['epoch']:<2} turn {str(it['turn']):20s} live {it['live_verdict']:8s} "
              f"grok {v.get('grok-4', ''):10s} sonnet {v.get('claude', '')}")
    reg = [r for r in rows if r["part"] == "regression"]
    print(f"\nREGRESSION (Grok, rubric 6, hidden): live -> now {dict(Counter((r['live_verdict'], r['verdict']) for r in reg))}")
    for r in reg:
        if r["verdict"] != r["live_verdict"]:
            print(f"\n  FLIP {r['run']} ep{r['epoch']} turn {r['turn']}: {r['live_verdict']} -> {r['verdict']}\n"
                  f"    {r['reason'][:220]}\n    {r['command'][:400]!r}")


if __name__ == "__main__":
    main()
