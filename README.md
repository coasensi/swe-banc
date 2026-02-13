# swe-banc: a swe-bench-style RL environment for software engineering

This project implements a reproducible, patch-based coding benchmark inspired by SWE-Bench. It evaluates whether a coding agent can repair a real historical regression in an open-source repository and provides a deterministic reward signal suitable for reinforcement learning.

The instance is grounded in a real FastAPI regression (PR #14349) involving incorrect handling of JSON Schema attributes named "$ref" during OpenAPI schema generation.

