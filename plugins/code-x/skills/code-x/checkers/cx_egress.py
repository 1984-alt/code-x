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

from cx_common import findings_report, load_yaml, field_present, resolve_risk_tier

# A conservative tripwire: a hit means "potential sensitive content" and (since a receipt /
# carve-out is mandatory anyway) is used mainly to catch a scrub receipt that did NOT scrub.
#
# PBF-PROP-021 hole #12 (round 1): the old sole PII shape was a blanket `\b\d{12,}\b` (any bare
# run of 12+ digits) — it MISSED the two money-app-real shapes (an 11-digit raw Indonesian
# mobile number, and a 10-digit bank account number both fall under 12) while ALSO being a "dead
# tripwire" residual risk (any long benign digit run would trip it with zero PII signal).
# Replaced with two STRUCTURED patterns: an Indonesian mobile number, and a bounded bare
# 10-digit run (bank-account-style number).
#
# PBF-PROP-021 P1-3 (GPT-5.5 xhigh built-code review, round 2): the hand-grown separator class
# (`[-\s]?`) still missed dot and parenthesis formats — `0812.3456.7890`, `(0812) 3456 7890`,
# `+62 (812) 3456-7890` all slipped it. Fix (the reviewer's own prescription): normalize FIRST —
# collapse space/NBSP/hyphen/dot/paren separators OUT of every digit run in the diff text, then
# match a bare-digit pattern against the normalized text. Only digit runs (an optional leading
# '+') are touched; all other diff text is left byte-for-byte untouched, so this cannot merge
# unrelated content across a non-digit boundary.
_DIGIT_RUN_RE = re.compile(r"\+?\d(?:[ \t\xa0\-.()]*\d)+")


def _normalize_digit_runs(text: str) -> str:
    """Collapse separators out of every digit-and-separator run so a phone/account number
    formatted with space, NBSP, hyphen, dot, OR parentheses matches the same bare-digit pattern —
    the separator class no longer needs to be grown by hand for the next format."""
    return _DIGIT_RUN_RE.sub(lambda m: re.sub(r"[^\d+]", "", m.group(0)), text)


# Matched against the NORMALIZED text (see above): +62 / 62 / 0 trunk prefix + the mobile block
# '8' + 8-10 more digits (the same 9-13 total digit span the old separator-aware regex covered).
_ID_PHONE_RE = re.compile(r"(?<!\d)(?:\+62|62|0)8\d{8,10}(?!\d)")

# PBF-PROP-021 P2-1 (GPT-5.5 xhigh built-code review): the bare 10-digit bank-account pattern false-tripped
# benign ids — an order id, a datelike number (2026070712), a numeric-leading chunk of a longer
# hex/alnum token (1234567890abcdef). A negative control that fires on every long benign number
# is a dead tripwire. Fixed two ways, WITHOUT weakening the real catch:
#   - the digit run must sit at a hard alnum boundary (excludes a hex/id chunk embedded in a
#     longer token — (?!\d) alone let a trailing letter through);
#   - it must have account/bank CONTEXT nearby (excludes a bare order id or date with no money
#     signal — shape alone is not evidence of a real account number).
_BANK_ACCOUNT_RE = re.compile(r"(?<![A-Za-z0-9_])\d{10}(?![A-Za-z0-9_])")
# No \b word-boundary here (deliberately): a real-world context marker is as likely to be
# embedded in an identifier (BANK_ACCOUNT, norek_pelanggan) as standalone prose — a boundary
# would silently blind the context check to the exact identifier shape money code actually uses.
_ACCOUNT_CONTEXT_RE = re.compile(
    r"(?i:bni|bri|mandiri|rekening|no\.?\s*rek|norek|account|acct|bank)")
_ACCOUNT_CONTEXT_WINDOW = 40


def _bank_account_hit(text: str) -> bool:
    """True only when a bare 10-digit run has account/bank context within
    _ACCOUNT_CONTEXT_WINDOW chars on either side — shape alone (an order id, a bare date) is not
    treated as evidence of a real account number (PBF-PROP-021 P2-1)."""
    for m in _BANK_ACCOUNT_RE.finditer(text):
        lo, hi = max(0, m.start() - _ACCOUNT_CONTEXT_WINDOW), m.end() + _ACCOUNT_CONTEXT_WINDOW
        if _ACCOUNT_CONTEXT_RE.search(text[lo:hi]):
            return True
    return False


SENSITIVE_PATTERNS = [
    ("AWS access key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("hardcoded secret assignment",
     re.compile(r"(?i)(api[_-]?key|secret|password|passwd|token|bearer)\s*[:=]\s*['\"]?[A-Za-z0-9_\-\.]{12,}")),
]


