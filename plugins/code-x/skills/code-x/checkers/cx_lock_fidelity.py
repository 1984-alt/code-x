# cx_lock_fidelity.py — shared lock-fidelity-continuity helpers (BF-PROP-007, fold v1.15).
#
# This module is the single source of truth for the RECOMPUTE-from-files primitives Levers
# A/B/C all share. NOTHING here trusts a model-authored copy — every value is recomputed
# from the frozen packet on disk + the live state, so a self-declared hash or a vacuous
# open_cards: [] cannot pass (the two forgeries the proposal review flagged).
#
# Reuse (no new machinery): the packet hash recipe is cx_deck._compute_packet_hash; the frozen
# requirement set is the deck's requirements-manifest; the canonical open-card set is derived
# from the frozen <packet_dir>/MODULE-REGISTRY.yaml (module_id -> card_ids) intersected with the
# live state.accepted_modules. Path-safety reuses the v1.10 helper shape (no absolute / no '..').
#
# OPEN-CARD DERIVATION RULE (the implementable authoritative choice — documented per CX-CHECK-SPEC):
#   open_card  := a compiled card_id named by a frozen-registry module whose module_id is NOT
#                 present in state.accepted_modules.
#   open_cards := sorted(set) of those card_ids across every not-yet-accepted module.
# Why this rule: the data model that is BOTH frozen (hash-bound, unforgeable) AND carries the
# card<->module mapping is <packet_dir>/MODULE-REGISTRY.yaml; state.accepted_modules is the only
# live "what has shipped" signal that is itself sha-bound (the Andon wall). A card's "status" in a
# loose card file is model-authored and NOT frozen, so it is deliberately NOT the derivation input.
# Honest limit: a card whose module is accepted is treated as closed even if a later fix re-opened
# it — re-opening a shipped module is its own typed event (a FIX card + lock_deviation), not a deck
# fact, so this derivation does not claim to model mid-flight re-openings of accepted modules.

import os
from pathlib import Path

from cx_common import load_yaml, nested_get
from cx_deck import _compute_packet_hash


def path_is_unsafe(rel: str) -> bool:
    """True if rel is absolute or contains a '..' component (reuses the v1.10 path-safety shape).
    A model-authored ref must be a repo-relative in-tree path; anything else is rejected closed."""
    p = Path(str(rel))
    return p.is_absolute() or ".." in p.parts


def resolve_in_repo(repo_root: str, rel: str) -> tuple[Path | None, str | None]:
    """Resolve a model-authored repo-relative path under repo_root, rejecting absolute paths,
    '..' escapes, symlinks, and any target that resolves OUTSIDE repo_root. Returns
    (resolved_path, error) — error is a human string when the path is unsafe (fail closed)."""
    if path_is_unsafe(rel):
        return None, f"'{rel}' must be a repo-relative path (no absolute path / '..' escape)"
    base = Path(repo_root).resolve()
    cand = base / rel
    if cand.is_symlink():
        return None, f"'{rel}' is a symlink — the frozen packet must be a real in-tree file"
    resolved = cand.resolve()
    if not (resolved == base or str(resolved).startswith(str(base) + os.sep)):
        return None, f"'{rel}' resolves OUTSIDE the repo root — rejected"
    return resolved, None


def recompute_frozen_packet_hash(repo_root: str, packet_dir_rel: str) -> tuple[str | None, str | None]:
    """RECOMPUTE the frozen packet hash from the packet body on disk (never trust a copy).
    packet_dir_rel = state.packet_dir (repo-relative). Returns (hash, error)."""
    if not packet_dir_rel:
        return None, "state.packet_dir is absent — no frozen packet to anchor against (fail closed)"
    resolved, perr = resolve_in_repo(repo_root, packet_dir_rel)
    if perr:
        return None, f"packet_dir {perr}"
    if not resolved.is_dir():
        return None, f"packet_dir '{packet_dir_rel}' is not a directory under the repo"
    try:
        return _compute_packet_hash(resolved), None
    except Exception as e:  # symlink-in-packet etc. — fail closed
        return None, f"could not hash packet '{packet_dir_rel}': {e}"


def _frozen_manifest_ids(packet_dir: Path) -> tuple[dict, str | None]:
    """Load the frozen requirements-manifest inside packet_dir. Returns ({req_id: disposition}, err)."""
    manifest_path = packet_dir / "requirements-manifest.yaml"
    data, err = load_yaml(str(manifest_path))
    if err or not isinstance(data, dict):
        return {}, f"requirements-manifest unreadable in packet: {err or 'not a mapping'}"
    rows = data.get("requirements")
    if not isinstance(rows, list):
        return {}, "requirements-manifest has no 'requirements' list"
    ids = {}
    for row in rows:
        if isinstance(row, dict) and row.get("id"):
            ids[str(row["id"])] = str(row.get("disposition", ""))
    return ids, None


