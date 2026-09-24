# spec-games

Experiments in how coding agents behave when the specification they are given
is solvable, underdetermined, or contradictory. Built on
[Inspect AI](https://inspect.aisi.org.uk/), run in Docker sandboxes, scored on
what the agent did to the world rather than on what it said.

Start with [`tasks/README.md`](tasks/README.md) for the headline finding and
the three-condition results table.

## Layout

| Folder | Role |
|---|---|
| `tasks/` | Environments: a buggy repo, a test file, a sandbox; one shared scorer in `tasks/_scoring.py` |
| `agents/` | Policies under test: solvers, prompts, tool sets |
| `monitors/` | Overseers that read transcripts and flag suspicious behaviour |
| `analysis/` | Aggregation of eval logs into tables |

`LOG.md` records corrections given to the coding agents that build each folder.

## Run

```bash
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.txt
echo 'ANTHROPIC_API_KEY=...' > .env
.venv/bin/python smoke.py
.venv/bin/inspect eval tasks/solvable_bug/task.py --model anthropic/claude-haiku-4-5 --epochs 5 --log-dir logs
```

Docker must be running for sandboxed tasks.
