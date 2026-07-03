<!--
  Source for the public repo's README "Get started" section (PBF-PROP-017).
  The public-port session replaces the current `### Install Code-X` +
  `### Prerequisites` steps with this — do NOT edit the release clone
  directly; this file is the port session's source of truth.

  Sequencing note (xfam P1): this section assumes the v1.22.4 public port has
  already landed (or lands in the same PR) — the installer installs THIS
  protocol version, not the stale v1.22.0 the public repo is on today.
-->

### Install Code-X

**Recommended: download, verify, then run.** This never trusts a moving
target — you fetch install.sh from an exact pinned release tag (not the
`main` branch, which can change at any time), check it against the sha256
checksum published in that release's GitHub Release notes, and only then
run it:

```bash
CX_TAG=v1.22.4   # use the tag from the release you're installing

curl -fsSL "https://raw.githubusercontent.com/1984-alt/code-x/${CX_TAG}/installer/install.sh" -o install.sh
echo "<sha256-from-the-v1.22.4-GitHub-Release-notes>  install.sh" | shasum -a 256 -c -
bash install.sh
```

If the checksum line does not print `install.sh: OK`, **stop** — do not run
the script. Get the checksum from the "Assets" section of the
[v1.22.4 release page](https://github.com/1984-alt/code-x/releases) itself,
not from anywhere else.

**Convenience one-liner** (same pinned release tag, still never `main` — but
skips the separate checksum step above, so you are trusting curl's TLS
connection to GitHub instead of a checksum you verified yourself):

```bash
curl -fsSL https://raw.githubusercontent.com/1984-alt/code-x/v1.22.4/installer/install.sh | bash
```

Either way, once install.sh is running it re-verifies everything else it
touches (Code-X, superpowers) against pinned release tags — see "What it
does" below.

What it does, in plain English:

1. **Checks your machine** — Python 3.10+, git, and the Claude Code CLI. If
   anything is missing, it tells you exactly what to install and stops there
   (it never guesses or installs something it can't verify).
2. **Installs Code-X and superpowers** — both pulled directly from their own
   GitHub repositories, pinned to an exact, checked release so you always get
   a known-good version, not whatever happens to be at the tip of a branch.
3. **Offers CodeRabbit** — an optional, separate code-review service used
   alongside Code-X's own review flow. It needs its own account, so the
   installer only prints the official install link — it never installs or
   configures CodeRabbit for you.
4. **Shows you a pass/fail table** so you can see exactly what worked, with a
   plain-English fix for anything that didn't.

Safe to run more than once — if something is already installed correctly,
the installer leaves it alone; if something is half-installed, it finishes
the job.

Prefer to see each step yourself, or on Codex? Use the manual steps below.

### Install Code-X (manual / Codex)

<details>
<summary>Prerequisites</summary>

**1. Python 3 + PyYAML** (pinned + hash-verified — same as the installer does;
never a bare `pip install`, which would trust whatever PyPI serves):

```bash
pip3 install --no-binary :all: --require-hashes \
  -r <(printf 'pyyaml==6.0.3 --hash=sha256:d76623373421df22fb4cf8817020cbb7ef15c725b9d5e45f17e189bfc384190f\n')
```

(If your shell doesn't support `<(...)`, write that one line to a file first
and pass it with `-r <file>`.) The pin + hash mirror `install.sh`'s
`PYYAML_PIN` / `PYYAML_SHA256` — update all three together if PyYAML moves.

**2. superpowers** ([obra/superpowers](https://github.com/obra/superpowers)) —
pinned to the SAME release the one-line installer uses (`v6.1.1` from
obra/superpowers, whose marketplace declares the name `superpowers-dev`), so
the manual path and the installer agree:

- **Claude Code:**
  ```
  /plugin marketplace add https://github.com/obra/superpowers.git#v6.1.1
  /plugin install superpowers@superpowers-dev
  ```
- **Codex:**
  ```bash
  codex plugin marketplace add https://github.com/obra/superpowers.git#v6.1.1
  codex plugin add superpowers@superpowers-dev
  ```

**3. CodeRabbit** (optional, third-party — works with Code-X, not included):

- **Claude Code:** `/plugin install coderabbit@claude-plugins-official`
- **Codex:** open a `codex` session, run `/plugins`, find **CodeRabbit**, Install

**4. frontend-design** (Claude Code only):

- **Claude Code:** `/plugin install frontend-design@claude-plugins-official`

</details>

<details>
<summary>Install Code-X itself</summary>

Pin the marketplace to the exact release tag (the full-git-URL + `#<tag>`
form — a bare `1984-alt/code-x` follows the moving default branch):

**Claude Code:**

```
/plugin marketplace add https://github.com/1984-alt/code-x.git#v1.22.4
/plugin install code-x@code-x
```

**Codex:**

```bash
codex plugin marketplace add https://github.com/1984-alt/code-x.git#v1.22.4
codex plugin add code-x@code-x
```

</details>

Then open a new session and start with: *"Let's start a new project with
Code-X."*
