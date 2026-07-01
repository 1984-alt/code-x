# cmd_class_sweep: validate a class-sweep receipt (BF-PROP-005 / GPT #6).
#
#   cx check class-sweep <receipt>
#
# The anti-whack-a-mole self-audit that lets ONE review resolve a WHOLE CLASS of a finding
# WITHOUT re-review (the root cause of the Sample / v1.10 review loops): name the class + a
# DETECTION method that finds ALL instances, sweep the module, fix every hit, and PIN the
# class with a regression test. Trust = the test (cx + tests green), never a second model
# pass. A deterministic finding's fix is "done" only with this receipt. CHECK-ONLY.
from pathlib import Path

from cx_common import findings_report, load_yaml, field_present

CLASS_SWEEP_REQUIRED_KEYS = ("class", "scope_boundary", "detection_command",
                             "pre_fix_hits", "post_fix_count", "positive_control")


def cmd_class_sweep(args) -> int:
    receipt_path = args.receipt
    loc = receipt_path
    findings = []

    doc, err = load_yaml(receipt_path)
    if err or not isinstance(doc, dict):
        print(f"FIX-FIRST\n  [P0] {receipt_path} — {err or 'not a YAML mapping'}")
        return 1

    blk = doc.get("class_sweep")
    if not isinstance(blk, dict):
        findings.append(("P1", loc,
            "class_sweep block missing — a deterministic finding's fix ships with a class-sweep "
            "receipt {class, scope_boundary, detection_command, pre_fix_hits, post_fix_count, "
            "positive_control} (BF-PROP-005 / GPT #6)"))
        return findings_report(findings)

    missing = [k for k in CLASS_SWEEP_REQUIRED_KEYS if not field_present(blk, k)]
    if missing:
        findings.append(("P1", loc,
            f"class_sweep missing {missing} — the sweep must name the class, the scope boundary it "
            "covers, the detection command that finds ALL instances, the pre-fix hit list, the post-fix "
            "count, and a positive control (BF-PROP-005 / GPT #6)"))
        return findings_report(findings)

    pre = blk.get("pre_fix_hits")
    if not isinstance(pre, list) or not pre:
        findings.append(("P1", loc,
            "class_sweep.pre_fix_hits must be a non-empty list — the sweep enumerates EVERY instance of "
            "the class found across the module; whack-a-mole is fixing one instance, not the class (BF-PROP-005)"))

    try:
        post = int(blk.get("post_fix_count"))
    except (TypeError, ValueError):
        post = -1
    if post != 0 and not field_present(blk, "post_fix_remainder_reason"):
        findings.append(("P1", loc,
            "class_sweep.post_fix_count != 0 without a post_fix_remainder_reason — a class is either "
            "closed (post_fix_count 0) or the remainder is explicitly justified (BF-PROP-005)"))

    pc = blk.get("positive_control")
    if not (isinstance(pc, dict) and str(pc.get("planted_instance_detected", "")).lower() in ("yes", "true")):
        findings.append(("P1", loc,
            "class_sweep.positive_control must show planted_instance_detected: yes — a detection method "
            "that does not catch a planted instance does not prove it finds the class (B-PROP-004 discipline)"))

    if not field_present(blk, "regression_test_ref"):
        findings.append(("P1", loc,
            "class_sweep missing regression_test_ref — TRUST is the test, not a second opinion; a fix "
            "with no pinning regression test is not 'done' (so it is safe to never re-review it) (BF-PROP-005)"))
    else:
        rt = str(blk.get("regression_test_ref"))
        if Path(rt).is_absolute() or ".." in Path(rt).parts:
            findings.append(("P1", loc,
                f"class_sweep.regression_test_ref '{rt}' must be a repo-relative path (no absolute path / "
                ".. escape) — the pinning test lives in the repo (BF-PROP-005 / GPT review F7)"))

    return findings_report(findings)
