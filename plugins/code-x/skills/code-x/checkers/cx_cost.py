# cmd_cost: validates and rolls up a WORK-ORDER-COST-LOG YAML file.
from cx_common import (
    findings_report, load_yaml, field_present,
    VALID_MODEL_TIERS, VALID_RESULTS, VALID_REVIEW_MODES, VALID_WASTE_FLAGS,
)


def _typed_int(entry: dict, field: str, entry_loc: str, findings: list, severity: str = "P1") -> int | None:
    """PBF-PROP-021 group-2 hole #4: return entry[field] as a validated int, or None when the
    field is absent/blank/wrong-typed. Uses `type(value) is int`, NOT `isinstance(value, int)` —
    `bool` is an `int` subclass in Python (`isinstance(True, int)` is True), so isinstance would
    silently let a boolean masquerade as a count. A YAML-QUOTED numeric (e.g. `review_fix_cycles:
    "4"`) previously made the field a str, which isinstance(..., int) already rejected — but
    SILENTLY, with no finding at all, so the quoted value just skipped every downstream
    comparison and a real one-and-done / anti-grind violation dodged the gate by quoting. This
    now fails LOUD: a wrong-typed field is itself a P1/P2 finding, never a silent skip."""
    if field not in entry or entry[field] is None:
        return None
    value = entry[field]
    if type(value) is not int:
        findings.append((severity, entry_loc,
            f"{field}={value!r} is not a real integer (got type {type(value).__name__}) — a "
            f"quoted or boolean value defeats the type-gated comparison this field feeds; fix "
            f"the YAML to an unquoted integer"))
        return None
    return value


def cmd_cost(args) -> int:
    log_path = args.log
    data, err = load_yaml(log_path)
    if err:
        print(f"FIX-FIRST\n  [P0] {log_path} — {err}")
        return 1

    if not isinstance(data, list):
        print(f"FIX-FIRST\n  [P0] {log_path} — cost log must be a YAML list of entries")
        return 1

    findings = []
    loc = log_path

    required_entry_fields = ["card_id", "stage", "actor", "model_family",
                              "model_tier", "files_read", "result"]

    for i, entry in enumerate(data):
        if not isinstance(entry, dict):
            findings.append(("P1", loc, f"entry[{i}] is not a mapping"))
            continue

        entry_loc = f"{loc}:entry[{i}]({entry.get('card_id','?')})"

        # Required fields
        for f in required_entry_fields:
            if not field_present(entry, f):
                findings.append(("P1", entry_loc, f"missing required field: {f}"))

        # model_tier valid
        tier = entry.get("model_tier", "")
        if tier and tier not in VALID_MODEL_TIERS:
            findings.append(("P1", entry_loc, f"model_tier '{tier}' not in {sorted(VALID_MODEL_TIERS)}"))

        # result valid
        result = entry.get("result", "")
        if result and result not in VALID_RESULTS:
            findings.append(("P1", entry_loc, f"result '{result}' not in {sorted(VALID_RESULTS)}"))

        # review_mode valid
        rm = entry.get("review_mode", "")
        if rm and rm not in VALID_REVIEW_MODES:
            findings.append(("P1", entry_loc, f"review_mode '{rm}' not in {sorted(VALID_REVIEW_MODES)}"))

        # waste_flags valid
        wf = entry.get("waste_flags") or []
        if isinstance(wf, list):
            for flag in wf:
                if flag not in VALID_WASTE_FLAGS:
                    findings.append(("P2", entry_loc,
                        f"unknown waste_flag '{flag}' — valid: {VALID_WASTE_FLAGS}"))

        # Waste alarm: flag over_read
        files_read = _typed_int(entry, "files_read", entry_loc, findings, severity="P2") or 0
        if files_read > 30:
            findings.append(("P2", entry_loc,
                f"over_read: files_read={files_read} — likely over kernel read budget"))

        # loops_used
        loops = _typed_int(entry, "loops_used", entry_loc, findings, severity="P2") or 0
        if loops > 3:
            findings.append(("P2", entry_loc,
                f"loop: loops_used={loops} — anti-grind lock (max 3 review-fix cycles)"))

        # review_fix_cycles: one-and-done rule (tracked SEPARATELY from self_heal_attempts)
        rfc = _typed_int(entry, "review_fix_cycles", entry_loc, findings, severity="P1")
        if rfc is not None and rfc > 1:
            findings.append(("P1", entry_loc,
                f"review_fix_cycles={rfc} > 1 violates one-and-done — review once, fix one batch, verify once "
                "(self_heal_attempts is a separate bounded loop and is NOT counted here)"))

        # wrong_model_tier: top model on a cheap task
        tier = entry.get("model_tier", "")
        stage = entry.get("stage", "")
        if tier == "top" and stage in ("REVIEW",) and not entry.get("waste_flags"):
            pass  # legitimate; no warning needed

    # Roll-up waste alarm
    total_top = sum(1 for e in data if isinstance(e, dict) and e.get("model_tier") == "top")
    total = len(data)
    top_ratio = total_top / total if total else 0

    if top_ratio > 0.5:
        findings.append(("P2", loc,
            f"waste-alarm: {total_top}/{total} cards used top model_tier ({top_ratio:.0%}) — consider cheaper tiers"))

    # PBF-PROP-021 group-2 hole #5 (VERIFY F13): `(e.get("loops_used") or 0)` crashed FATAL
    # (exit 2, `TypeError: unsupported operand type(s) for +: 'int' and 'str'`) the moment ANY
    # entry's loops_used was a truthy non-int (e.g. YAML-quoted "9") — `sum()` starts its
    # accumulator at int 0 and the str never coerces. The per-entry loop above already flags a
    # wrong-typed loops_used as its own finding; this roll-up only needs to not crash on it, so
    # a non-int value here contributes 0 rather than reaching the sum.
    total_loops = sum((e.get("loops_used") if type(e.get("loops_used")) is int else 0)
                       for e in data if isinstance(e, dict))
    if total_loops > total * 2:
        findings.append(("P2", loc,
            f"waste-alarm: total loops_used={total_loops} across {total} cards — repeated_review/loop pattern"))

    return findings_report(findings)
