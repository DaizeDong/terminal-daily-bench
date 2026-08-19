# Fix cache/complement/index/skip attributes shadowing Table methods

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

Follow-up to [redacted-ref] and [redacted-ref], finishing the same collision class.

## The class

`Table` gets most of its fluent API from module-level assignments
(`Table.cache = cache`, `Table.complement = complement`, `Table.skip = skip`)
plus the methods it inherits from `IterContainer` (`index`, `min`, `list`, ...) —
263 callables in total. Views then store their constructor arguments as instance
attributes of the same name. Python resolves the instance attribute first, so the
method is gone and calling it raises `TypeError`:

```python
>>> import [redacted-repo] as etl
>>> etl.sort([['foo'], ['a']], 'foo').cache()
TypeError: 'bool' object is not callable
>>> etl.select([['foo'], ['a']], lambda row: True).complement([['foo']])
TypeError: 'bool' object is not callable
>>> etl.addfield([['foo'], ['a']], 'bar', 1).index(('a', 1))
TypeError: 'NoneType' object is not callable
```

[redacted-sha] ([redacted-ref]) hit this on `header`, [redacted-ref] on `dicts`, [redacted-ref] on the remaining
thirteen `header` sites. I went back over the whole surface rather than the one
call I tripped over, by intersecting the 263-name API with every `self.<name> =`
assignment in a `Table` subclass. Twelve views were still affected:

| method | view | file |
|---|---|---|
| `cache()` | `HashJoinView` | `transform/hashjoins.py` |
| `cache()` | `HashLeftJoinView` | `transform/hashjoins.py` |
| `cache()` | `HashRightJoinView` | `transform/hashjoins.py` |
| `cache()` | `SortView` | `transform/sorts.py` |
| `cache()` | `CacheView` | `util/materialise.py` |
| `complement()` | `SearchView` | `transform/regex.py` |
| `complement()` | `RowSelectView` | `transform/selects.py` |
| `complement()` | `FieldSelectView` | `transform/selects.py` |
| `index()` | `AddFieldView` | `transform/basics.py` |
| `index()` | `MoveFieldView` | `transform/basics.py` |
| `skip()` | `AvroView` | `io/avro.py` |
| `skip()` | `BcolzView` | `io/bcolz.py` |

All twelve raise today; all twelve pass after the change, and the scan now comes
back empty.

## The fix

Rename the stored attribute with a leading underscore, the convention [redacted-sha]
introduced for `header` and [redacted-ref] followed for `dicts`.

The compatibility question that came up on [redacted-ref] does not arise here. `.dicts` was
the caller's own input data, so that PR kept it readable through a property. These
twelve are internal flags and offsets (`cache=True`, `complement=False`, `index=0`,
`skip=0`) — nothing in the docs, examples or tests reads them back off a view, and
`grep` finds no reader outside the class that owns them. So a plain rename, no shim.

I also looked at fixing this at the root, in `Table` itself: a `__setattr__` that
refuses to store an attribute shadowing a method would catch the whole class
permanently. It would put a Python-level call on every attribute write in every
view for a problem that only bites at construction time, and it would break any
downstream subclass doing the same thing. Not worth it — a test can do the same
job for free.

## Tests

`test_method_shadow.py` grows from the thirteen `header` cases to cover the four
new names: one test per view calling the method that used to raise, plus tests
that the renamed attributes still carry their options (`cache=False` really
disables caching, `complement=True` really inverts the selection, `index=0` really
positions the field, `skip=n` really skips). `fromavro`/`frombcolz` are driven
without fastavro and bcolz installed, since neither is needed to reach the
skipping code.

`test_no_shadowed_api_names` is the one that matters: it walks the package,
finds every `Table` subclass, and fails if any of them assigns an instance
attribute named after an API method — reporting file, line, class and name. It
reproduces all twelve sites on master and would have caught [redacted-ref], [redacted-ref] and [redacted-ref]
as well. A deliberate class-level override (`DictsView.dicts`, the property [redacted-ref]
added) is not flagged.

586 pass, 13 skip; `pytest --doctest-modules` 739 pass, 21 skip. I mutated each
renamed read in both directions — leaving a site shadowed, and dropping or
inverting the option the attribute carries — and every mutant is caught.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
