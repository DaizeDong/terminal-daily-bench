# Support response headers in @app.doc(responses={...})

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

[redacted-ref]

### What was happening

The custom response spec branch in `_generate_spec` only reads `content` and `description` out of the response dict:

```python
existing_response_content.update(value.get('content', {}))
if (new_description := value.get('description')) is not None:
    existing_response['description'] = new_description
continue
```

Anything else, including `headers`, was silently dropped. So there was no way to document the headers of an alternative response, even though `@app.output(..., headers=...)` has supported exactly that since 2.1.0.

### The change

`headers` is now read from the response dict. Since `@app.output` already takes a schema for its `headers` parameter, this follows the same convention rather than inventing a new one, which is the second of the two shapes proposed in the issue:

```python
@app.doc(responses={
    404: {
        'description': 'Custom error',
        'content': {'application/json': {'schema': SomeErrorSchema}},
        'headers': SomeHeaderSchema
    }
})
```

A schema class or instance goes through the same conversion `@app.output` uses, so header name normalization applies and `x_token` is emitted as `x-token`. Marshmallow schemas and Pydantic models both work.

A plain dict is already an OpenAPI headers object, so it is passed through untouched for anyone who would rather write it by hand:

```python
'headers': {'X-Token': {'description': 'The token.', 'schema': {'type': 'string'}}}
```

The conversion `_add_response` previously did inline moves into `_make_response_headers` so both paths build headers the same way, rather than duplicating the `in`/`name` stripping.

### Tests

`test_doc_responses_headers` covers a schema class, a schema instance, a raw dict, and a response with no `headers` key, and asserts the rest of the response spec is still applied. It fails on `main` with `KeyError: 'headers'` and passes with this change. Full suite is green at 403 passed and 1 skipped, and `ruff`, `ruff format` and `mypy` are clean.

Docs and the `doc` docstring are updated, and there is a `CHANGES.md` entry.

### Note

This is independent of [redacted-ref] and can be merged in either order. Both touch the `headers_schema` block in `_add_response`, so whichever lands second needs a one line rebase to keep the other's change. Happy to do that whenever you like.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
