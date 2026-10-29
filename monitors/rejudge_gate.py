"""Step 2 of the gate plan: send the gate's cut C texts to the judges again and compare.

    .venv/bin/python monitors/rejudge_gate.py           (DRY=1 lists the calls and stops)

replay_gate.py showed the live gate builds the same 96 texts as the offline cut C
views. This sends each of those texts through the gate's own judge call (thread,
timeout, judge_detail) to every model in JUDGES, and compares the verdict with the
one recorded offline (rubric v5, cut C) in results-truncated-{rescore,terse}-<judge>.csv.

Two comparisons per row:
  verdict   same label as offline, or flipped
  action    what the gate would do (decide()) offline versus now; a flip here is
            a write the gate would have treated differently

Writes monitors/results-rejudge-gate.csv, one row per (text, judge).
"""

import csv
import os
import sys
from collections import Counter
from pathlib import Path

import anyio

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "monitors"))

import gate  # noqa: E402
import replay_gate  # noqa: E402  (imports run_truncated, which loads .env)
import run_truncated as rt  # noqa: E402
from inspect_ai.log import read_eval_log  # noqa: E402

REAL_JUDGE = gate._judge  # replay_gate.replay swaps in a stub; keep the real one
JUDGES = {"grok-4.5": "xai/grok-4.5", "sonnet-5": "anthropic/claude-sonnet-5"}
CSV_TAG = {"marked": "rescore", "terse": "terse"}  # view folder -> offline results tag
OUT = ROOT / "monitors" / "results-rejudge-gate.csv"
FIELDS = ["set", "batch", "epoch", "write_index", "true_label", "judge_model", "old_verdict", "new_verdict",
          "verdict_same", "old_action", "new_action", "action_same", "stop_reason", "latency_s", "reason"]


def texts() -> list[dict]:
    """Every cut C text the gate builds on the old logs, with the old detector (as in replay_gate)."""
    out = []
    for folder, pattern in replay_gate.SETS.items():
        if pattern:
            os.environ["LOGS"] = pattern
        else:
            os.environ.pop("LOGS", None)
        for path, batch in rt.selected_logs().items():
            for sample in read_eval_log(path).samples or []:
                seen = replay_gate.replay(sample.messages, "v1")
                write_msgs = sorted({i for i, _, _ in seen})
                for i, _, text in seen:
                    out.append({"set": folder, "batch": batch, "epoch": str(sample.epoch),
                                "write_index": str(write_msgs.index(i) + 1), "text": text})
    return out


def offline(folder: str, judge: str) -> dict:
    path = ROOT / "monitors" / f"results-truncated-{CSV_TAG[folder]}-{judge}.csv"
    return {(r["batch"], r["epoch"], r["write_index"]): r for r in csv.DictReader(open(path))
            if r["cut"] == "C" and r["rubric"] == "v5"}


async def run_all(jobs: list[tuple[dict, str, str]]) -> list[dict]:
    limiter = anyio.CapacityLimiter(int(os.environ.get("WORKERS", "4")))
    results: list[dict] = [{}] * len(jobs)

    async def one(n: int, item: dict, model: str) -> None:
        async with limiter:
            results[n] = await REAL_JUDGE(model, item["text"], "v5")
        print(f"  {n + 1}/{len(jobs)} {item['set']} {item['batch']} ep{item['epoch']} w{item['write_index']}"
              f" {model}: {results[n]['verdict']}", flush=True)

    async with anyio.create_task_group() as tg:
        for n, (item, _, model) in enumerate(jobs):
            tg.start_soon(one, n, item, model)
    return results


def main() -> None:
    items = texts()
    old = {(f, j): offline(f, j) for f in CSV_TAG for j in JUDGES}
    jobs = []
    for item in items:
        key = (item["batch"], item["epoch"], item["write_index"])
        for j, model in JUDGES.items():
            row = old[(item["set"], j)].get(key)
            if row is None:
                sys.exit(f"no offline row for {item['set']} {key} {j}")
            jobs.append((item, row, model))
    print(f"{len(items)} texts x {len(JUDGES)} judges = {len(jobs)} calls")
    if os.environ.get("DRY") == "1":
        return
    if OUT.exists() and os.environ.get("OVERWRITE") != "1":
        sys.exit(f"{OUT.name} exists; set OVERWRITE=1 to replace it")

    results = anyio.run(run_all, jobs)
    rows = []
    for (item, row, model), res in zip(jobs, results):
        old_v, new_v = row["verdict"], res["verdict"]
        old_a, new_a = gate.decide(old_v), gate.decide(new_v)
        rows.append({"set": item["set"], "batch": item["batch"], "epoch": item["epoch"],
                     "write_index": item["write_index"], "true_label": row["true_label"], "judge_model": model,
                     "old_verdict": old_v, "new_verdict": new_v, "verdict_same": int(old_v == new_v),
                     "old_action": old_a, "new_action": new_a, "action_same": int(old_a == new_a),
                     "stop_reason": res.get("stop_reason", ""), "latency_s": res.get("latency_s", ""),
                     "reason": res.get("reason", "")})
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    print(f"\nwrote {OUT.name}\n")
    for model in JUDGES.values():
        for folder in CSV_TAG:
            rs = [r for r in rows if r["judge_model"] == model and r["set"] == folder]
            print(f"{model} {folder}: {sum(r['verdict_same'] for r in rs)}/{len(rs)} same verdict, "
                  f"{sum(r['action_same'] for r in rs)}/{len(rs)} same action; "
                  f"new verdicts {dict(Counter(r['new_verdict'] for r in rs))}")
    flips = [r for r in rows if not r["verdict_same"]]
    print(f"\n{len(flips)} verdict flips:")
    for r in flips:
        mark = "  ACTION CHANGES" if not r["action_same"] else ""
        print(f"  {r['judge_model']} {r['set']} {r['batch']} ep{r['epoch']} w{r['write_index']} "
              f"(true {r['true_label']}): {r['old_verdict']} -> {r['new_verdict']}{mark}")


if __name__ == "__main__":
    main()
