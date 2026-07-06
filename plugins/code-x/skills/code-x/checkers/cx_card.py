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
    """PBF-PROP-008 BUILD-ENGINE-PROFILES enforcement — card-side clauses 1-5."""
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


# --- B-PROP-003: UI-contract carry-forward (the Sample W4 scar) -----------------
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


def _resolve_card_registry_screen(data: dict, args) -> tuple[str | None, str | None, str | None]:
    """[PBF-PROP-020 Rule 1] Resolve (screen_id, live_lock_ref, error) for the card's module_id
    via the frozen MODULE-REGISTRY. Returns (None, None, None) when the card names no module_id,
    --state is not supplied, state.packet_dir is unsafe/absent, or the module_id does not resolve
    to a registry 'screen' row — Rule 1 then does not apply (legacy/no-registry projects and
    non-screen modules are untouched, matching the design's registry-gated scope). Returns
    (screen_id, None, error) when the card DOES target a registered screen but the registry or its
    live lock cannot be resolved — the caller fails closed on a non-None error."""
    module_id = str(data.get("module_id", "") or "").strip()
    state_path = getattr(args, "state", None)
    if not module_id or not state_path:
        return None, None, None
    state_data, _serr = load_yaml(state_path)
    if not isinstance(state_data, dict):
        return None, None, None
    packet_dir_rel = str(state_data.get("packet_dir", "") or "").strip()
    if not packet_dir_rel:
        return None, None, None
    from cx_lock_fidelity import path_is_unsafe, frozen_registry_rows, registry_screen_lock
    if path_is_unsafe(packet_dir_rel):
        return None, None, None
    repo_root = str(Path(state_path).resolve().parent)
    rows, rerr = frozen_registry_rows(repo_root, packet_dir_rel)
    if rerr:
        return None, None, rerr
    screen_id = None
    for m in rows:
        if isinstance(m, dict) and str(m.get("module_id", "")).strip() == module_id:
            if str(m.get("kind", "")).strip() == "screen" and m.get("screen_id"):
                screen_id = str(m.get("screen_id")).strip()
            break
    if not screen_id:
        return None, None, None
    live_lock, lerr = registry_screen_lock(rows, screen_id)
    if lerr:
        return screen_id, None, lerr
    return screen_id, live_lock, None


def _check_ui_contract(data: dict, args, loc: str, findings: list) -> None:
    """[G3/G6, B-PROP-003] ui_contract required on UI-touching/fixture-purging cards;
    purge additionally requires a complete fixture_replacement_map (no map, no G3 pass).
    DESIGN_FIXTURE_PURGE != DESIGN_DELETE: replace fixture data, preserve the
    CEO-accepted shell and controls."""
    ui = _touches_ui(data)
    purge = _purges_fixtures(data)
    if not ui and not purge:
        return

    # PBF-PROP-020 Rule 1 (MOCKUP-FIRST-CHANGE-NEEDS-LOCK, P0, fail-closed by default): a
    # UI-touching card that is NOT (mode: FIX + deviation_class: RESTORE) and whose module_id
    # resolves to a registered SCREEN must carry ui_contract.lock_ref == that screen's CURRENT
    # LIVE lock_ref in MODULE-REGISTRY.yaml, and that lock_ref must be in read.required. No
    # opt-in flag — a card cannot dodge by omission; the only zero-ceremony exemption is an
    # anchored RESTORE fix.
    if ui:
        is_restore_fix = (str(data.get("mode", "")) == "FIX"
                          and str(data.get("deviation_class", "") or "") == "RESTORE")
        if not is_restore_fix:
            screen_id, live_lock, rerr = _resolve_card_registry_screen(data, args)
            if screen_id:
                uc_r1 = data.get("ui_contract")
                lock_ref = (str(uc_r1.get("lock_ref", "") or "").strip()
                           if isinstance(uc_r1, dict) else "")
                read_required_r1 = [str(x) for x in (nested_get(data, "read", "required") or [])]
                if rerr:
                    findings.append(("P0", loc,
                        f"card targets registered screen '{screen_id}' but its CURRENT LIVE lock "
                        f"cannot be resolved from MODULE-REGISTRY.yaml — {rerr} (fail-closed, "
                        "MOCKUP-FIRST-CHANGE-NEEDS-LOCK, PBF-PROP-020 Rule 1)"))
                elif not lock_ref:
                    findings.append(("P0", loc,
                        f"card touches UI on registered screen '{screen_id}' (not a RESTORE fix) "
                        "with no ui_contract.lock_ref — a UI-touching change needs the screen's "
                        "CURRENT LIVE lock; prose-only change orders are rejected "
                        "(MOCKUP-FIRST-CHANGE-NEEDS-LOCK, PBF-PROP-020 Rule 1)"))
                elif lock_ref != live_lock:
                    findings.append(("P0", loc,
                        f"ui_contract.lock_ref '{lock_ref}' != screen '{screen_id}' CURRENT LIVE "
                        f"lock_ref '{live_lock}' in MODULE-REGISTRY.yaml — a stale or wrong lock is "
                        "not the mockup-first lock (MOCKUP-FIRST-CHANGE-NEEDS-LOCK, PBF-PROP-020 Rule 1)"))
                elif lock_ref not in read_required_r1:
                    findings.append(("P0", loc,
                        f"ui_contract.lock_ref '{lock_ref}' is not in read.required — the locked "
                        "mockup must ride the card's read set, not just be named "
                        "(MOCKUP-FIRST-CHANGE-NEEDS-LOCK, PBF-PROP-020 Rule 1)"))

                # FOLD RE-SWEEP FIX (CITE-AND-COMPARE): citing the lock is necessary but not
                # sufficient — a UI change on a registered screen must also be COMPARED against it.
                # The card must declare a render_bundle so the build-turn rail runs cx check
                # render-fidelity (Rules 2/7). Omitting render_bundle made build-turn mark
                # render-fidelity NOT_APPLICABLE — a fail-open dodge (lock referenced, never rendered
                # against) the extra xfam sweep caught. This is what makes Rule 2 the real backstop
                # the design leans on. RESTORE fixes never reach here (is_restore_fix short-circuits).
                if not str(data.get("render_bundle", "") or "").strip():
                    findings.append(("P0", loc,
                        f"card touches UI on registered screen '{screen_id}' (not a RESTORE fix) "
                        "with no render_bundle — the cited lock must be COMPARED against a render, "
                        "not merely referenced; declare render_bundle so the rendered-fidelity exit "
                        "gate (Rules 2/7) runs, else the change ships un-rendered-compared "
                        "(MOCKUP-FIRST-CHANGE-NEEDS-LOCK, PBF-PROP-020 Rule 1)"))

    uc = data.get("ui_contract")
    if not isinstance(uc, dict):
        findings.append(("P1", loc,
            "card touches UI files (templates/static/HTML) or purges Mode A fixtures "
            "WITHOUT ui_contract — STOP, the card is wrong; never infer the visual "
            "contract (B-PROP-003, the Sample W4 scar)"))
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
    # (PBF-PROP-009 stanza itself stays verbatim).
    rd = data.get("review_dispatch")
    if isinstance(rd, dict) and str(rd.get("required", "no")).lower() in ("yes", "true"):
        vcc = data.get("visual_contract_context")
        if not isinstance(vcc, dict):
            findings.append(("P1", loc,
                "UI review dispatch without visual_contract_context — the reviewer must "
                "answer: does this preserve the CEO-accepted visual contract? (B-PROP-003)"))
        else:
            for key in VISUAL_CONTEXT_KEYS:
                if not field_present(vcc, key):
                    findings.append(("P1", loc, f"visual_contract_context.{key} missing"))


