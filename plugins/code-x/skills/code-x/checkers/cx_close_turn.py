# cmd_close_turn: the turn-end gate (PROP-018 build-session rail).
#
#   cx check close-turn --state <CODE-X-STATE.yaml> --handoff <path> --repo-root <dir>
#
# The handoff must carry ONE fenced ```yaml block containing a typed `close_turn`
# mapping (typed, never free-text grep — GPT P2-018-03):
#
#   close_turn:
#     findings_delta:            # [] allowed — but the key must be present
#       - id:
#         severity: P0|P1|P2|P3
#         status: OPEN | CLOSED | DISCONFIRMED
#         finding:
#         state_item_ref:        # id of the CODE-X-STATE open_findings item
#     evidence_paths: [...]      # every path must exist under --repo-root
#     next_prompt:               # paste-ready next prompt (inline text or .md path)
#     vault_sync:
#       status: PASS | SKIPPED_WITH_REASON | NOT_APPLICABLE
#       reason:                  # required when status != PASS
#       where_saved:             # required when status != PASS — where the work IS durable
#
# Issue-sync: every OPEN delta row must exist as an OPEN open_findings item in state;
# every CLOSED/DISCONFIRMED row must NOT be open in state. State zero / handoff
# non-zero was the Sample W4 scar. HEAD's commit message must carry Code-X-Provenance:.
import re
import subprocess
from pathlib import Path

import yaml

from cx_common import findings_report, load_yaml

VALID_DELTA_STATUS = {"OPEN", "CLOSED", "DISCONFIRMED"}
VALID_SEVERITIES = {"P0", "P1", "P2", "P3"}
VALID_VAULT_SYNC = {"PASS", "SKIPPED_WITH_REASON", "NOT_APPLICABLE"}

YAML_FENCE = re.compile(r"```ya?ml\s*\n(.*?)```", re.S)


def _close_turn_block(handoff_text: str) -> dict | None:
    """First fenced yaml block whose top-level mapping carries close_turn."""
    for match in YAML_FENCE.finditer(handoff_text):
        try:
            data = yaml.safe_load(match.group(1))
        except yaml.YAMLError:
            continue
        if isinstance(data, dict) and isinstance(data.get("close_turn"), dict):
            return data["close_turn"]
    return None


def verify_lock_pointer(lock_block, state, repo_root, loc):
    """PROP-034 Lever B — RECOMPUTE the frozen_packet_hash + open_cards from real files and verify
    the handoff's COPIES match EXACTLY. The checker NEVER trusts the handoff copy; it recomputes the
    truth and compares. Catches the two forgeries: a self-declared hash (recompute, never trust) and
    a vacuous open_cards: [] (legal ONLY when the recomputed set is genuinely empty).

    lock_block = the close_turn.lock_pointer mapping; state = the live CODE-X-STATE; repo_root resolves
    the frozen packet via state.packet_dir. Returns a list of (severity, loc, msg) findings —
    EMPTY means the handoff points at the lock faithfully. Shared by cx check close-turn (write) and
    cx check state --session-start (read) so both ends recompute identically."""
    from cx_lock_fidelity import recompute_frozen_packet_hash, recompute_open_cards
    findings = []
    if not isinstance(lock_block, dict):
        findings.append(("P1", loc,
            "close_turn.lock_pointer missing or not a mapping — a handoff must POINT AT the lock "
            "(frozen_packet_hash + open_cards + lock_restatement_assertion), copied not paraphrased "
            "(PROP-034 Lever B)"))
        return findings

    packet_dir_rel = str(state.get("packet_dir", "") or "").strip()

    # frozen_packet_hash — recompute from the packet body, never trust the handoff's copy.
    real_hash, herr = recompute_frozen_packet_hash(repo_root, packet_dir_rel)
    declared_hash = str(lock_block.get("frozen_packet_hash", "") or "").strip()
    if herr or real_hash is None:
        findings.append(("P1", loc,
            f"cannot recompute the frozen packet hash to verify the handoff: {herr} (PROP-034 Lever B)"))
    elif not declared_hash:
        findings.append(("P1", loc,
            "close_turn.lock_pointer.frozen_packet_hash missing — copy the real packet hash verbatim "
            "(PROP-034 Lever B / LOCK-FIDELITY-HANDOFF-HASH-MISMATCH)"))
    elif declared_hash != real_hash:
        findings.append(("P1", loc,
            f"close_turn.lock_pointer.frozen_packet_hash '{declared_hash}' != the RECOMPUTED packet "
            f"hash '{real_hash}' — a self-declared hash is never trusted; the next session cannot boot "
            "on a drifted handoff (PROP-034 Lever B / LOCK-FIDELITY-HANDOFF-HASH-MISMATCH)"))

    # open_cards — recompute from frozen registry + state, never trust the handoff's copy.
    real_open, oerr = recompute_open_cards(repo_root, packet_dir_rel, state)
    declared_open = lock_block.get("open_cards")
    if oerr or real_open is None:
        findings.append(("P1", loc,
            f"cannot recompute the open-card set to verify the handoff: {oerr} (PROP-034 Lever B)"))
    elif not isinstance(declared_open, list):
        findings.append(("P1", loc,
            "close_turn.lock_pointer.open_cards missing or not a list — copy the deck+state open-card "
            "set (PROP-034 Lever B / LOCK-FIDELITY-HANDOFF-OPENCARDS-MISMATCH)"))
    else:
        declared_set = sorted(str(c) for c in declared_open)
        if declared_set != real_open:
            findings.append(("P1", loc,
                f"close_turn.lock_pointer.open_cards {declared_set} != the RECOMPUTED open-card set "
                f"{real_open} — the handoff copy is stale/vacuous; open_cards: [] is legal ONLY when "
                "the recomputed set is genuinely empty (PROP-034 Lever B / "
                "LOCK-FIDELITY-HANDOFF-OPENCARDS-MISMATCH)"))

    # lock_restatement_assertion — a one-line machine assertion naming the verified hash.
    assertion = str(lock_block.get("lock_restatement_assertion", "") or "").strip()
    if not assertion:
        findings.append(("P1", loc,
            "close_turn.lock_pointer.lock_restatement_assertion missing — a one-line "
            "'no requirement added/dropped since <hash>' assertion makes the lock, not the paraphrase, "
            "what the next session re-loads (PROP-034 Lever B)"))
    elif real_hash and real_hash not in assertion:
        findings.append(("P1", loc,
            "close_turn.lock_pointer.lock_restatement_assertion does not name the recomputed packet "
            f"hash '{real_hash}' — the assertion must pin the exact frozen hash (PROP-034 Lever B)"))
    return findings


