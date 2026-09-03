# feat(ble): allow private_key=False to disable command signing

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Intent

Allow a Bluetooth vehicle to be constructed with signing explicitly disabled, for passive-listening use (a BLE listener that only decodes broadcasts and never sends a signed command). The existing `Commands.__init__` behavior - raise `ValueError("No private key.")` when no key is available - is correct and must stay unchanged. What was missing was a way to say "I am deliberately disabling signing" distinct from "I forgot to supply a key".

**`False`, not `None`, is that signal.** An earlier revision of this PR used a `KeyOmitted`/`KEY_OMITTED` sentinel default so that an explicit `private_key=None` became the opt-out. That was withdrawn: it is a silent behaviour change, not an additive one.

- On `main`, `private_key` defaults to `None` and the constructor branches on `if private_key:`, so an explicit `None` falls through to the parent's key and raises `ValueError("No private key.")` when there is none.
- Under the sentinel design, that same explicit `None` constructed successfully with signing disabled.

So a caller who wrote `private_key=None` meaning "I haven't got one" would have silently received a vehicle that cannot sign, in place of the error that used to tell them so - on a published, security-adjacent library. `False` avoids this entirely: `None` keeps its existing meaning for both omitted and explicit-`None` callers, and `False` is a value no current caller can already be passing, so opting out of signing has to be deliberate.

**Implementation trap worth naming:** `False` and `None` are both falsy, so a truthiness check (`if private_key:`) collapses the two states and reintroduces the bug in a new form. The constructor branches on identity (`is False`, `is not None`) throughout.

Any operation that actually needs to sign fails clearly instead of raising a generic `AttributeError`/`TypeError` deep in the crypto code: `SigningDisabled(LibraryError)` in `exceptions.py` is raised at the top of `Commands._handshake` - reached by `_command` (all signed commands) and by `_ensure_handshake` (signed reads) - and, per the round-1 review finding, at the top of `VehicleBluetooth.pair()`, whose fast path builds its whitelist request from `self._public_key` and calls `_send` directly without ever reaching `_handshake`. A signing-disabled vehicle can still receive broadcasts via the existing `listen_*` methods, since those never go through `_handshake`/`_command`.

`Vehicles.createBluetooth` turned out to have no `key` parameter at all, so the opt-out was unreachable from the Fleet-parented factory. It gains one as **keyword-only**, so no existing positional caller shifts; the two `NotImplementedError` overrides in `[redacted-repo]`/`Tessie` are kept in step with their "parameters match the Fleet API Bluetooth factory" docstring contract. Flagging this as the one piece of surface beyond what the previous revision touched.

Deliberately out of scope, per explicit instruction: did not touch the funnel, stream publisher, or any BLE decoding logic; did not change how keys are generated/loaded/stored; kept this to one constructor path (no new listener class or passive-mode subsystem).

## What Changed

- Dropped `KeyOmitted`/`KEY_OMITTED`. `Commands.__init__`'s `private_key` (and `key` on `VehicleBluetooth.__init__`, `Vehicles.createBluetooth`, `VehiclesBluetooth.create`/`createBluetooth`) defaults to plain `None` again, restoring `main`'s signature and behaviour for omitted **and** explicit-`None` callers. `False` is the new explicit "signing is disabled" value; branches use identity checks, never truthiness. `Commands.private_key` is typed `EllipticCurvePrivateKey | None`, its `None` meaning signing-disabled.
- `Vehicles.createBluetooth` gains a keyword-only `key` parameter (it previously had none), with matching updates to the `[redacted-repo]`/`Tessie` `NotImplementedError` overrides.
- Kept `SigningDisabled(LibraryError)` and both guards - `Commands._handshake` and `VehicleBluetooth.pair()`'s fast path - plus the regression test proving `pair()` raises before touching the transport.
- `tests/test_ble_null_key.py` adds `ExplicitNoneIsUnchangedTests`, asserting directly that `key=None` still raises `ValueError` with no parent key and still falls back when the parent has one - the regression this whole revision exists to prevent. The `key=False` cases cover construction with signing disabled (including overriding an available parent key), broadcast dispatch via `listen_vehicle_lock_state`, and `SigningDisabled` from a signed command, a bare handshake, and `pair()`.
- Updated the type annotations, docstrings, `docs/bluetooth_vehicles.md`'s "Passive listening without a private key" section, and the `AGENTS.md` gotcha - all of which described the sentinel design.

## Risk Assessment

✅ Low: `None` and omission now behave exactly as they do on `main` (verified against both revisions and asserted by test), so there is no behaviour change for any existing caller. The only new reachable state is one a caller must opt into with a literal `False`. The added `key` parameter on `Vehicles.createBluetooth` is keyword-only, so it shifts no existing positional argument.

## Testing