def _frozen_registry(packet_dir: Path) -> tuple[dict, str | None]:
    """Load the frozen MODULE-REGISTRY inside packet_dir. Returns ({module_id: [card_ids]}, err).

    FAIL-CLOSED with the SAME integrity bar as the v1.10 order wall (cx_module_start) — F5. Silently
    skipping a malformed row or overwriting a duplicate module_id would HIDE cards from the derived
    open set (a dropped row vanishes a prior; a dup lets one row's card_ids shadow another's), which
    is exactly the P0-class ambiguity the order wall rejects. So this rejects: a symlinked registry
    file, a non-mapping/blank-module_id row, a non-list card_ids, a duplicate module_id, and a
    dependency_modules naming an unregistered module. Any of these returns an error → callers fail
    closed (open_cards cannot be derived, never a vacuous pass)."""
    reg_path = packet_dir / "MODULE-REGISTRY.yaml"
    if reg_path.is_symlink():
        return {}, ("MODULE-REGISTRY.yaml is a symlink — a frozen registry must be a real in-tree "
                    "file, not a pointer to arbitrary bytes (V1.10 R4 / F5)")
    data, err = load_yaml(str(reg_path))
    if err or not isinstance(data, dict):
        return {}, f"MODULE-REGISTRY unreadable in packet: {err or 'not a mapping'}"
    mr = data.get("module_registry")
    modules = (mr.get("modules") if isinstance(mr, dict) else None) or []
    if not isinstance(modules, list):
        return {}, "MODULE-REGISTRY.module_registry.modules is not a list"
    by_module = {}
    deps = {}
    for i, m in enumerate(modules):
        if not isinstance(m, dict):
            return {}, (f"MODULE-REGISTRY.modules[{i}] is not a mapping — a malformed row would be "
                        "silently dropped, hiding a module's cards from the open set (V1.10 R4 / F5)")
        raw_mid = m.get("module_id", None)
        if not isinstance(raw_mid, str) or not raw_mid.strip():
            return {}, (f"MODULE-REGISTRY.modules[{i}] has a missing/blank/non-string module_id — "
                        "every row must name its module (V1.10 R4 / F5)")
        mid = raw_mid.strip()
        if mid in by_module:
            return {}, (f"MODULE-REGISTRY has a duplicate module_id '{mid}' — a duplicate lets one "
                        "row's card_ids shadow another's, hiding cards from the open set; module "
                        "identity must be unambiguous (V1.10 R4 / F5)")
        cards = m.get("card_ids") or []
        if not isinstance(cards, list):
            return {}, (f"MODULE-REGISTRY.modules[{i}] ('{mid}') card_ids is not a list — malformed "
                        "card_ids cannot define the open set (V1.10 R4 / F5)")
        raw_deps = m.get("dependency_modules", []) or []
        if not isinstance(raw_deps, list):
            return {}, (f"MODULE-REGISTRY.modules[{i}] ('{mid}') dependency_modules is not a list "
                        "(V1.10 R4 / F5)")
        by_module[mid] = [str(c) for c in cards if c]
        deps[mid] = [str(d).strip() for d in raw_deps if str(d).strip()]
    unknown_deps = sorted({d for ds in deps.values() for d in ds if d not in by_module})
    if unknown_deps:
        return {}, (f"MODULE-REGISTRY dependency_modules reference unregistered module_id(s): "
                    f"{unknown_deps} — every dependency must be a registered module (V1.10 R4 / F5)")
    return by_module, None


def accepted_module_ids(state: dict) -> set:
    """The RAW set of module_ids the live state CLAIMS as accepted. NOTE: a raw id here is
    model-authored — it is NOT proof of a bound acceptance receipt. Use verified_accepted_module_ids()
    for any fail-closed derivation (recompute_open_cards / drift); this raw view is kept only for
    callers that already validate the receipt themselves."""
    out = set()
    for m in (state.get("accepted_modules") or []) if isinstance(state, dict) else []:
        if isinstance(m, dict) and str(m.get("module_id", "")).strip():
            out.add(str(m["module_id"]).strip())
    return out


