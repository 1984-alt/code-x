# cmd_module_start: the ORDER WALL (V1.10 module_acceptance gate family).
#
# A module-advancing build card (MODULE_BUILD / MODE_A_UI) may start ONLY when:
#   0. the card content-binds to the frozen packet: re-hashing --packet-dir (which CONTAINS the
#      module registry + manifest) equals the card's source_map.locked_packet_hash, AND the order is
#      read ONLY from the canonical <packet-dir>/MODULE-REGISTRY.yaml (V1.10 R4 — content-deep, not
#      string-deep; closes the trimmed-registry-with-stale-hash-string bypass AND the
#      alternate-in-packet-registry bypass),
#   1. its module_id is present in the frozen module_registry (no out-of-registry card), and
#   2. every PRIOR REQUIRED module is already `accepted` in state — where "prior required" =
#      the card module's explicit dependency_modules PLUS every module ordered before it in the
#      registry (the locked-plan order is itself a dependency: no silently skipping an earlier
#      module — closes the omit-a-module hole).
#
#   cx check module-start <card> --packet-dir <frozen-packet-dir> --registry <packet-dir>/MODULE-REGISTRY.yaml \
#       --state <CODE-X-STATE.yaml> --repo-root <dir>
# --repo-root is REQUIRED for a module-advancing card (fail-closed): it bounds the symlinked-ancestor
# check to the repo and anchors prior-module acceptance resolution.
#
# Each prior required module is re-validated through the SHARED acceptance validator
# (validate_accepted_module) — the wall NEVER trusts the accepted-module id set, so a hand-authored
# `accepted` entry with no bound receipt cannot unlock the next module (closes the bypass GPT flagged).
#
# READ-ONLY: never builds, routes actors, edits source, or creates evidence (CHARTER §4).
import os
from pathlib import Path

from cx_common import findings_report, load_yaml, nested_get
from cx_deck import _compute_packet_hash
from cx_module_acceptance import has_blocking, validate_accepted_module

BUILD_MODES = {"MODULE_BUILD", "MODE_A_UI"}


def _symlink_in_path_chain(repo_root, packet_dir):
    """When --repo-root is given, return an error string if ANY path component from repo_root
    (exclusive) down to packet_dir (inclusive) is a symlink — else None. Bounds the check to inside
    the repo so an unrelated symlink ABOVE the repo (e.g. macOS /tmp -> /private/tmp) is never
    flagged. Closes the symlinked-ANCESTOR vector (GPT R7): repo/link/packet where 'link' is a
    symlink to outside the repo (the packet's own dir + subtree are clean, so the under-packet guard
    misses it). The build rail (build-turn) always passes --repo-root, so this covers enforcement."""
    if not repo_root:
        return None
    root = Path(os.path.abspath(repo_root))
    target = Path(os.path.abspath(packet_dir))
    try:
        rel = target.relative_to(root)
    except ValueError:
        return (f"--packet-dir '{packet_dir}' is not under --repo-root '{repo_root}' — the frozen "
                "packet must live inside the repo (V1.10)")
    cur = root
    for part in rel.parts:
        cur = cur / part
        if cur.is_symlink():
            return (f"path component '{cur}' is a symlink — no symlink may appear between the repo "
                    "root and the frozen packet; it would point the packet at content OUTSIDE the "
                    "repo (V1.10 R4)")
    return None

# The module order is read ONLY from this canonical file at the TOP of the frozen packet. Binding the
# registry IDENTITY (not just "some registry inside the packet") closes the GPT R4 P0: a packet may
# legitimately contain other registry-shaped files, and a model-authored --registry could otherwise
# select a trimmed sibling to skip the order. (Mirrors the deck's canonical requirements-manifest.yaml.)
CANONICAL_REGISTRY_NAME = "MODULE-REGISTRY.yaml"


