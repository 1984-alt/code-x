# Contributing to Code-X

I'm a non-coder. Expert pushback is the point.

Code-X was built by someone who can't read code fluently — using AI to build the code, then building rules and checks to make the AI more trustworthy. That means there are almost certainly places where the approach is naive, insecure, over-engineered, or reinventing something that already exists. Issues and PRs that surface those problems are the most valuable contribution this project can receive.

---

## What feedback is most useful

**Design flaws** — does the three-stage planning → building → fixing flow make sense as described? Is the gate structure logically coherent? Does cross-family review (having a second AI family review the first's output) actually catch the things it claims to? Where is the reasoning broken?

**Security gaps** — the protocol was shaped by a non-coder; its security thinking was influenced by what could be learned, not by formal training. If you see naive assumptions, missing threat models, or patterns that look safe but aren't, please say so plainly.

**Simpler existing tools** — if something Code-X tries to solve is already solved by a well-known tool, method, or standard that the author has missed: name it. "This is just X" is useful, not insulting.

**Checker weaknesses** — the `cx` checker is a small Python program that mechanically verifies gate conditions. Where does it produce false greens? Where are its checks too weak to catch real drift? Where does it miss the thing it's supposed to enforce?

**Language or clarity** — the README and protocol docs are written by a non-coder, for non-coders. If something is unclear, overclaimed, or unintentionally misleading: flag it.

---

## How to contribute

**Open an issue** for anything you want to flag without writing a fix: a design question, a gap you spotted, a simpler alternative, a security concern. Plain language is fine — no need to file a formal bug report.

**Open a PR** if you want to propose a concrete change. Keep the diff focused. A short explanation of *why* (not just what) is more useful than a long description.

**Challenge the design** — issues that question the fundamental approach are welcome. If the whole cross-family review idea is flawed, say so. If the planning stage as described doesn't actually prevent drift, make the case. The goal is for the community to make this better than one non-coder's attempt could be on its own.

---

## What this is not looking for

- Marketing-style improvements to make things sound more impressive
- Adding complexity without a clear gain
- Novelty claims — the humble framing is deliberate

---

## Contact

The best way to reach me is to **[open a GitHub issue](https://github.com/1984-alt/code-x/issues)** — questions, feedback, or "this helped" all welcome.
