# Code-X — VERSION-HISTORY

> The protocol's version ledger. It ships with the format only: a fresh install records
> its own folds here over time. This is a history ledger, **not** part of the every-session
> read path (see `KAIZEN.md`).

Every approved protocol change bumps the version (v1.01, v1.02, …) and appends ONE dated,
timestamped row below.

## Format

```
<version> | <date> <time> | <one-line summary of the fold> | <PROP-### applied>
```

> **Version-floor base token (PBF-PROP-023):** the CURRENT version's row MUST declare
> exactly one row-level `` base=`<40-hex sha>` `` token (the conflict-scan floor anchor,
> checker-parsed, fail-closed) — see `checkers/cx_kaizen.py::_version_floor_base_for_version`.
> The base is the commit the version's conflict-scans are anchored to, deliberately NOT
> the lock commit itself. Only the current version's row is ever queried; historical
> rows are append-only and never rewritten.

## History

_(empty — append one row per fold, newest at the bottom)_
