"""Smoke test: confirms inspect-ai, the Anthropic provider, and the API key all work.

Run:
    .venv/bin/python smoke.py
or:
    .venv/bin/inspect eval smoke.py --model anthropic/claude-opus-5

Logs land in ./logs (gitignored). View them with `inspect view`.
"""

import os
import sys

from inspect_ai import Task, eval, task
from inspect_ai.dataset import Sample
from inspect_ai.scorer import includes
from inspect_ai.solver import generate, system_message

MODEL = os.environ.get("INSPECT_EVAL_MODEL", "anthropic/claude-opus-5")


@task
def smoke() -> Task:
    return Task(
        dataset=[
            Sample(input="What is 2 + 2? Reply with just the number.", target="4"),
            Sample(input="What is the capital of France? Reply with just the city.", target="Paris"),
        ],
        solver=[
            system_message("Answer as briefly as possible."),
            generate(),
        ],
        scorer=includes(),
    )


if __name__ == "__main__":
    logs = eval(smoke(), model=MODEL, log_dir="logs")
    log = logs[0]
    if log.status != "success":
        print(f"FAIL: eval status={log.status}", file=sys.stderr)
        if log.error:
            print(log.error.message, file=sys.stderr)
        sys.exit(1)
    acc = next(
        (m.value for s in log.results.scores for name, m in s.metrics.items() if name == "accuracy"),
        None,
    )
    print(f"OK: model={MODEL} samples={log.results.total_samples} accuracy={acc}")
    sys.exit(0 if acc == 1.0 else 1)
