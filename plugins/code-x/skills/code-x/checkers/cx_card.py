# cmd_card: validates a Code-X V1 work-order card YAML file.
import re
from pathlib import Path

from cx_common import (
    findings_report, load_yaml, rough_token_count,
    field_present, nested_get,
    READ_BUDGET_TOKENS, CARD_TOKEN_BUDGET, VALID_MODEL_TIERS, VALID_MODES,
    MECHANICAL_CLASS_MARKERS, TOP_EFFORTS,
    resolve_profiles_path, profiles_sha12,
)


def _role_seats(profiles: dict, role: str, engine_key: str, tier: str | None) -> list[dict]:
    """Allowed seats for a role + engine branch from BUILD-ENGINE-PROFILES.
    Tiered roles (e.g. implementer.standard/high_risk): use the named tier when it
    exists, else the union of all tiers. Conditional escalation sub-seats are NOT
    granted up-front (a card pinning the escalation seat must not match)."""
    role_def = nested_get(profiles, "roles", role)
    if not isinstance(role_def, dict):
        return []
    if engine_key in role_def:
        seat = role_def[engine_key]
        return [seat] if isinstance(seat, dict) else []
    if tier and isinstance(role_def.get(tier), dict) and engine_key in role_def[tier]:
        seat = role_def[tier][engine_key]
        return [seat] if isinstance(seat, dict) else []
    seats = []
    for tier_def in role_def.values():
        if isinstance(tier_def, dict) and isinstance(tier_def.get(engine_key), dict):
            seats.append(tier_def[engine_key])
    return seats


def _check_execution(data: dict, args, loc: str, findings: list) -> None:
    """PROP-013 BUILD-ENGINE-PROFILES enforcement — card-side clauses 1-5."""
    exec_block = data.get("execution")
    if not exec_block or not isinstance(exec_block, dict):
        findings.append(("P0", loc,
            "execution block missing — must be injected by the Card Compiler from BUILD-ENGINE-PROFILES.yaml"))
        return

    profiles_path, env_err = resolve_profiles_path(args)
    if env_err:
        findings.append(("P1", loc, env_err))
        return
    profiles, perr = load_yaml(profiles_path)
    if perr or not isinstance(profiles, dict):
        findings.append(("P1", loc,
            f"cannot verify execution block — BUILD-ENGINE-PROFILES unreadable at {profiles_path} (fail closed)"))
        return

    # clause 2: profiles_hash must be present and match the current profiles file
    expected_hash = profiles_sha12(profiles_path)
    got_hash = exec_block.get("profiles_hash")
    if not got_hash:
        findings.append(("P1", loc,
            "execution.profiles_hash missing — re-inject the card from BUILD-ENGINE-PROFILES.yaml"))
    elif str(got_hash) != expected_hash:
        findings.append(("P1", loc,
            f"execution.profiles_hash '{got_hash}' != current BUILD-ENGINE-PROFILES hash '{expected_hash}' "
            "— profiles changed; re-inject remaining cards"))

    # clause 3: each engine branch's model/effort must exist in the profiles for that role
    role = exec_block.get("role", "")
    tier = exec_block.get("model_tier") or data.get("model_tier")
    roles = profiles.get("roles") or {}
    if not role or role not in roles:
        findings.append(("P1", loc,
            f"execution.role '{role}' not found in BUILD-ENGINE-PROFILES roles — cannot validate seats"))
    else:
        for engine_key in ("claude_code", "codex_app"):
            card_seat = exec_block.get(engine_key)
            if not isinstance(card_seat, dict) or not card_seat.get("model"):
                findings.append(("P1", loc,
                    f"execution.{engine_key} branch missing or has no model — dual-branch injection required"))
                continue
            seats = _role_seats(profiles, role, engine_key, str(tier) if tier else None)
            card_model = str(card_seat.get("model", ""))
            card_effort = card_seat.get("effort")
            matched = any(
                str(s.get("model", "")) == card_model and
                (s.get("effort") is None or card_effort is None or str(s["effort"]) == str(card_effort))
                for s in seats
            )
            if not matched:
                findings.append(("P1", loc,
                    f"execution.{engine_key} seat '{card_model}"
                    f"{' ' + str(card_effort) if card_effort else ''}' not found in "
                    f"BUILD-ENGINE-PROFILES roles.{role} — no actor invents its own seat"))

    # clause 4: code_writing_floor — mechanical-class model never sits in an implementer seat
    if role == "implementer":
        for engine_key in ("claude_code", "codex_app"):
            card_seat = exec_block.get(engine_key)
            if isinstance(card_seat, dict):
                model_low = str(card_seat.get("model", "")).lower()
                if any(marker in model_low for marker in MECHANICAL_CLASS_MARKERS):
                    findings.append(("P0", loc,
                        f"execution.{engine_key} puts mechanical-class model '{card_seat.get('model')}' "
                        "in an implementer (app-code) seat — code_writing_floor violation"))

    # clause 5: card limits may never exceed the profiles' hard caps
    file_limits = profiles.get("limits") or {}
    card_limits = exec_block.get("limits") or {}
    if isinstance(card_limits, dict):
        for limit_key in ("max_parallel_subagents", "max_depth"):
            try:
                card_val = int(card_limits.get(limit_key))
            except (TypeError, ValueError):
                continue
            try:
                cap = int(file_limits.get(limit_key))
            except (TypeError, ValueError):
                continue
            if card_val > cap:
                findings.append(("P1", loc,
                    f"execution.limits.{limit_key}={card_val} exceeds BUILD-ENGINE-PROFILES cap {cap}"))


