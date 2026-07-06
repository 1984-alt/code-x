# cmd_accept: /cx-accept — the STAMPER (B-PROP-013 Unit 2, design-history/b-prop-013-forge-parity-
# design-2026-07-06.md §3). Mirrors cx_boot.py's generate->write->self-hash-seal pattern.
#
# HONEST FRAMING (council-mandated, §3/§10.3 — do NOT overclaim): this command is ERGONOMICS +
# the one honest generation moment for state_sha_before — it is NOT a forge wall. `generated_by`
# is a self-declared string the gate cannot authenticate; nothing forces a forger through this
# command — they can hand-write a receipt that skips it entirely. The WALL is `cx check
# module-acceptance` (Unit 1's recompute legs in cx_module_acceptance.py, forge_parity_findings)
# + the pre-existing state<->receipt-file sha12 seal. This command's honest value is: (a) it
# kills error-prone hand-authoring of the mechanical fields, (b) it is the ONLY honest moment to
# capture state_sha_before (the prior state is gone by the time a human writes a receipt later —
# symmetric with cx_boot's repo_head ceiling), and (c) it enforces the ceo_accept_token<->HEAD
# tie (CX-ACCEPT-NO-CEO-TOKEN) so a self-filling stamper cannot bypass the human MODULE-DEMO-
# MISSING wall that keeps long-autonomous OFF (CHARTER L80-84).
#
#   cx check accept --draft <MODULE-ACCEPTANCE-DRAFT.yaml> --state <CODE-X-STATE.yaml> \
#       --repo-root <dir> [--out <receipt>]
#
# The draft supplies every field a machine cannot invent (module_id, quality_card, self_review,
# build_validation, anti_slop, ceo_turn_ref, ceo_accept_token, the requested verdict, ...). This
# command OVERWRITES the mechanical/computed fields with recomputed ground truth — generated_by,
# state_sha_before, repo_sha_before, the repo_sha inside verify_app/module_demo/live_slice_accept
# (whichever blocks are present in the draft), and quality_card_hash (recomputed from the inline
# quality_card block) — then writes + self-hash-seals the receipt. It never trusts the draft for
# any of these, exactly as cx_boot never trusts the model for canon hashes.
#
# Exit 0 = receipt written; 1 = refused (bad draft, unreadable state/repo, or the CX-ACCEPT-
# NO-CEO-TOKEN refusal below) — a refusal writes NO receipt file.
from datetime import datetime, timezone
from pathlib import Path

import yaml

from cx_common import load_yaml, profiles_sha12
from cx_state import state_sha12_without_boot_ack
from cx_module_acceptance import _canonicalize_quality_card_hash, _git


def _resolve_head(repo_root: str) -> str | None:
    rc, out = _git(repo_root, "rev-parse", "HEAD")
    return out.strip() if rc == 0 and out.strip() else None


# FIX-FIRST (B-PROP-013 xfam P1): the honest-path token check must require MORE than a 6-char
# substring — a 6-char hex prefix collides easily (~16.7M space) and, worse, the OLD check let a
# forger write `ceo_accept_token: auto-<HEAD[:6]>` with no human ceo_turn_ref at all. TOKEN_PREFIX_LEN
# mirrors the file's own _sha12 convention (12 hex chars) used everywhere else a commit is bound.
TOKEN_PREFIX_LEN = 12


def _resolve_ceo_accept_context(ma: dict) -> tuple[str, str, str] | None:
    """FIX-FIRST (B-PROP-013 xfam P1, §3.2): returns (token, ceo_turn_ref, block_label) from the
    ONE block the CEO-accept context must live on, or None if no valid in-scope token is present.

    For a live_slice/module_demo module (SEE-AND-TEST binding, PBF-PROP-012 Part E) the token AND
    its ceo_turn_ref MUST be co-located on that SAME structured block — a bare top-level field
    does not count (closes the top-level-bypass gap: a forger writing ceo_accept_token at the top
    level while live_slice_accept/module_demo exists, but empty, must not slip through). For any
    OTHER module (neither structured block present) the bare top-level fields are accepted — that
    is the only shape such a draft can carry the context on."""
    for block_key in ("live_slice_accept", "module_demo"):
        block = ma.get(block_key)
        if isinstance(block, dict):
            token = block.get("ceo_accept_token", "")
            token = token.strip() if isinstance(token, str) else ""
            if token:
                turn_ref = block.get("ceo_turn_ref", "")
                turn_ref = turn_ref.strip() if isinstance(turn_ref, str) else ""
                return token, turn_ref, block_key
            return None  # structured module present but this block carries no token — a top-level
                         # field must NOT count as a substitute (closes the bypass)
    token = ma.get("ceo_accept_token", "")
    token = token.strip() if isinstance(token, str) else ""
    if not token:
        return None
    turn_ref = ma.get("ceo_turn_ref", "")
    turn_ref = turn_ref.strip() if isinstance(turn_ref, str) else ""
    return token, turn_ref, "top-level"


