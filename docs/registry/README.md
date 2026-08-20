# W1 fixed-50 task images

This directory records the container publication for the frozen W1 task set:

- `w1-fixed50-images.prepublish.json` is the source-derived publication plan.
- `w1-fixed50-images.json` is the completed task/archive/OCI/registry mapping.
- `w1-fixed50-publish-receipt.json` records completion and whether anonymous pull was verified.

The set contains 50 task IDs backed by 49 unique gzip OCI-layout archives. Treat a registry reference as publicly usable only when the receipt has `public_pull_verified: true`.

After publication, pull a task environment by its stable task alias:

```sh
docker pull ghcr.io/daizedong/terminal-daily-task-envs:task-td-626b33ab47f3a6eb
```

Every unique archive also has a content-oriented tag, `img-<first 16 hex characters of the certified archive SHA-256>`. Task aliases that share one archive resolve to the same registry digest. For immutable automation, use `canonical_ref` from the completed manifest (called `expected_digest_ref` in the prepublication plan).

Three digests have different meanings:

- `archive.sha256` authenticates the exact deterministic gzip file stored by the W1 generation run. Docker does not pull this wrapper byte-for-byte.
- `oci.top_index_digest` identifies the OCI image index that the registry stores and is the expected digest in `docker pull ...@sha256:...`.
- `oci.linux_amd64_manifest_digest` identifies the runnable Linux/AMD64 image manifest selected from that index; the index also retains BuildKit attestation metadata.

The JSON records preserve the roster file identity, the existing authority/audit object-set digest, and separately specified canonical publication-plan digests that can be recomputed directly from their 49 object entries.