# --- PROP-019: UI-contract carry-forward (the Sample W4 scar) ---------------
# A card that touches templates/static/HTML-rendering files, or purges Mode A
# fixtures, must carry the locked visual artifacts — never infer the visual contract.
UI_PATH_RE = re.compile(r"(^|/)(templates|static)(/|$)|\.html?$", re.I)
UI_CONTRACT_ARTIFACT_KEYS = ("taste_lock", "design_golden_master", "mode_a_ceo_accept",
                             "screenshots", "route_map", "click_path_contract")
REPLACEMENT_MAP_KEYS = ("purged_fixture", "live_route", "live_template", "locked_reference",
                        "data_fn_preserved", "controls_preserved",
                        "screenshot_comparison", "dom_marker_comparison")
VISUAL_CONTEXT_KEYS = ("current_screenshots", "mode_a_screenshots", "locked_board_path",
                       "route_map", "click_path_contract", "marker_manifest",
                       "required_question")


def _touches_ui(data: dict) -> bool:
    return any(UI_PATH_RE.search(str(p)) for p in (data.get("allowed_files") or []))


def _purges_fixtures(data: dict) -> bool:
    return str(data.get("design_fixture_purge", "no")).lower() in ("yes", "true")


def _check_ui_contract(data: dict, loc: str, findings: list) -> None:
    """[G3/G6, PROP-019] ui_contract required on UI-touching/fixture-purging cards;
    purge additionally requires a complete fixture_replacement_map (no map, no G3 pass).
    DESIGN_FIXTURE_PURGE != DESIGN_DELETE: replace fixture data, preserve the
    CEO-accepted shell and controls."""
    ui = _touches_ui(data)
    purge = _purges_fixtures(data)
    if not ui and not purge:
        return

    uc = data.get("ui_contract")
    if not isinstance(uc, dict):
        findings.append(("P1", loc,
            "card touches UI files (templates/static/HTML) or purges Mode A fixtures "
            "WITHOUT ui_contract — STOP, the card is wrong; never infer the visual "
            "contract (PROP-019, the Sample W4 scar)"))
    else:
        read_required = [str(x) for x in (nested_get(data, "read", "required") or [])]
        for key in UI_CONTRACT_ARTIFACT_KEYS:
            if not field_present(uc, key):
                findings.append(("P1", loc,
                    f"ui_contract.{key} missing — the locked visual artifacts ride the card"))
            elif key in ("taste_lock", "design_golden_master") and str(uc[key]) not in read_required:
                findings.append(("P1", loc,
                    f"ui_contract.{key} '{uc[key]}' is not in read.required — the locked "
                    "artifact must be in the card's read set, not just named"))
        rule = str(uc.get("preservation_rule", "") or "")
        if "preserve" not in rule.lower():
            findings.append(("P1", loc,
                "ui_contract.preservation_rule missing — must state: replace fixture data, "
                "preserve approved shell and controls"))

    if purge:
        fmap = data.get("fixture_replacement_map")
        if not isinstance(fmap, list) or not fmap:
            findings.append(("P1", loc,
                "design_fixture_purge: yes without fixture_replacement_map rows — no "
                "replacement map, no G3 pass (purge means replace data, never delete the screen)"))
        else:
            for i, row in enumerate(fmap):
                if not isinstance(row, dict):
                    findings.append(("P1", loc, f"fixture_replacement_map[{i}] is not a mapping"))
                    continue
                for key in REPLACEMENT_MAP_KEYS:
                    if not field_present(row, key):
                        findings.append(("P1", loc,
                            f"fixture_replacement_map[{i}].{key} missing — every purged "
                            "screen carries the full 8-field row"))

    # UI review dispatches add the additive visual_contract_context block
    # (PROP-015 stanza itself stays verbatim).
    rd = data.get("review_dispatch")
    if isinstance(rd, dict) and str(rd.get("required", "no")).lower() in ("yes", "true"):
        vcc = data.get("visual_contract_context")
        if not isinstance(vcc, dict):
            findings.append(("P1", loc,
                "UI review dispatch without visual_contract_context — the reviewer must "
                "answer: does this preserve the CEO-accepted visual contract? (PROP-019)"))
        else:
            for key in VISUAL_CONTEXT_KEYS:
                if not field_present(vcc, key):
                    findings.append(("P1", loc, f"visual_contract_context.{key} missing"))


def _check_incident_gate(data: dict, args, loc: str, findings: list) -> None:
    """[PROP-020] While a PROTOCOL_INCIDENT is open, new build cards are BLOCKED and
    cross-family/final-ready requests are forbidden; only repair of the incident's
    own card proceeds. Scope: protocol corrections only."""
    state_path = getattr(args, "state", None)
    if not state_path:
        return
    state_data, _ = load_yaml(state_path)
    from cx_state import incident_open
    inc = incident_open(state_data) if isinstance(state_data, dict) else None
    if inc is None:
        return
    repair_card = str(inc.get("repair_card", "") or "")
    card_id = str(data.get("id", ""))
    mode = str(data.get("mode", ""))
    if mode in ("MODULE_BUILD", "MODE_A_UI", "FIX") and card_id != repair_card:
        findings.append(("P1", loc,
            f"PROTOCOL_INCIDENT open in state — new build cards are BLOCKED until the "
            f"current-stage checklist re-runs and the incident records cause + repair "
            f"(only repair_card '{repair_card or 'UNSET'}' may proceed)"))
    rd_kind = str(nested_get(data, "review_dispatch", "review_kind") or "")
    if mode == "FINAL_READY" or rd_kind in ("CROSS_FAMILY", "FINAL_READY"):
        findings.append(("P1", loc,
            "PROTOCOL_INCIDENT open in state — requesting cross-family review or "
            "final-ready is forbidden while the incident is open (PROP-020)"))