def cmd_accept(args) -> int:
    draft_path = args.draft
    state_path = args.state
    repo_root = args.repo_root
    out_path = Path(args.out) if getattr(args, "out", None) else (
        Path(draft_path).resolve().parent / "MODULE-ACCEPTANCE.yaml")

    draft, derr = load_yaml(draft_path)
    if derr or not isinstance(draft, dict):
        print(f"FIX-FIRST\n  [P0] {draft_path} — {derr or 'not a mapping'}")
        return 1
    ma_raw = draft.get("module_acceptance")
    ma = ma_raw if isinstance(ma_raw, dict) else draft

    module_id = str(ma.get("module_id", "") or "").strip()
    if not module_id:
        print(f"FIX-FIRST\n  [P0] {draft_path} — module_acceptance.module_id is required; "
              "cx-accept refuses to stamp a module-less receipt")
        return 1

    # 1. state_sha_before — the ONE honest generation moment (captured BEFORE this command
    #    writes anything; the prior state is gone the instant acceptance is recorded).
    state_sha_before = state_sha12_without_boot_ack(state_path)
    if state_sha_before is None:
        print(f"FIX-FIRST\n  [P0] {state_path} — unreadable; cannot capture state_sha_before")
        return 1

    # repo HEAD — recomputed, never trusted from the draft (mirrors cx_boot's repo_head leg).
    head = _resolve_head(repo_root)
    if not head:
        print(f"FIX-FIRST\n  [P0] cannot resolve git HEAD at '{repo_root}' — cx-accept requires "
              "a real repo to bind the stamped receipt to")
        return 1

    verdict = str(ma.get("verdict", "") or "").strip().lower()

    # 2. CX-ACCEPT-NO-CEO-TOKEN (§3.2, P0/refuse): refuse to stamp verdict: accepted without a
    #    valid ceo_accept_token whose embedded repo_sha prefix matches the recomputed HEAD, PLUS a
    #    non-empty ceo_turn_ref on the SAME block, PLUS (for a live_slice/module_demo module) the
    #    token living on that structured block, not a bare top-level field. FIX-FIRST (B-PROP-013
    #    xfam P1): the old check was a forgeable 6-char substring with no ceo_turn_ref requirement
    #    and no block co-location — `ceo_accept_token: auto-<HEAD[:6]>` alone used to stamp clean.
    #    HONEST LIMIT (§10.3, unchanged): this ties the STAMP to a human-typed token + turn ref; it
    #    does not authenticate that a human typed it, and a hand-authored receipt can skip this
    #    command entirely — the real wall is Unit 1 + the state-seal, not this refusal.
    if verdict == "accepted":
        head_prefix = head[:TOKEN_PREFIX_LEN].lower()
        ctx = _resolve_ceo_accept_context(ma)
        if ctx is None:
            print("FIX-FIRST\n  [P0] refusing to stamp verdict: accepted — no ceo_accept_token "
                  "found on an in-scope block (live_slice_accept / module_demo when either is "
                  "present, else top-level) (CX-ACCEPT-NO-CEO-TOKEN, B-PROP-013 §3.2): a "
                  "self-filling stamper must not be able to bypass the human accept that keeps "
                  "long-autonomous OFF (CHARTER L80-84)")
            return 1
        token, turn_ref, block_label = ctx
        if head_prefix not in token.lower():
            print("FIX-FIRST\n  [P0] refusing to stamp verdict: accepted — ceo_accept_token on "
                  f"'{block_label}' does not embed the recomputed HEAD prefix '{head_prefix}' "
                  f"({TOKEN_PREFIX_LEN} hex chars required, not a short/forgeable substring) "
                  "(CX-ACCEPT-NO-CEO-TOKEN, B-PROP-013 §3.2): a self-filling stamper must not be "
                  "able to bypass the human accept that keeps long-autonomous OFF (CHARTER L80-84)")
            return 1
        if not turn_ref:
            print("FIX-FIRST\n  [P0] refusing to stamp verdict: accepted — ceo_accept_token on "
                  f"'{block_label}' has no ceo_turn_ref on that SAME block (a token with no turn "
                  "reference is not tied to a real CEO turn) (CX-ACCEPT-NO-CEO-TOKEN, B-PROP-013 "
                  "§3.2): a self-filling stamper must not be able to bypass the human accept that "
                  "keeps long-autonomous OFF (CHARTER L80-84)")
            return 1

    # 3. Overwrite mechanical/computed fields with recomputed ground truth — never trust the
    #    draft for these (mirrors cx_boot's canon-hash-not-model-authored pattern).
    ma["generated_by"] = "cx check accept"
    ma["state_sha_before"] = state_sha_before
    ma["repo_sha_before"] = head
    for block_key in ("verify_app", "module_demo", "live_slice_accept"):
        block = ma.get(block_key)
        if isinstance(block, dict):
            block["repo_sha"] = head

    qc = ma.get("quality_card")
    if isinstance(qc, dict) and qc:
        ma["quality_card_hash"] = _canonicalize_quality_card_hash(qc)

    ma["ts"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    receipt = {"module_acceptance": ma}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(receipt, f, sort_keys=False)
    receipt_hash = profiles_sha12(str(out_path))

    print("PASS")
    print(f"  [INFO] module_id: {module_id}  verdict: {verdict or 'UNSET'}")
    print(f"  [INFO] state_sha_before: {state_sha_before}  repo_sha_before (HEAD): {head}")
    print(f"  [INFO] acceptance receipt written: {out_path}")
    print(f"  [INFO] receipt sha12: {receipt_hash}")
    print("  [INFO] copy into CODE-X-STATE.yaml (values verbatim — cx generated them):")
    print("    accepted_modules:")
    print(f"      - module_id: {module_id}")
    print(f"        acceptance_ref: {out_path}")
    print(f"        acceptance_sha12: {receipt_hash}")
    print("  [INFO] HONEST FRAMING: this command is ergonomics + honest capture, NOT a forge "
          "wall — the wall is `cx check module-acceptance` (Unit 1 recompute + state-seal). A "
          "hand-authored receipt can still skip this command entirely; only the wall enforces.")
    return 0
