FROM python:3.12-slim

# System deps for git + potential wheels needing compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy this repo into the image
COPY . /app

# Install harness deps used for scoring + running tests
RUN pip install --no-cache-dir -U pip \
 && pip install --no-cache-dir pytest pytest-json-report httpx

# Default command: run evaluator for the task (adjust flags to match your eval.py CLI)
CMD ["python", "eval.py", "--task", "fastapi_ref_schema_regression"]