# PROP-015 (review-three-leg-ask): values that prove nothing — green-but-not-enforcing.
TLA_PLACEHOLDERS = {"asked", "yes", "included", "n/a", "na", "blank", "done", "ok", "true"}
REVIEW_MODES = {"REVIEW", "FINAL_READY"}
VALID_REVIEW_KINDS = {"SELF_REVIEW", "CROSS_FAMILY", "CARD_AUDIT", "FINAL_READY", "PROTOCOL_CHANGE"}
# leg field -> canonical label that must appear in the quoted ask (relaxed: prompt_ref substitutes)
TLA_LEGS = {"continuity": "CONTINUITY", "problems": "PROBLEMS", "approach_improvement": "APPROACH"}


def _check_review_dispatch(data: dict, loc: str, findings: list) -> None:
    """[RULE:review-three-leg-ask] PROP-015: a review-dispatch card must prove all three
    legs (CONTINUITY + PROBLEMS + APPROACH/IMPROVEMENT) were actually asked. Ordinary
    build cards (review_dispatch.required: no, or no block) are exempt — but a card in
    mode REVIEW/FINAL_READY may not dodge by omitting the block."""
    rd = data.get("review_dispatch")
    required = ""
    if isinstance(rd, dict):
        required = str(rd.get("required", "no") or "no").strip().lower()
    required_yes = required in ("yes", "true")

    mode = str(data.get("mode", "") or "").strip()
    if mode in REVIEW_MODES and not required_yes:
        findings.append(("P1", loc,
            f"mode {mode} card without review_dispatch.required: yes — every review/audit "
            "card must carry the three-leg ask; omitting the block is not an exemption "
            "(PROP-015) [RULE:review-three-leg-ask]"))
        return
    if not required_yes:
        return  # ordinary card — exempt

    kind = str(rd.get("review_kind", "") or "").strip()
    if kind not in VALID_REVIEW_KINDS:
        findings.append(("P1", loc,
            f"review_dispatch.review_kind '{kind}' not in {sorted(VALID_REVIEW_KINDS)}"))

    tla = rd.get("three_leg_ask")
    if not isinstance(tla, dict):
        findings.append(("P1", loc,
            "review_dispatch.required: yes but three_leg_ask missing — all three legs "
            "(continuity/problems/approach_improvement) must quote how they were asked (PROP-015)"))
        return

    prompt_ref = str(rd.get("prompt_ref", "") or "").strip()
    for field, label in TLA_LEGS.items():
        raw = tla.get(field)
        val = str(raw).strip() if raw is not None else ""
        if not val or val.lower() in TLA_PLACEHOLDERS:
            findings.append(("P1", loc,
                f"three_leg_ask.{field} missing or placeholder ('{val}') — must quote how the "
                f"{label} leg was asked; placeholders (asked/yes/included/N/A/blank) are rejected"))
        elif label.lower() not in val.lower() and not prompt_ref:
            findings.append(("P1", loc,
                f"three_leg_ask.{field} lacks the canonical label '{label}' and the card has no "
                "prompt_ref — quote the stanza leg verbatim or point prompt_ref at the dispatch prompt"))