def cmd_module_start(args) -> int:
    card_path = args.card
    findings = []

    card, cerr = load_yaml(card_path)
    if cerr:
        print(f"FIX-FIRST\n  [P0] {card_path} — {cerr}")
        return 1
    if not isinstance(card, dict):
        print(f"FIX-FIRST\n  [P0] {card_path} — not a YAML mapping")
        return 1

    loc = card_path
    mode = str(card.get("mode", "") or "").strip()
    module_id = str(card.get("module_id", "") or "").strip()

    # Only module-advancing build cards are gated by the order wall.
    if mode not in BUILD_MODES:
        print("PASS")
        print(f"  [INFO] {loc} — mode {mode or 'UNSET'} is not a module-advancing card; order wall N/A")
        return 0

    if not module_id:
        findings.append(("P0", loc,
            f"mode {mode} card carries no module_id — a module-advancing card must name the "
            "frozen module_registry module it builds so the order wall can gate it (V1.10)"))
        return findings_report(findings)

    # --repo-root is REQUIRED for a module-advancing card (fail-closed; the build rail always passes
    # it). Without it the order wall cannot bound the symlinked-ancestor check to the repo, so a
    # symlinked ANCESTOR of the packet would be an opt-out bypass (GPT R8). It also anchors prior
    # modules' acceptance-receipt resolution.
    repo_root = getattr(args, "repo_root", None)
    if not repo_root:
        findings.append(("P0", loc,
            "--repo-root required — the order wall verifies no symlink lies between the repo root and "
            "the frozen packet (a symlinked ancestor would point the packet outside the repo); without "
            "a repo root that check cannot run (fail-closed) (V1.10 R4)"))
        return findings_report(findings)

    # ── CONTENT-DEEP packet binding (V1.10 R4 — closes the R3 open P0) ──────────────────────
    # Earlier folds bound the registry to the card by comparing two FILE-AUTHORED hash STRINGS
    # (registry.frozen_packet_hash == card.locked_packet_hash). That is bypassable: a trimmed
    # registry (a prior module deleted) that keeps the same frozen_packet_hash string passes.
    # The fix re-hashes real bytes. The frozen packet dir CONTAINS the module registry + the
    # requirements manifest; the card's locked_packet_hash is the sha256 over that whole dir
    # (the deck's _compute_packet_hash — same recipe cx check deck uses). Re-hash the packet on
    # disk and require it equals the card's frozen hash: trimming the in-packet registry changes
    # the recompute, so the doctored registry no longer slips through.
    # (NOTE: requiring recompute == registry.frozen_packet_hash too is impossible — a registry
    # inside the packet cannot store the hash of the packet that contains it (self-reference).
    # Content-binding to the card's hash + requiring the registry live inside the packet, below,
    # is strictly STRONGER than the old string equality.)
    packet_dir = getattr(args, "packet_dir", None)
    if not packet_dir:
        findings.append(("P0", loc,
            "--packet-dir required — the order wall content-binds the card to the frozen packet: it "
            "re-hashes the packet dir (which CONTAINS the module registry) and requires it equals the "
            "card's locked_packet_hash. Without it a trimmed registry keeping a stale "
            "frozen_packet_hash string would slip through (fail-closed) (V1.10)"))
        return findings_report(findings)
    # Reject '..' in --packet-dir BEFORE any filesystem access (build-turn already forbids it in
    # state.packet_dir). os.path.abspath would lexically collapse 'link/..' to a sibling, hiding a
    # symlinked 'link' from the ancestor chain check while the real fs follows it outside the repo
    # (GPT R9). No '..' means the chain check sees every component that the fs will traverse.
    if ".." in Path(packet_dir).parts:
        findings.append(("P0", str(packet_dir),
            f"--packet-dir '{packet_dir}' contains a '..' component — parent-traversal can hide a "
            "symlinked ancestor from the path-chain check (lexical collapse) while the filesystem "
            "follows it OUTSIDE the repo; a frozen packet path must have no '..' (V1.10 R4)"))
        return findings_report(findings)
    pkt = Path(packet_dir)
    if pkt.is_symlink():
        findings.append(("P0", str(packet_dir),
            f"--packet-dir '{packet_dir}' is a symlink — a frozen packet must be a real, "
            "self-contained directory; a symlinked packet root resolves to bytes OUTSIDE the "
            "intended packet (V1.10)"))
        return findings_report(findings)
    if not pkt.is_dir():
        findings.append(("P0", str(packet_dir),
            f"--packet-dir '{packet_dir}' is not a directory — the order wall cannot recompute the "
            "frozen packet hash (V1.10)"))
        return findings_report(findings)
    # Reject a symlink in the path chain between the repo root and the packet (when --repo-root is
    # given — the build rail always passes it). A clean packet subtree + root is not enough if an
    # ANCESTOR directory is a symlink pointing outside the repo (GPT R7).
    chain_err = _symlink_in_path_chain(repo_root, packet_dir)
    if chain_err:
        findings.append(("P0", str(packet_dir), chain_err))
        return findings_report(findings)
    card_pkt = str(nested_get(card, "source_map", "locked_packet_hash") or "").strip()
    if not card_pkt:
        findings.append(("P0", loc,
            "card source_map.locked_packet_hash missing — a module-advancing card must bind to the "
            "frozen packet so the order wall can content-verify it (V1.10)"))
        return findings_report(findings)
    try:
        real_hash = _compute_packet_hash(pkt)
    except Exception as e:
        findings.append(("P0", str(packet_dir),
            f"could not recompute packet hash from '{packet_dir}': {e} (V1.10)"))
        return findings_report(findings)
    if real_hash != card_pkt:
        findings.append(("P0", loc,
            f"packet content mismatch: card locked_packet_hash {card_pkt} != recomputed packet hash "
            f"{real_hash} — the frozen packet (which CONTAINS the module registry) was edited after "
            "this card was frozen (e.g. a module trimmed from the registry). The order wall reads only "
            "the packet the card was frozen against (V1.10)"))
        return findings_report(findings)

    # The order is read ONLY from the CANONICAL registry at the top of the content-verified packet:
    # <packet-dir>/MODULE-REGISTRY.yaml. Binding the registry IDENTITY (not merely "some registry
    # inside the packet") closes the GPT R4 P0 — a packet may legitimately contain other
    # registry-shaped files, and an inside-packet but NON-canonical --registry could otherwise select a
    # trimmed sibling to skip the order. --registry, if given, MUST resolve to that canonical path.
    canonical = pkt / CANONICAL_REGISTRY_NAME
    try:
        canonical_resolved = canonical.resolve()
    except OSError as e:
        findings.append(("P0", str(canonical),
            f"could not resolve canonical registry path: {e} (V1.10)"))
        return findings_report(findings)
    registry_arg = getattr(args, "registry", None)
    if registry_arg is not None:
        try:
            arg_resolved = Path(registry_arg).resolve()
        except OSError as e:
            findings.append(("P0", str(registry_arg),
                f"could not resolve --registry path: {e} (V1.10)"))
            return findings_report(findings)
        if arg_resolved != canonical_resolved:
            findings.append(("P0", str(registry_arg),
                f"--registry must be the canonical '{CANONICAL_REGISTRY_NAME}' at the top of the frozen "
                f"packet ({canonical}) — the order wall reads the module order ONLY from that file, so an "
                "alternate/trimmed registry (even one committed inside the packet) cannot be selected to "
                "skip the order (V1.10 R4)"))
            return findings_report(findings)
    if not canonical.is_file():
        findings.append(("P0", str(canonical),
            f"frozen packet has no canonical '{CANONICAL_REGISTRY_NAME}' — the order wall reads the "
            "module order from that file; without it there is no frozen registry to gate (V1.10)"))
        return findings_report(findings)
    registry_path = str(canonical)
    registry, rerr = load_yaml(registry_path)
    if rerr:
        print(f"FIX-FIRST\n  [P0] {registry_path} — {rerr}")
        return 1
    mr = nested_get(registry, "module_registry") if isinstance(registry, dict) else None
    modules = mr.get("modules") if isinstance(mr, dict) else (
        registry.get("modules") if isinstance(registry, dict) else None)
    if not isinstance(modules, list) or not modules:
        findings.append(("P0", registry_path,
            "module_registry.modules missing or empty — no module order to enforce (V1.10)"))
        return findings_report(findings)

    # A frozen registry declares it belongs to a packet (presence-only — see the self-reference note
    # above; the real binding is the content hash + the inside-packet check).
    reg_pkt = str((mr.get("frozen_packet_hash") if isinstance(mr, dict) else
                   registry.get("frozen_packet_hash")) or "").strip()
    if not reg_pkt:
        findings.append(("P0", registry_path,
            "module_registry has no frozen_packet_hash — an UNBOUND registry is not frozen; a frozen "
            "registry must declare its packet (V1.10)"))
        return findings_report(findings)

    # Build the ordered id list — FAIL-CLOSED on any malformed row. Silently skipping a bad row would
    # drop a real prior module from the order (a row with no module_id BEFORE m2 would make m2 look
    # prior-less) — GPT R8 P0. Every registry row must be a mapping with a non-blank string module_id
    # and a list dependency_modules.
    ordered_ids = []
    deps = {}
    for i, m in enumerate(modules):
        if not isinstance(m, dict):
            findings.append(("P0", registry_path,
                f"module_registry.modules[{i}] is not a mapping — a malformed registry row would be "
                "silently dropped, vanishing a prior module from the order (V1.10 R4)"))
            return findings_report(findings)
        raw_mid = m.get("module_id", None)
        if not isinstance(raw_mid, str) or not raw_mid.strip():
            findings.append(("P0", registry_path,
                f"module_registry.modules[{i}] has a missing/blank/non-string module_id — every "
                "registry row must name its module so the order wall can gate it (a dropped row "
                "vanishes a prior) (V1.10 R4)"))
            return findings_report(findings)
        raw_deps = m.get("dependency_modules", []) or []
        if not isinstance(raw_deps, list):
            findings.append(("P0", registry_path,
                f"module_registry.modules[{i}] ('{raw_mid.strip()}') dependency_modules is not a list "
                "— malformed dependencies cannot be gated (V1.10 R4)"))
            return findings_report(findings)
        ordered_ids.append(raw_mid.strip())
        deps[raw_mid.strip()] = [str(d).strip() for d in raw_deps]

    # A DUPLICATE module_id lets `ordered_ids.index()` pick the FIRST occurrence and silently drop the
    # priors before a later occurrence — m2,m1,m2 makes a card for m2 see no priors (GPT R7 P0).
    # Module order must be unambiguous: fail-closed on duplicates.
    dupes = sorted({x for x in ordered_ids if ordered_ids.count(x) > 1})
    if dupes:
        findings.append(("P0", registry_path,
            f"duplicate module_id(s) in the registry: {dupes} — a duplicate lets the order wall pick "
            "the first occurrence and skip a real prior module; module order must be unambiguous "
            "(V1.10 R4)"))
        return findings_report(findings)
    # A dependency_modules entry that names a module not in the registry cannot be gated — reject it
    # (registry integrity; fail-closed rather than silently treating it as an always-unmet prior).
    unknown_deps = sorted({d for ds in deps.values() for d in ds if d and d not in ordered_ids})
    if unknown_deps:
        findings.append(("P0", registry_path,
            f"dependency_modules reference module_id(s) not in the registry: {unknown_deps} — every "
            "dependency must be a registered module the order wall can gate (V1.10 R4)"))
        return findings_report(findings)

    if module_id not in ordered_ids:
        findings.append(("P0", loc,
            f"out-of-registry card: module_id '{module_id}' is not in the frozen module_registry "
            f"— it cannot start (known modules: {ordered_ids}) (V1.10)"))
        return findings_report(findings)

    state_path = getattr(args, "state", None)
    if not state_path:
        findings.append(("P0", loc,
            "--state required — the order wall reads state.accepted_modules to verify prior "
            "modules are accepted (V1.10)"))
        return findings_report(findings)
    state, serr = load_yaml(state_path)
    if serr:
        print(f"FIX-FIRST\n  [P0] {state_path} — {serr}")
        return 1
    # repo_root already validated as required + symlink-chain-checked above.

    # prior required = explicit deps ∪ every module ordered before this one (registry order).
    idx = ordered_ids.index(module_id)
    required_prior = set(deps.get(module_id, [])) | set(ordered_ids[:idx])
    # Re-validate EACH prior required module's acceptance receipt — never trust the id set.
    for mid in ordered_ids:
        if mid not in required_prior:
            continue
        prior_findings = validate_accepted_module(mid, state, state_path, repo_root=repo_root)
        # Advisory-only findings (P2/P3, e.g. a legacy_no_baseline migration-debt carve-out) do NOT
        # block the order wall — the prior module IS validly accepted, just with recorded debt
        # (locked spec: legacy_no_baseline is a non-blocking advisory).
        if has_blocking(prior_findings):
            reasons = "; ".join(msg for _, _, msg in prior_findings)
            findings.append(("P0", loc,
                f"prior required module '{mid}' is not validly accepted — module '{module_id}' "
                f"cannot start (order wall, V1.10). Acceptance check: {reasons}"))

    if not findings:
        print("PASS")
        print(f"  [INFO] {loc} — module '{module_id}' authorized to start "
              f"(prior required {sorted(required_prior)} all validly accepted)")
        return 0
    return findings_report(findings)
