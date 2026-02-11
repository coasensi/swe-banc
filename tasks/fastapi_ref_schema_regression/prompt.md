# Task: Fix JSON Schema `$ref` alias regression (FastAPI PR #14349)

## Context

In FastAPI, OpenAPI generation relies on JSON Schema produced from Pydantic models. Some Pydantic models legitimately include fields whose JSON key is `"$ref"` (typically via an alias), e.g. when modelling JSON Schema fragments.

A regression was introduced where certain models containing a `"$ref"` field/alias can cause OpenAPI schema generation to crash or produce incorrect output under Pydantic v2.

## Expected behavior

FastAPI must correctly support Pydantic models that contain JSON Schema attributes named `"$ref"` (for example, a field declared with `Field(alias="$ref")`) without breaking OpenAPI generation.

After your fix:

- Generating OpenAPI for an application using such a model must not raise an exception.
- The resulting OpenAPI/JSON Schema must remain valid and stable (do not drop or corrupt the model schema just because it contains a `"$ref"` field/alias).
- The fix must work with the repository’s supported Pydantic v2 configuration and should not break compatibility behavior elsewhere.

## Constraints

- Keep the change minimal and aligned with existing FastAPI patterns.
- Do not introduce new runtime dependencies.
- Do not change the public API surface unless strictly necessary.
- Ensure the solution is robust to nested schema structures (avoid brittle string-based hacks).

## How to reproduce / validate locally

Run the test that currently fails:

```bash
pytest tests/test_schema_ref_pydantic_v2.py -q