def _sensitive_hits(diff_text: str) -> list:
    """Every SENSITIVE_PATTERNS name that hits the raw diff, plus the two normalize-then-match
    PII detectors (Indonesian phone / bank account) — kept OUT of the generic list because both
    need special handling the others don't (separator-normalized text; the account leg also needs
    account-context, PBF-PROP-021 P1-3/P2-1)."""
    hits = [name for name, rx in SENSITIVE_PATTERNS if rx.search(diff_text)]
    normalized = _normalize_digit_runs(diff_text)
    if _ID_PHONE_RE.search(normalized):
        hits.append("Indonesian phone number (PII)")
    if _bank_account_hit(normalized):
        hits.append("10-digit account number (bank/PII)")
    return hits


SCRUB_REQUIRED_KEYS = ("target", "diff_hash", "scrub_command", "positive_control_exit", "produced_at")
# PBF-PROP-019: the money/PII subset of cx_lock_fidelity.card_high_risk's security_tripwire
# classes (money/auth/secrets/PII/destructive) — egress ties specifically to money/PII per the
# design v2.B ceremony table, not the full high-risk set (auth-only/secrets-only cards do not by
# themselves force egress under LITE/STANDARD; a card can still separately force the Phase-2
# foundation checkpoint via cx_card's card_high_risk).
_MONEY_PII_TRIPWIRE_KEYS = ("touches_money_or_balances", "touches_bank_or_pii")


def _card_touches_money_or_pii(card: dict) -> bool:
    st = card.get("security_tripwire") if isinstance(card, dict) else None
    if not isinstance(st, dict):
        return False
    truthy = lambda v: str(v).strip().lower() in ("yes", "true", "1")
    return any(truthy(st.get(k)) for k in _MONEY_PII_TRIPWIRE_KEYS)


def cmd_egress(args) -> int:
    diff_path = args.diff
    target = str(args.target)
    receipt_ref = getattr(args, "receipt", None)
    loc = diff_path
    findings = []

    # PBF-PROP-019 Phase 3 (design v2.B ceremony row 4): LITE/STANDARD only require the scrub when
    # a card touches money/PII; STRICT requires it for every module. Fail-closed: with no --card /
    # --state supplied (the pre-existing call shape, preserved byte-for-byte), or an unresolvable
    # tier/packet_dir, this resolves to "always required" — the exact behaviour every existing
    # caller/test already gets. Only a caller that explicitly opts in with --card/--state can relax.
    card_path = getattr(args, "card", None)
    state_path = getattr(args, "state", None)
    repo_root_arg = getattr(args, "repo_root", None)

    money_pii_touch = True
    if card_path:
        card_data, cerr = load_yaml(card_path)
        if cerr or not isinstance(card_data, dict):
            findings.append(("P1", loc, f"--card {card_path} unreadable: {cerr or 'not a mapping'}"))
            return findings_report(findings)
        money_pii_touch = _card_touches_money_or_pii(card_data)

    risk_tier_val = "STRICT"
    if state_path:
        state_data, serr = load_yaml(state_path)
        if not serr and isinstance(state_data, dict):
            pkt_rel = str(state_data.get("packet_dir", "") or "").strip()
            if pkt_rel and not (Path(pkt_rel).is_absolute() or ".." in Path(pkt_rel).parts):
                base = Path(repo_root_arg) if repo_root_arg else Path(state_path).resolve().parent
                risk_tier_val = resolve_risk_tier(base / pkt_rel)

    egress_required = risk_tier_val == "STRICT" or money_pii_touch

    try:
        diff_text = Path(diff_path).read_text(errors="replace")
    except OSError as e:
        print(f"FIX-FIRST\n  [P0] {diff_path} — cannot read the diff to be egressed: {e}")
        return 1
    diff_hash = hashlib.sha256(diff_text.encode()).hexdigest()[:12]
    hits = _sensitive_hits(diff_text)

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

    # neither a scrub receipt nor a carve-out → BLOCK before any upload, UNLESS this tier/card
    # combination doesn't require egress at all (PBF-PROP-019) — but a MECHANICAL hit from the
    # sensitive-content tripwire always forces the requirement regardless of tier/card declaration
    # (a detected secret/PII pattern is evidence, not a self-declared risk class; never relaxed).
    if not egress_required and not hits:
        print(f"NOT_APPLICABLE — egress scrub not required for {target} "
              f"(risk_tier={risk_tier_val}, card does not touch money/PII) [PBF-PROP-019]")
        return 0
    detail = f"; sensitive content detected in the diff: {hits}" if hits else ""
    findings.append(("P0", loc,
        f"egress to {target} has NO scrub receipt and NO local-only carve-out — a raw diff must be "
        "scrubbed (an egress_scrub receipt) or explicitly carved out (sensitive_code_carveout) BEFORE it "
        f"is uploaded to an external reviewer{detail} (BF-PROP-005 / GPT #1)"))
    return findings_report(findings)