def _check_lock_pointer(block, state, repo_root, loc, findings):
    """Wrapper used at close-turn write time. PROP-034 Lever B applies to a build session that has a
    FROZEN packet (state.packet_dir set) — that is where the lock exists to point at. A turn with no
    packet_dir (planning / pre-freeze / a non-build handoff) has no lock to copy, so the sub-block is
    not required; but if the handoff DOES carry a lock_pointer it is still verified (no free pass)."""
    has_packet = bool(str(state.get("packet_dir", "") or "").strip())
    has_pointer = isinstance(block.get("lock_pointer"), dict)
    if not has_packet and not has_pointer:
        return
    findings.extend(verify_lock_pointer(block.get("lock_pointer"), state, repo_root, loc))


def cmd_close_turn(args) -> int:
    state_path = args.state
    handoff_path = args.handoff
    repo_root = args.repo_root

    state, serr = load_yaml(state_path)
    if serr or not isinstance(state, dict):
        print(f"FIX-FIRST\n  [P0] {state_path} — {serr or 'not a YAML mapping'}")
        return 1
    try:
        handoff_text = Path(handoff_path).read_text(encoding="utf-8")
    except OSError as e:
        print(f"FIX-FIRST\n  [P0] {handoff_path} — handoff unreadable: {e}")
        return 1

    findings = []
    loc = handoff_path

    # GPT cross-review 2026-06-12: state mutated at turn close must not dodge the
    # state-side PROP-020/021 clauses — re-run the targeted ones here.
    from cx_state import _check_fix_cycles, _check_protocol_incident
    _check_fix_cycles(state, state_path, findings)
    _check_protocol_incident(state, state_path, findings)

    block = _close_turn_block(handoff_text)
    if block is None:
        findings.append(("P1", loc,
            "handoff has no typed close_turn yaml block (findings_delta + evidence_paths "
            "+ next_prompt + vault_sync) — free-text handoffs cannot be reconciled"))
        return findings_report(findings)

    # --- findings_delta ↔ state open_findings issue-sync ---
    state_items = ((state.get("open_findings") or {}).get("items")) or []
    open_ids = {str(it.get("id")) for it in state_items
                if isinstance(it, dict) and str(it.get("status", "OPEN")).upper() == "OPEN"}

    delta = block.get("findings_delta")
    if not isinstance(delta, list):
        findings.append(("P1", loc,
            "close_turn.findings_delta missing or not a list ([] is allowed; absence is not) "
            "— the typed delta is the issue-sync contract"))
        delta = []
    for i, row in enumerate(delta):
        if not isinstance(row, dict):
            findings.append(("P1", loc, f"findings_delta[{i}] is not a mapping"))
            continue
        rid = str(row.get("id", ""))
        sev = str(row.get("severity", "")).upper()
        status = str(row.get("status", "")).upper()
        ref = str(row.get("state_item_ref", "") or "")
        if not rid:
            findings.append(("P1", loc, f"findings_delta[{i}].id missing"))
        if not str(row.get("finding", "") or "").strip():
            findings.append(("P1", loc,
                f"findings_delta[{i}].finding missing — every row carries the plain-line "
                "finding text (typed schema, all five fields)"))
        if not ref:
            findings.append(("P1", loc,
                f"findings_delta[{i}].state_item_ref missing — the explicit state item id "
                "is the reconcile key; defaults are not reconciliation"))
            continue
        if sev not in VALID_SEVERITIES:
            findings.append(("P1", loc,
                f"findings_delta[{i}].severity '{row.get('severity')}' not in {sorted(VALID_SEVERITIES)}"))
        if status not in VALID_DELTA_STATUS:
            findings.append(("P1", loc,
                f"findings_delta[{i}].status '{row.get('status')}' not in {sorted(VALID_DELTA_STATUS)}"))
            continue
        if status == "OPEN" and ref not in open_ids:
            findings.append(("P1", loc,
                f"findings_delta row '{rid}' is OPEN in the handoff but '{ref}' is not an "
                "OPEN open_findings item in state — state and handoff must agree "
                "(state-zero/handoff-nonzero is the W4 scar)"))
        if status in ("CLOSED", "DISCONFIRMED") and ref in open_ids:
            findings.append(("P1", loc,
                f"findings_delta row '{rid}' is {status} in the handoff but '{ref}' is "
                "still OPEN in state — close it in state or reopen it in the handoff"))

    # --- evidence paths exist ---
    ev_paths = block.get("evidence_paths")
    if not isinstance(ev_paths, list) or not ev_paths:
        findings.append(("P1", loc,
            "close_turn.evidence_paths missing or empty — every turn ends with evidence paths"))
    else:
        for ev in ev_paths:
            if not (Path(repo_root) / str(ev)).exists():
                findings.append(("P1", loc, f"evidence path missing under {repo_root}: {ev}"))

    # --- next prompt ---
    next_prompt = str(block.get("next_prompt", "") or "").strip()
    if not next_prompt:
        findings.append(("P1", loc,
            "close_turn.next_prompt missing — no actor ends useful work without a "
            "paste-ready next prompt (the single rule)"))
    elif next_prompt.endswith(".md") and "\n" not in next_prompt:
        if not (Path(repo_root) / next_prompt).is_file():
            findings.append(("P1", loc, f"next_prompt points at a missing file: {next_prompt}"))

    # --- provenance trailer on HEAD ---
    result = subprocess.run(["git", "-C", repo_root, "log", "-1", "--format=%B"],
                            capture_output=True, text=True)
    if result.returncode != 0:
        findings.append(("P1", repo_root, f"cannot read HEAD commit: {result.stderr.strip()}"))
    elif "Code-X-Provenance:" not in result.stdout:
        findings.append(("P1", repo_root,
            "HEAD commit message has no Code-X-Provenance: trailer — commit the turn's "
            "work with provenance before closing"))

    # --- PROP-034 Lever B: lock-pointing handoff sub-block ---
    _check_lock_pointer(block, state, repo_root, loc, findings)

    # --- vault_sync enum (the 11.7h-zero-vault-syncs scar) ---
    vs = block.get("vault_sync")
    vs = vs if isinstance(vs, dict) else {"status": vs}
    status = str(vs.get("status", "") or "")
    if status not in VALID_VAULT_SYNC:
        findings.append(("P1", loc,
            f"close_turn.vault_sync.status '{status}' not in {sorted(VALID_VAULT_SYNC)}"))
    elif status != "PASS":
        if not str(vs.get("reason", "") or "").strip() or not str(vs.get("where_saved", "") or "").strip():
            findings.append(("P1", loc,
                f"vault_sync {status} without reason + where_saved — a skip must say why "
                "AND where the work IS durably saved"))

    return findings_report(findings)
