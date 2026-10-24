"""Recompute the deterministic per-write columns in every results-truncated-<tag>-*.csv from the logs.

The regex behind `write_has_condition` and `rule_named` was widened on 2026-10-21
after the re-score jobs had started (it missed `max(..., 15)` and `5 <= discount`).
Views and verdicts are untouched; only these two columns are rewritten.
"""
import csv, glob, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import os
os.environ["LOGS"] = "logs/2026-09-23*"  # placeholder, overridden below
import run_truncated as rt

def columns_for(paths):
    out = {}
    for path in paths:
        from inspect_ai.log import read_eval_log
        log = read_eval_log(path)
        for sample in log.samples or []:
            msgs = sample.messages
            for k, cut in enumerate(rt.write_indices(msgs), start=1):
                prose = (msgs[cut].text or "").strip()
                out[(Path(path).name, sample.epoch, k)] = (
                    int(rt.rule_named(prose)), int(bool(rt.RULE_CONDITION.search(rt.write_command(msgs[cut])))))
    return out

logs = [str(rt.ROOT / rel) for rel in rt.BATCHES] + sorted(glob.glob(str(rt.ROOT / "logs/2026-10-21*")))
cols = columns_for(logs)
for f in sorted(glob.glob(str(rt.ROOT / "monitors/results-truncated-*-*.csv"))):
    rows = list(csv.DictReader(open(f)))
    if "write_index" not in rows[0]:
        continue
    changed = 0
    for r in rows:
        rn, wc = cols[(r["log"], int(r["epoch"]), int(r["write_index"]))]
        if (r["rule_named"], r["write_has_condition"]) != (str(rn), str(wc)):
            changed += 1
        r["rule_named"], r["write_has_condition"] = str(rn), str(wc)
    with open(f, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    print(f"{Path(f).name}: {len(rows)} rows, {changed} cells corrected")
