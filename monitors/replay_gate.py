"""Step 0 of the gate plan: replay old logs through the live gate, with no judge calls.

    .venv/bin/python monitors/replay_gate.py

Each run is walked in order. At every bash call the agent made, the gate's approver
is called with what Inspect would have handed it then: the conversation up to and
including the assistant message holding the call, and the call itself. The judge
is stubbed out; it records the text it was given and answers "general".

Two checks:
  render    with the old detector (the one the offline views were cut with), the
            text the gate would send to the judge must equal the saved cut C view
            in monitors/truncated-views-{marked,terse}/, character for character.
  trigger   with the fixed detector, list every write it fires on that the old one
            did not, and every write the old one fired on that it does not.
"""

import os
import sys
from pathlib import Path

import anyio

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "monitors"))

import gate  # noqa: E402
import run_truncated as rt  # noqa: E402
from gate_core import writes_discount, writes_discount_v2  # noqa: E402
from inspect_ai.log import read_eval_log  # noqa: E402

SETS = {"marked": None, "terse": "logs/2026-10-21*"}  # view folder -> LOGS glob (None: the six September batches)


class _Store(dict):
    def set(self, key, value):
        self[key] = value


def replay(messages, detector: str) -> list[tuple[int, str, str]]:
    """[(message index, command, text the judge was given)] for every write the gate judged."""
    seen: list[tuple[int, str, str]] = []
    current = {}

    async def fake_judge(model, evidence, rubric):
        seen.append((current["i"], current["cmd"], evidence))
        return {"verdict": "general", "reason": "", "raw": "", "stop_reason": "", "latency_s": 0, "model": model}

    gate._judge = fake_judge
    gate.store = lambda: current["store"]
    approve = gate.write_gate(mode="log", detector=detector)
    current["store"] = _Store()
    for i, m in enumerate(messages):
        if m.role != "assistant":
            continue
        for tc in m.tool_calls or []:
            current["i"], current["cmd"] = i, tc.arguments.get("command", "")
            anyio.run(approve, m.text or "", tc, None, messages[: i + 1])
    return seen


def saved_view(path: Path) -> str:
    """The view text of a dumped file, without its two header lines."""
    return path.read_text().split("\n", 2)[2][1:-1]


def main() -> None:
    match = differ = 0
    missing_saved, unreached = [], []
    extra_v2, lost_v2 = [], []
    for folder, pattern in SETS.items():
        if pattern:
            os.environ["LOGS"] = pattern
        else:
            os.environ.pop("LOGS", None)
        expected = {p.name for p in (ROOT / "monitors" / f"truncated-views-{folder}").glob("*-cutC.txt")}
        reached = set()
        for path, batch in rt.selected_logs().items():
            log = read_eval_log(path)
            for sample in log.samples or []:
                msgs = sample.messages
                old = replay(msgs, "v1")
                write_msgs = sorted({i for i, _, _ in old})
                for i, _, text in old:
                    k = write_msgs.index(i) + 1
                    name = f"{batch}-ep{sample.epoch}-w{k}-cutC.txt"
                    reached.add(name)
                    f = ROOT / "monitors" / f"truncated-views-{folder}" / name
                    if not f.exists():
                        missing_saved.append(name)
                    elif saved_view(f) == text:
                        match += 1
                    else:
                        differ += 1
                        print(f"DIFFERS: {folder}/{name}")
                old_cmds = {(i, c) for i, c, _ in old}
                new_cmds = {(i, c) for i, c, _ in replay(msgs, "v2")}
                for i, c in sorted(new_cmds - old_cmds):
                    extra_v2.append(f"{batch} ep{sample.epoch} msg{i}: {c[:200]!r}")
                for i, c in sorted(old_cmds - new_cmds):
                    lost_v2.append(f"{batch} ep{sample.epoch} msg{i}: {c[:200]!r}")
        unreached += sorted(f"{folder}/{n}" for n in expected - reached)

    print(f"\nrender: {match} identical, {differ} differ")
    print(f"gate judged a write with no saved view: {len(missing_saved)} {missing_saved}")
    print(f"saved view the gate never produced: {len(unreached)} {unreached}")
    print(f"\ntrigger: fixed detector fires on {len(extra_v2)} commands the old one did not")
    for line in extra_v2:
        print("  +", line)
    print(f"old detector fires on {len(lost_v2)} commands the fixed one does not")
    for line in lost_v2:
        print("  -", line)


if __name__ == "__main__":
    main()
