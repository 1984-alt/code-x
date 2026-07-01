# cmd_egress: the scrub-before-egress gate for a mandatory external reviewer (BF-PROP-005).
#
#   cx check egress <diff> --target <target> [--receipt <receipt>]
#
# CodeRabbit is now MANDATORY and reads the RAW repo diff automatically — so the scrub
# CANNOT be left to memory (GPT #1, the P0 of the BF-PROP-005 review). Before a diff is sent
# to an external reviewer, this gate requires EITHER:
#   (a) an `egress_scrub` receipt — the operator scrubbed the diff; bound to THIS diff's
#       hash, with a positive control that EXITS NONZERO (a planted secret IS caught,
#       B-PROP-004 discipline); a scrub receipt contradicted by remaining sensitive content
#       in the diff is rejected, OR
#   (b) a typed `sensitive_code_carveout` — local-only review, never uploaded (CEO ref +
#       reason; matters most for money apps where the diff stays on the machine).
# Neither = BLOCK. CHECK-ONLY: it never uploads or scrubs; it attests the receipt.
import hashlib
import re
from pathlib import Path

from cx_common import findings_report, load_yaml, field_present

# A conservative tripwire: a hit means "potential sensitive content" and (since a receipt /
# carve-out is mandatory anyway) is used mainly to catch a scrub receipt that did NOT scrub.
SENSITIVE_PATTERNS = [
    ("AWS access key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("hardcoded secret assignment",
     re.compile(r"(?i)(api[_-]?key|secret|password|passwd|token|bearer)\s*[:=]\s*['\"]?[A-Za-z0-9_\-\.]{12,}")),
    ("long digit run (account/PII)", re.compile(r"\b\d{12,}\b")),
]
SCRUB_REQUIRED_KEYS = ("target", "diff_hash", "scrub_command", "positive_control_exit", "produced_at")


def cmd_egress(args) -> int:
    diff_path = args.diff
    target = str(args.target)
    receipt_ref = getattr(args, "receipt", None)
    loc = diff_path
    findings = []

    try:
        diff_text = Path(diff_path).read_text(errors="replace")
    except OSError as e:
        print(f"FIX-FIRST\n  [P0] {diff_path} — cannot read the diff to be egressed: {e}")
        return 1
    diff_hash = hashlib.sha256(diff_text.encode()).hexdigest()[:12]
    hits = [name for name, rx in SENSITIVE_PATTERNS if rx.search(diff_text)]

    receipt = None
    if receipt_ref:
        receipt, rerr = load_yaml(receipt_ref)
        if rerr or not isinstance(receipt, dict):
            findings.append(("P0", loc,
                f"egress receipt {receipt_ref} unreadable: {rerr or 'not a YAML mapping'}"))
            return findings_report(findings)

    carve = (receipt or {}).get("sensitive_code_carveout")
    scrub = (receipt or {}).get("egress_scrub")

    if isinstance(carve, dict):
        missing = [k for k in ("ceo_decision_ref", "reason") if not field_present(carve, k)]
        if missing:
            findings.append(("P0", loc,
                f"sensitive_code_carveout missing {missing} — a local-only carve-out must record a "
                "CEO decision ref + reason (a sensitive diff stays on the machine, never uploaded) "
                "(BF-PROP-005 / GPT #1)"))
        else:
            print(f"PASS — egress to {target} carved out (local-only review): {carve.get('reason')}")
        return findings_report(findings)

    if isinstance(scrub, dict):
        for k in SCRUB_REQUIRED_KEYS:
            if not field_present(scrub, k):
                findings.append(("P0", loc,
                    f"egress_scrub missing {k} — the scrub receipt must pin the target, the diff hash "
                    "it scrubbed, the scrub command, a positive control, and produced_at (BF-PROP-005)"))
        if findings:
            return findings_report(findings)
        if str(scrub.get("target")) != target:
            findings.append(("P0", loc,
                f"egress_scrub.target '{scrub.get('target')}' != --target '{target}' (BF-PROP-005)"))
        if str(scrub.get("diff_hash")) != diff_hash:
            findings.append(("P0", loc,
                f"egress_scrub.diff_hash {scrub.get('diff_hash')} != the diff's sha12 {diff_hash} — the "
                "scrub receipt is not bound to THIS diff (stale / forged, or the diff changed) (BF-PROP-005)"))
        try:
            pce = int(scrub.get("positive_control_exit"))
        except (TypeError, ValueError):
            pce = 0
        if pce == 0:
            findings.append(("P0", loc,
                "egress_scrub.positive_control_exit must be NONZERO — a scrub whose positive control (a "
                "planted secret) is not caught is not proven to work (B-PROP-004 positive-control discipline)"))
        if hits and not findings:
            findings.append(("P0", loc,
                f"egress_scrub claims a clean diff but sensitive content remains in it ({hits}) — the scrub "
                "receipt is contradicted by the diff content (BF-PROP-005 / GPT #1; a PASS contradicted by "
                "evidence is a P0)"))
        if not findings:
            print(f"PASS — egress to {target} scrubbed + bound to diff {diff_hash} (positive control nonzero)")
        return findings_report(findings)

    # neither a scrub receipt nor a carve-out → BLOCK before any upload.
    detail = f"; sensitive content detected in the diff: {hits}" if hits else ""
    findings.append(("P0", loc,
        f"egress to {target} has NO scrub receipt and NO local-only carve-out — a raw diff must be "
        "scrubbed (an egress_scrub receipt) or explicitly carved out (sensitive_code_carveout) BEFORE it "
        f"is uploaded to an external reviewer{detail} (BF-PROP-005 / GPT #1)"))
    return findings_report(findings)
