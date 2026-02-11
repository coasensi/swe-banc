# C:\dev\SWE-smith\tasks\fastapi__ref_schema_regression\hidden_tests\test_hidden_ref_schema_regression.py

from __future__ import annotations

import json
from typing import List, Optional

import pytest
from fastapi import FastAPI, Body
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

class HiddenLeaf(BaseModel):
    ref_value: str = Field(alias="$ref")


class HiddenNode(BaseModel):
    leaves: List[HiddenLeaf]
    title: str


# Pydantic v2: ensure everything is fully built
HiddenLeaf.model_rebuild()
HiddenNode.model_rebuild()

def _find_all_ref_values(obj):
    """Return a list of all values of '$ref' keys found anywhere in a nested JSON-like object."""
    refs = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "$ref":
                refs.append(v)
            refs.extend(_find_all_ref_values(v))
    elif isinstance(obj, list):
        for item in obj:
            refs.extend(_find_all_ref_values(item))
    return refs


def _get_openapi(app: FastAPI) -> dict:
    # Ensure openapi generation is executed via the public method
    schema = app.openapi()
    # Sanity: must be JSON-serializable
    json.dumps(schema)
    return schema


def test_hidden_no_crash_and_preserve_property_named_ref():
    """
    A model that includes a field aliased to '$ref' must not break OpenAPI generation,
    and '$ref' must appear as a *property name* in the generated schema (not be treated
    as a JSON Schema reference at that level).
    """
    class ModelWithDollarRef(BaseModel):
        ref_value: str = Field(alias="$ref")
        other: int = 1

    app = FastAPI()

    @app.get("/item", response_model=ModelWithDollarRef)
    def read_item():
        return {"$ref": "hello", "other": 2}

    schema = _get_openapi(app)

    comps = schema.get("components", {}).get("schemas", {})
    assert comps, "Expected OpenAPI components/schemas to be present"

    # Find the schema for our model (name depends on pydantic config, but should be present)
    # We'll locate any component schema that defines a property named '$ref'
    candidates = [
        s for s in comps.values()
        if isinstance(s, dict) and isinstance(s.get("properties"), dict) and "$ref" in s["properties"]
    ]
    assert candidates, "Expected a component schema with a properties['$ref'] entry"

    model_schema = candidates[0]
    assert model_schema["properties"]["$ref"].get("type") in {"string", None}, "Expected '$ref' property to be a string-like schema"


def test_hidden_real_json_schema_refs_still_exist_for_components():
    """
    The fix must not remove genuine JSON Schema references used by OpenAPI.
    We require that some '$ref' keys still exist with values pointing to '#/components/schemas/...'
    """
    class Inner(BaseModel):
        x: int

    class Outer(BaseModel):
        inner: Inner
        ref_value: Optional[str] = Field(default=None, alias="$ref")

    app = FastAPI()

    @app.get("/outer", response_model=Outer)
    def read_outer():
        return {"inner": {"x": 1}, "$ref": "custom"}

    schema = _get_openapi(app)
    refs = _find_all_ref_values(schema)

    # We expect at least one genuine schema ref to components
    assert any(isinstance(r, str) and r.startswith("#/components/schemas/") for r in refs), (
        "Expected genuine JSON Schema $ref references to components/schemas to still exist"
    )


def test_hidden_nested_and_list_cases():
    """
    Nested models + lists: ensure OpenAPI generation remains stable and '$ref' can exist
    as a property name (alias) in component schemas.
    """
    app = FastAPI()

    @app.post("/node", response_model=HiddenNode)
    def create_node(node: HiddenNode = Body(...)):
        return node

    schema = _get_openapi(app)

    comps = schema.get("components", {}).get("schemas", {})
    assert comps, "Expected OpenAPI components/schemas to be present"

    assert any(
        isinstance(s, dict)
        and isinstance(s.get("properties"), dict)
        and "$ref" in s["properties"]
        for s in comps.values()
    ), "Expected '$ref' to appear as a property name in at least one component schema (nested/list case)"



def test_hidden_does_not_convert_property_ref_into_top_level_ref():
    """
    A common incorrect fix is to 'promote' '$ref' keys into actual JSON Schema refs.
    For a normal object schema, having top-level '$ref' would usually replace the object schema.
    We ensure our model schema is still an object with properties including '$ref'.
    """
    class Model(BaseModel):
        ref_value: str = Field(alias="$ref")
        y: int

    app = FastAPI()

    @app.get("/m", response_model=Model)
    def read_m():
        return {"$ref": "x", "y": 1}

    schema = _get_openapi(app)
    comps = schema.get("components", {}).get("schemas", {})

    # Locate our model schema by property signature
    found = None
    for s in comps.values():
        if isinstance(s, dict) and isinstance(s.get("properties"), dict):
            props = s["properties"]
            if "$ref" in props and "y" in props:
                found = s
                break

    assert found is not None, "Expected to find model schema with properties '$ref' and 'y'"
    assert found.get("type") == "object" or "properties" in found, "Expected an object schema"
    assert "$ref" not in found or "properties" in found, "If '$ref' exists, it must not replace the object schema"
