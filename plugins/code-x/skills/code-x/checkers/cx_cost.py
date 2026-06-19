# cmd_cost: validates and rolls up a WORK-ORDER-COST-LOG YAML file.
from cx_common import (
    findings_report, load_yaml, field_present,
    VALID_MODEL_TIERS, VALID_RESULTS, VALID_REVIEW_MODES, VALID_WASTE_FLAGS,
)


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
        files_read = entry.get("files_read", 0) or 0
        if isinstance(files_read, int) and files_read > 30:
            findings.append(("P2", entry_loc,
                f"over_read: files_read={files_read} — likely over kernel read budget"))

        # loops_used
        loops = entry.get("loops_used", 0) or 0
        if isinstance(loops, int) and loops > 3:
            findings.append(("P2", entry_loc,
                f"loop: loops_used={loops} — anti-grind lock (max 3 review-fix cycles)"))

        # review_fix_cycles: one-and-done rule (tracked SEPARATELY from self_heal_attempts)
        rfc = entry.get("review_fix_cycles")
        if isinstance(rfc, int) and rfc > 1:
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

    total_loops = sum((e.get("loops_used") or 0) for e in data if isinstance(e, dict))
    if total_loops > total * 2:
        findings.append(("P2", loc,
            f"waste-alarm: total loops_used={total_loops} across {total} cards — repeated_review/loop pattern"))

    return findings_report(findings)
