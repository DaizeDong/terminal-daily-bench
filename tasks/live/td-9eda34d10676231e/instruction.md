# Register nested Pydantic schemas used in parameter locations

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

[redacted-ref]

### What was happening

Pydantic puts nested definitions like enums into `$defs` and points the property schemas at `#/components/schemas/{parent}.{model}`.

For request bodies that works, because `[redacted-repo]._register_schema_and_get_ref` pulls those definitions out and registers them. For parameter locations it did not. `schema_to_parameters` built the parameters straight from `properties` and discarded `$defs`, so the emitted `$ref` pointed at a schema that was never added to the document.

Using the example from the issue, `PetQuery.PetCategory` was referenced but never defined:

```json
{
  "in": "query",
  "name": "category",
  "schema": {"anyOf": [{"$ref": "#/components/schemas/PetQuery.PetCategory"}, {"type": "null"}]}
}
```

while `components/schemas` only held `PetIn`, `PetIn.PetCategory`, `PetOut`, `PetOut.PetCategory` and `ValidationError`.

This is not only a docs rendering problem. The spec is genuinely invalid, and `openapi_spec_validator` rejects it with `PointerToNowhere`.

### The change

`schema_to_parameters` now takes the `APISpec` and registers the nested definitions itself, reusing the existing `extract_pydantic_defs` helper so parameters and bodies resolve names the same way. Both call sites in `app.py` pass it through, one for operation parameters and one for response headers.

The new argument is optional and defaults to `None`, so calling `schema_to_parameters` without a spec keeps the old behaviour and nothing outside [redacted-repo] breaks.

I went with registering the schema rather than inlining the enum values, since the issue lists that as the expected behaviour and it matches what already happens for `location="json"`.

### Tests

Added to `tests/test_pydantic_integration.py`:

* a parametrised test covering `query`, `headers` and `cookies`, asserting the enum lands in `components/schemas` and the parameter references it
* a test that builds a spec mixing a body model and a query model, walks every `$ref` in the document and asserts none of them dangle

Both fail on `main` and pass with this change. The full suite is green, 406 passed and 1 skipped, and `ruff`, `ruff format` and `mypy` are clean.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
