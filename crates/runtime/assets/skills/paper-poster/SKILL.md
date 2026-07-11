---
name: paper-poster
description: "DEPRECATED — superseded by /paper-poster-html. Kept only as a redirect for muscle memory; do not use for new posters."
argument-hint: [paper-dir-or-pdf]
allowed-tools: Read
---

# Paper Poster (DEPRECATED → /paper-poster-html)

This skill is retired. The LaTeX/tcbposter pipeline it described produced posters with
unbounded color palettes, no real paper figures, and no print-canvas verification, and
has been replaced by the measurement-gated HTML/CSS pipeline.

**Immediately proceed with `/paper-poster-html`**, passing through all of the user's
arguments unchanged. Do not attempt the legacy LaTeX flow.

The full legacy implementation remains available in git history
(`git log -- skills/paper-poster/SKILL.md`) if a venue ever mandates LaTeX poster
source — none is known to.