Full suite: **735 passed, 30 subtests** (733 on the previous head; +2 from the new explicit-`None` regression tests). `uv run ruff check tesla_fleet_api tests` and `uv run pyright tesla_fleet_api` both clean (0 errors). Beyond the suite, I exercised all four constructor states directly against the built library - omitted/no parent key → `ValueError`; explicit `None`/no parent key → `ValueError`; explicit `None` with a parent key → falls back; `False` → `private_key is None` even with a parent key available - confirming the explicit-`None` path matches `main` rather than the withdrawn sentinel behaviour.

## Pipeline

Updates from [git push no-mistakes]([redacted-url])

<!-- no-mistakes-pipeline-attestation:v1 {"head_sha":"[redacted-sha]","steps":[{"step":"intent","status":"completed"},{"step":"rebase","status":"completed"},{"step":"review","status":"completed"},{"step":"test","status":"completed"},{"step":"document","status":"completed"},{"step":"lint","status":"completed"},{"step":"push","status":"completed"},{"step":"pr","status":"running"},{"step":"ci","status":"pending"}]} -->

<details>
<summary>✅ **intent** - passed</summary>

✅ No issues found.
</details>

<details>
<summary>✅ **Rebase** - passed</summary>

✅ No issues found.
</details>

<details>
<summary>⚠️ **Review** - 1 info</summary>

- 🚨 `tesla_fleet_api/tesla/vehicle/bluetooth.py:1529` - The user intent states as required behavior: &[redacted-ref];raise it at the top of Commands._handshake - the single choke point every signed session goes through, reached both by _command (all signed commands) and by _ensure_handshake/pair()&[redacted-ref]; (also asserted verbatim in the AGENTS.md addition: &[redacted-ref];_handshake (the common choke point for every signed session, both _command and _ensure_handshake/pair() reach it)&[redacted-ref];). This is false for pair()&[redacted-ref];s fast path. pair() (bluetooth.py:1505) builds its WhitelistOperation request using self._public_key (line 1532) and calls self._send(msg, ...) directly (line 1549) without ever calling _handshake or checking self.private_key. _handshake is only reached from pair()&[redacted-ref];s slow path, inside _pair_probe() (line 1587), which only runs after the fast-path one-shot wait times out. For a vehicle constructed with key=None (signing disabled), __init__ sets self._public_key = b&[redacted-ref];&[redacted-ref]; (commands.py:481-486). Calling .pair() on such a vehicle therefore does NOT raise SigningDisabled up front as documented; instead it proceeds to connect_if_needed() and issues a real GATT write to the vehicle with a WhitelistOperation containing an empty PublicKeyRaw, sending a malformed pairing request to real hardware rather than failing clearly. This contradicts the intent&[redacted-ref];s explicit claim that _handshake is reached by pair(), and undermines the stated goal that any operation needing to sign now fails clearly instead of failing deep in the crypto/transport path - here it doesn&[redacted-ref];t fail at all before touching the transport. tests/test_ble_null_key.py does not cover pair(), only door_lock() and handshakeVehicleSecurity(). Recommended fix: add a self.private_key is None check (raising SigningDisabled) at the top of pair(), mirroring _handshake.

🔧 Fix: Raise SigningDisabled up front in pair() when private_key is None
1 info still open:

- ℹ️ `tests/test_ble_null_key.py` - The fix-round commit ([redacted-sha]) adds the SigningDisabled guard to pair() but adds no accompanying test exercising VehicleBluetooth.pair() with private_key=None. Existing tests in tests/test_ble_null_key.py only cover door_lock() and handshakeVehicleSecurity() (per the original round-1 finding), so the newly-fixed pair() path — the exact bug reported — still has zero regression coverage and could silently regress in a future refactor.
</details>

<details>
<summary>✅ **Test** - passed</summary>

✅ No issues found.
- `uv run pytest tests/test_ble_null_key.py -v (8 passed, including new test_pair_raises_signing_disabled_without_touching_transport)`
- <code>Manually reverted the pair() guard (removed the `if self.private_key is None: raise SigningDisabled()` lines) and reran the new test to confirm it fails without the fix (TypeError inside _raise_for_whitelist_reply, proving pair() proceeds to the transport), then restored the guard via `git checkout -- tesla_fleet_api/tesla/vehicle/bluetooth.py`</code>
- `uv run pytest tests/test_ble_null_key.py tests/test_ble_mocked_commands.py tests/test_ble_broadcast_confirmation.py tests/test_ble_broadcast_listeners.py -q (56 passed) as a targeted regression check around the touched BLE pairing/signing code`
</details>

<details>
<summary>✅ **Document** - passed</summary>

✅ No issues found.
</details>

<details>
<summary>✅ **Lint** - passed</summary>

✅ No issues found.
</details>

<details>
<summary>✅ **Push** - passed</summary>

✅ No issues found.
</details>

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
