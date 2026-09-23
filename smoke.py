"""Smoke test: confirms inspect-ai, the Anthropic provider, and the API key all work.

Run:
    .venv/bin/python smoke.py
or:
    .venv/bin/inspect eval smoke.py --model anthropic/claude-haiku-4-5

Logs land in ./logs (gitignored). View them with `inspect view`.
"""

import os
import sys

from inspect_ai import Task, eval, task
from inspect_ai.dataset import Sample
from inspect_ai.scorer import includes
from inspect_ai.solver import generate, system_message

MODEL = os.environ.get("INSPECT_EVAL_MODEL", "anthropic/claude-haiku-4-5")


@task
def smoke() -> Task:
    return Task(
        dataset=[
            Sample(input="What is 2 + 2", target="4"),
        ],
        solver=[
            generate(),
        ],
        scorer=includes(),
    )