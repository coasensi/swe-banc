FROM python:3.12-slim

# System deps for git + potential wheels needing compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
 && rm -rf /var/lib/apt/lists/*

# 1) Copy the harness (swe-banc) into /app
WORKDIR /app
COPY swe-banc/ /app/

# 2) Install harness deps used for scoring
RUN pip install --no-cache-dir -U pip \
 && pip install --no-cache-dir pytest pytest-json-report httpx

# 3) Copy YOUR FastAPI repo (including .git and your commits) into /repo/fastapi
COPY fastapi/ /repo/fastapi/

# 4) Install FastAPI in editable mode so tests/imports use this checkout
WORKDIR /repo/fastapi
RUN pip install --no-cache-dir -e .

# 5) Run evaluator using docker metadata
WORKDIR /app
CMD ["python", "eval.py", "--task-dir", "/app/tasks/fastapi_ref_schema_regression", "--harness-root", "/app", "--metadata", "metadata.docker.json"]
