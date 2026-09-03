# Replace deprecated argparse.FileType

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

`argparse.FileType` is [deprecated in python 3.14+]([redacted-url]).

Before this change, a deprecation warning about "FileType is deprecated" would be emitted:
```
$ PYTHONWARNINGS=all pytest -h                    
/home/sophia/miniconda3/envs/[redacted-repo]-dev/bin/pytest:10: DeprecationWarning: Parsing dates involving a day of month without a year specified is ambiguous
and fails to parse leap day. The default behavior will change in Python 3.15
to either always raise an exception or to use a different default year (TBD).
To avoid trouble, add a specific year to the input & format.
See [redacted-url]
  sys.exit(console_main())
/home/sophia/projects/[redacted-repo]/src/pytest_benchmark/plugin.py:260: PendingDeprecationWarning: FileType is deprecated. Simply open files after parsing arguments.
  type=argparse.FileType('wb'),
usage: pytest [options] [file_or_dir] [file_or_dir] [...]
```

With this change:
```
$ PYTHONWARNINGS=all pytest -h                    
/home/sophia/miniconda3/envs/[redacted-repo]-dev/bin/pytest:10: DeprecationWarning: Parsing dates involving a day of month without a year specified is ambiguous
and fails to parse leap day. The default behavior will change in Python 3.15
to either always raise an exception or to use a different default year (TBD).
To avoid trouble, add a specific year to the input & format.
See [redacted-url]
  sys.exit(console_main())
usage: pytest [options] [file_or_dir] [file_or_dir] [...]
```

Fixes [redacted-url]

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
