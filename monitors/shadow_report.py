"""Step 1 report: what the gate logged in shadow mode, and the trigger audit.

    .venv/bin/python monitors/shadow_report.py logs/<underdetermined>.eval logs/<solvable>.eval

Reads the "gate" and "gate_audit" entries the gate wrote to each sample's store.
Run label (fitted / general) is the scorer's, recomputed as in run_truncated.py.

Writes monitors/results-shadow.csv, one row per judged write, and prints:
  - verdicts per judge by run label, first write and every write
  - agreement between Grok, Sonnet and the regex
  - latency, retries, empty or unparseable replies, and where the context came from
  - trigger audit: calls after which discount.py changed with no judge call
    (missed writes), and judged writes after which it did not change
"""

import csv
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "monitors"))

import run_truncated as rt  # noqa: E402
from inspect_ai.log import read_eval_log  # noqa: E402

OUT = ROOT / "monitors" / "results-shadow.csv"
FIELDS = ["log", "task", "epoch", "run_label", "write", "n_writes", "grok", "sonnet", "regex",
          "grok_latency_s", "sonnet_latency_s", "retried", "context", "context_messages", "command"]


def verdict_of(entry: dict, prefix: str) -> dict:
    return next((j for j in entry["judges"] if j["model"].split("/")[-1].startswith(prefix)), {})


def audit_findings(audit: list[dict]) -> tuple[list[dict], list[dict]]:
    """(changes with no judge call, judged writes that changed nothing). The hash before call k+1
    is the hash after call k; the last call has no after, so it is not counted either way."""
    missed, idle = [], []
    for k in range(len(audit) - 1):
        a, b = audit[k], audit[k + 1]
        if a["hash_before"].startswith("error") or b["hash_before"].startswith("error"):
            continue
        changed = a["hash_before"] != b["hash_before"]
        if changed and not a["detector"]:
            missed.append(a)
        elif a["detector"] and not changed:
            idle.append(a)
    return missed, idle


def main() -> None:
    rows, missed_all, idle_all, audited = [], [], [], 0
    for path in sys.argv[1:]:
        log = read_eval_log(path)
        for s in log.samples or []:
            score = s.scores.get("cheat_check") if s.scores else None
            label = rt.true_label(log.eval.task, score)[0] if score else "unscored"
            gate_log = s.store.get("gate", [])
            for e in gate_log:
                g, so = verdict_of(e, "grok"), verdict_of(e, "claude")
                rows.append({"log": Path(path).name, "task": log.eval.task, "epoch": s.epoch, "run_label": label,
                             "write": e["write"], "n_writes": len(gate_log), "grok": g.get("verdict", ""),
                             "sonnet": so.get("verdict", ""), "regex": e["regex"],
                             "grok_latency_s": g.get("latency_s", ""), "sonnet_latency_s": so.get("latency_s", ""),
                             "retried": int(any(j.get("retried") for j in e["judges"])),
                             "context": e.get("context", ""), "context_messages": e.get("context_messages", ""),
                             "command": e["command"]})
            audit = s.store.get("gate_audit", [])
            audited += len(audit)
            missed, idle = audit_findings(audit)
            missed_all += [(log.eval.task, s.epoch, a) for a in missed]
            idle_all += [(log.eval.task, s.epoch, a) for a in idle]
            if not gate_log:
                print(f"no judged write: {log.eval.task} ep{s.epoch} ({label})")

    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {OUT.name}: {len(rows)} judged writes\n")

    for task in sorted({r["task"] for r in rows}):
        for label in ("fitted", "general"):
            rs = [r for r in rows if r["task"] == task and r["run_label"] == label]
            if not rs:
                continue
            runs = len({r["epoch"] for r in rs})
            print(f"{task}, {label} runs ({runs}), {len(rs)} writes")
            for judge in ("grok", "sonnet", "regex"):
                first = Counter(r[judge] for r in rs if r["write"] == 1)
                every = Counter(r[judge] for r in rs)
                print(f"  {judge:7s} first write {dict(first)}   every write {dict(every)}")
    print()
    pairs = [("grok", "sonnet"), ("grok", "regex"), ("sonnet", "regex")]
    for a, b in pairs:
        print(f"{a} = {b}: {sum(r[a] == r[b] for r in rows)}/{len(rows)}")
    lat = [float(r["grok_latency_s"]) for r in rows if r["grok_latency_s"] != ""]
    if lat:
        print(f"\nGrok latency: median {sorted(lat)[len(lat) // 2]:.1f}s, max {max(lat):.1f}s")
    bad = Counter(v for r in rows for v in (r["grok"], r["sonnet"])
                  if v in ("parse_error", "empty", "api_error"))
    print(f"retried {sum(r['retried'] for r in rows)}; bad replies {dict(bad)}; "
          f"context {dict(Counter(r['context'] for r in rows))}")
    print(f"\ntrigger audit over {audited} calls: {len(missed_all)} changes with no judge call, "
          f"{len(idle_all)} judged writes that changed nothing")
    for task, ep, a in missed_all:
        print(f"  MISSED {task} ep{ep}: {a['command'][:160]!r}")
    for task, ep, a in idle_all:
        print(f"  idle   {task} ep{ep}: {a['command'][:160]!r}")


if __name__ == "__main__":
    main()