def verified_accepted_module_ids(state: dict, state_loc: str, repo_root: str) -> set:
    """The set of module_ids that are VALIDLY accepted — i.e. validate_accepted_module() returns NO
    findings for them (a bound, sha-verified, in-repo acceptance receipt). A hand-authored
    accepted_modules row with no real receipt is therefore NOT treated as closed: its cards stay OPEN.
    This closes the F4 bypass where any row with a module_id made open_cards: [] verify (BF-PROP-007 xfam).
    Imported lazily to avoid a module-import cycle (cx_module_acceptance imports cx_drift→cx_lock_fidelity)."""
    from cx_module_acceptance import validate_accepted_module
    out = set()
    for mid in accepted_module_ids(state):
        if not validate_accepted_module(mid, state, state_loc, repo_root=repo_root):
            out.add(mid)
    return out


def recompute_open_cards(repo_root: str, packet_dir_rel: str, state: dict,
                         state_loc: str | None = None) -> tuple[list | None, str | None]:
    """RECOMPUTE the canonical open-card set from the frozen registry + live state.
    open_cards = sorted set of card_ids from frozen-registry modules whose acceptance is NOT
    receipt-VERIFIED (a module counts as closed ONLY when validate_accepted_module() passes for it —
    a bound, sha-verified, in-repo receipt). A hand-authored accepted_modules row with no real receipt
    leaves its cards OPEN (BF-PROP-007 xfam F4). Returns (sorted_list, error). An EMPTY list is legal only
    when every registry module is genuinely receipt-verified-accepted."""
    if not packet_dir_rel:
        return None, "state.packet_dir is absent — cannot derive the open-card set (fail closed)"
    resolved, perr = resolve_in_repo(repo_root, packet_dir_rel)
    if perr:
        return None, f"packet_dir {perr}"
    if not resolved.is_dir():
        return None, f"packet_dir '{packet_dir_rel}' is not a directory under the repo"
    by_module, rerr = _frozen_registry(resolved)
    if rerr:
        return None, rerr
    accepted = verified_accepted_module_ids(state, state_loc or str(resolved.parent), repo_root)
    open_set = set()
    for mid, cards in by_module.items():
        if mid not in accepted:
            open_set.update(cards)
    return sorted(open_set), None


def frozen_requirement_ids(repo_root: str, packet_dir_rel: str) -> tuple[dict | None, str | None]:
    """RECOMPUTE {req_id: disposition} from the frozen requirements-manifest. (hash, err)."""
    resolved, perr = resolve_in_repo(repo_root, packet_dir_rel)
    if perr:
        return None, f"packet_dir {perr}"
    if not resolved.is_dir():
        return None, f"packet_dir '{packet_dir_rel}' is not a directory under the repo"
    ids, merr = _frozen_manifest_ids(resolved)
    if merr:
        return None, merr
    return ids, None


def card_requirement_ids(card: dict) -> set:
    """Every requirement_id a card declares coverage of (source_map.source_sections[].requirement_ids)
    plus its lock_anchor_ref.requirement_id if present. Mirrors cx_deck._collect_card_data."""
    ids = set()
    sections = nested_get(card, "source_map", "source_sections") or []
    if isinstance(sections, list):
        for sec in sections:
            if isinstance(sec, dict):
                rids = sec.get("requirement_ids") or []
                if isinstance(rids, list):
                    ids.update(str(r) for r in rids if r)
    anchor = card.get("lock_anchor_ref")
    if isinstance(anchor, dict) and anchor.get("requirement_id"):
        ids.add(str(anchor["requirement_id"]))
    return ids


# Lever A — fix-card deviation_class machinery.
VALID_DEVIATION_CLASSES = {"RESTORE", "AMBIGUITY_RESOLVED", "SCOPE_CHANGE"}
# Risk classes that escalate an unauthorized SCOPE_CHANGE to P0 (per SEVERITY.md; xfam FIX #5).
HIGH_RISK_CLASSES = {"money", "auth", "shared-data-shape", "secrets", "destructive"}


def card_high_risk(card: dict) -> bool:
    """True if the card's security_tripwire marks a high-risk surface — used to escalate an
    unauthorized SCOPE_CHANGE from the P1 default to P0 (the only P0 path per SEVERITY.md).
    F3: covers ALL high-risk classes the card tripwire can express — money (touches_money_or_balances),
    auth (touches_auth), secrets (touches_secrets), shared-data-shape/PII (touches_bank_or_pii), AND
    destructive/restore-import (touches_upload_restore_import). The OLD set omitted
    touches_upload_restore_import, so a destructive unauthorized scope-change escalated only to P1 —
    the F3 hole."""
    st = card.get("security_tripwire")
    if not isinstance(st, dict):
        return False
    truthy = lambda v: str(v).strip().lower() in ("yes", "true", "1")
    return any(truthy(st.get(k)) for k in (
        "touches_auth", "touches_secrets", "touches_money_or_balances",
        "touches_bank_or_pii", "touches_upload_restore_import"))
