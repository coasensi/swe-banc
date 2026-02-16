# swe-banc: a swe-bench-style RL environment for software engineering

This project implements a reproducible, patch-based coding benchmark inspired by SWE-Bench. It evaluates whether a coding agent can repair a real historical regression in an open-source repository and provides a deterministic reward signal suitable for reinforcement learning.

The instance is grounded in a real FastAPI regression (PR #14349: https://github.com/fastapi/fastapi/pull/14349) involving incorrect handling of JSON Schema attributes named "$ref" during OpenAPI schema generation.

## what was built

### 1. task definition

tasks/fastapi_ref_schema_regression/
├── prompt.md
├── metadata.json
└── hidden_tests/
└── test_hidden_ref_schema_regression.py

task specifies:

- a broken commit
- hidden correctness tests (no exposure to the reference solution)

the agent must produce a patch that:
- prevents OpenAPI crashes
- preserves valid json schema `$ref` references
- works for nested and list-based models
- does not corrupt schema structure

### 2. Evaluation Engine (`eval.py`)

The evaluator performs:

1. Load task metadata
2. Checkout the broken commit
3. Apply an optional patch
4. Run hidden pytest suite
5. Compute reward and score

Example output:

```json
{
  "task_id": "fastapi_ref_schema_regression",
  "reward": 1,
  "score": 1.0,
  "passed": 4,
  "total": 4
}
```

### 3. patch hook (Agent interface)

agents interact via standard unified diffs:

```bash
python eval.py --task fastapi_ref_schema_regression --patch solution.patch
```

the patch is applied using git apply inside a sandbox checkout > ensures determinism, replayability and agent-environment separation

## how to run

The environment is fully containerized to ensure reproducibility.

```bash
git clone https://github.com/coasensi/swe-banc
cd swe-banc
docker build -t swe-banc
```

Run evaluation on the broken commit (should return reward:0):
```bash
docker run --rm swe-banc
```

Run evaluation with your patch:

you must mount a directory containing your patch:

```bash
docker run --rm \
  -v $(pwd)/attempts:/patches \
  swe-banc \
  python eval.py \
    --task fastapi_ref_schema_regression \
    --patch /patches/solution.patch
```

## why this matters for RL

this environment behaves like a one-step RL task:

- state: broken repository snapshot
- action: patch (unified diff)
- transition: apply patch
- reward: hidden test score

It supports:

- ranking agent attempts
- reward-based learning
- multi-task scaling
- reproducible evaluation

## futures directions

- penalize patch size/diff: could avoid test overfitting and agents rewriting entire files
- add time and agent runtime metrics
- integrate llm-based coding agents
- add a baseline agent and comparative scores