def _check_incident_gate(data: dict, args, loc: str, findings: list) -> None:
    """[BF-PROP-002] While a PROTOCOL_INCIDENT is open, new build cards are BLOCKED and
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
            "final-ready is forbidden while the incident is open (BF-PROP-002)"))


# PBF-PROP-009 (review-three-leg-ask): values that prove nothing — green-but-not-enforcing.
TLA_PLACEHOLDERS = {"asked", "yes", "included", "n/a", "na", "blank", "done", "ok", "true"}
REVIEW_MODES = {"REVIEW", "FINAL_READY"}
VALID_REVIEW_KINDS = {"SELF_REVIEW", "CROSS_FAMILY", "CARD_AUDIT", "FINAL_READY", "PROTOCOL_CHANGE"}
# leg field -> canonical label that must appear in the quoted ask (relaxed: prompt_ref substitutes)
TLA_LEGS = {"continuity": "CONTINUITY", "problems": "PROBLEMS", "approach_improvement": "APPROACH"}


def _check_review_dispatch(data: dict, loc: str, findings: list) -> None:
    """[RULE:review-three-leg-ask] PBF-PROP-009: a review-dispatch card must prove all three
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
            "(PBF-PROP-009) [RULE:review-three-leg-ask]"))
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
            "(continuity/problems/approach_improvement) must quote how they were asked (PBF-PROP-009)"))
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


def resolve_card_risk_tier(args) -> str:
    """PBF-PROP-019 Phase 3: resolve the CURRENT build's project risk_tier via --state.packet_dir,
    mirroring the packet_dir resolution every other cx_card fix-card helper already uses
    (path_is_unsafe + resolve_in_repo, e.g. _check_lock_fidelity above). Reuses the single
    cx_common.resolve_risk_tier helper — never re-implements tier resolution. Absent/unreadable
    state or an unsafe/unresolvable packet_dir resolves STRICT (fail-closed; a card check that
    cannot determine the tier must never silently relax ceremony)."""
    from cx_lock_fidelity import path_is_unsafe, resolve_in_repo
    from cx_common import resolve_risk_tier
    state_path = getattr(args, "state", None) if args is not None else None
    if not state_path:
        return "STRICT"
    state_data, serr = load_yaml(state_path)
    if serr or not isinstance(state_data, dict):
        return "STRICT"
    packet_dir_rel = str(state_data.get("packet_dir", "") or "").strip()
    if not packet_dir_rel or path_is_unsafe(packet_dir_rel):
        return "STRICT"
    repo_root = str(Path(state_path).resolve().parent)
    resolved_pkt, perr = resolve_in_repo(repo_root, packet_dir_rel)
    if perr or resolved_pkt is None:
        return "STRICT"
    return resolve_risk_tier(resolved_pkt)


def _check_coderabbit_required_for_code_diff(data: dict, loc: str, findings: list, risk_tier: str = "STRICT") -> None:
    """PROP-042 / v1.21: CodeRabbit is a planned rail on code-diff build cards, not an
    optional note the builder may forget. The receipt itself is produced after a
    diff exists and is validated by build-turn.

    PBF-PROP-019 Phase 3 (design v2.B ceremony row 3): a LITE-tier project drops the CodeRabbit
    requirement — self-review only. STANDARD/STRICT are unchanged from today. This tier read does
    NOT touch the Phase-2 mechanical high-risk-card force (CARD-HIGH-RISK-FORCES-FOUNDATION): a
    high-risk card still forces its foundation checkpoint + full cross-family review regardless of
    tier; CodeRabbit is a SEPARATE rail this clause alone governs."""
    mode = str(data.get("mode", "") or "").strip()
    if mode not in ("MODULE_BUILD", "MODE_A_UI"):
        return
    if risk_tier == "LITE":
        return  # PBF-PROP-019: LITE drops the CodeRabbit rail requirement
    cr = data.get("coderabbit")
    required = ""
    if isinstance(cr, dict):
        required = str(cr.get("required", "") or "").strip().lower()
    if required not in ("yes", "true"):
        findings.append(("P1", loc,
            "CodeRabbit rail missing — MODULE_BUILD / MODE_A_UI code-diff cards must declare "
            "coderabbit.required: yes so every build module/final code-diff review has a typed "
            "CodeRabbit receipt before self/cross review (PROP-042 / v1.21)"))