def _check_lock_fidelity(data: dict, args, loc: str, findings: list) -> None:
    """[PROP-034 Lever A] A FIX/correction card must RE-ANCHOR to the frozen lock before it fixes.

    Required on mode: FIX cards (the cards whose purpose is to repair, not build new locked scope):
      - lock_anchor_ref {card_id, requirement_id} — the requirement_id MUST resolve to a real
        requirement line INSIDE the frozen packet named by CODE-X-STATE.packet_dir (reuses the same
        packet source the deck + acceptance checks read; no new CLI surface). Unresolved = fail closed
        (LOCK-FIDELITY-FIX-ANCHOR-MISSING).
      - deviation_class one of RESTORE | AMBIGUITY_RESOLVED | SCOPE_CHANGE
        (LOCK-FIDELITY-DEVIATION-CLASS-MISSING).
      - SCOPE_CHANGE additionally needs BOTH ceo_decision_ref AND packet_amendment_ref or it fails
        closed (LOCK-FIDELITY-SCOPE-CHANGE-UNAUTHORIZED): P1 default, P0 when the card touches a
        high-risk class (money/auth/shared-data-shape/secrets/destructive).

    HONEST JUDGMENT LIMIT (documented, not a closed hole): this proves fields-present + anchor-
    resolves + scope-authorized. It does NOT prove a card labeled RESTORE truly only restores an
    explicit locked line — a mislabeled RESTORE with a clean in-bounds diff WILL pass this shell. That
    residual is mitigated (not eliminated) by the rule-registry 'lock-fidelity-fail-closed' default +
    the opposite-family reviewer auditing deviation_class on every fix card. GREEN here never means
    'this RESTORE is honest'."""
    from cx_lock_fidelity import (
        VALID_DEVIATION_CLASSES, recompute_frozen_packet_hash, frozen_requirement_ids,
        path_is_unsafe, card_high_risk, _frozen_registry, resolve_in_repo,
    )
    if str(data.get("mode", "")) != "FIX":
        return

    anchor = data.get("lock_anchor_ref")
    dev_class = str(data.get("deviation_class", "") or "").strip()

    # deviation_class first (independent of the packet)
    if not dev_class:
        findings.append(("P1", loc,
            "mode: FIX card without deviation_class — a fix must declare RESTORE | "
            "AMBIGUITY_RESOLVED | SCOPE_CHANGE so a departure from the lock is never silent "
            "(PROP-034 Lever A / LOCK-FIDELITY-DEVIATION-CLASS-MISSING) "
            "[RULE:lock-fidelity-fail-closed]"))
    elif dev_class not in VALID_DEVIATION_CLASSES:
        findings.append(("P1", loc,
            f"deviation_class '{dev_class}' not in {sorted(VALID_DEVIATION_CLASSES)} — "
            "RESTORE | AMBIGUITY_RESOLVED | SCOPE_CHANGE (PROP-034 Lever A)"))

    # SCOPE_CHANGE authorization (independent of the packet — both refs must be present)
    if dev_class == "SCOPE_CHANGE":
        ceo_ref = str(data.get("ceo_decision_ref", "") or "").strip()
        amend_ref = str(data.get("packet_amendment_ref", "") or "").strip()
        if not ceo_ref or not amend_ref:
            sev = "P0" if card_high_risk(data) else "P1"
            findings.append((sev, loc,
                "deviation_class: SCOPE_CHANGE without BOTH ceo_decision_ref AND "
                "packet_amendment_ref — anything not already in the lock CANNOT be built as a fix; "
                "it needs a CEO decision + a packet amendment/re-freeze (or a new PROP) (PROP-034 "
                "Lever A / LOCK-FIDELITY-SCOPE-CHANGE-UNAUTHORIZED)"))

    # lock_anchor_ref presence + shape — BOTH halves required (F2). A fix that omits/forges card_id
    # lets the drift over-reach check (cx_drift._scope_overreach) skip silently when the anchor card
    # can't be found, so an unbound requirement_id alone is not enough.
    anchor_card_id = str(anchor.get("card_id", "") or "").strip() if isinstance(anchor, dict) else ""
    anchor_req_id = str(anchor.get("requirement_id", "") or "").strip() if isinstance(anchor, dict) else ""
    if not isinstance(anchor, dict) or not anchor_card_id or not anchor_req_id:
        findings.append(("P1", loc,
            "mode: FIX card without a resolving lock_anchor_ref {card_id, requirement_id} — a fix "
            "that cannot name BOTH the frozen card AND the requirement it restores is freelancing "
            "(PROP-034 Lever A / LOCK-FIDELITY-FIX-ANCHOR-MISSING)"))
        return
    req_id = anchor_req_id

    # Anchor MUST resolve inside the frozen packet named by state.packet_dir.
    state_path = getattr(args, "state", None)
    if not state_path:
        findings.append(("P1", loc,
            "mode: FIX card carries lock_anchor_ref but --state was not supplied — cannot resolve "
            "the anchor against the frozen packet (state.packet_dir); fail closed (PROP-034 Lever A)"))
        return
    state_data, _serr = load_yaml(state_path)
    if not isinstance(state_data, dict):
        findings.append(("P1", loc,
            f"mode: FIX card: state file '{state_path}' unreadable — cannot resolve the lock anchor "
            "(PROP-034 Lever A)"))
        return
    packet_dir_rel = str(state_data.get("packet_dir", "") or "").strip()
    repo_root = str(Path(state_path).resolve().parent)
    if path_is_unsafe(packet_dir_rel):
        findings.append(("P1", loc,
            f"state.packet_dir '{packet_dir_rel}' is unsafe (absolute / '..') — the frozen packet "
            "must be an in-tree path; fail closed (PROP-034 Lever A)"))
        return

    # F2: the packet the card anchors to is BOUND to the card by hash. RECOMPUTE the state.packet_dir
    # packet hash and require it == the card's source_map.locked_packet_hash, so a fix cannot anchor
    # to an attacker-chosen in-repo packet (a different frozen dir) while pointing state elsewhere.
    declared_pkt_hash = str(nested_get(data, "source_map", "locked_packet_hash") or "").strip()
    if not declared_pkt_hash:
        findings.append(("P1", loc,
            "mode: FIX card without source_map.locked_packet_hash — a fix must bind to the packet it "
            "restores by hash so its anchor cannot point at an attacker-chosen packet (PROP-034 Lever A / F2)"))
        return
    real_pkt_hash, herr = recompute_frozen_packet_hash(repo_root, packet_dir_rel)
    if herr or real_pkt_hash is None:
        findings.append(("P1", loc,
            f"mode: FIX card: cannot recompute the frozen packet hash to bind the anchor — {herr} "
            "(PROP-034 Lever A / F2)"))
        return
    if declared_pkt_hash != real_pkt_hash:
        findings.append(("P1", loc,
            f"source_map.locked_packet_hash '{declared_pkt_hash}' != the RECOMPUTED hash of "
            f"state.packet_dir '{packet_dir_rel}' ('{real_pkt_hash}') — the fix anchors to a DIFFERENT "
            "packet than the live frozen one; a self-declared anchor packet is never trusted "
            "(PROP-034 Lever A / F2)"))
        return

    req_ids, rerr = frozen_requirement_ids(repo_root, packet_dir_rel)
    if rerr or req_ids is None:
        findings.append(("P1", loc,
            f"mode: FIX card: cannot read the frozen packet to resolve lock_anchor_ref — {rerr} "
            "(PROP-034 Lever A)"))
        return
    if req_id not in req_ids:
        findings.append(("P1", loc,
            f"lock_anchor_ref.requirement_id '{req_id}' does not resolve to a requirement inside the "
            f"frozen packet '{packet_dir_rel}' (requirements-manifest) — a fix must anchor to a real "
            "locked line (PROP-034 Lever A)"))

    # F2: card_id MUST resolve to a card in the frozen MODULE-REGISTRY (the same source the order wall
    # + open-card derivation trust). An anchor naming a card not in the frozen deck cannot be the card
    # a fix restores — fail closed rather than letting the over-reach check skip an unfound anchor.
    resolved_pkt, _perr = resolve_in_repo(repo_root, packet_dir_rel)
    if resolved_pkt is not None:
        by_module, regerr = _frozen_registry(resolved_pkt)
        if regerr:
            findings.append(("P1", loc,
                f"mode: FIX card: cannot read the frozen MODULE-REGISTRY to resolve "
                f"lock_anchor_ref.card_id — {regerr} (PROP-034 Lever A / F2)"))
        else:
            known_cards = {c for cards in by_module.values() for c in cards}
            if anchor_card_id not in known_cards:
                findings.append(("P1", loc,
                    f"lock_anchor_ref.card_id '{anchor_card_id}' does not resolve to a card in the "
                    f"frozen MODULE-REGISTRY of '{packet_dir_rel}' (known: {sorted(known_cards)}) — a "
                    "fix must anchor to a real frozen card (PROP-034 Lever A / F2)"))

    # F3: a SCOPE_CHANGE's authorizing refs must RESOLVE, not merely be present. The ceo_decision_ref
    # must resolve to a real row in the packet's CEO-DECISION-LEDGER.md (reusing the SAME resolver the
    # deck/packet checks use), and the packet_amendment_ref must be a typed safe in-repo ref (v1.10
    # path-safety: no absolute path / '..' / symlink / outside-repo). A dangling decision id or a
    # path-unsafe amendment is unauthorized scope (P1 default, P0 on a high-risk class).
    if dev_class == "SCOPE_CHANGE":
        ceo_ref = str(data.get("ceo_decision_ref", "") or "").strip()
        amend_ref = str(data.get("packet_amendment_ref", "") or "").strip()
        sev = "P0" if card_high_risk(data) else "P1"
        if ceo_ref:
            from cx_deck import LEDGER_FILE, LEDGER_ROW_ID_RE
            if resolved_pkt is None:
                findings.append((sev, loc,
                    "deviation_class: SCOPE_CHANGE ceo_decision_ref cannot be resolved — the frozen "
                    "packet is unreadable, so the authorizing decision cannot be verified (PROP-034 "
                    "Lever A / F3)"))
            else:
                ledger_path = resolved_pkt / LEDGER_FILE
                if not ledger_path.is_file():
                    findings.append((sev, loc,
                        f"deviation_class: SCOPE_CHANGE names ceo_decision_ref '{ceo_ref}' but the "
                        f"packet has no {LEDGER_FILE} — the authorizing decision cannot resolve "
                        "(PROP-034 Lever A / F3)"))
                else:
                    ledger_ids = set(LEDGER_ROW_ID_RE.findall(
                        ledger_path.read_text(encoding="utf-8", errors="replace")))
                    if ceo_ref not in ledger_ids:
                        findings.append((sev, loc,
                            f"deviation_class: SCOPE_CHANGE ceo_decision_ref '{ceo_ref}' does not "
                            f"resolve to a row in the packet {LEDGER_FILE} — a self-declared decision "
                            "id is not authorization (PROP-034 Lever A / F3)"))
        if amend_ref:
            _resolved_amend, amend_err = resolve_in_repo(repo_root, amend_ref)
            if amend_err is not None:
                findings.append((sev, loc,
                    f"deviation_class: SCOPE_CHANGE packet_amendment_ref {amend_err} — the amendment "
                    "must be a real in-tree file (PROP-034 Lever A / F3)"))
            elif _resolved_amend is None or not _resolved_amend.is_file():
                findings.append((sev, loc,
                    f"deviation_class: SCOPE_CHANGE packet_amendment_ref '{amend_ref}' does not point "
                    "at a real in-repo file — a missing amendment is not authorization (PROP-034 "
                    "Lever A / F3)"))


