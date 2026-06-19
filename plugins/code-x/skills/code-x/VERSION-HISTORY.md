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

## History

_(empty — append one row per fold, newest at the bottom)_