def _check_prevention_preamble(data: dict, loc: str, findings: list) -> None:
    """[RULE:builder-prevention-preamble] PBF-PROP-012 Part C: the orchestrator MUST inject the
    canonical do-less prevention preamble (B-PROP-005) into the builder subagent's prompt on EVERY
    engine. The Card Compiler records that injection in execution.prevention_preamble. Engine-
    agnostic: keys on the injection MARKER, not a vendor agent file. Missing/forged = P1 (the
    slice was built with no prevention reaching the builder — the exact real-project gap)."""
    mode = str(data.get("mode", "") or "").strip()
    if mode not in ("MODULE_BUILD", "MODE_A_UI"):
        return
    pp = nested_get(data, "execution", "prevention_preamble")
    if not isinstance(pp, dict):
        findings.append(("P1", loc,
            "execution.prevention_preamble missing — the orchestrator must inject the canonical "
            "builder prevention preamble (B-PROP-005 do-less ladder) into the builder prompt on every "
            "engine; the Card Compiler records the injection marker [RULE:builder-prevention-preamble]"))
        return
    if str(pp.get("rule", "")).strip() != "builder-prevention-preamble":
        findings.append(("P1", loc,
            "execution.prevention_preamble.rule must be 'builder-prevention-preamble' — the canon token"))
    if str(pp.get("injected", "")).strip().lower() not in ("yes", "true"):
        findings.append(("P1", loc,
            "execution.prevention_preamble.injected must be yes — proof the preamble reached the builder"))
    sha12_val = str(pp.get("preamble_sha12", "")).strip()
    if not sha12_val:
        findings.append(("P1", loc,
            "execution.prevention_preamble.preamble_sha12 missing — a real injected preamble must be hashed (no stub)"))
    elif not re.fullmatch(r"[0-9a-f]{12}", sha12_val):
        findings.append(("P1", loc,
            f"execution.prevention_preamble.preamble_sha12 {sha12_val!r} must be exactly 12 lowercase hex "
            "digits — a stub or shortened hash is not a real preamble hash (P2-005)"))
    ref = str(pp.get("standard_ref", "")).strip()
    if ref and (Path(ref).is_absolute() or ".." in Path(ref).parts):
        findings.append(("P1", loc,
            "execution.prevention_preamble.standard_ref must be a relative in-repo path"))
    elif ref and ref != "BUILDER-STANDARD.md":
        findings.append(("P1", loc,
            f"execution.prevention_preamble.standard_ref must be 'BUILDER-STANDARD.md', got {ref!r} — "
            "the canon preamble standard is fixed (P2-005)"))


