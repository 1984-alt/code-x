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