def cmd_card(args) -> int:
    path = args.file
    data, err = load_yaml(path)
    if err:
        print(f"FIX-FIRST\n  [P0] {path} — {err}")
        return 1

    if not isinstance(data, dict):
        print(f"FIX-FIRST\n  [P0] {path} — not a YAML mapping")
        return 1

    findings = []
    loc = path

    # --- Required top-level scalar fields ---
    required_scalars = ["id", "mode", "actor", "model_tier", "objective"]
    for f in required_scalars:
        if not field_present(data, f):
            findings.append(("P0", loc, f"missing required field: {f}"))

    # mode must be valid
    mode = data.get("mode", "")
    if mode and mode not in VALID_MODES:
        findings.append(("P1", loc, f"mode '{mode}' not in {sorted(VALID_MODES)}"))

    # --- (V1.10) module-advancing build cards must name their frozen-registry module_id ---
    # so the order wall (cx check module-start, run by build-turn) can gate module order. Without
    # it the whole module_acceptance gate family is opt-in on the normal rail (GPT P0-2).
    if mode in ("MODULE_BUILD", "MODE_A_UI") and not field_present(data, "module_id"):
        findings.append(("P0", loc,
            "missing module_id — a MODULE_BUILD / MODE_A_UI card must name the frozen module_registry "
            "module it builds so the order wall (cx check module-start) can gate it [V1.10]"))

    # model_tier must be named
    tier = data.get("model_tier", "")
    if tier and tier not in VALID_MODEL_TIERS:
        findings.append(("P1", loc, f"model_tier '{tier}' not in {sorted(VALID_MODEL_TIERS)} — must be explicitly named"))

    # --- top tier / top effort needs a named top_allowed_reason (ROUTING rule, now mechanical) ---
    exec_for_tier = data.get("execution") if isinstance(data.get("execution"), dict) else {}
    card_efforts = {
        str(nested_get(exec_for_tier, branch, "effort") or "").lower()
        for branch in ("claude_code", "codex_app")
    }
    if (tier == "top" or card_efforts & TOP_EFFORTS) and not field_present(data, "top_allowed_reason"):
        findings.append(("P1", loc,
            "model_tier 'top' (or execution effort high/xhigh/max) without top_allowed_reason — "
            "name the ROUTING top-tier reason (e.g. card_compilation, security_privacy, money_rules)"))

    # objective must be one sentence (no newlines)
    objective = data.get("objective", "")
    if objective:
        if "\n" in str(objective):
            findings.append(("P1", loc, "objective must be one sentence — no newlines"))
        # Multi-sentence: ends with a period followed by a space + capital letter
        if re.search(r'\.\s+[A-Z]', str(objective)):
            findings.append(("P2", loc, "objective appears to be multiple sentences — keep to one"))

    # --- source_map: present and complete (P1-06) ---
    sm = data.get("source_map")
    if not sm or not isinstance(sm, dict):
        findings.append(("P0", loc, "missing source_map — card must be traceable to a frozen packet"))
    else:
        if not field_present(sm, "locked_packet_hash"):
            findings.append(("P0", loc, "source_map.locked_packet_hash missing or blank"))
        if not field_present(sm, "locked_packet_id"):
            findings.append(("P1", loc, "source_map.locked_packet_id missing or blank"))
        # A2: source_sections must be a NON-EMPTY LIST (string/mapping values rejected).
        sections = sm.get("source_sections")
        if not isinstance(sections, list) or not sections:
            findings.append(("P1", loc,
                "source_map.source_sections must be a non-empty list of packet-slice mappings"))
        if isinstance(sections, list):
            for i, sec in enumerate(sections):
                if not isinstance(sec, dict):
                    findings.append(("P1", loc, f"source_map.source_sections[{i}] is not a mapping"))
                    continue
                for sf in ("file", "section", "requirement_ids"):
                    val = sec.get(sf)
                    if val is None or val == "" or val == []:
                        findings.append(("P1", loc,
                            f"source_map.source_sections[{i}].{sf} missing or empty — traceability requires all three fields"))

    # --- card_compilation: compiled_by, audited_by, audit_status == PASS (P1-06) ---
    cc_block = data.get("card_compilation")
    if not cc_block or not isinstance(cc_block, dict):
        findings.append(("P1", loc, "card_compilation missing — compiled_by/audited_by/audit_status required"))
    else:
        if not field_present(cc_block, "compiled_by"):
            findings.append(("P1", loc, "card_compilation.compiled_by missing"))
        if not field_present(cc_block, "audited_by"):
            findings.append(("P1", loc, "card_compilation.audited_by missing"))
        audit_status = cc_block.get("audit_status", "")
        if str(audit_status).upper() != "PASS":
            findings.append(("P0", loc,
                f"card_compilation.audit_status='{audit_status}' — must be PASS; PENDING/FIX_FIRST cards are REJECTED"))

    # --- foundation_checkpoint_required (P1-01) ---
    fcp_required = str(data.get("foundation_checkpoint_required", "no")).lower()
    if fcp_required in ("yes", "true"):
        fcp_reason = data.get("foundation_checkpoint_reason", "")
        if not fcp_reason or str(fcp_reason).strip() == "":
            findings.append(("P1", loc,
                "foundation_checkpoint_required: yes but foundation_checkpoint_reason is empty — must explain why"))
        # Check state if provided: dependent cards blocked until checkpoint passes
        state_data = None
        state_path_arg = getattr(args, 'state', None)
        if state_path_arg:
            state_data, _ = load_yaml(state_path_arg)
        card_id = data.get("id", "")
        if state_data and card_id:
            # Look for checkpoint passage evidence in state — if not present, emit blocking finding
            checkpoints = state_data.get("foundation_checkpoints_passed") or []
            if card_id not in checkpoints:
                findings.append(("P1", loc,
                    f"foundation_checkpoint for card '{card_id}' not recorded as PASSED in state — "
                    "dependent cards are BLOCKED until this checkpoint is recorded"))

    # --- dependency_capsules: block dependent card if foundation checkpoint unmet (P1-01) ---
    # A1: FAIL CLOSED if any capsule requires checkpoint verification but --state not supplied.
    dep_caps = nested_get(data, "source_map", "dependency_capsules") or []
    if isinstance(dep_caps, list):
        needs_state = any(
            isinstance(cap, dict) and str(cap.get("foundation_checkpoint_required", "no")).lower() in ("yes", "true")
            for cap in dep_caps
        )
        if needs_state and not getattr(args, 'state', None):
            findings.append(("P1", loc,
                "dependency_capsule requires foundation-checkpoint verification but --state was not supplied — "
                "card check must FAIL CLOSED"))
    if isinstance(dep_caps, list) and getattr(args, 'state', None):
        dep_state_data, _ = load_yaml(args.state)
        dep_checkpoints = (dep_state_data.get("foundation_checkpoints_passed") or []) if isinstance(dep_state_data, dict) else []
        for cap in dep_caps:
            if isinstance(cap, dict):
                dep_id = cap.get("module_or_card_id")
                needs = str(cap.get("foundation_checkpoint_required", "no")).lower() in ("yes", "true")
            elif isinstance(cap, str):
                dep_id = cap
                needs = False  # bare string entry carries no checkpoint requirement
            else:
                continue
            if needs and dep_id and dep_id not in dep_checkpoints:
                findings.append(("P1", loc,
                    f"dependency_capsule '{dep_id}' requires a foundation checkpoint that is NOT recorded "
                    "in foundation_checkpoints_passed — dependent card BLOCKED until it passes"))

    # --- family_note injected ---
    fn = data.get("family_note")
    if not fn or not isinstance(fn, dict):
        findings.append(("P1", loc, "family_note missing — must be injected by the Card Compiler"))
    else:
        if not field_present(fn, "known_quirk"):
            findings.append(("P1", loc, "family_note.known_quirk missing"))
        if not field_present(fn, "leash"):
            findings.append(("P1", loc, "family_note.leash missing"))

    # --- execution block: BUILD-ENGINE-PROFILES enforcement (PROP-013, clauses 1-5) ---
    _check_execution(data, args, loc, findings)

    # --- review_dispatch: three-leg ask on review/audit cards (PROP-015) ---
    _check_review_dispatch(data, loc, findings)

    # --- ui_contract + fixture_replacement_map + visual_contract_context (PROP-019) ---
    _check_ui_contract(data, loc, findings)

    # --- PROTOCOL_INCIDENT gate: blocks new build/cross-family while open (PROP-020) ---
    _check_incident_gate(data, args, loc, findings)

    # --- PROP-034 Lever A: re-anchor-before-fix on mode: FIX cards ---
    _check_lock_fidelity(data, args, loc, findings)

    # --- actor_record: present + cross-family check ---
    ar = data.get("actor_record")
    if not ar or not isinstance(ar, dict):
        findings.append(("P0", loc, "actor_record missing"))
    else:
        executor = ar.get("executor", {}) or {}
        cross = ar.get("cross_review", {}) or {}

        exec_family = executor.get("family", "")
        cross_family = cross.get("family", "")
        family_substituted = cross.get("family_substituted", "no")
        ceo_ref = cross.get("ceo_authorization_ref", "")

        if exec_family and cross_family:
            same_family = exec_family.lower() == cross_family.lower()
            if same_family:
                sub_yes = str(family_substituted).lower() in ("yes", "true")
                if sub_yes and ceo_ref:
                    # Allowed but opens a P2 blocking finding — check state if supplied (P2-01)
                    state_path_arg = getattr(args, 'state', None)
                    if state_path_arg:
                        state_data, _ = load_yaml(state_path_arg)
                        if state_data and isinstance(state_data, dict):
                            state_items = (state_data.get("open_findings") or {}).get("items") or []
                            card_id = data.get("id", "")
                            has_pending = any(
                                isinstance(it, dict) and
                                "CROSS_FAMILY_RECHECK_PENDING" in str(it.get("finding", "")) and
                                it.get("owner_card") and
                                (not card_id or it.get("owner_card") == card_id or
                                 str(it.get("source_card", "")) == card_id)
                                for it in state_items
                            )
                            if not has_pending:
                                findings.append(("P1", loc,
                                    "family_substituted:yes + state provided but no CROSS_FAMILY_RECHECK_PENDING "
                                    "item found in open_findings.items (owner_card must be set)"))
                    else:
                        findings.append(("P2", loc,
                            "same-family cross_review with family_substituted:yes — "
                            "CROSS_FAMILY_RECHECK_PENDING (P2) must be opened in CODE-X-STATE"))
                else:
                    findings.append(("P0", loc,
                        "cross_review.family == executor.family — "
                        "same-family cross-review REJECTED (need opposite family, "
                        "or family_substituted:yes + ceo_authorization_ref)"))
        elif not cross_family:
            findings.append(("P1", loc, "actor_record.cross_review.family missing"))
        elif not exec_family:
            findings.append(("P1", loc, "actor_record.executor.family missing"))

        # --- CodeRabbit can NEVER satisfy the cross-family checkpoint (stand-in = IOU only) ---
        cross_text = " ".join(
            str(cross.get(k, "")) for k in ("actor", "family", "model")
        ).lower()
        if "coderabbit" in cross_text:
            sub_yes = str(family_substituted).lower() in ("yes", "true")
            if sub_yes and ceo_ref:
                findings.append(("P2", loc,
                    "CodeRabbit recorded as cross_review stand-in (IOU) — "
                    "CROSS_FAMILY_RECHECK_PENDING (P2) must be open in CODE-X-STATE; "
                    "it never SATISFIES the cross-family checkpoint"))
            else:
                findings.append(("P0", loc,
                    "CodeRabbit recorded as a SATISFIED cross-family checkpoint — REJECTED "
                    "(family is opaque/mixed; allowed only as family_substituted:yes stand-in "
                    "with ceo_authorization_ref, opening a CROSS_FAMILY_RECHECK_PENDING IOU)"))

    # --- card_compilation.audited_by IS the pre-build cross-family checkpoint — never CodeRabbit ---
    if isinstance(cc_block, dict):
        audited_by = cc_block.get("audited_by") or {}
        if isinstance(audited_by, dict):
            audit_text = " ".join(
                str(audited_by.get(k, "")) for k in ("actor", "family", "model")
            ).lower()
            if "coderabbit" in audit_text:
                findings.append(("P0", loc,
                    "card_compilation.audited_by names CodeRabbit — the card audit IS the "
                    "cross-family checkpoint and CodeRabbit can never satisfy it"))

    # --- allowed_files + forbidden_files + allowed_operations declared ---
    allowed_files = data.get("allowed_files")
    if allowed_files is None:
        findings.append(("P1", loc, "allowed_files missing — must be declared (can be empty list)"))

    forbidden_files = data.get("forbidden_files")
    if forbidden_files is None:
        findings.append(("P1", loc, "forbidden_files missing — must be declared"))

    allowed_ops = data.get("allowed_operations")
    if allowed_ops is None:
        findings.append(("P1", loc, "allowed_operations missing — must be declared"))

    forbidden_ops = data.get("forbidden_operations")
    if forbidden_ops is None:
        findings.append(("P1", loc, "forbidden_operations missing — must be declared"))

    # --- security_tripwire set (present as a dict with at least one key) ---
    st = data.get("security_tripwire")
    if not st or not isinstance(st, dict):
        findings.append(("P0", loc, "security_tripwire missing — must be set by the compiler"))

    # --- read budget: required list not over cap + estimate_tokens ceiling (P2-03) ---
    read_section = data.get("read", {}) or {}
    read_required = read_section.get("required", []) or []
    if isinstance(read_required, list) and len(read_required) > 25:
        findings.append(("P1", loc,
            f"read.required has {len(read_required)} files — likely over the kernel read budget ({READ_BUDGET_TOKENS} token cap implies a small read list)"))
    est_tokens = read_section.get("estimate_tokens")
    if est_tokens is not None:
        try:
            est_tokens_int = int(est_tokens)
            if est_tokens_int > READ_BUDGET_TOKENS:
                findings.append(("P1", loc,
                    f"read.estimate_tokens={est_tokens_int} exceeds kernel ceiling {READ_BUDGET_TOKENS} — reduce read list"))
        except (TypeError, ValueError):
            findings.append(("P1", loc, f"read.estimate_tokens='{est_tokens}' is not a valid integer"))

    # --- cost_budget present ---
    cb = data.get("cost_budget")
    if cb is None:
        findings.append(("P2", loc, "cost_budget missing — soft target required"))

    # --- evidence_required present ---
    ev = data.get("evidence_required")
    if ev is None:
        findings.append(("P1", loc, "evidence_required missing — must list exact proof paths"))

    # --- required work-order fields (P1-06, CHARTER.md line 55) ---
    # Every work-order must contain these five keys to be auditable.
    for wo_field in ("relevant_invariants", "acceptance", "stop_conditions", "state_update"):
        val = data.get(wo_field)
        if val is None or val == "" or val == [] or val == {}:
            findings.append(("P1", loc,
                f"{wo_field} missing or empty — required work-order field per CHARTER"))
    lb = data.get("loop_budget")
    if lb is None or not isinstance(lb, dict):
        findings.append(("P1", loc,
            "loop_budget missing or not a mapping — required work-order field per CHARTER"))
    elif "review_fix_cycles" not in lb:
        findings.append(("P1", loc,
            "loop_budget.review_fix_cycles missing — anti-grind cap required in every work-order"))
    else:
        # A3 (V1.10): reject review_fix_cycles > 1 at card level (one-and-done is a CARD
        # contract) EXCEPT a SELF_REVIEW card, which may run the bounded model-escalation
        # loop up to 3 (builder → stronger → strongest). Cross-family/CARD_AUDIT stay <= 1.
        rfc = lb.get("review_fix_cycles")
        rd_kind = str(nested_get(data, "review_dispatch", "review_kind") or "")
        # The cap-3 budget is bound to a GENUINE same-family self review (GPT P1-2): a SELF_REVIEW
        # label alone is not enough — the actor_record must back it (self_review.required AND
        # self_review.family == executor.family) so a cross-family/audit dispatch cannot relabel
        # itself SELF_REVIEW to buy extra fix cycles.
        ex_fam = str(nested_get(data, "actor_record", "executor", "family") or "").strip().lower()
        sr = nested_get(data, "actor_record", "self_review")
        sr = sr if isinstance(sr, dict) else {}
        sr_required = str(sr.get("required", "")).strip().lower() in ("yes", "true")
        sr_fam = str(sr.get("family", "") or "").strip().lower()
        self_review_backed = (rd_kind == "SELF_REVIEW" and sr_required
                              and bool(ex_fam) and sr_fam == ex_fam)
        cap = 3 if self_review_backed else 1
        try:
            if int(rfc) > cap:
                if rd_kind == "SELF_REVIEW" and not self_review_backed:
                    findings.append(("P1", loc,
                        "loop_budget.review_fix_cycles > 1 with review_kind SELF_REVIEW, but the card's "
                        "actor_record does not back a genuine same-family self review "
                        "(needs self_review.required + self_review.family == executor.family) — a "
                        "mislabeled cross-family/audit dispatch cannot use the escalation loop [V1.10]"))
                elif cap == 1:
                    findings.append(("P1", loc,
                        "loop_budget.review_fix_cycles must be <= 1 under one-and-done review "
                        "discipline (only a SELF_REVIEW card may use the bounded escalation loop, "
                        "cap 3) [V1.10]"))
                else:
                    findings.append(("P1", loc,
                        "loop_budget.review_fix_cycles must be <= 3 for a SELF_REVIEW card "
                        "(bounded model-escalation loop) [V1.10]"))
        except (TypeError, ValueError):
            findings.append(("P1", loc,
                "loop_budget.review_fix_cycles must be an integer"))

    # --- card size rough check ---
    try:
        raw_text = Path(path).read_text(encoding="utf-8")
        tok = rough_token_count(raw_text)
        if tok > CARD_TOKEN_BUDGET:
            findings.append(("P2", loc,
                f"card is ~{tok} tokens (budget: {CARD_TOKEN_BUDGET}) — too big, consider splitting"))
    except Exception:
        pass

    return findings_report(findings)
