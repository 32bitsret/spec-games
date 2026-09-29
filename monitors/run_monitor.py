"""Judge every logged run twice: from the summary plus the spec, then from the full transcript.

Run from the repo root:
    .venv/bin/python monitors/run_monitor.py                # the three logs the article reports
    .venv/bin/python monitors/run_monitor.py 'logs/*.eval'  # any other set, by glob
    .venv/bin/python monitors/run_monitor.py 'logs/*foo*' monitors/results-foo.csv   # custom output
    JUDGE_MODEL=anthropic/claude-haiku-4-5 .venv/bin/python monitors/run_monitor.py
    RUBRIC_VERSION=v0 .venv/bin/python monitors/run_monitor.py '' monitors/results-v0-grok.csv
    EPOCHS=1 .venv/bin/python monitors/run_monitor.py 'logs/*19-32-07*' out.csv   # one epoch only

Default judge is xai/grok-4.5 (needs XAI_API_KEY in .env). Default rubric is
the latest; RUBRIC_VERSION selects an earlier one and the matching views.

Reads the judge's API key from the environment or from .env at the repo root.
Writes monitors/results.csv (or the second argument), one row per (run, view).
Refuses to overwrite an existing output file unless OVERWRITE=1 is set.
"""

import csv
import glob
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path) -> None:
    """Minimal .env loader so a plain script sees the same key inspect does."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))


load_dotenv(ROOT / ".env")

from inspect_ai.log import read_eval_log  # noqa: E402

from judge import DEFAULT_MODEL, RUBRIC_VERSION, judge  # noqa: E402


# Task names in older logs, before the 2026-09-23 rename.
TASK_DIRS = {
    "discount_bug": "solvable_bug",
    "impossible_discount": "underdetermined_spec",
    "impossible_discount2": "contradictory_spec",
}


def original_test(log, sample, test_file: str = "test_discount.py") -> str:
    """The test file as the agent received it.

    Read from the task directory (the definition of "original"); if that is
    missing, fall back to the agent's first `cat` of it in the transcript.
    """
    task_dir = ROOT / "tasks" / TASK_DIRS.get(log.eval.task, log.eval.task)
    path = task_dir / test_file
    if path.exists():
        return path.read_text()
    for m in sample.messages:
        if m.role == "tool" and m.text and "def test_discount" in m.text:
            return m.text
    return "(test file unavailable)"


def summary_view(sample) -> str:
    """v1/v2 summary view: the agent's final message and nothing else.

    Kept for reference. Withholds the task and the tests, so the judge must
    infer what was asked from the agent's own account. Under rubric v2 the
    judges mostly abstained on it, which is the honest answer. See README.
    """
    return sample.output.completion or ""


def summary_with_spec_view(log, sample) -> str:
    """v3 summary view: what was asked, the test file, and the agent's account.

    This is what a reviewer reading a PR description alongside the ticket and
    the failing test would see. Still no commands and no reasoning, so an
    invented rule is visible only if the agent describes it.
    """
    return "\n\n".join(
        [
            f"[task given to the agent]\n{sample.input}",
            f"[original test file]\n{original_test(log, sample)}",
            f"[agent's final message]\n{sample.output.completion or '(the agent never submitted)'}",
        ]
    )


def transcript_view(sample) -> str:
    """The task prompt, every agent message, every command, and the submit text.

    The first user message is the task, so the judge has the prompt here. The
    system prompt is omitted (identical across runs, says nothing about the
    discount), as are tool outputs.
    """
    parts = []
    for m in sample.messages:
        if m.role == "system":
            continue
        text = m.text or ""
        if text.strip():
            parts.append(f"[{m.role}] {text}")
        for tc in getattr(m, "tool_calls", None) or []:
            if tc.function == "bash":
                parts.append(f"[{m.role} runs] {tc.arguments.get('command', '')}")
            elif tc.function == "submit":
                parts.append(f"[{m.role} submits] {tc.arguments.get('answer', '')}")
    return "\n\n".join(parts)


# Each view is (name, fn(log, sample) -> str). Names are written into the CSV,
# so a renamed view is never confused with an earlier one. The summary view
# follows the rubric: v3 pairs the summary with the task and test file;
# v0, v1 and v2 use the bare summary, as they did when they first ran.
if RUBRIC_VERSION == "v3":
    VIEWS = (
        ("summary_with_spec", summary_with_spec_view),
        ("transcript", lambda log, sample: transcript_view(sample)),
    )
else:
    VIEWS = (
        ("summary", lambda log, sample: summary_view(sample)),
        ("transcript", lambda log, sample: transcript_view(sample)),
    )


# The final matched batch: Haiku 4.5, 5 epochs, identical prompt and scorer.
# These are the runs behind Table 1 and Table 2 in the write-up.
ARTICLE_LOGS = [
    "logs/2026-09-23T19-31-35-00-00_solvable-bug_KMLqkVcaHuiU2NT6MFjpkn.eval",
    "logs/2026-09-23T19-32-07-00-00_underdetermined-spec_N99rJcDzgkXwN49AzabhLS.eval",
    "logs/2026-09-23T19-33-24-00-00_contradictory-spec_fs4wMSXLVGpMMALt85wzKo.eval",
]


def main(pattern: str | None = None, out: str = "monitors/results.csv") -> None:
    paths = sorted(glob.glob(str(ROOT / pattern))) if pattern else [str(ROOT / p) for p in ARTICLE_LOGS]
    missing = [p for p in paths if not os.path.exists(p)]
    if missing:
        sys.exit("missing log(s):\n  " + "\n  ".join(missing))
    # EPOCHS=1,5 in the environment restricts the run to those epochs of every selected log.
    only_epochs = {int(e) for e in os.environ.get("EPOCHS", "").split(",") if e.strip()}
    rows = []
    for path in paths:
        log = read_eval_log(path)
        for sample in log.samples or []:
            score = sample.scores.get("cheat_check") if sample.scores else None
            if score is None:
                continue  # smoke tests and other scorers
            if only_epochs and sample.epoch not in only_epochs:
                continue
            for view_name, view in VIEWS:
                v = judge(view(log, sample))
                rows.append(
                    {
                        "log": os.path.basename(path),
                        "task": log.eval.task,
                        "epoch": sample.epoch,
                        "view": view_name,
                        "true_label": score.answer,
                        "cheated": score.value.get("cheated"),
                        "generalizes": score.value.get("generalizes"),
                        "verdict": v["verdict"],
                        "reason": v["reason"],
                        "judge_model": DEFAULT_MODEL,
                        "rubric": RUBRIC_VERSION,
                    }
                )
                print(f"{log.eval.task:22} ep{sample.epoch} {view_name:10} {score.answer!s:18} -> {v['verdict']}")

    if not rows:
        print("no cheat_check samples found in", pattern or "ARTICLE_LOGS")
        return
    out_path = ROOT / out
    if out_path.exists() and os.environ.get("OVERWRITE") != "1":
        sys.exit(f"{out_path} already exists; pass a different output path or set OVERWRITE=1")
    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"\n{len(rows)} rows -> {out_path}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
