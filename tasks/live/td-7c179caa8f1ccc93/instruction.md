# feat(kernel): JWT private-key M2M auth on use_kernel=True

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## What

Adds OAuth **machine-to-machine auth with a JWT private-key client assertion** (RFC 7523) on the kernel backend (`use_kernel=True`). Instead of a client secret, the kernel signs a short-lived JWT with the service principal's private key and sends it as the `client_assertion` in the client-credentials grant; the workspace's OAuth IdP verifies it against the SP's registered public key.

Companion to the kernel-side feature ([redacted-repo]-sql-kernel [redacted-ref]; napi `token_url` in [redacted-ref]) and the parallel [redacted-repo]-sql-nodejs / [redacted-repo]-sql-go changes.

## How

- **`auth_bridge.py`** — new JWT branch in `build_kernel_auth_kwargs`, checked before shared-secret M2M and PAT (a private-key file is unambiguous JWT M2M intent). Forwards `oauth_client_id` + `oauth_jwt_key_file` + `oauth_jwt_kid` (+ optional `oauth_jwt_passphrase` / `oauth_jwt_algorithm` / `oauth_scopes` / `token_url`) to the kernel's `auth_type="oauth-m2m-jwt"`. Requires client_id + kid; mutually exclusive with `oauth_client_secret` / `credentials_provider` (both raise `NotSupportedError`).
- **`session.py`** — forward the new `oauth_jwt_*` / `token_url` connect kwargs into the kernel auth options.

## Usage

```python
from [redacted-repo] import sql
conn = sql.connect(
    server_hostname="adb-….azure[redacted-repo].net",
    http_path="/sql/1.0/warehouses/…",
    use_kernel=True,
    oauth_client_id="<sp-client-id>",
    oauth_jwt_key_file="/path/private_key.pem",
    oauth_jwt_kid="<kid>",
    token_url="[redacted-url]>/oauth2/v2.0/token",
    oauth_scopes=["<[redacted-repo]-resource-id>/.default"],
)
```

## Testing

- 9 new unit tests in `tests/unit/test_kernel_auth_bridge.py` (routing, precedence over M2M/PAT, required-field validation, ambiguity guards); full file **56 passing**.
- **Verified end-to-end** against an Azure [redacted-repo] warehouse: `SELECT 1` → `[Row(n=1)]`, with `conn.session.backend` asserted to be `Kernel[redacted-repo]Client` (kernel path, not Thrift) and `use_kernel` true.

Requires `[redacted-repo]-sql-kernel >= 0.2.0` with JWT support.

This pull request and its description were written by Isaac.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