def _check_lock_fidelity(data: dict, args, loc: str, findings: list) -> None:
    """[BF-PROP-007 Lever A] A FIX/correction card must RE-ANCHOR to the frozen lock before it fixes.

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
            "(BF-PROP-007 Lever A / LOCK-FIDELITY-DEVIATION-CLASS-MISSING) "
            "[RULE:lock-fidelity-fail-closed]"))
    elif dev_class not in VALID_DEVIATION_CLASSES:
        findings.append(("P1", loc,
            f"deviation_class '{dev_class}' not in {sorted(VALID_DEVIATION_CLASSES)} — "
            "RESTORE | AMBIGUITY_RESOLVED | SCOPE_CHANGE (BF-PROP-007 Lever A)"))

    # SCOPE_CHANGE authorization (independent of the packet — both refs must be present)
    if dev_class == "SCOPE_CHANGE":
        ceo_ref = str(data.get("ceo_decision_ref", "") or "").strip()
        amend_ref = str(data.get("packet_amendment_ref", "") or "").strip()
        if not ceo_ref or not amend_ref:
            sev = "P0" if card_high_risk(data) else "P1"
            findings.append((sev, loc,
                "deviation_class: SCOPE_CHANGE without BOTH ceo_decision_ref AND "
                "packet_amendment_ref — anything not already in the lock CANNOT be built as a fix; "
                "it needs a CEO decision + a packet amendment/re-freeze (or a new PROP) (BF-PROP-007 "
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
            "(BF-PROP-007 Lever A / LOCK-FIDELITY-FIX-ANCHOR-MISSING)"))
        return
    req_id = anchor_req_id

    # Anchor MUST resolve inside the frozen packet named by state.packet_dir.
    state_path = getattr(args, "state", None)
    if not state_path:
        findings.append(("P1", loc,
            "mode: FIX card carries lock_anchor_ref but --state was not supplied — cannot resolve "
            "the anchor against the frozen packet (state.packet_dir); fail closed (BF-PROP-007 Lever A)"))
        return
    state_data, _serr = load_yaml(state_path)
    if not isinstance(state_data, dict):
        findings.append(("P1", loc,
            f"mode: FIX card: state file '{state_path}' unreadable — cannot resolve the lock anchor "
            "(BF-PROP-007 Lever A)"))
        return
    packet_dir_rel = str(state_data.get("packet_dir", "") or "").strip()
    repo_root = str(Path(state_path).resolve().parent)
    if path_is_unsafe(packet_dir_rel):
        findings.append(("P1", loc,
            f"state.packet_dir '{packet_dir_rel}' is unsafe (absolute / '..') — the frozen packet "
            "must be an in-tree path; fail closed (BF-PROP-007 Lever A)"))
        return

    # F2: the packet the card anchors to is BOUND to the card by hash. RECOMPUTE the state.packet_dir
    # packet hash and require it == the card's source_map.locked_packet_hash, so a fix cannot anchor
    # to an attacker-chosen in-repo packet (a different frozen dir) while pointing state elsewhere.
    declared_pkt_hash = str(nested_get(data, "source_map", "locked_packet_hash") or "").strip()
    if not declared_pkt_hash:
        findings.append(("P1", loc,
            "mode: FIX card without source_map.locked_packet_hash — a fix must bind to the packet it "
            "restores by hash so its anchor cannot point at an attacker-chosen packet (BF-PROP-007 Lever A / F2)"))
        return
    real_pkt_hash, herr = recompute_frozen_packet_hash(repo_root, packet_dir_rel)
    if herr or real_pkt_hash is None:
        findings.append(("P1", loc,
            f"mode: FIX card: cannot recompute the frozen packet hash to bind the anchor — {herr} "
            "(BF-PROP-007 Lever A / F2)"))
        return
    if declared_pkt_hash != real_pkt_hash:
        findings.append(("P1", loc,
            f"source_map.locked_packet_hash '{declared_pkt_hash}' != the RECOMPUTED hash of "
            f"state.packet_dir '{packet_dir_rel}' ('{real_pkt_hash}') — the fix anchors to a DIFFERENT "
            "packet than the live frozen one; a self-declared anchor packet is never trusted "
            "(BF-PROP-007 Lever A / F2)"))
        return

    req_ids, rerr = frozen_requirement_ids(repo_root, packet_dir_rel)
    if rerr or req_ids is None:
        findings.append(("P1", loc,
            f"mode: FIX card: cannot read the frozen packet to resolve lock_anchor_ref — {rerr} "
            "(BF-PROP-007 Lever A)"))
        return
    if req_id not in req_ids:
        findings.append(("P1", loc,
            f"lock_anchor_ref.requirement_id '{req_id}' does not resolve to a requirement inside the "
            f"frozen packet '{packet_dir_rel}' (requirements-manifest) — a fix must anchor to a real "
            "locked line (BF-PROP-007 Lever A)"))

    # F2: card_id MUST resolve to a card in the frozen MODULE-REGISTRY (the same source the order wall
    # + open-card derivation trust). An anchor naming a card not in the frozen deck cannot be the card
    # a fix restores — fail closed rather than letting the over-reach check skip an unfound anchor.
    resolved_pkt, _perr = resolve_in_repo(repo_root, packet_dir_rel)
    if resolved_pkt is not None:
        by_module, regerr = _frozen_registry(resolved_pkt)
        if regerr:
            findings.append(("P1", loc,
                f"mode: FIX card: cannot read the frozen MODULE-REGISTRY to resolve "
                f"lock_anchor_ref.card_id — {regerr} (BF-PROP-007 Lever A / F2)"))
        else:
            known_cards = {c for cards in by_module.values() for c in cards}
            if anchor_card_id not in known_cards:
                findings.append(("P1", loc,
                    f"lock_anchor_ref.card_id '{anchor_card_id}' does not resolve to a card in the "
                    f"frozen MODULE-REGISTRY of '{packet_dir_rel}' (known: {sorted(known_cards)}) — a "
                    "fix must anchor to a real frozen card (BF-PROP-007 Lever A / F2)"))

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
                    "packet is unreadable, so the authorizing decision cannot be verified (BF-PROP-007 "
                    "Lever A / F3)"))
            else:
                ledger_path = resolved_pkt / LEDGER_FILE
                if not ledger_path.is_file():
                    findings.append((sev, loc,
                        f"deviation_class: SCOPE_CHANGE names ceo_decision_ref '{ceo_ref}' but the "
                        f"packet has no {LEDGER_FILE} — the authorizing decision cannot resolve "
                        "(BF-PROP-007 Lever A / F3)"))
                else:
                    ledger_ids = set(LEDGER_ROW_ID_RE.findall(
                        ledger_path.read_text(encoding="utf-8", errors="replace")))
                    if ceo_ref not in ledger_ids:
                        findings.append((sev, loc,
                            f"deviation_class: SCOPE_CHANGE ceo_decision_ref '{ceo_ref}' does not "
                            f"resolve to a row in the packet {LEDGER_FILE} — a self-declared decision "
                            "id is not authorization (BF-PROP-007 Lever A / F3)"))
        if amend_ref:
            _resolved_amend, amend_err = resolve_in_repo(repo_root, amend_ref)
            if amend_err is not None:
                findings.append((sev, loc,
                    f"deviation_class: SCOPE_CHANGE packet_amendment_ref {amend_err} — the amendment "
                    "must be a real in-tree file (BF-PROP-007 Lever A / F3)"))
            elif _resolved_amend is None or not _resolved_amend.is_file():
                findings.append((sev, loc,
                    f"deviation_class: SCOPE_CHANGE packet_amendment_ref '{amend_ref}' does not point "
                    "at a real in-repo file — a missing amendment is not authorization (BF-PROP-007 "
                    "Lever A / F3)"))


def _packet_ledger_ids(args) -> tuple[set | None, str | None, str | None]:
    """Resolve the frozen packet's CEO-DECISION-LEDGER row ids via --state.packet_dir (the SAME source
    _check_lock_fidelity + the deck use). Returns (ledger_ids, repo_root, error). ledger_ids is a set of
    real row ids — an empty set means the packet has no ledger (every ref is then a ghost). error
    (non-None) means the ledger could not be resolved at all → the caller fails closed."""
    from cx_lock_fidelity import path_is_unsafe, resolve_in_repo
    from cx_deck import LEDGER_FILE, LEDGER_ROW_ID_RE
    state_path = getattr(args, "state", None)
    if not state_path:
        return None, None, "--state not supplied — cannot resolve the CEO-DECISION-LEDGER to verify refs"
    sd, _serr = load_yaml(state_path)
    if not isinstance(sd, dict):
        return None, None, f"state '{state_path}' unreadable — cannot resolve the ledger"
    pdr = str(sd.get("packet_dir", "") or "").strip()
    repo_root = str(Path(state_path).resolve().parent)
    if not pdr or path_is_unsafe(pdr):
        return None, repo_root, "state.packet_dir missing/unsafe — cannot resolve the ledger (fail closed)"
    resolved, perr = resolve_in_repo(repo_root, pdr)
    if perr or resolved is None:
        return None, repo_root, perr or "packet unresolved"
    lp = resolved / LEDGER_FILE
    if not lp.is_file():
        return set(), repo_root, None  # no ledger file = no known ids (refs will read as ghosts)
    return set(LEDGER_ROW_ID_RE.findall(lp.read_text(encoding="utf-8", errors="replace"))), repo_root, None


def load_fix_questions_log(repo_root: str, ref: str) -> tuple[set | None, str | None]:
    """[F-PROP-001 Lever B] Load + parse a typed FIX-QUESTIONS-LOG, returning (row_ids, error). The log is a
    YAML mapping carrying a fix_questions list of typed rows:
        fix_questions:
          - id: Q1
            question: "..."
            ...
    SHARED by cx_card (clarification_provenance file-backing) AND cx_close_turn (open-question reconcile)
    so both ends parse the SAME typed structure — never substring-matching free text (built-code review
    #5/#6: a card receipt or a `row in log_text` substring is not proof the question was filed). Fails
    closed: an unsafe ref / missing file / malformed YAML / non-typed shape returns an error; row_ids is
    the set of non-empty `id` values."""
    from cx_lock_fidelity import resolve_in_repo
    resolved, perr = resolve_in_repo(repo_root, str(ref))
    if perr is not None:
        return None, perr
    if resolved is None or not resolved.is_file():
        return None, f"'{ref}' does not resolve to a real in-repo file"
    doc, derr = load_yaml(str(resolved))
    if derr or not isinstance(doc, dict):
        return None, f"'{ref}' is not a typed FIX-QUESTIONS-LOG mapping {{fix_questions: [{{id, ...}}]}}"
    rows = doc.get("fix_questions")
    if not isinstance(rows, list) or not rows:
        return None, f"'{ref}' carries no fix_questions list — a typed log is fix_questions: [{{id, ...}}]"
    ids = {str(r.get("id", "") or "").strip() for r in rows if isinstance(r, dict)}
    ids.discard("")
    return ids, None


def _check_fix_amnesia(data: dict, args, loc: str, findings: list) -> None:
    """[F-PROP-001 Lever B] Anti-amnesia: every FIX-stage CEO question must be FILE-BACKED and reconcile.
    A mode: FIX card MAY carry a clarification_provenance block (a fix that asked no CEO questions has
    none — close-turn catches an asked-but-unlogged one). When present, EVERY question row must carry
    exactly one resolved path: (a) ledger_searched + related_ceo_d_refs that RESOLVE to real ledger rows,
    (b) a new_ledger_row_ref that resolves (the new decision was actually appended), or (c)
    contradicts_ceo_d + a resolved, path-safe ceo_override_ref for an answer that CHANGES a locked rule.
    Ghost ref / dangling new row / unresolved contradiction / unsafe override = fail closed. Severity P1
    default; P0 only when the card touches a danger class (the override changes money/auth/etc.)."""
    from cx_lock_fidelity import card_high_risk, resolve_in_repo
    if str(data.get("mode", "")) != "FIX":
        return
    cp = data.get("clarification_provenance")
    if cp is None:
        return  # no CEO questions to file-back (honest limit: close-turn reconciles an asked-but-unlogged one)
    if not isinstance(cp, dict):
        findings.append(("P1", loc,
            "clarification_provenance must be a mapping {fix_questions_log, questions: [...]} "
            "(F-PROP-001 Lever B)"))
        return
    questions = cp.get("questions")
    if not isinstance(questions, list) or not questions:
        findings.append(("P1", loc,
            "clarification_provenance.questions must be a non-empty list — a clarification_provenance "
            "block with no questions is meaningless (F-PROP-001 Lever B)"))
        return

    ledger_ids, repo_root, lerr = _packet_ledger_ids(args)
    if lerr:
        findings.append(("P1", loc,
            f"mode: FIX card carries clarification_provenance but {lerr} — cannot verify the "
            "anti-amnesia refs (F-PROP-001 Lever B / FIX-STAGE-AMNESIA-GHOST-REF)"))
        return

    # FIX-STAGE-AMNESIA-LOG-BACKED (built-code review #5): a card receipt is not file-backing. Require a
    # fix_questions_log that resolves to a real TYPED log, and every question.id must be a real row in it —
    # otherwise the question lived only on the card, defeating the close-turn reconcile that catches a
    # re-ask. Same typed parser the close-turn reconcile uses (one shared validator).
    log_ref = str(cp.get("fix_questions_log", "") or "").strip()
    if not log_ref:
        findings.append(("P1", loc,
            "clarification_provenance carries questions but no fix_questions_log — every FIX-stage question "
            "must be FILE-BACKED in a typed FIX-QUESTIONS-LOG, not a card-only receipt (F-PROP-001 Lever B / "
            "FIX-STAGE-AMNESIA-LOG-BACKED)"))
        return
    log_ids, logerr = load_fix_questions_log(repo_root, log_ref)
    if logerr is not None or log_ids is None:
        findings.append(("P1", loc,
            f"clarification_provenance.fix_questions_log {logerr} — the file-backed log must exist and be "
            "typed to anchor the questions (F-PROP-001 Lever B / FIX-STAGE-AMNESIA-LOG-BACKED)"))
        return

    high = card_high_risk(data)
    for i, q in enumerate(questions):
        if not isinstance(q, dict):
            findings.append(("P1", loc, f"clarification_provenance.questions[{i}] is not a mapping"))
            continue
        qid = str(q.get("id", "") or f"#{i}").strip()
        if qid not in log_ids:
            findings.append(("P1", loc,
                f"clarification_provenance question '{qid}' has no matching row in the FIX-QUESTIONS-LOG "
                f"'{log_ref}' — a question put to the CEO must be a typed row in the file-backed log, not "
                "declared only on the card (F-PROP-001 Lever B / FIX-STAGE-AMNESIA-LOG-BACKED)"))
            continue
        searched = str(q.get("ledger_searched", "")).strip().lower() in ("true", "yes", "1")
        related = q.get("related_ceo_d_refs") or []
        related = [str(r).strip() for r in related if str(r).strip()] if isinstance(related, list) else []
        new_ref = str(q.get("new_ledger_row_ref", "") or "").strip()
        contra = str(q.get("contradicts_ceo_d", "") or "").strip()
        override = str(q.get("ceo_override_ref", "") or "").strip()
        contra_sev = "P0" if high else "P1"

        if contra:
            # (c) the answer CHANGES a locked rule — needs a resolved, path-safe override + a real target.
            if not override:
                findings.append((contra_sev, loc,
                    f"clarification_provenance question '{qid}' contradicts {contra} with no "
                    "ceo_override_ref — changing a locked decision needs a resolved override, never a "
                    "silent second decision (F-PROP-001 Lever B / FIX-STAGE-AMNESIA-CONTRADICTION)"))
            else:
                _res, oerr = resolve_in_repo(repo_root, override)
                if oerr is not None:
                    findings.append(("P1", loc,
                        f"clarification_provenance question '{qid}' ceo_override_ref {oerr} (F-PROP-001 "
                        "Lever B / FIX-STAGE-AMNESIA-OVERRIDE-SAFE)"))
                elif _res is None or not _res.is_file():
                    findings.append((contra_sev, loc,
                        f"clarification_provenance question '{qid}' ceo_override_ref '{override}' does not "
                        "resolve to a real in-repo file — a missing override is not authorization (F-PROP-001 "
                        "Lever B / FIX-STAGE-AMNESIA-CONTRADICTION)"))
            if ledger_ids is not None and contra not in ledger_ids:
                findings.append((contra_sev, loc,
                    f"clarification_provenance question '{qid}' contradicts_ceo_d '{contra}' resolves to "
                    "no real ledger row — a self-declared decision id is not a real prior decision "
                    "(F-PROP-001 Lever B / FIX-STAGE-AMNESIA-GHOST-REF)"))
        elif new_ref:
            # (b) a genuinely new decision — the row must actually exist in the ledger.
            if ledger_ids is not None and new_ref not in ledger_ids:
                findings.append(("P1", loc,
                    f"clarification_provenance question '{qid}' new_ledger_row_ref '{new_ref}' is dangling "
                    "— a new decision must be appended to the CEO-DECISION-LEDGER, not merely named "
                    "(F-PROP-001 Lever B / FIX-STAGE-AMNESIA-GHOST-REF)"))
        elif searched and related:
            # (a) an already-decided answer — every related ref must resolve to a real ledger row.
            for r in related:
                if ledger_ids is not None and r not in ledger_ids:
                    findings.append(("P1", loc,
                        f"clarification_provenance question '{qid}' related_ceo_d_ref '{r}' resolves to no "
                        "real ledger row (ghost) — the search must point at a real prior decision (F-PROP-001 "
                        "Lever B / FIX-STAGE-AMNESIA-GHOST-REF)"))
        else:
            findings.append(("P1", loc,
                f"clarification_provenance question '{qid}' carries no resolution — a FIX-stage question "
                "must reconcile via ledger_searched+related_ceo_d_refs, a new_ledger_row_ref, or "
                "contradicts_ceo_d+ceo_override_ref; an unreconciled question is an off-the-books re-ask "
                "(F-PROP-001 Lever B / FIX-STAGE-AMNESIA-QLOG-RECONCILE)"))


def _check_fix_revert(data: dict, loc: str, findings: list) -> None:
    """[F-PROP-001 Lever E] Revert-on-drift honesty. No checker runs git reset — but a mode: FIX card that
    recovered from a Layer-1 lock drift must carry a typed revert_receipt {bad_head, restored_head,
    post_revert_clean, wip_handling}, NOT fix the drift forward. A card that marks
    drift_recovery_required but ships no (or a partial) revert_receipt is fixing forward in disguise."""
    if str(data.get("mode", "")) != "FIX":
        return
    rr = data.get("revert_receipt")
    needs = str(data.get("drift_recovery_required", "")).strip().lower() in ("true", "yes", "1")
    if not needs and rr is None:
        return  # no Layer-1 drift was recovered from — nothing to attest
    if rr is None:
        findings.append(("P1", loc,
            "mode: FIX card marks drift_recovery_required but carries no revert_receipt — a Layer-1 lock "
            "drift must be REVERTED then re-approached tighter, never fixed forward (F-PROP-001 Lever E / "
            "FIX-STAGE-REVERT-RECEIPT)"))
        return
    if not isinstance(rr, dict):
        findings.append(("P1", loc,
            "revert_receipt must be a typed mapping {bad_head, restored_head, post_revert_clean, "
            "wip_handling} (F-PROP-001 Lever E / FIX-STAGE-REVERT-RECEIPT)"))
        return
    missing = [k for k in ("bad_head", "restored_head", "post_revert_clean", "wip_handling")
               if not str(rr.get(k, "") or "").strip()]
    if missing:
        findings.append(("P1", loc,
            f"revert_receipt missing {missing} — a real revert names the bad head, the restored head, the "
            "clean post-revert state, and how WIP was handled; a partial receipt is a fix-forward in "
            "disguise (F-PROP-001 Lever E / FIX-STAGE-REVERT-RECEIPT)"))
        return
    for hk in ("bad_head", "restored_head"):
        h = str(rr.get(hk)).strip().lower()
        if len(h) < 7 or not all(c in "0123456789abcdef" for c in h):
            findings.append(("P1", loc,
                f"revert_receipt.{hk} '{rr.get(hk)}' is not a commit sha — the revert must name real "
                "commits (F-PROP-001 Lever E / FIX-STAGE-REVERT-RECEIPT)"))
    if str(rr.get("post_revert_clean")).strip().lower() not in ("true", "yes", "clean", "1"):
        findings.append(("P1", loc,
            "revert_receipt.post_revert_clean must assert the locked surfaces are CLEAN after the revert — "
            "a non-clean revert did not restore the architecture (F-PROP-001 Lever E / FIX-STAGE-REVERT-RECEIPT)"))


# F-PROP-001 Lever C — the per-target cross-lock taxonomy (closed set; two targets were too coarse, xfam P1-4).
VALID_FIX_TARGETS = {"frontend", "business_rule", "data_schema_migration", "api_contract",
                     "auth_security", "infra_config", "content_copy"}


def _check_fix_targets(data: dict, loc: str, findings: list) -> None:
    """[F-PROP-001 Lever C] The cross-lock: a mode: FIX card names ONE fix_target (or explicitly declares
    crossing layers); everything outside the declared targets' surfaces is a frozen assertion.
      - FIX-STAGE-POSTURE-DECL: fix_targets missing/empty, or a target outside the closed taxonomy.
      - FIX-STAGE-XLOCK-MULTI-ANCHOR: a MULTI-target fix must carry one lock_anchor_ref {card_id,
        requirement_id} + reason PER target — no blanket 'declare everything to open everything'.
      - FIX-STAGE-XLOCK-SURFACE: EVERY target must declare a non-empty `surfaces` list (built-code review
        #4 — surfaces were optional, so a fix could declare backend allowed_files and pass by omitting
        surfaces); and every allowed_files entry must fall within the union of declared surfaces. A target
        with no surfaces, or an allowed_file outside all declared surfaces, is a silent layer-cross (P1
        default, P0 on a danger-class card)."""
    import fnmatch as _fnmatch
    from cx_lock_fidelity import card_high_risk
    if str(data.get("mode", "")) != "FIX":
        return
    targets = data.get("fix_targets")
    if not isinstance(targets, list) or not targets:
        findings.append(("P1", loc,
            "mode: FIX card missing fix_targets — a fix must name ONE target from the cross-lock "
            "taxonomy (or explicitly declare crossing layers); everything else freezes (F-PROP-001 "
            "Lever C / FIX-STAGE-POSTURE-DECL)"))
        return

    multi = len(targets) >= 2
    declared_surfaces = []
    for i, t in enumerate(targets):
        if not isinstance(t, dict):
            findings.append(("P1", loc,
                f"fix_targets[{i}] is not a mapping {{target, lock_anchor_ref, reason, surfaces}} "
                "(F-PROP-001 Lever C / FIX-STAGE-POSTURE-DECL)"))
            continue
        name = str(t.get("target", "") or "").strip()
        if name not in VALID_FIX_TARGETS:
            findings.append(("P1", loc,
                f"fix_targets[{i}].target '{name}' not in {sorted(VALID_FIX_TARGETS)} — the cross-lock "
                "taxonomy is a closed set (F-PROP-001 Lever C / FIX-STAGE-POSTURE-DECL)"))
            continue
        if multi:
            anchor = t.get("lock_anchor_ref")
            ok_anchor = (isinstance(anchor, dict)
                         and str(anchor.get("card_id", "") or "").strip()
                         and str(anchor.get("requirement_id", "") or "").strip())
            if not ok_anchor or not str(t.get("reason", "") or "").strip():
                findings.append(("P1", loc,
                    f"fix_targets[{i}] ('{name}') in a multi-target fix lacks its own lock_anchor_ref "
                    "{card_id, requirement_id} + reason — a cross-layer fix declares each target out "
                    "loud, no blanket open-everything (F-PROP-001 Lever C / FIX-STAGE-XLOCK-MULTI-ANCHOR)"))
        # FIX-STAGE-XLOCK-SURFACE (surfaces REQUIRED — built-code review #4): every target must name the
        # surfaces it opens, else a fix bypasses the cross-lock by omitting surfaces entirely.
        surf = t.get("surfaces")
        clean = [str(s).strip() for s in surf if str(s).strip()] if isinstance(surf, list) else []
        if not clean:
            findings.append(("P1", loc,
                f"fix_targets[{i}] ('{name}') declares no surfaces — every target must name the allowed "
                "surfaces it opens; an omitted surfaces list lets a fix touch files its declared targets "
                "do not open, bypassing the cross-lock (F-PROP-001 Lever C / FIX-STAGE-XLOCK-SURFACE)"))
        declared_surfaces.extend(clean)

    if declared_surfaces:
        new_outputs = {str(x) for x in (data.get("new_outputs") or [])}
        sev = "P0" if card_high_risk(data) else "P1"
        for f in (str(x) for x in (data.get("allowed_files") or [])):
            if f in new_outputs:
                continue
            if not any(f == g or _fnmatch.fnmatch(f, g) for g in declared_surfaces):
                findings.append((sev, loc,
                    f"allowed_files entry '{f}' is OUTSIDE every declared fix_targets surface "
                    f"{declared_surfaces} — a fix that edits a surface its declared targets do not open "
                    "is silently crossing layers; declare the target or split the fix (F-PROP-001 Lever C / "
                    "FIX-STAGE-XLOCK-SURFACE)"))


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

    # PBF-PROP-019 Phase 3: resolve once, reused by the CodeRabbit + cross-review ceremony reads below.
    risk_tier_val = resolve_card_risk_tier(args)

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
    from cx_lock_fidelity import card_high_risk
    fcp_required = str(data.get("foundation_checkpoint_required", "no")).lower()

    # PBF-PROP-019 Phase 2 (design v2 P0-1, CARD-HIGH-RISK-FORCES-FOUNDATION): a card whose
    # security_tripwire marks it high-risk (money/auth/secrets/PII/destructive) MECHANICALLY
    # requires the foundation checkpoint — regardless of self-declaration AND regardless of
    # project risk tier (this gate is SPINE; it never reads risk_tier). Before this fix, a
    # high-risk card with foundation_checkpoint_required: no passed silently — the hole a LITE
    # tier would otherwise make unsafe to ship money/auth code through on self-review alone.
    if card_high_risk(data) and fcp_required not in ("yes", "true"):
        findings.append(("P0", loc,
            "card_high_risk (security_tripwire touches money/auth/secrets/PII/destructive) but "
            "foundation_checkpoint_required is not 'yes' — a high-risk card MECHANICALLY requires "
            "the foundation checkpoint + full cross-family review regardless of self-declaration "
            "or project risk tier (CARD-HIGH-RISK-FORCES-FOUNDATION, PBF-PROP-019)"))
        fcp_required = "yes"  # treat as forced-yes so the reason requirement below still applies

    if fcp_required in ("yes", "true"):
        fcp_reason = data.get("foundation_checkpoint_reason", "")
        if not fcp_reason or str(fcp_reason).strip() == "":
            findings.append(("P1", loc,
                "foundation_checkpoint_required: yes but foundation_checkpoint_reason is empty — must explain why"))
        # PB-PROP-002(b): the foundation card itself does NOT self-block on its own
        # checkpoint. Recording the checkpoint as PASSED can only happen AFTER the
        # card is built + xfam-reviewed, so self-blocking is a chicken-and-egg that
        # the foundation card can never escape. Per GATES.md:48 the checkpoint blocks
        # every DEPENDENT card until it passes, NOT the foundation card itself — and
        # that dependent-blocking is enforced just below via
        # source_map.dependency_capsules. (Implementation had drifted from canon.)

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

    # --- execution block: BUILD-ENGINE-PROFILES enforcement (PBF-PROP-008, clauses 1-5) ---
    _check_execution(data, args, loc, findings)

    # --- review_dispatch: three-leg ask on review/audit cards (PBF-PROP-009) ---
    _check_review_dispatch(data, loc, findings)

    # --- CodeRabbit rail on every code-diff build card (PROP-042 / v1.21; PBF-PROP-019 tier-gated) ---
    _check_coderabbit_required_for_code_diff(data, loc, findings, risk_tier_val)
    _check_prevention_preamble(data, loc, findings)

    # --- ui_contract + fixture_replacement_map + visual_contract_context (B-PROP-003) ---
    _check_ui_contract(data, args, loc, findings)

    # --- PROTOCOL_INCIDENT gate: blocks new build/cross-family while open (BF-PROP-002) ---
    _check_incident_gate(data, args, loc, findings)

    # --- BF-PROP-007 Lever A: re-anchor-before-fix on mode: FIX cards ---
    _check_lock_fidelity(data, args, loc, findings)

    # --- F-PROP-001 Lever B/E: anti-amnesia file-backed questions + revert-on-drift honesty (mode: FIX) ---
    _check_fix_amnesia(data, args, loc, findings)
    _check_fix_revert(data, loc, findings)

    # --- F-PROP-001 Lever C: per-target cross-lock taxonomy (mode: FIX) ---
    _check_fix_targets(data, loc, findings)

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

        # PBF-PROP-019 Phase 3 (design v2.B ceremony row 2): a LITE-tier project relaxes the
        # per-module cross-family review floor to self-review only — UNLESS the card is high-risk,
        # in which case the Phase-2 mechanical force (CARD-HIGH-RISK-FORCES-FOUNDATION, checked
        # above via foundation_checkpoint_required) already requires full cross-family review and
        # this relaxation MUST NOT override it. STANDARD/STRICT are unchanged from today.
        lite_self_review_ok = risk_tier_val == "LITE" and not card_high_risk(data)

        if exec_family and cross_family:
            same_family = exec_family.lower() == cross_family.lower()
            if same_family:
                if lite_self_review_ok:
                    pass  # LITE, not high-risk: same-family (self) review is legitimate — no IOU needed
                else:
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
            if not lite_self_review_ok:
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

    # --- PBF-PROP-018: preserve-posture gate (compile-time bite) ---
    # Opt-in on --repo-root (a card check with no repo context cannot resolve the accepted-surface
    # manifests directory); the build-turn rail runs it unconditionally so the gate is never
    # skippable on the normal build path.
    repo_root = getattr(args, "repo_root", None)
    if repo_root:
        from cx_accepted_surface import run_accepted_surface_checks
        findings.extend(run_accepted_surface_checks(data, loc, repo_root=repo_root))

    return findings_report(findings)
