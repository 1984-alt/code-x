# Code-X in 10 minutes

> A companion to the [README](README.md). The README explains *what* Code-X is and *why*.
> This gets it onto your machine and shows it actually catching a dropped requirement —
> the exact failure it exists to prevent — in about ten minutes.
>
> New to the words (packet, card, gate, cross-family)? Keep the
> [Rosetta glossary](ROSETTA.md) open alongside this. Nothing here needs you to read code.

**What you'll have at the end:** the `cx` checker proving itself on your machine, Code-X
installed into your AI tool, and a first project started the Code-X way.

---

## Before you start (2 minutes)

You need four things. Most machines already have the first two.

- **Python 3.10 or newer** — `python3 --version` should print 3.10+.
  (On macOS the built-in `/usr/bin/python3` may be older; if so, install a newer one from
  [python.org](https://www.python.org/downloads/) or Homebrew.)
- **git** — `git --version` should print something.
- **PyYAML** — the one library the checker needs: `pip3 install pyyaml`
- **An AI engine** — [Claude Code](https://claude.com/claude-code) or the `codex` CLI.
  This is the tool Code-X plugs into.

---

## Step 1 — See the checker actually work (3 minutes, no account needed)

This is the fastest way to watch Code-X do its job. You clone the repo at a pinned release,
run its self-tests, then run a tiny worked example where the checker **catches a requirement
that was silently dropped**.

First, clone the repo and pin it to a known-good release:

```bash
git clone https://github.com/1984-alt/code-x.git
cd code-x                    # ← you are now at the REPO ROOT
git checkout v1.22.4        # pin to a known-good release, not the moving main branch
```

The `cx` checker lives inside the plugin's skill folder. Step into it to run the
self-tests:

```bash
cd plugins/code-x/skills/code-x        # ← from the repo root, into the skill folder

python3 checkers/tests/run.py          # self-tests: prove the checker works on your machine
python3 checkers/cx --version          # should print: cx — Code-X V1.22.4
```

Now the worked example — a tiny "tip-split" project. It lives at the **repo root**, not in
the skill folder, so step back up first:

```bash
cd ../../../..                         # ← back to the repo root (up 4 levels)
bash examples/tip-split/run.sh
```

What you just saw: a clean card deck passes `cx check deck`. Then the script drops one
requirement's card and runs the check again — and `cx` flags it as a **`[P0]`** (a
blocker). That is the whole point of Code-X in one command: a requirement that vanished
when the plan became build tasks gets caught mechanically, not months later in production.

The captured output of both runs is saved under `examples/tip-split/receipts/` (also at the
repo root), so you can re-read the result any time without running anything.

> **Why this matters:** `cx` is plain, deterministic Python — not an AI grading another AI.
> A non-coder can run it and read the result. That's the layer you can trust without
> reading a line of code.

---

## Step 2 — Install Code-X into your AI (3 minutes)

Step 1 proved the checker. Now install Code-X as a plugin so your AI tool actually *works
inside the protocol* — plan first, build one card at a time, run the gates for you.

**Recommended: download, verify, then run.** You fetch the installer from an exact pinned
release (never the moving `main` branch), check it against the checksum published on that
release's page, and only then run it:

```bash
CX_TAG=v1.22.4

curl -fsSL "https://raw.githubusercontent.com/1984-alt/code-x/${CX_TAG}/installer/install.sh" -o install.sh
echo "<sha256-from-the-v1.22.4-GitHub-Release-notes>  install.sh" | shasum -a 256 -c -
bash install.sh
```

If the checksum line does **not** print `install.sh: OK`, stop — do not run the script.
Get the checksum from the "Assets" section of the
[v1.22.4 release page](https://github.com/1984-alt/code-x/releases) itself.

**Convenience one-liner** (same pinned release, skips the manual checksum step — you're
trusting curl's secure connection to GitHub instead of a checksum you verified yourself):

```bash
curl -fsSL https://raw.githubusercontent.com/1984-alt/code-x/v1.22.4/installer/install.sh | bash
```

What the installer does, in plain English:

1. **Checks your machine** — Python 3.10+, git, the Claude Code CLI. If something's missing
   it tells you exactly what to install and stops (it never guesses).
2. **Installs Code-X and superpowers** — both pinned to an exact, checked release, so you
   get a known-good version, not whatever's at the tip of a branch.
3. **Offers CodeRabbit** — an optional outside code-review service; the installer only
   prints the official link, it never installs it for you.
4. **Shows a pass/fail table** so you see exactly what worked, with a plain fix for anything
   that didn't.

Safe to run more than once — it leaves correct installs alone and finishes half-done ones.

**Prefer to click, or on Codex?** Every step above has a manual equivalent — see the
README's *Install Code-X (manual / Codex)* section.

---

## Step 3 — Start your first project (1 minute)

Open a fresh session in your AI tool and start with a plain sentence naming what you want
**+ Code-X**:

> "Plan a new app called [name] with Code-X."

A session-start hook (on by default) loads Code-X automatically, so the AI begins inside
the plan-then-build workflow. From here you're the director:

1. **Planning is your highest-leverage work.** Push until requirements, screens, flows,
   edge cases, and money rules are concrete — don't let building start while the plan still
   feels vague or not truly yours.
2. **Review the Master Blueprint** — the single generated page that shows what the finished
   app will look like, screen by screen — before any code is built.
3. **Approve module by module.** During building, the AI demos each finished piece and
   waits for your OK before the next.

> **The one rule above all: never build before the plan is locked and verified.** Every
> question you resolve in planning is friction you won't hit while building.

---

## Where to go next

- **[START-HERE.md](plugins/code-x/skills/code-x/START-HERE.md)** — the map of the whole protocol.
- **[OPERATING-MODES.md](OPERATING-MODES.md)** — how the author actually drives it
  day-to-day: which engine for planning vs building, context-window habits, clean handoffs.
- **[ROSETTA.md](ROSETTA.md)** — every Code-X word translated to plain English.
- **README "How the trust holds"** — the honest account of what Code-X proves and what it
  can't.

---

*Draft for CEO review. Flags to check:*
- *`cx --version` output — I wrote the expected line as `cx — Code-X V1.22.4` (extrapolated
  from the private checker printing `cx — Code-X V1.22.2` at that version). Confirm the
  public v1.22.4 checker formats it exactly this way.*
- *Clone paths — verified against the repo layout: the `cx` self-tests run from
  `plugins/code-x/skills/code-x`, and tip-split lives at the REPO ROOT
  (`examples/tip-split/run.sh`, receipts alongside). Step 1 now returns to the root
  (`cd ../../../..`) before the tip-split demo, with the working directory shown at each
  command block.*
- *`cx` on PATH — I deliberately used `python3 checkers/cx` (the README's pattern) rather
  than a bare `cx`, since a plain `cx` command isn't guaranteed on a new user's shell.
  Confirm that's the right call for the public repo.*
- *Ordering — I put "see the checker work" (clone) BEFORE "install the plugin," because the
  clone demo is the fastest, account-free proof. If you'd rather lead with the plugin
  install, the two blocks swap cleanly.*
- *Checksum placeholder — `<sha256-from-the-v1.22.4-GitHub-Release-notes>` is copied
  verbatim from the install source doc; it gets filled at release time.*
