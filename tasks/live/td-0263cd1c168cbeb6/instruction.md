# Fix: reproducibility when generating cmap .json.gz

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

**Pull request**

[redacted-url] pointed out that gzip reproducibility is current missing due to embedding mtime when generating cmap .json.gz files. The reply in [redacted-url] considered it to be minor, but downstream distributors would benefit from artifact generation reproducibility. See details in [redacted-ref] .

This commit properly set the generated gzip files' mtime=0, which solves the reproducibility issue. It also explicitly specify the gzip compression level (9 currently) to avoid reproducibility issues that may be triggered due to different values.

This pull request [redacted-ref] .

**How Has This Been Tested?**

The patch was tested manually, as well as tested in downstream Debian package [redacted-repo]/[redacted-sha]+dfsg-1 release.

**Checklist**

- [X] I have read [CONTRIBUTING.md]([redacted-url]).
- [X] I have added a concise human-readable description of the change to [CHANGELOG.md]([redacted-url]).
- [X] I have tested that this fix is effective or that this feature works.
- [X] I have added docstrings to newly created methods and classes.
- [X] I have updated the [README.md]([redacted-url]) and the [readthedocs]([redacted-url]) documentation. Or verified that this is not necessary.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
