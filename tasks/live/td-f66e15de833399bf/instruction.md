# Flag incomplete annotations on BoundingDimensions

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Summary

Adds two fields to `BoundingDimensions` so a consumer can tell an exact envelope from a lower bound.

Drawings frequently leave a component's outermost geometry undimensioned. Tabs, winglets, lugs, standoffs and welded-on brackets are drawn in the views, but no dimension line reaches them. The bounding dimensions derived from such a drawing are correct for the dimensioned body and *smaller than the real part* — and today that reading is indistinguishable from one where every extent is annotated.

```python
annotations_complete: bool = True
completeness_note: Optional[str] = None
```

Suppressing the value in that situation would be worse than reporting it: a close lower bound is useful. So the values still come through, and the flag says not to treat them as exact.

## Worked example

A welded sheet-metal enclosure dimensioned `47.14 x 44.54` with a `4.60` box depth. Its side panels carry small winglets, and a lift lug protrudes below the box; neither is dimensioned anywhere on the drawing. The response now carries:

```json
{
  "enclosing_cuboid": { "width": 47.14, "height": 44.54, "depth": 4.60 },
  "annotations_complete": false,
  "completeness_note": "The winglets on the side panels and the lift-plate lug extending below the box carry no explicit dimensions, so the reported depth and height are lower bounds and the true envelope is slightly larger."
}
```

## Version

Bumped `2.6.0` -> `2.7.0`. Minor, since this is purely additive. Follows the precedent of [redacted-ref], which bumped the minor version in the same PR as the new exception type.

## Compatibility

Both fields have defaults, so this is additive:

- existing producers construct `BoundingDimensions` unchanged
- payloads from older servers omit both keys and validate to `annotations_complete=True`, which is the correct reading of "no qualification given"
- no existing field changes type or meaning

Note for producers: pydantic ignores unknown keyword arguments, so a service that starts passing these two fields against an older client release will keep working while silently dropping them. Worth an explicit check on the producer side that the installed model has the fields.

## Testing

New `tests/test_bounding_dimensions_completeness.py` (4 tests): defaults, the flagged case including that the dimensions are still delivered, JSON round-trip, and validation of payloads that omit both fields.

- `tests/test_bounding_dimensions_completeness.py` — 4 passed
- full tracked test suite — 163 passed

The 16 failures present in my working tree come from untracked work in progress (`tests/test_usage_client.py`, `tests/test_homogeneity_grade_validation.py`, which depend on an uncommitted `werk24/models/v2/usage.py`). They are unrelated to this change and none of those files are touched here.

## Consumer

core-reader populates these from its external-dimension extraction and emits them on `dimensions_after_processing` of the insights response. That side is ready and gated on this landing.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
