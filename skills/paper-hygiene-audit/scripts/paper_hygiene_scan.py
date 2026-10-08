#!/usr/bin/env python3
"""
paper_hygiene_scan.py — deterministic Tier A scanner and verdict finalizer for
/paper-hygiene-audit, the targeted check of the files you are about to upload.

Doctrine:

- Definite findings are facts; candidates need a reviewer; a clean scan
  acquits only the deterministic checks it ran — it never acquits the
  semantic lenses. A definite finding stands unless a HUMAN exempts it in the
  allow-list; a candidate is ruled by the fresh cross-family reviewer (Tier B)
  or by a human. The executor never relabels a finding and never writes an
  exemption (`acceptance-gate.md`: drive, not acquit).
- The verdict is computed here (`finalize`), from a fixed decision table —
  never by the executor and never by the reviewer.
- Audit the bytes you will upload. Findings come from the PDF text, the PDF
  objects, the build log, and the supplementary archive. LaTeX sources add
  file:line and catch what a stale log no longer reports; a source-only hit
  that never reaches the PDF text is reported as INFO.
- Fail closed. A core check that could not run (no PDF text backend) caps the
  verdict at BLOCKED; a skipped advisory check caps it at WARN. Nothing that
  did not run is reported as clean.
- The report must not leak. Identity terms, deny-list terms, and secrets are
  redacted in every output; recorded paths are relative to the paper
  directory.

Subcommands:
  scan         Tier A — deterministic findings (+ review_input.json for Tier B)
  finalize     merge the reviewer's raw response, compute the verdict, write
               PAPER_HYGIENE_AUDIT.{json,md} (assurance-contract schema) and
               the fix plan for a person (FIX_PLAN.md)
  apply        `— fix` only: apply the executor's proposed edits for the fix
               queue, after checking each against the conservative whitelist
               (delete-only prose, verified cross-references, metadata lines,
               junk members); an edit that fails is never applied
  edits        list every change since round 0 with the whitelist verdict
  restore      put back the sources and supplement of an earlier fix round
               (the round with the fewest blocking findings and no regression)
  status       is an existing PAPER_HYGIENE_AUDIT.json still about the current
               bytes, and was it a read-only recheck (upload_ready)?
  list-checks  print the check table (single source of truth for the skill)
  repack       deterministic re-pack of a supplementary directory into a zip

Exit codes (scan and finalize):
  0  PASS, WARN, or NOT_APPLICABLE (WARN is carried in the JSON)
  1  FAIL — at least one blocking finding
  2  BLOCKED, ERROR, or a usage error — no trustworthy verdict
The JSON is written on every path, including BLOCKED and ERROR.
`status` exits 0 when the artifact is current and upload_ready, else 1.

PDF backends (graceful degradation; the `backends` field records what ran):
  page text + block geometry   PyMuPDF  >  poppler (pdftotext -bbox-layout)
  page text only               pypdf
  metadata, objects, bytes     always pure stdlib (zlib + object streams)

Artifacts (paths chosen by the caller):
  --json-out / --md-out        Tier A report (scan) or final report (finalize)
  --work-dir                   pdf_text.<stem>.txt (redacted), review_input.json,
                               supp_docs/ (redacted README-like texts)

Pure stdlib; optional PyMuPDF / poppler / pypdf for PDF text. Python >= 3.8.
"""

from __future__ import annotations

import argparse
import bisect
import codecs
import contextlib
import fnmatch
import getpass
import hashlib
import io
import json
import lzma
import math
import os
import posixpath
import re
import shutil
import statistics
import subprocess
import sys
import tarfile
import tempfile
import unicodedata
import zipfile
import zlib
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Set, Tuple


def _add_shared_tools_dir() -> None:
    """The optional shared ARIS helpers this script imports (threat_scan,
    provenance) live in the repository's tools/, while this script lives in
    skills/paper-hygiene-audit/scripts/ (Phase 3 layout). Find that tools/
    next to the repository this file belongs to, else through $ARIS_REPO or
    the ~/.aris/repo pointer, and append it — never prepend, so nothing can
    shadow the standard library. Without it the helpers count as missing."""
    here = os.path.dirname(os.path.realpath(__file__))
    cands = [os.path.join(here, os.pardir, os.pardir, os.pardir, "tools")]
    repo = os.environ.get("ARIS_REPO", "")
    if not repo:
        try:
            with open(os.path.join(os.path.expanduser("~"), ".aris", "repo"), encoding="utf-8") as fh:
                repo = fh.read().strip()
        except OSError:
            repo = ""
    if repo:
        cands.append(os.path.join(repo, "tools"))
    for d in cands:
        d = os.path.normpath(d)
        if os.path.isfile(os.path.join(d, "provenance.py")):
            if d not in sys.path:
                sys.path.append(d)
            return


_add_shared_tools_dir()

TOOL = "paper_hygiene_scan"
TOOL_VERSION = "1"
SKILL_NAME = "paper-hygiene-audit"
DETERMINISTIC_REVIEWER = "deterministic:paper_hygiene_scan"

BLOCK, WARN, INFO = "BLOCK", "WARN", "INFO"
_SEV_RANK = {INFO: 0, WARN: 1, BLOCK: 2}
DEFINITE, CANDIDATE = "definite", "candidate"

VERDICTS = ("PASS", "WARN", "FAIL", "NOT_APPLICABLE", "BLOCKED", "ERROR")
VERDICT_EXIT = {"PASS": 0, "WARN": 0, "NOT_APPLICABLE": 0, "FAIL": 1, "BLOCKED": 2, "ERROR": 2}

RUN_MODES = ("audit", "fix", "recheck")
HARDWARE_LEVELS = {"block": BLOCK, "warn": WARN, "info": INFO}  # also the --framework levels
CORE_LENSES = ("triage", "engineering", "anonymity", "statements")

# Safety limits (zip bombs, huge streams) — see Known Limitations in SKILL.md.
MAX_STREAM_BYTES = 20 * 1024 * 1024
MAX_PDF_DECODED_BYTES = 200 * 1024 * 1024
MAX_SUPP_MEMBER_BYTES = 50 * 1024 * 1024
MAX_SUPP_TOTAL_BYTES = 500 * 1024 * 1024
MAX_SUPP_DEPTH = 3
MAX_SUPP_DOCS_BYTES = 200 * 1024
MAX_SUPP_DATA_DEEP_CHARS = 5 * 1024 * 1024  # larger data members get the identity/path/secret pass only


# ─── Check table (single source of truth: list-checks, SKILL docs, tests) ────

def _chk(family: str, layer: str, certainty: str, default: str, confirm: Optional[str],
         priority: str, rule: str, fix: str, route: str = "fix") -> Dict[str, Any]:
    return {"family": family, "layer": layer, "certainty": certainty, "default": default,
            "confirm": confirm, "priority": priority, "route": route, "rule": rule, "fix": fix}


_REBUILD = "Fix the key, then rebuild fully (latexmk, or pdflatex/bibtex/pdflatex x2) until the log has no Rerun warning; never hand-write the number."
_DROP_ENV = ("Delete the leaking fragment (the whole sentence only when nothing else is left in it); point "
             "reproduction detail to the supplementary material.")
_CITE_FIX = ("In order: a typo -> use the closest existing key (see the note); else verify the work with /citation-audit and "
             "add its real entry; else (no real work found) drop the dangling key from a multi-key \\cite, or the clause that "
             "rests on a single-key \\cite unless it states a result. Rebuild fully afterwards.")

CHECKS: Dict[str, Dict[str, Any]] = {
    # XREF — unresolved cross-references and citations (P0)
    "XREF-PDF-QQ": _chk("XREF", "pdf", "D/C", "BLOCK/WARN", BLOCK, "P0",
                        "A cross-reference prints as ?? in the PDF text (reference context, (??), or a standalone ??).",
                        _REBUILD, route="/paper-compile"),
    "XREF-PDF-CITE": _chk("XREF", "pdf", "D", BLOCK, None, "P0",
                          "A citation prints as [?], (?), (?, ?) or ? (?) in the PDF text.",
                          _CITE_FIX, route="/paper-compile"),
    "XREF-PDF-KEY": _chk("XREF", "pdf+tex", "D", BLOCK, None, "P0",
                         "An undefined citation key is printed verbatim in the PDF text (biblatex style).",
                         "Add the missing entry or fix the key, then rebuild.", route="/paper-compile"),
    "XREF-LOG-REF": _chk("XREF", "log", "D", BLOCK, None, "P0",
                         "The build log reports an undefined reference.", _REBUILD, route="/paper-compile"),
    "XREF-LOG-CITE": _chk("XREF", "log", "D", BLOCK, None, "P0",
                          "The build log reports an undefined citation.", _REBUILD, route="/paper-compile"),
    "XREF-LOG-UNDEF": _chk("XREF", "log", "D", BLOCK, None, "P0",
                           "The build log reports 'There were undefined references/citations'.",
                           _REBUILD, route="/paper-compile"),
    "XREF-LOG-RERUN": _chk("XREF", "log", "D", "BLOCK/WARN", None, "P0",
                           "The build stopped before cross-references or citations settled (Rerun, Label(s) / Citation(s) "
                           "may have changed, rerun Biber); WARN when only the PDF bookmarks (outlines) are stale.",
                           "Run the full build sequence until no Rerun warning remains.", route="/paper-compile"),
    "XREF-LOG-MULTI": _chk("XREF", "log", "D", "WARN/BLOCK", None, "P0",
                           "A label is multiply defined (BLOCK when that label is referenced).",
                           "Rename one of the duplicate labels and update its references.", route="fix"),
    "XREF-LOG-DEST": _chk("XREF", "log", "D", WARN, None, "P0",
                          "A hyperlink destination is referenced but does not exist.",
                          "Fix the label/anchor the link points to.", route="fix"),
    "XREF-BLG": _chk("XREF", "blg", "D", BLOCK, None, "P0",
                     "BibTeX/Biber could not find a database entry or the database file.",
                     "A missing .bib path: fix the path. A missing entry: " + _CITE_FIX,
                     route="/citation-audit"),
    "XREF-SRC-REF": _chk("XREF", "tex", "D", BLOCK, None, "P0",
                         "A \\ref-family key has no matching \\label in the sources or the .aux.",
                         "Point the reference at an existing label (or remove the reference).", route="fix"),
    "XREF-SRC-CITE": _chk("XREF", "tex+bib", "D", BLOCK, None, "P0",
                          "A \\cite key has no entry in the .bib/.bbl/.aux (the note names the closest existing keys "
                          "and how many keys share the \\cite).",
                          _CITE_FIX, route="/citation-audit"),
    "BUILD-STALE": _chk("BUILD", "mtime", "D", "BLOCKED", None, "P0",
                        "The PDF is older than a source file it was built from.",
                        "Rebuild the PDF before auditing it.", route="/paper-compile"),
    # LOG — build-log hygiene (P1)
    "LOG-ERROR": _chk("LOG", "log", "D", BLOCK, None, "P1",
                      "The build log has a TeX error although a PDF was produced (nonstopmode).",
                      "Fix the error; a PDF built past an error can silently drop content.", route="/paper-compile"),
    "LOG-OVERFULL": _chk("LOG", "log", "D", WARN, None, "P1",
                         "Overfull boxes (count and worst overflow).",
                         "Reflow the offending lines; blocking policy lives in /auto-paper-improvement-loop Step 8.",
                         route="/auto-paper-improvement-loop"),
    "LOG-GLYPH": _chk("LOG", "log", "D", WARN, None, "P1",
                      "Missing glyphs or undefined font shapes (characters silently dropped or substituted).",
                      "Load a font/encoding that has the glyph, or replace the character.", route="fix"),
    # ENG — engineering and environment leakage (P0)
    "ENG-VER": _chk("ENG", "pdf+tex", "D", BLOCK, None, "P0",
                    "Library/toolchain/OS versions do not belong in the paper (they belong in the supplementary README).",
                    _DROP_ENV),
    "ENG-FW": _chk("ENG", "pdf+tex", "C", WARN, "FRAMEWORK", "P1",
                   "Framework or tooling named without a scientific reason (PyTorch, vLLM, Docker, W&B, ...).",
                   "Keep only if the claim depends on it; otherwise describe the method, not the tooling."),
    "ENG-HW": _chk("ENG", "pdf+tex", "C", WARN, "HARDWARE", "P1",
                   "Accelerator/CPU models (A100, H100, Xeon, ...) outside a compute-resources or related-work section.",
                   "Keep one minimal platform sentence only when a claim depends on it (e.g., latency); otherwise delete."),
    "ENG-QTY": _chk("ENG", "pdf+tex", "C", WARN, "HARDWARE", "P1",
                    "Accelerator or core counts, GPU-hours, memory bytes, pinned cores, process-seconds, CPU-only runs.",
                    "Move compute accounting to a compute-resources section or the supplement."),
    "ENG-OPS": _chk("ENG", "pdf+tex", "D/C", "BLOCK/WARN", BLOCK, "P0",
                    "Operational commands or infrastructure narration (ssh, nohup, sbatch, pip install, device_map=, "
                    "'on our server', launch logs).",
                    _DROP_ENV),
    "ENG-PATH": _chk("ENG", "pdf+tex", "D", BLOCK, None, "P0",
                     "Absolute local paths (/home/, /Users/, C:\\Users\\, \\\\wsl$, ~/x/).",
                     "Delete the path; refer to the supplementary material instead."),
    "ENG-NET": _chk("ENG", "pdf+tex", "D/C", "BLOCK/WARN", BLOCK, "P0",
                    "IP addresses, internal hostnames (.local/.internal/.corp), wandb entities, cloud-drive share links.",
                    "Delete it; use an anonymous artifact link if a link is needed."),
    "ENG-HASH": _chk("ENG", "pdf+tex", "D/C", "BLOCK/WARN", WARN, "P0",
                     "Commit ids, 32/40/64-hex digests, UUIDs (definite); hashing vocabulary and code hashes (candidate).",
                     "Move hashes and run ids to the supplementary README."),
    "ENG-SECRET": _chk("ENG", "pdf+tex", "D", BLOCK, None, "P0",
                       "API keys and tokens (sk-, ghp_, hf_, AKIA, xox?-, high-entropy key=value literals). "
                       "Redacted in every output.",
                       "Delete it and rotate the credential."),
    "ENG-DENY": _chk("ENG", "pdf+tex", "D", BLOCK, None, "P0",
                     "A term from the policy extra_deny list (internal code names). Redacted as [DENY#n].",
                     "Delete or replace the internal name."),
    "ENG-FILENAME": _chk("ENG", "pdf+tex", "C", WARN, WARN, "P1",
                         "A script, notebook, or config file name in the paper's prose ('run_eval.py', "
                         "'config.yaml'): the paper describes the method and points to the supplementary material, "
                         "not to its files. A README is a pointer to documentation (INFO, still reviewed; not "
                         "reported next to 'supplementary' or 'appendix'); INFO in end-matter statements too.",
                         "Describe what the file does, or say 'the supplementary material'; never in the fix queue "
                         "(rewording is for a person)."),
    "ENG-PRECISION": _chk("ENG", "pdf+tex", "C", WARN, WARN, "P2",
                          "Numeric precision and weight-loading detail (bf16, fp8, int8, mixed precision, "
                          "dequantized) — only with policy precision_disclosure: candidate; the default (exempt) "
                          "never reports it.",
                          "Keep it only where a claim depends on it (a precision ablation); otherwise move it to the "
                          "supplementary README."),
    # PROC — process and timeline narration (paper-write Key Rules 5, 8)
    "PROC-TIME": _chk("PROC", "pdf+tex", "D/C", "BLOCK/WARN", BLOCK, "P0",
                      "Clock times with a time zone (definite); dates, month batches, launch stamps (candidate).",
                      "Use neutral names ('original runs', 'replacement runs'); keep data-collection windows only if scientific."),
    "PROC-REVIEW": _chk("PROC", "pdf+tex", "C", WARN, BLOCK, "P1",
                        "Review/rebuttal narration (reviewer #2, rebuttal, camera-ready, previous version, simulated reviewers).",
                        "Rewrite as a neutral statement; never narrate the review process (/paper-write Key Rule 5)."),
    "PROC-REVISION": _chk("PROC", "pdf+tex", "C", WARN, BLOCK, "P1",
                          "Revision/run narration (round-2, phase_3, re-ran, hotfix, after fixing a bug, earlier runs, "
                          "the user asked).",
                          "State what was done, not how the draft or the runs evolved (/paper-write Key Rule 8)."),
    "PROC-AITOOL": _chk("PROC", "pdf+tex", "C", WARN, WARN, "P1",
                        "An AI tool brand co-occurs with writing/coding verbs and a manuscript/code object outside the "
                        "AI-use statement.",
                        "Disclose AI use in the venue's AI-use statement only, in generic terms."),
    "PROC-PENDING": _chk("PROC", "pdf+tex", "C", WARN, WARN, "P1",
                         "Unfinished-work status in the text ('not yet evaluated', 'to be added', 'results pending', "
                         "TBD): whether to finish, drop, or keep the work is the authors' decision.",
                         "A person decides: finish the work or delete the row or sentence that announces it; never "
                         "reword the status away ('not evaluated'). Never in the fix queue."),
    "PROC-DATESEED": _chk("PROC", "pdf+tex", "C", WARN, WARN, "P1",
                          "A random seed or salt shaped like a calendar date (20991231): next to 'seed' or 'salt' it "
                          "tells the reader when the study ran.",
                          "In the paper, describe the seeds ('three fixed seeds, listed in the supplement'); keep the "
                          "values in code and records. A person decides; never in the fix queue."),
    "PROC-REGLABEL": _chk("PROC", "pdf+tex", "C", WARN, WARN, "P2",
                          "A registration amendment, addendum, or clarification label ('Amendment 11', 'Addendum F', "
                          "'protocol addendum') - reported only with policy registration_labels: flag; "
                          "with keep (the default) the label is a required disclosure and is not reported.",
                          "Under 'flag', keep the timing fact the label carries ('this threshold was chosen once early "
                          "results were in; the analysis is otherwise as planned') and drop the label. A person decides."),
    # ANON — anonymity (off under --camera-ready)
    "ANON-NAME": _chk("ANON", "pdf+tex", "D", BLOCK, None, "P1",
                      "An identity term (anon-names list or auto identity) appears; INFO inside the references.",
                      "Remove it; cite your own work in the third person."),
    "ANON-EMAIL": _chk("ANON", "pdf+tex", "D", BLOCK, None, "P1",
                       "An e-mail address (placeholders such as example.com are exempt).",
                       "Delete the address."),
    "ANON-AUTHOR": _chk("ANON", "pdf+tex", "D", "BLOCK/WARN", None, "P1",
                        "A final-copy switch is active, or author names are printed; page 1 lacks 'Anonymous' (WARN).",
                        "Turn the final-copy option off and leave \\author to the venue style."),
    "ANON-ACK": _chk("ANON", "pdf+tex", "D", BLOCK, None, "P1",
                     "Acknowledgments, author contributions, or funding/grant text in an anonymous submission.",
                     "Remove the section (or use the venue's hidden ack environment)."),
    "ANON-LINK": _chk("ANON", "pdf+tex", "D/C", "BLOCK/WARN", BLOCK, "P1",
                      "Code/profile links (GitHub, GitLab, Hugging Face, *.github.io); definite when the owner is an identity term.",
                      "Use an anonymized host (e.g., anonymous.4open.science) or the supplement."),
    "ANON-SELFCITE": _chk("ANON", "pdf+tex", "C", WARN, BLOCK, "P1",
                          "First-person self-citation phrasing ('our previous work', 'we showed in').",
                          "Cite your earlier work in the third person."),
    "ANON-LIST-MISSING": _chk("ANON", "config", "D", WARN, None, "P1",
                              "Anonymous mode, but no identity list file exists (only auto identity terms were checked).",
                              "Create .aris/paper-hygiene/anon-names.txt (authors, affiliations, user/host names, e-mails)."),
    "ANON-LIST-LOCATION": _chk("ANON", "config", "D", WARN, None, "P1",
                               "The identity list lives inside the paper directory and could be uploaded with it.",
                               "Move it to .aris/paper-hygiene/ at the project root."),
    "ANON-LIST-TERM": _chk("ANON", "config", "D", WARN, None, "P1",
                           "An identity term is too short to match safely and was ignored.",
                           "Use a longer, more specific term."),
    "ANON-CODENAME": _chk("ANON", "supp", "C", "WARN/INFO", WARN, "P2",
                          "A probable internal project or code name, inferred from the supplement (its top folder, a "
                          "Python package folder, a /path/to/<name> placeholder, a document title, project= or paper= "
                          "in code): WARN when the paper's text uses the same lower-case token, INFO when it only "
                          "recurs in the supplement. A name an earlier round reported stays reported while any "
                          "occurrence is left.",
                          "If it is an internal name, a person replaces it in the paper and in the supplement's notes "
                          "and file names (in code literals and record keys only together with the outputs they "
                          "produce) and adds it to policy extra_deny; otherwise rule it a false positive."),
    # META — PDF metadata and object bytes (stdlib)
    "META-INFO": _chk("META", "pdf-meta", "D", "BLOCK/WARN/INFO", None, "P1",
                      "Info dictionary fields: Author (BLOCK when anonymous), Title/Subject/Keywords (WARN), Creator/Producer (INFO).",
                      "\\hypersetup{pdfauthor={},pdftitle={},pdfsubject={},pdfkeywords={},pdfcreator={},pdfproducer={}}."),
    "META-TZ": _chk("META", "pdf-meta", "D", "WARN/INFO", None, "P1",
                    "CreationDate/ModDate carry a local UTC offset (time zone), in the document Info or in an "
                    "embedded figure's PTEX.InfoDict.",
                    "Document Info: \\pdfinfoomitdate=1, or build with TZ=UTC SOURCE_DATE_EPOCH=<fixed> FORCE_SOURCE_DATE=1; "
                    "an embedded figure's date (PTEX.InfoDict): \\pdfsuppressptexinfo=-1 in the preamble."),
    "META-PTEX": _chk("META", "pdf-meta", "D", "BLOCK/WARN/INFO", None, "P1",
                      "PTEX.FileName/InfoDict of embedded figures (BLOCK with an absolute path or identity term; "
                      "InfoDict tool and version strings WARN in anonymous mode; a plain relative name is INFO).",
                      "\\pdfsuppressptexinfo=-1 in the preamble (one line, no figure changes); re-export figures "
                      "without metadata only with the user's consent."),
    "META-XMP": _chk("META", "pdf-meta", "D", "BLOCK/INFO", None, "P1",
                     "XMP metadata (BLOCK when it names an identity term).",
                     "Drop the XMP packet or the package that writes it."),
    "META-BYTES": _chk("META", "pdf-bytes", "D", BLOCK, None, "P1",
                       "Decompressed objects/streams contain an absolute path, identity term, or e-mail.",
                       "Rebuild without the offending figure metadata; re-export embedded figures."),
    "META-EMBED": _chk("META", "pdf-meta", "D", WARN, None, "P1",
                       "The PDF carries embedded file attachments.",
                       "Remove the attachments unless the venue asks for them."),
    "META-FIGURE": _chk("META", "pdf-meta", "D", "WARN/INFO", None, "P1",
                        "A figure carries tool versions, an author, or a local time zone in its own metadata: XMP of a "
                        "figure embedded in the PDF and PDF members of the supplement (WARN in anonymous mode); the "
                        "figure files the sources include (INFO: they ship only with a source upload).",
                        "Re-save the figure without metadata, or clear it where the figure is made (e.g. savefig(..., "
                        "metadata={'Creator': None, 'Producer': None, 'CreationDate': None})); rewriting a figure file "
                        "needs the user's OK, so a person does it."),
    # TEXT — text layer and garbling
    "TEXT-CODE": _chk("TEXT", "pdf", "D/C", "BLOCK/WARN/INFO", BLOCK, "P1",
                      "Code residue in prose: literal \\n or \\t, visible control words, \\boxed{, markdown ** or # headings "
                      "(definite); snake_case (candidate); INFO when the same text is typeset verbatim in the sources "
                      "(still sent to the reviewer as a low-priority group). An escape glued to words on both sides "
                      "('see\\nTable') is never verbatim, even when the source spells it with \\textbackslash.",
                      "Describe it in words; verbatim text belongs in a labelled prompt/code table."),
    "TEXT-MARKER": _chk("TEXT", "pdf+tex", "D/C", "BLOCK/WARN", BLOCK, "P1",
                        "TODO, FIXME, [VERIFY], DATA_NEEDED, [TBD], [citation needed] (definite); XXX or \\todo (candidate).",
                        "Resolve the marker and delete it."),
    "TEXT-REPL": _chk("TEXT", "pdf", "D/C", "BLOCK/WARN", BLOCK, "P1",
                      "U+FFFD replacement or control characters (definite); private-use glyphs other than "
                      "large-delimiter pieces (candidate).",
                      "Fix the font/encoding (\\input{glyphtounicode}\\pdfgentounicode=1) or the source character."),
    "TEXT-INVISIBLE": _chk("TEXT", "pdf", "D", BLOCK, None, "P2",
                           "Zero-width or bidirectional control characters in the text layer.",
                           "Delete them; they also hide text from detectors."),
    "TEXT-INJECT": _chk("TEXT", "pdf", "C", WARN, BLOCK, "P2",
                        "Text that reads like an instruction to an LLM reviewer (threat_scan context scope).",
                        "Delete hidden instructions; papers that study injection get a 'false_positive' ruling."),
    "TEXT-GLUE": _chk("TEXT", "pdf", "C", WARN, WARN, "P2",
                      "Glued words in the text layer (very long letter runs, wordAword, LetB, 'Eq. (3)gives').",
                      "Add \\pdfinterwordspaceon or fix the spacing around inline math and references; re-scan."),
    "TEXT-NOSPACE": _chk("TEXT", "pdf-bytes", "D", WARN, None, "P2",
                         "The text layer lacks real space characters: pdfTeX without interword spaces, or a second "
                         "extractor (pypdf) reads words glued together, mostly around inline math.",
                         "No verified automatic fix: a person decides. \\input{glyphtounicode}\\pdfgentounicode=1 is safe; "
                         "a global \\pdfinterwordspaceon draws spaces with math-font glyphs (a visible arrow or psi), "
                         "so any interword-space change is made by hand and checked against a rendering of every page "
                         "with inline math. Never in the fix queue."),
    "TEXT-MATHGLYPH": _chk("TEXT", "pdf", "C", WARN, WARN, "P2",
                           "Stray math-font glyphs (psi, left arrow) where spaces should be — an interwordspace side effect.",
                           "A person decides: undo the interword-space setting or reflow the sentence, then render and "
                           "compare the page. Never in the fix queue."),
    "TEXT-T3FONT": _chk("TEXT", "pdf-meta", "D", INFO, None, "P2",
                        "Type 3 fonts (usually from plotted figures): their text copies badly, and a minus sign or a "
                        "letter can be lost in extraction.",
                        "Re-export the figure with embedded TrueType or Type 1 fonts (matplotlib: rcParams['pdf.fonttype'] "
                        "= 42); needs the user's OK."),
    "TEXT-NUMFMT": _chk("TEXT", "pdf", "D", INFO, None, "P2",
                        "Machine number formats (3.7e-04, [1.25,3.50], hyphen used as a minus sign).",
                        "Typeset as math ($3.7\\times10^{-4}$, $-0.38$, '[1.25, 3.50]')."),
    # PAGE / TPL / ENDM
    "PAGE-LIMIT": _chk("PAGE", "pdf-geometry", "D", BLOCK, None, "P1",
                       "The main body ends after the page limit.",
                       "Move existing content to the appendix or tighten wording; never shrink fonts or margins.",
                       route="/paper-compile"),
    "PAGE-FILL": _chk("PAGE", "pdf-geometry", "D", WARN, None, "P1",
                      "The main body must end on page N with fill >= threshold (reports lines short).",
                      "Move existing content between body and appendix or resize floats; no layout hacks."),
    "TPL-OVERRIDE": _chk("TPL", "tex", "D", "BLOCK/WARN", None, "P1",
                         "Layout overrides (geometry, \\linespread, \\baselinestretch, size redefinitions; WARN for negative \\vspace, \\enlargethispage, caption/title spacing).",
                         "Remove the override; fix length by moving content."),
    "TPL-STYLE": _chk("TPL", "tex+log", "D", BLOCK, None, "P2",
                      "A loaded .sty/.cls/.bst differs byte-for-byte from the official template (--style-ref).",
                      "Restore the official file."),
    "ENDM-MISSING": _chk("ENDM", "pdf", "D", BLOCK, None, "P1",
                         "A required end-matter statement heading (--end-matter) is missing.",
                         "Add the statement with the exact heading the venue template uses."),
    "ENDM-ORDER": _chk("ENDM", "pdf", "D", BLOCK, None, "P1",
                       "Required end-matter statements are out of order or after the references.",
                       "Reorder them: after the main body, before the references, in the configured order."),
    # SUPP — supplementary archive
    "SUPP-INTEGRITY": _chk("SUPP", "supp", "D", BLOCK, None, "P1",
                           "The archive or a member is corrupt or truncated (CRC, zip/tar structure, gzip/xz stream).",
                           "Re-pack it (see `repack`)."),
    "SUPP-SIZE": _chk("SUPP", "supp", "D", BLOCK, None, "P1",
                      "The archive exceeds --supp-max-mb.", "Trim data or link an anonymous artifact."),
    "SUPP-JUNK": _chk("SUPP", "supp", "D/C", "BLOCK/WARN", WARN, "P1",
                      "Junk members (.git/, __MACOSX/, .env, .svn/ BLOCK; .DS_Store, __pycache__, *.pyc, editor dirs WARN); "
                      "run logs and runtime artifacts (*.log, nohup.out, slurm-*.out, wandb/, mlruns/, lightning_logs/, "
                      "events.out.tfevents.*) are WARN candidates: reproduction rarely needs them.",
                      "Re-pack without them (`repack --exclude <glob>`); keep a log only when the README uses it to "
                      "check a reproduction."),
    "SUPP-ARIS": _chk("SUPP", "supp", "D", BLOCK, None, "P1",
                      "ARIS/agent working files in the archive (.aris/, .claude/, CLAUDE.md, AGENTS.md, ARIS audit "
                      "reports, FIX_LOG.md, traces).",
                      "Re-pack without them; working notes never ship."),
    "SUPP-META": _chk("SUPP", "supp", "D", WARN, None, "P1",
                      "Zip comment, extra fields with timestamps/uid/gid, or real (non-1980) member timestamps.",
                      "Re-pack deterministically (see `repack`)."),
    "SUPP-GZIP": _chk("SUPP", "supp", "D", "BLOCK/WARN", None, "P1",
                      "A .gz header stores the original file name, a comment, or a modification time "
                      "(BLOCK when it holds an identity term).",
                      "Recompress with gzip -n."),
    "SUPP-TAR": _chk("SUPP", "supp", "D", "BLOCK/WARN", None, "P1",
                     "Tar members carry uname/gname/uid/gid/mtime (BLOCK when uname/gname is an identity term).",
                     "Re-create the tar with --owner=0 --group=0 --numeric-owner --mtime=@0."),
    "SUPP-NAME": _chk("SUPP", "supp", "D/C", "BLOCK/WARN", None, "P1",
                      "Member names with identity terms or home paths (BLOCK); dates, _r2, r3b_, v2_/_v3, phase2, _fix, "
                      "_bak (WARN); working-copy endings _now, _prev, _old, _new, _tmp (WARN candidates). Names that "
                      "read as process records are SUPP-PROCFILE.",
                      "Rename in the staged copy only when every reference can be updated: grep the whole package for the "
                      "old name and stem (zero hits left), every import and path still resolves (python -m py_compile, "
                      "the package's own checks when it has them); otherwise a person decides."),
    "SUPP-TEXT": _chk("SUPP", "supp", "D/C", "BLOCK/WARN", None, "P1",
                      "Member text with identity terms, home paths, secrets, user@host, internal hostnames (BLOCK; WARN "
                      "inside data records); process narration, clock times, and dates in docs and comments, run "
                      "timestamps in data records and logs, date stamps in records and code literals, timestamped ids "
                      "(WARN); candidates in notes: environment-variable prefixes of a command (CUDA_VISIBLE_DEVICES=), "
                      "short hashes after commit/sha/hash, seeds shaped like a date, and (by policy) precision or "
                      "registration labels. Versions, hardware notes, and install commands are fine here.",
                      "Edit the member in the staged copy (never the source): delete the leaking fragment of the "
                      "note; keep seeds, hashes, versions, and hardware notes that reproduction needs."),
    "SUPP-HW": _chk("SUPP", "supp", "C", "WARN/INFO", "SUPP_HARDWARE", "P1",
                    "Hardware, operating-system, or host words in supplementary notes and member names (accelerator or "
                    "CPU models and counts, CPU-only, GPU-hours, Ubuntu, WSL, 'on our two hosts'): WARN candidates "
                    "whose confirmed level follows the --hardware policy (a reproduction requirement is ruled "
                    "'necessary'); policy supp_hardware warn or block sets another level, and supp_hardware info "
                    "(or --hardware info) keeps them INFO and unreviewed.",
                    "Keep what reproduction needs (a requirement in the README); delete run-environment narration "
                    "('(CPU, cached inputs)', 'ran on our hosts')."),
    "SUPP-PATH": _chk("SUPP", "supp", "C", "WARN/INFO", WARN, "P1",
                      "Placeholder root paths (<DATA_ROOT>/x, ${ROOT}/x) in code literals and records (INFO in READMEs, "
                      "where they are usage notation); references to scripts the package does not contain (a README "
                      "command, a Usage line, 'generated by x.py', an old name left after a rename); paths in code "
                      "notes into directories the package does not contain, and relative paths in code literals "
                      "('../run_v1/cfg.json') that resolve to nothing in the package (INFO: often an output the code "
                      "writes).",
                      "Point the reference at the shipped file, make paths relative to the package "
                      "(Path(__file__).resolve().parents[k]), or delete the reference."),
    "SUPP-PROCFILE": _chk("SUPP", "supp", "C", "WARN/INFO", WARN, "P1",
                          "Members whose name or title reads as a process record: NOTES, TODO, STATUS, STOP, REVIEW, "
                          "ROUND, HANDOFF, PROGRESS, worklog, scratch, draft, old, root cause, post-mortem, as-found, "
                          "superseded, wip; addendum, amendment draft, and clarification files are registration "
                          "records: INFO with policy registration_labels: keep (the default), candidates with flag.",
                          "When the reviewer rules it a leak, leave it out of the upload (`repack --exclude`); move a "
                          "definition the README needs into the README first."),
    "SUPP-RUNTIME": _chk("SUPP", "supp", "C", "INFO/WARN", WARN, "P1",
                         "Code that writes the run time into its outputs: a date or timestamp key filled from "
                         "strftime/datetime.now, or a time-stamped output file name (INFO, WARN under --strict; the "
                         "run timestamps already in shipped records are SUPP-TEXT).",
                         "Report only: a person drops the key or uses a fixed value; the fix loop never changes code "
                         "logic. Never in the fix queue."),
    "SUPP-LANG": _chk("SUPP", "supp", "C", INFO, None, "P2",
                      "A supplementary document written mostly in another language than the paper (CJK prose in a "
                      "paper written in Latin script).",
                      "Translate it, or leave it out when the README does not need it."),
    "SUPP-COVERAGE": _chk("SUPP", "review", "D", WARN, None, "P1",
                          "Supplementary members of a reviewer batch that no batch reply marked as checked "
                          "(members_checked), and notes the review text budget left out of every batch or cut short "
                          "(never read in full, so never counted as covered).",
                          "Run the missing batch with a fresh reviewer and finalize again; read the members over the "
                          "review budget by hand, or split the supplement."),
    "SUPP-UNSCANNED": _chk("SUPP", "supp", "D", INFO, None, "P1",
                           "Members beyond the depth/size limits were not scanned.",
                           "Inspect them manually or split the archive."),
    # NUM / config
    "NUM-DRIFT": _chk("NUM", "pdf", "D/C", "BLOCK/WARN/INFO", None, "P1",
                      "Numbers changed against --baseline (decimals and percentages definite, integers candidate; the "
                      "note quotes the sentence). An integer that left together with a clause holding a baseline "
                      "finding (a deleted clock time, version, or launch detail) is INFO.",
                      "Stop: numbers belong to /paper-claim-audit; restore them or re-audit.",
                      route="/paper-claim-audit"),
    "CONFIG-CHANGED": _chk("CONFIG", "config", "D", BLOCK, None, "P1",
                           "allow.tsv, policy.json or anon-names.txt changed since the --baseline scan (fix rounds freeze them).",
                           "Revert the change; exemptions are a human decision outside the fix loop."),
    # FIX — what the fix loop itself broke (against the previous round and round 0)
    "FIX-REGRESSION": _chk("FIX", "pdf", "D", "BLOCK/WARN", None, "P0",
                           "A fix round made the PDF worse than the round before it (or than round 0): new stray "
                           "math-font glyphs (a space drawn as an arrow or psi, '±←'), a new ?? or (?), more glued "
                           "words in the text layer, a body that no longer fills the required page or passes the page "
                           "limit (BLOCK); a page count that grew (WARN).",
                           "Undo only the edits of the round that caused it (details.undo lists them; `apply --undo`), "
                           "rebuild, and re-scan; never answer with a global setting. The run delivers the round with "
                           "the fewest blocking findings and no regression."),
    "FIX-EDIT": _chk("FIX", "edit", "D", BLOCK, None, "P0",
                     "A change in the files since round 0 that the conservative whitelist does not allow: words added "
                     "or replaced (a rewrite), a deletion no fix-queue item asked for, a code line, data member, or "
                     "member name changed, or a cross-reference changed without a verified target. The fix loop only "
                     "deletes confirmed leak fragments, repairs verified references, adds metadata lines, and drops "
                     "junk members.",
                     "Undo the change (`apply --undo` for an applied edit, or restore the before text it lists); "
                     "what it tried to fix goes to the fix plan for a person."),
    "ALLOW-INVALID": _chk("ALLOW", "config", "D", WARN, None, "P1",
                          "An allow-list line is malformed, too broad, targets a non-exemptable check, or lacks typed "
                          "provenance (human:<id> | cross-family-review:<id>).",
                          "Fix or delete the line (humans edit allow.tsv; the executor never does)."),
    "ALLOW-UNUSED": _chk("ALLOW", "config", "D", INFO, None, "P1",
                         "An allow-list line or policy exempt_terms entry matched nothing in this run (stale exemption).",
                         "Delete it if it is no longer needed."),
    # LENS — findings from the Tier B reviewer (finalize only). A reviewer's own
    # finding is not a rule hit: it is WARN at most (a blocking one stays a
    # confirmed leak for upload), and it is never fixed automatically.
    "LENS-ENGINEERING": _chk("ENG", "review", "C", WARN, None, "P0",
                             "Tier B engineering lens finding (anchored quote); WARN at most — 'blocking' marks a "
                             "reviewer-confirmed leak that keeps upload_ready false.", _DROP_ENV, route="fix"),
    "LENS-ANONYMITY": _chk("ANON", "review", "C", WARN, None, "P1",
                           "Tier B anonymity lens finding (anchored quote); WARN at most, like every reviewer finding.",
                           "Remove the identifying detail."),
    "LENS-STATEMENTS": _chk("ENDM", "review", "C", WARN, None, "P1",
                            "Tier B end-matter statements lens finding (anchored quote); advisory unless policy "
                            "declared_ai_uses is set (only then can a statement contradict the record, a confirmed "
                            "finding at WARN).",
                            "Reword the statement to the venue template; never delete a sentence of a required "
                            "statement without the user's OK."),
    "LENS-OTHER": _chk("REVIEW", "review", "C", WARN, None, "P2",
                       "Tier B finding from an unknown or disabled lens (advisory).", "Advisory only."),
}
CHECK_IDS = frozenset(CHECKS)

# FAIL reason_code by family, in priority order (first match wins).
REASON_BY_FAMILY = {
    "FIX": "fix_regression",
    "XREF": "unresolved_refs", "ANON": "anonymity_leak", "ENG": "engineering_leak", "PROC": "process_narration",
    "META": "metadata_leak", "SUPP": "supplement_leak", "TEXT": "text_layer", "PAGE": "template_or_pages",
    "TPL": "template_or_pages", "NUM": "number_drift", "CONFIG": "config_changed", "ENDM": "end_matter",
    "LOG": "build_errors",
}
# What a reader of the recheck must learn first: a leak still in the files,
# then an unresolved reference, then metadata, then the rest (the fix loop's
# own damage included).
REASON_PRIORITY = ("anonymity_leak", "engineering_leak", "process_narration", "supplement_leak", "unresolved_refs",
                   "metadata_leak", "fix_regression", "text_layer", "template_or_pages", "number_drift",
                   "config_changed", "end_matter", "build_errors")
# WARN reasons, most substantive first (a confirmed leak is never "advisory only")
WARN_REASONS = ("confirmed_leaks", "ruling_flip", "carried_over", "unreviewed_candidates", "identity_list_missing",
                "coverage_gap", "advisory_only")
REASON_CODES = REASON_PRIORITY + WARN_REASONS + (
    "clean", "strict_warnings", "stale_pdf", "pdf_missing", "pdf_unreadable", "pdf_text_backend_missing",
    "pdf_text_empty", "supp_unreadable", "reviewer_error", "reviewer_output_malformed", "reviewer_unavailable",
    "scanner_unresolved", "scanner_error", "nothing_to_audit")

# Checks whose silent skip would hide a blocker: without a usable PDF text layer
# the verdict is capped at BLOCKED (`pdf_text_backend_missing` / `pdf_text_empty`), never PASS.
CORE_TEXT_CHECKS = ("XREF-PDF-QQ", "XREF-PDF-CITE", "XREF-PDF-KEY", "ENG-VER", "ENG-FW",
                    "ENG-HW", "ENG-QTY", "ENG-OPS", "ENG-PATH", "ENG-NET", "ENG-HASH",
                    "ENG-SECRET", "ENG-DENY", "PROC-TIME", "PROC-REVIEW", "PROC-REVISION",
                    "PROC-AITOOL", "ANON-NAME", "ANON-EMAIL", "ANON-LINK",
                    "ANON-SELFCITE", "TEXT-CODE", "TEXT-MARKER", "TEXT-REPL")
TEXT_ADVISORY_CHECKS = ("TEXT-INVISIBLE", "TEXT-INJECT", "TEXT-GLUE", "TEXT-MATHGLYPH",
                        "TEXT-NUMFMT", "ENDM-MISSING", "ENDM-ORDER", "NUM-DRIFT", "ENG-FILENAME", "ENG-PRECISION",
                        "PROC-DATESEED", "PROC-REGLABEL", "PROC-PENDING")
# Text-pattern checks: a source-only hit (string never reaches the PDF text) is
# demoted to INFO when the paired PDF text is available.
DEMOTABLE_CHECKS = frozenset(
    c for c in CHECKS if (c.startswith(("ENG-", "PROC-")) and c != "ENG-SECRET") or c in (
        "ANON-NAME", "ANON-EMAIL", "ANON-LINK", "ANON-SELFCITE", "ANON-ACK", "TEXT-MARKER", "TEXT-CODE"))
# (a credential in the sources stays a finding even when it never renders)

# Rulings that confirm a leak. `leak` takes the check's confirmed level (from a
# cross-family reviewer; a same-family review caps it at WARN); `reword` keeps
# the fact and changes the wording, and is WARN at most.
CONFIRMED_RULINGS = ("leak", "reword")
CLEARING_RULINGS = ("necessary", "false_positive")

# The conservative whitelist of `— fix`. details.fix_queue holds only findings
# of these fix classes, each fixed by an edit the `apply` subcommand checks
# mechanically; everything else goes to details.fix_plan (FIX_PLAN.md) for a
# person, with where it is, why it is a problem, and a suggested fix.
#   undo         an edit of this run that the whitelist rejects, or that caused a regression this round
#   xref-ref     a \ref whose label was renamed or misspelled: point it at the one existing label of the
#                same type the script names (fix_target)
#   xref-cite    a dangling key inside a multi-key \cite, with no similar key in any .bib: drop the key
#   rebuild      the build stopped before references settled: rebuild fully
#   delete       a confirmed leak fragment in the paper — a library or toolchain version, an absolute path,
#                a host, IP, or share link, an ops command, a secret, a reviewer-confirmed hardware model or
#                count: delete it (only words leave; the whole sentence only when nothing else is left)
#   delete-sentence  a sentence of the sources, or a clause of it, that holds a definite or cross-family-
#                confirmed ENG or PROC hit and says nothing once the leak goes: delete it as queued (the
#                script computes the exact source edit; `apply` recomputes it before it writes)
#   marker       an author marker (TODO, FIXME, XXX, [VERIFY], TKTK): delete it, never reword it
#   escape       a literal \n glued into prose: replace it by a space
#   meta         PDF metadata: empty the fields where the sources set them, add the preamble lines the
#                script names for the rest
#   supp-delete  a confirmed leak fragment in a supplementary note (README, comment, docstring): delete it
#   supp-remove  junk, agent files, run logs: leave them out of the staged copy
#   repack       archive metadata (zip, gz, tar times and owners; gzip headers): the deterministic re-pack
FIX_CLASSES = ("undo", "xref-ref", "xref-cite", "rebuild", "delete", "delete-sentence", "marker", "escape", "meta",
               "supp-delete", "supp-remove", "repack")
_FIX_ORDER = {c: i for i, c in enumerate(FIX_CLASSES)}
# definite findings whose fragment the loop deletes
_FIX_DELETE_DEFINITE = ("ENG-VER", "ENG-PATH", "ENG-NET", "ENG-OPS", "ENG-SECRET")
# candidates whose fragment the loop deletes once a reviewer ruled them `leak`
_FIX_DELETE_CONFIRMED = ("ENG-HW", "ENG-QTY")
_FIX_MARKER_RE = re.compile(r"\bTODO\b|\bFIXME\b|\bXXX+\b|\[VERIFY\]|\bTKTK\b")
_META_FIX_CHECKS = ("META-INFO", "META-TZ", "META-PTEX")
# The preamble lines a `meta` fix may add (pdfTeX; each is content-free).
META_PREAMBLE_LINES = (
    "\\hypersetup{pdfauthor={},pdftitle={},pdfsubject={},pdfkeywords={},pdfcreator={},pdfproducer={}}",
    "\\pdfinfoomitdate=1", "\\pdfsuppressptexinfo=-1", "\\pdftrailerid{}")
# Findings that end the fix loop at once while they stay at WARN or BLOCK.
STOP_CHECKS = ("NUM-DRIFT", "CONFIG-CHANGED")
# Never in the fix queue or the plan's to-do list: user configuration, coverage
# gaps, stale builds, and findings whose policy lives in another skill.
_NO_FIX_PREFIXES = ("SKIP-", "ALLOW-", "ANON-LIST-", "BUILD-STALE", "LOG-OVERFULL")
# The FIX family (the loop's own damage) is undone first.
UNDO_CHECKS = ("FIX-REGRESSION", "FIX-EDIT")

# The build log is the compiler's own statement: an allow-list line cannot
# exempt it (fix the build instead). XREF-PDF-QQ is exemptable only per page.
NON_EXEMPTABLE = ("XREF-LOG-REF", "XREF-LOG-CITE", "XREF-LOG-UNDEF", "XREF-LOG-RERUN", "LOG-ERROR")
EXEMPT_NEEDS_PAGE = ("XREF-PDF-QQ", "XREF-PDF-CITE")

BUILTIN_EXEMPTIONS = (
    "References region: ENG, PROC, ANON-LINK, ANON-SELFCITE are not reported; ANON-NAME and ANON-EMAIL are INFO.",
    "Compute-resources, checklist and related-work sections: ENG-HW, ENG-QTY, ENG-FW are INFO and still go to the "
    "reviewer as low-priority candidates (a 'leak' ruling restores the confirmed level).",
    "Model-id shapes (Llama-3.1-8B, Qwen2.5-7B, Mistral-7B-v0.3, GPT-4o) are not library versions; major-only versions ('Python 3') are not flagged.",
    "Numeric precision and method parameters (bf16, fp16, fp8, int8, TF32, mixed precision, batch size, "
    "single-threaded) are not flagged unless policy precision_disclosure is 'candidate'.",
    "Registration amendment, addendum, and clarification labels are not reported (files named so are INFO) unless "
    "policy registration_labels is 'flag'.",
    "The template running header ('Under review as a conference paper at ...') is not process narration.",
    "Dates in an Accessed/Retrieved/last-visited or posted/published/released-after context are exempt.",
    "Dependency declarations, install commands, and versions inside the supplement are not reported; hardware, OS, and "
    "host words in its notes are candidates at the hardware level (SUPP-HW), INFO with policy supp_hardware: info.",
    "??? and longer question-mark runs are not reference failures; a ?? in reference context (Table ??, (??)) is never exempt.",
    "Text typeset verbatim in the sources (listings, verbatim, \\texttt, table cells) is INFO for TEXT-CODE (the reviewer "
    "still sees it as a low-priority group) and does not count as glued words; an escape glued to words on both sides "
    "('see\\nTable') is never verbatim.",
    "Large-delimiter pieces in the private-use area (U+F8E5-U+F8FF) and listings line-break arrows are not glyph errors.",
    "Font-program %%CreationDate comments inside embedded fonts are not metadata.",
)


# ─── Small utilities ──────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _rel(path: str, base: str) -> str:
    """Path relative to `base` with '/' separators ('../' for outside files).
    Absolute only when no relative path exists (Windows cross-drive), which the
    assurance contract allows for files outside the paper directory."""
    try:
        rel = os.path.relpath(os.path.abspath(path), os.path.abspath(base))
    except ValueError:
        return os.path.abspath(path).replace(os.sep, "/")
    return rel.replace(os.sep, "/")


def _display_path(path: str, base: str) -> str:
    """A label for reports: relative when the file is at most two levels above
    `base`, else '…/<parent>/<name>' — a deep '../../../..' chain or another
    drive would only print the user's directory layout."""
    rel = _rel(path, base)
    if not (rel.startswith("../../../") or os.path.isabs(rel) or re.match(r"^[A-Za-z]:/", rel)):
        return rel
    parts = [p for p in rel.replace("\\", "/").split("/") if p and p != ".."]
    return "…/" + "/".join(parts[-2:])


def _is_within(path: str, base: str) -> bool:
    try:
        rp, rb = os.path.realpath(path), os.path.realpath(base)
        return os.path.commonpath([rp, rb]) == rb
    except ValueError:
        return False


def _write_atomic(path: str, text: str) -> None:
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp-", suffix=".part")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(tmp)
        raise


def _collapse_ws(s: Optional[str]) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _norm_key(s: Optional[str]) -> str:
    return _collapse_ws(unicodedata.normalize("NFKC", s or "")).casefold()


def _mtime(path: Optional[str]) -> Optional[float]:
    try:
        return os.path.getmtime(path) if path else None
    except OSError:
        return None


def _sev_max(a: str, b: str) -> str:
    return a if _SEV_RANK[a] >= _SEV_RANK[b] else b


def _excerpt(text: str, start: int, end: int, width: int = 70) -> str:
    a, b = max(0, start - width), min(len(text), end + width)
    ex = _collapse_ws(text[a:b])
    return ("…" if a > 0 else "") + ex + ("…" if b < len(text) else "")


# ─── Folding, term matching, redaction ───────────────────────────────────────

_CJK_CLASS = "\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uf900-\ufaff"
_CJK_RE = re.compile("[" + _CJK_CLASS + "]")
_DASHES = "\u2010\u2011\u2012\u2013\u2014\u2212"
_FOLD_CACHE: Dict[str, str] = {}


def _fold_char(c: str) -> str:
    r = _FOLD_CACHE.get(c)
    if r is None:
        if c in _DASHES:
            r = "-"
        else:
            base = "".join(x for x in unicodedata.normalize("NFKD", c) if not unicodedata.combining(x))
            r = base.lower()[:1] if base else " "
            if not r:
                r = " "
        _FOLD_CACHE[c] = r
    return r


_FOLD_TABLE: Dict[int, str] = {}
_FOLD_SEEN: Set[str] = set()


def fold_text(s: str) -> str:
    """Length-preserving case and accent fold: offsets in the result are offsets in `s`."""
    if s.isascii():  # fast path: every ASCII character folds to its own lower case
        return s.lower()
    for c in set(s) - _FOLD_SEEN:  # a translation table grows with the characters seen
        _FOLD_SEEN.add(c)
        f = _fold_char(c)
        if f != c:
            _FOLD_TABLE[ord(c)] = f
    return s.translate(_FOLD_TABLE)


class TermMatcher:
    """Case-insensitive, accent-insensitive, word-bounded term matching where a
    hyphen and a space are equivalent. CJK terms match as substrings (with
    optional spaces between ideographs, which some extractors insert), and a
    CJK neighbour never blocks the word boundary of a Latin term."""

    def __init__(self, terms: Sequence[Tuple[str, str]]):
        self.entries: List[Tuple[str, Any]] = []
        for label, term in terms:
            term = (term or "").strip()
            if not term:
                continue
            parts = [p for p in re.split(r"[-\s]+", fold_text(term)) if p]
            if not parts:
                continue
            pieces = [(r"\s*".join(re.escape(c) for c in p) if _CJK_RE.search(p) else re.escape(p)) for p in parts]
            body = r"[-\s]*".join(pieces) if _CJK_RE.search(term) else r"[-\s]+".join(pieces)
            # the body starts with a literal, so the regex engine can skip ahead
            # fast; the word boundaries are checked on each (rare) match instead
            # of as a lookbehind tried at every position of a large text
            self.entries.append((label, re.compile(body), not _CJK_RE.match(parts[0]),
                                 not _CJK_RE.match(parts[-1][-1])))

    def __bool__(self) -> bool:
        return bool(self.entries)

    def finditer(self, text: str, folded: Optional[str] = None) -> List[Tuple[int, int, str]]:
        if not self.entries or not text:
            return []
        f = folded if folded is not None else fold_text(text)
        n = len(f)
        out = []
        for label, rx, lead, tail in self.entries:
            pos = 0
            while True:
                m = rx.search(f, pos)
                if m is None:
                    break
                s, e = m.span()
                if (lead and s > 0 and _is_word_not_cjk(f[s - 1])) or (tail and e < n and _is_word_not_cjk(f[e])):
                    pos = s + 1
                    continue
                out.append((s, e, label))
                pos = max(e, s + 1)
        out.sort()
        return out


def _is_word_not_cjk(c: str) -> bool:
    return (c.isalnum() or c == "_") and not _CJK_RE.match(c)


# Each pattern starts with its literal prefix (the regex engine then skips
# ahead fast in large files); the word boundary before it is a lookbehind.
_SECRET_RES = [
    (re.compile(r"sk-(?<![A-Za-z0-9_]sk-)(?:ant-|proj-)?[A-Za-z0-9_-]{16,}"), None),
    (re.compile(r"gh(?<![A-Za-z0-9_]gh)[pousr]_[A-Za-z0-9]{20,}"), None),
    (re.compile(r"github_pat_(?<![A-Za-z0-9_]github_pat_)[A-Za-z0-9_]{20,}"), None),
    (re.compile(r"hf_(?<![A-Za-z0-9_]hf_)[A-Za-z0-9]{20,}"), None),
    (re.compile(r"AKIA(?<![A-Za-z0-9_]AKIA)[0-9A-Z]{16}(?![A-Za-z0-9_])"), None),
    (re.compile(r"xox(?<![A-Za-z0-9_]xox)[abprs]-[A-Za-z0-9-]{10,}"), None),
    (re.compile(r"AIza(?<![A-Za-z0-9_]AIza)[0-9A-Za-z_-]{35}(?![A-Za-z0-9_])"), None),
    (re.compile(r"glpat-(?<![A-Za-z0-9_]glpat-)[A-Za-z0-9_-]{20,}"), None),
]
# key = value: a quoted literal, or (for the specific key names) an unquoted
# token that is not an attribute chain or a call ("settings.API_KEY",
# "tokenizer.eos_token_id", "token=posterior_tokens" are code, not secrets).
_SECRET_KV_RE = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|auth[_-]?token|secret[_-]?key|client[_-]?secret|bearer|token|secret|"
    r"password|passwd)[\"']?\s*[:=]\s*(?:([\"'])([^\"'\s]{12,200})\2|([A-Za-z0-9+/_=-]{16,200})(?![\w.(\[]))")
_SECRET_GENERIC_KEYS = {"token", "secret", "password", "passwd", "bearer"}
_SECRET_PLACEHOLDER_RE = re.compile(r"your|xxx|example|placeholder|change[-_]?me|dummy|redacted|insert|<|>|\$\{|%\(|"
                                    r"environ|getenv|\.\.\.", re.I)
_SECRET_WORDS_RE = re.compile(r"[A-Za-z]+\d{0,3}(?:[_.-][A-Za-z]+\d{0,3})*")


def _entropy(s: str) -> float:
    c = Counter(s)
    n = float(len(s))
    return -sum((k / n) * math.log2(k / n) for k in c.values())


def _secret_value_ok(value: str) -> bool:
    """A value that looks like a credential: letters and digits, no
    placeholder words, not plain words joined by '_' / '-', and random enough."""
    if _SECRET_PLACEHOLDER_RE.search(value) or "." in value:
        return False
    if not (re.search(r"\d", value) and re.search(r"[A-Za-z]", value)):
        return False
    if _SECRET_WORDS_RE.fullmatch(value):
        return False
    return _entropy(value) >= 3.0


def _mask_secret(s: str) -> str:
    return s[:4] + "…[REDACTED]"


def find_secrets(text: str) -> List[Tuple[int, int]]:
    spans = []
    for rx, grp in _SECRET_RES:
        for m in rx.finditer(text):
            if grp:
                spans.append((m.start(grp), m.end(grp)))
            else:
                spans.append((m.start(), m.end()))
    for m in _SECRET_KV_RE.finditer(text):
        quoted = m.group(3) is not None
        if not quoted and m.group(1).lower().replace("-", "_") in _SECRET_GENERIC_KEYS:
            continue  # a bare `token=x` is far more often code than a credential
        g = 3 if quoted else 4
        if _secret_value_ok(m.group(g)) and not any(a <= m.start(g) < b for a, b in spans):
            spans.append((m.start(g), m.end(g)))
    return spans


class Redactor:
    """Replaces identity terms ([ANON#line]), auto identity terms ([AUTO#n]),
    deny-list terms ([DENY#n]) and secrets (first 4 chars) in any output text."""

    def __init__(self, identity: Optional[TermMatcher] = None, auto: Optional[TermMatcher] = None,
                 deny: Optional[TermMatcher] = None):
        self.matchers = [(identity, "ANON"), (auto, "AUTO"), (deny, "DENY")]

    def spans(self, text: str) -> List[Tuple[int, int, str]]:
        if not text:
            return []
        folded = None
        spans: List[Tuple[int, int, str]] = []
        for matcher, tag in self.matchers:
            if matcher:
                if folded is None:
                    folded = fold_text(text)
                for s, e, label in matcher.finditer(text, folded):
                    spans.append((s, e, "[%s#%s]" % (tag, label)))
        for s, e in find_secrets(text):
            spans.append((s, e, _mask_secret(text[s:e])))
        return spans

    def redact(self, text: Optional[str]) -> str:
        if not text:
            return text or ""
        spans = self.spans(text)
        if not spans:
            return text
        spans.sort(key=lambda x: (x[0], -(x[1] - x[0])))
        out, pos = [], 0
        for s, e, rep in spans:
            if s < pos:
                continue
            out.append(text[pos:s])
            out.append(rep)
            pos = e
        out.append(text[pos:])
        return "".join(out)


# ─── Configuration ───────────────────────────────────────────────────────────

POLICY_KEYS = {
    "venue", "anonymous", "page_limit", "fill_page", "fill_threshold", "end_matter", "hardware", "framework",
    "supp_hardware", "strict", "supp_max_mb", "metadata_policy", "exempt_terms", "extra_deny", "region_headings",
    "body_end_markers", "declared_ai_uses", "notes", "precision_disclosure", "registration_labels",
    "skeleton_result_words",
}
# user policy switches with community-friendly defaults (the first value)
PRECISION_POLICIES = ("exempt", "candidate")
REGISTRATION_POLICIES = ("keep", "flag")
_ALLOW_PROVENANCE = re.compile(r"^(?:human|cross-family-review):\S+$")
_AUTO_STOP = {
    "user", "users", "ubuntu", "root", "admin", "administrator", "runner", "jovyan", "vagrant",
    "ec2-user", "debian", "guest", "test", "tester", "builder", "build", "docker", "nobody",
    "default", "owner", "student", "researcher", "dev", "developer", "codespace", "vscode",
    "node", "app", "host", "local", "localhost", "home", "anonymous", "admin1", "github",
}


def parse_identity_list(text: str) -> Tuple[List[Tuple[str, str]], List[Tuple[int, str]]]:
    """(terms as (line_no, term), too-short terms as (line_no, reason)). CJK
    terms need >= 2 characters, others >= 3."""
    terms, short = [], []
    for i, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        minimum = 2 if _CJK_RE.search(line) else 3
        if len(line) < minimum:
            short.append((i, "term shorter than %d characters ignored" % minimum))
            continue
        terms.append((str(i), line))
    return terms, short


_WHERE_RE = re.compile(r"^(page|file|member)=(\S.*)$")


def _literal_len(rx: str) -> int:
    """Rough count of the literal characters a regex requires."""
    s = re.sub(r"\\[bBdDwWsSAZ]", "", rx)
    s = re.sub(r"\[(?:\\.|[^\]])*\]", "", s)
    s = re.sub(r"\{\d+(?:,\d*)?\}", "", s)
    s = re.sub(r"\(\?(?:[:=!]|<[=!])", "", s)
    s = re.sub(r"\\(.)", r"\1", s)
    return len(re.sub(r"[.^$*+?()|]", "", s))


def _parse_where(spec: str) -> Optional[Dict[str, Any]]:
    m = _WHERE_RE.match(spec.strip())
    if not m:
        return None
    kind, val = m.group(1), m.group(2).strip()
    if kind == "page":
        pages = [int(x) for x in re.split(r"[,\s]+", val) if x.isdigit()]
        return {"page": pages} if pages else None
    if kind == "file":
        f, _, line = val.partition(":")
        return {"file": f, "line": int(line) if line.isdigit() else None}
    return {"member": val}


def parse_allow(text: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Parse allow.tsv: check_glob<TAB>regex<TAB>approved_by<TAB>reason[<TAB>where].
    `where` is page=N[,M] | file=path[:line] | member=glob and scopes the line to
    those locations. Runs of 2+ spaces are accepted as a separator when a line
    has no tabs. Lines that would exempt too much are refused (ALLOW-INVALID):
    a '*' glob, a regex that matches the empty string or has fewer than three
    literal characters, any build-log XREF check, and a printed ?? or [?]
    without a page."""
    entries, issues = [], []
    for i, raw in enumerate(text.splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        cols = [c.strip() for c in re.split(r"\t+", raw.strip())]
        if len(cols) < 4:
            cols = [c.strip() for c in re.split(r"\s{2,}", raw.strip())]
        if len(cols) < 4:
            issues.append({"line": i, "problem": "expected 4 tab-separated columns: check_glob, regex, approved_by, reason"})
            continue
        where = None
        if len(cols) >= 5 and _WHERE_RE.match(cols[-1]):
            where = _parse_where(cols[-1])
            if where is None:
                issues.append({"line": i, "problem": "where must be page=N[,M], file=path[:line] or member=glob"})
                continue
            cols = cols[:-1]
        glob_, rx, who, reason = cols[0], cols[1], cols[2], " ".join(cols[3:]).strip()
        if not _ALLOW_PROVENANCE.match(who):
            issues.append({"line": i, "problem": "approved_by must be human:<id> or cross-family-review:<thread-or-agent-id>"})
            continue
        if not reason:
            issues.append({"line": i, "problem": "reason is empty"})
            continue
        try:
            compiled = re.compile(rx)
        except re.error as e:
            issues.append({"line": i, "problem": "invalid regex: %s" % e})
            continue
        problem = None
        if glob_.strip("*?-") == "":
            problem = "check_glob must name a check or a family, not every check"
        elif compiled.search("") is not None or _literal_len(rx) < 3:
            problem = "regex is too broad (it matches the empty string or has fewer than 3 literal characters)"
        elif any(fnmatch.fnmatchcase(c, glob_) for c in NON_EXEMPTABLE):
            problem = "build-log findings cannot be exempted; fix the build (%s)" % ", ".join(
                c for c in NON_EXEMPTABLE if fnmatch.fnmatchcase(c, glob_))
        elif not (where and where.get("page")) and any(fnmatch.fnmatchcase(c, glob_) for c in EXEMPT_NEEDS_PAGE):
            problem = "a printed ?? or [?] can only be exempted on named pages (add a where column: page=N)"
        if problem:
            issues.append({"line": i, "problem": problem})
            continue
        entries.append({"line": i, "check_glob": glob_, "regex": rx, "_rx": compiled, "where": where,
                        "approved_by": who, "reason": reason, "used": 0})
    return entries, issues


def load_config(config_dir: str, anon_names: Optional[str] = None, allow: Optional[str] = None,
                policy: Optional[str] = None) -> Dict[str, Any]:
    paths = {
        "anon_names": anon_names or os.path.join(config_dir, "anon-names.txt"),
        "allow": allow or os.path.join(config_dir, "allow.tsv"),
        "policy": policy or os.path.join(config_dir, "policy.json"),
    }
    cfg: Dict[str, Any] = {"paths": paths, "exists": {}, "sha256": {}, "issues": []}
    for k, p in paths.items():
        ok = os.path.isfile(p)
        cfg["exists"][k] = ok
        cfg["sha256"][k] = _sha256_file(p) if ok else None
    terms, short = ([], [])
    if cfg["exists"]["anon_names"]:
        terms, short = parse_identity_list(_read_text(paths["anon_names"]))
    cfg["identity_terms"], cfg["identity_short"] = terms, short
    entries, issues = ([], [])
    if cfg["exists"]["allow"]:
        entries, issues = parse_allow(_read_text(paths["allow"]))
    cfg["allow_entries"], cfg["allow_issues"] = entries, issues
    pol: Dict[str, Any] = {}
    if cfg["exists"]["policy"]:
        try:
            pol = json.loads(_read_text(paths["policy"]))
        except ValueError as e:
            raise UsageError("policy file is not valid JSON: %s" % e) from None
        if not isinstance(pol, dict):
            raise UsageError("policy file must hold a JSON object")
    cfg["policy"] = pol
    cfg["policy_unknown_keys"] = sorted(k for k in pol if k not in POLICY_KEYS)
    return cfg


def derived_usernames(terms: Sequence[Tuple[str, str]]) -> Set[str]:
    """The logins an identity term that is a person's name commonly becomes
    (first initial and last name, first and last name, with a dot or an
    underscore, last name and first initial): the supplement scan reports one
    only in front of an '@' (an account), never as a word of prose."""
    out: Set[str] = set()
    for _label, term in terms:
        words = [w.lower() for w in re.findall(r"[A-Za-z]+", fold_text(term or "")) if len(w) > 1]
        if not 2 <= len(words) <= 4:
            continue
        first, last = words[0], words[-1]
        for u in (first[0] + last, first + last, first + "." + last, first + "_" + last, last + first[0]):
            if len(u) >= 4:
                out.add(u)
    return out


def auto_identity_terms() -> List[str]:
    """git user.name/user.email (+ local part) and the OS user name; generic
    account names and terms shorter than 3 characters (2 for CJK) are dropped.
    Only ever printed as [AUTO#n]."""
    found: List[str] = []
    for key in ("user.name", "user.email"):
        try:
            # bytes, decoded as UTF-8: git stores config in UTF-8, while text=True
            # would decode with the locale code page on Windows (mojibake names)
            r = subprocess.run(["git", "config", "--get", key], capture_output=True, timeout=5)
            out_b = r.stdout or b""
            v = (out_b.decode("utf-8", errors="replace") if isinstance(out_b, bytes) else str(out_b)).strip()
        except (OSError, subprocess.SubprocessError):
            v = ""
        if v:
            found.append(v)
            if key == "user.email" and "@" in v:
                found.append(v.split("@", 1)[0])
    with contextlib.suppress(Exception):
        found.append(getpass.getuser())
    out, seen = [], set()
    for t in found:
        t = t.strip()
        k = t.casefold()
        if len(t) < (2 if _CJK_RE.search(t) else 3) or k in _AUTO_STOP or k in seen:
            continue
        seen.add(k)
        out.append(t)
    return out


class UsageError(Exception):
    pass


# ─── LaTeX sources ───────────────────────────────────────────────────────────

_VERB_ENVS = ("verbatim", "verbatim*", "Verbatim", "BVerbatim", "LVerbatim", "lstlisting",
              "minted", "alltt", "spverbatim", "comment")
_BEGIN_VERB_RE = re.compile(r"\\begin\s*\{(" + "|".join(re.escape(e) for e in _VERB_ENVS) + r")\}")
_INLINE_VERB_RE = re.compile(r"\\(?:verb\*?|lstinline(?:\[[^\]]*\])?|mintinline\{[^}]*\})([^\sA-Za-z{])")
_COND_RE = re.compile(r"\\(?:iffalse|else|fi|if(?!f\b|thenelse)[a-zA-Z@]*)(?![a-zA-Z@])")


def strip_tex_comments(line: str) -> str:
    """Drop an unescaped % comment; \\verb|..| spans are respected."""
    i, n = 0, len(line)
    while i < n:
        c = line[i]
        if c == "\\":
            m = _INLINE_VERB_RE.match(line, i)
            if m:
                close = line.find(m.group(1), m.end())
                i = n if close < 0 else close + 1
                continue
            i += 2
            continue
        if c == "%":
            return line[:i]
        i += 1
    return line


def _load_tex_file(path: str) -> List[Tuple[str, bool]]:
    """Per-line (text, is_verbatim) with comments, comment environments and
    \\iffalse...\\fi blocks blanked (line numbers are preserved)."""
    raw_lines = _read_text(path).splitlines()
    out: List[Tuple[str, bool]] = []
    verb_env: Optional[str] = None
    for line in raw_lines:
        if verb_env:
            env = verb_env
            end_tok = "\\end{%s}" % env
            if end_tok in line:
                verb_env = None
                if env == "comment":
                    out.append((strip_tex_comments(line.split(end_tok, 1)[1]), False))
                else:
                    out.append((line, True))
            else:
                out.append(("", False) if env == "comment" else (line, True))
            continue
        text = strip_tex_comments(line)
        m = _BEGIN_VERB_RE.search(text)
        if m:
            env = m.group(1)
            end_tok = "\\end{%s}" % env
            rest = text[m.end():]
            if end_tok in rest:  # one-line environment
                if env == "comment":
                    out.append((text[:m.start()] + rest.split(end_tok, 1)[1], False))
                else:
                    out.append((text, True))
            else:
                verb_env = env
                out.append((text[:m.start()], False) if env == "comment" else (text, True))
            continue
        out.append((text, False))
    # \iffalse ... \else ... \fi (nesting-aware; only the false branch is dropped)
    depth, skipping = 0, False
    result: List[Tuple[str, bool]] = []
    for text, verb in out:
        if verb or (depth == 0 and "\\iffalse" not in text):
            result.append((text, verb))
            continue
        keep, pos = [], 0
        for m in _COND_RE.finditer(text):
            tok = m.group(0)
            if depth == 0:
                if tok == "\\iffalse":
                    keep.append(text[pos:m.start()])
                    depth, skipping, pos = 1, True, m.end()
                continue
            if tok == "\\fi":
                depth -= 1
                if depth == 0:
                    if not skipping:
                        keep.append(text[pos:m.start()])
                    pos, skipping = m.end(), False
            elif tok == "\\else":
                if depth == 1 and skipping:
                    skipping, pos = False, m.end()
            else:  # any nested conditional, including another \iffalse
                depth += 1
        if depth == 0 or not skipping:
            keep.append(text[pos:])
        result.append(("".join(keep), False))
    return result


_INCLUDE_ONE_RE = re.compile(r"\\(input|include|subfile)\s*\{([^{}]+)\}")
_INCLUDE_TWO_RE = re.compile(r"\\(import|subimport|inputfrom|subinputfrom|includefrom|subincludefrom)\*?\s*\{([^{}]*)\}\s*\{([^{}]+)\}")
_INCLUDE_BARE_RE = re.compile(r"\\input\s+([^\s{}\\%]+)")


def _resolve_tex(name: str, bases: Sequence[str]) -> Optional[str]:
    name = name.strip()
    if not name:
        return None
    cands = [name] if name.endswith(".tex") else [name + ".tex", name]
    for base in bases:
        for c in cands:
            p = c if os.path.isabs(c) else os.path.join(base, c)
            if os.path.isfile(p):
                return p
    return None


def expand_tex(main_path: str, paper_dir: str, max_files: int = 500) -> Dict[str, Any]:
    """Expand \\input/\\include/\\subfile/\\import/\\subimport recursively (cycle
    safe). Returns lines [{'text','file','line','verbatim'}] plus file lists."""
    main_dir = os.path.dirname(os.path.abspath(main_path))
    lines: List[Dict[str, Any]] = []
    files: List[str] = []
    missing: List[str] = []
    cycles: List[str] = []

    def visit(path: str, stack: Tuple[str, ...], cur_dir: str) -> None:
        real = os.path.realpath(path)
        if real in stack:
            cycles.append(_rel(path, paper_dir))
            return
        if len(files) >= max_files:
            return
        files.append(path)
        rel = _rel(path, paper_dir)
        for lineno, (text, verb) in enumerate(_load_tex_file(path), 1):
            if verb:
                lines.append({"text": text, "file": rel, "line": lineno, "verbatim": True})
                continue
            events = []
            for m in _INCLUDE_ONE_RE.finditer(text):
                events.append((m.start(), m.end(), m.group(2), None, m.group(1)))
            for m in _INCLUDE_TWO_RE.finditer(text):
                events.append((m.start(), m.end(), m.group(3), m.group(2), m.group(1)))
            for m in _INCLUDE_BARE_RE.finditer(text):
                if not any(s <= m.start() < e for s, e, *_ in events):
                    events.append((m.start(), m.end(), m.group(1), None, "input"))
            events.sort()
            pos = 0
            for s, e, name, sub, kind in events:
                if s < pos:
                    continue
                before = text[pos:s]
                if before.strip():
                    lines.append({"text": before, "file": rel, "line": lineno, "verbatim": False})
                if sub is not None:
                    base = cur_dir if kind.startswith("sub") else main_dir
                    new_dir = os.path.normpath(sub if os.path.isabs(sub) else os.path.join(base, sub))
                    target = _resolve_tex(name, [new_dir])
                    next_dir = new_dir
                else:
                    target = _resolve_tex(name, [cur_dir, main_dir])
                    next_dir = cur_dir
                if target:
                    visit(target, stack + (real,), next_dir)
                elif kind != "input" or "/" in name:  # bare \input{x} may be a TeX-tree file
                    missing.append(name)
                pos = e
            lines.append({"text": text[pos:], "file": rel, "line": lineno, "verbatim": False})

    visit(main_path, tuple(), main_dir)
    return {"lines": lines, "files": files, "missing": sorted(set(missing)), "cycles": cycles,
            "main_dir": main_dir}


def _balanced_arg(text: str, start: int) -> Tuple[Optional[str], int]:
    """Content of the {...} group starting at text[start] == '{'."""
    if start >= len(text) or text[start] != "{":
        return None, start
    depth, i = 0, start
    while i < len(text):
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1:i], i + 1
        i += 1
    return None, start


_REF_RE = re.compile(r"\\(?:ref|Ref|cref|Cref|autoref|Autoref|eqref|pageref|nameref|Nameref|vref|Vref|"
                     r"cpageref|Cpageref|labelcref|namecref|nameCref|lcnamecref|zcref|zref|subref|thmref)"
                     r"\*?\s*(?:\[[^\]]*\]\s*)?\{([^{}]*)\}")
_REF_RANGE_RE = re.compile(r"\\(?:cref|Cref|cpageref|Cpageref)range\*?\s*\{([^{}]*)\}\s*\{([^{}]*)\}")
_HYPERREF_RE = re.compile(r"\\hyperref\s*\[([^\]]+)\]")
_LABEL_RE = re.compile(r"\\(?:label|zlabel)\s*(?:\[[^\]]*\]\s*)?\{([^{}]*)\}")
_OPT_LABEL_RE = re.compile(r"\blabel\s*=\s*\{?([^,\]}\s]+)")
_CITE_RE = re.compile(r"\\(?:[Cc]ite[a-zA-Z]*|[a-z]*cite[a-z]*|nocite|[Pp]arencite|[Tt]extcite|[Aa]utocite|"
                      r"[Ff]ootcite|[Ss]martcite|[Ss]upercite|fullcite)\*?\s*(?:\[[^\]]*\]\s*){0,2}\{([^{}]*)\}")
_BIBLIO_RE = re.compile(r"\\bibliography\s*\{([^{}]*)\}")
_ADDBIB_RE = re.compile(r"\\(?:addbibresource|addglobalbib|bibliography\*?)\s*(?:\[[^\]]*\])?\s*\{([^{}]*)\}")
_BIBITEM_RE = re.compile(r"\\bibitem\s*(?:\[[^\]]*\])?\s*\{([^{}]+)\}")
_BIB_ENTRY_RE = re.compile(r"@(\w+)\s*[{(]\s*([^,\s{}()]+)\s*,")
_BBL_ENTRY_RE = re.compile(r"\\entry\{([^{}]+)\}")
_GRAPHICS_RE = re.compile(r"\\includegraphics\s*(?:\[[^\]]*\]\s*)?\{([^{}]+)\}")
_GRAPHICSPATH_RE = re.compile(r"\\graphicspath\s*\{((?:\{[^{}]*\}\s*)+)\}")
_USEPKG_RE = re.compile(r"\\(?:usepackage|RequirePackage|documentclass)\s*(?:\[[^\]]*\])?\s*\{([^{}]+)\}")
_BIBSTYLE_RE = re.compile(r"\\bibliographystyle\s*\{([^{}]+)\}")


def _split_keys(s: str) -> List[str]:
    return [k.strip() for k in s.split(",") if k.strip()]


def parse_aux(paths: Iterable[str]) -> Dict[str, Set[str]]:
    labels: Set[str] = set()
    bibcites: Set[str] = set()
    seen: Set[str] = set()
    todo = [p for p in paths if p]
    while todo:
        p = todo.pop()
        if p in seen or not os.path.isfile(p):
            continue
        seen.add(p)
        text = _read_text(p)
        for m in re.finditer(r"\\newlabel\{([^{}]+)\}", text):
            key = m.group(1)
            labels.add(key[:-5] if key.endswith("@cref") else key)
        for m in re.finditer(r"\\bibcite\{([^{}]+)\}", text):
            bibcites.add(m.group(1))
        for m in re.finditer(r"\\@input\{([^{}]+)\}", text):
            todo.append(os.path.join(os.path.dirname(p), m.group(1)))
    return {"labels": labels, "bibcites": bibcites}


def parse_bib(path: str) -> Dict[str, str]:
    text = _read_text(path)
    entries: Dict[str, str] = {}
    matches = list(_BIB_ENTRY_RE.finditer(text))
    for i, m in enumerate(matches):
        if m.group(1).lower() in ("string", "preamble", "comment"):
            continue
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        entries[m.group(2)] = text[m.start():end]
    return entries


def parse_bbl(path: str) -> Set[str]:
    text = _read_text(path)
    return {m.group(1) for m in _BIBITEM_RE.finditer(text)} | {m.group(1) for m in _BBL_ENTRY_RE.finditer(text)}


def static_xref(expanded: Dict[str, Any], aux: Dict[str, Set[str]], bib_keys: Optional[Set[str]]) -> Dict[str, Any]:
    """Set difference of referenced vs defined labels and cited vs defined keys
    (works without a log — e.g. tectonic, which keeps none by default)."""
    refs: Dict[str, Tuple[str, int]] = {}
    ref_places: Dict[str, List[Tuple[str, int]]] = {}  # every place a key is referenced (a fix changes them all)
    labels: Set[str] = set()
    cites: Dict[str, Tuple[str, int]] = {}

    def ref_at(k: str, loc: Tuple[str, int]) -> None:
        refs.setdefault(k, loc)
        places = ref_places.setdefault(k, [])
        if loc not in places and len(places) < 50:
            places.append(loc)
    cite_sizes: Dict[str, int] = {}  # key -> most keys it shares one \cite with (a dangling key among others)
    bibitems: Set[str] = set()
    macro_labels = False
    for ln in expanded["lines"]:
        text, loc = ln["text"], (ln["file"], ln["line"])
        if "label" in text and "[" in text:  # \begin{lstlisting}[label=..], \lstinputlisting[label=..]{f}
            for m in _OPT_LABEL_RE.finditer(text):
                labels.add(m.group(1))
        if ln["verbatim"]:
            continue
        for m in _LABEL_RE.finditer(text):
            key = m.group(1).strip()
            if "#" in key or "\\csname" in key:
                macro_labels = True
            elif key:
                labels.add(key)
        for rx in (_REF_RE,):
            for m in rx.finditer(text):
                for k in _split_keys(m.group(1)):
                    if "#" not in k and "\\" not in k:
                        ref_at(k, loc)
        for m in _REF_RANGE_RE.finditer(text):
            for k in (m.group(1).strip(), m.group(2).strip()):
                if k and "#" not in k and "\\" not in k:
                    ref_at(k, loc)
        for m in _HYPERREF_RE.finditer(text):
            k = m.group(1).strip()
            if k and "#" not in k and "\\" not in k:
                ref_at(k, loc)
        for m in _CITE_RE.finditer(text):
            keys = [k for k in _split_keys(m.group(1)) if k != "*" and "#" not in k and "\\" not in k]
            for k in keys:
                cites.setdefault(k, loc)
                cite_sizes[k] = max(cite_sizes.get(k, 0), len(keys))
        for m in _BIBITEM_RE.finditer(text):
            bibitems.add(m.group(1).strip())
    defined_labels = labels | aux.get("labels", set())
    undefined_refs = {k: v for k, v in refs.items() if k not in defined_labels}
    defined_keys: Optional[Set[str]] = None
    if bib_keys is not None or bibitems or aux.get("bibcites"):
        defined_keys = set(bib_keys or set()) | bibitems | aux.get("bibcites", set())
    undefined_cites = ({k: v for k, v in cites.items() if k not in defined_keys}
                       if defined_keys is not None else {})
    return {"refs": refs, "labels": labels, "cites": cites, "undefined_refs": undefined_refs,
            "ref_places": {k: v for k, v in ref_places.items() if k in undefined_refs},
            "undefined_cites": undefined_cites, "macro_labels": macro_labels,
            "bib_known": defined_keys is not None, "cite_sizes": cite_sizes,
            "defined_keys": sorted(defined_keys) if defined_keys is not None else [],
            "defined_labels": sorted(defined_labels)}


# The kind of thing a label names: from cleveref's type in the .aux, from
# hyperref's anchor (figure.caption.3, table.2, section.4), or from the label's
# own prefix (fig:, tab:, sec:). A reference is repaired only towards a label
# of the same kind.
_LABEL_TYPE_PREFIX = {
    "fig": "figure", "figure": "figure", "subfig": "figure", "tab": "table", "table": "table", "tbl": "table",
    "sec": "section", "section": "section", "ssec": "section", "subsec": "section", "sub": "section",
    "app": "section", "appx": "section", "appendix": "section", "apx": "section", "chap": "section",
    "ch": "section", "part": "section", "para": "section", "par": "section",
    "eq": "equation", "eqn": "equation", "equation": "equation", "alg": "algorithm", "algo": "algorithm",
    "algorithm": "algorithm", "line": "line", "lst": "listing", "listing": "listing", "code": "listing",
    "thm": "theorem", "theorem": "theorem", "lem": "theorem", "lemma": "theorem", "prop": "theorem",
    "cor": "theorem", "def": "theorem", "defn": "theorem", "rem": "theorem", "remark": "theorem",
    "assump": "theorem", "asm": "theorem", "claim": "theorem", "conj": "theorem", "ex": "theorem",
    "example": "theorem", "fn": "footnote"}
_ANCHOR_TYPES = {
    "figure": "figure", "subfigure": "figure", "table": "table", "subtable": "table", "section": "section",
    "subsection": "section", "subsubsection": "section", "paragraph": "section", "chapter": "section",
    "part": "section", "appendix": "section", "equation": "equation", "ams@equation": "equation",
    "algorithm": "algorithm", "algocf": "algorithm", "alg@line": "line", "algocfline": "line",
    "lstlisting": "listing", "lstnumber": "line", "footnote": "footnote", "theorem": "theorem", "lemma": "theorem",
    "proposition": "theorem", "corollary": "theorem", "definition": "theorem", "remark": "theorem",
    "assumption": "theorem", "claim": "theorem", "conjecture": "theorem", "example": "theorem"}
_REF_WORD_TYPES = (
    (re.compile(r"(?:Figures?|Figs?\.)\s*~?\s*$", re.I), "figure"),
    (re.compile(r"(?:Tables?|Tabs?\.)\s*~?\s*$", re.I), "table"),
    (re.compile(r"(?:Sections?|Secs?\.|§|Appendix|Appendices|App\.|Chapters?)\s*~?\s*$", re.I), "section"),
    (re.compile(r"(?:Eqs?\.|Equations?)\s*~?\s*\(?\s*$", re.I), "equation"),
    (re.compile(r"(?:Algorithms?|Alg\.)\s*~?\s*$", re.I), "algorithm"),
    (re.compile(r"(?:Theorems?|Thms?\.|Lemmas?|Propositions?|Props?\.|Corollar(?:y|ies)|Definitions?|Defs?\.|"
                r"Remarks?|Assumptions?|Claims?|Examples?)\s*~?\s*$", re.I), "theorem"),
    (re.compile(r"(?:Lines?)\s*~?\s*$", re.I), "line"),
    (re.compile(r"(?:Listings?)\s*~?\s*$", re.I), "listing"))


def label_prefix_type(key: str) -> Optional[str]:
    m = re.match(r"([A-Za-z]+)[:_.\-]", key or "")
    return _LABEL_TYPE_PREFIX.get(m.group(1).lower()) if m else None


def aux_label_types(paths: Iterable[str]) -> Dict[str, str]:
    """label -> kind, read from the .aux files (cleveref type, else hyperref anchor)."""
    out: Dict[str, str] = {}
    seen: Set[str] = set()
    todo = [p for p in paths if p]
    while todo:
        p = todo.pop()
        if p in seen or not os.path.isfile(p):
            continue
        seen.add(p)
        text = _read_text(p)
        for m in re.finditer(r"\\@input\{([^{}]+)\}", text):
            todo.append(os.path.join(os.path.dirname(p), m.group(1)))
        for m in re.finditer(r"\\newlabel\{([^{}]+)\}", text):
            key, pos = m.group(1), m.end()
            body, _end = _balanced_arg(text, pos)
            if body is None:
                continue
            if key.endswith("@cref"):
                t = re.match(r"\s*\{\s*\[([A-Za-z@]+)\]", body)
                if t:
                    out[key[:-5]] = _ANCHOR_TYPES.get(t.group(1).lower(), t.group(1).lower())
                continue
            groups, i = [], 0
            while i < len(body) and len(groups) < 5:
                if body[i] == "{":
                    g, i = _balanced_arg(body, i)
                    if g is None:
                        break
                    groups.append(g)
                else:
                    i += 1
            if len(groups) >= 4 and groups[3]:
                kind = groups[3].split(".", 1)[0].lower()
                out.setdefault(key, _ANCHOR_TYPES.get(kind, kind))
    return out


def ref_context_type(text_before: str, command: str = "") -> Optional[str]:
    """The kind a reference asks for, from the word in front of it ('Table~\\ref')."""
    if command.startswith("eqref"):
        return "equation"
    tail = re.sub(r"\\[a-zA-Z@]+\*?|[{}]", " ", text_before[-40:])
    for rx, kind in _REF_WORD_TYPES:
        if rx.search(tail.rstrip()):
            return kind
    return None


def xref_fix_target(key: str, line: str, defined: Sequence[str],
                    types: Dict[str, str]) -> Tuple[Optional[str], List[str], Optional[str]]:
    """(target, close labels, kind) for an undefined reference: the one defined
    label of the same kind that is close to the key (a misspelling or a
    rename). No target when the kind is unknown or the choice is not unique."""
    import difflib
    kind = label_prefix_type(key)
    if kind is None and line:
        m = re.search(r"\\(eqref|[A-Za-z]*ref)\*?\s*(?:\[[^\]]*\]\s*)?\{[^{}]*?\b%s\b" % re.escape(key), line)
        if m:
            kind = ref_context_type(line[:m.start()], m.group(1))
    close = difflib.get_close_matches(key, list(defined), n=4, cutoff=0.6)
    same = [c for c in close if kind and (types.get(c) or label_prefix_type(c)) == kind]
    return (same[0] if len(same) == 1 else None), close, kind


def cite_key_note(key: str, x: Dict[str, Any]) -> str:
    """What a fix round needs to decide on a dangling cite key: the closest
    existing keys (a typo is fixed by using one) and how many keys share its
    \\cite (a dangling key among others renders nothing and can be dropped)."""
    import difflib
    bits = []
    close = difflib.get_close_matches(key, x.get("defined_keys") or [], n=3, cutoff=0.75)
    bits.append("closest bibliography keys: %s" % ", ".join(close) if close else "no similar key in the bibliography")
    peers = (x.get("cite_sizes") or {}).get(key, 1)
    if peers > 1:
        bits.append("one of %d keys in its \\cite" % peers)
    return "; ".join(bits)


# ─── Build log and .blg ──────────────────────────────────────────────────────

def unwrap_log(data: bytes, wrap: int = 79) -> str:
    """Undo TeX's hard wrap at max_print_line: a line of exactly `wrap` bytes
    continues on the next line. Decoded as UTF-8 with replacement."""
    out: List[bytes] = []
    buf = b""
    for raw in data.split(b"\n"):
        line = raw[:-1] if raw.endswith(b"\r") else raw
        buf += line
        if wrap > 0 and len(line) == wrap:
            continue
        out.append(buf)
        buf = b""
    if buf:
        out.append(buf)
    return "\n".join(x.decode("utf-8", errors="replace") for x in out)


_Q_OPEN, _Q_CLOSE = "[`'‘\"]", "['’\"]"
_LOG_RULES = [
    ("XREF-LOG-REF", re.compile(r"Reference " + _Q_OPEN + r"([^'’\"]+)" + _Q_CLOSE + r"\s+on\s+page\s+(\d+)\s+undefined")),
    ("XREF-LOG-CITE", re.compile(r"Citation " + _Q_OPEN + r"([^'’\"]+)" + _Q_CLOSE + r"(?:\s+on\s+page\s+(\d+))?\s+undefined")),
    ("XREF-LOG-UNDEF", re.compile(r"There were undefined (references|citations)")),
    ("XREF-LOG-RERUN", re.compile(r"Label\(s\) may have changed|Citation\(s\) may have changed|"
                                  r"Rerun to get (?!outlines\b)[\w\s/-]{1,40}? (?:right|correct)|"
                                  r"Please \(re\)run (?:Biber|BibTeX)|Please rerun LaTeX|"
                                  r"has changed\.\s*Rerun(?! to get outlines)|Rerun LaTeX")),
    ("XREF-LOG-MULTI", re.compile(r"Label " + _Q_OPEN + r"([^'’\"]+)" + _Q_CLOSE + r" multiply defined")),
    ("XREF-LOG-DEST", re.compile(r"pdfTeX warning \(dest\): name\{([^}]+)\} has been referenced but does not exist")),
]
# rerunfilecheck on the .out file: only the PDF bookmarks are stale (WARN)
_LOG_OUTLINES_RE = re.compile(r"Rerun to get outlines right")
_OUTPUT_WRITTEN_RE = re.compile(r"Output written on (.+?\.pdf) \((\d+) pages?")
_LOG_ERROR_RE = re.compile(r"^(?:! .+|!\s?(?:pdfTeX|LuaTeX|XeTeX) error.*|(?:\./)?[^\s:()]+\.(?:tex|sty|cls|ltx|bbl):\d+: .+)$", re.M)
_OVERFULL_RE = re.compile(r"Overfull \\[hv]box \((\d+(?:\.\d+)?)pt too (?:wide|high)\)")
_GLYPH_RES = [re.compile(r"Missing character: There is no (.+?) in font ([^!\n]+)!"),
              re.compile(r"Font Warning: Font shape " + _Q_OPEN + r"([^'’\"]+)" + _Q_CLOSE + r" undefined")]
_BLG_RES = [
    re.compile(r"Warning--I didn't find a database entry for [\"'`]([^\"']+)[\"']"),
    re.compile(r"I couldn't open (?:database|style|auxiliary) file ([^\s]+)"),
    re.compile(r"WARN - I didn't find a database entry for '([^']+)'"),
    re.compile(r"ERROR - Cannot find '([^']+)'"),
    re.compile(r"ERROR - (?:Data source|BibTeX subsystem)[^\n]*"),
]
_LOADED_FILE_RE = re.compile(r"\(([^()\s]+\.(?:sty|cls))\b")


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def scan_log(text: str) -> Dict[str, Any]:
    hits: List[Dict[str, Any]] = []
    for check, rx in _LOG_RULES:
        for m in rx.finditer(text):
            key = m.group(1) if m.groups() and m.group(1) else m.group(0)
            hits.append({"check": check, "match": _collapse_ws(key), "line": _line_of(text, m.start()),
                         "excerpt": _collapse_ws(m.group(0))})
    for m in _LOG_OUTLINES_RE.finditer(text):
        hits.append({"check": "XREF-LOG-RERUN", "match": m.group(0), "line": _line_of(text, m.start()),
                     "excerpt": m.group(0), "outlines": True})
    out_w = list(_OUTPUT_WRITTEN_RE.finditer(text))
    errors = [{"check": "LOG-ERROR", "match": _collapse_ws(m.group(0))[:160], "line": _line_of(text, m.start()),
               "excerpt": _collapse_ws(m.group(0))[:200]} for m in _LOG_ERROR_RE.finditer(text)]
    overs = [float(m.group(1)) for m in _OVERFULL_RE.finditer(text)]
    glyphs = []
    for rx in _GLYPH_RES:
        for m in rx.finditer(text):
            glyphs.append({"check": "LOG-GLYPH", "match": _collapse_ws(m.group(0))[:160],
                           "line": _line_of(text, m.start()), "excerpt": _collapse_ws(m.group(0))[:200]})
    loaded = sorted({os.path.basename(m.group(1)) for m in _LOADED_FILE_RE.finditer(text)})
    return {"hits": hits, "errors": errors, "overfull": overs, "glyphs": glyphs, "loaded": loaded,
            "loaded_paths": sorted({m.group(1) for m in _LOADED_FILE_RE.finditer(text)}),
            "output": ({"pdf": os.path.basename(_collapse_ws(out_w[-1].group(1)).strip('"')),
                        "pages": int(out_w[-1].group(2))} if out_w else None)}


def scan_blg(text: str) -> List[Dict[str, Any]]:
    out = []
    for rx in _BLG_RES:
        for m in rx.finditer(text):
            key = m.group(1) if m.groups() else m.group(0)
            out.append({"check": "XREF-BLG", "match": _collapse_ws(key), "line": _line_of(text, m.start()),
                        "excerpt": _collapse_ws(m.group(0))[:200]})
    return out


# ─── Stdlib PDF object parser (metadata and byte layers) ─────────────────────

class _Name(str):
    __slots__ = ()


class _Kw(str):
    __slots__ = ()


class _PdfString(bytes):
    def text(self) -> str:
        return pdf_string_text(bytes(self))


class _Ref(tuple):
    def __new__(cls, num: int, gen: int):
        return tuple.__new__(cls, (num, gen))


class _PdfError(Exception):
    pass


_WS_BYTES = frozenset(b" \t\r\n\f\x00")
_DELIM_WS = frozenset(b" \t\r\n\f\x00()<>[]{}/%")
_PDF_NUM_RE = re.compile(rb"[+-]?(?:\d+\.?\d*|\.\d+)")
_REF_TAIL_RE = re.compile(rb"[ \t\r\n\f\x00]+(\d+)[ \t\r\n\f\x00]+R(?=[ \t\r\n\f\x00/<>\[\]()%]|$)")
_STR_ESC = {ord("n"): 10, ord("r"): 13, ord("t"): 9, ord("b"): 8, ord("f"): 12,
            ord("("): 0x28, ord(")"): 0x29, ord("\\"): 0x5C}


def pdf_string_text(b: bytes) -> str:
    if b.startswith(b"\xfe\xff"):
        return b[2:].decode("utf-16-be", errors="replace")
    if b.startswith(b"\xff\xfe"):
        return b[2:].decode("utf-16-le", errors="replace")
    if b.startswith(b"\xef\xbb\xbf"):
        return b[3:].decode("utf-8", errors="replace")
    return b.decode("latin-1")


class _PdfLexer:
    def __init__(self, data: bytes, pos: int = 0):
        self.d, self.i, self.n = data, pos, len(data)

    def ws(self) -> None:
        d, i, n = self.d, self.i, self.n
        while i < n:
            c = d[i]
            if c in _WS_BYTES:
                i += 1
            elif c == 0x25:  # % comment
                while i < n and d[i] not in (0x0A, 0x0D):
                    i += 1
            else:
                break
        self.i = i

    def parse(self, depth: int = 0) -> Any:
        if depth > 64:
            raise _PdfError("nesting too deep")
        self.ws()
        d, i = self.d, self.i
        if i >= self.n:
            raise _PdfError("eof")
        c = d[i]
        if c == 0x3C:  # <
            if d[i + 1:i + 2] == b"<":
                self.i = i + 2
                out: Dict[str, Any] = {}
                while True:
                    self.ws()
                    if self.i >= self.n:
                        raise _PdfError("eof in dict")
                    if self.d[self.i:self.i + 2] == b">>":
                        self.i += 2
                        return out
                    key = self.parse(depth + 1)
                    if not isinstance(key, _Name):
                        raise _PdfError("dict key is not a name")
                    self.ws()
                    if self.d[self.i:self.i + 2] == b">>":
                        out[str(key)] = None
                        continue
                    out[str(key)] = self.parse(depth + 1)
            j = d.find(b">", i + 1)
            if j < 0:
                raise _PdfError("eof in hex string")
            hexs = re.sub(rb"[^0-9A-Fa-f]", b"", d[i + 1:j])
            if len(hexs) % 2:
                hexs += b"0"
            self.i = j + 1
            return _PdfString(bytes.fromhex(hexs.decode("ascii")))
        if c == 0x5B:  # [
            self.i = i + 1
            arr: List[Any] = []
            while True:
                self.ws()
                if self.i >= self.n:
                    raise _PdfError("eof in array")
                if self.d[self.i] == 0x5D:
                    self.i += 1
                    return arr
                arr.append(self.parse(depth + 1))
        if c == 0x28:  # (
            return self._literal()
        if c == 0x2F:  # /
            j = i + 1
            while j < self.n and self.d[j] not in _DELIM_WS:
                j += 1
            raw = re.sub(rb"#([0-9A-Fa-f]{2})", lambda m: bytes([int(m.group(1), 16)]), d[i + 1:j])
            self.i = j
            return _Name(raw.decode("latin-1"))
        j = i
        while j < self.n and self.d[j] not in _DELIM_WS:
            j += 1
        tok = d[i:j]
        if not tok:
            self.i = i + 1
            return _Kw(chr(c))
        self.i = j
        if _PDF_NUM_RE.fullmatch(tok):
            if b"." not in tok:
                v = int(tok)
                m = _REF_TAIL_RE.match(d, j)
                if m:
                    self.i = m.end()
                    return _Ref(v, int(m.group(1)))
                return v
            try:
                return float(tok)
            except ValueError:
                return 0.0
        if tok == b"true":
            return True
        if tok == b"false":
            return False
        if tok == b"null":
            return None
        return _Kw(tok.decode("latin-1"))

    def _literal(self) -> _PdfString:
        d, i, n = self.d, self.i + 1, self.n
        depth, out = 1, bytearray()
        while i < n:
            c = d[i]
            if c == 0x5C:
                i += 1
                if i >= n:
                    break
                e = d[i]
                if e in _STR_ESC:
                    out.append(_STR_ESC[e])
                    i += 1
                elif 0x30 <= e <= 0x37:
                    v, j = 0, i
                    while j < n and j < i + 3 and 0x30 <= d[j] <= 0x37:
                        v = v * 8 + (d[j] - 0x30)
                        j += 1
                    out.append(v & 0xFF)
                    i = j
                elif e == 0x0D:
                    i += 1
                    if i < n and d[i] == 0x0A:
                        i += 1
                elif e == 0x0A:
                    i += 1
                else:
                    out.append(e)
                    i += 1
                continue
            if c == 0x28:
                depth += 1
            elif c == 0x29:
                depth -= 1
                if depth == 0:
                    self.i = i + 1
                    return _PdfString(bytes(out))
            out.append(c)
            i += 1
        self.i = n
        return _PdfString(bytes(out))


class PdfObj:
    __slots__ = ("num", "gen", "value", "stream", "pos", "objstm")

    def __init__(self, num: int, gen: int, value: Any, stream: Optional[bytes], pos: int,
                 objstm: Optional[int] = None):
        self.num, self.gen, self.value, self.stream, self.pos, self.objstm = num, gen, value, stream, pos, objstm


class PdfDoc:
    """Objects (incl. object streams), the last trailer, decoded streams."""

    def __init__(self) -> None:
        self.objs: Dict[int, PdfObj] = {}
        self.trailer: Dict[str, Any] = {}
        self.encrypted = False
        self.header_ok = False
        self.errors: List[str] = []
        self.truncated = False
        self.outside_text = ""
        self._decoded: Dict[int, Optional[bytes]] = {}
        self._budget = MAX_PDF_DECODED_BYTES

    def resolve(self, v: Any, depth: int = 0) -> Any:
        while isinstance(v, _Ref) and depth < 32:
            o = self.objs.get(v[0])
            v = o.value if o is not None else None
            depth += 1
        return v

    def stream_data(self, num: int) -> Optional[bytes]:
        if num in self._decoded:
            return self._decoded[num]
        o = self.objs.get(num)
        out = None
        if o is not None and o.stream is not None and isinstance(o.value, dict):
            out = self._decode(o)
        self._decoded[num] = out
        return out

    def _decode(self, o: PdfObj) -> Optional[bytes]:
        d = o.value
        if self.resolve(d.get("Subtype")) == "Image":
            return None
        filt = self.resolve(d.get("Filter"))
        filters = [filt] if isinstance(filt, _Name) else [self.resolve(f) for f in (filt or [])]
        data = o.stream or b""
        for f in filters:
            if f not in ("FlateDecode", "Fl"):
                return None
            if self._budget <= 0:
                self.truncated = True
                return None
            limit = min(MAX_STREAM_BYTES, self._budget)
            try:
                dec = zlib.decompressobj()
                data = dec.decompress(data, limit)
                if dec.unconsumed_tail:
                    self.truncated = True
            except zlib.error:
                return None
            self._budget -= len(data)
        return data


_OBJ_HDR_RE = re.compile(rb"(?<![0-9])(\d{1,10})[ \t\r\n\f\x00]+(\d{1,5})[ \t\r\n\f\x00]+obj\b")


def _skip_ws_bytes(data: bytes, i: int) -> int:
    while i < len(data) and data[i] in _WS_BYTES:
        i += 1
    return i


def parse_pdf_objects(data: bytes) -> PdfDoc:
    """Sequential object scan (streams are skipped by /Length, so object
    headers inside binary streams are never mistaken for objects), object
    streams, and the last trailer / XRef-stream dictionary."""
    doc = PdfDoc()
    doc.header_ok = data[:1024].find(b"%PDF-") >= 0
    pos = 0
    stream_spans: List[Tuple[int, int]] = []
    while True:
        m = _OBJ_HDR_RE.search(data, pos)
        if not m:
            break
        num, gen = int(m.group(1)), int(m.group(2))
        lx = _PdfLexer(data, m.end())
        try:
            val = lx.parse()
        except (_PdfError, ValueError, IndexError):
            e = data.find(b"endobj", m.end())
            pos = e + 6 if e >= 0 else m.end()
            doc.errors.append("object %d unparsable" % num)
            continue
        lx.ws()
        stream = None
        if isinstance(val, dict) and data.startswith(b"stream", lx.i):
            s = lx.i + 6
            if data[s:s + 2] == b"\r\n":
                s += 2
            elif data[s:s + 1] in (b"\n", b"\r"):
                s += 1
            length = val.get("Length")
            end = -1
            if isinstance(length, int) and 0 <= length <= len(data) - s:
                if data.startswith(b"endstream", _skip_ws_bytes(data, s + length)):
                    end = s + length
            if end < 0:
                e = data.find(b"endstream", s)
                end = e if e >= 0 else len(data)
                while end > s and data[end - 1] in (0x0A, 0x0D):
                    end -= 1
            stream = data[s:end]
            stream_spans.append((s, end))
            after = data.find(b"endstream", end)
            pos = after + 9 if after >= 0 else end
        else:
            pos = lx.i
        e = data.find(b"endobj", pos, pos + 512)
        if e >= 0:
            pos = e + 6
        doc.objs[num] = PdfObj(num, gen, val, stream, m.start())
    # object streams
    for o in list(doc.objs.values()):
        if not (isinstance(o.value, dict) and o.value.get("Type") == "ObjStm"):
            continue
        dec = doc.stream_data(o.num)
        first = o.value.get("First")
        if not dec or not isinstance(first, int):
            continue
        ints = [int(x) for x in re.findall(rb"\d+", dec[:first])]
        pairs = list(zip(ints[0::2], ints[1::2]))
        for onum, off in pairs:
            start = first + off
            try:
                val = _PdfLexer(dec, start).parse()
            except (_PdfError, ValueError, IndexError):
                continue
            prev = doc.objs.get(onum)
            if prev is None or prev.pos < o.pos:
                doc.objs[onum] = PdfObj(onum, 0, val, None, o.pos, objstm=o.num)
    # trailers: classic `trailer << >>` and XRef-stream dictionaries
    trailers: List[Tuple[int, Dict[str, Any]]] = []
    for tm in re.finditer(rb"trailer[ \t\r\n\f\x00]*<<", data):
        with contextlib.suppress(_PdfError, ValueError, IndexError):
            t = _PdfLexer(data, tm.end() - 2).parse()
            if isinstance(t, dict):
                trailers.append((tm.start(), t))
    for o in doc.objs.values():
        if isinstance(o.value, dict) and o.value.get("Type") == "XRef":
            trailers.append((o.pos, o.value))
    trailers.sort(key=lambda x: x[0])
    if trailers:
        doc.trailer = dict(trailers[-1][1])
        for _, t in trailers:
            for k in ("Info", "Root", "Encrypt"):
                if k in t and k not in doc.trailer:
                    doc.trailer[k] = t[k]
    doc.encrypted = "Encrypt" in doc.trailer
    # the uncompressed bytes outside stream payloads (fallback byte layer)
    parts, last = [], 0
    for s, e in sorted(stream_spans):
        parts.append(data[last:s])
        last = max(last, e)
    parts.append(data[last:])
    doc.outside_text = b"".join(parts).decode("latin-1")
    return doc


def _walk_strings(v: Any, path: str = "", depth: int = 0) -> Iterator[Tuple[str, str]]:
    if depth > 40:
        return
    if isinstance(v, _PdfString):
        yield path, v.text()
    elif isinstance(v, dict):
        for k, x in v.items():
            yield from _walk_strings(x, path + "/" + k, depth + 1)
    elif isinstance(v, list):
        for x in v:
            yield from _walk_strings(x, path, depth + 1)


def _refs_in(v: Any, depth: int = 0) -> Iterator[int]:
    if depth > 20:
        return
    if isinstance(v, _Ref):
        yield v[0]
    elif isinstance(v, list):
        for x in v:
            yield from _refs_in(x, depth + 1)


def pdf_info(doc: PdfDoc) -> Dict[str, str]:
    info = doc.resolve(doc.trailer.get("Info"))
    out: Dict[str, str] = {}
    if isinstance(info, dict):
        for k, v in info.items():
            v = doc.resolve(v)
            if isinstance(v, _PdfString):
                out[k] = v.text()
            elif isinstance(v, _Name):
                out[k] = "/" + str(v)
    return out


def _content_stream_nums(doc: PdfDoc) -> Set[int]:
    nums: Set[int] = set()
    for o in doc.objs.values():
        v = o.value
        if isinstance(v, dict) and v.get("Type") == "Page":
            nums.update(_refs_in(v.get("Contents")))
            c = v.get("Contents")
            if isinstance(c, _Ref):
                arr = doc.resolve(c)
                if isinstance(arr, list):
                    nums.update(_refs_in(arr))
    return nums


def _skip_stream_nums(doc: PdfDoc) -> Set[int]:
    """Streams whose payload is not metadata: page content, form XObjects,
    images, font programs, CMaps, object/xref streams."""
    skip = set(_content_stream_nums(doc))
    for o in doc.objs.values():
        v = o.value
        if not isinstance(v, dict):
            continue
        for key in ("FontFile", "FontFile2", "FontFile3", "ToUnicode"):
            skip.update(_refs_in(v.get(key)))
        if o.stream is not None and (
                v.get("Subtype") in ("Form", "Image", "Type1C", "CIDFontType0C", "OpenType")
                or v.get("Type") in ("ObjStm", "XRef", "XObject")
                or "Length1" in v or "Length2" in v or "Length3" in v):
            skip.add(o.num)
    return skip


# ─── PDF text extraction (optional backends) ─────────────────────────────────

def _load_fitz() -> Any:
    for name in ("pymupdf", "fitz"):
        try:
            mod = __import__(name)
        except Exception:  # noqa: BLE001 — any import failure means "not available"
            continue
        if hasattr(mod, "open"):
            return mod
    return None


def _load_pypdf() -> Any:
    try:
        import pypdf  # type: ignore
        return pypdf
    except Exception:  # noqa: BLE001
        return None


def _which(name: str) -> Optional[str]:
    return shutil.which(name)


def available_backends() -> Dict[str, bool]:
    return {"pymupdf": _load_fitz() is not None, "poppler": _which("pdftotext") is not None,
            "pypdf": _load_pypdf() is not None}


def _blocks_from_text(text: str) -> List[Dict[str, Any]]:
    blocks, cur = [], []
    for line in text.splitlines():
        if line.strip():
            cur.append(line)
        elif cur:
            blocks.append({"bbox": None, "lines": cur, "kind": "text"})
            cur = []
    if cur:
        blocks.append({"bbox": None, "lines": cur, "kind": "text"})
    return blocks


def _xml_tag(e: Any) -> str:
    return e.tag.rsplit("}", 1)[-1] if isinstance(e.tag, str) else ""


def parse_bbox_xhtml(xml_text: str) -> List[Dict[str, Any]]:
    """Parse `pdftotext -bbox-layout` XHTML into pages of text blocks."""
    import xml.etree.ElementTree as ET
    xml_text = re.sub(r"<!DOCTYPE[^>]*>", "", xml_text, count=1)
    root = ET.fromstring(xml_text)
    pages = []
    for idx, pg in enumerate([e for e in root.iter() if _xml_tag(e) == "page"], 1):
        blocks = []
        for blk in [e for e in pg.iter() if _xml_tag(e) == "block"]:
            lines = []
            for ln in [e for e in blk.iter() if _xml_tag(e) == "line"]:
                words = [(w.text or "") for w in ln if _xml_tag(w) == "word"]
                lines.append(" ".join(words))
            try:
                bbox = [float(blk.get(k, "0")) for k in ("xMin", "yMin", "xMax", "yMax")]
            except ValueError:
                bbox = None
            blocks.append({"bbox": bbox, "lines": lines, "kind": "text"})
        pages.append({"page": idx, "width": float(pg.get("width", "0") or 0),
                      "height": float(pg.get("height", "0") or 0), "blocks": blocks})
    return pages


def extract_pdf(path: str, backend: str = "auto") -> Dict[str, Any]:
    """Pages with blocks: {'text_backend', 'bbox_backend', 'pages', 'error'}."""
    order = ["pymupdf", "poppler", "pypdf"] if backend == "auto" else [backend]
    if backend == "none":
        return {"text_backend": None, "bbox_backend": None, "pages": [], "error": None}
    last_err = None
    for name in order:
        try:
            if name == "pymupdf":
                fitz = _load_fitz()
                if fitz is None:
                    continue
                doc = fitz.open(path)
                try:
                    if getattr(doc, "needs_pass", False):
                        return {"text_backend": None, "bbox_backend": None, "pages": [], "error": "encrypted"}
                    pages = []
                    for i, page in enumerate(doc, 1):
                        blocks = []
                        for b in page.get_text("blocks"):
                            x0, y0, x1, y1, txt = b[0], b[1], b[2], b[3], b[4]
                            btype = b[6] if len(b) > 6 else 0
                            if btype == 1:
                                blocks.append({"bbox": [x0, y0, x1, y1], "lines": [], "kind": "image"})
                                continue
                            lines = (txt or "").split("\n")
                            while lines and not lines[-1].strip():
                                lines.pop()
                            blocks.append({"bbox": [x0, y0, x1, y1], "lines": lines, "kind": "text"})
                        pages.append({"page": i, "width": float(page.rect.width),
                                      "height": float(page.rect.height), "blocks": blocks})
                finally:
                    doc.close()
                return {"text_backend": "pymupdf", "bbox_backend": "pymupdf", "pages": pages, "error": None}
            if name == "poppler":
                exe = _which("pdftotext")
                if not exe:
                    continue
                r = subprocess.run([exe, "-bbox-layout", "-enc", "UTF-8", path, "-"],
                                   capture_output=True, timeout=300)
                if r.returncode == 0 and r.stdout:
                    try:
                        pages = parse_bbox_xhtml(r.stdout.decode("utf-8", errors="replace"))
                        return {"text_backend": "pdftotext", "bbox_backend": "pdftotext-bbox",
                                "pages": pages, "error": None}
                    except Exception:  # noqa: BLE001 — fall back to plain text
                        pass
                r = subprocess.run([exe, "-enc", "UTF-8", path, "-"], capture_output=True, timeout=300)
                if r.returncode != 0:
                    last_err = (r.stderr or b"").decode("utf-8", errors="replace").strip()[:200] or "pdftotext failed"
                    continue
                texts = r.stdout.decode("utf-8", errors="replace").split("\f")
                if texts and not texts[-1].strip():
                    texts.pop()
                pages = [{"page": i, "width": 0.0, "height": 0.0, "blocks": _blocks_from_text(t)}
                         for i, t in enumerate(texts, 1)]
                return {"text_backend": "pdftotext", "bbox_backend": None, "pages": pages, "error": None}
            if name == "pypdf":
                pypdf = _load_pypdf()
                if pypdf is None:
                    continue
                reader = pypdf.PdfReader(path)
                if getattr(reader, "is_encrypted", False):
                    return {"text_backend": None, "bbox_backend": None, "pages": [], "error": "encrypted"}
                pages = []
                for i, page in enumerate(reader.pages, 1):
                    try:
                        txt = page.extract_text() or ""
                    except Exception:  # noqa: BLE001
                        txt = ""
                    try:
                        w, h = float(page.mediabox.width), float(page.mediabox.height)
                    except Exception:  # noqa: BLE001
                        w, h = 0.0, 0.0
                    pages.append({"page": i, "width": w, "height": h, "blocks": _blocks_from_text(txt)})
                return {"text_backend": "pypdf", "bbox_backend": None, "pages": pages, "error": None}
        except Exception as e:  # noqa: BLE001 — a broken backend degrades, it never crashes the scan
            last_err = "%s: %s" % (name, type(e).__name__)
            continue
    return {"text_backend": None, "bbox_backend": None, "pages": [], "error": last_err}


# ─── Text normalization and regions ──────────────────────────────────────────

_ZW_FALLBACK = frozenset("\u200b\u200c\u200d\u2060\u2062\u2063\u2064\ufeff\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069")


def _invisible_set() -> Tuple[frozenset, bool]:
    try:
        from threat_scan import INVISIBLE_CHARS  # type: ignore
        return frozenset(INVISIBLE_CHARS) | _ZW_FALLBACK, True
    except Exception:  # noqa: BLE001
        return _ZW_FALLBACK, False


_PURE_INT_RE = re.compile(r"^\s*\d{1,4}\s*$")
_LINENO_PREFIX_RE = re.compile(r"^\s*(\d{1,4})\s{1,}(?=\S)")


def _clean_line(line: str, invisible: frozenset, found: List[str]) -> str:
    line = unicodedata.normalize("NFKC", line)
    if any(ch in invisible for ch in line):
        found.extend(ch for ch in line if ch in invisible)
        line = "".join(ch for ch in line if ch not in invisible)
    return line.replace("\u00ad", "").rstrip()


def join_lines_tracked(lines: Sequence[str]) -> Tuple[str, List[int]]:
    """Join wrapped lines: 'trans-\\nformers' -> 'transformers' (hyphen + lower
    case), a break between two CJK characters -> nothing, every other line
    break -> one space (catches 'transformers\\n5'). Also returns the offsets
    where a line-end hyphen was removed: a compound such as 'readout-\\nfree'
    joins to one token there, which is not a glued-words defect."""
    parts: List[str] = []
    joins: List[int] = []
    n = 0
    last = ""
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if last.endswith("-") and len(last) >= 2 and last[-2].isalpha() and line[:1].islower():
            parts[-1] = last = last[:-1]
            n -= 1
            joins.append(n)
        elif parts and _CJK_RE.match(last[-1:]) and _CJK_RE.match(line[:1]):
            pass
        elif parts:
            parts.append(" ")
            n += 1
        parts.append(line)
        n += len(line)
        last = line
    return "".join(parts), joins


def join_lines(lines: Sequence[str]) -> str:
    return join_lines_tracked(lines)[0]


def normalize_text(lines: Sequence[str], invisible: Optional[frozenset] = None) -> Tuple[str, List[str]]:
    """One block of extracted lines -> matching text: NFKC, zero-width chars
    removed (and returned, for TEXT-INVISIBLE), soft hyphens dropped, wrapped
    lines joined."""
    found: List[str] = []
    inv = invisible if invisible is not None else _invisible_set()[0]
    return join_lines([_clean_line(x, inv, found) for x in lines]), found


def _strip_line_numbers_textonly(lines: List[str]) -> List[str]:
    ints = [i for i, t in enumerate(lines) if _PURE_INT_RE.match(t)]
    if len(ints) >= 5:
        vals = [int(lines[i]) for i in ints]
        inc = sum(1 for a, b in zip(vals, vals[1:]) if b > a)
        if inc >= 0.8 * (len(vals) - 1):
            drop = set(ints)
            lines = [t for i, t in enumerate(lines) if i not in drop]
    pref = [(i, int(m.group(1))) for i, t in enumerate(lines) for m in [_LINENO_PREFIX_RE.match(t)] if m]
    if len(pref) >= 8:
        vals = [v for _, v in pref]
        steps = sum(1 for a, b in zip(vals, vals[1:]) if b == a + 1)
        if steps >= 0.8 * (len(vals) - 1):
            idx = {i for i, _ in pref}
            lines = [(_LINENO_PREFIX_RE.sub("", t, count=1) if i in idx else t) for i, t in enumerate(lines)]
    non_empty = [i for i, t in enumerate(lines) if t.strip()]
    for i in (non_empty[:1] + non_empty[-1:]):
        if _PURE_INT_RE.match(lines[i]):
            lines[i] = ""
    return lines


def normalize_pages(raw_pages: List[Dict[str, Any]], invisible: frozenset) -> List[Dict[str, Any]]:
    """Segments per page: NFKC, zero-width chars stripped (recorded), soft
    hyphens removed, line-number columns and page numbers dropped, header and
    footer bands and margin blocks labelled."""
    pages = []
    for p in raw_pages:
        w, h = p.get("width") or 0.0, p.get("height") or 0.0
        invis: List[str] = []
        segs: List[Dict[str, Any]] = []
        images: List[List[float]] = []
        blocks = p.get("blocks") or []
        has_bbox = any(b.get("bbox") for b in blocks)
        if not has_bbox:
            all_lines: List[str] = []
            for b in blocks:
                all_lines.extend(b["lines"])
                all_lines.append("")
            cleaned = _strip_line_numbers_textonly([_clean_line(t, invisible, invis) for t in all_lines])
            for blk in _blocks_from_text("\n".join(cleaned)):
                segs.append({"page": p["page"], "kind": "body", "lines": blk["lines"], "bbox": None})
        else:
            for b in blocks:
                bb = b.get("bbox")
                if b.get("kind") == "image":
                    if bb:
                        images.append(bb)
                    continue
                lines = [_clean_line(t, invisible, invis) for t in b["lines"]]
                lines = [t for t in lines if t.strip()]
                if not lines:
                    continue
                kind = "body"
                if bb and h and w:
                    x0, y0, x1, y1 = bb
                    if y1 <= 0.06 * h:
                        kind = "header"
                    elif y0 >= 0.94 * h:
                        kind = "footer"
                    elif x1 <= 0.16 * w or x0 >= 0.84 * w:
                        kind = "margin"
                    pure = all(_PURE_INT_RE.match(t) for t in lines)
                    if pure and (kind != "body" or (len(lines) == 1 and y0 >= 0.8 * h
                                                    and abs((x0 + x1) / 2 - w / 2) < 0.12 * w)):
                        continue  # line-number column or page number
                segs.append({"page": p["page"], "kind": kind, "lines": lines, "bbox": bb})
        for s in segs:
            s["text"], s["joins"] = join_lines_tracked(s["lines"])
        pages.append({"page": p["page"], "width": w, "height": h, "segs": segs, "images": images,
                      "invisible": invis})
    return pages


_NUMBERING_RE = re.compile(r"^(?:(?:\d{1,2}|[A-Z]|[IVX]{1,4})(?:\.\d{1,2}){0,3}\.?|§\s*\d+(?:\.\d+)*)\s+")
_NUMBER_ONLY_RE = re.compile(r"(?:\d{1,2}|[A-Z]|[IVX]{1,4})(?:\.\d{1,2}){0,3}\.?")
DEFAULT_HEADINGS: Dict[str, List[str]] = {
    "references": ["references", "bibliography", "参考文献", "works cited", "literature cited"],
    "appendix": ["appendix", "appendices", "附录", "supplementary material", "supplementary materials",
                 "technical appendix", "supplementary appendix"],
    "end_matter": ["ai use statement", "ai usage statement", "ai use", "use of ai", "use of large language models",
                   "use of llms", "llm usage statement", "llm usage", "llm use", "llm statement",
                   "large language model usage", "declaration of ai", "ethics statement", "ethical statement",
                   "reproducibility statement", "acknowledgments", "acknowledgements", "acknowledgment",
                   "acknowledgement", "author contributions", "funding", "impact statement",
                   "ai 使用声明", "ai使用声明", "伦理声明", "可复现性声明", "致谢"],
    "checklist": ["neurips paper checklist", "paper checklist", "reproducibility checklist", "checklist"],
    # only headings that name a compute-accounting section (venue checklists ask
    # for one); a bare "Hardware" subsection of the setup is where leaks live
    "compute": ["compute resources", "computational resources", "compute budget", "computing infrastructure",
                "computational cost", "compute requirements", "计算资源"],
    "related_work": ["related work", "related works", "background", "prior work", "background and related work",
                     "相关工作"],
}
DEFAULT_BODY_END = ["references", "bibliography", "参考文献", "appendix", "appendices", "附录",
                    "ai use statement", "ai usage statement", "use of large language models", "llm usage statement",
                    "llm usage", "ethics statement", "reproducibility statement", "acknowledgments",
                    "acknowledgements", "acknowledgment", "acknowledgement", "ai 使用声明", "ai使用声明",
                    "伦理声明", "可复现性声明", "致谢", "neurips paper checklist", "paper checklist"]


def _heading_core(text: str) -> Tuple[str, bool]:
    t = _collapse_ws(text)
    core = _NUMBERING_RE.sub("", t, count=1)
    numbered = core != t
    core = core.strip().rstrip(":：.").strip()
    return core, numbered


_APPX_WORD_RE = re.compile(r"^(?:appendix|appendices|附录)(?![a-z])", re.I)
_APPX_LABEL_RE = re.compile(r"^(?:[A-Z](?:\.\d{1,2})*|[IVX]{1,4}|\d{1,2}(?:\.\d{1,2})*)(?![\w.])")
_REF_WORDS = ("table", "tables", "tab", "figure", "figures", "fig", "section", "sec", "eq", "equation", "theorem",
              "lemma", "proposition", "corollary", "algorithm", "line", "listing", "definition", "remark", "example",
              "step", "part", "chapter", "for", "of", "in", "and", "to", "the", "a", "an", "gives", "shows")


def _appendix_heading_ok(core: str) -> bool:
    """'Appendix', 'Appendix B', 'Appendix B: Proofs', 'APPENDIX A TITLE' — but
    not a sentence that starts with a reference ('Appendix C describes ...',
    'Appendix Table 4 lists ...')."""
    m = _APPX_WORD_RE.match(core)
    if not m:
        return False
    rest = core[m.end():].strip()
    if not rest:
        return True
    lab = _APPX_LABEL_RE.match(rest)
    if lab:
        rest = rest[lab.end():].strip()
        if not rest:
            return True
    if rest[:1] in ":.–—-":
        return bool(rest[1:].strip())
    words = rest.split()
    first = re.sub(r"[^\w]", "", words[0]).casefold() if words else ""
    if not words or not words[0][:1].isupper() or first in _REF_WORDS:
        return False
    # a title is short and its later words are capitalized or short function words
    lower_long = [w for w in words[1:] if w[:1].islower() and len(w) > 4]
    return len(words) <= 8 and len(lower_long) <= 1


def heading_kind(text: str, main: str, tables: Dict[str, List[str]], letter_ok: bool = True
                 ) -> Optional[Tuple[str, Optional[str], str]]:
    """(kind, sub-label, heading core) for a heading line, else None."""
    t = _collapse_ws(text)
    if not t or len(t) > 60:
        return None
    core, numbered = _heading_core(t)
    low = core.casefold()
    if not low:
        return None
    if low in tables["references"]:
        return ("references", None, core)
    for h in tables["appendix"]:
        if low == h:
            return ("appendix", None, core)
    if any(h in ("appendix", "appendices", "附录") for h in tables["appendix"]) and _appendix_heading_ok(core) \
            and not t.endswith((".", ",", ";")):
        return ("appendix", None, core)
    for h in tables["end_matter"]:
        if low == h or (len(h) > 8 and low.startswith(h)):
            sub = ("reproducibility" if "reproducib" in h or "可复现" in h else
                   "acknowledgments" if h.startswith(("acknowledg", "致谢", "author contrib", "funding")) else
                   "ethics" if "ethic" in h or "伦理" in h else "ai_use")
            return ("end_matter", sub, core)
    if low in tables["checklist"] or any(low.startswith(h) for h in tables["checklist"] if len(h) > 12):
        return ("checklist", None, core)
    if low in tables["compute"]:
        return ("compute", None, core)
    if low in tables["related_work"]:
        return ("related_work", None, core)
    words = core.split()
    if (letter_ok and main in ("references", "appendix") and re.match(r"^[A-H](?:\.\d{1,2})?\s+[A-Z][A-Za-z]", t)
            and len(words) <= 8 and not t.endswith((".", ",", ";", "-"))):
        return ("appendix_section", None, core)
    if numbered and core[:1].isupper() and len(words) <= 10 and not t.endswith((".", ",", ";")):
        return ("generic", None, core)
    return None


def detect_regions(pages: List[Dict[str, Any]], policy: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Assign region/sub-region to every segment; split segments at heading
    lines. Returns heading events in reading order."""
    tables = {k: [x.casefold() for x in v] for k, v in DEFAULT_HEADINGS.items()}
    overrides = policy.get("region_headings") or {}
    if isinstance(overrides, dict):
        for k, v in overrides.items():
            if k in tables and isinstance(v, list):
                tables[k] = [str(x).casefold() for x in v]
    main, sub = "body", None
    events: List[Dict[str, Any]] = []

    def apply(kind: str, label: Optional[str]) -> None:
        nonlocal main, sub
        if kind in ("references", "checklist"):
            main, sub = kind, None
        elif kind in ("appendix", "appendix_section"):
            main, sub = "appendix", None
        elif kind == "end_matter":
            main, sub = "end_matter", label
        elif kind in ("compute", "related_work"):
            sub = kind
        elif kind == "generic" and main != "end_matter":
            sub = None

    for page in pages:
        new_segs: List[Dict[str, Any]] = []
        for seg in page["segs"]:
            if seg["kind"] != "body":
                seg["region"], seg["sub"], seg["heading"] = main, sub, None
                new_segs.append(seg)
                continue
            lines = seg["lines"]
            whole = None
            # a block is a heading as a whole only when it is one line, or a
            # bare number/letter line followed by the title ("1" / "Intro")
            if len(seg["text"]) <= 60 and (len(lines) == 1 or (
                    len(lines) <= 3 and all(_NUMBER_ONLY_RE.fullmatch(x.strip()) for x in lines[:-1]))):
                whole = heading_kind(seg["text"], main, tables)
            if whole:
                apply(whole[0], whole[1])
                seg["region"], seg["sub"], seg["heading"] = main, sub, whole[0]
                events.append({"page": page["page"], "kind": whole[0], "sub": whole[1], "text": whole[2],
                               "bbox": seg.get("bbox")})
                new_segs.append(seg)
                continue
            start = 0  # first line of the pending (non-heading) piece
            for k, line in enumerate(lines):
                hk = heading_kind(line, main, tables, letter_ok=seg.get("bbox") is None)
                if not hk:
                    continue
                if hk[0] == "appendix" and not _midblock_heading_ok(lines, k):
                    continue  # "... described in" / "Appendix E" / "gives ..." is prose
                if k > start:
                    new_segs.append(_seg_piece(page["page"], seg, start, k, main, sub, None))
                apply(hk[0], hk[1])
                piece = _seg_piece(page["page"], seg, k, k + 1, main, sub, hk[0])
                new_segs.append(piece)
                events.append({"page": page["page"], "kind": hk[0], "sub": hk[1], "text": hk[2],
                               "bbox": piece["bbox"]})
                start = k + 1
            if start < len(lines):
                new_segs.append(_seg_piece(page["page"], seg, start, len(lines), main, sub, None))
        page["segs"] = new_segs
        _float_pass(new_segs)
    return events


# A float (table, figure, algorithm) that LaTeX places on a page after the
# references, above the appendix heading, is paper content, not bibliography:
# its numbers count for NUM-DRIFT and its text is scanned like the body.
_FLOAT_CAPTION_RE = re.compile(r"^\s*(?:Table|Figure|Fig\.|Algorithm|Listing|表|图)\s*[A-Z]?\d+(?:\.\d+)*\s*[:.：|]")
_BIB_LIKE_RE = re.compile(r"(?<!\d)(?:19|20)\d\d[a-z]?(?!\d)|\bet\s+al\b|\barXiv\b|\bProceedings\b|\bProc\.|\bIn\s+[A-Z]"
                          r"|\bdoi\b|https?://|\bURL\b|\bJournal\b|\bpp\.\s*\d|\bvol\.|\bConference\b|\bTransactions\b"
                          r"|\bPress\b|\bpreprint\b", re.I)


def _float_pass(segs: List[Dict[str, Any]]) -> None:
    """On a page where a float caption sits inside the references region, the
    blocks that do not read as bibliography entries belong to that float."""
    refs = [s for s in segs if s.get("kind") == "body" and s.get("region") == "references" and not s.get("heading")]
    if not any(_FLOAT_CAPTION_RE.match(s.get("text") or "") for s in refs):
        return
    for s in refs:
        if _FLOAT_CAPTION_RE.match(s.get("text") or "") or not _BIB_LIKE_RE.search(s.get("text") or ""):
            s["region"] = "float"


def _midblock_heading_ok(lines: Sequence[str], k: int) -> bool:
    """A heading line inside a multi-line block must not continue a sentence:
    the previous line ends a sentence (or is a bare number) and the next line
    does not start in lower case."""
    if k > 0:
        prev = lines[k - 1].strip()
        if prev and not (prev.endswith((".", ":", "!", "?", "。", "：")) or _NUMBER_ONLY_RE.fullmatch(prev)):
            return False
    if k + 1 < len(lines):
        nxt = lines[k + 1].strip()
        if nxt[:1].islower():
            return False
    return True


def _seg_piece(page_no: int, seg: Dict[str, Any], k0: int, k1: int, region: str, sub: Optional[str],
               heading: Optional[str]) -> Dict[str, Any]:
    """Lines k0..k1 of a segment; the bbox is the proportional slice of the
    block (one block can hold body text and a heading line)."""
    lines = seg["lines"][k0:k1]
    bb = seg.get("bbox")
    if bb:
        n = max(1, len(seg["lines"]))
        h = (bb[3] - bb[1]) / n
        bb = [bb[0], bb[1] + h * k0, bb[2], bb[1] + h * k1]
    text, joins = join_lines_tracked(lines)
    return {"page": page_no, "kind": "body", "lines": lines, "bbox": bb, "text": text, "joins": joins,
            "region": region, "sub": sub, "heading": heading}


# ─── Text detectors (PDF text and de-TeXed sources) ──────────────────────────

class Hit:
    __slots__ = ("check", "certainty", "severity", "start", "end", "match", "note", "demoted", "usage", "plan_only")

    def __init__(self, check: str, certainty: str, severity: str, start: int, end: int,
                 match: Optional[str] = None, note: Optional[str] = None, demoted: Optional[str] = None,
                 usage: Optional[str] = None, plan_only: bool = False):
        self.check, self.certainty, self.severity = check, certainty, severity
        self.start, self.end, self.match, self.note, self.demoted = start, end, match, note, demoted
        self.usage = usage  # "metric" or "title": a hardware word that names a measured quantity or a heading
        self.plan_only = plan_only  # a recall candidate for a person: never queued for an automatic fix


# ASCII \b, \w, \d and \s in every detector: a CJK neighbour must never hide an
# English term ("使用PyTorch 2.1训练" — Python's Unicode \b sees no boundary there).
_A = re.ASCII
_NOT_CJK_END = r"[^\s,;)\]}>\"'`" + _CJK_CLASS + r"]*"
_STRONG_LIBS = (r"(?:py)?torch|torchvision|torchaudio|transformers|vllm|sglang|deepspeed|flash[-_ ]?attn|"
                r"flash[-_ ]?attention|xformers|bitsandbytes|numpy|scipy|pandas|jaxlib|jax|flax|tensorflow|keras|"
                r"scikit-learn|sklearn|cuda|cudnn|nccl|python|gcc|nvcc|tensorrt(?:-llm)?|megatron(?:-lm)?|"
                r"onnxruntime|onnx\s+runtime|langchain|lightgbm|xgboost|timm|diffusers|peft|trl|triton|ubuntu|centos|"
                r"debian|macos|einops|safetensors|cupy|numba|torch[-_]geometric|pyg|dgl|rocm|opencv(?:-python)?|"
                r"matplotlib|statsmodels|sympy|gurobi|huggingface[-_ ]hub|sentence[-_]transformers")
_WEAK_LIBS = r"datasets|tokenizers|accelerate|openai|anthropic|ray|pip|docker|conda|pillow|networkx|seaborn|cmake|clang|llvm|R"
_VER_TAIL = (r"\d+\.\d+(?:\.\d+){0,2}(?:(?:\.|-)?(?:post|dev|rc|a|b)\d+)?(?:\+(?:cu|rocm|cpu)[\w.]*)?"
             r"(?!\w|\.\d|-\d+(?:\.\d+)?[BbMmKk]\b|\s*(?:[×%]|x\b|times\b|fold\b|faster\b|slower\b|ms\b|GB\b|MB\b|"
             r"points?\b|pp\b))")
_ZH_VER_SEP = r"\s*的?\s*版本号?\s*(?:为|是|[:：])?\s*"  # "PyTorch 版本为 9.9.9", "transformers 版本号为 9.9"
_ENG_VER_RES = [
    re.compile(r"(?<![\w-])(?:" + _STRONG_LIBS + r")(?:\s*(?:==|>=|<=|~=|=|:|\(|-)\s*|" + _ZH_VER_SEP + r"|\s+)"
               r"(?:(?:version|ver\.?|release)\s*)?v?" + _VER_TAIL, re.I | _A),
    re.compile(r"(?<![\w-])(?:" + _WEAK_LIBS + r")(?:\s*(?:==|>=|~=)\s*|\s+(?:version|ver\.?)\s*|\s+v|" + _ZH_VER_SEP
               + r")" + _VER_TAIL, re.I | _A),
    re.compile(r"(?<![\w-])(?:" + _WEAK_LIBS + r")\s+\d+\.\d+\.\d+(?!\w|\.\d)", re.I | _A),
    re.compile(r"(?<![\w])cu1\d{2}(?![\w])", _A),
    re.compile(r"\+cu\d{2,3}\b", _A),
    re.compile(r"\b[Dd]river\s+(?:version\s+)?\d{3}\.\d+(?:\.\d+)?", _A),
]
# Recall candidates for a person (plan only; never an automatic fix): a release number that does not touch its
# library's name ("TRL's loss, unchanged in release 9.1.2"; "releases 9.0.1, 9.0.2 and 9.1.0"), with a named
# library in the same stretch of text (a one-letter name is a variable there, and a capital V before a number is
# a quantity of the text, not a release)
_LIB_NAME_RE = re.compile(r"(?<![\w-])(?:" + _STRONG_LIBS + r"|" + "|".join(
    x for x in _WEAK_LIBS.split("|") if len(x) > 1) + r")(?:['’]s)?(?![\w-])", re.I | _A)
_VER_NUM = r"\d+\.\d+(?:\.\d+){0,2}"
_RELEASE_VER_RE = re.compile(r"(?:(?<![\w-])(?:releases?|versions?)\s*|(?<![\w\\-])(?-i:v))" + _VER_NUM
                             + r"(?![\w]|\.\d)(?:\s*(?:,|and|or|to|through|-|–)\s*(?:(?-i:v))?" + _VER_NUM
                             + r"(?![\w]|\.\d))*", re.I | _A)
# a batch called by when it ran ("the earlier toy sweeps", "previously trained", "cells added later")
_PROC_BATCH_P2_RE = re.compile(
    r"\bpreviously\s+(?:deployed|run|ran|computed|collected|generated|evaluated|executed|launched|trained|scored|"
    r"sampled|recorded|registered)\b"
    r"|\b(?:the|our|an|its|their)\s+earlier\s+(?:[\w-]+\s+)?(?:runs?|batch(?:es)?|records?|diagnostics?|sweeps?|"
    r"evaluations?|drafts?|rounds?|executions?|checkpoints?)\b"
    r"|\bhistorical\s+(?:runs?|records?|batch(?:es)?|rankings?|sweeps?|evaluations?)\b"
    r"|\b(?:completed|finished|added|analy[sz]ed)\s+later\b", re.I | _A)
# how a registered design changed, as opposed to the label of a registration (kept under registration_labels: keep)
_REVISION_PROCESS_RE = re.compile(
    r"\b(?:was|were|has\s+been|have\s+been)\s+(?:replaced|superseded|appended|restated|re-?specified|re-?defined)"
    r"\s+(?:by|with|to|accordingly)\b"
    r"|\bin\s+the\s+order\s+in\s+which\s+they\s+were\s+(?:made|added|filed|written)\b"
    r"|\b(?:followed|accompanied)\s+by\s+(?:the\s+|its\s+)?(?:amendments?|addend(?:um|a))\b", re.I | _A)
# a run or a registration named by its date or its order ("the registered submission date", "the first
# registration"); "the original registration" names the registration as against its amendments, a label
# registration_labels: keep protects, never a round
_DATE_TITLE_RE = re.compile(r"\bregistered\s+(?:analysis|completion|submission|cut-?off|end)\s+dates?\b"
                            r"|\b(?:first|second|third|earlier|later)\s+(?:pre-?)?registration\b",
                            re.I | _A)
_FW_RE = re.compile(
    r"(?<![\w-])(?:PyTorch(?:\s+Lightning)?|TensorFlow|JAX|Flax|Keras|vLLM|SGLang|DeepSpeed|Megatron(?:-LM)?|"
    r"TensorRT(?:-LLM)?|ONNX\s+Runtime|Hugging\s?Face(?:'s)?\s+(?:Transformers|Accelerate|Datasets|PEFT|TRL|Hub|TGI)"
    r"(?:\s+librar(?:y|ies))?|Transformers\s+library|W&B|wandb|Weights\s+(?:&|and)\s+Biases|MLflow|Docker|"
    r"(?:Ana|Mini)?conda|Slurm|SLURM|Kubernetes|Ray\s+(?:Tune|Serve|Train|Data)|RLlib|scikit-learn)(?![\w-])", _A)
_HW_RE = re.compile(
    r"(?<![\w-])(?:A100|A800|A6000|A5000|A4000|RTX\s?A\d{4}|H100|H800|H200|GH200|B100|B200|GB200|L40S?|V100|P100|P40|"
    r"K80|RTX\s?\d{4}(?:\s?Ti)?|GTX\s?\d{3,4}(?:\s?Ti)?|GeForce|Quadro|Titan\s?(?:RTX|V|Xp?)|TPU\s?v\d[a-z]?|"
    r"MI\d{3}X?|Ascend\s?\d{3}[A-Z]?|Gaudi\s?\d?|Xeon|EPYC|Threadripper|Ryzen|Core\s?i[3579](?:-\d{4,5}[A-Z]*)?|"
    r"Apple\s+M[1-4](?:\s+(?:Pro|Max|Ultra))?|Grace\s+Hopper|DGX|HGX)(?![\w])"
    r"|(?:NVIDIA|Tesla|AMD|Intel)\s+(?:T4|L4|A10G?|A30|A40|A16|H20|K40|M60)(?![\w])"
    r"|(?<![\w-])(?:T4|L4|A10G?|A30|A40|H20)\s+GPUs?\b|\bNVIDIA\b"
    r"|显卡|单卡|多卡|卡时|\d+\s*(?:张|块)\s*(?:卡|GPU|显卡)", _A)
_QTY_RE = re.compile(
    r"(?:\b\d[\d,.]*\s*)?\b(?:GPU|TPU|NPU|accelerator|node|CPU|core)[- ](?:hours?|days?|years?|months?)\b"
    r"|\b\d+\s*[x×]\s*(?:[A-Z][\w-]*\s+)?(?:GPU|TPU|NPU|accelerator|card)s?\b"
    r"|(?<![\w-])\d+[- ](?:GPU|TPU|NPU)s?\b"
    r"|\bpeak\s+(?:(?:allocated|reserved|resident)\s+)?(?:(?:GPU|CUDA|device|host|CPU)\s+)?memory\b"
    r"|\b\d{6,}\s*bytes\b|\bprocess[- ]seconds\b|\bpinned\s+(?:CPU\s+)?cores?\b"
    r"|\b\d+\s+(?:physical\s+|logical\s+|CPU\s+)cores?\b"
    r"|\b(?:on|using|with|across)\s+(?:one|a\s+single|single|\d+)\s+(?:(?:physical|logical)\s+)?(?:CPU\s+)?cores?\b"
    r"|\b(?:one|a\s+single|single)\s+CPU\b(?!-)|\bCPU[- ]only\b|\b(?:no|without\s+(?:a\s+|any\s+)?)\s*GPUs?\b"
    r"|\b\d+\s*(?:GB|GiB)\s+(?:of\s+)?(?:GPU|device|HBM\d?|VRAM|video)(?:\s+(?:memory|RAM))?\b"
    r"|\b(?:single|multi)-(?:GPU|node)\b"
    r"|GPU\s*小时|机时|显存|单核|单个\s*CPU", re.I | _A)
_QTY_BARE_CORES_RE = re.compile(r"\b\d+\s+cores\b", re.I | _A)
_COMPUTE_CTX_RE = re.compile(r"\b(?:CPUs?|GPUs?|threads?|processors?|machines?|servers?|nodes?|hardware|parallel|"
                             r"workers?|wall[- ]?clock|runtime|seconds|minutes|hours|RAM|memory|Xeon|EPYC|Intel|AMD)\b",
                             re.I | _A)
_OPS_D_RE = re.compile(
    r"\b(?:ssh|scp|sftp|rsync)\s+-{1,2}[A-Za-z]|\b(?:ssh|scp|sftp)\s+[\w.-]+@[\w.-]+"
    r"|\b(?:nohup|setsid|tmux|kubectl|sbatch|srun|salloc|squeue|scancel|qsub|bsub|torchrun|mpirun|nvidia-smi)\b"
    r"|\bscreen\s+-[a-zA-Z]|\bdocker\s+(?:run|build|pull|push|exec|compose)\b"
    r"|\bconda\s+(?:activate|create|install|env)\b|\bpip3?\s+install\b"
    r"|\bCUDA_VISIBLE_DEVICES\b|\bOMP_NUM_THREADS\b|\b(?:HIP|ROCR)_VISIBLE_DEVICES\b"
    r"|\b(?:MKL|OPENBLAS|NUMEXPR|VECLIB_MAXIMUM)_NUM_THREADS\s*=|\bNCCL_[A-Z_]{3,}\s*=|\bMASTER_(?:ADDR|PORT)\s*="
    r"|\bPYTORCH_CUDA_ALLOC_CONF\s*=|\bdevice_map\s*=|\bcuda:\d\b|\blocalhost:\d{2,5}\b"
    r"|\bsudo\s+[a-z]|\b[\w.-]+@[\w-]+(?:\.[\w-]+)*:[~/][\w./~-]*"
    r"|\baccelerate\s+launch\b|\bdeepspeed\s+--|\bpython3?\s+(?:-m\s+[\w.]+|[\w./-]+\.py)\b"
    r"|\bexport\s+[A-Z][A-Z0-9_]{2,}=|\b(?:job|run|task|slurm)[ _-]?id\s*[:=#]\s*[\w-]{4,}", _A)
_OPS_C_RE = re.compile(
    r"\b(?:compute|GPU|CPU|login|head|worker|training|inference|cloud|remote|dedicated|shared|bare-metal|"
    r"on-prem(?:ise)?)\s+(?:node|server|host|cluster|machine|instance|box)s?\b"
    r"|\bon\s+(?:our|the|a|an|one|two|three|four|eight|\d+)\s+(?:[\w-]+\s+)?(?:server|cluster|workstation|host)s?\b"
    r"|\boffline\s+(?:host|machine|server|box)\b|\b(?:intranet|bastion|jump\s?(?:host|server|box))\b"
    r"|\blaunch\s+(?:logs?|commands?|scripts?)\b"
    r"|\bWSL2?\b|\blaptops?\b|\bssh\b"
    r"|服务器|主机|集群|内网|跳板机|工作站|计算节点", re.I | _A)
_PATH_END = _NOT_CJK_END
_PATH_RE = re.compile(
    r"(?<![\w./:~-])(?:/home/|/Users/|/mnt/|/root/|/scratch/|/nfs/|/gpfs/|/lustre/|/data\d*/|/tmp/|/opt/|"
    r"/private/var/|/var/folders/|/workspace/|/autofs/)" + _PATH_END
    + r"|(?<![\w])[A-Za-z]:[\\/](?:Users|Documents and Settings|home)[\\/]" + _PATH_END
    + r"|\\\\wsl(?:\$|\.localhost)[\\/]" + _PATH_END
    + r"|(?<![\w/.~-])~/[\w.-]+/" + _PATH_END
    + r"|\bfile:///?(?:localhost/)?[A-Za-z]?:?[\\/]?[\w.~-]" + _PATH_END, _A)
# identifying subset for supplement code (/data/, /tmp/, ~/.cache/ are generic there);
# one pattern per literal prefix, so large members are scanned quickly
_IDENT_PATH_RES = (
    re.compile(r"/(?<![\w./:~-]/)(?:home|Users|mnt|root|scratch|nfs|gpfs|lustre|autofs)/" + _PATH_END, _A),
    re.compile(r"(?<![\w])[A-Za-z]:[\\/](?:Users|Documents and Settings)[\\/]" + _PATH_END, _A),
    re.compile(r"\\\\wsl(?:\$|\.localhost)[\\/]" + _PATH_END, _A),
)
_PATH_PLACEHOLDER_RE = re.compile(r"^(?:/home/|/Users/|[A-Za-z]:[\\/]Users[\\/])(?:user|username|you|your[_-]?name|"
                                  r"me|<[^>]*>|\$\{?USER\}?|xxx|name|runner|ubuntu)(?:[\\/]|$)", re.I)
_IPV4_RE = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w]|\.\d)", _A)
_HOST_SUFFIXES = (".local", ".lan", ".internal", ".corp", ".intranet", ".localdomain", ".home.arpa")
_HOST_SUFFIX_RE = re.compile(r"\b[\w-]+(?:\.[\w-]+)*\.(?:local|lan|internal|corp|intranet|localdomain|home\.arpa)\b"
                             r"(?![\w.-])", _A)
_WANDB_RE = re.compile(r"\bwandb\.ai/[\w.-]+", re.I | _A)
_SHARE_RE = re.compile(r"\b(?:drive\.google\.com|docs\.google\.com|(?:www\.)?dropbox\.com/(?:s|sh|scl)|1drv\.ms|"
                       r"onedrive\.live\.com|notion\.(?:so|site)|pan\.baidu\.com|(?:[\w-]+\.)?feishu\.cn|"
                       r"(?:[\w-]+\.)?larksuite\.com|(?:www\.)?yuque\.com|app\.box\.com/s|wetransfer\.com|mega\.nz)"
                       r"/[^\s)\]}>\"']*", re.I | _A)
_URL_RE = re.compile(r"\bhttps?://[^\s)\]}>\"']+|\bwww\.[^\s)\]}>\"']+", re.I | _A)
_HEX_LONG_RE = re.compile(r"(?<![\w-])(?:[0-9a-f]{64}|[0-9a-f]{40}|[0-9a-f]{32}|[0-9A-F]{64}|[0-9A-F]{40}|[0-9A-F]{32})(?![\w-])",
                          _A)
_UUID_RE = re.compile(r"(?<![\w-])[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}(?![\w-])", _A)
_COMMIT_RE = re.compile(r"\b(?:commit|rev(?:ision)?|sha1?|git\s+hash|hash|checkpoint|ckpt)\s*(?:id\s*)?[:=#]?\s*"
                        r"([0-9a-f]{7,40})\b", re.I | _A)
_HASH_WORD_RE = re.compile(r"\bSHA-?(?:1|224|256|384|512)\b|\bMD5\b|\bchecksums?\b|\bhash[- ]chains?\b|"
                           r"\bhash(?:es)?\s+of\s+(?:the|every|each|all)\b|\b(?:code|commit|git|config(?:uration)?)\s+"
                           r"hash(?:es)?\b|哈希|校验和", re.I | _A)
_TZ = r"(?:CST|CEST|CET|UTC|GMT|PST|PDT|EST|EDT|BST|JST|KST|IST|AEST|AEDT|HKT|SGT|AoE)"
_CLOCK_TZ_RE = re.compile(
    r"\b(?:[01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d)?\s*(?:[AaPp]\.?\s?[Mm]\.?\s*)?\(?\s*" + _TZ
    + r"(?:\s*[+-]\s*\d{1,2}(?::?\d{2})?)?\b\)?|北京时间\s*\d{1,2}\s*[:：点时]\s*\d{0,2}|\d{1,2}\s*[:：]\s*\d{2}\s*[（(]?\s*北京时间",
    _A)
_MONTHS = r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
_MON3 = r"(?:Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?"
_DATE_RE = re.compile(
    r"(?<![\w.])20\d\d-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])(?![\w])"
    r"|\b(?:" + _MONTHS + "|" + _MON3 + r")\s+(?:[1-9]|[12]\d|3[01])(?:st|nd|rd|th)?,\s*20\d\d\b"
    r"|\b(?:[1-9]|[12]\d|3[01])\s+" + _MONTHS + r",?\s+20\d\d\b"
    r"|\b" + _MONTHS + r"\s+20\d\d\b"
    r"|\bthe\s+" + _MONTHS + r"\s+(?:runs?|records?|batch(?:es)?|experiments?|data|results|sweeps?)\b"
    r"|\d{1,2}\s*月\s*\d{1,2}\s*日|20\d\d\s*年\s*\d{1,2}\s*月"
    r"|(?<![\w.])20\d\d(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])(?:\d{2,4})?(?!\w|\.\d)", _A)
_STAMP_RE = re.compile(r"\b(?:launch|start(?:ing)?|end|finish)\s+(?:time\s*)?stamps?\b", re.I | _A)
_ACCESSED_RE = re.compile(r"(?:accessed|retrieved|last\s+visited|visited\s+on|访问于|访问日期|最后访问)[\s:：,]*(?:on\s+)?$", re.I)
# literature or model scoping, not the authors' own timeline
_LITDATE_RE = re.compile(r"(?:posted|published|released|available|appeared|introduced|cut-?off)\s+(?:on\s+|in\s+)?"
                         r"(?:after|before|since|until|by|from|in|on|of)?\s*$", re.I)
_REVIEW_RE = re.compile(
    r"\breviewers?\s*#\s*\d+\b|\b[Rr]eviewer\s+[1-9]\b"
    r"|\breviewers?\s+(?:asked|requested|pointed\s+out|suggested|noted|raised|wanted|were\s+concerned|questioned)\b"
    r"|\b(?:as|per)\s+(?:the\s+)?reviewers?(?:'s?)?\s+(?:requested|suggested|asked|comments?|feedback|request)\b"
    r"|\brebuttal\b|\bcamera[- ]ready\b|\bprevious\s+(?:submission|version|draft|round)s?\b|\bthis\s+revision\b"
    r"|\bin\s+response\s+to\s+(?:the\s+)?(?:reviewers?|reviews|comments|feedback)\b|\bresubmission\b|"
    r"\bmeta-?review(?:er)?s?\b|\barea\s+chairs?\b"
    r"|\bsimulat\w*\s+(?:peer[- ])?review(?:er)?s?\b|\b(?:mock|simulated|internal|pre-submission)\s+(?:peer[- ])?"
    r"review(?:s|ers?)?\b|\breviewer\s+critiques?\b"
    r"|审稿|答辩|返修|上一版|按审稿意见|根据审稿意见|模拟审稿", re.I | _A)
_REVISION_RE = re.compile(
    r"\bround[-_]\d+\b|\bphase_\d+\b|(?<![\w.-])v\d+(?:\.\d+)?:"
    # re-runs as narration ("we re-ran", "had to rerun", "rerun after the fix"), not a
    # design term ("the second rerun", "a preregistered rerun")
    r"|\bre-?ran\b|\bre-?running\b|\b(?:we|to|was|were|been|be|had|have|has|then|must|should|could)\s+re-?run\b"
    r"|\bre-?run\s+(?:after|because|once|again|it|them|everything|all\s+(?:the\s+)?(?:runs|experiments))\b"
    r"|\brelaunch(?:ed|es|ing)?\b|\bhot-?fix(?:es|ed)?\b|\bbug[- ]?fix(?:es|ed)?\b"
    r"|\bafter\s+fixing\s+(?:a|the|an?\s+[\w-]+)\s+bug\b"
    r"|\b(?:earlier|previous|older|old|later)\s+(?:runs?|launch(?:es)?|attempts?|registrations?|sweeps?|batch(?:es)?|"
    r"series)\b"
    r"|\bdated\s+(?:addend(?:um|a)|amendments?|entr(?:y|ies)|records?|notes?|logs?)\b|\bfirst[- ]version\s+(?:of\s+)?"
    r"(?:this|the|our|its)?\s*(?:scan|analysis|script|code|pipeline|run|implementation)\b"
    r"|\bbefore\s+(?:its|their|the)\s+first\s+run\b"
    r"|\bchronology\b|\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)(?:\s*(?:to|-|–)\s*(?:\d+|[a-z]+))?"
    r"\s+days\s+apart\b"
    r"|\bin\s+this\s+session\b|\bthe\s+user\s+(?:asked|requested|required|wanted)\b|用户要求|用户规定|重新跑|重跑", re.I | _A)
# work announced but not done: an authors' decision, never reworded away
_PENDING_RE = re.compile(
    r"\bnot\s+yet\s+(?:been\s+)?(?:evaluated|run|analy[sz]ed|finished|completed|computed|tested|verified|implemented|"
    r"scored|collected|measured)\b"
    r"|\bto\s+be\s+(?:added|completed|filled(?:\s+in)?|updated|evaluated|computed|written|finali[sz]ed|run|reported)\b"
    r"|\b(?:results?|numbers?|values?|scores?|evaluations?|analys[ie]s|experiments?|runs?)\s+(?:are\s+|is\s+)?"
    r"(?:still\s+)?pending\b|\bpending\s+(?:results?|evaluations?|analys[ie]s|runs?|completion)\b"
    r"|尚未(?:评估|运行|完成|分析)|待补充|待完成", re.I | _A)
_PENDING_CS_RE = re.compile(r"(?<![\w\[-])(?:TBD|TBA)(?![\w\]-])", _A)  # "[TBD]" is a TEXT-MARKER
_AI_BRAND_RE = re.compile(r"\b(?:ChatGPT|GPT-?[3-9](?:\.\d)?o?|Claude(?:\s+Code)?|Codex|Copilot|Gemini|DeepSeek|Kimi|"
                          r"Grok|Qwen|Devin|Perplexity)\b|文心一言|通义千问|豆包", _A)
_AI_VERB_RE = re.compile(r"\b(?:wr[io]te|written|writ(?:e|ing)|polish(?:ed|ing)?|proofread(?:ing)?|edit(?:ed|ing)?|"
                         r"draft(?:ed|ing)?|cod(?:ed|ing)|debug(?:ged|ging)?|refactor(?:ed|ing)?|assist(?:ed|ance)?|"
                         r"help(?:ed)?|implement(?:ed|ing)?|generat(?:e|ed|ing)|translat(?:e|ed|ion))\b|撰写|编写|润色|协助|辅助|生成|实现",
                         re.I | _A)
_AI_OBJ_RE = re.compile(r"\b(?:paper|manuscript|draft|text|writing|prose|code|codebase|implementation|scripts?|figures?|"
                        r"proofs?|experiments?|sections?)\b|论文|代码|实验|稿", re.I | _A)
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?。！？])\s+")
_EMAIL_RE = re.compile(r"(?:\{[^{}@]{1,200}\}|(?<![\w.+-])[A-Za-z0-9._%+-]+)@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"
                       r"(?![\w-])", _A)
_EMAIL_PLACEHOLDER_RE = re.compile(r"@(?:example\.(?:com|org|net|edu)|anonymous\.|anon\.|domain\.(?:com|org)|"
                                   r"email\.com|xxx\.)|^(?:anonymous|anon|author|name|user|email|first\.last|"
                                   r"firstname\.lastname|xxx|your[._-]?name|someone)@", re.I)
_LINK_RE = re.compile(
    r"(?<![\w.-])(?:https?://)?(?:www\.)?(?P<host>github\.com|gitlab\.com|bitbucket\.org|huggingface\.co|hf\.co|"
    r"codeberg\.org|gitee\.com|kaggle\.com|osf\.io)/(?P<path>[\w.~-]+(?:/[\w.~-]+)?)"
    r"|(?<![\w.-])(?:https?://)?(?P<pages>[\w-]+)\.(?:github|gitlab)\.io\b"
    r"|(?<![\w.-])(?:https?://)?(?:sites\.google\.com/view|scholar\.google\.com/citations\?user=|orcid\.org|"
    r"(?:www\.)?linkedin\.com/in|(?:twitter|x)\.com)/?(?P<prof>[\w.-]+)", re.I | _A)
_LINK_NON_OWNER = {"anonymous", "anon", "features", "topics", "orgs", "settings", "about", "docs", "blog", "papers",
                   "pricing", "login", "join", "explore", "collections", "tasks", "learn", "marketplace", "sponsors",
                   "search", "trending", "enterprise", "spaces", "models", "datasets", "competitions", "code"}
_SELFCITE_RE = re.compile(
    r"\b(?:we|our|my|I)\s+(?:prior|previous|earlier)\s+(?:work|paper|study|studies)\b"
    r"|\b(?:in|from)\s+our\s+(?:prior|previous|earlier)\s+(?:work|paper|study)\b"
    r"|\b(?:we|I)\s+(?:previously\s+)?(?:showed|proved|demonstrated|introduced|proposed)\s+(?:in|previously|earlier)\b"
    r"(?!\s+(?:Section|Sec\.|Appendix|App\.|Table|Figure|Fig\.|Theorem|Lemma|Eq|Equation|this|the\s+(?:previous|next|"
    r"following|preceding)\s+section|§|[0-9]))", re.I | _A)
_FUNDING_RE = re.compile(r"\b(?:supported|funded)\s+(?:in\s+part\s+)?by\b[^.]{0,120}?\b(?:grant|award|fellowship|NSF|NIH|ERC|"
                         r"NSFC|DFG|DARPA|ONR|EPSRC|JSPS)\b", re.I | _A)
_TC_ESC_RE = re.compile(r"\\[ntr](?![a-z])")
_TC_CTRL_RE = re.compile(r"\\[A-Za-z]{2,}\*?")
# an escape glued to words on both sides ("see\nTable", "that\nlatency") is
# residue, never a deliberate mention; the source spelling of the same defect
# (see\textbackslash nTable) must not certify itself as verbatim text
_GLUED_ESC_AT = re.compile(r"\\[ntr](?=[A-Za-z])")
_GLUED_ESC_SRC_RE = re.compile(r"(?<=[A-Za-z0-9])\\textbackslash(?:\{\}|[ \t])?[ntr](?=[A-Za-z])")
# the same defect in the sources, with the escape letter and the glued word, so
# the PDF finding ("\\nwidth") gets the file and line an `escape` fix needs
_GLUED_ESC_SRC_WORD_RE = re.compile(r"(?<=[A-Za-z0-9])(?:\\textbackslash(?:\{\}|[ \t])?|\$\\backslash\$\s?)"
                                    r"([ntr])([A-Za-z]+)")
_GLUED_ESC_NOTE = "an escape glued to the words on both sides"
_TC_BOXED_RE = re.compile(r"\\boxed\{")
_TC_MD_BOLD_RE = re.compile(r"\*\*[^*\s][^*\n]{0,80}?\*\*")
_TC_MD_HEAD_RE = re.compile(r"^#{2,6}\s+\S.*$|^#\s+[A-Z][a-z]+(?:\s+[A-Za-z]+)+\s*$")
_TC_SNAKE_RE = re.compile(r"(?<![\w/.:@-])[a-z][a-z0-9]*(?:_[a-z0-9]+)+(?![\w/.@-])", _A)
_MARKER_D_RE = re.compile(r"\bTODO\b|\bFIXME\b|\[VERIFY\]|\bDATA_NEEDED\b|\[TBD\]|\bTKTK\b", _A)
_MARKER_D2_RE = re.compile(r"\[(?:citation|cite|ref)\s+needed\]", re.I)
_MARKER_C_RE = re.compile(r"\bXXX+\b", _A)
_REPL_D_RE = re.compile(r"[\ufffd\x00-\x08\x0b\x0e-\x1f\x7f]")
_REPL_C_RE = re.compile(r"[\ue000-\uf8e4]")  # U+F8E5..U+F8FF are large-delimiter pieces of math extension fonts
_GLUE_LONG_RE = re.compile(r"(?<![\w/.:@-])[A-Za-z]{20,}(?![\w/.@-])", _A)
_GLUE_CAMEL_RE = re.compile(r"(?<![\w/.:@-])[a-z]{3,}[A-Z][a-z]{2,}(?![\w/.@-])", _A)
_GLUE_SMALL_RE = re.compile(r"(?<![\w-])(?:[Ll]et|[Ww]ith|of|by|at|to|over|and|is|are|for|from|where|then|[Ss]uppose)"
                            r"[A-Z\u0391-\u03a9\u03b1-\u03c9](?![a-z])", _A)
# a reference or equation number glued to the next word: "Eq. (3)gives", "Table 2shows"
_GLUE_REFNUM_RE = re.compile(r"\b(?:Eqs?\.|Equations?|Tables?|Tabs?\.|Figures?|Figs?\.|Sections?|Secs?\.|Appendix|App\.|"
                             r"Theorems?|Lemmas?|Algorithms?|Lines?)\s*~?\s*\(?(?:[A-Z]\.\d+(?:\.\d+)*|\d+(?:\.\d+)*)\)?"
                             r"(?=[a-z]{2,})|\(\d{1,3}\)(?=[a-z]{3,})", _A)
_GLUE_SUFFIXES = ("tion", "tions", "ment", "ments", "ness", "ability", "ization", "izations", "isation", "ically",
                  "ality", "ities", "ingly", "ational", "ousness", "fulness", "iveness", "ibility", "ically")
_NUMFMT_RE = re.compile(r"\b\d(?:\.\d+)?[eE][-+]\d{2,3}\b|\[\s*-?\d+(?:\.\d+)?,\S|(?<![\w.\-−])-\d+\.\d+", _A)
_QQ_CTX_RE = re.compile(
    r"(?:Figures?|Figs?\.|Tables?|Tabs?\.|Sections?|Secs?\.|Appendix|Appendices|App\.|Eqs?\.|Equations?|Theorems?|"
    r"Thms?\.|Lemmas?|Corollary|Cor\.|Propositions?|Prop\.|Definitions?|Def\.|Algorithms?|Alg\.|Lines?|Listings?|"
    r"Chapters?|Assumptions?|Remarks?|Examples?|Steps?|Parts?|§|图|表|附录|公式|式|定理|引理|算法|章节|节|第)"
    r"\s*~?\s*\(?\s*\?\?(?!\?)\s*\)?")
_QQ_PAREN_RE = re.compile(r"\(\s*\?\?\s*\)")
_QQ_ANY_RE = re.compile(r"(?<!\?)\?\?(?!\?)")
_CITE_Q_RE = re.compile(r"\[\s*\?\s*(?:[,;]\s*\?\s*)*\]|(?<!\w)\(\s*\?\s*(?:[,;]\s*\?\s*)*\)|(?<!\w)\?\s+\(\s*\?\s*\)", _A)
_SECTION_CTX_RE = re.compile(r"(?:\b(?:Sections?|Secs?\.|Tables?|Figures?|Figs?\.|Eqs?\.|Equations?|Algorithms?|Lines?|"
                             r"Appendix|App\.|Steps?|Theorems?|Thms?\.|Lemmas?|Corollary|Cor\.|Propositions?|Prop\.|"
                             r"Definitions?|Def\.|Assumptions?|Remarks?|Examples?|Claims?|Chapters?|Parts?|version|"
                             r"ver\.|release|build|v)|§|==|=)\s*$", re.I | _A)
_LIB_TAIL_RE = re.compile(r"(?<![\w-])(?:" + _STRONG_LIBS + r")\s*$", re.I | _A)
# a random seed or salt shaped like a calendar date (20991231): next to a seed
# word it dates the study (PROC-DATESEED); elsewhere it is a PROC-TIME candidate
# (a sentence's full stop may follow it; a decimal point and digits may not)
_DATESEED_NUM_RE = re.compile(r"(?<![\w.])20\d\d(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{0,4}(?!\w|\.\d)", _A)
_SEED_WORD_RE = re.compile(r"\b(?:seeds?|seeded|salts?|salted|random[- ]states?|rng|prng|random\s+number\s+generators?|"
                           r"nonces?)\b", re.I | _A)
# a README, script, notebook, or config file named in the prose (ENG-FILENAME)
_FILENAME_RE = re.compile(r"(?<![\w/.\\-])(?:README(?:\.(?:md|txt|rst))?(?![\w-])(?!\.[A-Za-z0-9])|(?:[A-Za-z_][\w.-]*/)*"
                          r"[A-Za-z_][\w-]*(?:\.[\w-]+)*\.(?:py|sh|bash|ipynb|ya?ml|toml|cfg|ini|jsonl?|md)(?![\w/-]))", _A)
_SUPPLEMENT_WORD_RE = re.compile(r"\bsupplement(?:ary|al)?\b|\bappendix\b", re.I | _A)
# reference failures that a queued reference repair and a full rebuild resolve
_XREF_SYMPTOMS = ("XREF-PDF-QQ", "XREF-PDF-CITE", "XREF-PDF-KEY", "XREF-LOG-REF", "XREF-LOG-CITE", "XREF-LOG-UNDEF",
                  "XREF-BLG")
# numeric precision and weight-loading detail (ENG-PRECISION, policy precision_disclosure: candidate)
_PRECISION_RE = re.compile(r"(?<![\w-])(?:bf16|bfloat16|fp16|float16|fp8|float8|e4m3|e5m2|int8|int4|nf4|tf32|"
                           r"half[- ]precision|mixed[- ]precision|(?:8|4)-bit\s+(?:weights|quantization|loading|"
                           r"precision))(?![\w-])|\bdequantiz\w*", re.I | _A)
# registration amendment labels (PROC-REGLABEL; policy registration_labels)
_REGLABEL_ID_RE = re.compile(r"\b(?:Amendments?|Addend(?:um|a)|Clarifications?|Errat(?:um|a))\s+(?:[A-Z]\d{0,2}|\d{1,2}|"
                             r"[IVX]{1,4})\b(?![\w-])", _A)
_REGLABEL_PHRASE_RE = re.compile(
    r"\b(?:registered|pre-?registered|protocol|post-?hoc|post-\w+|late)\s+(?:amendments?|addend(?:um|a)|"
    r"clarifications?)\b"
    r"|\b(?:amendments?|addend(?:um|a)|clarifications?)\s+(?:to|of)\s+(?:the\s+|this\s+|our\s+)?(?:pre-?)?"
    r"(?:registration|registered\s+plan|protocol|analysis\s+plan)\b"
    r"|\bamended\s+(?:subsets?|samples?|splits?|plans?|rules?|protocols?|registrations?|analys[ie]s)\b", re.I | _A)
_REGLABEL_KIND = {"amend": "amendment", "addend": "addendum", "clarif": "clarification", "errat": "erratum"}
_REGLABEL_ANY_RE = re.compile("(?:%s)|(?i:%s)" % (_REGLABEL_ID_RE.pattern, _REGLABEL_PHRASE_RE.pattern), _A)
# A hardware word that names a measured quantity ("measured CPU cost", "elapsed CPU query/ranking time", "peak
# GPU memory") — no amount right before it — is a metric of the study, not the authors' machine; one inside the
# brackets of a heading ("## T3 — toy recount (CPU, archived logs)") is the heading's wording. Neither is drafted as a
# deletion, and a reviewer's leak ruling does not raise either to BLOCK (WARN at most, for a person).
_HW_GAP = r"(?:-|[ \t]+|[ \t]*\n[ \t]*)"   # a hyphen, spaces, or one line break of the same paragraph
_HW_METRIC_TAIL_RE = re.compile(r"(?:" + _HW_GAP + r"(?:[\w.-]+/){0,4}[\w.-]+)?" + _HW_GAP
                                + r"(?:cost|costs|time|times|timing|timings|"
                                r"memory|hours?|seconds?|minutes?|throughput|latency|latencies|usage|"
                                r"utili[sz]ation|budget|footprint|load|consumption|efficiency|speed|cycles?)\b",
                                re.I | _A)
_HW_AMOUNT_BEFORE_RE = re.compile(r"\d[\d.,]*\s*(?:[x×*-]\s*)?(?:\$\\times\$\s*)?$")
_DOC_HEADING_RE = re.compile(r"^\s*(?:#{1,6}\s|=+\s|\\(?:sub){0,2}section\*?\s*\{|\\paragraph\*?\s*\{|\\caption\s*\{)")
# A compute measure named with no amount next to it ("the latency and peak memory per toy arm"; "fewer
# GPU-hours than the baseline") is what the study measures, not what the authors used: a metric as well.
# With an amount before or right after it ("120 GPU-hours", "two hundred GPU-hours", "peak memory of 40 GB")
# it is compute accounting, the rule's own case.
_QTY_MEASURE_END_RE = re.compile(r"(?:memory|hours?|days?|years?|months?|seconds?|小时|机时|显存)$", re.I)
_QTY_AMOUNT_BEFORE_RE = re.compile(
    r"(?:\d[\d.,]*|(?<![\w-])(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|thirty|"
    r"forty|fifty|hundreds?|thousands?|dozens?|several|few|many))\s*(?:[x×*-]\s*)?$", re.I)
_QTY_AMOUNT_AFTER_RE = re.compile(r"[^\n,;.]{0,25}?\d[\d.,]*\s*(?:[KMGT]i?B|bytes|h|hrs?|hours?|s|sec|seconds?|"
                                  r"min|minutes?|days?)\b", re.I)


def _hw_usage(text: str, s: int, e: int, heading: Optional[bool] = None) -> Optional[str]:
    """'metric' or 'title' for the hardware word at text[s:e] (see above), else
    None. `heading` says whether its line is a heading (None: read the line —
    a Markdown or LaTeX heading)."""
    lo = text.rfind("\n", 0, s) + 1
    hi = text.find("\n", e)
    hi = len(text) if hi < 0 else hi
    is_heading = bool(_DOC_HEADING_RE.match(text[lo:hi])) if heading is None else heading
    if is_heading:
        before, after = text[lo:s], text[e:hi]
        if before.count("(") + before.count("（") > before.count(")") + before.count("）") and re.search(r"[)）]", after):
            return "title"
    m = _HW_METRIC_TAIL_RE.match(text, e)
    if m and len(m.group(0)) <= 60 and not _HW_AMOUNT_BEFORE_RE.search(text[max(0, s - 16):s]):
        return "metric"
    span = text[s:e].strip()
    if (span and not re.search(r"\d", span) and _QTY_MEASURE_END_RE.search(span)
            and not _QTY_AMOUNT_BEFORE_RE.search(text[max(0, s - 24):s]) and not _QTY_AMOUNT_AFTER_RE.match(text, e)):
        return "metric"
    return None

_REF_REGION_SKIP = frozenset({
    "ENG-VER", "ENG-FW", "ENG-HW", "ENG-QTY", "ENG-OPS", "ENG-PATH", "ENG-NET", "ENG-HASH",
    "PROC-TIME", "PROC-REVIEW", "PROC-REVISION", "PROC-AITOOL", "PROC-PENDING", "ANON-LINK",
    "ANON-SELFCITE", "TEXT-GLUE", "TEXT-NUMFMT", "ANON-ACK", "ENG-FILENAME", "ENG-PRECISION", "PROC-DATESEED",
    "PROC-REGLABEL"})
# Sections whose subject is compute or other people's systems: hardware and
# framework names there are INFO, but still go to the reviewer (low priority).
_COMPUTE_SUBS = frozenset({"compute", "related_work"})
# INFO candidates that still reach the reviewer as low-priority groups: a
# section heuristic, the verbatim rule, or the deleted-clause rule of NUM-DRIFT
# demoted them, and no heuristic may be the last word ("leak" restores the
# confirmed level).
_REVIEWED_DEMOTIONS = ("region", "verbatim", "explained", "pointer")


_VQUOTES = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-", "\u2014": "-",
                          "\u2212": "-", "\u21a9": None, "\u21aa": None, "\u21b5": None})


def _vnorm(s: str) -> str:
    """Comparison form for verbatim matching: NFKC, straight quotes, no
    listings line-break arrows, no whitespace at all (extractors add and drop
    spaces freely in monospaced text)."""
    s = unicodedata.normalize("NFKC", s or "").replace("\u2190\u21a9", "")
    return re.sub(r"\s+", "", s.translate(_VQUOTES))


class ScanContext:
    """Everything a detector needs: mode, matchers, enabled checks, literals."""

    def __init__(self) -> None:
        self.anonymous = True
        self.strict = False
        self.hardware = BLOCK
        self.framework = WARN
        # SUPP-HW: None = INFO, not reviewed (policy supp_hardware: info); WARN or
        # BLOCK = the level a reviewer-confirmed leak takes (a scan follows the
        # hardware policy unless supp_hardware names another level)
        self.supp_hardware: Optional[str] = None
        # policy switches: precision and loading detail (exempt | candidate),
        # registration amendment labels (keep: INFO | flag: candidates)
        self.precision = "exempt"
        self.reg_labels = "keep"
        # code names an earlier fix round reported: reported while any occurrence is left
        self.persisted_codenames: List[str] = []
        self.codename_hits: Counter = Counter()
        self.codename_where: Dict[str, List[str]] = {}
        self.paper_script = "latin"  # "cjk" when the PDF text is mostly CJK (SUPP-LANG)
        self.run_mode = "audit"
        self.policy: Dict[str, Any] = {}
        self.identity = TermMatcher([])
        self.derived_users: Set[str] = set()  # logins an author's name commonly becomes (plee), before an '@'
        self.auto = TermMatcher([])
        self.deny = TermMatcher([])
        self.exempt = TermMatcher([])
        self.exempt_used: Counter = Counter()
        self.redactor = Redactor()
        self.enabled: Set[str] = set(CHECKS)
        self.verbatim_blob = ""
        self._vcache: Tuple[str, str] = ("", "")
        self.has_invisible_set = True

    def on(self, check: str) -> bool:
        return check in self.enabled

    def verbatim_norm(self) -> str:
        if self._vcache[0] is not self.verbatim_blob:
            self._vcache = (self.verbatim_blob, _vnorm(self.verbatim_blob))
        return self._vcache[1]


def _verbatim_context(text: str, s: int, e: int, ctx: ScanContext, need: int = 8) -> bool:
    """True when the hit and enough of its PDF neighbourhood occur in a verbatim
    source region (listing, verbatim, \\texttt, \\verb, a table cell): the
    authors typeset it on purpose. A short literal ('??', '\\n') needs at least
    `need` characters of matching context — a literal that merely occurs
    somewhere in a listing proves nothing about this occurrence."""
    blob = ctx.verbatim_norm()
    if not blob:
        return False
    core = _vnorm(text[s:e])
    if not core or core not in blob:
        return False
    if len(core) >= 12:
        return True
    left, right = _vnorm(text[max(0, s - 32):s]), _vnorm(text[e:e + 32])
    for n_l, n_r in ((12, 12), (12, 0), (0, 12), (6, 6), (8, 0), (0, 8)):
        cand = (left[-n_l:] if n_l else "") + core + (right[:n_r] if n_r else "")
        if len(cand) >= need and len(cand) > len(core) and cand in blob:
            return True
    return False


def _overlaps(spans: Sequence[Tuple[int, int, Any]], s: int, e: int) -> bool:
    return any(a < e and s < b for a, b, *_ in spans)


def _ipv4_ok(text: str, m: Any) -> Optional[str]:
    parts = [int(x) for x in m.group(0).split(".")]
    if any(p > 255 for p in parts):
        return None
    before = text[max(0, m.start() - 30):m.start()]
    if _SECTION_CTX_RE.search(before) or _LIB_TAIL_RE.search(before):
        return None
    a, b = parts[0], parts[1]
    private = (a in (10, 127) or (a == 172 and 16 <= b <= 31) or (a == 192 and b == 168)
               or (a == 169 and b == 254) or (a == 100 and 64 <= b <= 127))
    return DEFINITE if private else CANDIDATE


def _host_ok(text: str, m: Any, code: bool = False) -> bool:
    """A '.internal/.local/.corp' name that is a hostname, not an attribute
    chain ('cfg.cluster.internal', 'self.cfg.local'). In code, only a URL host,
    user@host, or a quoted host string counts."""
    before = text[max(0, m.start() - 5):m.start()]
    after = text[m.end():m.end() + 1]
    if after in ("(", "[") or before.endswith(("self.", "this.", "cls.")):
        return False
    if code:
        return before.endswith(("//", "@")) or (before[-1:] in ("'", '"') and after in ("'", '"', ":", "/"))
    return True


def _hex_ok(s: str) -> bool:
    return bool(re.search(r"\d", s)) and bool(re.search(r"[a-fA-F]", s))


def detect_text(text: str, region: str, sub: Optional[str], ctx: ScanContext, layer: str = "pdf",
                lines: Optional[Sequence[str]] = None, joins: Optional[Sequence[int]] = None) -> List[Hit]:
    """All text-pattern detectors over one segment (PDF) or paragraph (tex)."""
    hits: List[Hit] = []
    if not text:
        return hits
    folded = fold_text(text)
    exempt_spans = ctx.exempt.finditer(text, folded) if ctx.exempt else []
    urls = [(m.start(), m.end(), None) for m in _URL_RE.finditer(text)]

    def add(check: str, cert: str, sev: str, s: int, e: int, match: Optional[str] = None,
            note: Optional[str] = None, demoted: Optional[str] = None, usage: Optional[str] = None,
            plan_only: bool = False) -> None:
        if not ctx.on(check):
            return
        if cert == CANDIDATE and exempt_spans:
            # policy exempt_terms quiet lookalike CANDIDATES only; a definite
            # finding (a version, a path, a secret, a printed ??) is never quieted
            lab = next((lb for a, b, lb in exempt_spans if a < e and s < b), None)
            if lab is not None:
                ctx.exempt_used[lab] += 1
                return
        if any(h.check == check and h.start < e and s < h.end for h in hits):
            return  # one finding per span and check (two regexes, one hit)
        hits.append(Hit(check, cert, sev, s, e, match, note, demoted, usage, plan_only))

    # XREF (PDF only: sources are checked structurally)
    if layer == "pdf":
        qq_ref = [(m.start(), m.end(), None) for m in _QQ_CTX_RE.finditer(text)]
        qq_ref += [(m.start(), m.end(), None) for m in _QQ_PAREN_RE.finditer(text)]
        for m in _QQ_ANY_RE.finditer(text):
            s, e = m.start(), m.end()
            if _overlaps(qq_ref, s, e):  # "Table ??", "(??)": a reference, never excused
                add("XREF-PDF-QQ", DEFINITE, BLOCK, s, e, "??")
                continue
            prev_c = text[s - 1] if s > 0 else " "
            next_c = text[e] if e < len(text) else " "
            if _verbatim_context(text, s, e, ctx):
                add("XREF-PDF-QQ", CANDIDATE, INFO, s, e, "??", "the same text is typeset verbatim in the sources",
                    demoted="verbatim")
            elif not prev_c.isalnum() and not next_c.isalnum():
                add("XREF-PDF-QQ", DEFINITE, BLOCK, s, e, "??")
            else:
                add("XREF-PDF-QQ", CANDIDATE, WARN, s, e, "??", "?? is glued to a word")
        for m in _CITE_Q_RE.finditer(text):
            add("XREF-PDF-CITE", DEFINITE, BLOCK, m.start(), m.end())
    in_refs = region == "references"
    # ENG-VER
    ver_spans: List[Tuple[int, int, Any]] = []
    for rx in _ENG_VER_RES:
        for m in rx.finditer(text):
            if _overlaps(ver_spans, m.start(), m.end()):
                continue
            ver_spans.append((m.start(), m.end(), None))
            add("ENG-VER", DEFINITE, BLOCK, m.start(), m.end())
    hwish = sub in _COMPUTE_SUBS or region == "checklist"
    dnote = ("INFO in the %s section" % (sub or region).replace("_", " ")) if hwish else None

    def cand(check: str, s: int, e: int) -> None:
        usage = _hw_usage(text, s, e, heading=False) if check in ("ENG-HW", "ENG-QTY") else None
        if hwish:
            add(check, CANDIDATE, INFO, s, e, note=dnote, demoted="region", usage=usage)
        else:
            add(check, CANDIDATE, WARN, s, e, note=("the hardware word names a measured quantity here"
                                                    if usage == "metric" else None), usage=usage)

    for m in _FW_RE.finditer(text):
        if not _overlaps(ver_spans, m.start(), m.end()):
            cand("ENG-FW", m.start(), m.end())
    for m in _HW_RE.finditer(text):
        cand("ENG-HW", m.start(), m.end())
    for m in _QTY_RE.finditer(text):
        cand("ENG-QTY", m.start(), m.end())
    for m in _QTY_BARE_CORES_RE.finditer(text):
        if _COMPUTE_CTX_RE.search(text[max(0, m.start() - 60):m.end() + 60]):
            cand("ENG-QTY", m.start(), m.end())
        else:  # "50 cores" with no compute word nearby (a game core, a fruit core)
            add("ENG-QTY", CANDIDATE, INFO, m.start(), m.end(), note="no compute context nearby")
    ops_spans: List[Tuple[int, int, Any]] = []
    for m in _OPS_D_RE.finditer(text):
        if _overlaps(urls, m.start(), m.end()) and "@" not in m.group(0):
            continue
        ops_spans.append((m.start(), m.end(), None))
        add("ENG-OPS", DEFINITE, BLOCK, m.start(), m.end())
    for m in _OPS_C_RE.finditer(text):
        if not _overlaps(ops_spans, m.start(), m.end()):
            add("ENG-OPS", CANDIDATE, WARN, m.start(), m.end())
    for m in _PATH_RE.finditer(text):
        if not _overlaps(urls, m.start(), m.end()):
            add("ENG-PATH", DEFINITE, BLOCK, m.start(), m.end())
    for m in _IPV4_RE.finditer(text):
        cert = _ipv4_ok(text, m)
        if cert:
            add("ENG-NET", cert, BLOCK if cert == DEFINITE else WARN, m.start(), m.end())
    for m in _HOST_SUFFIX_RE.finditer(text):
        if _host_ok(text, m) and not (layer == "pdf" and _verbatim_context(text, m.start(), m.end(), ctx)):
            add("ENG-NET", DEFINITE, BLOCK, m.start(), m.end())
    for m in _WANDB_RE.finditer(text):
        add("ENG-NET", DEFINITE, BLOCK, m.start(), m.end())
    for m in _SHARE_RE.finditer(text):
        add("ENG-NET", DEFINITE, BLOCK if ctx.anonymous else INFO, m.start(), m.end())
    for rx in (_HEX_LONG_RE, _UUID_RE):
        for m in rx.finditer(text):
            if rx is _UUID_RE or _hex_ok(m.group(0)):
                add("ENG-HASH", DEFINITE, BLOCK, m.start(), m.end())
    for m in _COMMIT_RE.finditer(text):
        if _hex_ok(m.group(1)):
            add("ENG-HASH", DEFINITE, BLOCK, m.start(), m.end())
    for m in _HASH_WORD_RE.finditer(text):
        add("ENG-HASH", CANDIDATE, WARN, m.start(), m.end())
    for s, e in find_secrets(text):
        add("ENG-SECRET", DEFINITE, BLOCK, s, e)
    if ctx.deny:
        for s, e, _label in ctx.deny.finditer(text, folded):
            add("ENG-DENY", DEFINITE, BLOCK, s, e)
    path_like = [(h.start, h.end, None) for h in hits if h.check in ("ENG-PATH", "ENG-NET", "ENG-OPS")]
    for m in _FILENAME_RE.finditer(text):
        if _overlaps(urls, m.start(), m.end()) or _overlaps(path_like, m.start(), m.end()):
            continue
        if m.group(0).startswith("README") and _SUPPLEMENT_WORD_RE.search(text[max(0, m.start() - 30):m.end() + 30]):
            continue  # "the supplementary README" is the pointer to the supplement a paper should give
        if region == "end_matter":  # a reproducibility statement may point to the supplement's README
            add("ENG-FILENAME", CANDIDATE, INFO, m.start(), m.end(), note="INFO in an end-matter statement",
                demoted="region")
        elif m.group(0).startswith("README"):  # a pointer to documentation, not a file of the method
            add("ENG-FILENAME", CANDIDATE, INFO, m.start(), m.end(), note="a README is a pointer to the "
                "supplement's documentation", demoted="pointer")
        else:
            add("ENG-FILENAME", CANDIDATE, WARN, m.start(), m.end())
    if ctx.precision == "candidate":
        for m in _PRECISION_RE.finditer(text):
            cand("ENG-PRECISION", m.start(), m.end())
    # PROC
    seed_spans: List[Tuple[int, int, Any]] = []
    for m in _DATESEED_NUM_RE.finditer(text):
        if _SEED_WORD_RE.search(text[max(0, m.start() - 60):m.end() + 60]):
            seed_spans.append((m.start(), m.end(), None))
            add("PROC-DATESEED", CANDIDATE, WARN, m.start(), m.end(), "date-shaped seed")
    for m in _CLOCK_TZ_RE.finditer(text):
        add("PROC-TIME", DEFINITE, BLOCK, m.start(), m.end())
    for m in _DATE_RE.finditer(text):
        before = text[max(0, m.start() - 40):m.start()]
        if _ACCESSED_RE.search(before) or _LITDATE_RE.search(before) or _overlaps(seed_spans, m.start(), m.end()):
            continue
        add("PROC-TIME", CANDIDATE, WARN, m.start(), m.end())
    for m in _STAMP_RE.finditer(text):
        add("PROC-TIME", CANDIDATE, WARN, m.start(), m.end())
    for m in _REVIEW_RE.finditer(text):
        add("PROC-REVIEW", CANDIDATE, WARN, m.start(), m.end())
    for m in _REVISION_RE.finditer(text):
        add("PROC-REVISION", CANDIDATE, WARN, m.start(), m.end())
    for rx in (_PENDING_RE, _PENDING_CS_RE):
        for m in rx.finditer(text):
            add("PROC-PENDING", CANDIDATE, WARN, m.start(), m.end())
    if ctx.reg_labels == "flag":  # with "keep" (the default) a registration label is a required disclosure
        for rx in (_REGLABEL_ID_RE, _REGLABEL_PHRASE_RE):
            for m in rx.finditer(text):
                label = "registration label: %s" % _REGLABEL_KIND[
                    re.search(r"amend|addend|clarif|errat", m.group(0).lower()).group(0)]
                add("PROC-REGLABEL", CANDIDATE, WARN, m.start(), m.end(), label)
    in_ai_statement = region == "end_matter" and sub == "ai_use"
    if ctx.on("PROC-AITOOL") and not in_ai_statement and _AI_BRAND_RE.search(text):
        pos = 0
        for sent in _SENT_SPLIT_RE.split(text):
            start = text.find(sent, pos)
            pos = start + len(sent)
            b = _AI_BRAND_RE.search(sent)
            if b and _AI_VERB_RE.search(sent) and _AI_OBJ_RE.search(sent):
                add("PROC-AITOOL", CANDIDATE, WARN, start + b.start(), start + b.end())
    # ANON
    if ctx.anonymous:
        for matcher, kind in ((ctx.identity, "identity"), (ctx.auto, "auto")):
            for s, e, _label in matcher.finditer(text, folded):
                add("ANON-NAME", DEFINITE, INFO if in_refs else BLOCK, s, e,
                    note="auto identity term" if kind == "auto" else None)
        for m in _EMAIL_RE.finditer(text):
            if not _EMAIL_PLACEHOLDER_RE.search(m.group(0)):
                add("ANON-EMAIL", DEFINITE, INFO if in_refs else BLOCK, m.start(), m.end())
        for m in _LINK_RE.finditer(text):
            owner = None
            if m.group("host"):
                segs = m.group("path").split("/")
                owner = segs[1] if (m.group("host").lower() in ("huggingface.co", "hf.co") and segs[0].lower()
                                    in ("datasets", "spaces", "models") and len(segs) > 1) else segs[0]
            else:
                owner = m.group("pages") or m.group("prof")
            if not owner or owner.lower() in _LINK_NON_OWNER or owner.lower().startswith("anonymous"):
                continue
            ident = bool(ctx.identity.finditer(owner) or ctx.auto.finditer(owner))
            add("ANON-LINK", DEFINITE if ident else CANDIDATE, BLOCK if ident else WARN, m.start(), m.end())
        for m in _SELFCITE_RE.finditer(text):
            add("ANON-SELFCITE", CANDIDATE, WARN, m.start(), m.end())
        for m in _FUNDING_RE.finditer(text):
            add("ANON-ACK", DEFINITE, BLOCK, m.start(), m.end())
    # TEXT
    if layer == "pdf":
        path_spans = [(h.start, h.end, None) for h in hits if h.check == "ENG-PATH"]

        def glued_escape(s: int) -> bool:
            return s > 0 and text[s - 1].isalnum() and _GLUED_ESC_AT.match(text, s) is not None

        def code_hit(s: int, e: int, snake: bool = False) -> None:
            if _verbatim_context(text, s, e, ctx):
                if not snake:  # a verbatim snake_case identifier is not even worth an INFO line
                    # still a low-priority group for the reviewer: the verbatim rule must not be the last word
                    add("TEXT-CODE", CANDIDATE, INFO, s, e, note="typeset verbatim in the sources", demoted="verbatim")
                return
            glued = not snake and glued_escape(s)
            if snake:
                add("TEXT-CODE", CANDIDATE, WARN, s, e)
            elif not glued and _vnorm(text[s:e]) in ctx.verbatim_norm():
                add("TEXT-CODE", CANDIDATE, WARN, s, e, note="also present in a verbatim source region")
            else:
                add("TEXT-CODE", DEFINITE, BLOCK, s, e, note=_GLUED_ESC_NOTE if glued else None)

        for rx in (_TC_ESC_RE, _TC_BOXED_RE, _TC_MD_BOLD_RE):
            for m in rx.finditer(text):
                if not _overlaps(path_spans, m.start(), m.end()):  # a Windows path is reported once, as a path
                    code_hit(m.start(), m.end())
        esc_spans = [(h.start, h.end, None) for h in hits if h.check == "TEXT-CODE"]
        for m in _TC_CTRL_RE.finditer(text):
            if not (_overlaps(esc_spans, m.start(), m.end()) or _overlaps(urls, m.start(), m.end())
                    or _overlaps(path_spans, m.start(), m.end())):
                code_hit(m.start(), m.end())
        if not in_refs:
            for m in _TC_SNAKE_RE.finditer(text):
                if not _overlaps(urls, m.start(), m.end()):
                    code_hit(m.start(), m.end(), snake=True)
        for line in (lines or []):
            mm = _TC_MD_HEAD_RE.match(line.strip())
            if mm:
                idx = text.find(line.strip()[:20])
                if idx >= 0:
                    code_hit(idx, idx + min(len(line.strip()), 60))
        for m in _REPL_D_RE.finditer(text):
            add("TEXT-REPL", DEFINITE, BLOCK, m.start(), m.end(), "U+%04X" % ord(m.group(0)))
        for m in _REPL_C_RE.finditer(text):
            add("TEXT-REPL", CANDIDATE, WARN, m.start(), m.end(), "U+%04X" % ord(m.group(0)))
        if not in_refs:
            vn = ctx.verbatim_norm()
            for m in _GLUE_LONG_RE.finditer(text):
                w = m.group(0)
                if (w.lower().endswith(_GLUE_SUFFIXES) or _overlaps(urls, m.start(), m.end())
                        or any(m.start() < j < m.end() for j in (joins or ()))  # a line-end hyphen compound
                        or (vn and w in vn)):
                    continue
                add("TEXT-GLUE", CANDIDATE, WARN, m.start(), m.end())
            for rx in (_GLUE_CAMEL_RE, _GLUE_SMALL_RE, _GLUE_REFNUM_RE):
                for m in rx.finditer(text):
                    if _overlaps(urls, m.start(), m.end()):
                        continue
                    if rx is _GLUE_CAMEL_RE and ((vn and m.group(0) in vn)
                                                 or any(m.start() < j < m.end() for j in (joins or ()))):
                        continue  # an identifier typeset as code, or a hyphenated compound
                    add("TEXT-GLUE", CANDIDATE, WARN, m.start(), m.end())
            for m in _NUMFMT_RE.finditer(text):
                add("TEXT-NUMFMT", DEFINITE, INFO, m.start(), m.end())
    for m in _MARKER_D_RE.finditer(text):
        add("TEXT-MARKER", DEFINITE, BLOCK, m.start(), m.end())
    for m in _MARKER_D2_RE.finditer(text):
        add("TEXT-MARKER", DEFINITE, BLOCK, m.start(), m.end())
    for m in _MARKER_C_RE.finditer(text):
        add("TEXT-MARKER", CANDIDATE, WARN, m.start(), m.end())
    # recall candidates for a person (plan only: never queued for an automatic fix, whatever the ruling) —
    # after the rules above, so a definite hit of the same span keeps its own finding
    ref_versions: List[Hit] = []
    if ctx.on("ENG-VER"):
        for m in _RELEASE_VER_RE.finditer(text):
            if not _LIB_NAME_RE.search(text[max(0, m.start() - 150):m.end() + 150]):
                continue
            for v in re.finditer(_VER_NUM, m.group(0)):
                s_, e_ = m.start() + v.start(), m.start() + v.end()
                if _overlaps(ver_spans, s_, e_):
                    continue
                if in_refs:  # a version in a reference title or URL counts only where the body names it too
                    ref_versions.append(Hit("ENG-VER", CANDIDATE, INFO, s_, e_, None,
                                            "a release number in the references: it counts only where the body "
                                            "names the same release", "region", None, True))
                else:
                    add("ENG-VER", CANDIDATE, WARN, s_, e_, note="a release number of a named library: if the "
                        "release is what the study compares, name it by its order (the newest, an older release)",
                        plan_only=True)
    for rx, chk, what in ((_PROC_BATCH_P2_RE, "PROC-REVISION", "a batch called by when it ran"),
                          (_REVISION_PROCESS_RE, "PROC-REVISION", "how the design changed (a registration label "
                                                                  "stays; the story of the change is reworded)"),
                          (_DATE_TITLE_RE, "PROC-TIME", "a run or a registration named by its date or its order")):
        if not ctx.on(chk):
            continue
        for m in rx.finditer(text):
            add(chk, CANDIDATE, WARN, m.start(), m.end(), note="%s: for a person" % what, plan_only=True)
    if in_refs:
        hits = [h for h in hits if h.check not in _REF_REGION_SKIP] + ref_versions
    return hits


# ─── Findings ────────────────────────────────────────────────────────────────

def make_finding(ctx: ScanContext, check: str, severity: str, certainty: str, layer: str, raw_match: str,
                 excerpt: str = "", location: Optional[Dict[str, Any]] = None, region: Optional[str] = None,
                 note: Optional[str] = None, nodemote: bool = False, sub: Optional[str] = None,
                 demoted: Optional[str] = None) -> Dict[str, Any]:
    """One finding. `_key`/`_raw` (unredacted) stay internal: they drive
    grouping and allow-list matching and are stripped from every output."""
    spec = CHECKS[check] if check in CHECKS else CHECKS.get(check.split("-", 1)[-1], CHECKS["LENS-OTHER"])
    red_match = ctx.redactor.redact(raw_match or "")
    red_ex = ctx.redactor.redact(excerpt or "")
    confirm = None
    if certainty == CANDIDATE:
        c = spec.get("confirm")
        confirm = (ctx.hardware if c == "HARDWARE" else ctx.framework if c == "FRAMEWORK" else
                   (ctx.supp_hardware or INFO) if c == "SUPP_HARDWARE" else c)
    loc = {"artifact": None, "page": None, "file": None, "line": None, "member": None}
    loc.update(location or {})
    return {
        "id": None, "group": None, "check": check, "family": spec["family"] if check in CHECKS else "SKIP",
        "severity": severity, "certainty": certainty, "confirm_severity": confirm, "layer": layer,
        "region": region, "subregion": sub, "location": loc, "match": red_match, "excerpt": red_ex,
        "redacted": red_match != (raw_match or "") or red_ex != (excerpt or ""),
        "rule": spec["rule"], "route": spec["route"], "suggestion": spec["fix"], "exempted_by": None,
        "ruling": None, "note": note, "demoted": demoted, "_key": _norm_key(raw_match),
        "_raw": _collapse_ws(raw_match), "_nodemote": nodemote,
    }


def _hits_to_findings(ctx: ScanContext, hits: List[Hit], text: str, layer: str, location: Dict[str, Any],
                      region: Optional[str], sub: Optional[str] = None) -> List[Dict[str, Any]]:
    out = []
    for h in hits:
        raw = h.match if h.match is not None else text[h.start:h.end]
        out.append(make_finding(ctx, h.check, h.severity, h.certainty, layer, raw,
                                _excerpt(text, h.start, h.end), dict(location), region, h.note, sub=sub,
                                demoted=h.demoted))
        _hit_extras(out[-1], h)
    return out


def _hit_extras(f: Dict[str, Any], h: "Hit") -> None:
    """What a finding carries over from its hit: the use of a hardware word, and
    whether it is a recall candidate for a person only."""
    if h.usage:
        f["hw_usage"] = h.usage
    if h.plan_only:
        f["plan_only"] = True


# ─── PDF text layer scan ─────────────────────────────────────────────────────

def scan_pdf_text(pages: List[Dict[str, Any]], ctx: ScanContext, artifact: str) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    for page in pages:
        for seg in page["segs"]:
            hits = detect_text(seg["text"], seg.get("region") or "body", seg.get("sub"), ctx, "pdf", seg["lines"],
                               seg.get("joins"))
            findings += _hits_to_findings(ctx, hits, seg["text"], "pdf", {"artifact": artifact, "page": page["page"]},
                                          seg.get("region"), seg.get("sub"))
            if seg.get("heading") == "end_matter" and seg.get("sub") == "acknowledgments" and ctx.anonymous \
                    and ctx.on("ANON-ACK"):
                findings.append(make_finding(ctx, "ANON-ACK", BLOCK, DEFINITE, "pdf", seg["text"], seg["text"],
                                             {"artifact": artifact, "page": page["page"]}, seg.get("region")))
        if page["invisible"] and ctx.on("TEXT-INVISIBLE"):
            for ch, n in Counter(page["invisible"]).items():
                findings.append(make_finding(ctx, "TEXT-INVISIBLE", BLOCK, DEFINITE, "pdf", "U+%04X" % ord(ch),
                                             "%d occurrence(s) on this page" % n, {"artifact": artifact, "page": page["page"]}))
    if ctx.anonymous and ctx.on("ANON-AUTHOR") and pages:
        first = " ".join(s["text"] for s in pages[0]["segs"])
        if first.strip() and "anonymous" not in first.casefold():
            findings.append(make_finding(ctx, "ANON-AUTHOR", WARN, DEFINITE, "pdf", "page 1 lacks 'Anonymous'",
                                         _collapse_ws(first)[:160], {"artifact": artifact, "page": 1}))
    if ctx.on("TEXT-INJECT"):
        findings += _scan_injection(pages, ctx, artifact)
    # a release number in the references counts where the body names the same release
    body = " ".join(s["text"] for p in pages for s in p["segs"] if (s.get("region") or "body") != "references")
    for f in findings:
        if f["check"] == "ENG-VER" and f.get("plan_only") and f["severity"] == INFO and f.get("region") == "references":
            v = f.get("_raw") or f.get("match") or ""
            if v and re.search(r"(?<![\w.])%s(?![\w]|\.\d)" % re.escape(v), body):
                f["severity"] = WARN
                f["note"] = "a release number in the references that the body names too: for a person"
    return findings


scan_text = scan_pdf_text  # the name used in the design notes


def _scan_injection(pages: List[Dict[str, Any]], ctx: ScanContext, artifact: str) -> List[Dict[str, Any]]:
    try:
        import threat_scan  # type: ignore
    except Exception:  # noqa: BLE001
        return []
    compiled = getattr(threat_scan, "_COMPILED", {}).get("context") or []
    out = []
    for page in pages:
        text = " ".join(s["text"] for s in page["segs"])
        if compiled:
            for rx, pid in compiled:
                m = rx.search(text)
                if m:
                    out.append(make_finding(ctx, "TEXT-INJECT", WARN, CANDIDATE, "pdf", m.group(0)[:120],
                                            _excerpt(text, m.start(), m.end()), {"artifact": artifact, "page": page["page"]},
                                            note="threat_scan pattern %s" % pid))
        else:
            for pid in threat_scan.scan_for_threats(text, "context"):
                if not pid.startswith("invisible_unicode"):
                    out.append(make_finding(ctx, "TEXT-INJECT", WARN, CANDIDATE, "pdf", pid, "",
                                            {"artifact": artifact, "page": page["page"]}))
    return out


def scan_mathglyph(pages: List[Dict[str, Any]], ctx: ScanContext, artifact: str,
                   source_counts: Optional[Dict[str, int]]) -> List[Dict[str, Any]]:
    if not ctx.on("TEXT-MATHGLYPH"):
        return []
    out = []
    # "←↩" / "↪" are listings line-break markers (breaklines), not stray math glyphs
    text = " ".join(s["text"] for p in pages for s in p["segs"]).replace("←↩", " ").replace("↪←", " ")
    for glyph, label in (("ψ", "\\psi"), ("←", "\\leftarrow/\\gets")):
        n_pdf = text.count(glyph)
        if not n_pdf:
            continue
        if source_counts is not None:
            n_src = source_counts.get(glyph, 0)
            if n_pdf > n_src:
                out.append(make_finding(ctx, "TEXT-MATHGLYPH", WARN, CANDIDATE, "pdf", glyph,
                                        "PDF text has %d '%s' but the sources write %s %d time(s)" % (n_pdf, glyph, label, n_src),
                                        {"artifact": artifact}))
        else:
            m = re.search(r"[A-Za-z]%s[A-Za-z]|%s(?=[a-z]{2})" % (glyph, glyph), text)
            if m:
                out.append(make_finding(ctx, "TEXT-MATHGLYPH", WARN, CANDIDATE, "pdf", glyph,
                                        _excerpt(text, m.start(), m.end()), {"artifact": artifact}))
    return out


# Math-font glyphs that stand in for a space when pdfTeX's interword spaces
# meet inline math (cmsy slot 32 is a left arrow, cmmi slot 32 is psi), and
# the visible-space glyph of T1 fonts.
_LAYOUT_GLYPHS = ("←", "ψ", "␣")


def layout_stats(pages: List[Dict[str, Any]], src_counts: Optional[Dict[str, int]],
                 copy_glue_info: Optional[Dict[str, Any]], ctx: ScanContext) -> Dict[str, Any]:
    """What the fix-regression guard compares with round 0: page count, printed
    ??, glued words a second extractor reads, and stray math-font glyphs (with
    the counts the sources explain)."""
    glyphs: Counter = Counter()
    per_page: Dict[str, Dict[str, int]] = {}
    examples: Dict[str, List[Dict[str, Any]]] = {}
    qq = 0
    cite_q = 0
    for p in pages:
        text = " ".join(s["text"] for s in p["segs"]).replace("←↩", " ").replace("↪←", " ")
        qq += len(_QQ_ANY_RE.findall(text))
        cite_q += len(_CITE_Q_RE.findall(text))
        for g in _LAYOUT_GLYPHS:
            n = text.count(g)
            if not n:
                continue
            glyphs[g] += n
            per_page.setdefault(g, {})[str(p["page"])] = n
            ex = examples.setdefault(g, [])
            for m in re.finditer(re.escape(g), text):
                if len(ex) >= 12:
                    break
                ex.append({"page": p["page"], "excerpt": ctx.redactor.redact(_excerpt(text, m.start(), m.end(), 30))})
    return {"pages": len(pages), "qq": qq, "cite_q": cite_q, "glue": (copy_glue_info or {}).get("n"),
            "glyphs": dict(glyphs), "glyph_pages": per_page, "glyph_examples": examples,
            "src_glyphs": ({g: int((src_counts or {}).get(g, 0)) for g in _LAYOUT_GLYPHS}
                           if src_counts is not None else None)}


def regression_findings(base: Dict[str, Any], cur: Dict[str, Any], artifact: str,
                        ctx: ScanContext, against: str = "round 0") -> List[Dict[str, Any]]:
    """FIX-REGRESSION: what a fix round made worse than `against` (the
    previous round, or round 0) — new stray math-font glyphs the sources do
    not explain, a new ?? or (?), more glued words, a body that no longer
    fills the required page or keeps the page limit (BLOCK); a grown page
    count (WARN). Each finding records `regression: {kind, against}`."""
    out: List[Dict[str, Any]] = []
    if not ctx.on("FIX-REGRESSION") or not base or not cur:
        return out

    def add(kind: str, sev: str, match: str, excerpt: str, page: Any = None, note: Optional[str] = None) -> None:
        f = make_finding(ctx, "FIX-REGRESSION", sev, DEFINITE, "pdf", match, excerpt,
                         {"artifact": artifact, "page": page}, note=note)
        f["regression"] = {"kind": kind, "against": against}
        out.append(f)

    bsrc, csrc = base.get("src_glyphs"), cur.get("src_glyphs")
    for g in _LAYOUT_GLYPHS:
        d_pdf = int((cur.get("glyphs") or {}).get(g, 0)) - int((base.get("glyphs") or {}).get(g, 0))
        d_src = (int(csrc.get(g, 0)) - int(bsrc.get(g, 0))) if (bsrc and csrc) else 0
        excess = d_pdf - max(0, d_src)
        if excess <= 0:
            continue
        old = {_norm_quote(e.get("excerpt") or "") for e in (base.get("glyph_examples") or {}).get(g, [])}
        new = [e for e in (cur.get("glyph_examples") or {}).get(g, []) if _norm_quote(e.get("excerpt") or "") not in old]
        ex = new[0] if new else ((cur.get("glyph_examples") or {}).get(g) or [{}])[0]
        rose = [pg for pg, n in sorted((cur.get("glyph_pages") or {}).get(g, {}).items(), key=lambda x: int(x[0]))
                if n > int((base.get("glyph_pages") or {}).get(g, {}).get(pg, 0))]
        add("glyph:%s" % g, BLOCK, "new stray '%s' x%d" % (g, excess),
            "%s (%s: %d, now: %d; the sources explain %+d; pages where it rose: %s)" % (
                ex.get("excerpt") or "", against, int((base.get("glyphs") or {}).get(g, 0)),
                int((cur.get("glyphs") or {}).get(g, 0)), max(0, d_src), ", ".join(rose[:8]) or "?"),
            ex.get("page"), "a space drawn with a math-font glyph: undo the edit on that page; never switch "
                            "interword spaces on globally")
    for key, label in (("qq", "new ?? in the PDF"), ("cite_q", "new (?) citation in the PDF")):
        b_n, c_n = int(base.get(key) or 0), int(cur.get(key) or 0)
        if c_n > b_n:
            add(key, BLOCK, label, "%s: %d, now: %d" % (against, b_n, c_n))
    bg, cg = base.get("glue"), cur.get("glue")
    if isinstance(bg, int) and isinstance(cg, int) and cg > bg:
        add("glue", BLOCK if cg - bg >= COPY_GLUE_MIN else WARN, "more glued words in the text layer",
            "a second extractor reads %d glued word(s), %d at %s" % (cg, bg, against))
    for key, label in (("fill_ok", "the body no longer fills the required page"),
                       ("limit_ok", "the body no longer keeps the page limit")):
        if base.get(key) is True and cur.get(key) is False:
            add(key, BLOCK, label, "body ends on page %s at %s fill (%s: page %s at %s)" % (
                cur.get("body_end_page"), cur.get("fill"), against, base.get("body_end_page"), base.get("fill")),
                cur.get("body_end_page"))
    bp, cp = base.get("pages"), cur.get("pages")
    if isinstance(bp, int) and isinstance(cp, int) and cp > bp:
        # a deletion that moves a float in the appendix can add a page; that is no regression while the
        # body ends where it did and still fills the required page and keeps the limit
        be, ce = base.get("body_end_page"), cur.get("body_end_page")
        body_kept = isinstance(be, int) and isinstance(ce, int) and ce <= be
        fill_bad = base.get("fill_ok") is True and cur.get("fill_ok") is False
        limit_bad = base.get("limit_ok") is True and cur.get("limit_ok") is False
        if body_kept and not fill_bad and not limit_bad:
            add("pages", INFO, "page count grew", "%d pages at %s, %d now; the body still ends on page %s, so only "
                "pages after it grew (a float placed later): no undo" % (bp, against, cp, ce), ce,
                "the page limit and the required fill still hold")
        else:
            add("pages", WARN, "page count grew", "%d pages at %s, %d now%s" % (
                bp, against, cp, ("; the body now ends on page %s (was %s)" % (ce, be)) if body_kept is False
                and isinstance(ce, int) and isinstance(be, int) else ""), ce if isinstance(ce, int) else None)
    return out


_WORD_TOKEN_RE = re.compile(r"[A-Za-z]+")
COPY_GLUE_MIN = 5


def copy_glue(pdf_path: str, pages: List[Dict[str, Any]], primary: Optional[str]) -> Dict[str, Any]:
    """Words that a second, layout-blind extractor (pypdf) reads glued together
    where the geometry-aware primary backend sees separate words: the text layer
    has no space glyph there, typically next to inline math ('Letxbe'). Many
    readers and venue text extraction copy them glued. {} when pypdf is not
    installed or is already the primary backend."""
    if primary == "pypdf":
        return {}
    pypdf = _load_pypdf()
    if pypdf is None:
        return {}
    try:
        alt = [(pg.extract_text() or "") for pg in pypdf.PdfReader(pdf_path).pages]
    except Exception:  # noqa: BLE001 — an optional cross-check never breaks the scan
        return {}
    n, examples, where = 0, [], []
    for p in pages:
        if p["page"] > len(alt):
            continue
        words = _WORD_TOKEN_RE.findall(" ".join(s["text"] for s in p["segs"]
                                                if s["kind"] == "body" and s.get("region") != "references"))
        known = set(words)
        joined = {}
        for i in range(len(words) - 1):
            joined.setdefault(words[i] + words[i + 1], 1)
            if i + 2 < len(words):
                joined.setdefault(words[i] + words[i + 1] + words[i + 2], 1)
        glued = sorted(t for t in set(_WORD_TOKEN_RE.findall(alt[p["page"] - 1]))
                       if len(t) >= 4 and t not in known and t in joined)
        if glued:
            n += len(glued)
            where.append(p["page"])
            examples += glued[:max(0, 5 - len(examples))]
    return {"n": n, "examples": examples, "pages": where}


# ─── Page geometry and end matter ────────────────────────────────────────────

def page_geometry(pages: List[Dict[str, Any]], events: List[Dict[str, Any]],
                  markers: Optional[Sequence[str]] = None, start_page: int = 3) -> Dict[str, Any]:
    """Where the main body ends and how full that page is (needs block bboxes).
    Body end = the last content before the first not-counted heading on page
    >= start_page; fill = (content bottom - body top) / (body bottom - body top)."""
    marks = [m.casefold() for m in (markers or DEFAULT_BODY_END)]
    if not pages or not any(s.get("bbox") for p in pages for s in p["segs"]):
        return {"status": "no_bbox"}
    end_ev = None
    for ev in events:
        if ev["page"] < start_page:
            continue
        core = ev["text"].casefold()
        if ev["kind"] in ("references", "appendix", "end_matter", "checklist") and (
                core in marks or any(core.startswith(m) for m in marks if len(m) > 8)
                or (ev["kind"] == "appendix" and any(m in ("appendix", "appendices", "附录") for m in marks))):
            end_ev = ev
            break
    def content_boxes(p: Dict[str, Any]) -> List[List[float]]:
        boxes = [s["bbox"] for s in p["segs"] if s.get("bbox") and s["kind"] == "body"]
        return boxes + [b for b in p.get("images", []) if b]
    tops, bottoms, lhs = [], [], []
    limit_page = end_ev["page"] if end_ev else len(pages)
    for p in pages[:max(1, min(8, limit_page))]:
        boxes = content_boxes(p)
        if boxes:
            tops.append(min(b[1] for b in boxes))
            bottoms.append(max(b[3] for b in boxes))
        for s in p["segs"]:
            if s.get("bbox") and s["kind"] == "body" and len(s["lines"]) >= 2:
                lhs.append((s["bbox"][3] - s["bbox"][1]) / len(s["lines"]))
    if not tops:
        return {"status": "no_bbox"}
    top, bottom = statistics.median(tops), max(bottoms)
    line_h = statistics.median(lhs) if lhs else 12.0
    if end_ev is None:
        return {"status": "no_heading", "body_top": round(top, 1), "body_bottom": round(bottom, 1)}
    hp = pages[end_ev["page"] - 1]
    ebox = end_ev.get("bbox")
    before = []
    for s in hp["segs"]:
        if s.get("heading") and s.get("bbox") == ebox and _collapse_ws(s["text"]).endswith(end_ev["text"][-10:]):
            break
        if s.get("bbox") and s["kind"] == "body":
            before.append(s["bbox"])
    before += [b for b in hp.get("images", []) if ebox and b[3] <= ebox[1] + 1]
    if before:
        end_page, last_bottom = end_ev["page"], max(b[3] for b in before)
    else:
        end_page = end_ev["page"] - 1
        prev = content_boxes(pages[end_page - 1]) if end_page >= 1 else []
        last_bottom = max((b[3] for b in prev), default=top)
    span = max(bottom - top, 1.0)
    fill = max(0.0, min(1.0, (last_bottom - top) / span))
    return {"status": "ok", "body_end_page": end_page, "fill": round(fill, 3),
            "lines_short": int(round((1 - fill) * span / max(line_h, 1.0))),
            "end_heading": end_ev["text"], "end_heading_page": end_ev["page"],
            "body_top": round(top, 1), "body_bottom": round(bottom, 1), "line_height": round(line_h, 2)}


def parse_end_matter(spec: Any) -> List[List[str]]:
    if not spec:
        return []
    slots = spec if isinstance(spec, list) else str(spec).split(";")
    out = []
    for s in slots:
        alts = s if isinstance(s, list) else str(s).split("|")
        alts = [_collapse_ws(str(a)) for a in alts if _collapse_ws(str(a))]
        if alts:
            out.append(alts)
    return out


def check_end_matter(pages: List[Dict[str, Any]], slots: List[List[str]], ctx: ScanContext,
                     artifact: str) -> List[Dict[str, Any]]:
    if not slots:
        return []
    heads: List[Tuple[int, int, str, str]] = []
    order = 0
    for p in pages:
        for s in p["segs"]:
            order += 1
            if s["kind"] == "body" and len(s["text"]) <= 60:
                core, _ = _heading_core(s["text"])
                heads.append((order, p["page"], core.casefold(), s.get("heading") or ""))
    refs_pos = next((o for o, _, _, h in heads if h == "references"), None)
    out, found = [], []
    for slot in slots:
        alts = [a.casefold() for a in slot]
        hit = next(((o, pg) for o, pg, core, _ in heads if core in alts), None)
        if hit is None:
            if ctx.on("ENDM-MISSING"):
                out.append(make_finding(ctx, "ENDM-MISSING", BLOCK, DEFINITE, "pdf", slot[0], " | ".join(slot),
                                        {"artifact": artifact}))
            continue
        found.append((hit[0], hit[1], slot[0]))
    if ctx.on("ENDM-ORDER"):
        for (o1, _, a), (o2, pg2, b) in zip(found, found[1:]):
            if o2 < o1:
                out.append(make_finding(ctx, "ENDM-ORDER", BLOCK, DEFINITE, "pdf", "%s before %s" % (b, a),
                                        "", {"artifact": artifact, "page": pg2}))
        if refs_pos is not None:
            for o, pg, name in found:
                if o > refs_pos:
                    out.append(make_finding(ctx, "ENDM-ORDER", BLOCK, DEFINITE, "pdf", "%s after References" % name,
                                            "", {"artifact": artifact, "page": pg}))
    return out


# ─── PDF metadata and byte layer ─────────────────────────────────────────────

_TZ_OFFSET_RE = re.compile(r"D:\d{4,14}([+-])(\d{2})'?(\d{2})?")
_XMP_FIELD_RE = re.compile(r"<(dc:creator|dc:title|dc:rights|xmp:CreatorTool|pdf:Producer|pdf:Author|"
                           r"xmp:CreateDate|xmp:ModifyDate|xmp:MetadataDate)\b[^>]*>(.*?)</\1>", re.S)


def _tz_nonutc(date: str) -> bool:
    m = _TZ_OFFSET_RE.search(date or "")
    return bool(m and (m.group(2) != "00" or (m.group(3) or "00") != "00"))


def scan_metadata(doc: PdfDoc, ctx: ScanContext, artifact: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """META-INFO, META-TZ, META-PTEX, META-XMP, META-EMBED (pure stdlib)."""
    out: List[Dict[str, Any]] = []
    loc = {"artifact": artifact}
    empty_policy = ctx.policy.get("metadata_policy") == "empty"
    info = pdf_info(doc)

    def ident(s: str) -> bool:
        return ctx.anonymous and bool(ctx.identity.finditer(s) or ctx.auto.finditer(s))

    for key, val in info.items():
        if key in ("CreationDate", "ModDate", "Trapped") or not val.strip():
            continue
        if key.startswith("PTEX."):
            sev = BLOCK if (_PATH_RE.search(val) or ident(val)) else (WARN if empty_policy else INFO)
            if ctx.on("META-PTEX"):
                out.append(make_finding(ctx, "META-PTEX", sev, DEFINITE, "pdf-meta", "%s=%s" % (key, val),
                                        "Info /%s" % key, dict(loc)))
            continue
        if ident(val):
            sev = BLOCK
        elif key == "Author":
            sev = BLOCK if ctx.anonymous else INFO
        elif key in ("Title", "Subject", "Keywords"):
            sev = WARN if (ctx.anonymous or empty_policy) else INFO
        else:
            sev = WARN if empty_policy else INFO
        if ctx.on("META-INFO"):
            out.append(make_finding(ctx, "META-INFO", sev, DEFINITE, "pdf-meta", "%s=%s" % (key, val[:200]),
                                    "Info /%s" % key, dict(loc)))
    tz_sev = WARN if ctx.anonymous else INFO
    for key in ("CreationDate", "ModDate"):
        if _tz_nonutc(info.get(key, "")) and ctx.on("META-TZ"):
            out.append(make_finding(ctx, "META-TZ", tz_sev, DEFINITE, "pdf-meta", "%s=%s" % (key, info[key]),
                                    "Info /%s" % key, dict(loc)))
    embedded_info_nums: Set[int] = set()
    for o in doc.objs.values():
        v = o.value
        if not isinstance(v, dict):
            continue
        fn = doc.resolve(v.get("PTEX.FileName"))
        if isinstance(fn, _PdfString) and ctx.on("META-PTEX"):
            name = fn.text()
            # a plain relative figure name ("./figures/plot.pdf") identifies nobody
            sev = BLOCK if (_PATH_RE.search(name) or ident(name)) else (WARN if empty_policy else INFO)
            out.append(make_finding(ctx, "META-PTEX", sev, DEFINITE, "pdf-meta", "PTEX.FileName=%s" % name,
                                    "embedded figure (object %d)" % o.num, dict(loc)))
        idict = v.get("PTEX.InfoDict")
        if isinstance(idict, _Ref):
            embedded_info_nums.add(idict[0])
    for num in sorted(embedded_info_nums):
        d = doc.resolve(_Ref(num, 0))
        if not isinstance(d, dict):
            continue
        for key, raw in d.items():
            val = doc.resolve(raw)
            if not isinstance(val, _PdfString):
                continue
            s = val.text()
            if key in ("CreationDate", "ModDate"):
                if _tz_nonutc(s) and ctx.on("META-TZ"):
                    out.append(make_finding(ctx, "META-TZ", tz_sev, DEFINITE, "pdf-meta", "embedded %s=%s" % (key, s),
                                            "PTEX.InfoDict (object %d)" % num, dict(loc)))
                continue
            if ctx.on("META-PTEX") and s.strip():
                # an embedded figure's tool and version strings are environment detail
                # in an anonymous submission; one preamble line drops them all
                sev = BLOCK if (ident(s) or _PATH_RE.search(s)) else (WARN if (empty_policy or ctx.anonymous) else INFO)
                out.append(make_finding(ctx, "META-PTEX", sev, DEFINITE, "pdf-meta", "embedded %s=%s" % (key, s[:200]),
                                        "PTEX.InfoDict (object %d)" % num, dict(loc)))
    # XMP that a figure brought along (a Form XObject's /Metadata survives
    # \pdfsuppressptexinfo): its tool versions are environment detail
    fig_meta: Set[int] = set()
    n_type3 = 0
    for o in doc.objs.values():
        v = o.value
        if not isinstance(v, dict):
            continue
        if v.get("Subtype") == "Form" and isinstance(v.get("Metadata"), _Ref):
            fig_meta.add(v["Metadata"][0])
        if v.get("Type") == "Font" and v.get("Subtype") == "Type3":
            n_type3 += 1
    xmp_fields: List[Tuple[str, str, bool]] = []
    for o in doc.objs.values():
        v = o.value
        if isinstance(v, dict) and v.get("Type") == "Metadata" and o.stream is not None:
            data = doc.stream_data(o.num)
            if data is None and not v.get("Filter"):
                data = o.stream
            text = (data or b"").decode("utf-8", errors="replace")
            if "xmpmeta" not in text and "rdf:RDF" not in text:
                continue
            for m in _XMP_FIELD_RE.finditer(text):
                inner = _collapse_ws(re.sub(r"<[^>]+>", " ", m.group(2)))
                if inner:
                    xmp_fields.append((m.group(1), inner, o.num in fig_meta))
    for field, val, is_fig in xmp_fields:
        if field in ("xmp:CreateDate", "xmp:ModifyDate", "xmp:MetadataDate"):
            if re.search(r"[+-](?!00:?00)\d{2}:?\d{2}$", val) and ctx.on("META-TZ"):
                out.append(make_finding(ctx, "META-TZ", tz_sev, DEFINITE, "pdf-meta", "XMP %s=%s" % (field, val), "",
                                        dict(loc)))
            continue
        if (is_fig and not ident(val) and field in ("xmp:CreatorTool", "pdf:Producer", "dc:creator", "pdf:Author")
                and (_TOOL_VERSION_RE.search(val) or field in ("dc:creator", "pdf:Author")) and ctx.on("META-FIGURE")):
            out.append(make_finding(ctx, "META-FIGURE", WARN if ctx.anonymous else INFO, DEFINITE, "pdf-meta",
                                    "figure XMP %s=%s" % (field, val[:200]), "XMP of an embedded figure", dict(loc)))
            continue
        sev = BLOCK if ident(val) else (WARN if empty_policy else INFO)
        if ctx.on("META-XMP"):
            out.append(make_finding(ctx, "META-XMP", sev, DEFINITE, "pdf-meta", "XMP %s=%s" % (field, val[:200]), "",
                                    dict(loc)))
    if n_type3 and ctx.on("TEXT-T3FONT"):
        out.append(make_finding(ctx, "TEXT-T3FONT", INFO, DEFINITE, "pdf-meta", "%d Type 3 font(s)" % n_type3,
                                "Type 3 fonts, usually from plotted figures", dict(loc)))
    if ctx.on("META-EMBED"):
        for o in doc.objs.values():
            v = o.value
            if isinstance(v, dict) and ("EmbeddedFiles" in v or v.get("Type") == "EmbeddedFile"):
                out.append(make_finding(ctx, "META-EMBED", WARN, DEFINITE, "pdf-meta", "embedded file attachment",
                                        "object %d" % o.num, dict(loc)))
                break
    return out, info


def scan_pdf_bytes(doc: PdfDoc, ctx: ScanContext, artifact: str) -> List[Dict[str, Any]]:
    """META-BYTES: strings in every object dictionary plus non-content,
    non-font, non-image stream payloads (XMP, attachments, ...)."""
    if not ctx.on("META-BYTES"):
        return []
    texts: List[Tuple[str, str]] = []
    for o in doc.objs.values():
        for path, s in _walk_strings(o.value):
            if path.endswith(("/PTEX.FileName",)):
                continue
            texts.append(("object %d %s" % (o.num, path), s))
    skip = _skip_stream_nums(doc)
    for o in doc.objs.values():
        if o.stream is None or o.num in skip:
            continue
        data = doc.stream_data(o.num)
        if data is None and isinstance(o.value, dict) and not o.value.get("Filter"):
            data = o.stream
        if data:
            texts.append(("stream %d" % o.num, data.decode("latin-1")))
    texts.append(("uncompressed bytes", doc.outside_text))
    out: List[Dict[str, Any]] = []
    seen: Set[Tuple[str, str]] = set()

    def add(raw: str, where: str) -> None:
        key = _norm_key(raw)
        if (key, where.split(" ")[0]) in seen:
            return
        seen.add((key, where.split(" ")[0]))
        out.append(make_finding(ctx, "META-BYTES", BLOCK, DEFINITE, "pdf-bytes", raw, where, {"artifact": artifact}))

    for where, s in texts:
        for m in _PATH_RE.finditer(s):
            if not _PATH_PLACEHOLDER_RE.match(m.group(0)):
                add(m.group(0)[:200], where)
        if ctx.anonymous:
            for matcher in (ctx.identity, ctx.auto):
                for a, b, _ in matcher.finditer(s):
                    add(s[a:b], where)
            for m in _EMAIL_RE.finditer(s):
                if not _EMAIL_PLACEHOLDER_RE.search(m.group(0)):
                    add(m.group(0), where)
    return out


_TJ_ARRAY_RE = re.compile(rb"\[((?:[^\]\\]|\\.)*)\]\s*TJ", re.S)
_TJ_NUM_RE = re.compile(rb"(?<![\w.])-\d+(?:\.\d+)?")
_PDF_STR_RE = re.compile(rb"\((?:[^()\\]|\\.)*\)", re.S)


def nospace_stats(doc: PdfDoc) -> Dict[str, Any]:
    """Real space characters vs. large negative TJ kerns in page content."""
    spaces = kerns = 0
    for num in sorted(_content_stream_nums(doc)):
        data = doc.stream_data(num)
        if data is None:
            o = doc.objs.get(num)
            if o is None or (isinstance(o.value, dict) and o.value.get("Filter")):
                continue
            data = o.stream or b""
        for m in _TJ_ARRAY_RE.finditer(data):
            body = _PDF_STR_RE.sub(b" ", m.group(1))
            kerns += sum(1 for k in _TJ_NUM_RE.findall(body) if float(k) <= -200)
        for s in _PDF_STR_RE.findall(data):
            spaces += s.count(b" ") + s.count(b"\\040")
    ratio = spaces / (spaces + kerns) if (spaces + kerns) else 1.0
    return {"spaces": spaces, "kerns": kerns, "ratio": round(ratio, 4)}


# ─── Supplementary archive ───────────────────────────────────────────────────

_JUNK_BLOCK_RE = re.compile(r"(?:^|/)(?:\.git|__MACOSX|\.svn|\.hg)(?:/|$)|(?:^|/)\.env(?:\.[\w-]+)?$")
_JUNK_WARN_RE = re.compile(r"(?:^|/)(?:\.DS_Store|Thumbs\.db|desktop\.ini)$|(?:^|/)(?:__pycache__|\.ipynb_checkpoints|"
                           r"\.idea|\.vscode|\.pytest_cache|\.mypy_cache)(?:/|$)|\.pyc$|\.swp$|~$")
# run logs and runtime artifacts: reproduction rarely needs them and their
# lines carry wall-clock stamps (WARN candidates the reviewer rules on)
_RUNLOG_RE = re.compile(r"(?:^|/)(?:nohup\.out|slurm-[\w.-]*\.(?:out|err)|[^/]+\.log(?:\.\d+)?|events\.out\.tfevents\.[^/]+)$"
                        r"|(?:^|/)(?:wandb|mlruns|lightning_logs|\.hydra)(?:/|$)", re.I)
# a line that starts with a wall-clock stamp: ISO date and time (bracketed or
# not), a ctime stamp ("Mon Mar  5 09:11:42"), or a glog prefix ("I0305 09:11:42")
_LOG_TS_LINE_RE = re.compile(r"^[ \t]*[\[(]?(?:20\d\d-[01]\d-[0-3]\d[T ][0-2]\d:[0-5]\d|(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun) "
                             r"[A-Z][a-z]{2} [ \d]\d [0-2]\d:[0-5]\d:[0-5]\d|[IWEF][01]\d[0-3]\d [0-2]\d:[0-5]\d:[0-5]\d)",
                             re.M | _A)
# a timestamp inside an identifier or a value (run-20990101T101500Z, ckpt_20990101T1015)
_TS_ID_RE = re.compile(r"(?<![0-9])20\d\d[01]\d[0-3]\dT[0-2]\d[0-5]\d(?:[0-5]\d)?Z?(?![0-9])", _A)
# a provenance key that holds a calendar date in a record or a code literal
# (a date with a time is a run timestamp, reported by _TS_KEY_RE)
_DATE_STAMP_RE = re.compile(r"(?<![\w-])[\"']?(?:date|created|written|built|generated|ran|run_date|registered|frozen|sealed)"
                            r"(?:_?(?:at|on|date|utc|local))?[\"']?\s*[:=]\s*[\"']20\d\d-[01]\d-[0-3]\d(?![T ][0-2]?\d:)",
                            re.I | _A)
# the authors' own process verbs: a date next to one is the timeline, not a data parameter
_PROC_VERB_RE = re.compile(r"\b(?:registered|written|wrote|added|amended|addend(?:um|a)|relaunch(?:ed)?|re-?ran|launched|"
                           r"frozen|sealed|submitted|revised|corrected|superseded|fixed)\b", re.I | _A)
# ARIS and agent working files: exact report and state names, never a broad
# "*_AUDIT.*" pattern (a data file such as LABEL_AUDIT.json is not one of them)
_ARIS_FILES = ("PAPER_CLAIM_AUDIT", "CITATION_AUDIT", "PAPER_HYGIENE_AUDIT", "EXPERIMENT_AUDIT", "PROOF_AUDIT",
               "PROOF_ORCHESTRATOR_AUDIT", "KILL_ARGUMENT", "REVIEW_STATE", "PAPER_PLAN", "NARRATIVE_REPORT",
               "EXPERIMENT_LOG", "EXPERIMENT_TRACKER", "PAPER_IMPROVEMENT_LOG", "IDEA_REPORT",
               "REVIEWER_MEMORY", "FIX_LOG", "FIX_PLAN", "PAPER_ACCEPTANCE_CONTRACT", "CLAIMS_FROM_RESULTS",
               "KNOWN_WEAKNESSES", "GATE_REPORT", "REFINE_STATE")
_ARIS_RE = re.compile(r"(?:^|/)(?:\.aris|\.claude|\.codex|\.agents)(?:/|$)|(?:^|/)(?:CLAUDE|AGENTS)\.md$"
                      r"|(?:^|/)(?:" + "|".join(_ARIS_FILES) + r")\.(?:md|json|html)$|(?:^|/)AUTO_REVIEW[\w.-]*\.md$"
                      r"|(?:^|/)traces/[^/]+/\d{4}-\d{2}-\d{2}_run\d{2}(?:/|$)|(?:^|/)run\.meta\.json$")
# date / round / version / fix markers in member names (each path component)
_NAME_MARKERS = (
    ("date", re.compile(r"(?<!\d)20\d\d[01]\d[0-3]\d(?:[_-]?\d{4,6})?(?!\d)|(?<!\d)20\d\d-[01]\d-[0-3]\d(?!\d)"
                        r"|(?<=[_-])0[1-9](?:0[1-9]|[12]\d|3[01])(?=[._-]|$)")),  # zero-padded MMDD: _0915
    # _r2, and a one-digit round tag with a short suffix or at the start: r3b_rows, x_r4cpu, r2_tables
    ("round", re.compile(r"(?<=_)r\d+(?=[._-]|$)|(?:^|(?<=[_-]))r\d[a-z]{0,8}(?=[._-]|$)|phase[-_]?\d|round[-_]?\d",
                         re.I)),
    # v2_x.py, x_v3.py; a lone _v1 and two-digit model versions (_v03 = v0.3, _v15 = v1.5) are not iteration marks
    ("version", re.compile(r"(?:^|(?<=[_-]))v(?:[2-9]|[1-9]\d)(?=[._-]|$)", re.I)),
    ("fix", re.compile(r"(?:bug|hot|quick)[-_]?fix(?:ed|es)?|_(?:fix(?:ed)?|backup|bak)(?=(?:\.[A-Za-z0-9]+)+$|$)",
                       re.I)),
)
# members that read as process records (SUPP-PROCFILE): strong markers in any
# member name, weak ones only for documents and logs (a notes.py or review.py
# module is code); and process-like document titles. Addenda, amendment drafts,
# and clarifications are registration records: policy registration_labels
# decides (keep: INFO, flag: candidates).
_PROCFILE_STRONG_RE = re.compile(
    r"(?:^|(?<=[_.\-/]))(wip|root-?cause|post-?mortem|as-?found|superseded)(?=[_.\-/]|$)", re.I)
_PROCFILE_REG_RE = re.compile(r"(?:^|(?<=[_.\-/]))(addend(?:um|a)|amendments?[_-]draft|clarifications?)(?=[_.\-/]|$)",
                              re.I)
# working-copy endings in member names (x_now.py, figs_prev/): SUPP-NAME candidates
# ("_temp" is left out: sweep_temp.py is as often a temperature as a scratch copy)
_COPY_MARKER_RE = re.compile(r"(?<=[_-])(now|prev|previous|old|new|tmp)(?=\.[A-Za-z0-9]+$|$)", re.I)
# environment-variable prefixes of a command (a machine's devices or threads)
_ENV_PREFIX_RE = re.compile(r"\b(?:(?:CUDA|HIP|ROCR)_VISIBLE_DEVICES|(?:OMP|MKL|OPENBLAS|NUMEXPR|VECLIB_MAXIMUM)"
                            r"_NUM_THREADS|NCCL_[A-Z_]{3,}|MASTER_(?:ADDR|PORT)|PYTORCH_CUDA_ALLOC_CONF)\s*=\s*[^\s;&|]*",
                            _A)
# a short hash after commit/sha/hash (7-12 hex digits, maybe cut with "...")
_SHORT_HASH_RE = re.compile(r"\b(?:commit|sha(?:-?(?:1|256))?|hash|digest|md5|checksum|rev(?:ision)?)\b"
                            r"[\s:=#(\"'`]{0,4}([0-9a-fA-F]{7,12})(?:\.\.\.|…)?(?![0-9A-Za-z])", re.I | _A)
# relative paths in code literals ('../run_v1/cfg.json'), resolved against the package
_REL_LITERAL_RE = re.compile(r"""(["'])(\.{1,2}/[^"'\s{}*?<>$%]{1,200})\1""")
# a project name in a placeholder path (/path/to/<name>)
_CODENAME_PATH_RE = re.compile(r"/path/to/([A-Za-z][A-Za-z0-9_-]{2,30})(?![A-Za-z0-9_-])")
# "old" and "draft" only as the end of a file stem (x_old.py, PLAN_DRAFT.md): a "draft model" or an "old
# policy" is science, not a working copy; "draft" only for documents
_PROCFILE_SUFFIX_RE = re.compile(r"(?:^|[_.-])(old|draft)$", re.I)
_PROCFILE_WEAK_RE = re.compile(r"(?:^|(?<=[_.\-/]))(notes?|todo|status|stop|review|round\d*|progress|hand-?off|"
                               r"hand-?over|worklog|scratch)(?=[_.\-/]|$)", re.I)
_PROCFILE_TITLE_RE = re.compile(
    r"^\s*#*\s*(?:[\w-]+\s+)?(?:hand-?off|progress\s+(?:log|notes|report)|status\s+(?:report|update|notes)|work\s*log|"
    r"working\s+notes|lab\s+notes|to-?do(?:\s+list)?|review\s+(?:round|notes|log)|round\s+\d+\s+(?:notes|summary|review)|"
    r"draft|post-?mortem|root[- ]cause)\b", re.I)
# hardware, OS, and host words (SUPP-HW): notes and names, never code lines
_SUPP_HW_RE = re.compile(
    r"\b(?:CPU|GPU|TPU|NPU)s?\b"
    r"|\b(?:Ubuntu|CentOS|Debian|Fedora|RHEL|Red\s+Hat|macOS|Mac\s+OS\s+X|Windows\s+(?:\d{1,2}|Server|XP)|WSL2?)\b"
    r"|\bhostnames?\b|\b(?:on|across|between|from)\s+(?:(?:the|our|both|two|three|four|several|\d+)\s+){0,2}"
    r"(?:hosts|servers|workstations|laptops?)\b", _A)
_SUPP_HW_NAME_RE = re.compile(r"(?:^|(?<=[_.\-/]))(cpu|gpu|tpu|a100|h100|h800|a800|v100|a6000|ubuntu|centos|macos|wsl)"
                              r"(?=[_.\-/\d]|$)", re.I)
# placeholder roots (SUPP-PATH): <DATA_ROOT>/x, ${ROOT}/x
# (an identifier in angle brackets, not prompt text such as "<your answer>/" or an HTML tag)
_PLACEHOLDER_ROOT_RE = re.compile(r"(?<![\w$<])(<[A-Za-z][A-Za-z0-9_]{0,40}>|\$\{[A-Za-z_][A-Za-z0-9_]*\})/"
                                  r"(?=[\w.~-])")  # '/' only: "<tag>\n" in an escaped JSON string is no path
_HTML_TAGS = frozenset(("<a>", "<b>", "<i>", "<p>", "<s>", "<u>", "<br>", "<hr>", "<em>", "<li>", "<ol>", "<ul>",
                        "<td>", "<th>", "<tr>", "<div>", "<span>", "<sub>", "<sup>", "<pre>", "<code>", "<img>",
                        "<strong>", "<table>", "<html>", "<body>", "<head>"))
_SHELLISH_RE = re.compile(r"\.(?:sh|bash|zsh|mk|ya?ml|toml|cfg|ini|env|conf)$|(?:^|/)(?:Makefile|Dockerfile)$", re.I)
# references to scripts and data paths, resolved against the package (SUPP-PATH)
_SCRIPT_REF_RE = re.compile(r"(?<![\w/.:@~$-])((?:[\w.-]+/)*[\w-]*[A-Za-z][\w.-]*\.(?:py|sh|ipynb|R|jl|bash|pl))(?![\w/])")
_DATA_REF_RE = re.compile(r"(?<![\w/.:@~$<-])((?:[A-Za-z_][\w.-]*/)+[\w.-]+\.(?:json|jsonl|csv|tsv|npz|npy|pt|pkl|"
                          r"parquet|ya?ml|txt|tex))(?![\w/])")
_COMMON_SCRIPTS = frozenset(("setup.py", "conftest.py", "manage.py", "__init__.py", "__main__.py"))
_EXTERNAL_DIRS = frozenset(("vendor", "third_party", "thirdparty", "external", "extern", "deps", "site-packages",
                            "node_modules"))
_CMD_BEFORE_RE = re.compile(r"(?:\bpython3?(?:\s+-[BuOW]\w*)*|\bbash|\bsh|\bsource|\bUsage:|\busage:)\s+$")
# a line that says the file belongs to another package, and the documents that list dependencies
_EXTERNAL_NOTE_RE = re.compile(r"not\s+(?:included|shipped|part\s+of)|third[- ]party|upstream|vendor|pip\s+install|"
                               r"site-packages|installed\s+package", re.I)
_DEPENDENCY_DOC_RE = re.compile(r"^(?:DEPENDENC|VENDOR|THIRD|LICEN[CS]E|NOTICE|REQUIREMENTS)", re.I)
# a member that patches or wraps another package talks about that package's files
_VENDOR_PATH_RE = re.compile(r"(?:^|/)[^/]*(?:vendor|third[_-]?party|shim)[^/]*/", re.I)
# unfinished status strings in code and records (RESULTS_PENDING, X_WIP)
_STATUS_STR_RE = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*_(?:PENDING|UNREVIEWED|NOT_REVIEWED|WIP|DRAFT)\b"
                            r"|\bPENDING_[A-Z][A-Z0-9_]*\b", _A)
# run time written into outputs (SUPP-RUNTIME)
_RUNTIME_CALL_RE = re.compile(r"\b(?:datetime\.(?:datetime\.)?(?:now|utcnow|today)|date\.today|time\.(?:strftime|ctime|"
                              r"asctime|localtime|gmtime)|pd\.Timestamp\.now)\s*\(|\$\(\s*date\b|`date\b", _A)
_RUNTIME_KEY_RE = re.compile(r"[\"'](?:date|time|timestamp|datetime|created(?:_at|_on)?|generated(?:_at|_on)?|run_?at|"
                             r"ran_at|run_?date|written(?:_at|_on)?|started(?:_at)?|finished(?:_at)?|completed(?:_at)?|"
                             r"built(?:_at)?|when)[\"']\s*(?::|\]\s*=)", re.I)
_RUNTIME_NAME_RE = re.compile(r"\.(?:json|jsonl|csv|tsv|log|txt|png|pdf|pt|pkl|npz|out)\b|\b(?:path|file|fname|"
                              r"filename|out_?dir|outdir|log_?dir|run_?dir)\b", re.I)
_ASSIGN_RE = re.compile(r"^\s*([A-Za-z_]\w*)\s*=")
# a project or code name: a document title "X — ..." / "X: ...", a name in code
_CODENAME_TITLE_RE = re.compile(r"^\s*#\s+([A-Za-z][A-Za-z0-9_-]{2,30})\s*(?:—|–|--|-|:)\s+\S", re.M)
_CODENAME_CODE_RE = re.compile(r"\b(?:paper|project|codename|project_name)\s*=\s*[\"']([A-Za-z][A-Za-z0-9_-]{2,30})", _A)
_GENERIC_NAMES = frozenset(("supplement", "supplementary", "supplementary_material", "code", "src", "data", "release",
                            "artifact", "artifacts", "package", "paper", "repo", "project", "materials", "readme",
                            "experiments", "scripts", "results", "analysis", "appendix", "usage", "overview",
                            "introduction", "setup", "install", "installation", "requirements", "notes", "license",
                            "data_and_code", "reproduction", "reproducibility", "contents", "summary", "method",
                            "methods", "evaluation", "registration", "tests", "test", "examples", "docs", "main"))
_GENERIC_PARTS = frozenset(("anonymous", "anon", "supp", "suppl", "supplement", "supplementary", "material",
                            "materials", "code", "data", "files", "final", "submission", "camera", "ready", "upload",
                            "v1", "public", "release", "artifact", "artifacts", "and"))
# common folder and package names: never a project's code name
_VENDORED_DIR_RE = re.compile(r"(?:^|/)(?:third[_-]?party|3rd[_-]?party|vendor(?:ed)?|external|extern|deps|"
                               r"site-packages|node_modules)(?:/|$)", re.I)
_GENERIC_PACKAGES = frozenset((
    "agent", "agents", "model", "models", "bench", "benchmark", "benchmarks", "utils", "util", "lib", "libs", "core",
    "common", "tools", "tool", "helpers", "eval", "evals", "evaluation", "configs", "config", "notebooks",
    "figures", "figs", "plots", "plotting", "outputs", "output", "logs", "tests", "baselines", "baseline",
    "methods", "train", "training", "inference", "prompts", "prompt", "tasks", "task", "envs", "environments",
    "games", "game", "datasets", "dataset", "metrics", "preprocessing", "pipeline", "pipelines", "runner", "server",
    "client", "api", "app", "web", "demo", "examples", "assets", "resources", "misc", "legacy", "archive", "cache",
    "checkpoints", "weights", "modules", "layers", "ops", "kernels", "records", "tables", "stats", "statistics",
    "shared", "scripts", "experiment", "analyses", "reproduce", "reproduction", "package", "pkg", "source", "sources",
    "vendor", "external", "third_party", "thirdparty"))
_NAME_HOME_RE = re.compile(r"^(?:home|Users)/[^/]+/|^(?:mnt|scratch|nfs|gpfs|lustre)/", re.I)
_NAME_SEPARATORS = str.maketrans({c: " " for c in "_./\\-"})
_TEXT_EXTS = (".md", ".txt", ".py", ".sh", ".json", ".jsonl", ".csv", ".tsv", ".yaml", ".yml", ".ipynb", ".tex",
              ".cfg", ".toml", ".ini", ".r", ".m", ".jl", ".c", ".cc", ".cpp", ".h", ".hpp", ".java", ".js", ".ts",
              ".rst", ".html", ".xml", ".bib", ".log", ".bash", ".zsh", ".ps1", ".bat", ".sql", ".rs", ".go", ".lua",
              ".pl", ".scala", ".kt", ".swift", ".cu", ".cuh", ".env", ".conf", ".properties", ".gitignore",
              ".ndjson", ".diff", ".patch")
_DATA_EXTS = (".json", ".jsonl", ".ndjson", ".csv", ".tsv")
_DOC_RE = re.compile(r"(?:^|/)(?:README|NOTES?|CHANGELOG|HOWTO|INSTALL)[^/]*$|\.(?:md|txt|rst)$", re.I)
_SUPP_PROC_RE = re.compile(r"\bTODO\b|\bFIXME\b|\bXXX\b|待核实|待确认", _A)
# process markers that live in notes and code comments rather than in prose:
# internal batch names, sealed or corrected plans
_SUPP_NARRATION_RE = re.compile(
    r"\bphase[-_]\d+\b|\bround[-_]\d+\b|\bsealed\b|\bfrozen\s+environment\b|\bsupersed(?:ed|es|ing)\b"
    r"|\b(?:was|were|been|later|subsequently)\s+corrected\b|\bbefore\s+(?:the\s+)?launch\b"
    # instructions about the manuscript and unfinished work left in working notes
    r"|\b(?:manuscript|paper|draft)\s+(?:must|should|now|will|needs?\s+to)\s+(?:add|drop|remove|replace|mention|say|"
    r"state|cite|report|include)\b|\bclaims?\s+(?:kept|dropped|removed|softened|weakened)\b"
    r"|\bnot\s+yet\s+(?:been\s+)?(?:evaluated|run|analy[sz]ed|finished|completed)\b|\bpartial\s+runs?\b"
    r"|\b(?:already|still)[- ]running\b"
    r"|\bto\s+be\s+(?:added|completed|filled(?:\s+in)?|evaluated|computed|written|reported)\b|\bTBD\b", re.I | _A)
# a date that is a parameter of the data (a cutoff, a window, an assignment) is
# reproduction detail, not the authors' timeline
_DATA_DATE_CTX_RE = re.compile(r"(?:=|\bcut-?offs?\b|\bwindows?\b|\bhorizon\b|\bsnapshot\b|\brelease\b|\bversion\b|"
                               r"\brecords?\b|\bevents?\b|\bcollected\b|\bfrom\b|\bsince\b|\buntil\b|\bthrough\b)"
                               r"[^.\n]{0,25}$", re.I)
# a model family before a version tag makes it a model version (mistral_v03, vicuna_v15)
_MODEL_FAMILY_RE = re.compile(r"(?:^|[_.-])(?:llama|mistral|mixtral|ministral|vicuna|qwen|gemma|phi|falcon|mpt|bloom|"
                              r"opt|gpt|t5|flan|bert|roberta|deberta|clip|vit|sdxl|whisper|deepseek|yi|internlm|"
                              r"baichuan|chatglm|glm|olmo|pythia|starcoder|codellama|granite|command|claude|gemini)"
                              r"(?:[_.-]|\d|$)", re.I)
_COMMENT_PREFIXES = ("#", "//", "%", "\"\"\"", "'''", "*", "--", "/*", ";")
_GIT_SSH_RE = re.compile(r"\bgit@([\w.-]+):([\w.-]+)/", _A)
_USER_HOST_RE = re.compile(r"\b[\w.-]+@[\w-]+(?:\.[\w-]+)*:[~/][\w./~-]*", _A)
# an account at a host with no path after it: the login command names it ("ssh ada@10.9.8.7")
_SSH_ACCOUNT_RE = re.compile(r"(?<![\w.-])(?:ssh|scp|sftp|rsync)\s+(?:-{1,2}[\w-]+(?:\s+[^\s@-]\S*)?\s+)*"
                             r"[\w.-]+@[\w-]+(?:\.[\w-]+)*", _A)
_ACCOUNT_AT_RE = re.compile(r"(?<![\w.@-])([\w.-]{3,40})@(?=[\w-])", _A)
# the account and the host of a usage example ("ssh user@remote-host", "you@your-server")
_ACCOUNT_PLACEHOLDER_RE = re.compile(r"^(?:user(?:name)?|you|your[\w-]*|me|name|login|account|someone|somebody|uid|"
                                     r"xxx+|foo|bar|baz|example|demo|test|guest|admin|root|ubuntu|runner|jovyan)$",
                                     re.I | _A)
_HOST_PLACEHOLDER_RE = re.compile(r"^(?:host(?:name)?|remote(?:[-_]?(?:host|server|machine))?|server|machine|"
                                  r"cluster|localhost|your[\w.-]*|example(?:\.[\w-]+)*|[\w-]+\.example(?:\.[\w-]+)*|"
                                  r"login[-_]?node|head[-_]?node|domain|address|ip|x+)$", re.I | _A)
# a host-shaped name where a note logs in or runs on it: after ssh, after an '@', or after "run on" (with two
# digits or a colon after it: "gpu0" alone is a device index)
_HOST_TOKEN = r"(?:gpu|node|cn|compute|worker|host|server|srv|box|dgx|login|gn|vm)[-_]?\d{1,4}"
_SUPP_HOSTNAME_RE = re.compile(
    r"(?P<pre>(?<![\w.-])(?:ssh|scp|sftp|rsync)\s+(?:-{1,2}[\w-]+\s+)*(?:[\w.-]+@)?|(?<=[\w.-])@|"
    r"\b(?:run|runs|ran|running|executed|launched|submitted|logged\s+in(?:to)?|log\s+in(?:to)?)\s+(?:on|at|to|into)"
    r"\s+(?:the\s+)?(?:(?:host|node|server|machine|box)\s+)?)(?P<host>" + _HOST_TOKEN + r")(?![\w.-])(?P<colon>:?)",
    re.I | _A)
# explicit dates only: a date-shaped seed in supplementary code is a reproduction input
_SUPP_DATE_RE = re.compile(
    r"(?<![\w.])20\d\d-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])(?![\w])"
    r"|\b(?:" + _MONTHS + "|" + _MON3 + r")\s+(?:[1-9]|[12]\d|3[01])(?:st|nd|rd|th)?,\s*20\d\d\b"
    r"|\b(?:[1-9]|[12]\d|3[01])\s+" + _MONTHS + r",?\s+20\d\d\b|\d{1,2}\s*月\s*\d{1,2}\s*日"
    r"|\b" + _MONTHS + r"\s+20\d\d\b|20\d\d\s*年\s*\d{1,2}\s*月", _A)
_LOOSE_DATE = (r"(?:20\d\d-[01]\d-[0-3]\d|(?:" + _MONTHS + "|" + _MON3 + r")\s+\d{1,2},?\s*20\d\d|\d{1,2}\s+"
               + _MONTHS + r",?\s+20\d\d|\d{1,2}\s*月\s*\d{1,2}\s*日|" + _MONTHS + r"\s+20\d\d)")
_RANGE_GAP = r"\s*(?:\.\.\.?|–|—|-|~|to|through|until|and|至|到)\s*"
_DATE_RANGE_AFTER_RE = re.compile(_RANGE_GAP + _LOOSE_DATE, re.I | _A)
_DATE_RANGE_BEFORE_RE = re.compile(_LOOSE_DATE + _RANGE_GAP + r"$", re.I | _A)
# run timestamps stored in data records ("completed_at": "2026-...T..", {"utc": 1760000000})
_TS_KEY_RE = re.compile(r"[\"']?((?:completed|started|finished|created|updated|modified|generated|launched|run|start|end|"
                        r"ran|written|built|saved|logged|submitted|registered|recorded|exported|dumped|evaluated|trained|"
                        r"frozen|sealed)_?(?:at|time|ts|on|utc|local|date)|timestamp|datetime|utc|wall_?clock)[\"']?\s*[:=]"
                        r"\s*[\"']?(20\d\d-[01]\d-[0-3]\d[T ][0-2]\d:[0-5]\d|1[5-9]\d{8}(?:\.\d+)?|"
                        r"20\d\d[01]\d[0-3]\dT[0-2]\d[0-5]\d)(?!\d)", re.I | _A)


def _is_archive_name(name: str) -> bool:
    n = name.lower()
    return n.endswith((".zip", ".tar", ".tar.gz", ".tgz", ".tar.xz", ".txz", ".tar.bz2", ".tbz2", ".gz", ".xz"))


def _zip_extra_ids(extra: bytes) -> List[int]:
    ids, i = [], 0
    while i + 4 <= len(extra):
        hid, size = int.from_bytes(extra[i:i + 2], "little"), int.from_bytes(extra[i + 2:i + 4], "little")
        ids.append(hid)
        i += 4 + size
    return ids


def _gzip_header(data: bytes) -> Optional[Dict[str, Any]]:
    """RFC 1952 header fields that can carry identity or time: FNAME, FCOMMENT, MTIME."""
    if len(data) < 10 or data[:2] != b"\x1f\x8b":
        return None
    flg = data[3]
    mtime = int.from_bytes(data[4:8], "little")
    i, fname, comment = 10, None, None
    if flg & 0x04 and len(data) >= i + 2:  # FEXTRA
        i += 2 + int.from_bytes(data[i:i + 2], "little")
    if flg & 0x08:  # FNAME
        end = data.find(b"\x00", i)
        if end >= i:
            fname, i = data[i:end].decode("latin-1"), end + 1
    if flg & 0x10:  # FCOMMENT
        end = data.find(b"\x00", i)
        if end >= i:
            comment, i = data[i:end].decode("latin-1"), end + 1
    return {"fname": fname or None, "comment": comment or None, "mtime": mtime}


def _bounded_decompress(data: bytes, kind: str, limit: int) -> Tuple[Optional[bytes], str]:
    """(bytes, status): status is ok, limit (stopped at `limit`), truncated
    (input ended before the end of the stream), or corrupt (bytes None)."""
    try:
        if kind == "gz":
            d = zlib.decompressobj(16 + zlib.MAX_WBITS)
            out = d.decompress(data, limit)
            if d.unconsumed_tail:
                return out, "limit"
            return out, ("ok" if d.eof else "truncated")
        if kind == "xz":
            d2 = lzma.LZMADecompressor()
            out = d2.decompress(data, max_length=limit)
            if d2.eof:
                return out, "ok"
            return out, ("truncated" if d2.needs_input else "limit")
    except (zlib.error, lzma.LZMAError, EOFError):
        return None, "corrupt"
    return None, "corrupt"


def _decode_text(data: bytes) -> Tuple[str, str]:
    """BOM-aware decoding (UTF-8-SIG, UTF-16), strict UTF-8, then GB18030 (a
    common non-UTF-8 encoding for Chinese notes), else UTF-8 with replacement."""
    if data.startswith(codecs.BOM_UTF8):
        return data[3:].decode("utf-8", errors="replace"), "utf-8-sig"
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return data.decode("utf-16", errors="replace"), "utf-16"
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass
    try:
        return data.decode("gb18030"), "gb18030"
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace"), "utf-8 (lossy)"


def _looks_text(chunk: bytes) -> bool:
    """Text sniffing on a prefix: a BOM, or decodable as UTF-8 / GB18030 (a
    multibyte character cut at the end of the prefix is tolerated)."""
    if not chunk:
        return False
    if chunk.startswith((codecs.BOM_UTF8, codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return True
    if b"\x00" in chunk:
        return False
    for enc in ("utf-8", "gb18030"):
        try:
            codecs.getincrementaldecoder(enc)().decode(chunk, final=False)
            return True
        except UnicodeDecodeError:
            continue
    return False


def _docstring_lines(text: str) -> Set[int]:
    """1-based numbers of the lines inside triple-quoted blocks, which a reader
    sees as notes as much as # comments: what the scan reads and the batch
    reviewer is shown. Never what the loop may edit — a triple-quoted string
    can be a template the code writes out (_code_note_lines decides that)."""
    inside, out = False, set()
    for no, line in enumerate(text.split("\n"), 1):
        n = line.count('"""') + line.count("'''")
        if inside or n:
            out.add(no)
        if n % 2:
            inside = not inside
    return out


# What the fix loop may edit in a code member: the lines that are notes and
# nothing else, read by the rules of the member's language — a comment line,
# a line of a docstring (a string that stands alone as a statement), or a blank
# line outside every string. A triple-quoted string assigned to a name (a
# template that writes a table, a prompt the code sends) is code, and so is a
# line of it that starts with '#' or '%', a shell here-document, and a Python
# continuation line that starts with '*' or '%'. A member of a language the
# loop does not know (a patch, a license, a file without an extension) has no
# editable line: its findings are for a person.
_NOTE_LANGS: Dict[str, Dict[str, Any]] = {
    "hash": {"line": ("#",), "quotes": ("'", '"'), "span": ("'", '"')},
    "julia": {"line": ("#",), "block": (("#=", "=#"),), "quotes": ('"',), "span": ('"',), "triple": True},
    "shell": {"line": ("#",), "quotes": ("'", '"'), "span": ("'", '"'), "word_hash": True, "heredoc": True},
    "c": {"line": ("//",), "block": (("/*", "*/"),), "quotes": ("'", '"'), "span": ()},
    "js": {"line": ("//",), "block": (("/*", "*/"),), "quotes": ("'", '"', "`"), "span": ("`",)},
    "jvm": {"line": ("//",), "block": (("/*", "*/"),), "quotes": ("'", '"'), "span": (), "triple": True},
    "percent": {"line": ("%",), "quotes": (), "span": (), "escape_line": True},
    "dash": {"line": ("--",), "quotes": ("'", '"'), "span": ()},
    "semi": {"line": (";",), "quotes": ('"',), "span": ('"',)},
}
_NOTE_LANG_BY_EXT = {
    ".py": "python", ".pyw": "python", ".pyi": "python",
    ".r": "hash", ".pl": "hash", ".pm": "hash", ".rb": "hash", ".mk": "hash", ".cmake": "hash", ".nf": "hash",
    ".smk": "hash", ".jl": "julia",
    ".sh": "shell", ".bash": "shell", ".zsh": "shell", ".ksh": "shell",
    ".c": "c", ".cc": "c", ".cpp": "c", ".cxx": "c", ".h": "c", ".hh": "c", ".hpp": "c", ".cu": "c", ".cuh": "c",
    ".java": "c", ".go": "c", ".rs": "c", ".cs": "c", ".proto": "c",
    ".js": "js", ".mjs": "js", ".cjs": "js", ".ts": "js", ".tsx": "js", ".jsx": "js",
    ".kt": "jvm", ".kts": "jvm", ".scala": "jvm", ".swift": "jvm", ".groovy": "jvm",
    ".tex": "percent", ".sty": "percent", ".cls": "percent", ".m": "percent",
    ".lua": "dash", ".sql": "dash", ".hs": "dash",
    ".el": "semi", ".lisp": "semi", ".clj": "semi", ".scm": "semi",
}
_NOTE_LANG_BY_NAME = {"makefile": "hash", "gnumakefile": "hash", "dockerfile": "hash", "snakefile": "hash"}
_HEREDOC_RE = re.compile(r"<<(-?)[ \t]*(?:'([^'\n]+)'|\"([^\"\n]+)\"|\\?([A-Za-z_][\w.-]*))")


def _py_note_lines(text: str) -> Optional[Set[int]]:
    """The editable lines of Python source, by Python's own tokenizer (None
    when the text cannot be tokenized)."""
    import tokenize
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except Exception:  # noqa: BLE001 — any tokenizer failure: not readable as Python
        return None
    starts = (None, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT)
    sig = [i for i, tk in enumerate(toks) if tk.type not in (tokenize.NL, tokenize.COMMENT)]
    bare: Set[int] = set()  # the tokens of a string that stands alone as a statement (a docstring)
    k = 0
    while k < len(sig):
        tk = toks[sig[k]]
        prev = toks[sig[k - 1]].type if k else None
        if tk.type == tokenize.STRING and prev in starts:
            j = k
            while j < len(sig) and toks[sig[j]].type == tokenize.STRING:
                j += 1
            end = toks[sig[j]].type if j < len(sig) else tokenize.ENDMARKER
            if end in (tokenize.NEWLINE, tokenize.ENDMARKER) and not any(
                    re.match(r"[A-Za-z]*[bBfF]", toks[sig[x]].string) for x in range(k, j)):
                bare.update(sig[x] for x in range(k, j))
            k = j
            continue
        k += 1
    skip = {tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.ENDMARKER}
    note_rows: Set[int] = set()
    code_rows: Set[int] = set()
    for i, tk in enumerate(toks):
        if tk.type in skip:
            continue
        rows = range(tk.start[0], tk.end[0] + 1)
        (note_rows if tk.type == tokenize.COMMENT or i in bare else code_rows).update(rows)
    return {no for no, ln in enumerate(text.split("\n"), 1)
            if no not in code_rows and (no in note_rows or not ln.strip())}


def _scan_note_lines(text: str, line: Sequence[str] = (), block: Sequence[Tuple[str, str]] = (),
                     quotes: Sequence[str] = (), span: Sequence[str] = (), triple: bool = False,
                     word_hash: bool = False, heredoc: bool = False, escape_line: bool = False) -> Set[int]:
    """The editable lines of a member, by a light lexer of its language: line
    and block comments are notes; strings (a quote that may span lines, a
    triple quote, a here-document) and everything else are code."""
    n = len(text)
    note_rows: Set[int] = set()
    code_rows: Set[int] = set()
    i, row = 0, 1
    pending: List[Tuple[str, bool]] = []  # here-documents whose bodies start on the next line

    def mark(rows: Set[int], a: int, b: int, r0: int) -> int:
        """Mark the rows text[a:b] is on (from r0); return the row text[b] is on."""
        r1 = r0 + text.count("\n", a, b)
        rows.update(range(r0, r1 + 1))
        return r1

    while i < n:
        c = text[i]
        if c == "\n":
            i += 1
            row += 1
            while pending:  # a here-document's body, through its terminator line: code
                delim, strip_tabs = pending.pop(0)
                j = i
                while j < n:
                    e = text.find("\n", j)
                    e = n if e < 0 else e
                    ln = text[j:e].rstrip("\r")
                    j = e
                    if (ln.lstrip("\t") if strip_tabs else ln) == delim:
                        break
                    j = e + 1
                row = mark(code_rows, i, min(j, n), row)
                i = j
            continue
        if c in " \t\r\f":
            i += 1
            continue
        lc = next((tok for tok in line if text.startswith(tok, i)), None)
        if lc and (not word_hash or i == 0 or text[i - 1] in " \t\n;|&()") and \
                not (escape_line and i and text[i - 1] == "\\"):
            e = text.find("\n", i)
            note_rows.add(row)
            i = n if e < 0 else e
            continue
        bc = next(((o, cl) for o, cl in block if text.startswith(o, i)), None)
        if bc:
            e = text.find(bc[1], i + len(bc[0]))
            e = n if e < 0 else e + len(bc[1])
            row = mark(note_rows, i, e, row)
            i = e
            continue
        if c in quotes:
            q = c * 3 if triple and text.startswith(c * 3, i) else c
            j = i + len(q)
            while j < n:
                if text[j] == "\\" and not (heredoc and q == "'"):  # no escape inside a shell '...'
                    j += 2
                    continue
                if text.startswith(q, j):
                    j += len(q)
                    break
                if text[j] == "\n" and len(q) == 1 and q not in span:
                    break  # a string that cannot span lines ends with its line
                j += 1
            row = mark(code_rows, i, min(j, n), row)
            i = j
            continue
        if heredoc and c == "<" and not text.startswith("<<<", i):
            m = _HEREDOC_RE.match(text, i)
            if m:
                pending.append((m.group(2) or m.group(3) or m.group(4), bool(m.group(1))))
                code_rows.add(row)
                i = m.end()
                continue
        code_rows.add(row)
        i += 2 if c == "\\" else 1
    return {no for no, ln in enumerate(text.split("\n"), 1)
            if no not in code_rows and (no in note_rows or not ln.strip())}


def _code_note_lines(text: str, member: str) -> Set[int]:
    """1-based numbers of the lines of a code member the fix loop may edit:
    notes and nothing else, by the member's language (_NOTE_LANGS); a member
    of an unknown language has none."""
    name = posixpath.basename(str(member or "")).lower()
    lang = _NOTE_LANG_BY_EXT.get(os.path.splitext(name)[1]) or _NOTE_LANG_BY_NAME.get(name)
    if lang is None:
        return set()
    got = _py_note_lines(text) if lang == "python" else _scan_note_lines(text, **_NOTE_LANGS[lang])
    if got is None:
        # not readable as Python: every triple-quoted text counts as code (it may be a template)
        got = _scan_note_lines(text, line=("#",), quotes=("'", '"'), triple=True)
    if text.startswith("#!"):
        got.discard(1)  # the interpreter line
    return got


def _note_lines_ok(text: str, first: int, last: int, member: str) -> bool:
    """Every line first..last (1-based) of a member is one the loop may edit:
    any line of a document, a note line of code (_code_note_lines)."""
    if _member_kind(member) != "code":
        return True
    ok = _code_note_lines(text, member)
    return all(i in ok for i in range(first, last + 1))


def _line_starts(text: str) -> List[int]:
    starts, pos = [0], 0
    for line in text.split("\n")[:-1]:
        pos += len(line) + 1
        starts.append(pos)
    return starts


class _SuppState:
    def __init__(self) -> None:
        self.total = 0
        self.docs: List[Tuple[str, str, str]] = []   # (member, kind, redacted text) for the reviewer
        self.docs_bytes = 0
        self.notes_bytes = 0
        self.unreadable: List[str] = []
        self.shallow = 0
        # what the reviewer never reads in full: members past the review text budget
        # (left out), members cut short by it, and notes cut at the per-member limit
        self.review_left: List[str] = []
        self.review_cut: List[str] = []
        self.review_partial = 0
        # text members no batch reviewer is given by design (the rules still scan them):
        # data records, and code or logs without a note line — counted, so coverage states its scope
        self.review_scope: Counter = Counter()


_SUPP_DOC_HEADER = "=== member: "
MAX_SUPP_NOTES_BYTES = 200 * 1024     # code comments/docstrings and log heads for the reviewer
MAX_SUPP_NOTES_PER_MEMBER = 8 * 1024


def _narrative_lines(text: str) -> List[Tuple[int, str]]:
    """(line number, line) of the comment and docstring lines of a code member:
    the notes a reader sees, without the code."""
    doc = _docstring_lines(text)
    out = []
    for no, line in enumerate(text.split("\n"), 1):
        s = line.strip()
        if (no in doc or s.startswith(_COMMENT_PREFIXES)) and re.search(r"[A-Za-z一-鿿]{3}", s):
            out.append((no, s))
    return out


def scan_supp(path: str, ctx: ScanContext, paper_dir: str, supp_max_mb: Optional[float] = None,
              capture: Optional[Dict[str, Any]] = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Scan a .zip / .tar(.gz|.xz|.bz2) / directory supplement (nested
    archives up to depth 3). Returns (findings, info). With `capture`, every
    leaf member's sha256 and the bytes of text members up to the snapshot
    limits are recorded there (the change review diffs them), and so is the
    complete name list of every container read (`listed`: member -> its
    container; `containers`: container -> {parent, opened}) — taken from the
    archive's directory, whatever the scan budget read — so a member the budget
    skipped is never mistaken for a member left out."""
    artifact = _display_path(path, paper_dir)
    st = _SuppState()
    out: List[Dict[str, Any]] = []
    info: Dict[str, Any] = {"path": artifact, "members": 0}
    names_seen: List[str] = []
    refs: List[Tuple[str, str, str, int, str, str]] = []  # (kind, ref, member, line, excerpt, member kind)
    codenames: Counter = Counter()
    structural_names: Set[str] = set()  # code names from the layout or a placeholder path, not from a title
    procfile_members: Set[str] = set()
    persisted = [(tok, re.compile(r"(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_])" % re.escape(tok), re.I))
                 for tok in (ctx.persisted_codenames or [])]
    if os.path.isfile(path):
        info["sha256"] = _sha256_file(path)
        info["size"] = os.path.getsize(path)
        if supp_max_mb and info["size"] > supp_max_mb * 1024 * 1024 and ctx.on("SUPP-SIZE"):
            out.append(make_finding(ctx, "SUPP-SIZE", BLOCK, DEFINITE, "supp", "%.1f MB" % (info["size"] / 1048576.0),
                                    "limit %s MB" % supp_max_mb, {"artifact": artifact}))
    elif not os.path.isdir(path):
        st.unreadable.append(artifact)
        info["unreadable"] = True
        return out, info

    def emit(check: str, sev: str, raw: str, excerpt: str, member: str, line: Optional[int] = None,
             cert: str = DEFINITE, note: Optional[str] = None, kind: Optional[str] = None,
             demoted: Optional[str] = None) -> None:
        # `kind` (doc, code, data, log) becomes the subregion, so one ruling never
        # covers a README sentence and a data record at once
        if ctx.on(check):
            out.append(make_finding(ctx, check, sev, cert, "supp", raw, excerpt,
                                    {"artifact": artifact, "member": ctx.redactor.redact(member), "line": line},
                                    note=note, sub=kind, demoted=demoted))

    def ident_in(s: str) -> bool:
        return bool(ctx.anonymous and s and (ctx.identity.finditer(s) or ctx.auto.finditer(s)))

    def note_listed(member: str, container: str, depth: int) -> None:
        # the change review's name list: a member exists in `container` whether or not
        # the scan budget lets its bytes be read (a .gz member is listed under the name
        # its content is hashed with; an archive the walk opens is a container)
        if capture is None:
            return
        low = member.lower()
        if _is_archive_name(low) and depth < MAX_SUPP_DEPTH:
            for ext in (".gz", ".xz"):
                if low.endswith(ext) and not low.endswith((".tar" + ext, ".tgz", ".txz")):
                    note_listed(member[:-len(ext)], container, depth + 1)
                    return
            capture.setdefault("containers", {}).setdefault(member, {"parent": container, "opened": False})
            return
        capture.setdefault("listed", {})[member] = container

    def note_opened(container: str, complete: bool) -> None:
        if capture is not None:
            rec = capture.setdefault("containers", {}).setdefault(
                container, {"parent": None if container == "" else "", "opened": False})
            rec["opened"] = bool(complete)

    def budget(n: int, member: str) -> bool:
        if st.total + n > MAX_SUPP_TOTAL_BYTES:
            emit("SUPP-UNSCANNED", INFO, member, "total scanned bytes above the archive limit", member)
            return False
        st.total += n
        return True

    def check_name(member: str) -> None:
        # the matched component (or marker kind) is the match, so ".git/" x200
        # is ONE group; the member path goes into the location
        info["members"] += 1
        m = _ARIS_RE.search(member)
        if m:
            emit("SUPP-ARIS", BLOCK, m.group(0).strip("/"), "ARIS/agent working file in the archive", member)
        m = _JUNK_BLOCK_RE.search(member)
        if m:
            emit("SUPP-JUNK", BLOCK, m.group(0).strip("/"), "repository/OS/secret junk", member)
        else:
            m = _JUNK_WARN_RE.search(member)
            if m:
                emit("SUPP-JUNK", WARN, m.group(0).strip("/"), "editor/cache junk", member)
            else:
                m = _RUNLOG_RE.search(member)
                if m:  # one group for every run log: the reviewer rules once whether reproduction needs them
                    emit("SUPP-JUNK", WARN, "run log or runtime artifact", "'%s' in the archive" % m.group(0).strip("/"),
                         member, cert=CANDIDATE)
        base = member.rsplit("/", 1)[-1]
        if not (m or _ARIS_RE.search(member)):  # junk, run logs, and agent files are reported as such
            stem = os.path.splitext(base)[0]
            doc_like = bool(_DOC_RE.search(member) or _RUNLOG_RE.search(member))
            m_p = _PROCFILE_STRONG_RE.search(member)
            if not m_p:
                m_s = _PROCFILE_SUFFIX_RE.search(stem)
                if m_s and (m_s.group(1).lower() == "old" or doc_like):
                    m_p = m_s
            if not m_p and doc_like:
                m_p = _PROCFILE_WEAK_RE.search(stem)
            if m_p:
                procfile_members.add(member)
                emit("SUPP-PROCFILE", WARN, "process file: %s" % re.sub(r"[\d_-]+$", "", m_p.group(1).lower()),
                     "'%s' in %s" % (m_p.group(1), member), member, cert=CANDIDATE)
            else:
                m_r = _PROCFILE_REG_RE.search(member)
                if m_r:  # a registration record: the policy decides whether it is history to drop
                    procfile_members.add(member)
                    kind_r = re.sub(r"[\d_-]+$", "", m_r.group(1).lower()).replace("addenda", "addendum")
                    flag = ctx.reg_labels == "flag"
                    emit("SUPP-PROCFILE", WARN if flag else INFO, "registration record: %s" % kind_r,
                         "'%s' in %s" % (m_r.group(1), member), member, cert=CANDIDATE,
                         note=None if flag else "policy registration_labels: keep")
            m_h = _SUPP_HW_NAME_RE.search(member)
            if m_h:
                emit("SUPP-HW", WARN if ctx.supp_hardware else INFO, m_h.group(1).lower(),
                     "hardware or OS word in a member name: %s" % member, member, cert=CANDIDATE, kind="name")
        names_seen.append(member)
        spaced = member.translate(_NAME_SEPARATORS)  # alice_notes/ -> "alice notes " (same offsets)
        hits = (ctx.identity.finditer(spaced) + ctx.auto.finditer(spaced)) if ctx.anonymous else []
        hm = _NAME_HOME_RE.search(member)
        if hits:
            a_, b_, _ = hits[0]
            emit("SUPP-NAME", BLOCK, member[a_:b_], "identity term in a member name", member)
        elif hm:
            emit("SUPP-NAME", BLOCK, hm.group(0), "home-directory path stored in the archive", member)
        else:
            for part in member.split("/"):
                for kind, rx in _NAME_MARKERS:
                    m = rx.search(part)
                    if m and kind == "version" and _MODEL_FAMILY_RE.search(part[:m.start()]):
                        m = None  # a model version, not an iteration of the authors' file
                    if m:
                        emit("SUPP-NAME", WARN, "%s marker in a name" % kind, "'%s' in %s" % (m.group(0), part), member)
                        return
            if member not in procfile_members:
                for part in member.split("/"):
                    m = _COPY_MARKER_RE.search(part)
                    if m:  # x_now.py, figs_prev/: a working copy, not a name a reader needs
                        emit("SUPP-NAME", WARN, "working-copy marker in a name", "'_%s' in %s" % (m.group(1), part),
                             member, cert=CANDIDATE)
                        return

    def scan_more(member: str, text: str, kind: str, low: str, where: Any, narrative: Any,
                  enc_note: Optional[str], editable: Any = None) -> None:
        """SUPP-HW, SUPP-PATH, SUPP-RUNTIME, SUPP-LANG, unfinished status
        strings, and code-name candidates of one text member."""
        def at(check: str, sev: str, raw: str, s: int, e: int, why: Optional[str] = None) -> None:
            no, line, base_ = where(s)
            emit(check, sev, raw, _excerpt(line, s - base_, e - base_), member, no, CANDIDATE,
                 "; ".join(x for x in (why, enc_note) if x) or None, kind=kind)

        if kind in ("doc", "code") and ctx.on("SUPP-HW"):
            # one finding per word and member, with every line it is on (a fix needs them all);
            # one occurrence is one finding: where the patterns overlap ("CPU only", "8 GPUs",
            # "no GPU"), the longest wording stands for it, never also the bare word inside it
            hw_hits = sorted(((m.start(), -(m.end() - m.start()), i, m)
                              for i, rx in enumerate((_SUPP_HW_RE, _HW_RE, _QTY_RE))
                              for m in rx.finditer(text) if narrative(m.start())), key=lambda x: x[:3])
            # one finding per word, member, and use: the places where the word names a measured quantity
            # ("measured CPU cost") or sits in a heading's brackets are one finding (never drafted as a
            # deletion; a leak ruling keeps it at WARN), the other places another
            seen_hw: Dict[Tuple[str, bool], Optional[Dict[str, Any]]] = {}
            uses_of: Dict[Tuple[str, bool], Set[str]] = {}
            # the lines of each finding the loop may not edit (a code line, a template string): a finding
            # with no other line is for a person
            code_hw: Dict[Tuple[str, bool], Set[int]] = {}
            hw_end = -1
            for _s, _neg, _i, m in hw_hits:
                if m.start() < hw_end:
                    continue  # inside (or across) the wording already counted for this occurrence
                hw_end = m.end()
                k = _norm_key(m.group(0))
                no_hw = where(m.start())[0]
                usage = _hw_usage(text, m.start(), m.end(), heading=None if kind == "doc" else False)
                kk = (k, bool(usage))
                if usage:
                    uses_of.setdefault(kk, set()).add(usage)
                if kind == "code" and editable is not None and not editable(m.start()):
                    code_hw.setdefault(kk, set()).add(no_hw)
                if kk in seen_hw:
                    f_hw = seen_hw[kk]
                    if f_hw is not None and no_hw not in f_hw["lines"] and len(f_hw["lines"]) < 200:
                        f_hw["lines"].append(no_hw)
                    if f_hw is not None and usage == "title" and not f_hw.get("title_line"):
                        _no, hline, hbase = where(m.start())
                        hs, he = _one_space(text, *_take_marks(text, m.start(), m.end()))
                        f_hw["title_line"] = ctx.redactor.redact(_collapse_ws(hline))[:300]
                        f_hw["title_without"] = ctx.redactor.redact(_collapse_ws(
                            text[hbase:hs] + text[he:hbase + len(hline)]))[:300]
                    continue
                n0 = len(out)
                at("SUPP-HW", WARN if ctx.supp_hardware else INFO, m.group(0), m.start(), m.end())
                seen_hw[kk] = out[-1] if len(out) > n0 else None
                if seen_hw[kk] is not None:
                    seen_hw[kk]["matched"] = [ctx.redactor.redact(_collapse_ws(m.group(0)))[:120]]
                    seen_hw[kk]["lines"] = [no_hw]
                    if usage == "title":  # the heading as a person may reword it, for the plan
                        _no, hline, hbase = where(m.start())
                        hs, he = _one_space(text, *_take_marks(text, m.start(), m.end()))
                        seen_hw[kk]["title_line"] = ctx.redactor.redact(_collapse_ws(hline))[:300]
                        seen_hw[kk]["title_without"] = ctx.redactor.redact(_collapse_ws(
                            text[hbase:hs] + text[he:hbase + len(hline)]))[:300]
            for kk, f_hw in seen_hw.items():
                if f_hw is not None and kk in code_hw and set(f_hw["lines"]) <= code_hw[kk]:
                    f_hw["code_line"] = True  # every place is code: never a supp-delete (for a person)
                if f_hw is None or not kk[1]:
                    continue
                f_hw["hw_usage"] = "+".join(sorted(uses_of.get(kk) or {"metric"}))
                f_hw["note"] = "; ".join(x for x in (f_hw.get("note"), "the hardware word names a measured "
                                                     "quantity or sits in a heading (%s)" % f_hw["hw_usage"]) if x)
        if ctx.on("SUPP-PATH") and ("<" in text or "${" in text):
            shellish = bool(_SHELLISH_RE.search(member))
            first: Dict[str, List[Any]] = {}
            for m in _PLACEHOLDER_ROOT_RE.finditer(text):
                if (m.group(1).startswith("$") and shellish) or m.group(1).lower() in _HTML_TAGS:
                    continue  # ${VAR}/x is how a shell script or a config file says it
                first.setdefault(m.group(1), [m, 0])[1] += 1
            for tok, (m, n) in sorted(first.items()):
                usage = kind == "doc" or narrative(m.start())  # usage notation in a README or a comment
                at("SUPP-PATH", INFO if usage else WARN, "placeholder root %s/" % tok, m.start(), m.end(),
                   "%d occurrence(s) in this member" % n + ("; usage notation in a note" if usage else ""))
        if kind in ("doc", "code"):
            for m in _SCRIPT_REF_RE.finditer(text):
                if not (narrative(m.start()) or (m.start() > 0 and text[m.start() - 1] in "\"'")):
                    continue
                no, line, base_ = where(m.start())
                # a command ("python x/y.py", "Usage: y.py") names a path inside the package
                cmd = bool(_CMD_BEFORE_RE.search(line[:m.start() - base_]))
                refs.append(("script_cmd" if cmd else "script", m.group(1), member, no,
                             _excerpt(line, m.start() - base_, m.end() - base_), kind))
            if kind == "code":
                for m in _DATA_REF_RE.finditer(text):
                    if narrative(m.start()):
                        no, line, base_ = where(m.start())
                        refs.append(("data", m.group(1), member, no,
                                     _excerpt(line, m.start() - base_, m.end() - base_), kind))
                if "!/" not in member:
                    for m in _REL_LITERAL_RE.finditer(text):
                        if narrative(m.start()):
                            continue
                        no, line, base_ = where(m.start())
                        refs.append(("relpath", m.group(2), member, no,
                                     _excerpt(line, m.start() - base_, m.end() - base_), kind))
        for m in _CODENAME_PATH_RE.finditer(text, 0, MAX_SUPP_DATA_DEEP_CHARS):
            tok = m.group(1)
            if tok.lower() not in _GENERIC_NAMES and tok.lower() not in _GENERIC_PACKAGES:
                codenames[tok] += 1
                structural_names.add(tok)
        if kind == "code" and ctx.on("SUPP-RUNTIME") and _RUNTIME_CALL_RE.search(text):
            doclines = _docstring_lines(text)
            stamp_vars: Set[str] = set()
            hits_rt: Dict[str, Tuple[int, str]] = {}
            for no, line in enumerate(text.split("\n"), 1):
                s_ = line.strip()
                if not s_ or s_.startswith(_COMMENT_PREFIXES) or no in doclines:
                    continue
                call = _RUNTIME_CALL_RE.search(line)
                uses = bool(call) or any(re.search(r"(?<![\w.])%s\b" % re.escape(v), line) for v in stamp_vars)
                if call:
                    am = _ASSIGN_RE.match(line)
                    if am and not _RUNTIME_KEY_RE.search(line):
                        stamp_vars.add(am.group(1))
                if not uses:
                    continue
                if _RUNTIME_KEY_RE.search(line):
                    hits_rt.setdefault("run time written under a key", (no, line))
                elif _RUNTIME_NAME_RE.search(line):
                    hits_rt.setdefault("run time in an output file name", (no, line))
            for label, (no, line) in sorted(hits_rt.items()):
                # a candidate for a person (never a fix-loop edit): INFO and not reviewed, a reviewed WARN under --strict
                emit("SUPP-RUNTIME", WARN if ctx.strict else INFO, label, _collapse_ws(line)[:200], member, no,
                     CANDIDATE, enc_note, kind=kind)
        if ctx.on("SUPP-TEXT") and kind in ("code", "data"):
            # recall candidates for a person (plan only, never an edit): the authors' machine set in code, debug
            # output left in, a working-copy alias; a data record whose text field tells the run's story
            found_p2: List[Tuple[str, int, int]] = []
            if kind == "code":
                for rx, label in _CODE_P2_RES:
                    m = rx.search(text, 0, MAX_SUPP_DATA_DEEP_CHARS)
                    if m:
                        found_p2.append((label, m.start(), m.end()))
            elif len(text) <= MAX_SUPP_DATA_DEEP_CHARS:
                for m in _DATA_TEXT_FIELD_RE.finditer(text):
                    v = m.group("v")
                    if _DATA_STORY_RE.search(v) or _REVISION_RE.search(v) or _PROC_BATCH_P2_RE.search(v):
                        found_p2.append(("a data record's text field tells the run's story", m.start("v"),
                                         m.end("v")))
                        break
            for label, s_, e_ in found_p2:
                no, line, base_ = where(s_)
                n0 = len(out)
                emit("SUPP-TEXT", WARN, label, _excerpt(line, s_ - base_, e_ - base_), member, no, CANDIDATE,
                     "; ".join(x for x in ("for a person: the loop never edits code or data", enc_note) if x),
                     kind=kind)
                if len(out) > n0:
                    out[-1]["plan_only"] = True
                    out[-1]["code_line"] = kind == "code"
        if kind != "log":
            sm = list(_STATUS_STR_RE.finditer(text, 0, MAX_SUPP_DATA_DEEP_CHARS))
            if sm:
                at("SUPP-TEXT", WARN, "unfinished status string", sm[0].start(), sm[0].end(),
                   "%d string(s) like '%s'" % (len(sm), sm[0].group(0)[:60]))
        if kind == "doc" and ctx.on("SUPP-LANG") and ctx.paper_script == "latin":
            cjk = len(_CJK_RE.findall(text))
            lat = len(re.findall(r"[A-Za-z]", text))
            if cjk >= 100 and cjk / float(cjk + lat) >= 0.3:
                emit("SUPP-LANG", INFO, "document mostly in another language",
                     "%d CJK characters, %d Latin letters" % (cjk, lat), member, None, CANDIDATE, enc_note, kind=kind)
        if kind == "doc":
            first = next((ln for ln in text[:2000].split("\n") if ln.strip()), "")
            if member not in procfile_members and _PROCFILE_TITLE_RE.match(first) and ctx.on("SUPP-PROCFILE"):
                procfile_members.add(member)
                emit("SUPP-PROCFILE", WARN, "process title", "title '%s'" % _collapse_ws(first)[:80], member, 1,
                     CANDIDATE, enc_note, kind=kind)
            for m in _CODENAME_TITLE_RE.finditer(text[:4000]):
                if m.group(1).lower() not in _GENERIC_NAMES:
                    codenames[m.group(1)] += 1
        elif kind == "code":
            for m in _CODENAME_CODE_RE.finditer(text):
                if m.group(1).lower() not in _GENERIC_NAMES:
                    codenames[m.group(1)] += 1
                    structural_names.add(m.group(1))

    def scan_text_member(member: str, data: bytes) -> None:
        text, enc = _decode_text(data)
        low = member.lower()
        is_doc = bool(_DOC_RE.search(member))
        is_data = low.endswith(_DATA_EXTS) and not is_doc
        is_log = not (is_doc or is_data) and bool(_RUNLOG_RE.search(member))
        is_code = not (is_doc or is_data or is_log)
        kind = "doc" if is_doc else "data" if is_data else "log" if is_log else "code"
        note = None if enc in ("utf-8", "utf-8-sig") else "decoded as %s" % enc
        # a large data dump (model outputs, run records) is scanned for what can
        # identify the authors — identity terms, home paths, secrets — and for run
        # timestamps; shell prompts and hostnames inside generated text are noise
        big_data = is_data and len(text) > MAX_SUPP_DATA_DEEP_CHARS
        if big_data:
            st.shallow += 1
        line_starts: List[List[int]] = []

        def where(s: int) -> Tuple[int, str, int]:
            if not line_starts:  # computed only once a member has a hit
                line_starts.append(_line_starts(text))
            starts = line_starts[0]
            k = bisect.bisect_right(starts, s) - 1
            end = starts[k + 1] - 1 if k + 1 < len(starts) else len(text)
            return k + 1, text[starts[k]:end], starts[k]

        def hit(sev: str, raw: str, s: int, e: int, cert: str = DEFINITE, why: Optional[str] = None,
                demoted: Optional[str] = None) -> None:
            no, line, base = where(s)
            n0 = len(out)
            emit("SUPP-TEXT", sev, raw, _excerpt(line, s - base, e - base), member, no, cert,
                 "; ".join(x for x in (why, note) if x) or None, kind=kind, demoted=demoted)
            if len(out) > n0 and is_code and not editable(s):
                out[-1]["code_line"] = True  # a code line: the fix loop never edits it (for a person)

        doc_lines: List[Set[int]] = []
        note_ok: List[Set[int]] = []

        def editable(s: int) -> bool:  # a line the fix loop may edit: a note and nothing else (_code_note_lines)
            if not is_code:
                return True
            if not note_ok:
                note_ok.append(_code_note_lines(text, member))
            return where(s)[0] in note_ok[0]

        def narrative(s: int) -> bool:  # docs, or a comment or docstring line in code
            if is_doc:
                return True
            if not is_code:
                return False
            no, line, _ = where(s)
            if line.lstrip().startswith(_COMMENT_PREFIXES):
                return True
            if not doc_lines:
                doc_lines.append(_docstring_lines(text))
            return no in doc_lines[0]

        ident_spans: List[Tuple[int, int, Any]] = []
        if ctx.anonymous and (ctx.identity or ctx.auto):
            folded = fold_text(text)  # once per member, shared by both matchers
            for matcher in (ctx.identity, ctx.auto):
                for a, b, _ in matcher.finditer(text, folded):
                    ident_spans.append((a, b, None))
                    hit(BLOCK, text[a:b], a, b)
        for rx in _IDENT_PATH_RES:
            for m in rx.finditer(text):
                if not _PATH_PLACEHOLDER_RE.match(m.group(0)):
                    hit(BLOCK, m.group(0)[:200], m.start(), m.end())
        for a, b in find_secrets(text):
            hit(BLOCK, text[a:b], a, b)
        # hosts: model-generated text in data records invents shell prompts and
        # hostnames; there they are WARN candidates unless an identity term is in them
        if not big_data and "@" in text and (":/" in text or ":~" in text):
            for m in _USER_HOST_RE.finditer(text):
                g = _GIT_SSH_RE.match(m.group(0))
                if g and not ident_in(g.group(2)):
                    continue
                if is_data and not _overlaps(ident_spans, m.start(), m.end()):
                    hit(WARN, m.group(0), m.start(), m.end(), CANDIDATE, "inside a data record")
                else:
                    hit(BLOCK, m.group(0), m.start(), m.end())
        shellish_m = bool(_SHELLISH_RE.search(member))
        if not big_data and "@" in text:
            # an account at a host with no path after it ("ssh ada@10.9.8.7"), and an account named the way
            # an author's name becomes a login (from the identity list: plee, pat.lee, …)
            acct: List[Tuple[int, int, Any]] = []
            for m in _SSH_ACCOUNT_RE.finditer(text):
                if is_code and not (narrative(m.start()) or shellish_m):
                    continue
                user_, _at, host_ = m.group(0).split()[-1].partition("@")
                if _ACCOUNT_PLACEHOLDER_RE.match(user_) or _HOST_PLACEHOLDER_RE.match(host_):
                    continue  # "ssh user@remote-host": how to log in, no account of the authors
                acct.append((m.start(), m.end(), None))
                if is_data and not _overlaps(ident_spans, m.start(), m.end()):
                    hit(WARN, m.group(0), m.start(), m.end(), CANDIDATE, "inside a data record")
                else:
                    hit(BLOCK, m.group(0), m.start(), m.end(), DEFINITE, "an account at a host")
            if ctx.derived_users:
                for m in _ACCOUNT_AT_RE.finditer(text):
                    if m.group(1).lower() in ctx.derived_users and not _overlaps(acct, m.start(), m.end()):
                        hit(WARN if is_data else BLOCK, m.group(0), m.start(), m.end(),
                            CANDIDATE if is_data else DEFINITE, "an account named the way an author's name "
                                                                "becomes a login")
        if not big_data and not is_data:
            for m in _SUPP_HOSTNAME_RE.finditer(text):
                if is_code and not (narrative(m.start()) or shellish_m):
                    continue
                pre = m.group("pre")
                login_ = re.search(r"([\w.-]+)@$", pre)
                if login_ and _ACCOUNT_PLACEHOLDER_RE.match(login_.group(1)):
                    continue  # "ssh user@host1": an example of how to log in
                by_login = pre.endswith("@") or re.match(r"\s*(?:ssh|scp|sftp|rsync)\b", pre, re.I)
                if not by_login and not (m.group("colon") or len(re.sub(r"\D", "", m.group("host"))) >= 2):
                    continue  # "run on gpu0": a device index, not a host
                hit(BLOCK, m.group("host"), m.start("host"), m.end("host"), DEFINITE, "a host name where a note "
                                                                                       "logs in or runs")
        for rx, hint in ((_HOST_SUFFIX_RE, any(s in text for s in _HOST_SUFFIXES)),
                         (_WANDB_RE, "andb.ai" in text or "ANDB.AI" in text)):
            if big_data or not hint:
                continue
            for m in rx.finditer(text):
                if rx is _HOST_SUFFIX_RE and not _host_ok(text, m, code=is_code):
                    continue
                if is_data and not _overlaps(ident_spans, m.start(), m.end()):
                    hit(WARN, m.group(0), m.start(), m.end(), CANDIDATE, "inside a data record")
                else:
                    hit(BLOCK, m.group(0), m.start(), m.end())
        if not big_data:
            for m in _IPV4_RE.finditer(text):
                if _ipv4_ok(text, m) == DEFINITE and not m.group(0).startswith(("127.", "0.")):
                    hit(WARN if is_data else BLOCK, m.group(0), m.start(), m.end(),
                        CANDIDATE if is_data else DEFINITE, "inside a data record" if is_data else None)
        if is_data or is_code:
            # presence, not a census: one finding per member and kind of stamp
            ts = list(_TS_KEY_RE.finditer(text, 0, MAX_SUPP_DATA_DEEP_CHARS))
            if ts:
                hit(WARN, "run timestamps in %s" % ("data records" if is_data else "code literals"), ts[0].start(),
                    ts[0].end(), CANDIDATE, "%d field(s) like '%s'%s" % (
                        len(ts), ts[0].group(1), " in the first part of the member" if big_data else ""))
            ds = list(_DATE_STAMP_RE.finditer(text, 0, MAX_SUPP_DATA_DEEP_CHARS))
            if ds:
                hit(WARN, "date stamps in %s" % ("data records" if is_data else "code literals"), ds[0].start(),
                    ds[0].end(), CANDIDATE, "%d field(s) hold a calendar date" % len(ds))
        if not is_data:
            stamped = list(_LOG_TS_LINE_RE.finditer(text))
            if stamped:
                hit(WARN, "run timestamps in a log", stamped[0].start(), stamped[0].end(), CANDIDATE,
                    "%d line(s) start with a date and time" % len(stamped))
        tid = _TS_ID_RE.search(text, 0, MAX_SUPP_DATA_DEEP_CHARS)
        if tid:
            hit(WARN, "timestamp in an identifier", tid.start(), tid.end(), CANDIDATE)
        if not (is_data or is_log):
            told: List[Tuple[int, int, Any]] = []
            for rx in (_REVIEW_RE, _REVISION_RE, _SUPP_PROC_RE, _SUPP_NARRATION_RE):
                for m in rx.finditer(text):
                    if narrative(m.start()) and not _overlaps(told, m.start(), m.end()):
                        told.append((m.start(), m.end(), None))
                        hit(WARN, m.group(0), m.start(), m.end(), CANDIDATE)
            for m in _CLOCK_TZ_RE.finditer(text):
                if narrative(m.start()):
                    hit(WARN, m.group(0), m.start(), m.end(), DEFINITE, "clock time in a note")
            for m in _SUPP_DATE_RE.finditer(text):
                before = text[max(0, m.start() - 40):m.start()]
                # a range ("from 2099-01-02 to 2099-03-04", "2099-01-02..2099-03-04") is a
                # data window, which reproduction needs, not the authors' timeline
                in_range = bool(_DATE_RANGE_AFTER_RE.match(text, m.end()) or _DATE_RANGE_BEFORE_RE.search(before))
                # a data parameter ("cutoff = 2099-01-31") — unless one of the authors' own
                # process verbs sits between the keyword and the date ("records) — registered 2099-..")
                dctx = _DATA_DATE_CTX_RE.search(before)
                data_param = bool(dctx) and not _PROC_VERB_RE.search(before[dctx.start():])
                if narrative(m.start()) and not (in_range or _ACCESSED_RE.search(before) or _LITDATE_RE.search(before)
                                                 or data_param):
                    hit(WARN, m.group(0), m.start(), m.end(), CANDIDATE, "date in a note")
        # candidates in notes (READMEs, comments, docstrings; every line of a shell or
        # config file): one finding per member and kind, the first occurrence quoted
        shellish = is_code and bool(_SHELLISH_RE.search(member))

        def note_at(s: int) -> bool:
            return narrative(s) or shellish

        def first_note(rx: Any, why: str, label: str, sev: str = WARN, ok: Any = None, data_too: bool = False,
                       demoted: Optional[str] = None) -> None:
            found = [m for m in rx.finditer(text, 0, MAX_SUPP_DATA_DEEP_CHARS)
                     if ((data_too and is_data) or note_at(m.start())) and (ok is None or ok(m))]
            if found:
                n0 = len(out)
                hit(sev, label, found[0].start(), found[0].end(), CANDIDATE,
                    "%d occurrence(s) like '%s'; %s" % (len(found), _collapse_ws(found[0].group(0))[:60], why),
                    demoted=demoted)
                if len(out) > n0:
                    # the match is a label: the fix needs what was matched, and every line
                    keep_occurrences(out[-1], found)

        def keep_occurrences(f: Dict[str, Any], found: Sequence[Any]) -> None:
            f["matched"] = sorted({ctx.redactor.redact(_collapse_ws(m.group(0)))[:120] for m in found})[:50]
            f["lines"] = sorted({where(m.start())[0] for m in found})[:200]

        if not (is_log or big_data):
            first_note(_ENV_PREFIX_RE, "a machine's devices or threads in a command", "environment-variable prefix")
            first_note(_SHORT_HASH_RE, "a short hash names a commit or a file version", "short hash after commit/sha/hash",
                       ok=lambda m: _hex_ok(m.group(1)), data_too=True)
            # in the supplement a seed is reproduction detail: INFO, still a low-priority group for the reviewer
            first_note(_DATESEED_NUM_RE, "a seed shaped like a date tells when the study ran; reproduction may need "
                       "the value", "date-shaped seed in a note", sev=INFO, demoted="region",
                       ok=lambda m: bool(_SEED_WORD_RE.search(text[max(0, m.start() - 60):m.end() + 60])))
            if ctx.precision == "candidate":
                first_note(_PRECISION_RE, "policy precision_disclosure: candidate", "precision or loading detail")
            if ctx.reg_labels == "flag":
                first_note(_REGLABEL_ANY_RE, "policy registration_labels: flag", "registration label")
        if persisted:
            for tok, rx_tok in persisted:
                n_tok = len(rx_tok.findall(text, 0, MAX_SUPP_DATA_DEEP_CHARS))
                if n_tok:
                    ctx.codename_hits[tok] += n_tok
                    ctx.codename_where.setdefault(tok, []).append(member)
        if not big_data:
            scan_more(member, text, kind, low, where, narrative, note, editable)
        # what the reviewer reads besides the PDF: README-like documents, then the
        # notes of code members (comments, docstrings) and the head of each log
        red_member = ctx.redactor.redact(member)
        # (a member the review text budget leaves out, or cuts short, is recorded:
        # the coverage count never calls it reviewed)
        if is_doc:
            if st.docs_bytes < MAX_SUPP_DOCS_BYTES:
                full = ctx.redactor.redact(text)
                red = full[:MAX_SUPP_DOCS_BYTES - st.docs_bytes]
                st.docs.append((red_member, "doc", red))
                st.docs_bytes += len(red.encode("utf-8"))
                if len(red) < len(full.rstrip()):
                    st.review_cut.append(red_member)
            elif text.strip():
                st.review_left.append(red_member)
        elif is_data:
            st.review_scope["data records"] += 1
        elif (is_code or is_log) and not big_data:
            if is_code:
                body = "\n".join("L%d: %s" % (no, s) for no, s in _narrative_lines(text))
            else:
                body = "\n".join("L%d: %s" % (no, s) for no, s in enumerate(text.split("\n")[:40], 1) if s.strip())
            if not body.strip():
                st.review_scope["code or logs without a note line"] += 1
            elif st.notes_bytes < MAX_SUPP_NOTES_BYTES:
                budget_left = min(MAX_SUPP_NOTES_PER_MEMBER, MAX_SUPP_NOTES_BYTES - st.notes_bytes)
                full = ctx.redactor.redact(body)
                red = full[:budget_left]
                if red.strip():
                    st.docs.append((red_member, "notes" if is_code else "log head", red))
                    st.notes_bytes += len(red.encode("utf-8"))
                if len(red) < len(full):
                    if budget_left < MAX_SUPP_NOTES_PER_MEMBER:
                        st.review_cut.append(red_member)   # the total budget ran out inside this member
                    else:
                        st.review_partial += 1             # the per-member limit (a long comment block)
            else:
                st.review_left.append(red_member)

    def scan_pdf_member(member: str, data: bytes) -> None:
        try:
            doc = parse_pdf_objects(data)
        except Exception:  # noqa: BLE001 — a broken figure PDF is reported, never fatal
            emit("SUPP-UNSCANNED", INFO, member, "PDF member could not be parsed", member)
            return
        for f in scan_pdf_bytes(doc, ctx, artifact):
            emit("SUPP-TEXT", BLOCK, f["_raw"], "PDF member bytes: " + f["excerpt"], member)
        if ctx.on("META-FIGURE"):
            for key, val in figure_meta_issues(pdf_info(doc), ctx.anonymous):
                emit("META-FIGURE", WARN if ctx.anonymous else INFO, "%s=%s" % (key, val[:120]),
                     "PDF member Info /%s" % key, member)

    def handle_member(member: str, data: bytes, depth: int) -> None:
        low = member.lower()
        if capture is not None and not (_is_archive_name(low) and depth < MAX_SUPP_DEPTH):
            capture.setdefault("hashes", {})[member] = _sha256_bytes(data)
            texts = capture.setdefault("texts", {})
            if (len(data) <= SNAPSHOT_MEMBER_MAX and capture.get("_bytes", 0) + len(data) <= SNAPSHOT_TOTAL_MAX
                    and not low.endswith(".pdf") and (low.endswith(_TEXT_EXTS) or _looks_text(data[:4096]))):
                texts[member] = data
                capture["_bytes"] = capture.get("_bytes", 0) + len(data)
        if _is_archive_name(low) and depth < MAX_SUPP_DEPTH:
            for ext, kind in ((".gz", "gz"), (".xz", "xz")):
                if low.endswith(ext) and not low.endswith((".tar" + ext, ".tgz", ".txz")):
                    if kind == "gz":
                        hdr = _gzip_header(data)
                        if hdr:
                            gzip_header_check(member, hdr)
                    inner, status = _bounded_decompress(data, kind, MAX_SUPP_MEMBER_BYTES)
                    if inner is None:
                        emit("SUPP-INTEGRITY", BLOCK, member, "corrupt %s member" % kind, member)
                        return
                    if status == "truncated":
                        emit("SUPP-INTEGRITY", BLOCK, member, "truncated %s stream" % kind, member)
                    elif status == "limit":
                        emit("SUPP-UNSCANNED", INFO, member, "decompressed size above the member limit", member)
                    if budget(len(inner), member):
                        handle_member(member[:-len(ext)], inner, depth + 1)
                    return
            walk_archive(io.BytesIO(data), member, depth + 1, data)
            return
        if _is_archive_name(low):
            emit("SUPP-UNSCANNED", INFO, member, "nested deeper than %d archives" % MAX_SUPP_DEPTH, member)
            return
        if low.endswith(".pdf"):
            scan_pdf_member(member, data)
            return
        if low.endswith(_TEXT_EXTS) or _looks_text(data[:4096]):
            scan_text_member(member, data)

    def gzip_header_check(member: str, hdr: Dict[str, Any]) -> None:
        for key, what in (("fname", "file name"), ("comment", "comment")):
            if hdr.get(key):
                emit("SUPP-GZIP", BLOCK if ident_in(hdr[key]) else WARN, "gzip %s" % key.upper(),
                     "the header stores a %s: %s" % (what, hdr[key][:120]), member)
        if hdr.get("mtime"):
            emit("SUPP-GZIP", WARN, "gzip MTIME", "the header stores a modification time", member)

    def read_limited(size: int, member: str, opener: Any) -> Optional[bytes]:
        if size > MAX_SUPP_MEMBER_BYTES:
            emit("SUPP-UNSCANNED", INFO, member, "member larger than %d MB" % (MAX_SUPP_MEMBER_BYTES // 1048576), member)
            return None
        if st.total + size > MAX_SUPP_TOTAL_BYTES:
            emit("SUPP-UNSCANNED", INFO, member, "total scanned bytes above the archive limit", member)
            return None
        try:
            data = opener()
        except (zipfile.BadZipFile, zlib.error, lzma.LZMAError, EOFError, OSError, tarfile.TarError) as e:
            emit("SUPP-INTEGRITY", BLOCK, member, "member unreadable (%s)" % type(e).__name__, member)
            return None
        except (RuntimeError, NotImplementedError) as e:  # encrypted member / unsupported method
            emit("SUPP-UNSCANNED", INFO, member, "member not scannable (%s)" % type(e).__name__, member)
            return None
        st.total += len(data)
        return data

    def walk_archive(fobj: Any, label: str, depth: int, raw: Optional[bytes] = None) -> None:
        prefix = (label + "!/") if depth > 0 else ""
        ckey = label if depth > 0 else ""  # the container's key in the change review's name list
        head = raw[:6] if raw is not None else _peek(fobj, 6)
        if head[:2] == b"PK":
            try:
                zf = zipfile.ZipFile(fobj)
            except (zipfile.BadZipFile, OSError, ValueError):
                st.unreadable.append(label)
                emit("SUPP-INTEGRITY", BLOCK, label, "not a readable zip", label)
                note_opened(ckey, False)
                return
            with zf:
                # no testzip(): it inflates every member, including the ones
                # skipped below for size; each read member is CRC-checked by read()
                if zf.comment:
                    emit("SUPP-META", WARN, "zip comment", repr(zf.comment[:60]), label)
                stamps, extras, n_files = [], set(), 0
                # the central directory names every member, read or not
                for zi in zf.infolist():
                    if not zi.is_dir():
                        note_listed(prefix + zi.filename.replace("\\", "/"), ckey, depth)
                note_opened(ckey, True)
                for zi in zf.infolist():
                    if zi.is_dir():
                        continue
                    name = zi.filename.replace("\\", "/")  # old Windows packers store backslashes
                    n_files += 1
                    check_name(prefix + name)
                    stamps.append(zi.date_time)
                    for hid in _zip_extra_ids(zi.extra):
                        if hid in (0x5455, 0x7875, 0x000D, 0x5855):
                            extras.add(hid)
                    data = read_limited(zi.file_size, prefix + name, lambda zi=zi: zf.read(zi))
                    if data is not None:
                        handle_member(prefix + name, data, depth)
                real = [s for s in stamps if s != (1980, 1, 1, 0, 0, 0)]
                if real:  # even one shared real date says when the archive was packed
                    emit("SUPP-META", WARN, "real member timestamps",
                         "%d of %d member(s) carry a real date" % (len(real), n_files), label)
                if extras:
                    emit("SUPP-META", WARN, "zip extra fields", "extra field ids: %s" % ", ".join("0x%04X" % x for x in sorted(extras)), label)
            return
        if raw is not None and raw[:2] == b"\x1f\x8b" and depth > 0:
            hdr = _gzip_header(raw)
            if hdr:
                gzip_header_check(label, hdr)
        elif raw is None and head[:2] == b"\x1f\x8b":
            with contextlib.suppress(OSError):
                with open(path, "rb") as fh:
                    hdr = _gzip_header(fh.read(4096))
                if hdr:
                    gzip_header_check(label, hdr)
        try:
            # streaming mode: one sequential pass, never a full getmembers()
            # decompression before the size limits apply
            tf = tarfile.open(fileobj=fobj, mode="r|*")
        except (tarfile.TarError, OSError, EOFError, ValueError, zlib.error, lzma.LZMAError):
            st.unreadable.append(label)
            emit("SUPP-INTEGRITY", BLOCK, label, "not a readable zip or tar archive", label)
            note_opened(ckey, False)
            return
        owners, ids, mtimes = set(), set(), set()
        declared = 0
        complete = False
        try:
            with tf:
                for ti in tf:
                    if not ti.isfile():
                        continue
                    name = ti.name.replace("\\", "/")
                    check_name(prefix + name)
                    note_listed(prefix + name, ckey, depth)
                    if ti.uname or ti.gname:
                        owners.add((ti.uname, ti.gname))
                    if ti.uid or ti.gid:
                        ids.add((ti.uid, ti.gid))
                    mtimes.add(ti.mtime)
                    declared += ti.size
                    if declared > 2 * MAX_SUPP_TOTAL_BYTES:
                        emit("SUPP-UNSCANNED", INFO, label, "archive larger than the scan budget; the rest was not read", label)
                        break

                    def opener(ti: Any = ti) -> bytes:
                        fh = tf.extractfile(ti)
                        return fh.read() if fh else b""
                    data = read_limited(ti.size, prefix + name, opener)
                    if data is not None:
                        handle_member(prefix + name, data, depth)
                else:
                    complete = True  # a tar names its members as it is read: only a full pass lists them all
        except (tarfile.TarError, OSError, EOFError, zlib.error, lzma.LZMAError):
            emit("SUPP-INTEGRITY", BLOCK, label, "truncated or corrupt tar", label)
            note_opened(ckey, False)
            if not mtimes:
                st.unreadable.append(label)
                return
        else:
            note_opened(ckey, complete)
        for un, gn in sorted(owners):
            ident = any(ident_in(x) for x in (un, gn) if x)
            emit("SUPP-TAR", BLOCK if ident else WARN, "tar owner names", "uname=%s gname=%s" % (un, gn), label)
        if ids:
            emit("SUPP-TAR", WARN, "tar uid/gid", "numeric owners: %s" % ", ".join("%d/%d" % x for x in sorted(ids)[:5]), label)
        if any(mtimes):
            emit("SUPP-TAR", WARN, "tar mtimes", "%d distinct member mtimes" % len(mtimes), label)

    if os.path.isdir(path):
        for root, dirs, files in os.walk(path):
            dirs.sort()
            keep = []
            for d in dirs:
                rel_d = _rel(os.path.join(root, d), path) + "/"
                if _JUNK_BLOCK_RE.search(rel_d) or _JUNK_WARN_RE.search(rel_d) or _ARIS_RE.search(rel_d):
                    check_name(rel_d)  # report the directory once; do not descend
                else:
                    keep.append(d)
            dirs[:] = keep
            for fn in sorted(files):
                full = os.path.join(root, fn)
                member = _rel(full, path)
                check_name(member)
                note_listed(member, "", 0)
                try:
                    size = os.path.getsize(full)
                except OSError:
                    continue

                def opener(full: str = full) -> bytes:
                    with open(full, "rb") as fh:
                        return fh.read()
                data = read_limited(size, member, opener)
                if data is not None:
                    handle_member(member, data, 0)
        note_opened("", True)
    else:
        with open(path, "rb") as fh:
            walk_archive(fh, artifact, 0)
    _resolve_supp_refs(refs, names_seen, emit, ctx)
    # code-name candidates: titles, project names in code, the archive's top folder,
    # Python package folders, /path/to/<name> placeholders
    tops = {n.split("/", 1)[0] for n in names_seen if "/" in n}
    if len(tops) == 1 and all("/" in n for n in names_seen):
        # the top folder without its generic words: "<name>_supplementary" names <name>
        parts = [p for p in re.split(r"[_.-]+", next(iter(tops))) if p and p.lower() not in _GENERIC_NAMES
                 and p.lower() not in _GENERIC_PARTS]
        top = "_".join(parts)
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{2,30}", top) and top.lower() not in _GENERIC_NAMES:
            codenames[top] += 1
            structural_names.add(top)
    # only a top-level package names the project: a sub-package names a module
    # (pkg/oracle/), and vendored code (third_party/, vendor/) carries other people's names
    init_dirs = {n.rsplit("/", 1)[0] for n in names_seen if n.endswith("/__init__.py") and "!/" not in n}
    for d in sorted(init_dirs):
        if (d.rsplit("/", 1)[0] if "/" in d else "") in init_dirs or _VENDORED_DIR_RE.search(d):
            continue
        pkg = d.rsplit("/", 1)[-1]
        if (re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{2,30}", pkg) and pkg.lower() not in _GENERIC_NAMES
                and pkg.lower() not in _GENERIC_PACKAGES):
            codenames[pkg] += 1
            structural_names.add(pkg)
    if codenames:
        texts_low = [t.lower() for _m, _k, t in st.docs]
        cand: Dict[str, int] = {}
        for tok in codenames:
            rx = re.compile(r"(?<![A-Za-z0-9])%s(?![A-Za-z0-9])" % re.escape(tok.lower()))
            cand[tok] = (sum(1 for n in names_seen if rx.search(n.lower()))
                         + sum(1 for t in texts_low if rx.search(t)))
        info["codename_candidates"] = cand
        info["codename_structural"] = sorted(structural_names & set(cand))
    if persisted:
        for tok, rx_tok in persisted:
            n_names = [n for n in names_seen if rx_tok.search(n)]
            if n_names:
                ctx.codename_hits[tok] += len(n_names)
                ctx.codename_where.setdefault(tok, []).extend(n_names[:3])
    info["unreadable"] = bool(st.unreadable) and any(u == artifact for u in st.unreadable)
    if st.shallow:
        info["shallow_data_members"] = st.shallow
    if st.review_left or st.review_cut or st.review_partial:
        # notes the reviewer never reads in full: the coverage count holds them as not covered
        info["review_left_out"] = st.review_left[:200]
        info["review_left_out_n"] = len(st.review_left)
        info["review_cut"] = st.review_cut[:200]
        info["review_partial"] = st.review_partial
    if st.review_scope:
        info["review_scope_out"] = dict(sorted(st.review_scope.items()))
    info["docs"] = st.docs
    return out, info


SNAPSHOT_MEMBER_MAX = 4 * 1024 * 1024    # text members kept for the change review
SNAPSHOT_TOTAL_MAX = 128 * 1024 * 1024
_TOOL_VERSION_RE = re.compile(r"\d+\.\d+")


def figure_meta_issues(info: Dict[str, str], anonymous: bool) -> List[Tuple[str, str]]:
    """The fields of a figure's Info dictionary that say who made it, with which
    tool version, or in which time zone."""
    out = []
    for key in ("Author", "Creator", "Producer"):
        v = _collapse_ws(info.get(key) or "")
        if not v:
            continue
        if key == "Author":
            if anonymous:
                out.append((key, v))
        elif _TOOL_VERSION_RE.search(v):
            out.append((key, v))
    for key in ("CreationDate", "ModDate"):
        v = info.get(key) or ""
        if _tz_nonutc(v):
            out.append((key, v))
    return out


def _resolve_supp_refs(refs: List[Tuple[str, str, str, int, str, str]], names: List[str], emit: Any,
                       ctx: ScanContext) -> None:
    """SUPP-PATH dangling references: a script the package does not contain,
    a code note's path into a directory the package does not contain."""
    if not ctx.on("SUPP-PATH") or not names:
        return
    bases = {n.rsplit("/", 1)[-1] for n in names}
    dirs: Set[str] = set()
    roots: Set[str] = set()  # the package layout: the first two folder levels
    full_paths = {n.rstrip("/") for n in names}
    full_dirs: Set[str] = set()
    for n in names:
        parts = [p for p in n.split("/")[:-1] if p]
        dirs.update(parts)
        roots.update(parts[:2])
        for i in range(1, len(parts) + 1):
            full_dirs.add("/".join(parts[:i]))
    seen: Set[Tuple[str, str]] = set()
    for rk, ref, member, line, excerpt, kind in refs:
        base = ref.rsplit("/", 1)[-1]
        sev, why = WARN, None
        if rk == "relpath":
            # relative to the file, to the package's top folder, or to the archive root
            mdir = posixpath.dirname(member)
            top = member.split("/", 1)[0] if "/" in member else ""
            targets = {posixpath.normpath(posixpath.join(d, ref)) for d in {mdir, top, ""}}
            if any(t_ in full_paths or t_ in full_dirs for t_ in targets):
                continue
            label, sev, why = ("relative path resolves to nothing in the package: %s" % ref.rstrip("/")[:80], INFO,
                               "a path in a code literal; the code may create it, or it points to a folder that "
                               "was renamed or never shipped")
            if (label, member) in seen:
                continue
            seen.add((label, member))
            emit("SUPP-PATH", sev, label, excerpt, member, line, CANDIDATE, why, kind=kind)
            continue
        if rk in ("script", "script_cmd"):
            top = ref.split("/", 1)[0] if "/" in ref else None
            external = bool(top) and (top in _EXTERNAL_DIRS or (rk == "script" and top not in roots))
            if (base in bases or base in _COMMON_SCRIPTS or external or _EXTERNAL_NOTE_RE.search(excerpt)
                    or _DEPENDENCY_DOC_RE.search(member.rsplit("/", 1)[-1]) or _VENDOR_PATH_RE.search(member)):
                continue  # shipped, or a file of another package ("vendor/x/y.py", a dependency list, a shim)
            label = "script not in the package: %s" % base
        else:
            top = ref.split("/", 1)[0]
            if top in dirs or top in (".", ".."):
                continue
            # often an output the code writes, or a template: INFO for a person, never reviewed
            label, sev, why = ("path into a directory not in the package: %s/" % top, INFO,
                               "may be an output the code writes; check the folder is not an internal one")
        if (label, member) in seen:
            continue
        seen.add((label, member))
        emit("SUPP-PATH", sev, label, excerpt, member, line, CANDIDATE, why, kind=kind)


def _peek(fobj: Any, n: int) -> bytes:
    pos = fobj.tell()
    data = fobj.read(n)
    fobj.seek(pos)
    return data


# ─── Numbers (NUM-DRIFT) ─────────────────────────────────────────────────────

_NUM_REFS_RE = re.compile(r"(?:Figures?|Figs?\.|Tables?|Tabs?\.|Sections?|Secs?\.|§|Appendix|App\.|Eqs?\.|Equations?|"
                          r"Theorems?|Lemmas?|Corollary|Propositions?|Definitions?|Algorithms?|Lines?|Steps?|Examples?|"
                          r"Remarks?|Assumptions?|Chapters?|Parts?)\s*~?\(?\s*[A-Z]?\d+(?:\.\d+)*\)?", re.I)
_NUM_CITE_RE = re.compile(r"\[\d+(?:\s*[,–-]\s*\d+)*\]|\b(?:et al\.|and [A-Z][\w-]+|[A-Z][\w-]+),?\s*\(?(?:19|20)\d\d[a-z]?\)?|"
                          r"\((?:[^()]{0,80}?\b(?:19|20)\d\d[a-z]?[;,]?)+\)")
_NUM_EQNO_RE = re.compile(r"\(\d{1,3}\)")
_NUM_TOKEN_RE = re.compile(r"(?<![\w.])[-−]?\d+(?:[.,]\d+)*%?(?![\w])")


def _number_tokens(text: str) -> List[str]:
    """The numbers NUM-DRIFT counts in a piece of text (no figure, section,
    equation, or citation numbers)."""
    t = _NUM_REFS_RE.sub(" ", text)
    t = _NUM_CITE_RE.sub(" ", t)
    t = _NUM_EQNO_RE.sub(" ", t)
    return [tok for tok in (m.group(0).replace("−", "-").rstrip(".,") for m in _NUM_TOKEN_RE.finditer(t)) if tok]


def _counted_segs(page: Dict[str, Any]) -> List[str]:
    return [s["text"] for s in page["segs"]
            if s["kind"] == "body" and s.get("region") not in ("references", "checklist") and not s.get("heading")]


def number_multiset(pages: List[Dict[str, Any]]) -> Counter:
    """Numbers in body/appendix/end-matter text, without figure/section/equation
    numbers, citations, headings, page and line numbers."""
    c: Counter = Counter()
    for p in pages:
        for text in _counted_segs(p):
            c.update(_number_tokens(text))
    return c


def number_multiset_all(pages: List[Dict[str, Any]]) -> Counter:
    """The same numbers over the whole body text, references and checklist
    included: a number that only moved between regions (a float placed after
    the references) changes number_multiset but not this one."""
    c: Counter = Counter()
    for p in pages:
        for s in p["segs"]:
            if s["kind"] == "body" and not s.get("heading"):
                c.update(_number_tokens(s["text"]))
    return c


def number_text(pages: List[Dict[str, Any]], ctx: ScanContext) -> Dict[str, str]:
    """{page: redacted text} of the segments number_multiset counts: frozen at
    round 0 of a fix loop so that a later round can quote where a number left."""
    out = {}
    for p in pages:
        parts = _counted_segs(p)
        if parts:
            out[str(p["page"])] = ctx.redactor.redact(" ".join(parts))
    return out


_CLAUSE_DELIM_RE = re.compile(r"[.!?;:,](?=\s)|[。；！？，]")


def _clause_bounds(text: str, s: int, e: int) -> Tuple[int, int]:
    left = 0
    for m in _CLAUSE_DELIM_RE.finditer(text, 0, s):
        left = m.end()
    m = _CLAUSE_DELIM_RE.search(text, e)
    return left, (m.start() if m else len(text))


_SENT_BOUND_RE = re.compile(r"(?<=[.!?。！？])\s+")


def _sentence_bounds(text: str, s: int, e: int) -> Tuple[int, int]:
    left = 0
    for m in _SENT_BOUND_RE.finditer(text, 0, s):
        left = m.end()
    m = _SENT_BOUND_RE.search(text, e)
    return left, (m.start() if m else len(text))


def clause_explained(base_pages: Dict[int, str], cur_pages: Dict[int, str],
                     base_findings: Sequence[Dict[str, Any]], sentence: bool = False
                     ) -> Tuple[Counter, Dict[str, Tuple[int, str]]]:
    """Numbers that left together with a clause that held a baseline finding
    (a deleted clock time, version, launch or hardware detail) and is gone from
    the current text. With `sentence` (the finding was a confirmed leak), the
    whole sentence counts when it is gone. Returns the counts and, per token,
    the page and clause."""
    cur_norm = _norm_quote(" ".join(cur_pages[k] for k in sorted(cur_pages)))
    counts: Counter = Counter()
    where: Dict[str, Tuple[int, str]] = {}
    seen: Set[Tuple[int, int, int]] = set()
    for f in base_findings:
        pg = (f.get("location") or {}).get("page")
        text = base_pages.get(pg) if pg else None
        m = str(f.get("match") or "").strip()
        if not text or len(m) < 2:
            continue
        i = text.find(m)
        if i < 0:
            continue
        s, e = _clause_bounds(text, i, i + len(m))
        if sentence:
            s2, e2 = _sentence_bounds(text, i, i + len(m))
            if _norm_quote(text[s2:e2]) not in cur_norm:
                s, e = s2, e2
        if (pg, s, e) in seen:
            continue
        seen.add((pg, s, e))
        clause = text[s:e].strip()
        if not clause or _norm_quote(clause) in cur_norm:
            continue  # the clause (and its numbers) is still there
        for tok in _number_tokens(clause):
            counts[tok] += 1
            where.setdefault(tok, (pg, clause[:200]))
    return counts, where


def drift_context(token: str, change: str, base_pages: Dict[int, str], cur_pages: Dict[int, str]
                  ) -> Optional[Tuple[int, str]]:
    """(page, sentence) where a drifting number left (removed: a baseline
    sentence gone from the current text) or arrived (added: a new sentence)."""
    src, other = (base_pages, cur_pages) if change == "removed" else (cur_pages, base_pages)
    other_norm = _norm_quote(" ".join(other[k] for k in sorted(other)))
    for pg in sorted(src):
        for sent in _SENT_SPLIT_RE.split(src[pg]):
            sent = sent.strip()
            if sent and token in _number_tokens(sent) and _norm_quote(sent) not in other_norm:
                return pg, sent[:200]
    return None


def number_drift(baseline: Counter, current: Counter, explained: Counter) -> List[Dict[str, Any]]:
    out = []
    removed = baseline - current
    added = current - baseline
    for tok, n in sorted(removed.items()):
        n_unexplained = n - min(n, explained.get(tok, 0))
        if n_unexplained > 0:
            out.append({"token": tok, "change": "removed", "n": n_unexplained})
    for tok, n in sorted(added.items()):
        out.append({"token": tok, "change": "added", "n": n})
    for d in out:
        d["certainty"] = DEFINITE if ("." in d["token"] or "%" in d["token"]) else CANDIDATE
    return out


# ─── Allow-list, grouping, verdict ───────────────────────────────────────────

def _where_ok(where: Optional[Dict[str, Any]], f: Dict[str, Any]) -> bool:
    if not where:
        return True
    loc = f["location"]
    if "page" in where:
        return loc.get("page") in where["page"]
    if "file" in where:
        return (loc.get("file") or "") == where["file"] and (where.get("line") is None or loc.get("line") == where["line"])
    return bool(loc.get("member")) and fnmatch.fnmatchcase(loc["member"], where["member"])


def apply_allow(findings: List[Dict[str, Any]], entries: List[Dict[str, Any]], ctx: ScanContext
                ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Exempt matching findings. A definite finding accepts only human:
    provenance; candidates accept human: or cross-family-review:. A line with
    a `where` column applies only at those locations. Every exemption is
    recorded (with the severity it removed) in exemptions_applied."""
    applied, refused = [], []
    for f in findings:
        if f["check"].startswith(("SKIP-", "ALLOW-", "CONFIG-")) or f["check"] in NON_EXEMPTABLE:
            continue
        for e in entries:
            if not fnmatch.fnmatchcase(f["check"], e["check_glob"]):
                continue
            if not (e["_rx"].search(f.get("_raw", "")) or e["_rx"].search(f["_key"])):
                continue
            if not _where_ok(e.get("where"), f):
                continue
            if f["certainty"] == DEFINITE and not e["approved_by"].startswith("human:"):
                refused.append({"line": e["line"], "finding": f["check"],
                                "problem": "a definite finding can only be exempted by human: provenance"})
                continue
            e["used"] += 1
            f["exempted_by"] = e["approved_by"]
            f["original_severity"] = f["severity"]
            f["severity"] = INFO
            applied.append({"line": e["line"], "check": f["check"], "approved_by": e["approved_by"],
                            "removed_severity": f["original_severity"], "reason": ctx.redactor.redact(e["reason"])})
            break
    return applied, refused


def _group_bucket(f: Dict[str, Any]) -> str:
    """Findings of one check and match are ruled together only within one
    region and section: 'A100' in related work and 'A100' in the setup are
    different questions for the reviewer."""
    return "%s/%s" % (f.get("region") or "", f.get("subregion") or "")


def group_findings(findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Stable ids (<CHECK>-NNN) and groups (G-NNN) per (check, match, certainty, region/section)."""
    def loc_key(f: Dict[str, Any]) -> Tuple[Any, ...]:
        loc = f["location"]
        return (f["check"], loc.get("artifact") or "", loc.get("page") or 0, loc.get("file") or "",
                loc.get("line") or 0, loc.get("member") or "", f["_key"])
    findings.sort(key=loc_key)
    per: Counter = Counter()
    for f in findings:
        per[f["check"]] += 1
        f["id"] = "%s-%03d" % (f["check"], per[f["check"]])
    keys = sorted({(f["check"], f["_key"], f["certainty"], _group_bucket(f)) for f in findings})
    gid = {k: "G-%03d" % i for i, k in enumerate(keys, 1)}
    groups: Dict[str, Dict[str, Any]] = {}
    for f in findings:
        k = (f["check"], f["_key"], f["certainty"], _group_bucket(f))
        g = groups.get(gid[k])
        if g is None:
            g = groups[gid[k]] = {"group": gid[k], "check": f["check"], "family": f["family"], "match": f["match"],
                                  "n": 0, "certainty": f["certainty"], "severity": f["severity"],
                                  "region": f.get("region"), "subregion": f.get("subregion"), "pages": [], "ids": [],
                                  "key": stable_key(f["check"], f["match"], f.get("region"), f.get("subregion"))}
        f["group"] = gid[k]
        g["n"] += 1
        g["severity"] = _sev_max(g["severity"], f["severity"])
        g["ids"].append(f["id"])
        pg = f["location"].get("page")
        if pg and pg not in g["pages"]:
            g["pages"].append(pg)
    return [groups[k] for k in sorted(groups)]


# ─── Cross-round memory: stable keys, rulings ledger, fix state ──────────────

LEDGER_NAME = "rulings_ledger.json"      # every reviewer ruling, per stable key, across rounds and runs
STATE_NAME = "last_fix_state.json"       # what the latest fix round left: queue, stops, reviewer findings, code names


def stable_key(check: Any, match: Any, region: Any = None, sub: Any = None) -> str:
    """A finding group's identity across rounds and runs (G-NNN ids are
    renumbered on every scan): the check, the redacted match, the section."""
    raw = "|".join((str(check or ""), _norm_key(str(match or "")), str(region or ""), str(sub or "")))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _load_json(path: Optional[str]) -> Optional[Any]:
    if not path or not os.path.isfile(path):
        return None
    try:
        return json.loads(_read_text(path))
    except (OSError, ValueError):
        return None


def load_ledger(work_dir: Optional[str]) -> Dict[str, Any]:
    data = _load_json(os.path.join(work_dir, LEDGER_NAME)) if work_dir else None
    if not isinstance(data, dict) or not isinstance(data.get("entries"), dict):
        return {"version": 1, "entries": {}}
    return data


def _decisive(ruling: Any) -> bool:
    return ruling in CONFIRMED_RULINGS or ruling in CLEARING_RULINGS


def _ruling_class(ruling: Any) -> Optional[str]:
    return "confirm" if ruling in CONFIRMED_RULINGS else "clear" if ruling in CLEARING_RULINGS else None


def prior_decision(ledger: Dict[str, Any], key: str, run_label: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """The latest decisive ruling (leak, reword, necessary, false_positive) an
    earlier run gave this stable key; `uncertain` binds nobody."""
    entry = (ledger.get("entries") or {}).get(key) or {}
    for r in reversed(entry.get("rulings") or []):
        if run_label and r.get("run") == run_label:
            continue
        if _decisive(r.get("ruling")):
            return r
    return None


def prior_rulings_for_review(ledger: Dict[str, Any], key: str, limit: int = 3) -> List[Dict[str, Any]]:
    entry = (ledger.get("entries") or {}).get(key) or {}
    out = [{"run": r.get("run"), "ruling": r.get("ruling"), "rationale": str(r.get("rationale") or "")[:300]}
           for r in entry.get("rulings") or [] if _decisive(r.get("ruling"))]
    return out[-limit:]


def confirmed_ledger_keys(ledger: Dict[str, Any]) -> Set[str]:
    return {k for k, e in (ledger.get("entries") or {}).items()
            if any(r.get("ruling") in CONFIRMED_RULINGS for r in e.get("rulings") or [])}


def _counts(findings: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    """Severity counts of real findings; SKIP-<CHECK> records (a check that
    could not run) and SUPP-COVERAGE (supplementary notes no reviewer read in
    full, also a WARN finding) count as coverage gaps, as the `coverage_gap`
    reason does; `exempted_block` counts BLOCK findings an allow-list line
    turned into INFO."""
    c = {BLOCK: 0, WARN: 0, INFO: 0, "coverage_gaps": 0, "exempted_block": 0}
    for f in findings:
        if f["check"].startswith("SKIP-"):
            c["coverage_gaps"] += 1
        else:
            c[f["severity"]] += 1
            if f["check"] == "SUPP-COVERAGE" and f["severity"] != INFO:
                c["coverage_gaps"] += 1
            if f.get("exempted_by") and f.get("original_severity") == BLOCK:
                c["exempted_block"] += 1
    return c


def decide_verdict(findings: List[Dict[str, Any]], blocked: Sequence[str], skipped: Sequence[Dict[str, Any]],
                   strict: bool, review_status: str = "skipped", nothing: bool = False) -> Tuple[str, str]:
    """The decision table (first matching row wins)."""
    if nothing:
        return "NOT_APPLICABLE", "nothing_to_audit"
    for code in ("pdf_missing", "pdf_unreadable", "stale_pdf"):
        if code in blocked:
            return "BLOCKED", code
    live = [f for f in findings if not f.get("exempted_by")]
    blocking = [f for f in live if f["severity"] == BLOCK]
    promoted = [f for f in live if strict and f["severity"] == WARN and not f["check"].startswith("SKIP-")]
    if blocking or promoted:
        reasons = {REASON_BY_FAMILY.get(f["family"]) for f in blocking}
        for code in REASON_PRIORITY:
            if code in reasons:
                return "FAIL", code
        return "FAIL", "strict_warnings"
    for code in ("pdf_text_backend_missing", "pdf_text_empty", "supp_unreadable"):
        if code in blocked:
            return "BLOCKED", code
    if review_status == "error":
        return "ERROR", "reviewer_error"
    if review_status == "malformed":
        return "ERROR", "reviewer_output_malformed"
    if review_status == "unavailable":
        return "BLOCKED", "reviewer_unavailable"
    warns = [f for f in live if f["severity"] == WARN]
    gap = any(s.get("cap") in ("WARN", "BLOCKED") for s in skipped)
    if warns or gap:
        return "WARN", _warn_reasons(warns, gap)[0]
    return "PASS", "clean"


def _warn_kinds(f: Dict[str, Any]) -> List[str]:
    """The WARN reasons a WARN finding stands for (WARN_REASONS order)."""
    out: List[str] = []
    if f.get("ruling_flip"):
        return ["ruling_flip"]  # contested: neither confirmed nor cleared until a person decides
    if f.get("ruling") in CONFIRMED_RULINGS or (f.get("ruling") == "reviewer_finding"
                                                and f.get("reviewer_severity") == "blocking"):
        out.append("confirmed_leaks")  # a leak a reviewer confirmed (its level is WARN): never advisory
    if f.get("carried_from") and not (f.get("layer") == "review" and f.get("reviewer_severity") != "blocking"):
        out.append("carried_over")  # (carried advice stays advice: listed, never a hold on upload)
    if out:
        return out
    if f["certainty"] == CANDIDATE and f.get("ruling") in (None, "unreviewed"):
        return ["unreviewed_candidates"]
    if f["check"] == "ANON-LIST-MISSING":
        return ["identity_list_missing"]
    if f["check"].startswith("SKIP-") or f["check"] == "SUPP-COVERAGE":
        return ["coverage_gap"]
    return ["advisory_only"]


def _warn_reasons(warns: List[Dict[str, Any]], gap: bool) -> List[str]:
    """WARN reasons, most substantive first: a leak the reviewer confirmed (its
    configured level is WARN) is never 'advisory only', a ruling that flipped
    without new evidence or an item carried over from the fix run is held for
    a person, and a missing identity list must not hide any of them."""
    kinds = {k for f in warns for k in _warn_kinds(f)}
    if gap:
        kinds.add("coverage_gap")
    out = [r for r in WARN_REASONS if r in kinds]
    return out or ["advisory_only"]


def verdict_reasons(findings: List[Dict[str, Any]], blocked: Sequence[str], skipped: Sequence[Dict[str, Any]],
                    strict: bool, review_status: str = "skipped", nothing: bool = False) -> List[str]:
    """Every reason that applies, in decision-table order — reason_code names
    only the first, which must never be the only thing a reader learns (a FAIL
    for a missing citation can sit on top of a supplement leak)."""
    if nothing:
        return ["nothing_to_audit"]
    out = [c for c in ("pdf_missing", "pdf_unreadable", "stale_pdf") if c in blocked]
    live = [f for f in findings if not f.get("exempted_by")]
    fams = {REASON_BY_FAMILY.get(f["family"]) for f in live if f["severity"] == BLOCK}
    out += [c for c in REASON_PRIORITY if c in fams]
    # a blocking finding kept by the conservative rule, or carried over from the fix run
    out += [c for c, flag in (("ruling_flip", "ruling_flip"), ("carried_over", "carried_from"))
            if any(f["severity"] == BLOCK and f.get(flag) for f in live)]
    if strict and any(f["severity"] == WARN and not f["check"].startswith("SKIP-") for f in live):
        out.append("strict_warnings")
    out += [c for c in ("pdf_text_backend_missing", "pdf_text_empty", "supp_unreadable") if c in blocked]
    out += {"error": ["reviewer_error"], "malformed": ["reviewer_output_malformed"],
            "unavailable": ["reviewer_unavailable"]}.get(review_status, [])
    warns = [f for f in live if f["severity"] == WARN]
    gap = any(s.get("cap") in ("WARN", "BLOCKED") for s in skipped)
    if warns or gap:
        out += _warn_reasons(warns, gap)
    return list(dict.fromkeys(out)) or ["clean"]


def tier_a_verdict(findings: List[Dict[str, Any]], blocked: Sequence[str], skipped: Sequence[Dict[str, Any]],
                   strict: bool, nothing: bool = False) -> Tuple[str, str]:
    """Verdict of the deterministic scan alone (candidates are unreviewed)."""
    return decide_verdict(findings, blocked, skipped, strict, "skipped", nothing)


def final_verdict(findings: List[Dict[str, Any]], blocked: Sequence[str], skipped: Sequence[Dict[str, Any]],
                  strict: bool, review_status: str, nothing: bool = False) -> Tuple[str, str]:
    """Verdict after the reviewer's rulings were merged (same decision table)."""
    return decide_verdict(findings, blocked, skipped, strict, review_status, nothing)


def _summary_line(verdict: str, reason: str, counts: Dict[str, int], n_groups: int,
                  reasons: Optional[Sequence[str]] = None) -> str:
    gaps = counts.get("coverage_gaps", 0)
    ex = counts.get("exempted_block", 0)
    others = [r for r in (reasons or []) if r != reason]
    return "%s (%s): %d blocking, %d advisory, %d info finding(s) in %d group(s)%s%s%s." % (
        verdict, reason, counts.get(BLOCK, 0), counts.get(WARN, 0), counts.get(INFO, 0), n_groups,
        "; %d coverage gap(s) (a check that could not run, or supplementary notes not read in full)" % gaps
        if gaps else "",
        "; %d blocking finding(s) exempted by allow.tsv" % ex if ex else "",
        "; also: %s" % ", ".join(others) if others else "")


def _public(f: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in f.items() if not k.startswith("_")}


# ─── Inputs ──────────────────────────────────────────────────────────────────

_OUT_DIRS = ("", "build", "out", "_build", "output")


def _is_main_tex(path: str) -> bool:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            head = fh.read(200000)
    except OSError:
        return False
    body = "\n".join(strip_tex_comments(t) for t in head.splitlines())
    return "\\documentclass" in body and "\\begin{document}" in body


def discover_inputs(paper_dir: str, pdf_args: Sequence[str], tex_args: Sequence[str],
                    no_sources: bool) -> Dict[str, Any]:
    """Main .tex files (top level), PDFs (args or <stem>.pdf in common output
    dirs), and their pairing by file stem."""
    mains: List[str] = []
    if not no_sources:
        if tex_args:
            mains = [os.path.abspath(t) for t in tex_args]
        elif os.path.isdir(paper_dir):
            for fn in sorted(os.listdir(paper_dir)):
                p = os.path.join(paper_dir, fn)
                if fn.endswith(".tex") and os.path.isfile(p) and _is_main_tex(p):
                    mains.append(os.path.abspath(p))
    pdfs: List[str] = [os.path.abspath(p) for p in pdf_args]
    if not pdf_args:
        for m in mains:
            stem = os.path.splitext(os.path.basename(m))[0]
            for d in _OUT_DIRS:
                c = os.path.join(os.path.dirname(m), d, stem + ".pdf")
                if os.path.isfile(c):
                    pdfs.append(os.path.abspath(c))
                    break
    pairs: Dict[str, Optional[str]] = {}
    for p in pdfs:
        stem = os.path.splitext(os.path.basename(p))[0]
        match = next((m for m in mains if os.path.splitext(os.path.basename(m))[0] == stem), None)
        if match is None and len(mains) == 1:
            match = mains[0]
        pairs[p] = match
    return {"mains": mains, "pdfs": pdfs, "pairs": pairs}


def _find_sidecar(stem: str, dirs: Sequence[str], ext: str) -> Optional[str]:
    for base in dirs:
        for d in _OUT_DIRS:
            c = os.path.join(base, d, stem + ext)
            if os.path.isfile(c):
                return c
    return None


# ─── scan orchestration ──────────────────────────────────────────────────────

def _selected(cid: str, tokens: Sequence[str]) -> bool:
    for t in tokens:
        t = t.strip()
        if not t:
            continue
        if cid == t or cid.startswith(t.rstrip("-") + "-") or fnmatch.fnmatchcase(cid, t):
            return True
    return False


def _detex_line(text: str) -> str:
    t = text
    t = re.sub(r"\\(?:label|ref|cref|Cref|autoref|eqref|pageref|nameref|vref|[Cc]ite[a-zA-Z]*|[a-z]*cite[a-z]*|nocite|"
               r"bibliography\w*|bibliographystyle|addbibresource|includegraphics|input|include|subfile|usepackage|"
               r"RequirePackage|documentclass|graphicspath|newcommand|renewcommand|providecommand|DeclareMathOperator|"
               r"newenvironment|setlength|addtolength|vspace|hspace|begin|end|hypersetup|definecolor|pgfplotsset|tikzset)"
               r"\*?\s*(?:\[[^\]]*\]\s*)*(?:\{[^{}]*\}\s*){0,3}", " ", t)
    t = t.replace("\\times", "×").replace("\\%", "%").replace("\\&", "&").replace("\\_", "_").replace("\\#", "#")
    t = t.replace("\\$", "$").replace("\\textbackslash", "\\").replace("\\ldots", "...").replace("\\dots", "...")
    t = t.replace("\\textasciitilde", "~").replace("\\@", "").replace("\\\\", " ")
    t = re.sub(r"\\[,;:! ]", " ", t)
    t = t.replace("~", " ")
    t = re.sub(r"\\[a-zA-Z@]+\*?", "", t)
    t = t.replace("}{", " ").replace("{", "").replace("}", "").replace("$", "")
    return t


def _detex_literal(s: str) -> str:
    """The text a typewriter-font argument prints: TeX escapes undone
    (\\textbackslash, \\{, \\}, \\_, \\#, ...), other commands and grouping
    braces dropped. Escaped characters survive the brace removal."""
    s = re.sub(r"\\textbackslash(?:\{\})?\s?", "\x00", s)
    s = re.sub(r"\\textasciitilde(?:\{\})?|\\~\{\}", "\x03", s)
    s = re.sub(r"\\textasciicircum(?:\{\})?|\\\^\{\}", "\x04", s)
    s = s.replace("\\{", "\x01").replace("\\}", "\x02")
    s = re.sub(r"\\([_#%&$ ])", r"\1", s)
    s = re.sub(r"\\[a-zA-Z@]+\*?\s?", "", s)
    s = s.replace("{", "").replace("}", "")
    return s.replace("\x00", "\\").replace("\x01", "{").replace("\x02", "}").replace("\x03", "~").replace("\x04", "^")


_TT_ARG_RE = re.compile(r"\\(?:texttt|path|url|lstinline|code|ttfamily)\s*(?=\{)")
_CELLS_BEGIN_RE = re.compile(r"\\begin\{(?:tabular\*?|tabularx|tabulary|longtable)\}")
_CELLS_END_RE = re.compile(r"\\end\{(?:tabular\*?|tabularx|tabulary|longtable)\}")


def _prose_literal(text: str) -> str:
    """A prose source line as it may enter the verbatim blob: an escape glued to
    words on both sides (see\\textbackslash nTable) outside a typewriter argument
    becomes a sentinel that never matches PDF text, so the residue cannot
    certify itself; \\texttt{a\\textbackslash nb} keeps its literal."""
    keep: List[Tuple[int, int]] = []
    for m in _TT_ARG_RE.finditer(text):
        body, end = _balanced_arg(text, m.end())
        if body is not None:
            keep.append((m.start(), end))
    out, pos = [], 0
    for a_, b_ in keep:
        if a_ < pos:
            continue
        out.append(_GLUED_ESC_SRC_RE.sub("\x05", text[pos:a_]))
        out.append(text[a_:b_])
        pos = b_
    out.append(_GLUED_ESC_SRC_RE.sub("\x05", text[pos:]))
    return "".join(out)


def _env_set(var: str, val: str) -> str:
    """A literal written into the environment: os.environ["VAR"] = "val" or os.environ.setdefault("VAR", "val")."""
    return (r"os\.environ\s*(?:\[\s*['\"](?:%s)['\"]\s*\]\s*=\s*|\.setdefault\s*\(\s*['\"](?:%s)['\"]\s*,\s*)"
            r"['\"](?:%s)['\"]" % (var, var, val))


# code-level recall candidates of the supplement (plan only): the authors' machine written into the
# environment as a literal — a device list, a cache path, a tracking account; a value read from an argument
# (`= args.gpu`), an empty device list, or an offline switch is configuration, not the machine
_CODE_P2_RES = (
    (re.compile("|".join((
        _env_set(r"(?:CUDA|HIP|ROCR)_VISIBLE_DEVICES", r"\s*\d+(?:\s*,\s*\d+)*\s*"),
        _env_set(r"HF_HOME|HF_\w*CACHE\w*|TRANSFORMERS_CACHE|TORCH_HOME|XDG_CACHE_HOME",
                 r"(?:/|~|[A-Za-z]:[\\/])[^'\"\n]*"),
        _env_set(r"WANDB_(?:ENTITY|PROJECT|DIR|USERNAME)", r"[^'\"\n]+"))), _A),
     "the authors' machine set in code (a device list, a cache path, a tracking account)"),
    (re.compile(r"['\"]\s*\[DEBUG\]", _A), "debug output left in the code"),
    (re.compile(r"(?m)^\s*(?:import\s+[\w.]+\s+as\s+(?:old|legacy|backup|bak|orig|prev)\w*\b|from\s+[\w.]*_(?:old|legacy|"
                r"backup|bak|orig|prev|fix|fixed)\s+import\b)", _A), "a working-copy module alias"),
)
# a text field of a data record (note, verdict, comment, …) and the run's story it may tell
_DATA_TEXT_FIELD_RE = re.compile(r"\"(?:note|notes|comment|comments|verdict|remark|remarks|reason|description|message|"
                                 r"msg|status_note)\"\s*:\s*\"(?P<v>(?:[^\"\\\n]|\\.){4,400})\"", re.I | _A)
# ("fixed" alone is a design word — a fixed frame, a fixed seed; only a repair is the run's story)
_DATA_STORY_RE = re.compile(r"\b(?:broken|buggy|bug|fixed\s+(?:a|an|the)\s+(?:bug|error|issue|problem|typo)|hotfix|"
                            r"re-?run|redo|redone|stale|obsolete|superseded|discarded|wrong|invalid|by\s+hand|manually|"
                            r"retry|retried|crash(?:ed)?)\b", re.I | _A)
_TABLE_RELEASE_HEAD_RE = re.compile(r"(?<![\w-])(?:releases?|versions?)(?![\w-])", re.I | _A)
_BARE_RELEASE_RE = re.compile(r"(?<![\w.])\d+\.\d+\.\d+(?![\w]|\.\d)", _A)


def _table_release_findings(buf: Sequence[Tuple[str, str, int]], ctx: ScanContext, main: str,
                            sub: Optional[str]) -> List[Dict[str, Any]]:
    """Bare release numbers in the cells of a table whose header names a
    release or a version (ENG-VER recall candidates, plan only)."""
    out: List[Dict[str, Any]] = []
    if not ctx.on("ENG-VER") or main == "references" or not _TABLE_RELEASE_HEAD_RE.search(
            " ".join(_detex_line(t_) for t_, _f, _n in buf[:4])):
        return out
    for t_, f_, n_ in buf:
        plain = _REF_CMD_RE.sub(" ", _CITE_CMD_RE.sub(" ", t_))
        named = [(x.start(), x.end(), None) for rx in _ENG_VER_RES for x in rx.finditer(plain)]
        for m in _BARE_RELEASE_RE.finditer(plain):
            if _overlaps(named, m.start(), m.end()):
                continue  # the library's own name is beside it: the definite rule reports it
            out.append(make_finding(ctx, "ENG-VER", WARN, CANDIDATE, "tex", m.group(0), _excerpt(plain, m.start(), m.end()),
                                    {"file": f_, "line": n_}, main, "a release number in a table whose header "
                                    "names releases: if the release is what the study compares, name it by its "
                                    "order", sub=sub))
            out[-1]["plan_only"] = True
            if len(out) >= 40:
                return out
    return out


_TEX_REGION_RE = re.compile(r"\\(appendix)\b|\\(bibliography|printbibliography)\b|\\begin\{(thebibliography)\}|"
                            r"\\(?:section|subsection|subsubsection|paragraph)\*?\s*\{([^{}]*)\}|\\begin\{(acks?)\}")


def scan_sources(expanded: Dict[str, Any], ctx: ScanContext, paper_dir: str, policy: Dict[str, Any],
                 pdf_page1: Optional[str]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Text-pattern hits on de-TeXed paragraphs (file:line) plus structural
    source checks: final-copy switches, \\author, acknowledgments, layout
    overrides, \\todo-style markers."""
    tables = {k: [x.casefold() for x in v] for k, v in DEFAULT_HEADINGS.items()}
    findings: List[Dict[str, Any]] = []
    main, sub = "body", None
    para: List[Tuple[str, str, int]] = []
    verb_parts: List[str] = []
    table_depth = 0
    table_buf: List[Tuple[str, str, int]] = []
    after_doc = False
    neg_vspace = 0
    src_counts = {"ψ": 0, "←": 0, "␣": 0}

    def flush() -> None:
        if not para:
            return
        texts, offs = [], []
        pos = 0
        for t, f, line_no in para:
            offs.append((pos, f, line_no))
            texts.append(t)
            pos += len(t) + 1
        text = " ".join(texts)
        for h in detect_text(text, main, sub, ctx, "tex"):
            f_, l_ = next(((f, n) for o, f, n in reversed(offs) if o <= h.start), (para[0][1], para[0][2]))
            raw = h.match if h.match is not None else text[h.start:h.end]
            findings.append(make_finding(ctx, h.check, h.severity, h.certainty, "tex", raw,
                                         _excerpt(text, h.start, h.end), {"file": f_, "line": l_}, main, h.note,
                                         sub=sub, demoted=h.demoted))
            _hit_extras(findings[-1], h)
        para.clear()

    full_text = "\n".join(ln["text"] for ln in expanded["lines"] if not ln["verbatim"])
    for ln in expanded["lines"]:
        text, f, line_no = ln["text"], ln["file"], ln["line"]
        if ln["verbatim"]:
            verb_parts.append(text)
            flush()
            if text.strip():
                para.append((text, f, line_no))
            flush()
            continue
        if "\\begin{document}" in text:
            after_doc = True
        for m in _INLINE_VERB_RE.finditer(text):
            close = text.find(m.group(1), m.end())
            if close > 0:
                verb_parts.append(text[m.end():close])
        for m in _TT_ARG_RE.finditer(text):
            body, _ = _balanced_arg(text, m.end())  # \texttt{\textbackslash boxed\{x\}} has nested braces
            if body is not None:
                verb_parts.append(_detex_literal(body))
        # table cells (prompt and format tables), counted per occurrence: "\end{tabular}
        # \end{table}" on one line must not leave the rest of the paper "inside a table";
        # a table float's caption is prose, so only cell environments count
        n_open = len(_CELLS_BEGIN_RE.findall(text))
        n_close = len(_CELLS_END_RE.findall(text))
        if "\\textbackslash" in text:
            # A backslash the author escaped on purpose prints literally: in a table
            # cell always; in prose only when the escape stands apart.
            # "see\textbackslash nTable", glued to words on both sides, is the residue
            # itself and must not certify itself as verbatim text.
            lit = text if (table_depth or n_open) else _prose_literal(text)
            verb_parts.append(_detex_literal(lit))
        table_depth += n_open
        if table_depth and "??" in text:
            verb_parts.append(text)
        if table_depth:
            table_buf.append((text, f, line_no))
        table_depth = max(0, table_depth - n_close)
        if table_buf and not table_depth:
            findings.extend(_table_release_findings(table_buf, ctx, main, sub))
            table_buf.clear()
        src_counts["ψ"] += len(re.findall(r"\\psi(?![a-zA-Z])", text))
        src_counts["←"] += len(re.findall(r"\\(?:leftarrow|gets|longleftarrow)(?![a-zA-Z])", text))
        src_counts["␣"] += len(re.findall(r"\\(?:textvisiblespace|visiblespace)(?![a-zA-Z])", text))
        for m in _TEX_REGION_RE.finditer(text):
            flush()
            if m.group(1):
                main, sub = "appendix", None
            elif m.group(2) or m.group(3):
                main, sub = "references", None
            elif m.group(5):
                main, sub = "end_matter", "acknowledgments"
            elif m.group(4) is not None:
                hk = heading_kind(_detex_line(m.group(4)), main, tables, letter_ok=False)
                if hk and hk[0] in ("references", "checklist"):
                    main, sub = hk[0], None
                elif hk and hk[0] == "end_matter":
                    main, sub = "end_matter", hk[1]
                elif hk and hk[0] in ("compute", "related_work"):
                    sub = hk[0]
                elif hk and hk[0] == "appendix":
                    main, sub = "appendix", None
                else:
                    sub = None
        if re.search(r"\\end\{thebibliography\}", text):
            main = "body" if main == "references" else main
        if after_doc:
            neg_vspace += len(re.findall(r"\\vspace\*?\s*\{\s*-", text))
        dt = _detex_line(text)
        if not dt.strip():
            flush()
            continue
        para.append((dt, f, line_no))
    flush()
    ctx.verbatim_blob = "\n".join(verb_parts)
    struct = _structural_source_checks(full_text, expanded, ctx, pdf_page1, neg_vspace)
    findings += struct
    return findings, {"src_counts": src_counts, "neg_vspace": neg_vspace}


_FINALCOPY_RE = re.compile(r"\\(?:iclrfinalcopy|aclfinalcopy|cvprfinalcopy|iccvfinalcopy|wacvfinalcopy|eccvfinalcopy)\b"
                           r"|\\usepackage\s*\[[^\]]*\b(?:final|accepted|preprint|camera-?ready|nonanonymous)\b[^\]]*\]\s*"
                           r"\{(?:neurips|nips|icml|iclr|acl|naacl|emnlp|eacl|coling|aaai|ijcai|colm|cvpr|iccv|eccv|kdd|uai|"
                           r"aistats|colt|tmlr|jmlr|rlc|corl|l4dc|automl|mlsys|icra|iros)[\w-]*\}")
_TPL_BLOCK_RE = re.compile(r"\\usepackage\s*(?:\[[^\]]*\])?\s*\{[^}]*\b(?:geometry|fullpage|savetrees|a4wide)\b[^}]*\}"
                           r"|\\(?:set|add)tolength\s*\{?\s*\\(?:textheight|textwidth|oddsidemargin|evensidemargin|topmargin|"
                           r"headheight|headsep|footskip|columnsep|hoffset|voffset|marginparwidth)\b"
                           r"|\\setlength\s*\{?\s*\\(?:textheight|textwidth|oddsidemargin|evensidemargin|topmargin|headheight|"
                           r"headsep|footskip|columnsep|hoffset|voffset)\b"
                           r"|\\linespread\s*\{|\\renewcommand\s*\{?\s*\\baselinestretch|\\geometry\s*\{|\\newgeometry\s*\{"
                           r"|\\(?:renewcommand|def)\s*\{?\s*\\(?:normalsize|small|footnotesize|scriptsize|large|Large)\b")
_TPL_WARN_RE = re.compile(r"\\enlargethispage\b|\\captionsetup\s*(?:\[[^\]]*\])?\s*\{[^}]*\b(?:skip|font|belowskip|aboveskip)\s*="
                          r"|\\titlespacing\b|\\usepackage\s*(?:\[[^\]]*\])?\s*\{[^}]*\btitlesec\b"
                          r"|\\(?:set|add)tolength\s*\{?\s*\\(?:abovecaptionskip|belowcaptionskip|textfloatsep|floatsep|intextsep|"
                          r"abovedisplayskip|belowdisplayskip|parskip|baselineskip|dbltextfloatsep)\b"
                          r"|\\setlength\s*\{?\s*\\(?:abovecaptionskip|belowcaptionskip|textfloatsep|floatsep|intextsep|"
                          r"abovedisplayskip|belowdisplayskip|parskip|baselineskip|dbltextfloatsep)\b")
_SRC_ACK_RE = re.compile(r"\\(?:section|subsection|subsubsection|paragraph)\*?\s*\{\s*(?:Acknowledg|Author Contributions|Funding|致谢)"
                         r"|\\begin\{acks?\}|\\acknowledgments\b")
_SRC_TODO_RE = re.compile(r"\\(?:todo|TODO|fixme|FIXME|revise|missingfigure|hl)\s*(?:\[[^\]]*\])?\s*\{")


def _structural_source_checks(full_text: str, expanded: Dict[str, Any], ctx: ScanContext, pdf_page1: Optional[str],
                              neg_vspace: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    nv = [ln for ln in expanded["lines"] if not ln["verbatim"]]  # the lines `full_text` was joined from

    def loc_of(snippet_re: Any) -> Iterator[Tuple[Any, Dict[str, Any]]]:
        for ln in nv:
            for m in snippet_re.finditer(ln["text"]):
                yield m, {"file": ln["file"], "line": ln["line"]}

    if ctx.anonymous:
        if ctx.on("ANON-AUTHOR"):
            for m, loc in loc_of(_FINALCOPY_RE):
                out.append(make_finding(ctx, "ANON-AUTHOR", BLOCK, DEFINITE, "tex", m.group(0), m.group(0), loc,
                                        note="final-copy switch is active"))
            for am in re.finditer(r"\\(?:author|icmlauthor)\s*(?:\[[^\]]*\])?\s*\{", full_text):
                body, _ = _balanced_arg(full_text, am.end() - 1)
                plain = _collapse_ws(_detex_line(body or ""))
                if not plain or re.search(r"anonymous|anon\.|under review|paper id", plain, re.I):
                    continue
                line_no = full_text.count("\n", 0, am.start())
                ln = nv[min(line_no, len(nv) - 1)] if nv else {}
                loc = {"file": ln.get("file"), "line": ln.get("line")}
                if pdf_page1 is None:
                    sev, cert, note = WARN, DEFINITE, "could not confirm against the PDF text"
                elif "anonymous" in pdf_page1.casefold():
                    sev, cert, note = INFO, DEFINITE, "hidden by the venue style (page 1 shows 'Anonymous')"
                else:
                    sev, cert, note = BLOCK, DEFINITE, "page 1 of the PDF does not show 'Anonymous'"
                out.append(make_finding(ctx, "ANON-AUTHOR", sev, cert, "tex", "\\author{...}", plain[:120], loc, note=note))
                break
        if ctx.on("ANON-ACK"):
            for m, loc in loc_of(_SRC_ACK_RE):
                out.append(make_finding(ctx, "ANON-ACK", BLOCK, DEFINITE, "tex", "acknowledgments", m.group(0), loc))
    if ctx.on("TPL-OVERRIDE"):
        for m, loc in loc_of(_TPL_BLOCK_RE):
            out.append(make_finding(ctx, "TPL-OVERRIDE", BLOCK, DEFINITE, "tex", m.group(0), m.group(0), loc))
        for m, loc in loc_of(_TPL_WARN_RE):
            out.append(make_finding(ctx, "TPL-OVERRIDE", WARN, DEFINITE, "tex", m.group(0), m.group(0), loc))
        if neg_vspace:
            out.append(make_finding(ctx, "TPL-OVERRIDE", WARN, DEFINITE, "tex", "negative \\vspace",
                                    "%d negative \\vspace in the document body" % neg_vspace, {}))
    if ctx.on("TEXT-MARKER"):
        for m, loc in loc_of(_SRC_TODO_RE):
            out.append(make_finding(ctx, "TEXT-MARKER", WARN, CANDIDATE, "tex", m.group(0), m.group(0), loc,
                                    note="renders as a margin note unless the package is disabled", nodemote=True))
    if ctx.on("TEXT-CODE"):
        # the source spelling of an escape glued into prose (see\textbackslash nTable): paired with the
        # PDF finding of the same text, it gives the `escape` fix its file and line
        for m, loc in loc_of(_GLUED_ESC_SRC_WORD_RE):
            if not _in_tt_arg(m.string, m.start()):
                out.append(make_finding(ctx, "TEXT-CODE", BLOCK, DEFINITE, "tex", "\\" + m.group(1) + m.group(2),
                                        m.group(0), loc, note=_GLUED_ESC_NOTE))
    return out


def _in_tt_arg(text: str, pos: int) -> bool:
    """Whether text[pos] lies inside a typewriter argument (\\texttt{...}): a literal kept on purpose."""
    for m in _TT_ARG_RE.finditer(text, 0, pos):
        body, end = _balanced_arg(text, m.end())
        if body is not None and m.end() <= pos < end:
            return True
    return False


_PDF_FIELD_NAME_RE = re.compile(r"\bpdf(?:author|title|subject|keywords|creator|producer)\s*=", re.I)


def _merge_tex_into_pdf(pdf_f: List[Dict[str, Any]], tex_f: List[Dict[str, Any]], pdf_text_ok: bool,
                        recheck_sources_newer: bool) -> List[Dict[str, Any]]:
    """Attach file:line of source hits to the PDF finding with the same
    (check, match); demote source-only text-pattern hits to INFO when the PDF
    text was available."""
    by_key: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for f in pdf_f:
        by_key.setdefault((f["check"], f["_key"]), []).append(f)
    out: List[Dict[str, Any]] = []
    for t in tex_f:
        k = (t["check"], t["_key"])
        targets = by_key.get(k)
        if targets:
            for f in targets:
                if not f["location"].get("file"):
                    f["location"]["file"], f["location"]["line"] = t["location"]["file"], t["location"]["line"]
                    break
            continue
        if recheck_sources_newer and t["severity"] != INFO:
            t["original_severity"], t["severity"] = t["severity"], INFO
            t["note"] = "sources are newer than this PDF; source-level findings may not describe the uploaded bytes"
        elif (pdf_text_ok and t["check"] in DEMOTABLE_CHECKS and t["severity"] != INFO and t["layer"] == "tex"
              and not t.get("_nodemote")):
            if t["check"] == "ANON-ACK" and any(f["check"] == "ANON-ACK" for f in pdf_f):
                pass
            elif t["check"] in ("ANON-NAME", "ANON-EMAIL") and _PDF_FIELD_NAME_RE.search(t.get("excerpt") or ""):
                # a PDF metadata field of the sources: the PDF carries it unless a later line empties
                # the field, and the sources keep it (an arXiv or camera-ready source shows it)
                if t["severity"] == BLOCK:
                    t["original_severity"], t["severity"] = t["severity"], WARN
                t["pdf_field"] = True
                t["note"] = ("set in a PDF metadata field of the sources: the sources keep it, and the PDF shows it "
                             "unless a later line empties the field")
                t["suggestion"] = ("Empty the field where the sources set it (pdfauthor={}); an override line after it "
                                   "keeps the value in the sources")
            else:
                t["original_severity"], t["severity"] = t["severity"], INFO
                t["note"] = ("present in the LaTeX source but not in the PDF text (hidden, a figure path, or an option)"
                             if not t.get("note") else t["note"] + "; not in the PDF text")
        out.append(t)
    return pdf_f + out


def _text_layer_empty(pages: List[Dict[str, Any]]) -> bool:
    """No usable text: outlined fonts, an image-only (scanned) PDF, or fonts
    without a Unicode map. Then no text check ran, so the scan cannot pass."""
    counts = [len(re.sub(r"\s+", "", " ".join(s["text"] for s in p["segs"]))) for p in pages]
    return bool(counts) and sum(counts) < 10 * len(counts) and max(counts) < 50


def run_scan(a: Any) -> Dict[str, Any]:
    """The Tier A scan. Returns the scan document (JSON-ready)."""
    t0 = _now()
    pdf_args = list(a.pdf or [])
    paper_dir = a.paper_dir or (os.path.dirname(os.path.abspath(pdf_args[0])) if pdf_args else "paper")
    paper_dir = os.path.abspath(paper_dir)
    if not os.path.isdir(paper_dir):
        raise UsageError("paper directory not found: %s" % (a.paper_dir or "paper"))
    cfg = load_config(a.config_dir, a.anon_names, a.allow, a.policy)
    pol = cfg["policy"]
    ctx = ScanContext()
    ctx.policy = pol
    run_mode = a.run_mode
    camera = bool(a.camera_ready) or pol.get("anonymous") is False
    ctx.anonymous = not camera
    ctx.strict = bool(a.strict) or bool(pol.get("strict"))
    for attr, flag, default in (("hardware", a.hardware, "block"), ("framework", a.framework, "warn")):
        lvl = str(flag or pol.get(attr) or default).lower()
        if lvl not in HARDWARE_LEVELS:
            raise UsageError("%s must be one of block, warn, info (got %r)" % (attr, lvl))
        setattr(ctx, attr, HARDWARE_LEVELS[lvl])
    # hardware, OS, and host words in the supplement follow the hardware policy: WARN
    # candidates whose confirmed level is the --hardware level (a reviewer rules a
    # reproduction requirement 'necessary'); policy supp_hardware sets another level,
    # and 'info' (or --hardware info) keeps them INFO and unreviewed
    sh = getattr(a, "supp_hardware", None) or pol.get("supp_hardware")
    if sh is not None:
        sh = str(sh).lower()
        if sh not in HARDWARE_LEVELS:
            raise UsageError("supp_hardware must be one of block, warn, info (got %r)" % sh)
        ctx.supp_hardware = None if sh == "info" else HARDWARE_LEVELS[sh]
    else:
        ctx.supp_hardware = None if ctx.hardware == INFO else ctx.hardware
    # user policy switches (community-friendly defaults: precision exempt, registration labels kept)
    for attr, flag, key, allowed in (("precision", getattr(a, "precision_disclosure", None), "precision_disclosure",
                                      PRECISION_POLICIES),
                                     ("reg_labels", getattr(a, "registration_labels", None), "registration_labels",
                                      REGISTRATION_POLICIES)):
        val = str(flag or pol.get(key) or allowed[0]).lower()
        if val not in allowed:
            raise UsageError("%s must be one of %s (got %r)" % (key, ", ".join(allowed), val))
        setattr(ctx, attr, val)
    ctx.run_mode = run_mode
    ctx.log_wrap = a.log_wrap  # type: ignore[attr-defined]
    page_limit = a.page_limit if a.page_limit is not None else pol.get("page_limit")
    fill_page = a.fill_page if a.fill_page is not None else pol.get("fill_page")
    fill_thr = a.fill_threshold if a.fill_threshold is not None else float(pol.get("fill_threshold", 0.97))
    end_slots = parse_end_matter(a.end_matter if a.end_matter else pol.get("end_matter"))
    supp_max_mb = a.supp_max_mb if a.supp_max_mb is not None else pol.get("supp_max_mb")
    # identity / deny / exempt
    auto_terms: List[str] = []
    if ctx.anonymous and not a.no_auto_identity:
        auto_terms = auto_identity_terms()
    ctx.identity = TermMatcher(cfg["identity_terms"] if ctx.anonymous else [])
    ctx.derived_users = derived_usernames(cfg["identity_terms"]) if ctx.anonymous else set()
    ctx.auto = TermMatcher([(str(i), t) for i, t in enumerate(auto_terms, 1)])
    ctx.deny = TermMatcher([(str(i), t) for i, t in enumerate(pol.get("extra_deny") or [], 1)])
    exempt_terms = [str(x) for x in (pol.get("exempt_terms") or []) if str(x).strip()]
    ctx.exempt = TermMatcher([(str(i), t) for i, t in enumerate(exempt_terms, 1)])
    ctx.redactor = Redactor(ctx.identity, ctx.auto, ctx.deny)
    invisible, has_ts = _invisible_set()
    ctx.has_invisible_set = has_ts
    # check selection
    skipped: List[Dict[str, Any]] = []
    enabled: Set[str] = set()
    include = [x for x in (a.checks or "").split(",") if x.strip()]
    exclude = [x for x in (a.skip_checks or "").split(",") if x.strip()]

    def skip(cid: str, reason: str, cap: Optional[str] = None, hint: Optional[str] = None) -> None:
        if cid in enabled:
            enabled.discard(cid)
        if not any(s["check"] == cid for s in skipped):
            skipped.append({"check": cid, "reason": reason, "cap": cap, "hint": hint})

    for cid, spec in CHECKS.items():
        if spec["layer"] == "review":
            continue
        if include and not _selected(cid, include):
            skipped.append({"check": cid, "reason": "user", "cap": None, "hint": None})
            continue
        if exclude and _selected(cid, exclude):
            skipped.append({"check": cid, "reason": "user", "cap": None, "hint": None})
            continue
        if spec["family"] == "ANON" and not ctx.anonymous:
            skipped.append({"check": cid, "reason": "camera_ready", "cap": None, "hint": None})
            continue
        enabled.add(cid)
    for cid, cond, why in (("PAGE-LIMIT", page_limit is None, "not_configured"),
                           ("PAGE-FILL", fill_page is None, "not_configured"),
                           ("ENDM-MISSING", not end_slots, "not_configured"),
                           ("ENDM-ORDER", not end_slots, "not_configured"),
                           ("TPL-STYLE", not a.style_ref, "not_configured"),
                           ("NUM-DRIFT", not a.baseline, "not_configured"),
                           ("FIX-REGRESSION", not a.baseline, "not_configured"),
                           ("CONFIG-CHANGED", not a.baseline or run_mode == "recheck", "not_configured"),
                           ("ENG-DENY", not pol.get("extra_deny"), "not_configured")):
        if cond and cid in enabled:
            skip(cid, why)
    if not a.supp:
        for cid in [c for c in enabled if c.startswith("SUPP-")]:
            skip(cid, "not_applicable")
    if not has_ts and "TEXT-INVISIBLE" in enabled:
        skip("TEXT-INVISIBLE", "threat_scan_unavailable", "WARN", "tools/threat_scan.py must be importable")
    if not has_ts and "TEXT-INJECT" in enabled:
        skip("TEXT-INJECT", "threat_scan_unavailable", "WARN", "tools/threat_scan.py must be importable")
    ctx.enabled = enabled

    findings: List[Dict[str, Any]] = []
    blocked: List[str] = []
    notes: List[str] = []
    inputs: Dict[str, Any] = {"pdf": [], "tex": [], "bib": [], "log": [], "blg": [], "supp": [], "config": {}}
    hashes: Dict[str, str] = {}
    backends: Dict[str, Any] = {"text": None, "bbox": None, "metadata": "stdlib", "bytes": "stdlib", "nospace": "stdlib",
                                "copy_check": None}
    page_geo: List[Dict[str, Any]] = []
    regions_out: List[Dict[str, Any]] = []
    numbers_out: Dict[str, Dict[str, int]] = {}
    numbers_all_out: Dict[str, Dict[str, int]] = {}
    num_texts: Dict[str, Dict[str, str]] = {}
    layouts: Dict[str, Dict[str, Any]] = {}
    pdf_text_all: List[str] = []
    pdf_pages_text: List[Tuple[str, int, str]] = []  # (artifact, page, body text): code names in the paper
    page_norms: List[Tuple[str, int, str]] = []  # (artifact, page, normalized redacted text): carried quotes
    end_matter_seen = False
    work_dir = os.path.abspath(a.work_dir) if a.work_dir else None
    ledger = load_ledger(work_dir) if work_dir else {"version": 1, "entries": {}}
    if work_dir and _is_within(work_dir, paper_dir):
        notes.append("the work directory is inside the paper directory: never upload the LaTeX sources with it "
                     "(backups and snapshots there still hold the leaks)")
    fix_state = (_load_json(os.path.join(work_dir, STATE_NAME))
                 if work_dir and (run_mode == "recheck" or (run_mode == "fix" and a.baseline)) else None)
    if isinstance(fix_state, dict):
        # code names an earlier round reported stay reported while any occurrence is left
        ctx.persisted_codenames = [str(x) for x in fix_state.get("codenames") or [] if str(x).strip()]
    track_edits = bool(work_dir and a.baseline and run_mode in ("fix", "recheck")
                       and not str(a.baseline).lower().endswith(".pdf"))

    def add_hash(path: str) -> None:
        if path and os.path.isfile(path):
            hashes[_rel(path, paper_dir)] = "sha256:" + _sha256_file(path)

    # config bookkeeping
    for k in ("anon_names", "allow", "policy"):
        p = cfg["paths"][k]
        inputs["config"][k] = _rel(p, paper_dir) if cfg["exists"][k] else None
        if cfg["exists"][k]:
            add_hash(p)
    if ctx.anonymous:
        if not cfg["exists"]["anon_names"] and "ANON-LIST-MISSING" in enabled:
            findings.append(make_finding(ctx, "ANON-LIST-MISSING", WARN, DEFINITE, "config", "identity list missing",
                                         "no anon-names file at %s" % _display_path(cfg["paths"]["anon_names"], paper_dir),
                                         {}))
        elif cfg["exists"]["anon_names"] and _is_within(cfg["paths"]["anon_names"], paper_dir) \
                and "ANON-LIST-LOCATION" in enabled:
            findings.append(make_finding(ctx, "ANON-LIST-LOCATION", WARN, DEFINITE, "config",
                                         _rel(cfg["paths"]["anon_names"], paper_dir), "identity list inside the paper directory", {}))
        for line, why in cfg["identity_short"]:
            if "ANON-LIST-TERM" in enabled:
                findings.append(make_finding(ctx, "ANON-LIST-TERM", WARN, DEFINITE, "config", "line %d" % line, why, {}))
    for issue in cfg["allow_issues"]:
        if "ALLOW-INVALID" in enabled:
            findings.append(make_finding(ctx, "ALLOW-INVALID", WARN, DEFINITE, "config", "allow.tsv line %d" % issue["line"],
                                         issue["problem"], {}))
    if cfg["policy_unknown_keys"]:
        notes.append("policy keys ignored (unknown): %s" % ", ".join(cfg["policy_unknown_keys"]))

    disc = discover_inputs(paper_dir, pdf_args, a.main_tex or [], a.no_sources)
    nothing = not disc["pdfs"] and not disc["mains"] and not a.supp
    for p in pdf_args:
        if not os.path.isfile(p):
            blocked.append("pdf_missing")
            notes.append("PDF not found: %s" % _display_path(p, paper_dir))
    if disc["mains"] and not disc["pdfs"] and "pdf_missing" not in blocked:
        blocked.append("pdf_missing")
        notes.append("no compiled PDF found next to the main .tex (pass --pdf)")

    text_missing_pdfs: List[str] = []
    text_empty_pdfs: List[str] = []
    source_cache: Dict[str, Dict[str, Any]] = {}
    for pdf in disc["pdfs"]:
        if not os.path.isfile(pdf):
            continue
        rel_pdf = _display_path(pdf, paper_dir)
        stem = os.path.splitext(os.path.basename(pdf))[0]
        with open(pdf, "rb") as fh:
            raw = fh.read()
        add_hash(pdf)
        entry: Dict[str, Any] = {"path": rel_pdf, "sha256": _sha256_bytes(raw), "pages": None, "text_file": None}
        inputs["pdf"].append(entry)
        doc = parse_pdf_objects(raw)
        if not doc.header_ok or doc.encrypted or not doc.objs:
            blocked.append("pdf_unreadable")
            notes.append("%s: %s" % (rel_pdf, "encrypted" if doc.encrypted else "not a readable PDF"))
            continue
        if doc.truncated:
            notes.append("%s: decompression limits reached; byte layer partially scanned" % rel_pdf)
        meta_f, info = scan_metadata(doc, ctx, rel_pdf)
        findings += meta_f
        byte_f = scan_pdf_bytes(doc, ctx, rel_pdf)
        if ctx.on("TEXT-NOSPACE") and "pdftex" in (info.get("Producer", "") or "").casefold():
            ns = nospace_stats(doc)
            entry["nospace"] = ns
            if ns["kerns"] >= 50 and ns["ratio"] < 0.05:
                findings.append(make_finding(ctx, "TEXT-NOSPACE", WARN, DEFINITE, "pdf-bytes",
                                             "%d real spaces vs %d kerned gaps" % (ns["spaces"], ns["kerns"]),
                                             "pdfTeX text layer without interword spaces", {"artifact": rel_pdf}))
        # text layer
        ext = extract_pdf(pdf, a.backend)
        if ext["error"] == "encrypted" or (ext["error"] and not ext["text_backend"] and a.backend != "none"
                                            and any(available_backends().values())):
            # a backend exists but could not read this file: the PDF, not the
            # environment, is the problem
            blocked.append("pdf_unreadable")
            notes.append("%s: %s" % (rel_pdf, "encrypted" if ext["error"] == "encrypted"
                                     else "text extraction failed (%s)" % ext["error"]))
            continue
        main_tex = disc["pairs"].get(pdf)
        pdf_mtime = _mtime(pdf) or 0.0
        text_ok = bool(ext["text_backend"]) and bool(ext["pages"])
        pages: List[Dict[str, Any]] = []
        events: List[Dict[str, Any]] = []
        if text_ok:
            backends["text"] = backends["text"] or ext["text_backend"]
            backends["bbox"] = backends["bbox"] or ext["bbox_backend"]
            pages = normalize_pages(ext["pages"], invisible)
            entry["pages"] = len(pages)
            if _text_layer_empty(pages):
                text_ok = False
                text_empty_pdfs.append(rel_pdf)
                notes.append("%s: the PDF has no extractable text" % rel_pdf)
                pages = []
        else:
            text_missing_pdfs.append(rel_pdf)
        if text_ok:
            events = detect_regions(pages, pol)
            end_matter_seen = end_matter_seen or any(e["kind"] == "end_matter" for e in events)
            regions_out.append({"artifact": rel_pdf, "headings": [{"page": e["page"], "kind": e["kind"],
                                                                    "text": ctx.redactor.redact(e["text"])} for e in events]})
        else:
            entry["pages"] = entry["pages"] or sum(1 for o in doc.objs.values()
                                                   if isinstance(o.value, dict) and o.value.get("Type") == "Page")
        # sources paired with this PDF
        src: Optional[Dict[str, Any]] = None
        if main_tex and not a.no_sources:
            if main_tex not in source_cache:
                source_cache[main_tex] = _load_sources(main_tex, paper_dir, ctx, pol)
            src = source_cache[main_tex]
        page1 = " ".join(s["text"] for s in pages[0]["segs"]) if pages else None
        pdf_f: List[Dict[str, Any]] = []
        tex_f: List[Dict[str, Any]] = []
        src_counts = None
        sources_newer = False
        if src is not None:
            for p in src["closure"]:
                add_hash(p)
            inputs["tex"] = sorted(set(inputs["tex"]) | {_rel(p, paper_dir) for p in src["tex_files"]})
            inputs["bib"] = sorted(set(inputs["bib"]) | {_rel(p, paper_dir) for p in src["bib_files"]})
            newest = max((_mtime(p) or 0.0) for p in src["closure"]) if src["closure"] else 0.0
            sources_newer = newest > pdf_mtime + 2
            if run_mode != "recheck" and not a.no_freshness and sources_newer:
                blocked.append("stale_pdf")
                newer = [_rel(p, paper_dir) for p in src["closure"] if (_mtime(p) or 0) > pdf_mtime + 2][:5]
                findings.append(make_finding(ctx, "BUILD-STALE", WARN, DEFINITE, "mtime", rel_pdf,
                                             "newer than the PDF: " + ", ".join(newer), {"artifact": rel_pdf}))
            elif run_mode == "recheck" and sources_newer:
                findings.append(make_finding(ctx, "BUILD-STALE", INFO, DEFINITE, "mtime", rel_pdf,
                                             "sources are newer than this PDF; source-level findings are INFO",
                                             {"artifact": rel_pdf}))
            ctx.verbatim_blob = src["verbatim_blob"]
            tex_res, aux_info = scan_sources(src["expanded"], ctx, paper_dir, pol, page1)
            src_counts = aux_info["src_counts"]
            tex_f += tex_res
            tex_f += _xref_findings(src, ctx)
            if not src.get("_figs_done"):
                src["_figs_done"] = True
                tex_f += _figure_file_findings(src.get("figs") or [], paper_dir, ctx)
            if src["xref"]["cites"] and not src["xref"]["bib_known"] and ctx.on("XREF-SRC-CITE"):
                # nothing to compare against; the PDF layer ([?]) still covers it
                skip("XREF-SRC-CITE", "no_bibliography_source", None,
                     "no .bib/.bbl/\\bibitem found next to the main .tex")
        else:
            ctx.verbatim_blob = ""
        if text_ok:
            pdf_f += scan_pdf_text(pages, ctx, rel_pdf)
            pdf_f += scan_mathglyph(pages, ctx, rel_pdf, src_counts)
            if src is not None and ctx.on("XREF-PDF-KEY"):
                pdf_f += _pdf_key_findings(pages, src, ctx, rel_pdf)
            pdf_f += check_end_matter(pages, end_slots, ctx, rel_pdf) if end_slots else []
            if ctx.on("TEXT-NOSPACE"):
                glue = copy_glue(pdf, pages, ext["text_backend"])
                if glue:
                    backends["copy_check"] = "pypdf"
                    entry["copy_glue"] = {"n": glue["n"], "pages": glue["pages"][:20]}
                if glue.get("n", 0) >= COPY_GLUE_MIN:
                    pdf_f.append(make_finding(
                        ctx, "TEXT-NOSPACE", WARN, DEFINITE, "pdf", "words glued in a second extractor",
                        "pypdf reads %d glued word(s) on page(s) %s, e.g. %s" % (
                            glue["n"], ", ".join(str(x) for x in glue["pages"][:8]),
                            ", ".join("'%s'" % x for x in glue["examples"])),
                        {"artifact": rel_pdf, "page": glue["pages"][0]}))
            geo = page_geometry(pages, events, pol.get("body_end_markers"))
            geo["artifact"] = rel_pdf
            page_geo.append(geo)
            pdf_f += _page_findings(geo, page_limit, fill_page, fill_thr, ctx, rel_pdf, skipped)
            numbers_out[rel_pdf] = dict(number_multiset(pages))
            numbers_all_out[rel_pdf] = dict(number_multiset_all(pages))
            num_texts[rel_pdf] = number_text(pages, ctx)
            entry["layout"] = layouts[rel_pdf] = layout_stats(pages, src_counts, entry.get("copy_glue"), ctx)
            if geo.get("status") == "ok":  # what the fix-regression guard compares: the body's end and fill
                lay = layouts[rel_pdf]
                lay["body_end_page"], lay["fill"] = geo.get("body_end_page"), round(float(geo.get("fill") or 0), 3)
                if fill_page is not None:
                    lay["fill_ok"] = geo["body_end_page"] == int(fill_page) and geo["fill"] >= fill_thr
                if page_limit is not None:
                    lay["limit_ok"] = geo["body_end_page"] <= int(page_limit)
            pdf_text_all.append(" ".join(s["text"] for p in pages for s in p["segs"] if s["kind"] == "body"))
            pdf_pages_text.extend((rel_pdf, p["page"], " ".join(s["text"] for s in p["segs"] if s["kind"] == "body"))
                                  for p in pages)
            if a.work_dir:
                tf = os.path.join(a.work_dir, "pdf_text.%s.txt" % stem)
                _write_atomic(tf, _render_pdf_text(pages, ctx))
                entry["text_file"] = _rel(tf, paper_dir)
                for p in pages:
                    page_norms.append((rel_pdf, p["page"], _norm_quote(ctx.redactor.redact(
                        " ".join(s["text"] for s in p["segs"])))))
                if run_mode == "fix" and not a.baseline:
                    # round 0 of a fix loop: freeze the counted text, so a later round can
                    # tell a number that left with a deleted clause from a changed result
                    nf = os.path.join(a.work_dir, "numtext.%s.r0.json" % stem)
                    _write_atomic(nf, json.dumps({"pages": num_texts[rel_pdf]}, ensure_ascii=False) + "\n")
                    entry["baseline_numtext"] = _rel(nf, paper_dir)
        merged = _merge_tex_into_pdf(pdf_f, tex_f, text_ok, run_mode == "recheck" and sources_newer)
        # META-BYTES: drop what another check already reports for this PDF
        keys = {f["_key"] for f in merged + meta_f}
        meta_raws = [f["_key"] for f in meta_f]
        findings += [f for f in byte_f if f["_key"] not in keys and not any(f["_key"] in r for r in meta_raws)]
        findings += merged
        # logs
        log_path = a.log or (_find_sidecar(stem, [os.path.dirname(pdf), paper_dir], ".log"))
        if not log_path and os.path.isfile(os.path.join(paper_dir, "compile.log")):
            log_path = os.path.join(paper_dir, "compile.log")
        findings += _log_findings(log_path, pdf_mtime, run_mode, ctx, paper_dir, inputs, skipped, src, add_hash,
                                  has_sources=src is not None, pdf_name=os.path.basename(pdf),
                                  pdf_pages=entry.get("pages"), notes=notes)
        blg_path = a.blg or _find_sidecar(stem, [os.path.dirname(pdf), paper_dir], ".blg")
        findings += _blg_findings(blg_path, pdf_mtime, run_mode, ctx, paper_dir, inputs, src, add_hash)
    if a.style_ref and ctx.on("TPL-STYLE"):
        findings += _style_findings(a.style_ref, paper_dir, ctx)
    # sources without any PDF (audit verdict is pdf_missing, but report them)
    if not disc["pdfs"]:
        for main_tex in disc["mains"]:
            src = _load_sources(main_tex, paper_dir, ctx, pol)
            for p in src["closure"]:
                add_hash(p)
            inputs["tex"] = sorted(set(inputs["tex"]) | {_rel(p, paper_dir) for p in src["tex_files"]})
            ctx.verbatim_blob = src["verbatim_blob"]
            tex_res, _ = scan_sources(src["expanded"], ctx, paper_dir, pol, None)
            findings += tex_res + _xref_findings(src, ctx)
    for missing, reason, inst in (
            (text_missing_pdfs, "pdf_text_backend_missing",
             "pip install pymupdf (or pypdf), or install poppler-utils (pdftotext)"),
            (text_empty_pdfs, "pdf_text_empty",
             "the PDF has no extractable text (outlined or Type 3 fonts without a Unicode map, or scanned pages); "
             "rebuild it with real text")):
        if not missing:
            continue
        core_requested = [cid for cid in CORE_TEXT_CHECKS if cid in enabled]
        for cid in core_requested:
            skip(cid, reason, "BLOCKED", inst)
        for cid in TEXT_ADVISORY_CHECKS + ("PAGE-LIMIT", "PAGE-FILL", "ANON-AUTHOR", "TEXT-INVISIBLE", "TEXT-INJECT"):
            if cid in enabled:
                skip(cid, reason, "WARN", inst)
        if core_requested:  # fail closed only for checks that were asked for
            blocked.append(reason)
    # supplements
    supp_docs: List[Tuple[str, str, str]] = []
    pdf_joined = " ".join(pdf_text_all)
    if pdf_joined:
        n_cjk = len(_CJK_RE.findall(pdf_joined))
        n_lat = len(re.findall(r"[A-Za-z]", pdf_joined))
        ctx.paper_script = "cjk" if n_cjk > 0.2 * max(1, n_cjk + n_lat) else "latin"
    snap_supp: List[Dict[str, Any]] = []
    codename_cands: Counter = Counter()
    codename_structural: Set[str] = set()
    for sp in a.supp or []:
        sp_abs = os.path.abspath(sp)
        cap: Optional[Dict[str, Any]] = {} if (work_dir and (run_mode == "fix" or track_edits)) else None
        sf, sinfo = scan_supp(sp_abs, ctx, paper_dir, supp_max_mb, capture=cap)
        findings += sf
        supp_docs += sinfo.pop("docs", [])
        for tok, n in (sinfo.pop("codename_candidates", None) or {}).items():
            codename_cands[tok] += n
        codename_structural.update(sinfo.pop("codename_structural", None) or [])
        inputs["supp"].append(sinfo)
        add_hash(sp_abs)
        if cap is not None:
            snap_supp.append({"archive": sinfo.get("path"), "capture": cap})
        if sinfo.get("unreadable"):
            blocked.append("supp_unreadable")
        if sinfo.get("shallow_data_members"):
            notes.append("%s: %d data member(s) larger than %d MB were checked for identity terms, home paths, "
                         "secrets, and run timestamps only" % (sinfo["path"], sinfo["shallow_data_members"],
                                                               MAX_SUPP_DATA_DEEP_CHARS // 1048576))
    # code-name candidates: a lower-case project name from the supplement's layout (its
    # top folder, a package folder, a /path/to/<name> placeholder) that the paper's text
    # uses is a candidate (WARN); one that only recurs in the supplement is INFO
    reported_names: Set[str] = set()
    pdf_by_page = pdf_pages_text
    if ctx.anonymous and ctx.on("ANON-CODENAME") and codename_cands and pdf_joined:
        pdf_low = pdf_joined.lower()
        for tok, n in sorted(codename_cands.items()):
            rx_exact = re.compile(r"(?<![A-Za-z0-9_-])%s(?![A-Za-z0-9_-])" % re.escape(tok))
            in_pdf = [(art, pg, m_) for art, pg, txt in pdf_by_page for m_ in [rx_exact.search(txt)] if m_]
            if (tok in codename_structural and tok == tok.lower() and len(tok) >= 4 and in_pdf
                    and tok.lower() not in _GENERIC_PACKAGES and tok.lower() not in _GENERIC_NAMES):
                art, pg, m_ = in_pdf[0]
                txt = next(t for a_, p_, t in pdf_by_page if a_ == art and p_ == pg)
                findings.append(make_finding(
                    ctx, "ANON-CODENAME", WARN, CANDIDATE, "pdf", tok,
                    "%s (the supplement's layout names it; the paper's text uses it on %d page(s))" % (
                        _excerpt(txt, m_.start(), m_.end()), len({(x[0], x[1]) for x in in_pdf})),
                    {"artifact": art, "page": pg}))
                reported_names.add(tok)
            elif n >= 2 and not re.search(r"(?<![A-Za-z0-9])%s(?![A-Za-z0-9])" % re.escape(tok.lower()), pdf_low):
                findings.append(make_finding(
                    ctx, "ANON-CODENAME", INFO, CANDIDATE, "supp", tok,
                    "in %d supplementary member(s) or names, never in the PDF" % n,
                    {"artifact": inputs["supp"][0].get("path") if inputs["supp"] else None}))
                reported_names.add(tok)
    for tok in ctx.persisted_codenames:
        if tok in reported_names or not ctx.anonymous:
            continue
        rx_tok = re.compile(r"(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_])" % re.escape(tok), re.I)
        in_pdf = [(art, pg) for art, pg, txt in pdf_by_page if rx_tok.search(txt)]
        n_supp = ctx.codename_hits.get(tok, 0)
        if in_pdf or n_supp:
            where_m = ctx.codename_where.get(tok) or []
            findings.append(make_finding(
                ctx, "ANON-CODENAME", WARN if in_pdf else INFO, CANDIDATE, "pdf" if in_pdf else "supp", tok,
                "an earlier round reported this name; still in %d PDF page(s) and %d supplementary place(s)%s" % (
                    len(in_pdf), n_supp, (": " + ", ".join(where_m[:4])) if where_m else ""),
                {"artifact": in_pdf[0][0] if in_pdf else (inputs["supp"][0].get("path") if inputs["supp"] else None),
                 "page": in_pdf[0][1] if in_pdf else None, "member": None if in_pdf else (where_m[0] if where_m else None)},
                note="carried: a code name found by an earlier round stays reported while any occurrence is left"))
    # baseline: NUM-DRIFT / CONFIG-CHANGED / FIX-REGRESSION (against round 0 and the previous round)
    prev_layouts: Dict[str, Dict[str, Any]] = {}
    if getattr(a, "previous", None):
        prev = _load_json(a.previous)
        if not isinstance(prev, dict):
            raise UsageError("cannot read --previous (a scan JSON of the previous fix round)")
        for p in (prev.get("inputs") or {}).get("pdf") or []:
            if isinstance(p.get("layout"), dict):
                prev_layouts[str(p.get("path"))] = p["layout"]
    if a.baseline:
        findings += _baseline_findings(a.baseline, numbers_out, cfg, ctx, a.backend, invisible, pol, paper_dir,
                                       num_texts, numbers_all_out, layouts, ledger, run_mode, prev_layouts)
    # the fix loop's memory: a snapshot of the sources this round audited, and the
    # whitelist check of every edit since round 0 (fix rounds and the recheck)
    snapshot: Optional[Dict[str, Any]] = None
    edits_doc: Optional[Dict[str, Any]] = None
    if work_dir and (run_mode == "fix" or track_edits):
        paper_files = sorted({p for s in source_cache.values() for p in s["closure"]
                              if p.lower().endswith(_SNAP_SRC_EXTS)})
        snapshot = write_snapshot(work_dir, paper_dir, paper_files, snap_supp)
    if track_edits and snapshot:
        base_doc = _load_json(a.baseline)
        bdir, bman = _snapshot_manifest(base_doc if isinstance(base_doc, dict) else {}, paper_dir)
        cdir, cman = _snapshot_manifest({"snapshot": snapshot}, paper_dir)
        if bman and cman:
            items, unreadable = diff_snapshots(bdir, bman, cdir, cman)
            ec = edit_check_for(list(source_cache.values()), ctx.redactor,
                                _load_json(os.path.join(work_dir, FIX_HISTORY_NAME)))
            edits_doc = check_edits(items, ec, ctx.redactor)
            raw_edits = edits_doc.pop("_raw")
            edits_doc["unreadable"] = [{"member": ctx.redactor.redact(u["member"]), "archive": u.get("archive"),
                                        "why": u["why"]} for u in unreadable]
            _write_atomic(os.path.join(work_dir, "edits_check.raw.json"),
                          json.dumps(raw_edits, ensure_ascii=False) + "\n")
            if ctx.on("FIX-EDIT"):
                findings += fix_edit_findings(edits_doc, ctx)
            # a phrase the paper lost by a verified deletion, still in a supplementary note
            for it in edits_doc["items"]:
                if it.get("kind") != "paper" or it.get("verdict") != "ok" or "delete" not in str(it.get("fix_class")):
                    continue
                gone = raw_edits.get(it["id"]) or {}
                for phrase in _removed_phrases(gone.get("before") or "", gone.get("after") or ""):
                    mems = sorted({m for m, _k, t in supp_docs if _norm_quote(phrase) in _norm_quote(t)})
                    if mems and ctx.on("SUPP-TEXT"):
                        findings.append(make_finding(
                            ctx, "SUPP-TEXT", WARN, CANDIDATE, "supp", "fixed in the paper, still in the supplement",
                            "%s (removed from %s; still in %s)" % (phrase[:120], it.get("where"), ", ".join(mems[:4])),
                            {"artifact": inputs["supp"][0].get("path") if inputs["supp"] else None, "member": mems[0]},
                            note="apply the same deletion to the supplementary copy, or say why the copy differs"))
        else:
            notes.append("no round-0 snapshot in --baseline: the edits since round 0 were not checked "
                         "(run round 0 with --run-mode fix --work-dir)")
    carried: List[Dict[str, Any]] = []
    if isinstance(fix_state, dict):
        carried = carried_findings(fix_state, page_norms, [(m, _norm_quote(t)) for m, _k, t in supp_docs],
                                   inputs["supp"][0].get("path") if len(inputs["supp"]) == 1 else None)
    # one SKIP-<CHECK> finding per coverage gap (a check that should have run)
    for s in skipped:
        if s["cap"] in ("WARN", "BLOCKED"):
            findings.append(_skip_finding(ctx, s))
    # allow-list and policy exempt_terms (every suppression is on the record)
    applied, refused = apply_allow(findings, cfg["allow_entries"], ctx)
    for i, term in enumerate(exempt_terms, 1):
        n = ctx.exempt_used.get(str(i), 0)
        if n:
            applied.append({"line": "policy.exempt_terms[%d]" % i, "check": "candidates", "approved_by": "policy.json",
                            "removed_severity": WARN, "reason": "%d candidate hit(s) on '%s' not reported"
                            % (n, ctx.redactor.redact(term))})
        elif "ALLOW-UNUSED" in enabled:
            findings.append(make_finding(ctx, "ALLOW-UNUSED", INFO, DEFINITE, "config", "policy exempt_terms[%d]" % i,
                                         "matched nothing in this run", {}))
    for e in cfg["allow_entries"]:
        if not e["used"] and "ALLOW-UNUSED" in enabled:
            findings.append(make_finding(ctx, "ALLOW-UNUSED", INFO, DEFINITE, "config", "allow.tsv line %d" % e["line"],
                                         "matched nothing in this run", {}))
    for r in refused:
        if "ALLOW-INVALID" in enabled:
            findings.append(make_finding(ctx, "ALLOW-INVALID", WARN, DEFINITE, "config", "allow.tsv line %d" % r["line"],
                                         r["problem"], {}))
    groups = group_findings(findings)
    blocked_u = sorted(set(blocked), key=blocked.index)
    verdict, reason = tier_a_verdict(findings, blocked_u, skipped, ctx.strict, nothing)
    reasons = verdict_reasons(findings, blocked_u, skipped, ctx.strict, "skipped", nothing)
    counts = _counts(findings)
    lenses_all = ["triage", "engineering"] + (["anonymity"] if ctx.anonymous else []) + \
                 (["statements"] if end_matter_seen else [])
    doc_out: Dict[str, Any] = {
        "tool": TOOL, "tool_version": TOOL_VERSION, "generated_at": t0, "run_mode": run_mode,
        "anonymous": ctx.anonymous, "strict": ctx.strict, "hardware": ctx.hardware.lower(),
        "framework": ctx.framework.lower(), "supp_hardware": (ctx.supp_hardware or INFO).lower(), "lenses": lenses_all,
        "declared_ai_uses_set": bool(pol.get("declared_ai_uses")),
        "inputs": inputs, "input_hashes": hashes,
        "config_hashes": {k: cfg["sha256"][k] for k in ("anon_names", "allow", "policy")},
        "backends": backends,
        "checks_run": sorted(enabled),
        "checks_skipped": skipped,
        "counts": counts, "groups": groups,
        "findings": [_public(f) for f in findings],
        "exemptions_applied": applied,
        "allow_issues": cfg["allow_issues"] + refused,
        "page_geometry": page_geo, "regions": regions_out,
        "numbers": numbers_out, "numbers_all": numbers_all_out,
        "policy": {"hardware": ctx.hardware.lower(), "framework": ctx.framework.lower(),
                   "supp_hardware": (ctx.supp_hardware or INFO).lower(), "precision_disclosure": ctx.precision,
                   "registration_labels": ctx.reg_labels},
        "snapshot": snapshot, "edits_check": edits_doc, "carried_findings": carried,
        "blocked": blocked_u, "notes": notes,
        "verdict_tier_a": verdict, "reason_code": reason, "reasons": reasons,
        "summary": _summary_line(verdict, reason, counts, len(groups), reasons),
        "review_input": None,
    }
    if a.work_dir:
        if supp_docs or os.path.isdir(os.path.join(a.work_dir, "supp_docs")):
            # the reviewer reads every file in supp_docs/: drop what an earlier scan wrote
            sd = os.path.join(a.work_dir, "supp_docs")
            os.makedirs(sd, exist_ok=True)
            for fn in os.listdir(sd):
                if re.match(r"^\d{2,4}_.*\.txt$", fn):
                    with contextlib.suppress(OSError):
                        os.remove(os.path.join(sd, fn))
            index = []
            for i, (name, kind, text) in enumerate(supp_docs, 1):
                tag = "" if kind == "doc" else "." + kind.replace(" ", "_")
                safe = re.sub(r"[^\w.-]+", "_", name + tag)[-80:]
                fp = os.path.join(sd, "%03d_%s.txt" % (i, safe))
                _write_atomic(fp, "%s%s (%s) ===\n%s" % (_SUPP_DOC_HEADER, name, kind, text))
                index.append({"file": _rel(fp, paper_dir), "member": name, "kind": kind})
            inputs["supp_docs"] = index
        inputs["supp_batches"] = write_supp_batches(a.work_dir, paper_dir, supp_docs, doc_out["policy"])
        ri = build_review_input(doc_out, pol, ledger)
        rp = os.path.join(a.work_dir, "review_input.json")
        _write_atomic(rp, json.dumps(ri, ensure_ascii=False, indent=2) + "\n")
        doc_out["review_input"] = _rel(rp, paper_dir)
    return doc_out


def _skip_finding(ctx: ScanContext, s: Dict[str, Any]) -> Dict[str, Any]:
    f = make_finding(ctx, "SKIP-" + s["check"], WARN, DEFINITE, "skip", s["check"],
                     "%s%s" % (s["reason"], ("; " + s["hint"]) if s.get("hint") else ""), {})
    f["rule"] = "Check %s did not run (%s); the verdict is capped at %s." % (s["check"], s["reason"], s["cap"])
    f["route"] = "install a backend or provide the missing input"
    f["suggestion"] = s.get("hint") or "Provide the missing input and re-run."
    return f


def _load_sources(main_tex: str, paper_dir: str, ctx: ScanContext, pol: Dict[str, Any]) -> Dict[str, Any]:
    expanded = expand_tex(main_tex, paper_dir)
    main_dir = expanded["main_dir"]
    stem = os.path.splitext(os.path.basename(main_tex))[0]
    text_all = "\n".join(ln["text"] for ln in expanded["lines"] if not ln["verbatim"])
    bib_files: List[str] = []
    for m in list(_BIBLIO_RE.finditer(text_all)) + list(_ADDBIB_RE.finditer(text_all)):
        for name in _split_keys(m.group(1)):
            cand = name if name.endswith(".bib") else name + ".bib"
            p = os.path.join(main_dir, cand)
            if os.path.isfile(p):
                bib_files.append(p)
    bib_files = sorted(set(bib_files))
    bib_entries: Dict[str, str] = {}
    for b in bib_files:
        bib_entries.update(parse_bib(b))
    aux_path = _find_sidecar(stem, [main_dir], ".aux")
    bbl_path = _find_sidecar(stem, [main_dir], ".bbl")
    aux = parse_aux([aux_path] if aux_path else [])
    # xr / xr-hyper: labels of an \externaldocument live in ITS .aux
    external_missing = False
    for m in re.finditer(r"\\externaldocument\s*(?:\[([^\]]*)\])?\s*\{([^{}]+)\}", text_all):
        name = m.group(2).strip()
        ext_aux = _find_sidecar(os.path.basename(name), [os.path.join(main_dir, os.path.dirname(name))], ".aux")
        if not ext_aux:
            external_missing = True
            continue
        aux["labels"] |= {(m.group(1) or "") + k for k in parse_aux([ext_aux])["labels"]}
    bbl_keys = parse_bbl(bbl_path) if bbl_path else set()
    known: Optional[Set[str]] = None
    if bib_files or bbl_keys:
        known = set(bib_entries) | bbl_keys
    xref = static_xref(expanded, aux, known)
    xref["external_missing"] = external_missing
    # graphics and local style files (freshness closure)
    gpaths = [""]
    for m in _GRAPHICSPATH_RE.finditer(text_all):
        gpaths += re.findall(r"\{([^{}]*)\}", m.group(1))
    figs: List[str] = []
    for m in _GRAPHICS_RE.finditer(text_all):
        name = m.group(1).strip()
        for gp in gpaths:
            base = os.path.join(main_dir, gp, name)
            for ext in ("", ".pdf", ".png", ".jpg", ".jpeg", ".eps"):
                if os.path.isfile(base + ext):
                    figs.append(base + ext)
                    break
            else:
                continue
            break
    styles: List[str] = []
    for m in _USEPKG_RE.finditer(text_all):
        for name in _split_keys(m.group(1)):
            for ext in (".sty", ".cls"):
                p = os.path.join(main_dir, name + ext)
                if os.path.isfile(p):
                    styles.append(p)
    for m in _BIBSTYLE_RE.finditer(text_all):
        p = os.path.join(main_dir, m.group(1).strip() + ".bst")
        if os.path.isfile(p):
            styles.append(p)
    closure = sorted(set(expanded["files"]) | set(bib_files) | set(figs) | set(styles))
    verb = []
    for ln in expanded["lines"]:
        if ln["verbatim"]:
            verb.append(ln["text"])
    return {"main": main_tex, "expanded": expanded, "tex_files": expanded["files"], "bib_files": bib_files,
            "bib_entries": bib_entries, "aux": aux_path, "bbl": bbl_path, "xref": xref, "closure": closure,
            "verbatim_blob": "\n".join(verb), "figs": sorted(set(figs)),
            "label_types": aux_label_types([aux_path]) if aux_path else {}}


def _figure_file_findings(figs: Sequence[str], paper_dir: str, ctx: ScanContext) -> List[Dict[str, Any]]:
    """META-FIGURE (INFO) for the figure PDFs the sources include: their own
    Info dictionary ships with any source upload (arXiv, camera-ready)."""
    out: List[Dict[str, Any]] = []
    if not ctx.on("META-FIGURE"):
        return out
    for fig in figs:
        if not fig.lower().endswith(".pdf"):
            continue
        try:
            if os.path.getsize(fig) > MAX_STREAM_BYTES:
                continue
            with open(fig, "rb") as fh:
                doc = parse_pdf_objects(fh.read())
        except Exception:  # noqa: BLE001 — a figure that cannot be parsed is not a finding here
            continue
        for key, val in figure_meta_issues(pdf_info(doc), ctx.anonymous):
            out.append(make_finding(ctx, "META-FIGURE", INFO, DEFINITE, "tex", "%s=%s" % (key, val[:120]),
                                    "figure file Info /%s" % key, {"file": _rel(fig, paper_dir)},
                                    note="ships only with a source upload (arXiv, camera-ready sources)",
                                    nodemote=True))
    return out


def _xref_findings(src: Dict[str, Any], ctx: ScanContext) -> List[Dict[str, Any]]:
    """XREF-SRC-REF / XREF-SRC-CITE, with what a conservative fix may do: a
    reference gets `fix_target` only when exactly one defined label of the same
    kind is close to the key; a dangling cite key gets `fix_drop` only inside a
    multi-key \\cite and with no similar key in any bibliography (a probable
    typo, or a single-key \\cite, is for a person)."""
    out = []
    x = src["xref"]
    lines = {(ln["file"], ln["line"]): ln["text"] for ln in src["expanded"]["lines"]}
    types = src.get("label_types") or {}
    if ctx.on("XREF-SRC-REF"):
        for key, (f, line_no) in sorted(x["undefined_refs"].items()):
            why = ("macro-generated labels exist and no .aux was found" if x["macro_labels"] and not src["aux"] else
                   "an \\externaldocument has no compiled .aux to check against" if x.get("external_missing") else None)
            fd = make_finding(ctx, "XREF-SRC-REF", WARN if why else BLOCK, CANDIDATE if why else DEFINITE,
                              "tex", key, "\\ref{%s} has no \\label" % key, {"file": f, "line": line_no}, note=why)
            target, close, kind = xref_fix_target(key, lines.get((f, line_no), ""), x.get("defined_labels") or [],
                                                  types)
            # every place the key is referenced: a repair changes them all, and the plan names them all
            places = [(pf, pl) for pf, pl in (x.get("ref_places") or {}).get(key) or [(f, line_no)]]
            fd["ref_places"] = ["%s:%s" % (pf, pl) for pf, pl in places][:20]
            bits = [fd.get("note")]
            if close:
                fd["close_labels"] = [ctx.redactor.redact(c_) for c_ in close[:3]]
                bits.append(ctx.redactor.redact("closest labels: " + ", ".join(close[:3])))
            if target and not why:
                fd["fix_target"] = target
                bits.append("the one %s label close to it: %s" % (kind, ctx.redactor.redact(target)))
            else:
                bits.append("no unique close label of the same kind%s: a person points the reference"
                            % (" (%s)" % kind if kind else ""))
            fd["note"] = "; ".join(b for b in bits if b)
            out.append(fd)
    if ctx.on("XREF-SRC-CITE") and x["bib_known"]:
        import difflib
        for key, (f, line_no) in sorted(x["undefined_cites"].items()):
            fd = make_finding(ctx, "XREF-SRC-CITE", BLOCK, DEFINITE, "tex+bib", key,
                              "\\cite{%s} has no bibliography entry" % key, {"file": f, "line": line_no},
                              note=ctx.redactor.redact(cite_key_note(key, x)))
            similar = difflib.get_close_matches(key, x.get("defined_keys") or [], n=1, cutoff=0.75)
            if (x.get("cite_sizes") or {}).get(key, 1) > 1 and not similar:
                fd["fix_drop"] = True
            out.append(fd)
    return out


def _pdf_key_findings(pages: List[Dict[str, Any]], src: Dict[str, Any], ctx: ScanContext,
                      artifact: str) -> List[Dict[str, Any]]:
    out = []
    keys = [k for k in src["xref"]["undefined_cites"] if len(k) >= 4 and re.search(r"[\d:_]", k)]
    for k in keys:
        rx = re.compile(r"(?<![\w:/.-])" + re.escape(k) + r"(?![\w:/.-])")
        for p in pages:
            for s in p["segs"]:
                m = rx.search(s["text"])
                if m:
                    out.append(make_finding(ctx, "XREF-PDF-KEY", BLOCK, DEFINITE, "pdf", k, _excerpt(s["text"], m.start(), m.end()),
                                            {"artifact": artifact, "page": p["page"]}))
                    break
            else:
                continue
            break
    return out




def _page_findings(geo: Dict[str, Any], page_limit: Optional[int], fill_page: Optional[int], thr: float,
                   ctx: ScanContext, artifact: str, skipped: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    wants = [c for c, v in (("PAGE-LIMIT", page_limit), ("PAGE-FILL", fill_page)) if v is not None and ctx.on(c)]
    if not wants:
        return out
    if geo.get("status") != "ok":
        reason = "no_block_geometry_backend" if geo.get("status") == "no_bbox" else "body_end_heading_not_found"
        for c in wants:
            if not any(s["check"] == c for s in skipped):
                skipped.append({"check": c, "reason": reason, "cap": "WARN",
                                "hint": "pip install pymupdf, or install poppler-utils" if reason.startswith("no_block") else
                                "set policy body_end_markers to the heading that ends the main body"})
        return out
    end_page, fill = geo["body_end_page"], geo["fill"]
    if "PAGE-LIMIT" in wants and end_page > int(page_limit):
        out.append(make_finding(ctx, "PAGE-LIMIT", BLOCK, DEFINITE, "pdf-geometry", "body ends on page %d" % end_page,
                                "limit %d; next heading '%s'" % (int(page_limit), geo.get("end_heading")),
                                {"artifact": artifact, "page": end_page}))
    if "PAGE-FILL" in wants:
        n = int(fill_page)
        if not (end_page == n and fill >= thr):
            out.append(make_finding(ctx, "PAGE-FILL", WARN, DEFINITE, "pdf-geometry",
                                    "body ends on page %d at %.0f%% fill" % (end_page, fill * 100),
                                    "required: page %d with fill >= %.0f%%; about %d line(s) short" % (n, thr * 100, geo["lines_short"]),
                                    {"artifact": artifact, "page": end_page}))
    return out


def _render_pdf_text(pages: List[Dict[str, Any]], ctx: ScanContext) -> str:
    parts = []
    for p in pages:
        parts.append("=== page %d ===" % p["page"])
        for s in p["segs"]:
            parts.append(ctx.redactor.redact(s["text"]))
            parts.append("")
    return "\n".join(parts) + "\n"


def _log_findings(log_path: Optional[str], pdf_mtime: float, run_mode: str, ctx: ScanContext, paper_dir: str,
                  inputs: Dict[str, Any], skipped: List[Dict[str, Any]], src: Optional[Dict[str, Any]],
                  add_hash: Any, has_sources: bool, pdf_name: Optional[str] = None,
                  pdf_pages: Optional[int] = None, notes: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Build-log findings, only when the log belongs to the audited PDF: written
    within 60 s of it, or (the PDF was post-processed or copied after the build,
    so it is newer) the log's 'Output written on <name>.pdf (N pages' names the
    same file stem and page count. A log newer than the PDF is never bound."""
    log_checks = [c for c in CHECKS if c.startswith(("XREF-LOG-", "LOG-"))]
    out: List[Dict[str, Any]] = []

    def skip_all(reason: str, cap: Optional[str]) -> None:
        for c in log_checks:
            if ctx.on(c) and not any(s["check"] == c for s in skipped):
                skipped.append({"check": c, "reason": reason, "cap": cap, "hint": None})
    if not log_path or not os.path.isfile(log_path):
        skip_all("log_missing", "WARN" if has_sources else None)
        return out
    lm = _mtime(log_path) or 0.0
    rel = _display_path(log_path, paper_dir)
    with open(log_path, "rb") as fh:
        text = unwrap_log(fh.read(), getattr(ctx, "log_wrap", 79))
    res = scan_log(text)
    bound = abs(lm - pdf_mtime) <= 60 if run_mode == "recheck" else lm >= pdf_mtime - 60
    by_output = False
    if not bound and lm <= pdf_mtime + 60 and res.get("output") and pdf_name and pdf_pages:
        outp = res["output"]
        same_stem = os.path.splitext(outp["pdf"])[0] == os.path.splitext(pdf_name)[0]
        if same_stem and outp["pages"] == pdf_pages:
            bound = by_output = True
            if notes is not None:
                notes.append("%s: the PDF is newer than its build log (post-processed or copied); the log was bound "
                             "by its 'Output written on' file name and page count" % rel)
    inputs["log"].append({"path": rel, "fresh": bound, "bound_by": "output_line" if by_output else
                          ("mtime" if bound else None)})
    if not bound:
        skip_all("log_not_bound_to_pdf" if run_mode == "recheck" else "log_stale", "WARN")
        return out
    add_hash(log_path)
    refd = set(src["xref"]["refs"]) if src else set()
    for h in res["hits"]:
        if not ctx.on(h["check"]):
            continue
        sev, note = BLOCK, None
        if h["check"] == "XREF-LOG-MULTI":
            sev = BLOCK if h["match"] in refd else WARN
        elif h["check"] == "XREF-LOG-DEST":
            sev = WARN
        elif h.get("outlines"):
            sev, note = WARN, "only the PDF bookmarks (outlines) are stale; references are unaffected"
        out.append(make_finding(ctx, h["check"], sev, DEFINITE, "log", h["match"], h["excerpt"],
                                {"artifact": rel, "line": h["line"]}, note=note))
    if ctx.on("LOG-ERROR"):
        for h in res["errors"]:
            out.append(make_finding(ctx, "LOG-ERROR", BLOCK, DEFINITE, "log", h["match"], h["excerpt"],
                                    {"artifact": rel, "line": h["line"]}))
    if ctx.on("LOG-OVERFULL") and res["overfull"]:
        out.append(make_finding(ctx, "LOG-OVERFULL", WARN, DEFINITE, "log", "%d overfull box(es)" % len(res["overfull"]),
                                "worst %.1fpt" % max(res["overfull"]), {"artifact": rel}))
    if ctx.on("LOG-GLYPH"):
        for h in res["glyphs"]:
            out.append(make_finding(ctx, "LOG-GLYPH", WARN, DEFINITE, "log", h["match"], h["excerpt"],
                                    {"artifact": rel, "line": h["line"]}))
    ctx.loaded_styles = res["loaded_paths"]  # type: ignore[attr-defined]
    return out


def _blg_findings(blg_path: Optional[str], pdf_mtime: float, run_mode: str, ctx: ScanContext, paper_dir: str,
                  inputs: Dict[str, Any], src: Optional[Dict[str, Any]], add_hash: Any) -> List[Dict[str, Any]]:
    if not ctx.on("XREF-BLG") or not blg_path or not os.path.isfile(blg_path):
        return []
    bm = _mtime(blg_path) or 0.0
    rel = _display_path(blg_path, paper_dir)
    if run_mode == "recheck":
        bound = pdf_mtime - 3600 <= bm <= pdf_mtime + 60
    else:
        newest_bib = max([_mtime(p) or 0.0 for p in (src["bib_files"] if src else [])] or [0.0])
        bound = bm >= newest_bib
    inputs["blg"].append({"path": rel, "fresh": bound})
    if not bound:
        return []
    add_hash(blg_path)
    x = src["xref"] if src else {}

    def note(key: str) -> Optional[str]:
        return ctx.redactor.redact(cite_key_note(key, x)) if key in (x.get("cites") or {}) else None
    return [make_finding(ctx, "XREF-BLG", BLOCK, DEFINITE, "blg", h["match"], h["excerpt"], {"artifact": rel, "line": h["line"]},
                         note=note(h["match"]))
            for h in scan_blg(_read_text(blg_path))]


def _style_findings(style_ref: str, paper_dir: str, ctx: ScanContext) -> List[Dict[str, Any]]:
    """Byte-compare the local .sty/.cls/.bst copies with the official ones."""
    out = []
    if not os.path.isdir(style_ref):
        raise UsageError("--style-ref is not a directory: %s" % style_ref)
    for fn in sorted(os.listdir(style_ref)):
        if not fn.endswith((".sty", ".cls", ".bst")):
            continue
        local = os.path.join(paper_dir, fn)
        if not os.path.isfile(local):
            continue
        if _sha256_file(local) != _sha256_file(os.path.join(style_ref, fn)):
            out.append(make_finding(ctx, "TPL-STYLE", BLOCK, DEFINITE, "tex+log", fn, "differs from the official file",
                                    {"file": _rel(local, paper_dir)}))
    return out


def _pick(d: Dict[str, Any], art: str) -> Any:
    """The baseline entry for an artifact: same path, '*', or the only one."""
    v = d.get(art) or d.get("*")
    if v is None and len(d) == 1:
        v = next(iter(d.values()))
    return v


def _baseline_findings(baseline: str, numbers_out: Dict[str, Dict[str, int]], cfg: Dict[str, Any], ctx: ScanContext,
                       backend: str, invisible: frozenset, pol: Dict[str, Any], paper_dir: str,
                       num_texts: Optional[Dict[str, Dict[str, str]]] = None,
                       numbers_all: Optional[Dict[str, Dict[str, int]]] = None,
                       layouts: Optional[Dict[str, Dict[str, Any]]] = None,
                       ledger: Optional[Dict[str, Any]] = None, run_mode: str = "fix",
                       prev_layouts: Optional[Dict[str, Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """NUM-DRIFT, CONFIG-CHANGED (fix rounds only), and FIX-REGRESSION against
    the round-0 scan. With the text frozen at round 0 (numtext.<stem>.r0.json),
    every drifting number carries the sentence it left or arrived in. A number
    only stops the loop when nothing explains it:
      - it moved between the counted text and the references or checklist (a
        float placed after the references): INFO, `moved`;
      - it left with the sentence or clause of a confirmed leak (a definite
        finding, a candidate ruled leak or reword, a blocking reviewer finding —
        the rulings ledger knows which): INFO, `confirmed_deletion`, not sent
        to the reviewer (the change review judges what the deletion lost);
      - an integer that left with a clause holding an unconfirmed baseline
        finding: INFO, `explained`, still shown to the reviewer.
    Decimals and percentages are explained only by a confirmed deletion."""
    out: List[Dict[str, Any]] = []
    if not os.path.isfile(baseline):
        raise UsageError("--baseline not found: %s" % baseline)
    explained: Counter = Counter()
    base_numbers: Dict[str, Counter] = {}
    base_all: Dict[str, Counter] = {}
    base_texts: Dict[str, Dict[int, str]] = {}
    base_layouts: Dict[str, Dict[str, Any]] = {}
    base_fs: List[Dict[str, Any]] = []
    confirmed_fs: List[Dict[str, Any]] = []
    if baseline.lower().endswith(".pdf"):
        ext = extract_pdf(baseline, backend)
        if ext["pages"]:
            pages = normalize_pages(ext["pages"], invisible)
            detect_regions(pages, pol)
            base_numbers["*"] = number_multiset(pages)
            base_all["*"] = number_multiset_all(pages)
            base_texts["*"] = {int(k): v for k, v in number_text(pages, ctx).items()}
    else:
        try:
            b = json.loads(_read_text(baseline))
        except ValueError:
            raise UsageError("--baseline is neither a PDF nor a scan JSON") from None
        for art, toks in (b.get("numbers") or {}).items():
            base_numbers[art] = Counter(toks)
        for art, toks in (b.get("numbers_all") or {}).items():
            base_all[art] = Counter(toks)
        for f in b.get("findings") or []:
            for m in _NUM_TOKEN_RE.finditer(str(f.get("match") or "")):
                explained[m.group(0).replace("−", "-").rstrip(".,")] += 1
        base_fs = [f for f in b.get("findings") or [] if isinstance(f, dict) and (f.get("location") or {}).get("page")
                   and not str(f.get("check", "")).startswith(("NUM-", "CONFIG-", "SKIP-", "ALLOW-", "FIX-"))]
        ckeys = confirmed_ledger_keys(ledger or {})
        for f in base_fs:
            if ((f.get("certainty") == DEFINITE and f.get("severity") != INFO)
                    or stable_key(f.get("check"), f.get("match"), f.get("region"), f.get("subregion")) in ckeys):
                confirmed_fs.append(f)
        for e in ((ledger or {}).get("entries") or {}).values():
            if e.get("reviewer_finding") and e.get("page") and e.get("match"):
                confirmed_fs.append({"check": e.get("check"), "match": e.get("match"),
                                     "location": {"page": e.get("page"), "artifact": e.get("artifact")}})
        for p in (b.get("inputs") or {}).get("pdf") or []:
            rel = p.get("baseline_numtext")
            full = (rel if os.path.isabs(rel) else os.path.join(paper_dir, rel)) if rel else None
            if full and os.path.isfile(full):
                with contextlib.suppress(ValueError, OSError, TypeError, AttributeError):
                    pages_b = json.loads(_read_text(full)).get("pages") or {}
                    base_texts[str(p.get("path"))] = {int(k): str(v) for k, v in pages_b.items()}
            if isinstance(p.get("layout"), dict):
                base_layouts[str(p.get("path"))] = p["layout"]
        if ctx.on("CONFIG-CHANGED") and run_mode != "recheck":
            old = b.get("config_hashes") or {}
            for k in ("anon_names", "allow", "policy"):
                if old.get(k) != cfg["sha256"].get(k):
                    out.append(make_finding(ctx, "CONFIG-CHANGED", BLOCK, DEFINITE, "config", k,
                                            "changed since the baseline scan", {}))
    confirmed_ids = {id(f) for f in confirmed_fs}
    if ctx.on("NUM-DRIFT"):
        for art, cur in numbers_out.items():
            base = _pick(base_numbers, art)
            if base is None:
                continue
            ball = _pick(base_all, art)
            call = Counter(numbers_all[art]) if (ball is not None and numbers_all and art in numbers_all) else None
            bt = _pick(base_texts, art)
            ct = {int(k): v for k, v in ((num_texts or {}).get(art) or {}).items()}
            mine = [f for f in base_fs if (f.get("location") or {}).get("artifact") in (art, None)]
            conf_n: Counter = Counter()
            conf_at: Dict[str, Tuple[int, str]] = {}
            by_clause: Counter = Counter()
            clause_at: Dict[str, Tuple[int, str]] = {}
            if bt:
                conf_n, conf_at = clause_explained(
                    bt, ct, [f for f in confirmed_fs if (f.get("location") or {}).get("artifact") in (art, None)],
                    sentence=True)
                by_clause, clause_at = clause_explained(bt, ct, [f for f in mine if id(f) not in confirmed_ids])
            for d in number_drift(base, Counter(cur), explained):
                tok, left = d["token"], d["n"]
                if call is not None:
                    g = max(0, (ball[tok] - call[tok]) if d["change"] == "removed" else (call[tok] - ball[tok]))
                    moved = left - min(left, g)
                    if moved:
                        out.append(make_finding(
                            ctx, "NUM-DRIFT", INFO, d["certainty"], "pdf", tok,
                            "%s x%d in the counted text only: the number moved between the body and the references "
                            "or checklist (a float placed after the references), the whole text still has it"
                            % (d["change"], moved), {"artifact": art}, note="moved between regions", demoted="moved"))
                        left -= moved
                if left <= 0:
                    continue
                if d["change"] == "removed" and conf_n.get(tok):
                    n_c = min(left, conf_n[tok])
                    conf_n[tok] -= n_c
                    pg, clause = conf_at[tok]
                    out.append(make_finding(
                        ctx, "NUM-DRIFT", INFO, d["certainty"], "pdf", tok,
                        "removed x%d with the deleted text of a confirmed leak, p.%d: \"%s\"" % (n_c, pg, clause),
                        {"artifact": art, "page": pg},
                        note="attributed to a confirmed deletion; the change review judges whether a result was lost",
                        demoted="confirmed_deletion"))
                    left -= n_c
                if left <= 0:
                    continue
                n_cl = (min(left, by_clause.get(tok, 0))
                        if d["change"] == "removed" and d["certainty"] == CANDIDATE else 0)
                if n_cl:
                    pg, clause = clause_at[tok]
                    out.append(make_finding(ctx, "NUM-DRIFT", INFO, CANDIDATE, "pdf", tok,
                                            "removed x%d with a deleted clause that held a baseline finding, p.%d: \"%s\""
                                            % (n_cl, pg, clause), {"artifact": art, "page": pg},
                                            note="left together with a flagged clause", demoted="explained"))
                    left -= n_cl
                if left <= 0:
                    continue
                at = drift_context(tok, d["change"], bt, ct) if bt else None
                sev = BLOCK if d["certainty"] == DEFINITE else WARN
                out.append(make_finding(ctx, "NUM-DRIFT", sev, d["certainty"], "pdf", tok,
                                        "%s x%d against the baseline%s" % (
                                            d["change"], left, (", p.%d: \"%s\"" % at) if at else ""),
                                        {"artifact": art, "page": at[0] if at else None}))
    if layouts and (base_layouts or prev_layouts):
        for art, cur_l in layouts.items():
            # what this round broke (against the previous round) names the round to undo;
            # what is worse than round 0 decides which round the run may deliver
            prev = _pick(prev_layouts, art) if prev_layouts else None
            r_prev = regression_findings(prev, cur_l, art, ctx, "the previous round") if prev else []
            r_base = regression_findings(_pick(base_layouts, art), cur_l, art, ctx, "round 0") if base_layouts else []
            kinds = {f["regression"]["kind"] for f in r_prev}
            out += r_prev + [f for f in r_base if f["regression"]["kind"] not in kinds]
    return out




_GROUP_QUESTIONS = {
    "XREF-PDF-QQ": "Is this ?? text the authors typeset on purpose (code, a quoted string, a table entry), or an "
                   "unresolved reference or citation? Rule 'leak' if it is unresolved, 'false_positive' if it is "
                   "intended literal text.",
    "TEXT-CODE": "Is this code-like text intended (a labelled prompt, code, or format example) or residue of a "
                 "template, a script, or Markdown in the prose? Rule 'leak' for residue.",
    "ENG-HW": "Does a claim of the paper depend on this hardware — a speed, memory, or cost result compared on it? "
              "Rule 'necessary' only then. Context for a runtime or cost figure is not enough: an inventory "
              "('8x <model>') and the timing sentence that carries it are 'leak' outside a compute-resources section.",
    "ENG-QTY": "Is this compute accounting a result the paper compares (cost, efficiency), or setup detail? Rule "
               "'necessary' only for a compared result; GPU-hours that only give context are 'leak' outside a "
               "compute-resources section.",
    "PROC-TIME": "Is this date or time a scientific parameter (a data-collection window, a model snapshot, a cut-off "
                 "the analysis uses) or the authors' own timeline (when something was run, registered, written, or "
                 "fixed)? The timeline is 'leak' (or 'reword' to keep an ordering such as 'registered before any "
                 "analysis'); keep a calendar date only next to a public registration id or link.",
    "PROC-REVISION": "Is this revision, re-run, or round narration, or a design term of the study? Narration is "
                     "'leak'; a fact that must stay but is told as history ('one seed stopped early and was rerun') is "
                     "'reword' with a neutral rewrite that keeps the fact.",
    "SUPP-JUNK": "Does the supplementary README use this run log or runtime artifact to check a reproduction? Rule "
                 "'necessary' only then; otherwise 'leak' (re-pack without it).",
    "NUM-DRIFT": "A number left or entered the text against the round-0 baseline (the excerpt quotes the sentence). "
                 "Rule 'leak' ONLY when a reported result, count, or setting of the study itself changed or "
                 "disappeared; 'false_positive' when the number belonged to engineering or process detail that was "
                 "deleted (a run time such as 'about an hour', a clock time, a version, a hardware count) or merely moved.",
    "PROC-PENDING": "Does the text announce work that is not done (not yet evaluated, to be added, TBD)? Rule 'leak' "
                    "if so — a person then decides whether to finish it or drop the announcement; 'false_positive' "
                    "for a mathematical 'to be determined' or a released-upon-acceptance promise.",
    "SUPP-PROCFILE": "Is this member a record of the authors' process (notes, status, drafts, superseded or as-found "
                     "versions, clarifications, root-cause write-ups) rather than material the README uses to "
                     "reproduce the results? 'leak' leaves it out of the upload; 'necessary' only when the README "
                     "needs it.",
    "SUPP-PATH": "Does the package ship what this path or script reference points to? A placeholder root that the "
                 "user must fill in a README command is 'false_positive'; a placeholder that hides a private path in "
                 "code or records, or a reference to a script or folder that is not shipped, is 'leak'.",
    "SUPP-RUNTIME": "Does this code write the time of the run into its outputs (a date key, a time-stamped file "
                    "name)? 'leak' if so; a person then decides how to drop it (code logic is never changed by the "
                    "fix loop).",
    "SUPP-HW": "Does this hardware, OS, or host word tell the reader a reproduction requirement ('needs a GPU with "
               "24 GB', 'tested on Linux') — 'necessary' — or narrate the authors' own runs ('(CPU, existing "
               "records)', 'ran on our hosts') — 'leak'?",
    "ENG-FILENAME": "Does the paper's prose name a file of the code or the supplement (a README, a script, a config) "
                    "where it should describe the method or say 'the supplementary material'? 'leak' for such a file "
                    "name; 'necessary' only for an artifact the paper itself introduces; 'false_positive' when it "
                    "is not a file name.",
    "PROC-DATESEED": "Is this number a random seed or salt shaped like a calendar date (20991231)? In the paper such a "
                     "seed tells the reader when the study ran: 'leak' (describe the seeds in words; the values stay "
                     "in code); 'false_positive' when it is no seed or no date.",
    "PROC-REGLABEL": "Is this a registration amendment, addendum, or clarification label? With policy "
                     "registration_labels 'flag' the label is revision history: 'reword' to keep the timing fact it "
                     "carries ('chosen once early results were in') without the label.",
    "ENG-PRECISION": "Does a claim of the paper depend on this precision or loading detail (a precision ablation)? "
                     "'necessary' only then; otherwise 'leak' (policy precision_disclosure is 'candidate').",
    "ANON-CODENAME": "Is this lower-case token an internal project or code name (it names the supplement's folder or "
                     "package) that the paper's text uses? 'leak' if so; 'false_positive' for a method, dataset, or "
                     "an ordinary word.",
}
MAX_REVIEW_EXCERPTS = 6


def build_review_input(scan: Dict[str, Any], pol: Dict[str, Any],
                       ledger: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """What Tier B sees besides the PDF text: candidate groups only (machine
    extracted, redacted), the enabled lenses, and the author's venue policy
    fields. Never an executor summary. Candidates that a compute-resources or
    related-work section turned into INFO come along as low-priority groups:
    the section heuristic must not be the last word. A group that earlier
    rounds of this audit already ruled carries those rulings (prior_rulings,
    from the script's ledger); blocking findings an earlier round's reviewer
    reported and the text still holds come as carried_findings (C-NNN)."""
    by_group: Dict[str, List[Dict[str, Any]]] = {}
    for f in scan["findings"]:
        by_group.setdefault(f["group"], []).append(f)
    cands = []
    for g in scan["groups"]:
        if g["certainty"] != CANDIDATE:
            continue
        members = [f for f in by_group.get(g["group"], []) if not f.get("exempted_by")]
        low = g["severity"] == INFO
        if low:  # demoted by a section heuristic or by the verbatim rule: neither may be the last word
            members = [f for f in members if f.get("demoted") in _REVIEWED_DEMOTIONS]
        if not members:
            continue
        excerpts: List[str] = []
        for f in members:
            if f["excerpt"] and f["excerpt"] not in excerpts:
                excerpts.append(f["excerpt"])
            if len(excerpts) >= MAX_REVIEW_EXCERPTS:
                break
        entry = {"group": g["group"], "check": g["check"], "family": g["family"], "match": g["match"],
                 "n": len(members), "pages": g["pages"],
                 "section": "/".join(x for x in (g.get("region"), g.get("subregion")) if x) or None,
                 "priority": "low" if low else "normal",
                 "question": _GROUP_QUESTIONS.get(g["check"]) or CHECKS.get(g["check"], {}).get("rule", ""),
                 "excerpts": excerpts}
        mems = sorted({f["location"].get("member") for f in members if f["location"].get("member")})
        if mems:  # supplementary groups: which members, so the reviewer can open them in supp_docs
            entry["members"] = mems[:MAX_REVIEW_EXCERPTS]
        key = g.get("key") or stable_key(g["check"], g["match"], g.get("region"), g.get("subregion"))
        prior = prior_rulings_for_review(ledger, key) if ledger else []
        if prior:
            entry["prior_rulings"] = prior
        cands.append(entry)
    carried = [{"id": c["id"], "lens": c.get("lens"), "quote": c.get("quote"),
                ("member" if c.get("member") else "page"): c.get("member") or c.get("page"),
                "earlier_rationale": str(c.get("rationale") or "")[:300], "from": c.get("run")}
               for c in scan.get("carried_findings") or []]
    out = {"tool": TOOL, "tool_version": TOOL_VERSION, "lenses": scan["lenses"], "anonymous": scan["anonymous"],
           "venue": pol.get("venue"), "declared_ai_uses": pol.get("declared_ai_uses"),
           "venue_policy": scan.get("policy") or {},
           "pdf_text_files": [p["text_file"] for p in scan["inputs"]["pdf"] if p.get("text_file")],
           "supp_doc_files": [d["file"] for d in scan["inputs"].get("supp_docs") or []],
           "candidate_groups": cands,
           "rulings_allowed": list(_RULINGS)}
    if carried:
        out["carried_findings"] = carried
    batches = scan["inputs"].get("supp_batches") or []
    if batches:
        out["supp_batches"] = [{"file": b["file"], "members": len(b.get("members") or [])} for b in batches]
        out["supp_checklist"] = SUPP_CHECKLIST
    return out


# ─── Markdown rendering ──────────────────────────────────────────────────────

def _md_escape(s: Any) -> str:
    return str(s if s is not None else "").replace("|", "\\|").replace("\n", " ")


def _rx_escape(s: str) -> str:
    """Escape regex metacharacters only (spaces stay readable in allow.tsv)."""
    return re.sub(r"([.^$*+?{}\[\]\\|()])", r"\\\1", s)


def render_md(doc: Dict[str, Any], final: bool = False) -> str:
    """Human-readable report (Tier A or final). Matches are already redacted."""
    det = doc.get("details", doc)
    findings = det.get("findings", [])
    verdict = doc.get("verdict") or doc.get("verdict_tier_a")
    reason = doc.get("reason_code")
    lines = ["# Paper Hygiene Audit Report" if final else "# Paper Hygiene Scan (Tier A)", ""]
    lines.append("**Date**: %s" % doc.get("generated_at", ""))
    lines.append("**Mode**: %s · tiers: %s" % (det.get("run_mode", ""), "+".join(det.get("tiers_run", ["A"]))))
    if final:
        lines.append("**Reviewer**: %s (%s; %s / %s)" % (doc.get("reviewer_model"), doc.get("reviewer_reasoning"),
                                                       doc.get("review_independence"), doc.get("acceptance_status")))
    lines.append("**Verdict**: %s (`reason_code: %s`)" % (verdict, reason))
    if doc.get("summary"):
        lines.append("**Summary**: %s" % doc["summary"])
    if final:
        lines.append("**Upload-ready**: %s" % (
            "yes — a read-only recheck of these exact bytes" if det.get("upload_ready") else
            "no — %s" % ("run `— recheck` on the final PDF and archive before upload" if det.get("recheck_required")
                         else "resolve the findings below, then run `— recheck` again")))
    rs = det.get("reasons") or doc.get("reasons") or []
    if len(rs) > 1:
        lines.append("**All reasons**: %s" % ", ".join("`%s`" % r for r in rs))
    lines.append("")
    arts = det.get("artifacts") or [
        {"path": p.get("path"), "sha256": p.get("sha256"), "pages": p.get("pages")} for p in det.get("inputs", {}).get("pdf", [])]
    supp = det.get("inputs", {}).get("supp", []) if not final else det.get("supplements", [])
    if arts or supp:
        lines += ["## Audited files", "", "| File | sha256 | Pages |", "|---|---|---|"]
        for a_ in arts:
            lines.append("| %s | `%s` | %s |" % (_md_escape(a_.get("path")), (a_.get("sha256") or "")[:16], a_.get("pages") or ""))
        for s in supp:
            lines.append("| %s | `%s` | |" % (_md_escape(s.get("path")), (s.get("sha256") or "")[:16]))
        lines.append("")
    fams: Dict[str, Counter] = {}
    for f in findings:
        fams.setdefault(f["family"], Counter())[f["severity"]] += 1
    lines += ["## Summary by family", "", "| Family | BLOCK | WARN | INFO |", "|---|---|---|---|"]
    for fam in sorted(fams):
        c = fams[fam]
        lines.append("| %s | %d | %d | %d |" % (fam, c[BLOCK], c[WARN], c[INFO]))
    lines.append("")
    groups = det.get("groups", [])
    by_group: Dict[str, List[Dict[str, Any]]] = {}
    for f in findings:
        by_group.setdefault(f.get("group") or "", []).append(f)
    plan_of: Dict[str, Dict[str, Any]] = {}
    for pi in det.get("fix_plan") or []:
        for gid in pi.get("groups") or [pi.get("group")]:
            plan_of.setdefault(str(gid), pi)

    def group_block(sev: str, title: str) -> None:
        sel = [g for g in groups if any(f["severity"] == sev for f in by_group.get(g["group"], []))
               and not g["check"].startswith("SKIP-")]
        if not sel:
            return
        lines.extend(["## %s" % title, ""])
        for g in sel:
            mem = [f for f in by_group.get(g["group"], []) if f["severity"] == sev]
            f0 = mem[0]
            locs = []
            for f in mem[:6]:
                loc = f["location"]
                bits = []
                if loc.get("artifact"):
                    bits.append(loc["artifact"] + (":%s" % loc["line"] if loc.get("line") and not loc.get("file") else ""))
                if loc.get("page"):
                    bits.append("p.%s" % loc["page"])
                if loc.get("member"):
                    bits.append(loc["member"])
                if loc.get("file"):
                    bits.append("%s:%s" % (loc["file"], loc.get("line")))
                locs.append(" ".join(bits))
            lines.append("### [%s] %s ×%d — \"%s\" (%s, %s)" % (sev, g["check"], len(mem), _md_escape(g["match"])[:80],
                                                             g["group"], g["certainty"]))
            lines.append("- **Where**: %s%s" % ("; ".join(x for x in locs if x) or "—", " …" if len(mem) > 6 else ""))
            pi = plan_of.get(g["group"])
            if pi:  # one place of the text is one plan item, however many groups hit it
                others = [x for x in (pi.get("groups") or []) if x != g["group"]]
                lines.append("- **Fix plan**: %s%s%s" % (pi.get("id"), " (automatic)" if pi.get("auto") else "",
                                                        (" — one place with %s" % ", ".join(others[:6])) if others
                                                        else ""))
            if f0.get("excerpt"):
                lines.append("- **Excerpt**: \"%s\"" % _md_escape(f0["excerpt"])[:240])
            if f0.get("ruling"):
                lines.append("- **Ruling**: %s%s" % (f0["ruling"], (" — " + _md_escape(f0.get("ruling_rationale")))
                                                     if f0.get("ruling_rationale") else ""))
            if f0.get("note"):
                lines.append("- **Note**: %s" % _md_escape(f0["note"]))
            lines.append("- **Rule**: %s" % f0["rule"])
            lines.append("- **Fix**: %s" % f0["suggestion"])
            lines.append("")

    group_block(BLOCK, "Blocking findings")
    group_block(WARN, "Advisory findings")
    info_groups = [g for g in groups if all(f["severity"] == INFO for f in by_group.get(g["group"], []))]
    if info_groups:
        lines += ["## Informational", "", "| Group | Check | Match | n |", "|---|---|---|---|"]
        for g in info_groups[:200]:
            lines.append("| %s | %s | %s | %d |" % (g["group"], g["check"], _md_escape(g["match"])[:80], g["n"]))
        lines.append("")
    down = det.get("downgraded_blockers") or []
    if down:
        lines += ["## Blocking candidates that were downgraded", "",
                  "These would block, but a ruling, the verbatim rule, or an exemption made them INFO. The verdict no "
                  "longer counts them: look at each once.", "",
                  "| Group | Check | Match | n | Why | Where |", "|---|---|---|---|---|---|"]
        for g in down:
            lines.append("| %s | %s | %s | %d | %s | %s |" % (g["group"], g["check"], _md_escape(g["match"])[:80], g["n"],
                                                             _md_escape(g["why"])[:160], _md_escape("; ".join(g["where"]))))
        lines.append("")
    stops = det.get("stop_conditions") or []
    queue = det.get("fix_queue") or []
    ae = det.get("auto_edits") or {}
    if final and ae.get("total"):
        lines += ["## Changed by this run (since round 0)", "",
                  "Every change in the files since round 0, with the whitelist verdict: `— fix` only deletes confirmed "
                  "leak fragments, repairs verified references, adds metadata lines, and drops junk members. A "
                  "rejected change is a FIX-EDIT finding: undo it.", "",
                  "- %s changed place(s)%s: %s ok, %s rejected; files: %s" % (
                      ae.get("total"), (" from %d applied edit(s); edits next to each other show as one place"
                                        % ae["applied_edits"]) if ae.get("applied_edits") else "",
                      ae.get("ok"), ae.get("rejected"), _md_escape(", ".join(ae.get("files") or []))), "",
                  "| Edit | Where | Class | Verdict | Before | After |", "|---|---|---|---|---|---|"]
        for e in (ae.get("items") or [])[:200]:
            lines.append("| %s | %s | %s | %s | %s | %s |" % (
                e.get("id"), _md_escape(e.get("where")), e.get("fix_class") or "—",
                e.get("verdict") if e.get("verdict") == "ok" else "rejected: " + _md_escape(e.get("why"))[:120],
                _md_escape(e.get("before_fragment"))[:120], _md_escape(e.get("after_fragment"))[:120]))
        lines.append("")
    nc = ae.get("not_compared") or []
    if final and nc:
        lines += ["Not compared (binary, over the snapshot limit, or past the scan budget; never counted as left "
                  "out): %s." % _md_escape("; ".join("%s (%s)" % (u.get("member"), u.get("why")) for u in nc[:8])), ""]
    ce = det.get("contested_edits") or []
    if final and ce:
        lines += ["## Contested changes (recomputed by finalize from the files)", "",
                  "| Edit | Change | Where | Verdict | Why |", "|---|---|---|---|---|"]
        for c in ce:
            lines.append("| %s | %s | %s | %s | %s |" % (c.get("id"), c.get("op") or "—", _md_escape(c.get("where")),
                                                         c.get("verdict"), _md_escape(c.get("why"))[:200]))
        lines.append("")
    pdm = det.get("policy_demoted") or []
    if final and pdm:
        lines += ["## Reviewer findings the venue policy keeps (INFO, `necessary_by_policy`)", ""]
        for p_ in pdm[:60]:
            lines.append("- %s %s (%s): \"%s\" — %s" % (p_.get("group"), p_.get("check"), _md_escape(p_.get("where")),
                                                       _md_escape(p_.get("match"))[:100], _md_escape(p_.get("why"))))
        lines.append("")
    if final and (queue or stops):
        lines += ["## Fix queue (`— fix`: automatic, whitelist only)", ""]
        if stops:
            lines.append("Stop conditions (the fix loop ends at once): %s." % ", ".join(
                "%s %s \"%s\"" % (g["group"], g["check"], _md_escape(g["match"])[:40]) for g in stops))
            lines.append("")
        if queue:
            lines += ["| Group | Class | Check | Severity | Match | Where |", "|---|---|---|---|---|---|"]
            for g in queue:
                lines.append("| %s | %s | %s | %s | %s | %s |" % (g["group"], g["fix_class"], g["check"],
                                                               g["severity"], _md_escape(g["match"])[:80],
                                                               _md_escape("; ".join(g["where"]))))
            lines.append("")
    undo = det.get("undo") or []
    if final and undo:
        lines += ["## Undo (this round made the PDF worse)", "",
                  "Undo only these edits of this round (`apply --undo`), rebuild, and re-check; their items go to "
                  "the fix plan.", ""]
        for u in undo:
            lines.append("- %s (%s): %s" % (u.get("id"), u.get("group"), _md_escape(u.get("why"))))
        lines.append("")
    rounds = det.get("rounds") or []
    if final and rounds:
        lines += ["## Fix rounds", "", "| Round | Verdict | BLOCK | WARN | Regressions | Rejected edits | Eligible |",
                  "|---|---|---|---|---|---|---|"]
        for r in rounds:
            lines.append("| %s | %s | %s | %s | %s | %s | %s |" % (
                r.get("round"), r.get("verdict"), r.get("block"), r.get("warn"),
                _md_escape("; ".join(r.get("regressions") or [])) or "—", len(r.get("rejected_edits") or []),
                "yes" if r.get("eligible") else "no"))
        lines += ["", "Deliver: %s" % (det.get("deliver") or "round %s" % det.get("best_round")), ""]
    plan = [p for p in det.get("fix_plan") or [] if not p.get("auto")]
    if final and plan:
        lines += ["## Fix plan (for a person)", "",
                  "Every live finding the automatic fix does not change, with why — the full list with the original "
                  "text and a suggested fix is in FIX_PLAN.md. None of them is cleared by being left to a person.", "",
                  "| Id | Severity | Category | Match | Where | Why not automatic |", "|---|---|---|---|---|---|"]
        for p in plan[:300]:
            lines.append("| %s | %s | %s | %s | %s | %s |" % (p["id"], p["severity"], _md_escape(p["category"]),
                                                             _md_escape(p["match"])[:70],
                                                             _md_escape("; ".join(p["where"][:3])),
                                                             _md_escape(p.get("why_not_auto"))[:140]))
        lines.append("")
    changes = det.get("ruling_changes") or []
    if final and changes:
        lines += ["## Rulings that changed across rounds", "",
                  "Without new evidence the conservative side wins: an earlier confirmation stays, and a new "
                  "confirmation is held at WARN for a person.", "",
                  "| Group | Check | Match | Earlier | Now | New evidence | Effective | Held |",
                  "|---|---|---|---|---|---|---|---|"]
        for c in changes:
            lines.append("| %s | %s | %s | %s (%s) | %s | %s | %s | %s |" % (
                c.get("group"), c.get("check"), _md_escape(c.get("match"))[:60], c.get("prior"), c.get("prior_run"),
                c.get("current"), _md_escape(c.get("new_evidence") or "—")[:120], c.get("effective"),
                "yes" if c.get("held") else "no"))
        lines.append("")
    co = det.get("carried_over") or {}
    if final and (co.get("stops") or co.get("reviewer_findings")):
        lines += ["## Carried over from %s" % co.get("from"), ""]
        for s in co.get("stops") or []:
            lines.append("- The fix loop stopped on NUM-DRIFT %s; this recheck had no baseline to re-check it." % s)
        for rf in co.get("reviewer_findings") or []:
            lines.append("- %s %s (%s, %s): \"%s\"%s" % (
                rf.get("group"), rf.get("check"), rf.get("reviewer_severity"), _md_escape(rf.get("where")),
                _md_escape(rf.get("quote"))[:160],
                " — re-read in full by this run's batch reviewer, nothing reported on the member: INFO, not "
                "confirmed again" if rf.get("reread_clean") else ""))
        lines.append("")
    sr = det.get("supp_review") or {}
    if final and sr:
        lines += ["## Supplementary review coverage", "",
                  "- %s of %s member(s) checked in full (%s batch(es))%s%s" % (
                      sr.get("checked"), sr.get("members"), sr.get("batches"),
                      ("; %s sent only in part and %s never sent (over the review text budget: read them by hand)"
                       % (sr.get("cut") or 0, sr.get("not_sent") or 0)) if (sr.get("cut") or sr.get("not_sent")) else "",
                      ("; not covered: " + _md_escape("; ".join(sr.get("missing")[:10]))) if sr.get("missing") else "")]
        if sr.get("not_in_review"):
            lines.append("- Not given to the batch reviewers by design (only the deterministic rules read them): %s" %
                         ", ".join("%d %s" % (n, k) for k, n in sr["not_in_review"].items()))
        lines.append("")
    sk = det.get("checks_skipped", [])
    gaps = [s for s in sk if s.get("cap")]
    lines += ["## Coverage", ""]
    lines.append("- Backends: %s" % ", ".join("%s=%s" % (k, v) for k, v in sorted((det.get("backends") or {}).items())))
    lines.append("- Checks run: %d; skipped: %d (coverage gaps: %d)" % (len(det.get("checks_run", [])), len(sk), len(gaps)))
    if gaps:
        lines += ["", "| Skipped check | Reason | Verdict cap | Hint |", "|---|---|---|---|"]
        for s in gaps:
            lines.append("| %s | %s | %s | %s |" % (s["check"], s["reason"], s["cap"], _md_escape(s.get("hint") or "")))
    lines.append("")
    geo = [g for g in det.get("page_geometry", []) if g.get("status") == "ok"]
    if geo:
        lines += ["## Page geometry", "", "| PDF | Body ends | Fill | Lines short | Next heading |", "|---|---|---|---|---|"]
        for g in geo:
            lines.append("| %s | p.%d | %.1f%% | %d | %s |" % (_md_escape(g.get("artifact")), g["body_end_page"], g["fill"] * 100,
                                                            g["lines_short"], _md_escape(g.get("end_heading"))))
        lines.append("")
    ex = det.get("exemptions_applied", [])
    if ex:
        lines += ["## Exemptions applied", "", "| Source | Check | Removed severity | Approved by | Reason |",
                  "|---|---|---|---|---|"]
        for e in ex:
            lines.append("| %s | %s | %s | %s | %s |" % (_md_escape(e["line"]), e["check"], e.get("removed_severity", ""),
                                                        _md_escape(e["approved_by"]), _md_escape(e["reason"])))
        lines.append("")
    sugg = det.get("suggested_allow_lines", [])
    if sugg:
        lines += ["## Suggested allow-list lines", "",
                  "Copy by hand into `.aris/paper-hygiene/allow.tsv` if you agree; the executor never writes that file.", "",
                  "```"] + sugg + ["```", ""]
    stale = det.get("stale_other_audits", [])
    if stale:
        lines += ["## Other audits now stale", ""]
        for s in stale:
            lines.append("- `%s` (%s): re-run — changed inputs: %s" % (s["artifact"], s.get("audit_skill"),
                                                                    ", ".join(s.get("stale_inputs", [])[:6])))
        lines.append("")
    lines += ["## Built-in exemptions", ""] + ["- " + x for x in BUILTIN_EXEMPTIONS] + [""]
    return "\n".join(lines)


# ─── finalize ────────────────────────────────────────────────────────────────

_JSON_BLOCK_RE = re.compile(r"```(?:json|JSON)?[ \t]*\n(.*?)```", re.S)
_RULINGS = ("leak", "reword", "necessary", "false_positive", "uncertain")
REWRITE_MAX = 2000  # a reviewer's wording is kept whole (a cut suggestion reads as one that drops words)
_LENS_CHECK = {"engineering": "LENS-ENGINEERING", "anonymity": "LENS-ANONYMITY", "statements": "LENS-STATEMENTS",
               "triage": "LENS-ENGINEERING"}
_REVIEW_SEV = {"blocking": BLOCK, "block": BLOCK, "advisory": WARN, "warn": WARN, "warning": WARN, "info": INFO}


def parse_review(text: str) -> Optional[Dict[str, Any]]:
    """The LAST fenced json block that parses as an object."""
    for body in reversed(_JSON_BLOCK_RE.findall(text or "")):
        try:
            obj = json.loads(body)
        except ValueError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def _norm_quote(s: str) -> str:
    return _collapse_ws(unicodedata.normalize("NFKC", s or "")).casefold()


def _apply_ruling(f: Dict[str, Any], effective: str, level: str) -> None:
    """Set a candidate's severity from its (effective) ruling."""
    if f["severity"] == INFO:  # a low-priority group: only a confirming ruling changes it
        if effective in CONFIRMED_RULINGS:
            f["original_severity"], f["severity"] = INFO, level
        return
    if effective in CONFIRMED_RULINGS:
        f["severity"] = level  # fixed at scan time (HARDWARE / FRAMEWORK policy included)
    elif effective in CLEARING_RULINGS:
        f["original_severity"], f["severity"] = f["severity"], INFO
    else:
        f["severity"] = WARN


def anonymity_evidence(raw: str, redacted: str, derived_users: Iterable[str] = ()) -> Optional[str]:
    """What in a reviewer's quote identifies the authors by a deterministic
    rule (None: nothing): an identity, auto, or deny-list term, a home path, an
    account at a host, a login made from an author's name, a host name where
    a note logs in or runs, a private IP address, an internal host name."""
    if re.search(r"\[(?:ANON|AUTO|DENY)#", redacted or ""):
        return "an identity term"
    t_ = raw or ""
    for rx in _IDENT_PATH_RES:
        m = rx.search(t_)
        if m and not _PATH_PLACEHOLDER_RE.match(m.group(0)):
            return "a home path"
    for m in list(_SSH_ACCOUNT_RE.finditer(t_)) + list(_USER_HOST_RE.finditer(t_)):
        user_, _at, host_ = m.group(0).split()[-1].partition("@")
        host_ = host_.split(":", 1)[0]
        if not (_ACCOUNT_PLACEHOLDER_RE.match(user_) or _HOST_PLACEHOLDER_RE.match(host_)):
            return "an account at a host"
    derived = {str(x).lower() for x in derived_users}
    if any(m.group(1).lower() in derived for m in _ACCOUNT_AT_RE.finditer(t_)):
        return "a login made from an author's name"
    for m in _SUPP_HOSTNAME_RE.finditer(t_):
        pre = m.group("pre")
        login_ = re.search(r"([\w.-]+)@$", pre)
        if login_ and _ACCOUNT_PLACEHOLDER_RE.match(login_.group(1)):
            continue
        if pre.endswith("@") or re.match(r"\s*(?:ssh|scp|sftp|rsync)\b", pre, re.I) or m.group("colon") or \
                len(re.sub(r"\D", "", m.group("host"))) >= 2:
            return "a host name where a note logs in or runs"
    for m in _IPV4_RE.finditer(t_):
        if _ipv4_ok(t_, m) == DEFINITE and not m.group(0).startswith(("127.", "0.")):
            return "a private IP address"
    for m in _HOST_SUFFIX_RE.finditer(t_):
        if _host_ok(t_, m):
            return "an internal host name"
    return None


def merge_review(scan: Dict[str, Any], review: Dict[str, Any], page_texts: Dict[str, Dict[int, str]],
                 reviewer_handle: str, redactor: Optional[Redactor] = None,
                 supp_texts: Optional[Dict[str, str]] = None, ledger: Optional[Dict[str, Any]] = None,
                 run_label: Optional[str] = None, extra_findings: Sequence[Dict[str, Any]] = (),
                 cross_family: bool = True, supp_reread: Optional[Set[str]] = None
                 ) -> Tuple[List[Dict[str, Any]], List[str], List[str], Dict[str, Any]]:
    """Apply rulings to candidate groups and add anchored lens findings. Every
    string the reviewer wrote (quotes, rationales, rewrites) passes through the
    same redaction as the scan: a reviewer who read the .tex sources can quote
    a name the PDF text files had already masked. A finding anchors in the PDF
    text, or else in the supplementary texts the reviewer was given (supp_docs:
    READMEs, code notes, log heads) — then it is a supplement finding.

    What may block: a definite finding, or a candidate of a rule that a
    cross-family reviewer ruled `leak` (the check's confirmed level). A
    `reword` ruling is WARN at most (the fact stays, the wording changes); a
    same-family confirmation is WARN at most; a reviewer's own finding (a lens
    finding) is WARN at most — a 'blocking' one stays a confirmed leak that
    keeps upload_ready false — except an anonymity-lens finding reported as
    blocking whose quote holds what a deterministic rule reads as the
    authors' identity (anonymity_evidence): BLOCK, whatever the family.

    With a rulings ledger, a ruling that flips an earlier round's decision
    (clearing vs confirming) without `new_evidence` is resolved the
    conservative way and listed: an earlier confirmation stays, and a new
    confirmation is held at WARN for a person. A candidate group this reviewer
    did not rule inherits the latest decisive ruling of the same stable key.
    Reviewer findings carried over from the fix run (scan["carried_findings"],
    ids C-NNN) stay unless a ruling clears them with new evidence — or, for a
    supplementary member, unless this run's batch reviewer was given the
    passage in full (`supp_reread`: members marked checked, never cut short)
    and reported nothing on that member while nothing else flags it: that full
    re-read outweighs a ruling made from the quote alone, and the finding is
    listed at INFO, not confirmed again (an anonymity finding whose quote holds
    deterministic identity evidence always stays). Returns (findings, notes,
    lenses_run, memo) where memo holds ruling_changes, ledger_updates, the
    carried findings a re-read did not confirm, and the number of inherited
    rulings."""
    red = redactor or Redactor()

    def clean(x: Any, n: int = 400) -> str:
        return red.redact(_collapse_ws(str(x or "")))[:n]

    findings = [dict(f, location=dict(f["location"])) for f in scan["findings"]]
    notes: List[str] = []
    memo: Dict[str, Any] = {"ruling_changes": [], "ledger_updates": [], "inherited": 0, "carried_reread": []}
    groups = {g["group"]: g for g in scan["groups"]}
    carried = {c["id"]: c for c in scan.get("carried_findings") or [] if isinstance(c, dict) and c.get("id")}
    carried_rulings: Dict[str, Dict[str, Any]] = {}
    levels = {"HARDWARE": HARDWARE_LEVELS.get(str(scan.get("hardware", "block")).lower(), BLOCK),
              "FRAMEWORK": HARDWARE_LEVELS.get(str(scan.get("framework", "warn")).lower(), WARN),
              "SUPP_HARDWARE": HARDWARE_LEVELS.get(str(scan.get("supp_hardware") or "info").lower(), INFO)}
    rulings = [r for r in review.get("rulings") or [] if isinstance(r, dict)]
    ruled = {str(r.get("group", "")) for r in rulings}
    if ledger:
        # a group this reviewer left out keeps the latest decisive ruling of its stable key
        for gid, g in groups.items():
            if gid in ruled or g["certainty"] != CANDIDATE:
                continue
            key = g.get("key") or stable_key(g["check"], g["match"], g.get("region"), g.get("subregion"))
            prior = prior_decision(ledger, key)
            if prior:
                rulings.append({"group": gid, "ruling": prior.get("effective") or prior.get("ruling"),
                                "rationale": prior.get("rationale"), "_inherited": prior})
    for r in rulings:
        gid, ruling = str(r.get("group", "")), str(r.get("ruling", "")).strip().lower()
        if ruling not in _RULINGS:
            notes.append("unknown_ruling:%s:%s" % (clean(gid, 20), clean(ruling, 20)))
            ruling = "uncertain"
        if gid in carried:
            carried_rulings[gid] = {"ruling": ruling, "new_evidence": clean(r.get("new_evidence"), 300),
                                    "rationale": clean(r.get("rationale")),
                                    "rewrite": clean(r.get("rewrite"), REWRITE_MAX) if r.get("rewrite") else ""}
            continue
        g = groups.get(gid)
        if g is None:
            notes.append("review_unknown_group:%s" % clean(gid, 20))
            continue
        if g["certainty"] != CANDIDATE:
            notes.append("ruling_on_definite_group_ignored:%s" % gid)
            continue
        if ruling == "reword" and not r.get("rewrite"):
            notes.append("reword_without_rewrite:%s" % gid)
        key = g.get("key") or stable_key(g["check"], g["match"], g.get("region"), g.get("subregion"))
        inherited = r.get("_inherited")
        prior = None if inherited else (prior_decision(ledger, key, run_label) if ledger else None)
        new_ev = clean(r.get("new_evidence"), 300)
        pc, cc = (_ruling_class(prior["ruling"]) if prior else None), _ruling_class(ruling)
        effective, side, change = ruling, None, None
        if pc and cc and pc != cc:
            change = {"group": gid, "check": g["check"], "match": g["match"], "key": key, "prior": prior["ruling"],
                      "prior_run": prior.get("run"), "current": ruling, "new_evidence": new_ev or None}
            if not new_ev:
                # no new evidence: the conservative side wins and a person looks once
                side = "prior" if cc == "clear" else "current"
                effective = prior["ruling"] if side == "prior" else ruling
            change.update({"effective": effective, "held": side is not None})
            memo["ruling_changes"].append(change)
        if inherited:
            memo["inherited"] += 1
        else:
            memo["ledger_updates"].append({"key": key, "check": g["check"], "match": g["match"],
                                           "region": g.get("region"), "subregion": g.get("subregion"),
                                           "ruling": ruling, "effective": effective,
                                           "rationale": clean(r.get("rationale"), 300), "new_evidence": new_ev or None})
        for f in findings:
            if f.get("group") != gid or f.get("exempted_by"):
                continue
            if f["severity"] == INFO and f.get("demoted") not in _REVIEWED_DEMOTIONS:
                continue  # INFO the reviewer was never asked about
            f["ruling"] = effective
            f["ruled_by"] = (inherited.get("by") or "ledger") if inherited else reviewer_handle
            f["ruling_rationale"] = clean(r.get("rationale"))
            if r.get("rewrite"):
                f["rewrite"] = clean(r["rewrite"], REWRITE_MAX)
            notes_f = []
            if inherited:
                notes_f.append("ruling inherited from %s (this reviewer did not rule the group)" % inherited.get("run"))
            level = f.get("confirm_severity") or levels.get(CHECKS.get(f["check"], {}).get("confirm"), WARN)
            if effective == "reword" and level == BLOCK:
                level = WARN  # the fact stays, the wording changes: for a person, never a blocker
                notes_f.append("reword: keep the fact, reword the passage (WARN at most)")
            elif effective == "reword":
                notes_f.append("keep the fact, reword the passage")
            if effective == "leak" and level == BLOCK and not cross_family:
                level = WARN
                notes_f.append("same-family review: a confirmation is WARN at most")
            if effective in CONFIRMED_RULINGS and level == BLOCK and f.get("hw_usage"):
                # a metric of the study or a heading's wording: never a blocker on a reviewer's word alone
                level = WARN
                notes_f.append("the hardware word names a measured quantity or sits in a heading (%s): a leak "
                               "ruling keeps it at WARN, for a person" % f["hw_usage"])
            if side == "current":
                level = WARN
                notes_f.append("ruling flipped from %s (%s) without new evidence: held for a person"
                               % (change["prior"], change["prior_run"]))
            elif side == "prior":
                notes_f.append("kept the %s ruling of %s: the %s ruling gives no new evidence"
                               % (change["prior"], change["prior_run"], ruling))
            if side:
                f["ruling_flip"] = {"prior": change["prior"], "prior_run": change["prior_run"], "current": ruling}
            elif change:
                f["ruling_overturned"] = {"prior": change["prior"], "prior_run": change["prior_run"],
                                          "new_evidence": new_ev}
            if notes_f:
                f["note"] = "; ".join(x for x in [f.get("note")] + notes_f if x)
            _apply_ruling(f, effective, level)
    for f in findings:
        if f["certainty"] == CANDIDATE and f["severity"] != INFO and not f.get("ruling") and not f.get("exempted_by"):
            f["ruling"] = "unreviewed"
    enabled_lenses = set(scan.get("lenses") or [])
    norm_pages = {art: {pg: _norm_quote(t) for pg, t in pages.items()} for art, pages in page_texts.items()}
    norm_supp = {m: _norm_quote(t) for m, t in (supp_texts or {}).items()}
    supp_art = next((s.get("path") for s in (scan.get("inputs") or {}).get("supp") or [] if s.get("path")), None)
    n = 0
    for rf in list(review.get("findings") or []) + list(extra_findings or []):
        if not isinstance(rf, dict):
            continue
        lens = str(rf.get("lens", "")).strip().lower()
        check = _LENS_CHECK.get(lens, "LENS-OTHER")
        if lens not in enabled_lenses and check != "LENS-OTHER":
            check = "LENS-OTHER"
        stated = str(rf.get("severity", "advisory")).strip().lower()
        stated = {"block": "blocking", "warn": "advisory", "warning": "advisory"}.get(stated, stated)
        if stated not in ("blocking", "advisory", "info"):
            stated = "advisory"
        cap_note = None
        if check == "LENS-STATEMENTS" and not scan.get("declared_ai_uses_set") and stated == "blocking":
            # without declared_ai_uses the lens judges style, not truth: a required
            # statement is reworded by a person, never cut by a fix round
            stated, cap_note = "advisory", "statements lens without policy declared_ai_uses: advisory"
        if check == "LENS-OTHER" and stated == "blocking":
            stated = "advisory"
        # a reviewer's own finding is no rule hit: WARN at most; "blocking" keeps it a confirmed leak
        sev = INFO if stated == "info" else WARN
        raw_quote = str(rf.get("quote") or "")
        quote = red.redact(raw_quote)  # the page texts it is anchored in are redacted too
        q = _norm_quote(quote)
        where = None
        member = None
        if len(q) >= 8:
            for art, pages in norm_pages.items():
                for pg, t in pages.items():
                    if q in t:
                        where = (art, pg)
                        break
                if where:
                    break
            if where is None and norm_supp:
                want = red.redact(str(rf.get("member") or ""))
                order = sorted(norm_supp, key=lambda m: (m != want, m))
                member = next((m for m in order if q in norm_supp[m]), None)
        family = CHECKS[check]["family"]
        note = cap_note
        if member is not None:
            family = "SUPP" if check in ("LENS-ENGINEERING", "LENS-ANONYMITY") else family
            note = "; ".join(x for x in (note, "anchored in the supplementary text") if x)
        elif where is None:
            note = "; ".join(x for x in (note, "unanchored: the quote was not found in the PDF or supplementary text")
                             if x)
            if stated == "blocking":
                stated = "advisory"  # a quote that cannot be found confirms nothing
        if stated == "blocking":
            note = "; ".join(x for x in (note, "reported as blocking: a confirmed leak (WARN at most, never "
                                               "advisory)") if x)
        n += 1
        spec = CHECKS[check]
        if rf.get("category"):
            note = "; ".join(x for x in (note, "category: %s" % clean(rf.get("category"), 40)) if x)
        findings.append({
            "id": "%s-%03d" % (check, n), "group": "R-%03d" % n, "check": check, "family": family,
            "severity": sev, "certainty": CANDIDATE, "confirm_severity": None, "layer": "review",
            "region": None, "subregion": None,
            "location": {"artifact": where[0] if where else (supp_art if member else None),
                         "page": where[1] if where else (None if member else rf.get("page")),
                         "file": None, "line": None, "member": member},
            "match": quote[:200], "excerpt": quote[:200], "redacted": quote != raw_quote, "rule": spec["rule"],
            "route": spec["route"], "suggestion": clean(rf.get("rewrite") or spec["fix"], REWRITE_MAX),
            "exempted_by": None,
            "ruling": "reviewer_finding", "ruled_by": reviewer_handle, "note": note, "demoted": None,
            "ruling_rationale": clean(rf.get("rationale")), "anchored": where is not None or member is not None,
            "reviewer_severity": stated,
        })
        f_new = findings[-1]
        if rf.get("rewrite"):
            f_new["rewrite"] = clean(rf.get("rewrite"), REWRITE_MAX)
        if check == "LENS-ANONYMITY" and f_new["anchored"] and stated == "blocking":
            # the quote itself holds what a deterministic rule reads as the authors' identity: a blocker
            ev = anonymity_evidence(raw_quote, quote, getattr(red, "derived_users", ()) or ())
            if ev:
                f_new["severity"], f_new["confirm_evidence"] = BLOCK, ev
                f_new["note"] = "; ".join(x for x in (
                    (f_new.get("note") or "").replace("a confirmed leak (WARN at most, never advisory)",
                                                      "a confirmed leak"),
                    "deterministic evidence in the quote (%s): BLOCK" % ev) if x)
        if f_new["anchored"] and stated == "blocking" and check in ("LENS-ENGINEERING", "LENS-ANONYMITY"):
            # a reviewer-confirmed leak: NUM-DRIFT may attribute numbers of its deleted sentence to it
            memo["ledger_updates"].append({
                "key": stable_key(check, f_new["match"]), "check": check, "match": f_new["match"], "ruling": "leak",
                "effective": "leak", "rationale": f_new["ruling_rationale"][:300], "new_evidence": None,
                "reviewer_finding": True, "page": f_new["location"]["page"], "artifact": f_new["location"]["artifact"],
                "member": member})
    # reviewer findings an earlier round left in the text: they stay until a
    # ruling clears them with new evidence (or this reviewer reports them again)
    reported = [_norm_quote(f["match"]) for f in findings if f.get("layer") == "review"]
    # the supplementary members something in this run still flags (a finding above INFO, or a batch reviewer's
    # finding on it, anchored or not): a carried finding there is never taken as re-read clean
    flagged = {_collapse_ws(str(f["location"].get("member"))).casefold() for f in findings
               if f["location"].get("member") and f["severity"] != INFO and not f.get("exempted_by")}
    flagged |= {_collapse_ws(red.redact(str(rf.get("member")))).casefold() for rf in extra_findings or []
                if isinstance(rf, dict) and rf.get("member")}

    def is_flagged(member: str) -> bool:
        m = _collapse_ws(member).casefold()
        return any(x == m or m.endswith("/" + x) or x.endswith("/" + m) for x in flagged if x)
    for cid, c in sorted(carried.items()):
        q = _norm_quote(c.get("quote") or "")
        if not q or any(q in x or x in q for x in reported if len(x) >= 8):
            continue
        rr = carried_rulings.get(cid)
        if rr and rr["ruling"] in CLEARING_RULINGS and rr["new_evidence"]:
            memo["ruling_changes"].append({"group": cid, "check": c.get("check"), "match": c.get("quote"),
                                           "key": c.get("key"), "prior": "leak", "prior_run": c.get("run"),
                                           "current": rr["ruling"], "new_evidence": rr["new_evidence"],
                                           "effective": rr["ruling"], "held": False})
            continue
        check = c.get("check") if c.get("check") in CHECKS else "LENS-ENGINEERING"
        stated = c.get("reviewer_severity") or ("blocking" if c.get("severity") == BLOCK else "advisory")
        note = "carried over from %s: an earlier reviewer reported it and the text still holds it" % c.get("run")
        mem = str(c.get("member") or "")
        reread = bool(mem and supp_reread is not None and mem in supp_reread and not is_flagged(mem)
                      and q in norm_supp.get(mem, "")
                      and not (rr and rr["ruling"] in CONFIRMED_RULINGS and rr["new_evidence"])
                      and not (check == "LENS-ANONYMITY" and anonymity_evidence(
                          str(c.get("quote") or ""), red.redact(str(c.get("quote") or "")),
                          getattr(red, "derived_users", ()) or ())))
        flip = None
        if reread:
            note += ("; this run's batch reviewer was given the passage in full and reported nothing on the member"
                     "%s: not confirmed again (INFO, listed for a person)"
                     % ("" if not rr else " (the %s ruling was made from the quote alone, without new evidence)"
                        % rr["ruling"]))
            memo["carried_reread"].append({"group": cid, "check": check, "quote": str(c.get("quote") or "")[:200],
                                           "member": mem, "prior_run": c.get("run"),
                                           "ruling": rr["ruling"] if rr else None})
        elif rr and rr["ruling"] in CLEARING_RULINGS:
            flip = {"prior": "leak", "prior_run": c.get("run"), "current": rr["ruling"]}
            note += "; ruled %s without new evidence: kept" % rr["ruling"]
            memo["ruling_changes"].append({"group": cid, "check": check, "match": c.get("quote"), "key": c.get("key"),
                                           "prior": "leak", "prior_run": c.get("run"), "current": rr["ruling"],
                                           "new_evidence": None, "effective": "leak", "held": True})
        spec = CHECKS[check]
        rewrite = (rr or {}).get("rewrite") or c.get("rewrite")  # this run's wording first
        f_c = {
            "id": "%s-C%s" % (check, cid[2:]), "group": cid, "check": check, "family": c.get("family") or spec["family"],
            "severity": INFO if reread else WARN, "certainty": CANDIDATE, "confirm_severity": None, "layer": "review",
            "region": None, "subregion": None,
            "location": {"artifact": c.get("artifact"), "page": c.get("page"), "file": None, "line": None,
                         "member": c.get("member")},
            "match": str(c.get("quote") or "")[:200], "excerpt": str(c.get("quote") or "")[:200], "redacted": False,
            "rule": spec["rule"], "route": spec["route"], "suggestion": rewrite or spec["fix"],
            "exempted_by": None, "ruling": "reviewer_finding", "ruled_by": c.get("by") or reviewer_handle,
            "note": note, "demoted": None,
            "ruling_rationale": ((rr or {}).get("rationale") if not reread else "") or c.get("rationale") or "",
            "anchored": True, "carried_from": c.get("run"), "reviewer_severity": stated}
        if rewrite:
            f_c["rewrite"] = rewrite
        if reread:
            f_c["reread_clean"] = True
        if flip:
            f_c["ruling_flip"] = flip
        if check == "LENS-ANONYMITY" and stated == "blocking" and not reread:
            ev = anonymity_evidence(f_c["match"], red.redact(f_c["match"]), getattr(red, "derived_users", ()) or ())
            if ev:
                f_c["severity"], f_c["confirm_evidence"] = BLOCK, ev
                f_c["note"] += "; deterministic evidence in the quote (%s): BLOCK" % ev
        findings.append(f_c)
    return findings, notes, sorted({str(x) for x in (review.get("lenses_run") or []) if isinstance(x, str)}), memo


# What a policy keeps on purpose (finalize demotes a reviewer finding that holds
# only this): registration labels and the ordering statements of a registration.
_POLICY_REG_RE = re.compile(r"\b(?:amendments?|addend(?:um|a)|clarifications?|errat(?:um|a)|pre-?registrations?|"
                            r"registrations?|pre-?registered|registered|pre-?specified)\b"
                            # a file's name (PREREGISTRATION.md) is a pointer, not a registration word
                            r"(?!\.(?:md|markdown|txt|rst|pdf|json|ya?ml|toml|tex|py|csv|tsv|html?)\b)", re.I | _A)
_ORDER_ANCHOR_RE = re.compile(
    r"\b(?:pre-?registered|registered|specified|written|fixed|frozen|defined|chosen|decided|committed|declared|"
    r"planned|filed|sealed|locked|agreed)\b[^.;:]{0,40}?\b(?:before|after|prior\s+to|ahead\s+of|until)\b"
    r"|\b(?:before|prior\s+to)\s+(?:any|all|the\s+first|seeing|looking\s+at|computing|running|unblinding)\b",
    re.I | _A)
_POLICY_TOLERATED = frozenset({"ENG-FILENAME", "TEXT-CODE", "TEXT-GLUE", "TEXT-NUMFMT"})
# a date or a time of the authors' own work is never what a policy keeps, also
# where no check reads it as one: a date-shaped number anywhere (a seed, a stamp
# inside a name: run_20991231T235959Z), a clock time
_POLICY_NEVER_RE = re.compile(r"(?<!\d)(?:19|20)\d\d(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])(?:T?\d{2,6}Z?)?(?!\d)"
                              r"|(?<![\w:.])(?:[01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d)?(?![\w:])", _A)


def _plan_ctx(policy: Dict[str, Any], anonymous: bool = True) -> ScanContext:
    """A scan context for the deterministic checks finalize runs on short texts
    (reviewer quotes, suggested wording): the scan's policy, no identity terms
    (the texts are redacted already)."""
    ctx = ScanContext()
    ctx.anonymous = anonymous
    ctx.enabled = set(CHECKS)
    ctx.precision = str(policy.get("precision_disclosure") or PRECISION_POLICIES[0])
    ctx.reg_labels = str(policy.get("registration_labels") or REGISTRATION_POLICIES[0])
    return ctx


# what never rides along with a registration label or the order it states under registration_labels: keep:
# a correction or a re-run, work completed or added later, a batch name, a month-day date ("09-24")
_POLICY_RIDE_RE = re.compile(
    r"(?<![\w-])(?:corrected|correction|correcting|fixed\s+(?:a|the)\s+bug|bug\s*-?fix\w*|re-?r[au]n\w*|"
    r"re-?(?:evaluat|comput|generat|launch)\w*|completed\s+later|later\s+(?:completed|added)|added\s+(?:later|after)|"
    r"(?:phase|round|batch|wave|cohort)[-_ ]?\d+\w*|"
    r"(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)[- ]round|"
    r"(?<!\d)(?:0?[1-9]|1[0-2])[-/](?:0?[1-9]|[12]\d|3[01])(?![\d/-]))", re.I | _A)
# a label of a registration or a study part (E2, R5-D, A12, T3b): kept only where the paper itself names it
_POLICY_LABEL_RE = re.compile(r"(?<![\w-])[A-Z]{1,2}\d{1,3}(?:[a-z]|-[A-Z][\w]*)?(?![\w-])", _A)


def demote_by_policy(findings: List[Dict[str, Any]], policy: Dict[str, Any], anonymous: bool = True,
                     page_texts: Optional[Dict[str, Dict[int, str]]] = None, hardware: str = "block"
                     ) -> List[Dict[str, Any]]:
    """Reviewer findings of the engineering lens (Task B, a batch, carried
    ones) whose passage holds only what the authors' policy keeps — a
    registration label or ordering statement under registration_labels: keep,
    numeric precision under precision_disclosure: exempt, a hardware word in
    the supplement under supp_hardware: info — become INFO with the ruling
    `necessary_by_policy`. A passage that also holds anything a check flags (a
    date, a clock time, a host, a path, a version, revision or review talk,
    unfinished work), or any date-shaped number or clock time at all, stays as
    it was. Under registration_labels: keep the passage keeps its level as
    well when, beside the registration words and the order, it holds a code
    name, a month-day date, a hardware word (hardware block), a batch name, a
    correction, a re-run, or work completed later — and a label is kept only
    where the paper's own text names it."""
    reg_keep = str(policy.get("registration_labels") or "keep") == "keep"
    prec_exempt = str(policy.get("precision_disclosure") or "exempt") == "exempt"
    hw_info = str(policy.get("supp_hardware") or "").lower() == "info"
    hw_block = str(policy.get("hardware") or hardware or "block").lower() == "block"
    ctx = _plan_ctx(policy, anonymous)
    paper_text = " ".join(t_ for pp in (page_texts or {}).values() for t_ in pp.values())

    def in_paper(label: str) -> bool:
        return bool(paper_text) and re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(label), paper_text) is not None
    names = {str(f.get("match") or "").casefold() for f in findings
             if f["check"] in ("ANON-CODENAME", "ENG-DENY") and len(str(f.get("match") or "")) >= 3}
    out: List[Dict[str, Any]] = []
    for f in findings:
        if (f.get("layer") != "review" or f["check"] != "LENS-ENGINEERING" or f["severity"] == INFO
                or f.get("exempted_by")):
            continue
        q = str(f.get("match") or "")
        why, tolerated = None, set(_POLICY_TOLERATED)
        if reg_keep and (_POLICY_REG_RE.search(q) or _ORDER_ANCHOR_RE.search(q)):
            rest = _ORDER_ANCHOR_RE.sub(" ", _REGLABEL_ANY_RE.sub(" ", _POLICY_REG_RE.sub(" ", q)))
            labels = [x for x in _POLICY_LABEL_RE.findall(q) if not re.fullmatch(r"[A-Z]\d{3,}", x)]
            if (_POLICY_RIDE_RE.search(rest) or "[ANON#" in q or "[DENY#" in q or "[AUTO#" in q
                    or any(re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(n), q, re.I) for n in names)
                    or (hw_block and (_SUPP_HW_RE.search(rest) or _HW_RE.search(rest)))
                    or any(not in_paper(x) for x in labels)):
                continue  # more than the label and the order: the finding keeps its level
            why, tolerated = ("policy registration_labels: keep — a registration label or the order it states is a "
                              "required disclosure"), tolerated | {"PROC-REGLABEL"}
        elif prec_exempt and _PRECISION_RE.search(q):
            why, tolerated = ("policy precision_disclosure: exempt — numeric precision is a method parameter",
                              tolerated | {"ENG-PRECISION"})
        elif hw_info and f["location"].get("member") and (_SUPP_HW_RE.search(q) or _HW_RE.search(q)):
            why, tolerated = ("policy supp_hardware: info — hardware words in the supplement's notes are "
                              "reproduction notes"), tolerated | {"ENG-HW", "ENG-QTY", "ENG-OPS"}
        if not why or _POLICY_NEVER_RE.search(q):
            continue
        if [h for h in detect_text(q, "body", None, ctx, "pdf") if h.check not in tolerated]:
            continue
        f["original_severity"], f["severity"] = f["severity"], INFO
        f["ruling"] = "necessary_by_policy"
        f["note"] = "; ".join(x for x in (f.get("note"), why) if x)
        out.append({"group": f["group"], "check": f["check"], "match": f["match"][:120], "why": why,
                    "reviewer_severity": f.get("reviewer_severity"), "where": _where_str(f)})
    return out


def _load_supp_texts(scan: Dict[str, Any], paper_dir: str) -> Dict[str, str]:
    """member -> the redacted supplementary text the reviewer was given."""
    out: Dict[str, str] = {}
    for d in (scan.get("inputs") or {}).get("supp_docs") or []:
        rel = d.get("file")
        if not rel:
            continue
        full = rel if os.path.isabs(rel) else os.path.join(paper_dir, rel)
        if not os.path.isfile(full):
            continue
        text = _read_text(full)
        if text.startswith(_SUPP_DOC_HEADER):
            text = text.split("\n", 1)[1] if "\n" in text else ""
        member = str(d.get("member") or rel)
        out[member] = (out.get(member, "") + "\n" + text) if member in out else text
    return out


def _load_page_texts(scan: Dict[str, Any], paper_dir: str) -> Dict[str, Dict[int, str]]:
    out: Dict[str, Dict[int, str]] = {}
    for p in scan.get("inputs", {}).get("pdf", []):
        tf = p.get("text_file")
        if not tf:
            continue
        full = tf if os.path.isabs(tf) else os.path.join(paper_dir, tf)
        if not os.path.isfile(full):
            continue
        pages: Dict[int, List[str]] = {}
        cur = 0
        for line in _read_text(full).splitlines():
            m = re.match(r"^=== page (\d+) ===$", line)
            if m:
                cur = int(m.group(1))
                pages[cur] = []
            elif cur:
                pages[cur].append(line)
        out[p["path"]] = {k: "\n".join(v) for k, v in pages.items()}
    return out


def stale_other_audits(paper_dir: str, own: str = "PAPER_HYGIENE_AUDIT.json") -> List[Dict[str, Any]]:
    """Other audit artifacts whose audited_input_hashes no longer match."""
    out = []
    if not os.path.isdir(paper_dir):
        return out
    for fn in sorted(os.listdir(paper_dir)):
        if not fn.endswith(".json") or fn == own:
            continue
        p = os.path.join(paper_dir, fn)
        try:
            data = json.loads(_read_text(p))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict) or "audit_skill" not in data or not isinstance(data.get("audited_input_hashes"), dict):
            continue
        changed = []
        for rel, rec in data["audited_input_hashes"].items():
            full = rel if os.path.isabs(rel) else os.path.join(paper_dir, rel)
            want = str(rec).split(":", 1)[-1]
            if not os.path.isfile(full) or _sha256_file(full) != want:
                changed.append(rel)
        if changed:
            out.append({"artifact": fn, "audit_skill": data.get("audit_skill"), "stale_inputs": changed})
    gate = os.path.join(paper_dir, ".aris", "forensics", "gate.json")
    if os.path.isfile(gate):
        out.append({"artifact": ".aris/forensics/gate.json", "audit_skill": "integrity-forensics",
                    "stale_inputs": ["re-check with forensics_gate.py fresh"]})
    return out


def _model_family(name: str) -> Tuple[str, Optional[str]]:
    try:
        from provenance import model_family  # type: ignore
    except Exception:  # noqa: BLE001
        return "unknown", "provenance.py not importable; family could not be derived"
    return model_family(name), None


def _default_trace_dir(today: str) -> str:
    base = os.path.join(".aris", "traces", SKILL_NAME)
    n = 1
    while os.path.isdir(os.path.join(base, "%s_run%02d" % (today, n))):
        if os.path.isfile(os.path.join(base, "%s_run%02d" % (today, n), "run.meta.json")):
            break
        n += 1
    return os.path.join(base, "%s_run%02d" % (today, n))


def _finalize_redactor(scan: Dict[str, Any], paper_dir: str, config_dir: str) -> Redactor:
    """The scan's own redaction, rebuilt from the config files it recorded
    (paths relative to the paper directory; CONFIG_DIR as a fallback)."""
    recorded = (scan.get("inputs") or {}).get("config") or {}

    def find(key: str, default_name: str) -> Optional[str]:
        rel = recorded.get(key)
        cands = [rel if (rel and os.path.isabs(rel)) else os.path.join(paper_dir, rel)] if rel else []
        cands.append(os.path.join(config_dir, default_name))
        return next((c for c in cands if os.path.isfile(c)), None)

    anonymous = scan.get("anonymous", True)
    names = find("anon_names", "anon-names.txt")
    terms_ = parse_identity_list(_read_text(names))[0] if (names and anonymous) else []
    identity = TermMatcher(terms_)
    deny_terms: List[str] = []
    pol_path = find("policy", "policy.json")
    if pol_path:
        with contextlib.suppress(ValueError, OSError):
            pol = json.loads(_read_text(pol_path))
            deny_terms = [str(x) for x in (pol.get("extra_deny") or [])] if isinstance(pol, dict) else []
    auto = TermMatcher([(str(i), t) for i, t in enumerate(auto_identity_terms() if anonymous else [], 1)])
    red = Redactor(identity, auto, TermMatcher([(str(i), t) for i, t in enumerate(deny_terms, 1)]))
    red.derived_users = derived_usernames(terms_)  # logins an author's name becomes (deterministic evidence)
    return red


def _parse_supp_reviews(paths: Sequence[str]) -> Tuple[List[Dict[str, Any]], Set[str], List[str]]:
    """Findings and members_checked of the supplementary batch reviewers."""
    found: List[Dict[str, Any]] = []
    checked: Set[str] = set()
    problems: List[str] = []
    for p in paths:
        obj = parse_review(_read_text(p)) if p and os.path.isfile(p) else None
        if obj is None:
            problems.append("supp_review_unreadable:%s" % os.path.basename(str(p)))
            continue
        for rf in obj.get("findings") or []:
            if not isinstance(rf, dict):
                continue
            rf = dict(rf)
            if str(rf.get("lens") or "").strip().lower() not in ("engineering", "anonymity"):
                rf["lens"] = "anonymity" if str(rf.get("category") or "").strip().lower() == "identity" else "engineering"
            found.append(rf)
        for m in obj.get("members_checked") or []:
            checked.add(_collapse_ws(str(m)))
    return found, checked, problems


def _supp_coverage(scan: Dict[str, Any], checked: Set[str], status: str,
                   findings: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Every member of every supplementary batch must be marked checked by a
    batch reviewer; the rest is a coverage gap (SUPP-COVERAGE, WARN). Members
    the review text budget left out of every batch, or cut short, were never
    read in full: they count as not covered, whatever a reply lists."""
    batches = (scan.get("inputs") or {}).get("supp_batches") or []
    expected = [m for b in batches for m in b.get("members") or []]
    supps = (scan.get("inputs") or {}).get("supp") or []
    left = [m for s in supps for m in s.get("review_left_out") or []]
    n_left = sum(int(s.get("review_left_out_n") or len(s.get("review_left_out") or [])) for s in supps)
    cut = list(dict.fromkeys(m for s in supps for m in s.get("review_cut") or []))
    partial = sum(int(s.get("review_partial") or 0) for s in supps)
    scope: Counter = Counter()
    for s in supps:
        scope.update(s.get("review_scope_out") or {})
    if not expected and not n_left:
        return {}
    low = {c.casefold() for c in checked}
    cut_set = set(cut)
    unchecked = [m for m in expected if _collapse_ws(m).casefold() not in low and m not in cut_set]
    missing = unchecked + [m for m in cut if m in set(expected)] + left
    out = {"batches": len(batches), "members": len(expected) + n_left, "sent": len(expected),
           "checked": len(expected) - len(unchecked) - len([m for m in cut if m in set(expected)]),
           "cut": len(cut), "not_sent": n_left, "partial_notes": partial, "missing": missing[:50],
           # outside the batch review by design (the rules scan them): the scope of the count above
           "not_in_review": dict(sorted(scope.items()))}
    if (unchecked or cut or n_left) and status == "ok":
        spec = CHECKS["SUPP-COVERAGE"]
        bits = ["%d unchecked" % len(unchecked)] if unchecked else []
        if cut:
            bits.append("%d sent only in part" % len(cut))
        if n_left:
            bits.append("%d never sent (over the review text budget)" % n_left)
        findings.append({
            "id": "SUPP-COVERAGE-001", "group": "S-COV", "check": "SUPP-COVERAGE", "family": "SUPP",
            "severity": WARN, "certainty": DEFINITE, "confirm_severity": None, "layer": "review", "region": None,
            "subregion": None, "location": {"artifact": None, "page": None, "file": None, "line": None, "member": None},
            "match": "%d of %d member(s) not covered: %s" % (len(unchecked) + len(cut) + n_left, out["members"],
                                                            ", ".join(bits)),
            "excerpt": "; ".join(missing[:10]) + (" …" if len(missing) > 10 else ""), "redacted": False,
            "rule": spec["rule"], "route": spec["route"], "suggestion": spec["fix"], "exempted_by": None,
            "ruling": None, "note": None, "demoted": None})
    return out


def _supp_reread_members(scan: Dict[str, Any], checked: Set[str]) -> Set[str]:
    """The supplementary members a batch reviewer of this run was given and
    marked checked, never one the review text budget cut short or left out:
    what a carried finding may count as re-read in full (merge_review)."""
    batches = (scan.get("inputs") or {}).get("supp_batches") or []
    supps = (scan.get("inputs") or {}).get("supp") or []
    short = {m for s in supps for m in list(s.get("review_cut") or []) + list(s.get("review_left_out") or [])}
    low = {_collapse_ws(c).casefold() for c in checked}
    return {m for b in batches for m in b.get("members") or []
            if _collapse_ws(m).casefold() in low and m not in short}


def _read_member_text(archive: str, member: str) -> Optional[str]:
    """The current text of one supplementary member (a directory, zip, or tar),
    or None when it cannot be read (nested archives included)."""
    if not member or "!/" in member:
        return None
    try:
        if os.path.isdir(archive):
            p = os.path.join(archive, member)
            return _decode_text(open(p, "rb").read())[0] if os.path.isfile(p) else ""
        if zipfile.is_zipfile(archive):
            with zipfile.ZipFile(archive) as zf:
                try:
                    return _decode_text(zf.read(member))[0]
                except KeyError:
                    return ""
        with tarfile.open(archive, "r:*") as tf:
            try:
                fh = tf.extractfile(member)
            except KeyError:
                return ""
            return _decode_text(fh.read())[0] if fh else ""
    except (OSError, zipfile.BadZipFile, tarfile.TarError, zlib.error, lzma.LZMAError, EOFError, RuntimeError):
        return None


def _carry_from_state(state: Dict[str, Any], scan: Dict[str, Any], findings: List[Dict[str, Any]], paper_dir: str,
                      run_mode: str, page_texts: Dict[str, Dict[int, str]], supp_texts: Dict[str, str]
                      ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """What the latest fix round left that this run must not lose: NUM-DRIFT
    stops a recheck without a baseline cannot re-check. Reviewer findings come
    back through the scan's carried_findings, code names through the scan's
    persisted list, and edits through the scan's edit check."""
    out: List[Dict[str, Any]] = []
    run = state.get("run") or "the fix run"
    info: Dict[str, Any] = {"from": run, "generated_at": state.get("generated_at"), "stops": []}
    if run_mode == "recheck" and "NUM-DRIFT" not in set(scan.get("checks_run") or []):
        for g in state.get("stop_conditions") or []:
            if g.get("check") != "NUM-DRIFT":
                continue  # CONFIG-CHANGED freezes the fix loop only
            spec = CHECKS["NUM-DRIFT"]
            out.append({"id": "NUM-DRIFT-CARRIED", "group": "K-%s" % str(g.get("group")), "check": "NUM-DRIFT",
                        "family": "NUM", "severity": WARN, "certainty": DEFINITE, "confirm_severity": None,
                        "layer": "pdf", "region": None, "subregion": None,
                        "location": {"artifact": None, "page": None, "file": None, "line": None, "member": None},
                        "match": str(g.get("match") or "")[:200],
                        "excerpt": "the fix run stopped on this number (%s); this recheck has no --baseline to "
                                   "re-check it" % ", ".join(g.get("where") or []), "redacted": False,
                        "rule": spec["rule"], "route": spec["route"],
                        "suggestion": "Re-run the recheck with --baseline <WORK>/scan_r0.json, or settle the number "
                                      "with /paper-claim-audit.", "exempted_by": None, "ruling": None,
                        "note": None, "demoted": None, "carried_from": run})
            info["stops"].append(g.get("group"))
    return out, info


def _write_memory(work_dir: str, ledger: Optional[Dict[str, Any]], memo: Dict[str, Any], run_label: str,
                  handle: str, run_mode: str, findings: List[Dict[str, Any]], fix_queue: List[Dict[str, Any]],
                  stops: List[Dict[str, Any]], scan: Dict[str, Any], verdict: str, reasons: List[str],
                  fix_round: Optional[int]) -> None:
    """Persist the cross-round memory in WORK: the rulings ledger, and (fix
    runs) the state a later round or the recheck carries — reviewer findings
    still in the text, code names, stops — and the fix history (every queued
    item: the matches a later deletion may remove)."""
    if ledger is not None and memo.get("ledger_updates"):
        for u in memo["ledger_updates"]:
            e = ledger["entries"].setdefault(u["key"], {"check": u["check"], "match": u["match"]})
            for k in ("region", "subregion", "page", "artifact", "member", "reviewer_finding"):
                if u.get(k) is not None:
                    e[k] = u[k]
            e["match"] = u["match"]
            rs = [r for r in e.get("rulings") or [] if r.get("run") != run_label]
            rs.append({"run": run_label, "ruling": u["ruling"], "effective": u["effective"],
                       "rationale": u.get("rationale"), "new_evidence": u.get("new_evidence"), "by": handle,
                       "at": _now()})
            e["rulings"] = rs[-12:]
        _write_atomic(os.path.join(work_dir, LEDGER_NAME), json.dumps(ledger, ensure_ascii=False, indent=1) + "\n")
    if run_mode != "fix":
        return
    rev = [f for f in findings if f.get("layer") == "review" and f.get("anchored") and not f.get("exempted_by")
           and f["severity"] in (WARN, BLOCK) and f["check"].startswith("LENS-")]
    codenames = sorted({f["match"] for f in findings if f["check"] == "ANON-CODENAME" and not f.get("exempted_by")
                        and f.get("ruling") not in CLEARING_RULINGS and f.get("match")})
    state = {
        "version": 2, "skill": SKILL_NAME, "run": run_label, "generated_at": _now(), "verdict": verdict,
        "reasons": reasons, "snapshot": (scan.get("snapshot") or {}).get("id"),
        "fix_queue": fix_queue, "stop_conditions": stops, "codenames": codenames,
        "reviewer_findings": [{"key": stable_key(f["check"], f["match"]), "check": f["check"], "family": f["family"],
                               "severity": f["severity"], "reviewer_severity": f.get("reviewer_severity"),
                               "quote": f["match"], "artifact": f["location"].get("artifact"),
                               "page": f["location"].get("page"), "member": f["location"].get("member"),
                               "rationale": f.get("ruling_rationale"), "rewrite": f.get("rewrite"),
                               "run": f.get("carried_from") or run_label, "by": f.get("ruled_by")} for f in rev],
    }
    _write_atomic(os.path.join(work_dir, STATE_NAME), json.dumps(state, ensure_ascii=False, indent=1) + "\n")
    hp = os.path.join(work_dir, FIX_HISTORY_NAME)
    hist = _load_json(hp) or {"version": 1, "items": {}}
    if not isinstance(hist.get("items"), dict):
        hist["items"] = {}
    for g in fix_queue:
        if g.get("fix_class") in ("delete", "delete-sentence", "marker", "supp-delete", "escape", "xref-ref",
                                  "xref-cite", "meta"):
            h = hist["items"].setdefault(g["key"], {"group": g["group"], "check": g["check"],
                                                    "fix_class": g["fix_class"], "match": g["match"],
                                                    "round": fix_round})
            for x in g.get("anchors") or []:  # every text a later deletion may have removed
                if x not in h.setdefault("anchors", []) and len(h["anchors"]) < 50:
                    h["anchors"].append(x)
    _write_atomic(hp, json.dumps(hist, ensure_ascii=False, indent=1) + "\n")


def _blocked_keys(applied: Sequence[Tuple[int, str, Dict[str, Any]]]) -> Dict[str, str]:
    """Stable keys whose automatic fix is over: an applied edit that was undone
    (it caused a regression), or a proposal the whitelist rejected. They go to
    the fix plan, so no later round tries again. An edit undone for a layout
    regression (the body grew, it stopped filling the page or keeping the
    limit) is located by halving the round's suspects, so an innocent edit can
    be undone with the culprit: it is tried again in the next round, and only a
    second layout undo of the same key ends its automatic fix."""
    out: Dict[str, str] = {}
    layout_undos: Counter = Counter()
    for rn, _p, d in applied:
        for r in d.get("applied") or []:
            if r.get("undone") and r.get("key"):
                if (r["undone"] or {}).get("kind") == "layout":
                    layout_undos[r["key"]] += 1
                    if layout_undos[r["key"]] < 2:
                        continue
                out[r["key"]] = "its automatic fix (round %d) was undone: %s" % (rn, r["undone"].get("reason"))
        for r in d.get("rejected") or []:
            if r.get("whitelist") and r.get("key"):
                out.setdefault(r["key"], "the proposed edit (round %d) is outside the whitelist: %s" % (rn, r.get("why")))
    return out


def _edit_pages(rec: Dict[str, Any], page_words: Dict[Tuple[str, int], List[str]]) -> Set[int]:
    """Pages whose text holds the words around an applied edit (5-word windows)."""
    words = _wordlist(_detex_line((rec.get("left") or "") + " " + (rec.get("after") or "") + " "
                                  + (rec.get("right") or "")))
    pages: Set[int] = set()
    for i in range(0, max(1, len(words) - 4)):
        win = words[i:i + 5]
        if len(win) < 3:
            break
        for (art, pg), pw in page_words.items():
            if pg in pages:
                continue
            for j in range(0, len(pw) - len(win) + 1):
                if pw[j:j + len(win)] == win:
                    pages.add(pg)
                    break
    return pages


def undo_suspects(findings: List[Dict[str, Any]], applied: Sequence[Tuple[int, str, Dict[str, Any]]], rnd: int,
                  page_texts: Dict[str, Dict[int, str]]) -> List[Dict[str, Any]]:
    """What this round must undo, and nothing more: every change the whitelist
    refused (FIX-EDIT, by its E-id: a text edit, or a member change put back
    from round 0's supplement), and the applied edits a regression against the
    previous round points to. A layout regression is never the doing of a
    metadata line or of a supplement edit (they change no page); of the paper
    edits, the ones on the page it names (by the words around each edit), an
    XREF repair for a new ?? or (?), the edits on body pages for a page fill or
    limit — and all paper edits of the round only when none can be located.
    Edits in other files or on other pages are never taken back with it."""
    out: Dict[str, Dict[str, Any]] = {}
    for f in findings:
        if f["check"] == "FIX-EDIT" and f["severity"] != INFO and not f.get("exempted_by") and f.get("edit_id"):
            out.setdefault(f["edit_id"], {"id": f["edit_id"], "group": f.get("group"), "key": None,
                                          "why": f["match"], "part": _finding_part(f), "kind": "edit"})
    regs = [f for f in findings if f["check"] == "FIX-REGRESSION" and f["severity"] != INFO
            and not f.get("exempted_by") and (f.get("regression") or {}).get("against") == "the previous round"]
    if regs:
        this = [r for rn, _p, d in applied if rn == rnd for r in d.get("applied") or []
                if not r.get("undone") and r.get("file") and "meta" not in str(r.get("class") or "")]
        page_words = {(art, pg): _wordlist(t) for art, pages in page_texts.items() for pg, t in pages.items()}
        pages_of = {r["id"]: _edit_pages(r, page_words) for r in this}
        for f in regs:
            kind, pg = (f.get("regression") or {}).get("kind", ""), f["location"].get("page")
            layout = kind in ("fill_ok", "limit_ok", "pages")
            if kind in ("qq", "cite_q"):
                sus = [r for r in this if str(r.get("class") or "").startswith("xref")] or this
            elif (kind.startswith("glyph") or kind == "glue") and pg:
                sus = [r for r in this if pg in pages_of[r["id"]]] or this
            elif layout and pg:
                sus = [r for r in this if pages_of[r["id"]] and min(pages_of[r["id"]]) <= int(pg)] or this
            else:
                sus = this
            bisect_note = None
            if layout and len(sus) > 1:
                # one edit made the body longer, not the round: undo half of the suspects, rebuild, and
                # check again (the next finalize of the same round halves what is left); the other half stays
                order = sorted(sus, key=lambda r: (min(pages_of.get(r["id"]) or {0}), r["id"]))
                half = order[:(len(order) + 1) // 2]
                bisect_note = {"suspects": [r["id"] for r in order], "undo_now": [r["id"] for r in half]}
                sus = half
            for r in sus:
                rec = out.setdefault(r["id"], {"id": r["id"], "group": r.get("group"), "key": r.get("key"),
                                               "why": f["match"], "part": "paper",
                                               "kind": "layout" if layout else "regression"})
                if bisect_note:
                    rec["bisect"] = bisect_note
    return [out[k] for k in sorted(out)]


def _finding_part(f: Dict[str, Any]) -> str:
    """Which delivered file a finding is about: the supplement or the paper."""
    if f["check"] == "FIX-EDIT":
        return "supp" if (f.get("location") or {}).get("member") else "paper"
    return "supp" if f.get("family") == "SUPP" else "paper"


def _finding_sig(f: Dict[str, Any]) -> str:
    """A finding's place-independent identity across rounds: its stable key,
    the part it is about, and its member."""
    return "%s|%s|%s" % (stable_key(f["check"], f.get("match"), f.get("region"), f.get("subregion")),
                         _finding_part(f), (f.get("location") or {}).get("member") or "")


def _edited_places(applied: Sequence[Tuple[int, str, Dict[str, Any]]], rnd: int,
                   page_texts: Optional[Dict[str, Dict[int, str]]]
                   ) -> Tuple[Set[int], Set[str], Set[str], List[List[str]]]:
    """(pages, files, members, word runs) the fix loop's kept edits of rounds
    <= rnd changed: a page by the words around each paper edit, and the words
    around each edit (to tell whether a finding sits in edited text)."""
    pages: Set[int] = set()
    files: Set[str] = set()
    members: Set[str] = set()
    runs: List[List[str]] = []
    page_words = {(art, pg): _wordlist(t) for art, pp in (page_texts or {}).items() for pg, t in pp.items()}
    for rn, _p, d in applied:
        if rn > rnd:
            continue
        for r in d.get("applied") or []:
            if r.get("undone"):
                continue
            if r.get("member"):
                members.add(str(r["member"]))
            elif r.get("file"):
                files.add(str(r["file"]))
                if page_words and "meta" not in str(r.get("class") or ""):
                    pages |= _edit_pages(r, page_words)
            if "meta" not in str(r.get("class") or ""):
                runs.append(_wordlist(_detex_line((r.get("left") or "") + " " + (r.get("after") or "") + " "
                                                  + (r.get("right") or ""))))
    return pages, files, members, runs


def _in_edited_text(f: Dict[str, Any], runs: Sequence[Sequence[str]]) -> Optional[bool]:
    """Whether a finding's excerpt shares a run of three words with the text
    around a kept edit (None: the finding has no words to tell)."""
    words = _wordlist(_excerpt_core(str(f.get("excerpt") or "")))
    if len(words) < 3:
        return None
    grams = {tuple(words[i:i + 3]) for i in range(len(words) - 2)}
    return any(tuple(r[i:i + 3]) in grams for r in runs for i in range(max(0, len(r) - 2)))


def _record_round(work_dir: str, paper_dir: str, rnd: int, verdict: str, counts: Dict[str, int],
                  findings: List[Dict[str, Any]], scan: Dict[str, Any],
                  applied: Sequence[Tuple[int, str, Dict[str, Any]]] = (),
                  page_texts: Optional[Dict[str, Dict[int, str]]] = None) -> Dict[str, Any]:
    """rounds.json: what each fix round left (blocking findings, regressions,
    rejected edits, the snapshot and a copy of the supplement it audited), and
    the round the run delivers: the fewest blocking findings with no
    regression and no rejected edit (ties: the later round). The paper and the
    supplement are judged apart as well (best_paper_round, best_supp_round): a
    supplement problem never takes the paper's verified fixes back with it, nor
    the reverse — the run then delivers each part from its own best round.
    Rounds are compared by the blocking findings their edits brought in
    (`block_new`): a blocker round 0 already had, and one in text no kept
    edit changed (the same passage ruled `uncertain` in one round and `leak`
    in another is the reviewer's variance, not a round's doing), never takes a
    round's verified fixes (a re-pack, members left out, archive metadata,
    deletions elsewhere) back with it."""
    rp = os.path.join(work_dir, ROUNDS_NAME)
    data = _load_json(rp) or {"version": 1, "rounds": []}
    live = [f for f in findings if not f.get("exempted_by")]
    r0 = next((r for r in data.get("rounds") or [] if r.get("round") == 0), None)
    if rnd == 0:
        r0_keys = {_finding_sig(f) for f in live}
        r0_block = {_finding_sig(f) for f in live if f["severity"] == BLOCK}
    else:
        r0_keys, r0_block = set((r0 or {}).get("keys") or []), set((r0 or {}).get("block_keys") or [])
    pages_e, files_e, members_e, runs_e = _edited_places(applied, rnd, page_texts)

    def is_new(f: Dict[str, Any]) -> bool:
        sig = _finding_sig(f)
        if rnd == 0 or sig in r0_block:
            return False                        # it was blocking before any edit
        loc = f.get("location") or {}
        if loc.get("member"):
            if str(loc["member"]) not in members_e:
                return False
            near = _in_edited_text(f, runs_e)
            return True if near is None else near
        if loc.get("file") or loc.get("page"):
            near = _in_edited_text(f, runs_e)
            if near is not None:
                return near
            if loc.get("file"):
                return str(loc["file"]) in files_e
            try:
                return int(loc["page"]) in pages_e
            except (TypeError, ValueError):
                pass
        return sig not in r0_keys               # no place to read: new when round 0 did not have it
    new_blocks = [f for f in live if f["severity"] == BLOCK and is_new(f)]
    regs = [f["match"] for f in live if f["check"] == "FIX-REGRESSION" and f["severity"] != INFO]
    bad_edits = [f for f in live if f["check"] == "FIX-EDIT" and f["severity"] != INFO]
    rejected = [f.get("edit_id") or f["match"] for f in bad_edits]
    paper_ok = not regs and not any(_finding_part(f) == "paper" for f in bad_edits)
    supp_ok = not any(_finding_part(f) == "supp" for f in bad_edits)
    supps = []
    for s in (scan.get("inputs") or {}).get("supp") or []:
        path, sha = s.get("path"), s.get("sha256")
        full = path if (path and os.path.isabs(path)) else os.path.join(paper_dir, path or "")
        rec: Dict[str, Any] = {"path": path, "sha256": sha}
        if sha and os.path.isfile(full):
            dst = os.path.join(work_dir, "rounds", "%s_%s" % (sha[:12], os.path.basename(full)))
            if not os.path.isfile(dst):
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(full, dst)
            rec["copy"] = _rel(dst, work_dir)
        supps.append(rec)
    entry = {"round": rnd, "verdict": verdict, "block": counts.get(BLOCK, 0), "warn": counts.get(WARN, 0),
             "block_paper": sum(1 for f in live if f["severity"] == BLOCK and _finding_part(f) == "paper"),
             "block_supp": sum(1 for f in live if f["severity"] == BLOCK and _finding_part(f) == "supp"),
             "block_new": len(new_blocks),
             "block_new_paper": sum(1 for f in new_blocks if _finding_part(f) == "paper"),
             "block_new_supp": sum(1 for f in new_blocks if _finding_part(f) == "supp"),
             "regressions": regs, "rejected_edits": rejected, "snapshot": (scan.get("snapshot") or {}).get("id"),
             "supplements": supps, "generated_at": _now(),
             "paper_ok": paper_ok, "supp_ok": supp_ok, "eligible": paper_ok and supp_ok}
    if rnd == 0:
        entry["keys"], entry["block_keys"] = sorted(r0_keys), sorted(r0_block)
    data["rounds"] = sorted([r for r in data.get("rounds") or [] if r.get("round") != rnd] + [entry],
                            key=lambda r: r.get("round", 0))
    # rounds are compared by the blocking findings they brought in (round 0 recorded what it had)
    compare_new = all("block_new" in r for r in data["rounds"]) and any(
        "keys" in r for r in data["rounds"] if r.get("round") == 0)

    def best_of(ok_key: str, block_key: str) -> Optional[int]:
        ok = [r for r in data["rounds"] if r.get(ok_key, r.get("eligible"))]
        key = block_key.replace("block", "block_new", 1) if compare_new else block_key
        b = min(ok, key=lambda r: (r.get(key, r.get("block", 0)), -r.get("round", 0))) if ok else None
        return b.get("round") if b else None
    data["best_round"] = best_of("eligible", "block")
    data["best_paper_round"] = best_of("paper_ok", "block_paper")
    data["best_supp_round"] = best_of("supp_ok", "block_supp")
    _write_atomic(rp, json.dumps(data, ensure_ascii=False, indent=1) + "\n")
    bp, bs = data["best_paper_round"], data["best_supp_round"]
    has_supp = bool(supps)
    by_round = {r.get("round"): r for r in data["rounds"]}
    supp_file = None
    if has_supp and bs is not None:
        supp_file = ((by_round.get(bs) or {}).get("supplements") or [{}])[0].get("path")
    if data["best_round"] == rnd and bp in (rnd, None) and (bs in (rnd, None) or not has_supp):
        deliver = "this round"
    elif bp is not None and (bs == bp or not has_supp):
        deliver = "round %s: run `restore --round %s`, rebuild, scan, and finalize to confirm" % (bp, bp)
    elif bp is not None and bs is not None:
        bits = ["the paper of %s" % ("this round" if bp == rnd else "round %s (`restore --round %s --part paper`, "
                                                                     "rebuild)" % (bp, bp)),
                "the supplement of %s" % ("this round" if bs == rnd else "round %s (`restore --round %s --part supp`)"
                                          % (bs, bs))]
        deliver = "%s; then scan and finalize to confirm" % " and ".join(bits)
    else:
        deliver = "no eligible round"
    return {"rounds": [{k: r.get(k) for k in ("round", "verdict", "block", "warn", "regressions", "rejected_edits",
                                              "eligible", "paper_ok", "supp_ok")} for r in data["rounds"]],
            "best_round": data["best_round"], "best_paper_round": bp, "best_supp_round": bs if has_supp else None,
            "current": rnd, "deliver": deliver,
            "deliver_parts": {"paper_round": bp, "supp_round": bs if has_supp else None,
                              "supplement": supp_file}}


def _round0_snapshot(work_dir: str) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    rounds = (_load_json(os.path.join(work_dir, ROUNDS_NAME)) or {}).get("rounds") or []
    rec = next((r for r in rounds if isinstance(r, dict) and r.get("round") == 0), None)
    sid = (rec or {}).get("snapshot")
    if not sid:
        return None, None
    sdir = os.path.join(work_dir, "snapshots", str(sid))
    man = _load_json(os.path.join(sdir, "manifest.json"))
    return (sdir, man) if isinstance(man, dict) else (None, None)


def _recompute_edit(e: Dict[str, Any], cur_supp: Optional[str], r0_supp: Optional[str], work_dir: str,
                    paper_dir: str, red: Redactor) -> Tuple[str, str]:
    """('overturned' | 'upheld', why): the change a FIX-EDIT names, recomputed
    from the files themselves (whole members and files, no scan budget)."""
    op, kind = e.get("op"), e.get("kind")
    history = _load_json(os.path.join(work_dir, FIX_HISTORY_NAME))

    def same(b0: Optional[bytes], b1: Optional[bytes]) -> bool:
        return b0 is not None and b1 is not None and _sha256_bytes(b0) == _sha256_bytes(b1)
    if kind == "supplement":
        if not (cur_supp and r0_supp and os.path.exists(cur_supp)):
            return "upheld", "round 0's supplement or the audited archive cannot be read"
        name = str(e.get("member") or "")
        shown = red.redact(name)
        b0, b1 = member_bytes(r0_supp, name), member_bytes(cur_supp, name)
        if op == "remove":
            if b1 is None:
                return "upheld", "%s is not in the audited archive" % shown
            if same(b0, b1):
                return "overturned", "%s is in the audited archive with round 0's bytes (sha256 %s…)" % (
                    shown, _sha256_bytes(b1)[:12])
            return "upheld", "%s is in the archive, but its bytes differ from round 0" % shown
        if op == "add":
            if same(b0, b1):
                return "overturned", "round 0's supplement has %s with the same bytes" % shown
            return "upheld", "round 0's supplement %s" % ("has other bytes for it" if b0 is not None else
                                                         "does not have %s" % shown)
        if op == "rename":
            old = str(e.get("old_member") or "")
            if old and same(member_bytes(r0_supp, old), member_bytes(cur_supp, old)) and same(b0, b1):
                return "overturned", "both names are in both archives with the same bytes: nothing was renamed"
            return "upheld", "the names differ between round 0 and the audited archive"
        if op == "data":
            for n in list(e.get("members") or []) or [name]:
                if not same(member_bytes(r0_supp, n), member_bytes(cur_supp, n)):
                    return "upheld", "%s has other bytes than in round 0" % red.redact(n)
            return "overturned", "every data member it names has round 0's bytes"
        if op == "edit":
            if b0 is None or b1 is None:
                return "upheld", "%s cannot be read in both archives" % shown
            if same(b0, b1):
                return "overturned", "%s has round 0's bytes: nothing changed" % shown
            ec = edit_check_for([], red, history)
            for it in line_edits(_decode_text(b0)[0], _decode_text(b1)[0], code=_member_kind(name) == "code",
                                 member=name):
                v = verify_change(it["_raw_before"], it["_raw_after"], ec, "supplement", bool(it.get("code_logic")))
                if v["verdict"] != "ok":
                    return "upheld", "recomputed on the whole member: %s" % v["why"]
            return "overturned", "recomputed on the whole member: every change passes the whitelist"
        return "upheld", "this kind of change cannot be recomputed"
    if kind == "paper":
        sdir, man = _round0_snapshot(work_dir)
        rel = str(e.get("file") or "")
        old = _snap_text(sdir, ((man or {}).get("paper_files") or {}).get(rel)) if sdir else None
        cur = _within(paper_dir, rel)
        new = None
        if cur and os.path.isfile(cur):
            with open(cur, "rb") as fh:
                new = _decode_text(fh.read())[0]
        if old is None or new is None:
            return "upheld", "round 0's snapshot or the current file cannot be read"
        if old == new:
            return "overturned", "%s has round 0's text: nothing changed" % rel
        ec = edit_check_for(_paper_sources(paper_dir), red, history)
        for it in prose_edits(old, new):
            v = verify_change(it["_raw_before"], it["_raw_after"], ec, "paper")
            if v["verdict"] != "ok":
                return "upheld", "recomputed on the whole file: %s" % v["why"]
        return "overturned", "recomputed on the whole file: every change passes the whitelist"
    return "upheld", "this kind of change cannot be recomputed"


def contest_edits(ids: Sequence[str], findings: List[Dict[str, Any]], scan: Dict[str, Any],
                  work_dir: Optional[str], paper_dir: str, red: Redactor) -> List[Dict[str, Any]]:
    """FIX-EDIT findings the executor contests (`--contest-edit E-xxxxxxxx`).
    Finalize re-reads the files itself — round 0's supplement copy and
    snapshot against the audited archive and sources — and overturns a finding
    (INFO, noted) only when the bytes show no such change (a member 'left out'
    that is in the archive with round 0's bytes, an 'added' one round 0 had,
    data that did not change) or the change passes the whitelist on the whole
    file. The executor's word overturns nothing; an upheld finding stays."""
    out: List[Dict[str, Any]] = []
    raw = (_load_json(os.path.join(work_dir, "edits_check.raw.json")) if work_dir else None) or {}
    cur = next((s.get("path") for s in (scan.get("inputs") or {}).get("supp") or [] if s.get("path")), None)
    cur_supp = (cur if os.path.isabs(cur) else os.path.normpath(os.path.join(paper_dir, cur))) if cur else None
    r0_supp = _round0_supplement(work_dir, paper_dir) if work_dir else None
    for eid in dict.fromkeys(str(x).strip() for x in ids if str(x).strip()):
        f = next((x for x in findings if x["check"] == "FIX-EDIT" and x.get("edit_id") == eid), None)
        res: Dict[str, Any] = {"id": eid, "verdict": "upheld"}
        e = raw.get(eid)
        if f is None:
            res["why"] = "no FIX-EDIT with this id in this scan"
        elif not isinstance(e, dict) or not work_dir:
            res["why"] = "the scan kept no record of this change (edits_check.raw.json in --work-dir)"
        else:
            res.update(op=e.get("op"), where=red.redact(str(e.get("file") or e.get("member") or "")))
            res["verdict"], res["why"] = _recompute_edit(e, cur_supp, r0_supp, work_dir, paper_dir, red)
        if f is not None:
            f["contested"] = {"verdict": res["verdict"], "why": res["why"]}
            if res["verdict"] == "overturned":
                f["original_severity"], f["severity"] = f["severity"], INFO
            f["note"] = "; ".join(x for x in (f.get("note"), "contested, %s: %s" % (res["verdict"], res["why"])) if x)
        out.append(res)
    return out


def run_finalize(a: Any) -> Tuple[Dict[str, Any], int]:
    paper_dir = os.path.abspath(a.paper_dir)
    try:
        scan = json.loads(_read_text(a.scan))
        if not isinstance(scan, dict) or "findings" not in scan:
            raise ValueError("not a scan document")
    except (OSError, ValueError) as e:
        raise UsageError("cannot read --scan: %s" % e) from None
    tier_a = scan.get("verdict_tier_a")
    if tier_a not in VERDICTS or tier_a == "ERROR":
        # Fail closed: a scan that crashed or was misused acquits nothing, so it
        # can never be finalized into PASS (its findings list is simply empty).
        raise UsageError("--scan is not a completed Tier A scan (verdict_tier_a=%s, reason_code=%s); "
                         "fix the scan error and re-run scan before finalize"
                         % (tier_a, scan.get("reason_code")))
    status = a.review_status
    tiers = ["A"]
    review_obj = None
    handle = a.thread_id or a.agent_id or DETERMINISTIC_REVIEWER
    notes: List[str] = []
    lenses_run: List[str] = []
    if status == "ok":
        if not a.review or not os.path.isfile(a.review):
            raise UsageError("--review-status ok needs --review pointing at the reviewer's raw response")
        if not (a.reviewer_model and a.reviewer_reasoning and (a.thread_id or a.agent_id)):
            raise UsageError("--review-status ok needs --reviewer-model, --reviewer-reasoning and "
                             "--thread-id or --agent-id (the model and effort that actually ran)")
        review_obj = parse_review(_read_text(a.review))
        if review_obj is None:
            status = "malformed"
        else:
            tiers.append("B")
    run_mode = a.run_mode or scan.get("run_mode")
    run_label = ("recheck" if run_mode == "recheck" else "fix r%d" % (a.fix_round or 0) if run_mode == "fix"
                 else "audit")
    work_dir = os.path.abspath(a.work_dir) if getattr(a, "work_dir", None) else None
    ledger = load_ledger(work_dir) if work_dir else None
    red = _finalize_redactor(scan, paper_dir, a.config_dir)
    page_texts = _load_page_texts(scan, paper_dir)
    supp_texts = _load_supp_texts(scan, paper_dir)
    # provenance first: whether a reviewer's confirmation may block depends on it
    fam_warn: List[str] = []
    exec_fam, w = _model_family(a.executor_model)
    if w:
        fam_warn.append(w)
    if status == "skipped":
        reviewer_model, reviewer_fam, independence, acceptance, reasoning = (
            DETERMINISTIC_REVIEWER, "deterministic", "deterministic", "accepted", "n/a")
    else:
        reviewer_model = a.reviewer_model or "unknown"
        reviewer_fam, w = _model_family(reviewer_model)
        if w and w not in fam_warn:
            fam_warn.append(w)
        reasoning = a.reviewer_reasoning or "unknown"
        if reviewer_fam not in ("unknown", "deterministic") and exec_fam not in ("unknown",) and reviewer_fam != exec_fam:
            independence, acceptance = "cross-family", "accepted"
        else:
            independence, acceptance = "same-family", "provisional"
            if "unknown" in (reviewer_fam, exec_fam):
                fam_warn.append("unrecognized model family (executor=%s, reviewer=%s); recorded as same-family/provisional"
                                % (exec_fam, reviewer_fam))
    supp_found, supp_checked, supp_problems = _parse_supp_reviews(getattr(a, "supp_review", None) or [])
    notes += supp_problems
    findings, more_notes, lenses_run, memo = merge_review(
        scan, review_obj if review_obj is not None else {"rulings": [], "findings": []}, page_texts, handle, red,
        supp_texts, ledger, run_label, supp_found if review_obj is not None else (),
        cross_family=independence in ("cross-family", "deterministic"),
        supp_reread=_supp_reread_members(scan, supp_checked) if review_obj is not None and supp_checked else None)
    notes += more_notes
    # a reviewer finding that holds only what the authors' policy keeps is no finding (INFO, listed)
    policy_demoted = demote_by_policy(findings, scan.get("policy") or {}, bool(scan.get("anonymous", True)),
                                      page_texts, str(scan.get("hardware") or "block"))
    supp_cov = _supp_coverage(scan, supp_checked, status, findings)
    state = _load_json(os.path.join(work_dir, STATE_NAME)) if work_dir and run_mode in ("fix", "recheck") else None
    carried_info: Dict[str, Any] = {}
    if isinstance(state, dict) and (run_mode == "recheck" or (run_mode == "fix" and (a.fix_round or 0) > 0)):
        extra, carried_info = _carry_from_state(state, scan, findings, paper_dir, run_mode, page_texts, supp_texts)
        findings += extra
    # a FIX-EDIT the executor contests is recomputed from the files; only the bytes can overturn it
    contested = (contest_edits(a.contest_edit, findings, scan, work_dir, paper_dir, red)
                 if getattr(a, "contest_edit", None) else [])
    carried_now = [f for f in findings if f.get("carried_from") and f.get("layer") == "review"]
    if carried_now or carried_info.get("stops"):
        carried_info.setdefault("from", (state or {}).get("run"))
        carried_info["reviewer_findings"] = [dict({"group": f["group"], "check": f["check"], "quote": f["match"],
                                                   "where": _where_str(f), "reviewer_severity": f.get("reviewer_severity")},
                                                  **({"reread_clean": True} if f.get("reread_clean") else {}))
                                             for f in carried_now]
    applied = _applied_logs(work_dir) if work_dir else []
    blocked_keys = _blocked_keys(applied)
    for k_, why_ in _discarded_keys(work_dir, run_mode, a.fix_round, applied).items():
        blocked_keys.setdefault(k_, why_)
    # pure-leak sentences and clauses (the delete-sentence class), and the narration a reword cannot keep at WARN
    units = pure_leak_units(findings, paper_dir, scan.get("policy") or {}, independence == "cross-family",
                            bool(scan.get("anonymous", True)), red=red)
    narration_raised = escalate_pure_narration(findings, units, independence == "cross-family")
    strict = bool(a.strict) or bool(scan.get("strict"))
    blocked = scan.get("blocked", [])
    nothing = scan.get("verdict_tier_a") == "NOT_APPLICABLE"
    verdict, reason = final_verdict(findings, blocked, scan.get("checks_skipped", []), strict, status, nothing)
    reasons = verdict_reasons(findings, blocked, scan.get("checks_skipped", []), strict, status, nothing)
    counts = _counts(findings)
    # trace
    today = datetime.now().strftime("%Y-%m-%d")
    trace_dir = a.trace_dir or _default_trace_dir(today)
    os.makedirs(trace_dir, exist_ok=True)
    # one file per round and one for the recheck: a recheck never overwrites round 0
    name = "tier-a-scan%s.json" % (".r%d" % a.fix_round if a.fix_round is not None else
                                   ".recheck" if run_mode == "recheck" else "")
    _write_atomic(os.path.join(trace_dir, name), _read_text(a.scan))
    meta_path = os.path.join(trace_dir, "run.meta.json")
    if not os.path.isfile(meta_path):
        _write_atomic(meta_path, json.dumps({
            "skill": SKILL_NAME, "run_id": os.path.basename(os.path.normpath(trace_dir)), "started_at": _now(),
            "executor": ("codex" if str(a.executor_model).lower().startswith("codex") else
                         "claude-code" if exec_fam == "anthropic" else "unknown"),
            "executor_model": a.executor_model, "executor_family": exec_fam,
            "reviewer_family": reviewer_fam, "family_relation": "deterministic" if status == "skipped" else (
                "different" if independence == "cross-family" else "same-or-unknown"),
            "project_dir": os.getcwd()}, indent=2) + "\n")
    trace_rel = _rel(trace_dir, paper_dir).rstrip("/") + "/"
    # suggested allow lines (Tier B rulings only; humans copy them). Only a
    # cross-family ruling may carry cross-family-review provenance; anything else
    # needs a named human to take it over before it can exempt a finding.
    approver = ("cross-family-review:%s" % handle) if independence == "cross-family" else "human:<your-id>"
    sugg = []
    seen_g: Set[str] = set()
    for f in findings:
        if f.get("ruling") in ("false_positive", "necessary") and f.get("group") not in seen_g and f.get("match"):
            seen_g.add(f["group"])
            if "[ANON#" in f["match"] or "[AUTO#" in f["match"] or "[DENY#" in f["match"] or "[REDACTED]" in f["match"]:
                continue
            sugg.append("%s\t%s\t%s\t%s" % (f["check"], _rx_escape(f["match"]), approver,
                                            (f.get("ruling_rationale") or f["ruling"])[:160]))
    stale = stale_other_audits(paper_dir, os.path.basename(a.out_json)) if a.out_json else []
    groups_final = []
    gmap: Dict[str, Dict[str, Any]] = {}
    for f in findings:
        g = gmap.get(f["group"])
        if g is None:
            g = gmap[f["group"]] = {"group": f["group"], "check": f["check"], "family": f["family"], "match": f["match"],
                                    "n": 0, "certainty": f["certainty"], "severity": f["severity"], "pages": [],
                                    "ruling": f.get("ruling")}
            groups_final.append(g)
        g["n"] += 1
        g["severity"] = _sev_max(g["severity"], f["severity"])
        pg = f["location"].get("page")
        if pg and pg not in g["pages"]:
            g["pages"].append(pg)
    artifact: Dict[str, Any] = {
        "audit_skill": SKILL_NAME,
        "verdict": verdict,
        "reason_code": reason,
        "summary": _summary_line(verdict, reason, counts, len(groups_final), reasons),
        "audited_input_hashes": scan.get("input_hashes", {}),
        "trace_path": trace_rel,
    }
    if a.thread_id:
        artifact["thread_id"] = a.thread_id
    else:
        artifact["agent_id"] = a.agent_id or DETERMINISTIC_REVIEWER
    # Only a read-only recheck of the final bytes can say "upload these": an
    # audit or fix-round PASS describes a build that may still change. A
    # confirmed leak is never "advisory only" (reason confirmed_leaks).
    upload_ready = run_mode == "recheck" and (verdict == "PASS" or (verdict, reason) == ("WARN", "advisory_only"))
    undo: List[Dict[str, Any]] = []
    if run_mode == "fix" and work_dir and a.fix_round:
        undo = undo_suspects(findings, applied, a.fix_round, page_texts)
    fix_queue, stop_conditions = build_fix_queue(findings, blocked_keys, undo, units, meta_field_sites(paper_dir),
                                                 late_round=run_mode == "fix" and (a.fix_round or 0) >= 1)
    # fragment items are read the way the draft takes them: one without a clean deletion is for a person
    fix_queue, frag_manual = settle_fragment_items(
        fix_queue, paper_dir, scan, red, {"policy": scan.get("policy") or {},
                                          "anonymous": bool(scan.get("anonymous", True))})
    plan_ctx = {"page_texts": page_texts, "supp_texts": supp_texts, "sources": plan_sources(paper_dir),
                "policy": scan.get("policy") or {}, "anonymous": bool(scan.get("anonymous", True)),
                "units": units, "manual": frag_manual}
    plan = build_fix_plan(findings, fix_queue, blocked_keys, plan_ctx)
    plan_check = fix_plan_check(plan, fix_queue)
    downgraded = downgraded_blockers(findings)
    ec_doc = scan.get("edits_check") or {}
    auto_edits = {k: ec_doc.get(k) for k in ("total", "ok", "rejected") if k in ec_doc}
    if ec_doc:
        auto_edits["items"] = ec_doc.get("items") or []
        auto_edits["files"] = sorted({x.get("file") or ("%s (supplement)" % x.get("member")) for x in auto_edits["items"]
                                      if x.get("file") or x.get("member")})
        # members whose content could not be compared (binary, over the snapshot limit, past the scan budget)
        auto_edits["not_compared"] = list(ec_doc.get("unreadable") or [])[:UNSCANNED_LIST_MAX + 1]
        # the edits apply accepted (and kept): FIX_LOG counts these, the list above counts changed places
        n_applied = sum(1 for _rn, _pth, d in applied for r in d.get("applied") or [] if not r.get("undone"))
        if n_applied:
            auto_edits["applied_edits"] = n_applied
    rounds_info: Dict[str, Any] = {}
    if work_dir and run_mode == "fix" and a.fix_round is not None:
        rounds_info = _record_round(work_dir, paper_dir, a.fix_round, verdict, counts, findings, scan, applied,
                                    page_texts)
    elif work_dir and run_mode == "recheck":
        rd = _load_json(os.path.join(work_dir, ROUNDS_NAME)) or {}
        if rd.get("rounds"):
            rounds_info = {"rounds": rd["rounds"], "best_round": rd.get("best_round"),
                           "best_paper_round": rd.get("best_paper_round"),
                           "best_supp_round": rd.get("best_supp_round")}
    if work_dir:
        _write_memory(work_dir, ledger, memo, run_label, handle, run_mode, findings, fix_queue, stop_conditions,
                      scan, verdict, reasons, a.fix_round)
    artifact.update({
        "executor_model": a.executor_model, "executor_family": exec_fam,
        "reviewer_model": reviewer_model, "reviewer_family": reviewer_fam,
        "review_independence": independence, "acceptance_status": acceptance,
        "reviewer_reasoning": reasoning, "generated_at": _now(),
        "details": {
            "scanner_version": scan.get("tool_version", TOOL_VERSION),
            "run_mode": run_mode, "upload_ready": upload_ready, "recheck_required": run_mode != "recheck",
            "tiers_run": tiers, "lenses_run": lenses_run or ([] if status != "ok" else scan.get("lenses", [])),
            "lenses_enabled": scan.get("lenses", []),
            "anonymous": scan.get("anonymous"), "strict": strict, "policy": scan.get("policy") or {},
            "artifacts": _artifact_rows(scan),
            "supplements": scan.get("inputs", {}).get("supp", []),
            "backends": scan.get("backends", {}), "counts": counts, "groups": groups_final, "findings": findings,
            "checks_run": scan.get("checks_run", []), "checks_skipped": scan.get("checks_skipped", []),
            "exemptions_applied": scan.get("exemptions_applied", []), "page_geometry": scan.get("page_geometry", []),
            "tier_b_status": {"ok": "ok", "skipped": "skipped", "error": "error", "unavailable": "unavailable",
                              "malformed": "malformed"}[status],
            "tier_a_verdict": scan.get("verdict_tier_a"), "review_notes": notes,
            "family_warning": "; ".join(fam_warn) if fam_warn else None,
            "fix_round": a.fix_round, "suggested_allow_lines": sugg, "stale_other_audits": stale,
            "reasons": reasons, "fix_queue": fix_queue, "stop_conditions": stop_conditions,
            "fix_plan": plan, "fix_plan_check": plan_check, "undo": undo, "auto_edits": auto_edits,
            "rounds": rounds_info.get("rounds") or [], "best_round": rounds_info.get("best_round"),
            "best_paper_round": rounds_info.get("best_paper_round"),
            "best_supp_round": rounds_info.get("best_supp_round"),
            "deliver": rounds_info.get("deliver"), "deliver_parts": rounds_info.get("deliver_parts"),
            "contested_edits": contested, "policy_demoted": policy_demoted,
            "pure_leak_units": [{"file": u["file"], "line": u["line"], "unit": u.get("unit"),
                                 "skeleton": u.get("skeleton"), "reason": u.get("reason"),
                                 "exclusion": u.get("exclusion"), "checks": u.get("checks"),
                                 "groups": u.get("groups"), "deleted": red.redact(u.get("deleted") or "")[:300],
                                 "sentence": red.redact(_collapse_ws(u.get("printed") or ""))[:400]}
                                for u in units],
            "narration_raised": narration_raised,
            "downgraded_blockers": downgraded, "inherited_rulings": memo.get("inherited", 0),
            "ruling_changes": memo["ruling_changes"],
            "supp_review": supp_cov, "carried_over": carried_info,
            "blocked": blocked, "notes": scan.get("notes", []),
        },
    })
    if getattr(a, "plan_out", None):
        _write_atomic(a.plan_out, render_fix_plan(artifact))
    return artifact, VERDICT_EXIT[verdict]


def _where_str(f: Dict[str, Any]) -> str:
    loc = f.get("location") or {}
    bits = []
    if loc.get("page"):
        bits.append("p.%s" % loc["page"])
    if loc.get("file"):
        bits.append("%s:%s" % (loc["file"], loc.get("line")))
    if loc.get("member"):
        bits.append(str(loc["member"]) + (":%s" % loc["line"] if loc.get("line") and not loc.get("file") else ""))
    return " ".join(bits) or str(loc.get("artifact") or "")


def _fix_class(f: Dict[str, Any]) -> Optional[str]:
    """The conservative fix class of a finding (FIX_CLASSES), or None: then it
    goes to the fix plan for a person. Only what an edit the `apply` check can
    verify will fix is ever queued."""
    chk, sev = f["check"], f["severity"]
    if f.get("exempted_by") or chk.startswith(_NO_FIX_PREFIXES) or chk in STOP_CHECKS or f.get("plan_only"):
        return None  # (a recall candidate is for a person, whatever its ruling)
    if chk == "FIX-REGRESSION":
        return "undo" if sev != INFO and (f.get("regression") or {}).get("against") == "the previous round" else None
    if chk == "FIX-EDIT":
        return "undo" if sev != INFO else None
    if chk in _META_FIX_CHECKS:
        return "meta"
    if sev == INFO or f.get("layer") == "review" or f.get("ruling_flip"):
        return None
    confirmed = f.get("ruling") == "leak"
    if chk == "XREF-SRC-REF":
        return "xref-ref" if f.get("fix_target") and f["certainty"] == DEFINITE else None
    if chk == "XREF-SRC-CITE":
        return "xref-cite" if f.get("fix_drop") else None
    if chk == "XREF-LOG-RERUN":
        return "rebuild"
    if chk in _FIX_DELETE_DEFINITE:
        return "delete" if f["certainty"] == DEFINITE else None
    if chk in _FIX_DELETE_CONFIRMED:
        # a hardware word that names a measured quantity or sits in a heading is for a person
        return "delete" if confirmed and not f.get("hw_usage") else None
    if chk == "TEXT-MARKER":
        ok = _FIX_MARKER_RE.search(str(f.get("match") or ""))
        return "marker" if ok and (f["certainty"] == DEFINITE or confirmed) else None
    if chk == "TEXT-CODE":
        mt = str(f.get("match") or "")
        esc = re.fullmatch(r"\\[ntr]", mt) or (re.fullmatch(r"\\[ntr][A-Za-z]+", mt)
                                               and f.get("note") == _GLUED_ESC_NOTE)
        return "escape" if f["certainty"] == DEFINITE and esc else None
    if chk in ("SUPP-JUNK", "SUPP-ARIS"):
        return "supp-remove" if (f["certainty"] == DEFINITE or confirmed or f.get("ruling") == "unreviewed") else None
    if chk in ("SUPP-META", "SUPP-GZIP", "SUPP-TAR"):
        return "repack"
    if chk == "SUPP-TEXT":
        if f.get("code_line") or (f.get("subregion") in ("data", "log")):
            return None
        if f["certainty"] == DEFINITE and sev == BLOCK:
            return "supp-delete"
        return "supp-delete" if confirmed and f.get("match") == "environment-variable prefix" else None
    if chk == "SUPP-HW":
        return ("supp-delete" if confirmed and f.get("subregion") != "name" and not f.get("hw_usage")
                and not f.get("code_line") else None)
    return None


def build_fix_queue(findings: List[Dict[str, Any]], blocked: Optional[Dict[str, str]] = None,
                    undo: Sequence[Dict[str, Any]] = (), units: Sequence[Dict[str, Any]] = (),
                    meta_fields: Sequence[Dict[str, Any]] = (), late_round: bool = False
                    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """(fix_queue, stop_conditions) — what a `— fix` round may change, and what
    ends the loop at once. Script-decided: the executor neither adds to nor
    removes from it, and `apply` refuses an edit for anything else. Every item
    carries its fix class (and what the class needs: the label to point at,
    the members to leave out, the preamble lines and the metadata fields to
    empty in place, the edits to undo, the exact deletion of a pure-leak
    sentence or clause — `units` from pure_leak_units — which replaces the
    fragment items it holds)."""
    blocked = blocked or {}
    queue: Dict[str, Dict[str, Any]] = {}
    stops: Dict[str, Dict[str, Any]] = {}
    meta_checks: Set[str] = set()
    meta_live: Set[str] = set()   # PDF Info fields a non-INFO META-INFO finding names (pdfauthor, pdftitle, …)
    meta_tz_doc = False
    for f in findings:
        if f["check"] in STOP_CHECKS and f["severity"] in (WARN, BLOCK) and not f.get("exempted_by"):
            target, cls = stops, "stop"
        else:
            cls = _fix_class(f)
            if cls is None:
                continue
            key = stable_key(f["check"], f["match"], f.get("region"), f.get("subregion"))
            if cls != "undo" and key in blocked:
                continue
            if cls == "meta":
                meta_checks.add(f["check"])
                meta_tz_doc = meta_tz_doc or (f["check"] == "META-TZ" and not str(f["match"]).startswith(
                    ("embedded", "XMP")))
                if f["check"] == "META-INFO" and f["severity"] != INFO:
                    meta_live.add("pdf" + str(f["match"]).split("=", 1)[0].strip().lower())
                continue
            target = queue
        gid = f["group"] if cls not in ("repack",) else "REPACK"
        g = target.get(gid)
        if g is None:
            g = target[gid] = {"group": gid, "check": f["check"], "fix_class": cls, "severity": f["severity"],
                               "match": f["match"], "n": 0, "where": [],
                               "key": stable_key(f["check"], f["match"], f.get("region"), f.get("subregion"))}
            for k in ("fix_target", "rewrite", "carried_from", "edit_id"):
                if f.get(k):
                    g[k] = f[k]
            if cls == "xref-cite":
                g["drop_key"] = f["match"]
        g["n"] += 1
        g["severity"] = _sev_max(g["severity"], f["severity"])
        w = _where_str(f)
        if w and w not in g["where"] and len(g["where"]) < 6:
            g["where"].append(w)
        loc = f.get("location") or {}
        mem = loc.get("member")
        if cls == "supp-remove" and mem:
            g.setdefault("members", [])
            if mem not in g["members"] and len(g["members"]) < 500:
                g["members"].append(mem)
        if cls == "xref-ref":
            # every place the key is referenced: the repair changes each of them
            gl = g.setdefault("lines", [])
            for pl in f.get("ref_places") or []:
                if pl not in gl and len(gl) < 50:
                    gl.append(pl)
        if cls in ("delete", "supp-delete", "marker"):
            # what a deletion must remove: the text each occurrence matched (never a
            # description such as "environment-variable prefix"), on every line it is on
            ga = g.setdefault("anchors", [])
            for x in (f.get("matched") or [f.get("match")]):
                if x and x not in ga and len(ga) < 50:
                    ga.append(x)
            gl = g.setdefault("lines", [])
            place = mem or loc.get("file")
            for ln in (f.get("lines") or ([loc.get("line")] if loc.get("line") else [])):
                pl = "%s:%s" % (place, ln) if place else "line %s" % ln
                if pl not in gl and len(gl) < 200:
                    gl.append(pl)
    # a metadata field the sources set with a value — a listed name in \hypersetup{pdfauthor={…}} included
    pdf_fields = [f for f in findings if f.get("pdf_field") and f["severity"] != INFO and not f.get("exempted_by")]
    if meta_checks or pdf_fields:
        lines = []
        if "META-INFO" in meta_checks:
            lines.append(META_PREAMBLE_LINES[0])
        if meta_tz_doc:
            lines += [META_PREAMBLE_LINES[1], META_PREAMBLE_LINES[3]]
        if "META-PTEX" in meta_checks or ("META-TZ" in meta_checks and not meta_tz_doc):
            lines.append(META_PREAMBLE_LINES[2])
        item = {"group": "META", "check": "+".join(sorted(meta_checks | {f["check"] for f in pdf_fields})),
                "fix_class": "meta", "severity": WARN, "match": "PDF metadata",
                "n": len(meta_checks) + len(pdf_fields), "where": ["preamble"],
                "key": stable_key("META", "preamble"), "lines": lines}
        # where the sources already set metadata fields with a value, they are emptied in place: an empty
        # override after them would keep the value in the sources (an arXiv or camera-ready source shows it)
        # (file, line, and field names only: the values stay out of the report; `edits --from-queue` reads them)
        inplace = [dict({"file": x["file"], "line": x["line"], "fields": list(x["fields"])},
                        **({"added": list(x["added"])} if x.get("added") else {})) for x in meta_fields
                   if x.get("fields")]
        if inplace:
            item["inplace"] = inplace
            done = {k for x in inplace for k in x["fields"] + x.get("added", [])}
            if lines and lines[0] == META_PREAMBLE_LINES[0] and meta_live <= done:
                # every field that matters is emptied where it is set (the first \hypersetup takes the
                # others, empty): no override line after it
                item["lines"] = lines[1:]
        live_meta = any(f["severity"] != INFO and not f.get("exempted_by") and
                        (f["check"] in _META_FIX_CHECKS or f.get("pdf_field")) for f in findings)
        if late_round and not live_meta and not inplace:
            # only INFO metadata is left after the first round emptied the fields in place: the loop stops
            # here (the plan lists it), never another round for a second override line
            pass
        else:
            queue["META"] = item
    # pure-leak sentences and clauses: one item per place, with the exact source edit
    for u in units:
        if not u.get("unit"):
            continue
        key = stable_key("SENTENCE", "%s:%s" % (u["file"], _norm_key(u["printed"])[:300]))
        if key in blocked:
            continue
        gid = "S-%03d" % (sum(1 for g in queue.values() if g["fix_class"] == "delete-sentence") + 1)
        sev = INFO
        for f in findings:
            if f.get("group") in u["groups"] and f["severity"] != INFO:
                sev = _sev_max(sev, f["severity"])
        queue[gid] = {"group": gid, "check": "+".join(u["checks"]), "fix_class": "delete-sentence",
                      "severity": sev if sev != INFO else WARN, "match": _collapse_ws(u["printed"])[:200], "n": 1,
                      "where": ["%s:%s" % (u["file"], u["line"])], "key": key, "file": u["file"], "line": u["line"],
                      "unit": u["unit"], "before": u["before"], "after": u["after"], "reason": u["reason"],
                      "deleted": u.get("deleted") or "", "region": list(u.get("region") or ["body", None]),
                      "groups": list(u["groups"]), "anchors": list(dict.fromkeys(x["match"] for x in u["leak"]))[:50],
                      "leaks": [[x["check"], x["key"]] for x in u["leak"]],
                      "lines": ["%s:%s" % (u["file"], ln) for ln in range(u["line"], u.get("last_line", u["line"]) + 1)]}
    sentence_units = [u for u in units if u.get("unit")
                      and any(g.get("fix_class") == "delete-sentence" and g.get("before") == u.get("before")
                              for g in queue.values())]
    if sentence_units:
        # a group every live occurrence of which a queued sentence item deletes is taken by it: its fragment
        # item is superseded, and the plan lists the group with the sentence item (automatic)
        live: Dict[str, List[Dict[str, Any]]] = {}
        for f in findings:
            if f["severity"] != INFO and not f.get("exempted_by") and f.get("group"):
                live.setdefault(f["group"], []).append(f)
        fully = {gid for gid, occ in live.items() if all(_unit_covering(sentence_units, f) is not None for f in occ)}
        for gid in list(queue):
            if gid in fully and queue[gid]["fix_class"] == "delete":
                del queue[gid]
        for g in [g for g in queue.values() if g["fix_class"] == "delete-sentence"]:
            g["covers"] = sorted(set(g["groups"]) & fully)
    # text in a member the queue leaves out of the package (junk, an AppleDouble file) is never edited: the
    # member goes, and a deletion inside it would only edit bytes nobody receives
    gone = {str(m) for g in queue.values() if g["fix_class"] == "supp-remove" for m in g.get("members") or []}
    for gid in list(queue):
        g = queue[gid]
        if g["fix_class"] != "supp-delete":
            continue
        keep = [w for w in g.get("lines") or [] if str(w).rsplit(":", 1)[0] not in gone
                and not re.search(r"(?:^|/)(?:__MACOSX/|\._)", str(w).rsplit(":", 1)[0])]
        if len(keep) != len(g.get("lines") or []):
            if keep:
                g["lines"] = keep
            else:
                del queue[gid]
    for g in queue.values():
        if g["fix_class"] != "undo":
            continue
        if g["check"] == "FIX-EDIT":
            g["undo_ids"] = [g.get("edit_id")] if g.get("edit_id") else []
        else:  # a regression: the applied edits it points to (refused changes are their own items)
            g["undo_ids"] = [u["id"] for u in undo if not str(u["id"]).startswith("E-")]
    return (sorted(queue.values(), key=lambda g: (_FIX_ORDER.get(g["fix_class"], 99), g["group"])),
            sorted(stops.values(), key=lambda g: g["group"]))


def settle_fragment_items(queue: List[Dict[str, Any]], paper_dir: str, scan: Dict[str, Any], red: Redactor,
                          det: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
    """The fragment items (`delete`, `supp-delete`) read the way `edits
    --from-queue` drafts them: an item none of whose occurrences has a clean
    draft leaves the queue — the plan names why and shows the sentence as the
    deletion would leave it, for a person; an item with some clean drafts keeps
    them and lists its other occurrences under `manual` (redacted). Returns
    (queue, manual by group)."""
    if not any(g.get("fix_class") in ("delete", "supp-delete") for g in queue):
        return queue, {}
    supp = next((s.get("path") for s in (scan.get("inputs") or {}).get("supp") or [] if s.get("path")), None)
    archive = (supp if os.path.isabs(supp) else os.path.normpath(os.path.join(paper_dir, supp))) if supp else None
    cache: Dict[str, Optional[str]] = {}

    def read_paper(rel: str) -> Optional[str]:
        if "p:" + rel not in cache:
            full = _within(paper_dir, rel)
            cache["p:" + rel] = None
            if full and os.path.isfile(full):
                with open(full, "rb") as fh:
                    t_, enc = _decode_text(fh.read())
                cache["p:" + rel] = t_ if enc in ("utf-8", "utf-8-sig", "gb18030") else None
        return cache["p:" + rel]

    def read_member(member: str) -> Optional[str]:
        if "s:" + member not in cache:
            data = member_bytes(archive, member) if archive and os.path.exists(archive) else None
            cache["s:" + member] = _decode_text(data)[0] if data is not None else None
        return cache["s:" + member]
    try:
        ec = edit_check_for(_paper_sources(paper_dir), red, None)
        frag = fragment_drafts(queue, read_paper, read_member, ec, det, paper_dir)
    except Exception:  # noqa: BLE001 — the queue stands as built; the draft step lists what it cannot draft
        return queue, {}
    drafted: Set[str] = set()
    for _p, _k, ed in frag["edits"]:
        drafted.update([ed["group"]] + list(ed.get("covers") or []))
    manual: Dict[str, List[Dict[str, Any]]] = {}
    for place, _kind, mn in frag["manual"]:
        entry = {"where": red.redact("%s:%s" % (place, mn.get("line"))), "why": mn["why"],
                 "usage": mn.get("usage"),
                 "sentence": red.redact(_collapse_ws(mn.get("sentence") or ""))[:_PLAN_ORIGINAL_MAX],
                 "after": (red.redact(_collapse_ws(mn["after"]))[:_PLAN_ORIGINAL_MAX]
                           if mn.get("after") is not None else None)}
        for gid in mn["groups"]:
            if len(manual.setdefault(gid, [])) < 20:
                manual[gid].append(entry)
    out = []
    for g in queue:
        gid = g["group"]
        if g.get("fix_class") in ("delete", "supp-delete") and gid in manual:
            if gid not in drafted:
                continue  # no clean draft anywhere: for a person, with the sentence the deletion would leave
            g["manual"] = manual[gid]
        out.append(g)
    return out, manual


_PLAN_CATEGORY = (
    ("XREF-SRC-REF", "unresolved reference"), ("XREF-SRC-CITE", "unresolved citation"), ("XREF-", "references"),
    ("ENG-FW", "framework or tooling name"), ("ENG-HW", "hardware"), ("ENG-QTY", "compute accounting"),
    ("ENG-OPS", "engineering wording"), ("ENG-HASH", "hash or run id"), ("ENG-DENY", "internal code name"),
    ("ENG-FILENAME", "file name in the prose"), ("ENG-PRECISION", "precision or loading detail"),
    ("ENG-", "engineering detail"), ("PROC-TIME", "date or batch name"), ("PROC-DATESEED", "date-shaped seed"),
    ("PROC-REVIEW", "review narration"), ("PROC-REVISION", "revision or run narration"),
    ("PROC-REGLABEL", "registration label"), ("PROC-PENDING", "unfinished work"), ("PROC-AITOOL", "AI-tool use"),
    ("ANON-CODENAME", "internal code name"), ("ANON-", "anonymity"), ("META-FIGURE", "figure metadata"),
    ("META-", "PDF metadata"), ("TEXT-NOSPACE", "text layer spacing"), ("TEXT-", "text layer"),
    ("PAGE-", "pages"), ("TPL-", "template"), ("ENDM-", "end-matter statements"),
    ("SUPP-NAME", "supplement file name"), ("SUPP-PROCFILE", "process file"), ("SUPP-PATH", "supplement path"),
    ("SUPP-HW", "supplement hardware note"), ("SUPP-RUNTIME", "run time written by code"),
    ("SUPP-LANG", "supplement language"), ("SUPP-", "supplement"), ("LENS-STATEMENTS", "statements"),
    ("LENS-", "reviewer finding"), ("NUM-", "number changed"), ("FIX-", "fix-loop damage"), ("CONFIG-", "configuration"),
    ("LOG-", "build log"))
_PLAN_ADVICE = {
    "date or batch name": "If the date or batch name orders events, write a relative expression (after, before, the "
                          "later runs); otherwise delete it. Keep a calendar date only next to a public registration "
                          "id.",
    "revision or run narration": "Delete the narration; a sentence that states a result, rule, decision, or "
                                 "commitment keeps everything but the leaking fragment. Add no fact.",
    "review narration": "Delete the reference to the review process; keep what the sentence states.",
    "registration label": "With registration_labels: flag, keep the timing fact the label carries and drop the "
                          "label; otherwise keep it.",
    "unfinished work": "Finish the work, or delete the row or sentence that announces it; never reword the status "
                       "away.",
    "reviewer finding": "Delete only the leaking fragment; if the sentence carries a conclusion, rule, or commitment, "
                        "keep the rest of it. Add no fact.",
    "statements": "Reword the statement to the venue template; never cut a sentence of a required statement without "
                  "the authors' OK.",
    "internal code name": "Replace the name in the paper and in the supplement's notes and file names — in code "
                          "literals and record keys only together with the outputs they produce — or rule it a false "
                          "positive.",
}


def _vet_suggestion(rewrite: str, original: str) -> Dict[str, Any]:
    """Whether a suggested wording only deletes words of the passage it
    rewrites, or adds some (listed: check they state no new fact)."""
    rw, ow = _wordlist(rewrite), _wordlist(original)
    if not rw:
        return {"delete_only": True, "added_words": []}
    if _is_subseq(rw, ow):
        return {"delete_only": True, "added_words": []}
    added = _added_words(ow, rw)
    if not added:  # the same words in another order
        return {"delete_only": False, "added_words": [], "reordered": True}
    return {"delete_only": False, "added_words": added[:12]}


# ─── The fix plan's deterministic filter ─────────────────────────────────────
# Finalize reads every suggested wording against the whole sentence it would
# replace (from the audited text, never a cut excerpt) and marks it not usable —
# a hint, never offered as the fix — when it changes a number (another digit
# string, or the same value in hex or with digit groups), drops a registration
# label or an ordering the sentence states, still matches the check that found
# the passage (or adds wording a check flags), or leaves a skeleton sentence.
# Items at one place of the text (one sentence, one reference key, the page
# count) become one item; differing usable wordings are listed as a conflict.

_ALT_NUMBER_RE = re.compile(r"\b0[xX][0-9a-fA-F]+\b|(?<![\w.])\d{1,3}(?:_\d{3})+(?![\w.])", _A)
_TEX_HEADING_RE = re.compile(r"\s*\\(?:(?:sub){0,2}section|paragraph)\*?\s*\{")
_LINE_MARK_RE = re.compile(r"(?m)(?:^|(?<=\s))L\d{1,6}:[ \t]?")  # the 'L12: ' marks of a code member's notes
_GENERIC_DELETE_RE = re.compile(r"^\s*(?:Delete|Remove)\b", re.I)
_XREF_KEYED = ("XREF-SRC-REF", "XREF-SRC-CITE", "XREF-LOG-REF", "XREF-LOG-CITE", "XREF-BLG", "XREF-PDF-KEY")
_XREF_REF_KEYED = ("XREF-SRC-REF", "XREF-LOG-REF")
_TEX_SEP = r"(?:[^\w\\]|\\[A-Za-z@]+\*?|\\[^A-Za-z@])*?"
_PLAN_ORIGINAL_MAX = 600


def _find_norm(text: str, needle: str) -> Tuple[int, int]:
    """(start, end) of `needle` in `text`, whatever the whitespace between its
    words, ignoring case; (-1, -1) when absent."""
    toks = (needle or "").split()
    if not toks or not text:
        return -1, -1
    m = re.search(r"\s+".join(re.escape(t) for t in toks), text, re.I)
    return (m.start(), m.end()) if m else (-1, -1)


def _excerpt_core(ex: str) -> str:
    """An excerpt without its ellipses and the words they cut."""
    toks = (ex or "").split()
    if ex.startswith("…") and toks:
        toks = toks[1:]
    if ex.endswith("…") and toks:
        toks = toks[:-1]
    return " ".join(toks)


_SENT_END_RE = re.compile(r"[.!?。！？][\"'’”)\]]*\s*$")
_NOTE_END_RE = re.compile(r"[.!?:;。！？：；][\"'’”)\]]*\s*$")   # a note line ending a sentence or opening a list
_CONTINUES_RE = re.compile(r"\s*[a-z0-9(]")                     # text that goes on with a sentence begun before
_PAGE_NO_RE = re.compile(r"^(?:\d{1,4}|[ivxlcdm]{1,7}|[IVXLCDM]{1,7})$")
_NOTE_LEAD_RE = re.compile(r"^\s*(#+|//|%+|;+|--)?\s?")
_ITEM_START_RE = re.compile(r"(?:[-*+•]\s|#|\d{1,3}[.)]\s)")


def _page_paragraphs(text: str) -> List[str]:
    return [p.strip() for p in (text or "").split("\n\n") if p.strip()]


def _body_paragraphs(pages: Dict[int, str], pg: int) -> List[str]:
    """The paragraphs of page `pg` without its running header or footer (a
    paragraph repeated at the same edge of a neighbouring page) or its page
    number."""
    paras = _page_paragraphs(pages.get(pg) or "")

    def edge(k: int, i: int) -> Optional[str]:
        ps = _page_paragraphs(pages.get(k) or "")
        return _norm_quote(ps[i]) if ps else None
    heads = {edge(pg - 1, 0), edge(pg + 1, 0)} - {None}
    feet = {edge(pg - 1, -1), edge(pg + 1, -1)} - {None}
    while paras and (_PAGE_NO_RE.match(paras[0]) or _norm_quote(paras[0]) in heads):
        paras = paras[1:]
    while paras and (_PAGE_NO_RE.match(paras[-1]) or _norm_quote(paras[-1]) in feet):
        paras = paras[:-1]
    return paras


def _across_pages(sentence: str, para: str, s: int, e: int, pages: Dict[int, str], pg: int) -> str:
    """A sentence a page break cuts in two, made whole: the tail of the previous
    page's last paragraph when that tail has no sentence end and this page's
    first paragraph goes on in lower case; the head of the next page's first
    paragraph when the sentence runs to the end of the page without an end."""
    body = _body_paragraphs(pages, pg)
    if not body:
        return sentence
    here, out = _norm_quote(para), sentence.strip()
    if not para[:s].strip() and here == _norm_quote(body[0]) and _CONTINUES_RE.match(sentence):
        prev = _body_paragraphs(pages, pg - 1)
        if prev and not _SENT_END_RE.search(prev[-1]):
            k = 0
            for m in _SENT_BOUND_RE.finditer(prev[-1]):
                k = m.end()
            out = prev[-1][k:] + " " + out
    if not para[e:].strip() and here == _norm_quote(body[-1]) and not _SENT_END_RE.search(sentence):
        nxt = _body_paragraphs(pages, pg + 1)
        if nxt and _CONTINUES_RE.match(nxt[0]):
            m = _SENT_BOUND_RE.search(nxt[0])
            out = out + " " + (nxt[0][:m.start()] if m else nxt[0])
    return out


def _note_parts(line: str) -> Tuple[str, str]:
    """(comment mark, text) of a line of a supplementary note."""
    m = _NOTE_LEAD_RE.match(line)
    return (m.group(1) or ""), line[m.end():].strip()


def _across_note_lines(t: str, lo: int, hi: int, s: int, e: int) -> str:
    """The sentence of a supplementary note that runs over more lines of one
    comment, docstring, or paragraph: a line goes on with the one before when
    both carry the same comment mark, the one before has no sentence end, and
    the line starts in lower case (never a list item or a heading); three
    lines each way at most, the comment marks of a joined sentence dropped."""
    line = t[lo:hi]
    own = line[s:e]
    mark = _note_parts(line)[0]
    before: List[str] = []
    after: List[str] = []
    if not line[e:].strip() and not _NOTE_END_RE.search(own):
        pos = hi
        for _ in range(3):
            if pos >= len(t):
                break
            nhi = t.find("\n", pos + 1)
            nhi = len(t) if nhi < 0 else nhi
            nmark, nbody = _note_parts(t[pos + 1:nhi])
            if nmark != mark or not nbody or not _CONTINUES_RE.match(nbody) or _ITEM_START_RE.match(nbody):
                break
            m = _SENT_BOUND_RE.search(nbody)
            after.append(nbody[:m.start()] if m else nbody)
            if m or _NOTE_END_RE.search(nbody):
                break
            pos = nhi
    head = _note_parts(line)[1]
    if not _note_parts(line[:s])[1] and head and _CONTINUES_RE.match(head) and not _ITEM_START_RE.match(head):
        plo = lo
        for _ in range(3):
            if plo <= 0:
                break
            pstart = t.rfind("\n", 0, plo - 1) + 1
            pmark, pbody = _note_parts(t[pstart:plo - 1])
            if pmark != mark or not pbody or _NOTE_END_RE.search(pbody) or _ITEM_START_RE.match(pbody):
                break
            k = 0
            for m in _SENT_BOUND_RE.finditer(pbody):
                k = m.end()
            before.insert(0, pbody[k:])
            if k or not _CONTINUES_RE.match(pbody):
                break
            plo = pstart
    if not (before or after):
        return own
    return " ".join(before + [_note_parts(own)[1]] + after)


def _sentence_of(f: Dict[str, Any], ctxd: Dict[str, Any]) -> Tuple[str, str]:
    """(passage, sentence): the finding's own text (a reviewer's quote, or the
    rule's match) and the whole sentence of the audited text around it — the
    PDF page text (a sentence a page break cuts is joined), or the
    supplementary note the reviewer read (a sentence wrapped over several
    comment lines is joined). Falls back to the excerpt when the text cannot
    be found."""
    loc = f.get("location") or {}
    passage = str(f.get("match") or "")
    texts: List[Tuple[str, str, Optional[Dict[int, str]], int]] = []
    if loc.get("member"):
        t = (ctxd.get("supp_texts") or {}).get(loc["member"])
        if t:
            texts.append(("supp", _LINE_MARK_RE.sub("", t), None, 0))
    if loc.get("page"):
        for art, pages in (ctxd.get("page_texts") or {}).items():
            if loc.get("artifact") in (None, art):
                with contextlib.suppress(ValueError, TypeError):
                    pg = int(loc["page"])
                    t = pages.get(pg)
                    if t:
                        texts.append(("pdf", t, pages, pg))
    core = _excerpt_core(f.get("excerpt") or "")
    for kind, t, pages, pg in texts:
        a, b = -1, -1
        if len(core) >= 12:
            i, j = _find_norm(t, core)
            if i >= 0:
                k, l_ = _find_norm(t[i:j], passage) if passage else (-1, -1)
                a, b = (i + k, i + l_) if k >= 0 else (i, j)
        if a < 0 and len(passage) >= 4:
            a, b = _find_norm(t, passage)
        if a < 0:
            continue
        if kind == "supp":
            lo = t.rfind("\n", 0, a) + 1
            hi = t.find("\n", b)
        else:  # the paragraph (a segment of the page text) holds the sentence
            r_ = t.rfind("\n\n", 0, a)
            lo = r_ + 2 if r_ >= 0 else 0
            hi = t.find("\n\n", b)
        hi = len(t) if hi < 0 else hi
        s, e = _sentence_bounds(t[lo:hi], a - lo, b - lo)
        if kind == "supp":
            sentence = _across_note_lines(t, lo, hi, s, e)
        else:
            sentence = _across_pages(t[lo + s:lo + e], t[lo:hi], s, e, pages or {}, pg)
        return _collapse_ws(t[a:b]), _collapse_ws(sentence)
    return passage, _collapse_ws(core or passage)


def _replace_norm(sentence: str, passage: str, rewrite: str) -> Optional[str]:
    i, j = _find_norm(sentence, passage)
    if i < 0:
        return None
    return _collapse_ws(sentence[:i] + rewrite + sentence[j:])


# a suggestion written as an instruction ("Replace 'A' with 'B'", "delete 'A'"):
# the wording it proposes is B, put in place of A, never the instruction itself
_Q = r"[\"“”‘’'`]"
# an instruction may open with a phrase that names where it applies ("Throughout these occurrences, replace …")
_INSTR_START_RE = re.compile(r"^\s*(?:[^:;\n\"“”‘’'`]{0,160}?,\s*)?(?:replace|change|substitute|reword|rewrite|"
                             r"delete|remove|drop|cut|omit|strike|use|write|say)\b", re.I)
_INSTR_FILL = r"(?:[A-Za-z-]+\s+){0,3}?"  # "replace only 'A'", "delete the words 'A'", "replace every occurrence of 'A'"
# where a replacement applies, between the quoted text and its replacement ("'A' in this group with 'B'")
_INSTR_SCOPE = (r"(?:\s+(?:in|throughout|across|within|everywhere\s+in)\s+(?:this|the|that|each|every|all|these|those)"
                r"(?:\s+[\w-]+){1,3})?")
_INSTR_PAIR_RE = re.compile(r"\b(?:replace|change|substitute|reword|rewrite)\s+" + _INSTR_FILL + _Q
                            + r"(?P<a>[^\"“”‘’`]{1,400}?)" + _Q + _INSTR_SCOPE + r"\s+(?:with|to|by|into)\s+" + _Q
                            + r"(?P<b>[^\"“”‘’`]{0,400}?)" + _Q, re.I)
# the further pairs of one replacement instruction ("…, 'C' with 'D', and 'E' with 'F'")
_INSTR_MORE_RE = re.compile(r"(?:[,;]\s*(?:and\s+)?|\band\s+)" + _Q + r"(?P<a>[^\"“”‘’`]{1,400}?)" + _Q + _INSTR_SCOPE
                            + r"\s+(?:with|to|by|into)\s+" + _Q + r"(?P<b>[^\"“”‘’`]{0,400}?)" + _Q, re.I)
_INSTR_DEL_RE = re.compile(r"\b(?:delete|remove|drop)\s+" + _INSTR_FILL + _Q + r"(?P<a>[^\"“”‘’`]{1,400}?)" + _Q, re.I)
# an instruction to delete a whole sentence it quotes, or the one that begins with what it quotes
_INSTR_SENT_DEL_RE = re.compile(r"^\s*(?:[^:;\n\"“”‘’'`]{0,160}?,\s*)?(?:delete|remove|drop|cut|omit|strike)\s+"
                                r"(?:only\s+|just\s+)?(?:the\s+|this\s+)?(?:whole\s+|entire\s+|full\s+)?"
                                r"(?:sentence|line)\s*(?:that\s+(?:begins|starts|reads)|beginning|starting|reading)?"
                                r"\s*(?:with\s+)?:?\s*" + _Q + r"(?P<a>[^\"“”‘’`]{4,600}?)" + _Q, re.I)
# "Use 'B' for 'A' and 'D' for 'C'": the new wording comes first
_INSTR_USE_START_RE = re.compile(r"^\s*(?:(?:in|for|at)\b[^:;\n]{0,160}?,\s*)?(?:use|write|say)\s+" + _Q, re.I)
_INSTR_FOR_RE = re.compile(_Q + r"(?P<b>[^\"“”‘’`]{0,400}?)" + _Q + r"\s+(?:for|instead\s+of|in\s+place\s+of|"
                           r"rather\s+than)\s+" + _Q + r"(?P<a>[^\"“”‘’`]{1,400}?)" + _Q, re.I)


def _instruction_pairs(rewrite: str) -> List[Tuple[str, str]]:
    """(quoted text, its replacement) for every replacement or deletion an
    instruction names; empty for a plain wording."""
    if not _INSTR_START_RE.match(rewrite or ""):
        return []
    pairs = [(m.group("a"), m.group("b")) for m in _INSTR_PAIR_RE.finditer(rewrite)]
    if pairs:
        pairs += [(m.group("a"), m.group("b")) for m in _INSTR_MORE_RE.finditer(rewrite)
                  if (m.group("a"), m.group("b")) not in pairs]
    pairs += [(m.group("a"), "") for m in _INSTR_DEL_RE.finditer(rewrite)]
    if _INSTR_USE_START_RE.match(rewrite):
        pairs += [(m.group("a"), m.group("b")) for m in _INSTR_FOR_RE.finditer(rewrite)]
    return pairs


def _apply_instruction(sentence: str, rewrite: str) -> Optional[Tuple[str, str]]:
    """(the sentence with the instruction's replacements made, the words it
    puts in) when `rewrite` instructs replacements or deletions of quoted text
    the sentence holds; None for a plain wording."""
    pairs = _instruction_pairs(rewrite)
    if not pairs:
        return None
    out, put, hit = sentence, [], False
    for a, b in pairs:
        toks = a.split()
        if not toks:
            continue
        rx = re.compile(r"\s+".join(re.escape(x) for x in toks), re.I)
        pos, n = 0, 0
        while n < 10:  # every occurrence of the quoted text, never one inside the words put in
            m = rx.search(out, pos)
            if not m:
                break
            out, pos, n = out[:m.start()] + b + out[m.end():], m.start() + len(b), n + 1
        if n:
            hit = True
            put.append(b)
    return (_tidy_text(_collapse_ws(out)), " ".join(put)) if hit else None


def _rewrites_passage(sentence: str, i: int, j: int, rw: str) -> bool:
    """A wording that rewrites the quoted passage sentence[i:j], not its whole
    sentence: about as long as the passage, it starts or ends as the passage
    does (the same first or last word, or the same bracket), and it repeats no
    run of two words of the sentence outside the passage."""
    import difflib
    pw, ww = _wordlist(sentence[i:j]), _wordlist(rw)
    if not pw or not ww or len(ww) > len(pw) + 3:
        return False
    p, r = sentence[i:j].strip(), rw.strip()
    if not (pw[0] == ww[0] or pw[-1] == ww[-1] or (p[:1] in "([{\"'“‘" and p[:1] == r[:1])
            or (p[-1:] in ")]}\"'”’" and p[-1:] == r[-1:])):
        return False
    toks = [(m.group(0).casefold(), m.start()) for m in _WORDS_RE.finditer(sentence)]
    inside = {k for k, (_w, st) in enumerate(toks) if i <= st < j}
    sm = difflib.SequenceMatcher(None, [w for w, _s in toks], ww, autojunk=False)
    return not any(len([k for k in range(b.a, b.a + b.size) if k not in inside]) >= 2
                   for b in sm.get_matching_blocks())


def _result_of(sentence: str, passage: str, rewrite: str) -> str:
    """The sentence as the suggestion would leave it. A wording that rewrites
    the quoted passage (about its length, starting or ending like it) replaces
    the passage; a wording that starts and ends like a sentence replaces the
    whole sentence; otherwise it replaces the stretch from the first to the
    last sentence word it keeps (the passage included), so a clause-level
    rewrite is read inside its sentence."""
    import difflib
    rw = _collapse_ws(rewrite)
    if not sentence:
        return rw
    pi, pj = _find_norm(sentence, passage) if passage else (-1, -1)
    part = pi >= 0 and bool(sentence[:pi].strip() or sentence[pj:].strip(" .;:!?"))  # the passage is not all of it
    if part and _rewrites_passage(sentence, pi, pj, rw):
        return _tidy_text(sentence[:pi] + rw + sentence[pj:])
    full_start = bool(re.match(r"[A-Z\"'(\[]", rw)) or _wordlist(rw)[:1] == _wordlist(sentence)[:1]
    full_end = bool(re.search(r"[.!?][\"')\]]*$", rw))
    if full_start and full_end:
        return rw
    toks = [(m.group(0).casefold(), m.start(), m.end()) for m in re.finditer(r"\w+", sentence)]
    sm = difflib.SequenceMatcher(None, [x[0] for x in toks], _wordlist(rw), autojunk=False)
    blocks = [b for b in sm.get_matching_blocks()  # (a lone common word counts only where the wording starts)
              if b.size >= 2 or (b.size == 1 and (toks[b.a][0] not in _SKELETON_GENERIC or b.b == 0))]
    starts = [toks[b.a][1] for b in blocks]
    ends = [toks[b.a + b.size - 1][2] for b in blocks]
    i, j = _find_norm(sentence, passage)
    if i >= 0:
        starts.append(i)
        ends.append(j)
    if not starts:
        return rw
    a = 0 if full_start else min(starts)
    b = len(sentence) if full_end else max(ends)
    return _tidy_text(sentence[:a] + rw + sentence[b:])


def plan_sources(paper_dir: str) -> List[Dict[str, Any]]:
    """The non-verbatim source lines of every main .tex ({file, line, text}),
    so a plan item shows where it is in the sources and is worded there."""
    out: List[Dict[str, Any]] = []
    try:
        mains = discover_inputs(paper_dir, [], [], False)["mains"]
    except Exception:  # noqa: BLE001 — the plan works without sources
        return out
    for main in mains:
        with contextlib.suppress(Exception):
            for ln in expand_tex(main, paper_dir)["lines"]:
                if not ln["verbatim"] and ln["text"].strip():
                    out.append({"file": ln["file"], "line": ln["line"], "text": ln["text"]})
    return out


def _flex_re(words: Sequence[str]) -> Optional[Any]:
    """A run of words as it may be spelled in LaTeX: anything but letters and
    digits between them (spaces, ~, braces, $, commands such as \\times)."""
    if not words:
        return None
    return re.compile(_TEX_SEP.join(r"(?<![A-Za-z0-9])%s(?![A-Za-z0-9])" % re.escape(w) for w in words), re.I)


def _source_of(sentence: str, f: Dict[str, Any], sources: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """{file, line, text}: the source spelling of a PDF sentence, found by runs
    of its words (near the finding's own file:line when it has one)."""
    words = re.findall(r"\w+", unicodedata.normalize("NFKC", sentence or ""))
    if len(words) < 3 or not sources:
        return None
    loc = f.get("location") or {}
    pool = list(sources)
    if loc.get("file") and loc.get("line"):
        near = [s for s in sources if s["file"] == loc["file"] and abs(int(s["line"]) - int(loc["line"])) <= 3]
        pool = near or pool
    anchor = None
    low = [s["text"].casefold() for s in pool]
    tries = [words[i:i + 3] for i in range(0, max(1, len(words) - 2))][:6]
    tries += [words[i:i + 3] for i in range(max(0, len(words) - 3), max(0, len(words) - 9), -1)]
    for run in tries:
        rx = _flex_re(run)
        key = max(run, key=len).casefold()  # a cheap filter before the TeX-tolerant pattern
        hits = [k for k in range(len(pool)) if key in low[k] and rx and rx.search(pool[k]["text"])]
        if len(hits) == 1:
            anchor = hits[0]
            break
    if anchor is None:
        return None
    # the paragraph around it: consecutive non-empty lines of the same file
    lo = hi = anchor
    while lo > 0 and pool[lo - 1]["file"] == pool[anchor]["file"] and \
            int(pool[lo - 1]["line"]) == int(pool[lo]["line"]) - 1 and anchor - lo < 8:
        lo -= 1
    while hi + 1 < len(pool) and pool[hi + 1]["file"] == pool[anchor]["file"] and \
            int(pool[hi + 1]["line"]) == int(pool[hi]["line"]) + 1 and hi - anchor < 8:
        hi += 1
    para = "\n".join(pool[k]["text"] for k in range(lo, hi + 1))
    first, last = _flex_re(words[:3]), _flex_re(words[-3:])
    m1 = first.search(para) if first else None
    m2 = last.search(para, m1.start()) if (m1 and last) else None
    if m1 and m2:
        end = m2.end()
        tail = re.match(r"[^\w\s\\]*", para[end:])
        end += len(tail.group(0)) if tail else 0
        raw, start = para[m1.start():end], m1.start()
    else:
        raw, start = pool[anchor]["text"], para.find(pool[anchor]["text"])
    line = int(pool[lo]["line"]) + para.count("\n", 0, max(0, start))
    return {"file": pool[anchor]["file"], "line": line, "text": raw.strip()}


_SRC_TOK_RE = re.compile(r"\w+(?:[-\u2010]\w+)*")   # a hyphenated word is one word ("re-reads")
_BRACKET_PAIRS = (("(", ")"), ("[", "]"), ("{", "}"))
_FMT_EMPTY_RE = re.compile(r"\\(?:emph|textbf|textit|textsc|textsl|textup|underline)\s*\{\s*\}")
_PRINTED_TOK_RE = re.compile(r"\w+(?:[-\u2010]\w+)*|[,;:.!?()\[\]-]")
_SRC_WILDCARD = "zqxprintedzqx"   # a reference, a citation, or inline math in a source spelling


def _pair_brackets(raw: str, s: int, e: int) -> Tuple[int, int]:
    """A deleted span widened over the bracket its own unmatched bracket would
    leave behind: deleting 'at 07:15 (UTC-5' takes the ')' as well."""
    for o, c in _BRACKET_PAIRS:
        d = raw[s:e].count(o) - raw[s:e].count(c)
        while d > 0:
            m = re.match(r"\s*" + re.escape(c), raw[e:])
            if not m:
                break
            e, d = e + m.end(), d - 1
        while d < 0:
            m = re.search(re.escape(o) + r"\s*$", raw[:s])
            if not m:
                break
            s, d = m.start(), d + 1
    return s, e


def _printed_tokens(text: str, tex: bool) -> List[str]:
    """The words and marks a sentence prints, case-folded; in a source
    spelling a reference, a citation, or inline math is one wildcard."""
    t = text or ""
    if tex:
        t = _REF_CMD_RE.sub(" %s " % _SRC_WILDCARD, t)
        t = _CITE_CMD_RE.sub(" %s " % _SRC_WILDCARD, t)
        t = re.sub(r"(?<!\\)\$[^$]*\$|\\\(.*?\\\)", " %s " % _SRC_WILDCARD, t)
        t = _detex_line(t)
    t = unicodedata.normalize("NFKC", t).replace("---", "\u2014").replace("--", "\u2013")
    return [x.casefold() for x in _PRINTED_TOK_RE.findall(t)]


def _prints_as(tex: str, text: str) -> bool:
    """Whether a source spelling prints as `text`, word for word and mark for
    mark (a wildcard stands for up to ten printed tokens; a spelling with more
    than six wildcards is never compared)."""
    toks = _printed_tokens(tex, True)
    if toks.count(_SRC_WILDCARD) > 6:
        return False
    pat = "".join(r"(?:\S+ ){0,10}?" if x == _SRC_WILDCARD else re.escape(x) + " " for x in toks)
    return re.fullmatch(pat, " ".join(_printed_tokens(text, False)) + " ") is not None


def _source_residue(ss: str, raw: str) -> Optional[str]:
    """What a source edit leaves that its source line did not have: a leading
    mark, an unpaired bracket or $, a hyphen without its word."""
    if re.match(r"\s*[,;:.)\]}]", ss) and not re.match(r"\s*[,;:.)\]}]", raw):
        return "it starts with a punctuation mark"
    for o, c in _BRACKET_PAIRS:
        d_new, d_old = ss.count(o) - ss.count(c), raw.count(o) - raw.count(c)
        if d_new != d_old:
            return "it leaves an unpaired '%s'" % (o if d_new > d_old else c)
    if (ss.count("$") - ss.count("\\$")) % 2 != (raw.count("$") - raw.count("\\$")) % 2:
        return "it leaves an unpaired '$'"
    lone = re.compile(r"(?:^|\s)-(?=[A-Za-z])")
    if lone.search(ss) and not lone.search(raw):
        return "it leaves a hyphen without its word"
    return None


def _tidy_text(s: str) -> str:
    s = _FMT_EMPTY_RE.sub("", s)  # a formatting command a deletion emptied (\emph{})
    s = re.sub(r"[ \t]{2,}", " ", s)
    s = re.sub(r"[ \t]+([,.;:!?])", r"\1", s)
    s = re.sub(r"([,;:])\s*([.!?])", r"\2", s)
    s = re.sub(r"(?<!\.)\.\.(?!\.)", ".", s)
    s = re.sub(r",\s*,", ",", s)
    s = re.sub(r"\(\s*\)", "", s)
    return s.strip()


def _source_suggestion(pdf_sentence: str, result: str, raw: str) -> Optional[str]:
    """The suggested wording carried over to the source spelling: every run of
    words the suggestion deletes or replaces is found once in the source (TeX
    markup between its words allowed) and changed there; None when a run is
    missing, ambiguous, or the suggestion only inserts. A deleted run takes
    the marks the suggestion no longer has with it — the comma after the
    sentence's first words, the comma before its last ones, the separator the
    suggestion has between kept words, the bracket its own bracket pairs —
    and a new first word is capitalized like the suggestion's."""
    import difflib
    ta = [(m.group(0), m.start(), m.end()) for m in _SRC_TOK_RE.finditer(pdf_sentence)]
    tb = [(m.group(0), m.start(), m.end()) for m in _SRC_TOK_RE.finditer(result)]
    ops = difflib.SequenceMatcher(None, [x[0].casefold() for x in ta], [x[0].casefold() for x in tb],
                                  autojunk=False).get_opcodes()
    edits: List[Tuple[int, int, str]] = []
    pos, cap = 0, False
    for tag, i1, i2, j1, j2 in ops:
        if tag == "equal":
            continue
        if i1 == i2:
            return None
        rx = _flex_re([w for x in ta[i1:i2] for w in re.findall(r"\w+", x[0])])
        ms = list(rx.finditer(raw)) if rx else []
        if len(ms) != 1 or ms[0].start() < pos:
            return None
        s, e = ms[0].start(), ms[0].end()
        rep = result[tb[j1][1]:tb[j2 - 1][2]] if j2 > j1 else ""
        if not rep:
            s, e = _pair_brackets(raw, s, e)
            if i1 == 0:  # the sentence's first words go, with the mark after them
                e += re.match(r"[\s,;:]*", raw[e:]).end()
                cap = bool(tb) and tb[0][0][:1].isupper()
            elif i2 == len(ta):  # its last words go, with the mark before them
                s = re.search(r"[\s,;:]*$", raw[:s]).start()
            else:  # between kept words: the separator the suggestion has there
                s = re.search(r"[\s,;:]*$", raw[:s]).start()
                e += re.match(r"[\s,;:]*", raw[e:]).end()
                gap = result[tb[j1 - 1][2]:tb[j1][1]] if 0 < j1 < len(tb) else " "
                rep = re.sub(r"[^,;:]", "", gap)[:1] + " "
        if s < pos:
            return None
        edits.append((s, e, rep))
        pos = e
    if not edits:
        return None
    out = raw
    for s, e, rep in reversed(edits):
        out = out[:s] + rep + out[e:]
    if cap:
        out = re.sub(r"^(\s*(?:``|[`\"'(\[])?\s*)([a-z])", lambda m: m.group(1) + m.group(2).upper(), out, count=1)
    return _tidy_text(out)


# what a suggested wording may keep or name without being unusable: a file name
# (its own check aside); in a supplementary note, also the commands that run or
# install the package — a code package's notes are where they belong
_PLAN_TOLERATED = frozenset({"ENG-FILENAME", "TEXT-CODE", "TEXT-GLUE", "TEXT-NUMFMT"})
_PLAN_SUPP_USAGE_RE = re.compile(r"(?:python3?\s+(?:-m\s+[\w.]+|[\w./-]+\.py)|pip3?\s+install|conda\s+(?:activate|create|"
                                 r"install|env))$", re.I | _A)


def _plan_hits(text: str, ctx: ScanContext, own: str = "", member: bool = False) -> Set[Tuple[str, str]]:
    """(check, match) of the engineering, process, and anonymity rules on a
    short text (INFO-level hits aside, and what a wording may keep at its place:
    _PLAN_TOLERATED unless it is the finding's own check, usage commands in a
    supplementary note)."""
    out: Set[Tuple[str, str]] = set()
    # with registration_labels: keep, the order a registration states is what a wording must keep
    orders = [(m.start(), m.end()) for m in _ORDER_ANCHOR_RE.finditer(text)] if ctx.reg_labels != "flag" else []
    for h in detect_text(text, "body", None, ctx, "pdf"):
        if CHECKS.get(h.check, {}).get("family") not in ("ENG", "PROC", "ANON") or h.severity == INFO:
            continue
        key = _norm_key(h.match if h.match is not None else text[h.start:h.end])
        if h.check != own and (h.check in _PLAN_TOLERATED or (
                member and h.check == "ENG-OPS" and _PLAN_SUPP_USAGE_RE.match(_collapse_ws(text[h.start:h.end])))
                or any(h.start < e and s < h.end for s, e in orders)):
            continue
        out.add((h.check, key))
    return out


def _seed_values(text: str) -> List[str]:
    """The integers a text gives as a seed: digits inside a name that says
    seed (seed_2099, SEED=7), or a whole integer within a few words of a seed
    word — never a decimal (a threshold such as 0.2)."""
    out: List[str] = []
    for m in re.finditer(r"[^\s,;()\[\]{}\"'`]+", text or ""):
        if re.search(r"seed", m.group(0), re.I):
            out += re.findall(r"\d+", m.group(0))
    for m in re.finditer(r"(?<![\w.])\d+(?![\w]|\.\d)", text or ""):
        if _SEED_WORD_RE.search((text or "")[max(0, m.start() - 40):m.end() + 40]):
            out.append(m.group(0))
    return list(dict.fromkeys(out))


def suggestion_problems(f: Dict[str, Any], sentence: str, passage: str, result: str, generic: bool,
                        suggestion: str, ctxd: Dict[str, Any], focus: Optional[str] = None) -> List[str]:
    """Why a suggested wording is not usable as the fix (empty: usable).
    Numbers, orderings, labels, and skeletons are read on the sentence the
    suggestion leaves (`result`); what the wording still says or adds is read
    on the words it puts in (`focus`, default the result), so a leak elsewhere
    in the sentence — another finding's — is not held against it."""
    pol = ctxd.get("policy") or {}
    reg_keep = str(pol.get("registration_labels") or "keep") != "flag"
    probs: List[str] = []
    if generic:
        m = _ORDER_ANCHOR_RE.search(passage) or (_REGLABEL_ANY_RE.search(passage) if reg_keep else None)
        if _GENERIC_DELETE_RE.match(suggestion or "") and m:
            probs.append("a plain deletion would drop the ordering or registration label it states ('%s'): keep "
                         "it (rule 1)" % _collapse_ws(m.group(0))[:60])
        return probs
    o_nums, r_nums = Counter(_number_tokens(sentence)), Counter(_number_tokens(result))
    alt = [x for x in _ALT_NUMBER_RE.findall(result) if x not in sentence]
    if alt:
        probs.append("writes a number in another form (%s)" % ", ".join(alt[:3]))
    new = list(dict.fromkeys((r_nums - o_nums).elements()))
    if new:
        probs.append("changes a number (%s is not in the original)" % ", ".join(new[:4]))
    # a seed value the wording no longer gives ("with its fixed seed", "seed_<s>"): a reproduction needs it
    gone_seed = next((s_ for s_ in _seed_values(sentence)
                      if not re.search(r"(?<!\d)%s(?!\d)" % re.escape(s_), result)), None)
    if gone_seed is not None:
        probs.append("drops a seed value (%s) a reproduction needs" % gone_seed)
    for rx, what in ((_ORDER_ANCHOR_RE, "an ordering"), (_REGLABEL_ANY_RE if reg_keep else None, "a registration label"),
                     (_POLICY_REG_RE if reg_keep else None, "a registration word")):
        if rx is None:
            continue
        o_m = [_collapse_ws(m.group(0)) for m in rx.finditer(sentence)]
        if len(list(rx.finditer(result))) < len(o_m):
            gone = next((x for x in o_m if x.casefold() not in result.casefold()), o_m[0])
            probs.append("drops %s ('%s')" % (what, gone[:60]))
            break
    ctx = _plan_ctx(pol, bool(ctxd.get("anonymous", True)))
    in_supp = bool((f.get("location") or {}).get("member"))
    put = result if focus is None else focus
    ho = _plan_hits(sentence, ctx, f["check"], in_supp)
    hr = _plan_hits(put, ctx, f["check"], in_supp)
    own_fam = CHECKS.get(f["check"], {}).get("family")
    for c, m in sorted(hr & ho):
        if f.get("layer") == "review" or c == f["check"] or CHECKS[c]["family"] == own_fam:
            probs.append("still matches %s ('%s')" % (c, m[:60]))
    o_checks = {c for c, _m in ho}
    for c, m in sorted(hr - ho):
        if c == f["check"]:  # the finding's own kind of wording, in other words ("July" -> "August")
            probs.append("still matches %s ('%s')" % (c, m[:60]))
        elif c not in o_checks:  # a kind of wording the sentence did not have (a reworded name or path is none)
            probs.append("adds wording %s flags ('%s')" % (c, m[:60]))
    match = str(f.get("match") or "")
    if (f.get("layer") != "review" and len(match) >= 3 and match.casefold() in sentence.casefold()
            and re.search(r"(?<!\w)%s(?!\w)" % re.escape(match), put, re.I)
            and not any(match.casefold() in p_.casefold() for p_ in probs)):
        probs.append("still contains '%s'" % match[:60])
    if f["check"] in ("PROC-REVISION", "PROC-REVIEW"):
        # the run or revision told in other words: any redo word (repeat, redo, again, re-execute, a
        # re-run) the sentence does not have outside the narration itself — a design term of the
        # sentence ("each arm is repeated five times") is its own — or what was fixed or corrected
        pi, pj = _find_norm(sentence, passage) if passage else (-1, -1)
        outside = sentence[:pi] + " " + sentence[pj:] if pi >= 0 else sentence
        alt = next((m.group(0) for m in _REDO_ALT_RE.finditer(put)
                    if not re.search(r"(?<!\w)%s(?!\w)" % re.escape(m.group(0)), outside, re.I)), None)
        if alt is None and f.get("pure_narration"):
            alt = next((m.group(0) for m in _REDO_ALT_NARR_RE.finditer(put)
                        if not re.search(r"(?<!\w)%s(?!\w)" % re.escape(m.group(0)), outside, re.I)), None)
        alt = alt or next((m.group(0) for m in _FIXED_ALT_RE.finditer(put)), None)
        if alt:
            probs.append("still narrates the run or the revision in other words ('%s')" % _collapse_ws(alt)[:60])
    if result.strip() and _norm_quote(result) != _norm_quote(sentence):
        sk = plan_skeleton_reason(result)
        if sk:
            probs.append("leaves a skeleton (%s): delete the whole sentence" % sk)
        else:
            cut = _empty_last_clause(result)
            if cut:
                probs.append("keeps a clause that says nothing (%s): drop it" % cut[2])
    return probs


# a run or a revision told in other words (PROC-REVISION, PROC-REVIEW wordings); "a second time" and "once more"
# only where the passage is pure narration (a rule that lets an incomplete execution run a second time is a
# fact of the design, and its neutral wording is the fix)
_REDO_ALT_RE = re.compile(r"\b(?:repeat(?:s|ed|ing)?|redo(?:ne|ing|es)?|redid|re-?execut(?:e|es|ed|ing)|"
                          r"re-?evaluat(?:e|es|ed|ing)|re-?comput(?:e|es|ed|ing)|re-?generat(?:e|es|ed|ing)|"
                          r"re-?train(?:s|ed|ing)?|re-?launch(?:es|ed|ing)?|re-?r[au]n(?:s|ning)?|again|anew|afresh)"
                          r"\b", re.I | _A)
_REDO_ALT_NARR_RE = re.compile(r"\b(?:a\s+second\s+time|once\s+more)\b", re.I | _A)
_FIXED_ALT_RE = re.compile(r"\b(?:fixed|fixing|corrected|correcting|patched|patching|repaired|repairing|updated|"
                           r"updating)\s+(?:(?:the|a|an|our|its|their|this|that)\s+)?(?:[\w-]+\s+)?(?:bugs?|scripts?|"
                           r"code|evaluators?|pipelines?|implementations?|initiali[sz]ations?|versions?|parsers?|"
                           r"scorers?|loaders?|runs?|results?|values?|evaluations?|experiments?|setups?|"
                           r"analys[ie]s|outputs?|numbers?|metrics?|fits?|data)\b", re.I | _A)
# what the plan also reads as saying nothing (never `apply`, whose deletions stay as narrow as
# before): where the numbers were read, what the code is written in, that the runs were done
_SOURCE_PRED_RE = re.compile(r"\b(?:is|are|was|were)\s+(?:taken|obtained|read|collected|derived|extracted|parsed|"
                             r"gathered|pulled|copied)\s+from\s+(?:(?:the|our|these|those|its|their)\s+)?"
                             r"(?:[\w-]+\s+){0,2}(?:logs?|log\s+files?|records?|files?|outputs?|runs?|traces?|dumps?)"
                             r"\s*[.;:!]?\s*$", re.I | _A)
_DONE_PRED_RE = re.compile(r"\b(?:is|are|was|were|has\s+been|have\s+been)\s+(?:completed|finished|done|concluded)"
                           r"\s*[.;:!]?\s*$", re.I | _A)
_IMPL_PRED_RE = re.compile(r"\b(?:is|are|was|were)\s+(?:implemented|written|built|developed|coded|programmed)\s+"
                           r"(?:in|with|using|on|via|atop)\s+", re.I | _A)
_CLAUSE_CUT_RE = re.compile(r",\s+(?=(?:and|but|while|whereas)\s)|;\s+", re.I)
# a reviewer's reason that asks for the whole sentence to go ("Delete this timing sentence.")
_REMOVE_SENTENCE_RE = re.compile(r"\b(?:remove|delete|drop|cut|omit|strike)\s+(?:the|this|that)\s+(?:(?:whole|entire|"
                                 r"standalone|full)\s+)?(?:[\w-]+\s+){0,2}sentence\b(?!['\u2019]s)", re.I)
_TIMEISH_RE = re.compile(r"(?<![\w:])\d{1,2}:\d{2}(?::\d{2})?(?![\w:])|\b(?:19|20)\d\d(?:[-/.]\d{1,2}(?:[-/.]\d{1,2})?)?\b"
                         r"|\b(?:UTC|GMT)\s*[+\-\u2212]\s*\d{1,2}\b", _A)


def plan_skeleton_reason(text: str) -> Optional[str]:
    """skeleton_reason, and what the fix plan also reads as saying nothing
    (never `apply`): only where the numbers were read ("Scores are read from
    the logs."), only that the runs were done, only what the code is
    written in — one clause, no number, no negation or comparison, at most two
    content words before the predicate (three before an implementation note)."""
    r = skeleton_reason(text)
    if r:
        return r
    t = unicodedata.normalize("NFKC", _NOTE_MARK_RE.sub(" ", _detex_line(text or ""))).strip()
    if re.search(r"\d", t) or _NEGATION_RE.search(t) or _COMPARE_RE.search(t):
        return None
    for rx, what in ((_SOURCE_PRED_RE, "where the numbers were read"), (_DONE_PRED_RE, "that the runs were done")):
        m = rx.search(t)
        if m and not re.search(r"[;:,]", t[:m.start()]) and len(_content_words(t[:m.start()])) <= 2:
            return "only %s is left ('%s')" % (what, _collapse_ws(t)[-60:])
    m = _IMPL_PRED_RE.search(t)
    if m and not re.search(r"[;:]", t[:m.start()]) and len(_content_words(t[:m.start()])) <= 3:
        tail, found = t[m.end():], []
        for rx in _SKELETON_STRIP:
            found += [x.group(0) for x in rx.finditer(tail)]
            tail = rx.sub(" ", tail)
        if found and not _content_words(tail):
            return "only what the code is written in is left (%s)" % ", ".join(
                "'%s'" % _collapse_ws(x) for x in found[:3])
    return None


def _empty_last_clause(text: str) -> Optional[Tuple[int, int, str]]:
    """(start, end, why) of a last clause that says nothing ("…, and the toy
    runs were done."), its separator included and the final mark not —
    only in a whole sentence (a final mark) and a clause of three words or more,
    never in a line a note continues on the next one."""
    cuts = list(_CLAUSE_CUT_RE.finditer(text or ""))
    tail = re.search(r"[.!?][\"')\]]*\s*$", text or "")
    if not cuts or not tail:
        return None
    m, end = cuts[-1], tail.start()
    clause = re.sub(r"^(?:and|but|while|whereas)\s+", "", text[m.end():end].strip(), flags=re.I)
    if len(_wordlist(clause)) < 3 or re.search(r"\d", clause):
        return None
    why = plan_skeleton_reason(clause)
    return (m.start(), end, why) if why else None


def _delete_sentence_basis(f: Dict[str, Any], sentence: str, ctxd: Dict[str, Any]) -> Optional[str]:
    """Why the plan may offer deleting the whole sentence for a confirmed leak
    the reviewer gave no wording for: the sentence says nothing once its
    tooling goes, or the reviewer asks for the sentence to go and it holds no
    number but the leaked date or time. Never for an ordering, a registration
    label (unless the policy flags them), a comparison, a required statement,
    or a heading."""
    if f.get("ruling") != "leak" or len(sentence or "") < 8 or f.get("region") == "end_matter":
        return None
    if _TEX_HEADING_RE.match(sentence) or sentence.lstrip().startswith("#"):
        return None
    if _ORDER_ANCHOR_RE.search(sentence) or _COMPARE_RE.search(sentence):
        return None
    pol = ctxd.get("policy") or {}
    if str(pol.get("registration_labels") or "keep") != "flag" and (
            _REGLABEL_ANY_RE.search(sentence) or _POLICY_REG_RE.search(sentence)):
        return None
    if str(f.get("check") or "").startswith("ENG-"):
        why = plan_skeleton_reason(sentence)
        if why:
            return "the sentence names only tooling (%s)" % why
    if _REMOVE_SENTENCE_RE.search(str(f.get("ruling_rationale") or "")):
        rest = _TIMEISH_RE.sub(" ", sentence.replace(str(f.get("match") or "\x00"), " "))
        if not re.search(r"\d", rest):
            return "the reviewer asks for the sentence to go; it states nothing else with a number"
    return None


def _sentence_delete_guard(f: Dict[str, Any], sentence: str, ctxd: Dict[str, Any]) -> Optional[str]:
    """What a whole-sentence deletion the plan offers would drop that a
    sentence must keep (None: it may be offered): a required statement, a
    heading, an ordering, a registration label (unless the policy flags them),
    a comparison."""
    if f.get("region") == "end_matter" or f.get("subregion") in ("ai_use", "ethics", "reproducibility"):
        return "it is part of a required statement"
    if _TEX_HEADING_RE.match(sentence) or sentence.lstrip().startswith("#"):
        return "it is a heading"
    m = _ORDER_ANCHOR_RE.search(sentence)
    if m:
        return "it states an ordering ('%s')" % _collapse_ws(m.group(0))[:60]
    pol = ctxd.get("policy") or {}
    m = (_REGLABEL_ANY_RE.search(sentence) or _POLICY_REG_RE.search(sentence)) if str(
        pol.get("registration_labels") or "keep") != "flag" else None
    if m:
        return "it holds a registration label ('%s')" % _collapse_ws(m.group(0))[:60]
    m = _COMPARE_RE.search(sentence)
    if m:
        return "it states a comparison ('%s')" % m.group(0)
    return None


def _deletes_the_sentence(sentence: str, rewrite: str) -> bool:
    """Whether an instruction asks for this whole sentence to go: it quotes
    the sentence, or the words it begins with ("Delete only the sentence
    beginning 'X'")."""
    m = _INSTR_SENT_DEL_RE.match(rewrite or "")
    if not m or not sentence:
        return False
    q = _norm_quote(re.sub(r"(?:\.\.\.|…)\s*$", "", m.group("a"))).rstrip(" .")
    s = _norm_quote(sentence)
    return len(q) >= 8 and (s.startswith(q) or (q in s and len(q) >= 0.6 * len(s)))


def _analyze_plan_entry(p: Dict[str, Any], f: Dict[str, Any], ctxd: Dict[str, Any]) -> None:
    """The whole sentence, the source spelling, and the deterministic filter of
    one plan entry (from the group's first finding)."""
    loc = f.get("location") or {}
    passage, sentence = _sentence_of(f, ctxd)
    if sentence:
        p["original"] = sentence[:_PLAN_ORIGINAL_MAX]
    rewrite = _LINE_MARK_RE.sub("", str(f.get("rewrite") or "")).strip()
    if rewrite and _deletes_the_sentence(sentence, rewrite):
        # "Delete (only) the sentence beginning 'X'": a deletion, never a wording to read for numbers
        guard = _sentence_delete_guard(f, sentence, ctxd)
        src = _source_of(sentence, f, ctxd.get("sources") or []) if not loc.get("member") else None
        if src:
            p["source"] = src
        p["_result"], p["_sentence"] = "", sentence
        if guard is None:
            p["suggestion"] = "Delete the whole sentence: \"%s\"" % sentence[:300]
            p["suggestion_basis"] = "the reviewer asks for this sentence to go"
            p["specific"], p["suggestion_usable"] = True, True
            if src and _safe_sentence(src["text"], "paper"):
                p["source_suggestion"] = "(delete) %s" % src["text"][:300]
        else:
            p["suggestion_usable"], p["specific"] = False, False
            p["suggestion_problems"] = ["deleting the whole sentence would drop what it must keep: %s (rule 1)" % guard]
            p["rejected_suggestion"] = rewrite
            p["suggestion"] = "No usable wording (%s): a person rewrites the passage." % p["suggestion_problems"][0]
        if sentence and len(sentence) >= 8:
            p["_site"] = ("text", loc.get("member") or loc.get("artifact") or "", str(loc.get("page") or ""),
                          _norm_quote(sentence), _note_line_of(loc, ctxd, passage))
        return
    instr = _apply_instruction(sentence, rewrite) if rewrite else None
    # an instruction whose quoted words this sentence does not hold was written for another place
    elsewhere = bool(rewrite) and instr is None and bool(_instruction_pairs(rewrite))
    if instr is not None:  # "Replace 'A' with 'B'": the sentence with B in place of A
        result, focus = instr
    else:
        result = _result_of(sentence, passage, rewrite) if rewrite and not elsewhere else ""
        focus = rewrite or None
    if rewrite:
        if not elsewhere:
            p["suggestion_check"] = _vet_suggestion(result, sentence)
        p["suggestion"] = rewrite
    probs = (["the instruction quotes words this sentence does not hold (written for another place of the group)"]
             if elsewhere else
             suggestion_problems(f, sentence, passage, result, not rewrite, p.get("suggestion") or "", ctxd, focus))
    cut = _empty_last_clause(result) if (probs and result and all(
        x.startswith("keeps a clause that says nothing") for x in probs)) else None
    if cut:  # the wording without its last clause, when that clause is all that is wrong with it
        trimmed = _tidy_text(result[:cut[0]] + result[cut[1]:])
        if not suggestion_problems(f, sentence, passage, trimmed, False, trimmed, ctxd, None):
            p["trimmed_from"], p["suggestion"] = rewrite, trimmed
            p["suggestion_check"] = _vet_suggestion(trimmed, sentence)
            result, probs = trimmed, []
    src = _source_of(sentence, f, ctxd.get("sources") or []) if not loc.get("member") else None
    if src:
        p["source"] = src
    p["specific"] = bool(rewrite)
    basis = None if (rewrite or probs) else _delete_sentence_basis(f, sentence, ctxd)
    if basis:  # a confirmed leak with no wording, in a sentence that says nothing else
        p["suggestion"] = "Delete the whole sentence: \"%s\"" % sentence[:300]
        p["suggestion_basis"], p["specific"] = basis, True
        if src and _safe_sentence(src["text"], "paper"):
            p["source_suggestion"] = "(delete) %s" % src["text"][:300]
    if probs:
        p["suggestion_usable"] = False
        p["suggestion_problems"] = probs
        p["rejected_suggestion"] = rewrite or p.get("suggestion")
        # a heading is reworded, never deleted: "#" opens a heading in a document, a comment in code
        heading = bool(_TEX_HEADING_RE.match(sentence)) or (
            sentence.lstrip().startswith("#") and bool(_DOC_RE.search(str(loc.get("member") or ""))))
        if any(x.startswith("leaves a skeleton") for x in probs) and len(sentence) >= 3 and not heading:
            p["suggestion"] = "Delete the whole sentence: \"%s\"" % sentence[:300]
            p["specific"], p["_fallback"] = True, True
            if src and _safe_sentence(src["text"], "paper"):
                p["source_suggestion"] = "(delete) %s" % src["text"][:300]
        else:
            p["suggestion"] = "No usable wording (%s): a person rewrites the %s%s." % (
                probs[0], "heading" if heading else "passage", " (see How)" if p.get("advice") else "")
            p["specific"] = False
    else:
        p["suggestion_usable"] = True
        if rewrite and src:
            ss = _source_suggestion(sentence, result, src["text"])
            if ss is not None:
                # offered only when it leaves no stray mark and, where the source line prints as
                # the PDF sentence, prints as the suggestion
                why = _source_residue(ss, src["text"])
                if why is None and _prints_as(src["text"], sentence) and not _prints_as(ss, result):
                    why = "it would not print as the suggestion"
                if why:
                    p["source_suggestion_problem"] = why
                else:
                    p["source_suggestion"] = ss
    if f.get("pure_narration"):
        # the sentence (or clause) says nothing but the narration: the fix is deleting it, never a reword
        if rewrite:
            p["rejected_suggestion"] = rewrite
            p["suggestion_problems"] = list(dict.fromkeys(
                (p.get("suggestion_problems") or []) + ["tells the run or the revision again: the passage says "
                                                        "nothing else (%s)" % f["pure_narration"]]))
        unit = f.get("unit_text") or sentence
        p["suggestion"] = "Delete the narration: \"%s\"" % unit[:300]
        p["suggestion_basis"], p["specific"], p["suggestion_usable"] = "pure narration: %s" % f["pure_narration"], \
            True, True
        p.pop("source_suggestion", None)
        if src and _norm_quote(unit) == _norm_quote(sentence) and _safe_sentence(src["text"], "paper"):
            p["source_suggestion"] = "(delete) %s" % src["text"][:300]
    # what the suggestion leaves of the sentence: two wordings that change different words of one sentence
    # complement each other (the merge reads it)
    p["_result"], p["_sentence"] = (result if not p.get("_fallback") else ""), sentence
    chk = f["check"]
    if chk in _XREF_KEYED:
        p["_site"] = ("xref", _norm_key(f.get("match")))
    elif chk.startswith("PAGE-"):
        p["_site"] = ("page", loc.get("artifact"))
    elif sentence and len(sentence) >= 8:
        p["_site"] = ("text", loc.get("member") or loc.get("artifact") or "",
                      str(loc.get("page") or ""), _norm_quote(sentence), _note_line_of(loc, ctxd, passage))


def _note_line_of(loc: Dict[str, Any], ctxd: Dict[str, Any], passage: str) -> str:
    """The line of a supplementary note a finding quotes: findings on two lines
    of one wrapped sentence stay two places, each rewording its own line."""
    t = (ctxd.get("supp_texts") or {}).get(loc.get("member") or "") if loc.get("member") else None
    if not t or len(passage) < 4:
        return ""
    t = _LINE_MARK_RE.sub("", t)
    i, _j = _find_norm(t, passage)
    return str(t.count("\n", 0, i)) if i >= 0 else ""


def _complementary(ps: Sequence[Dict[str, Any]]) -> bool:
    """Whether usable wordings for one sentence change words that never
    overlap (each keeps what the others change): then all of them apply."""
    import difflib
    sents = {_norm_quote(p.get("_sentence") or "") for p in ps}
    if len(sents) != 1 or not next(iter(sents)) or any(not (p.get("_result") or "").strip() for p in ps):
        return False
    base = _wordlist(ps[0]["_sentence"])
    spans: List[Tuple[int, int]] = []
    for p in ps:
        ops = [(i1, i2) for tag, i1, i2, _j1, _j2 in difflib.SequenceMatcher(
            None, base, _wordlist(p["_result"]), autojunk=False).get_opcodes() if tag != "equal"]
        if not ops:
            return False
        spans.append((min(a for a, _b in ops), max(b for _a, b in ops)))
    spans.sort()
    return all(spans[i][1] < spans[i + 1][0] for i in range(len(spans) - 1))


def _merge_plan_sites(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One plan item per place of the text and root cause: the checks that hit
    one sentence, every symptom of one reference key (the log line, the printed
    ?? or (?), the source key), the page-count findings. Automatic items and
    groups spread over several places are left as they are. Differing usable
    wordings for one place become one item that names the conflict."""
    person = [p for p in items if not p.get("auto")]
    refs = {p["_site"][1] for p in person if p.get("_site") and p["_site"][0] == "xref"
            and p["check"] in _XREF_REF_KEYED}
    cites = {p["_site"][1] for p in person if p.get("_site") and p["_site"][0] == "xref"
             and p["check"] not in _XREF_REF_KEYED}
    for p in person:  # a printed ?? or (?) is the symptom of the one broken key, when there is one
        kind = ("ref" if p["check"] == "XREF-PDF-QQ" or (p["check"] == "XREF-LOG-UNDEF" and "ref" in
                                                         str(p["match"]).lower()) else
                "cite" if p["check"] in ("XREF-PDF-CITE", "XREF-LOG-UNDEF") else None)
        keys = refs if kind == "ref" else cites if kind == "cite" else set()
        if kind and len(keys) == 1:
            p["_site"] = ("xref", next(iter(keys)))
    by_site: Dict[Tuple[Any, ...], List[Dict[str, Any]]] = {}
    for p in person:
        site = p.get("_site")
        if not site or (site[0] == "text" and len(p["where"]) > 1):
            continue
        by_site.setdefault(site, []).append(p)
    merged_away: Set[int] = set()
    out: List[Dict[str, Any]] = []
    for site, ps in by_site.items():
        if len(ps) < 2:
            continue
        ps = sorted(ps, key=lambda p: (-_SEV_RANK[p["severity"]], p["group"]))
        m = dict(ps[0])
        m["groups"] = [g for p in ps for g in p["groups"]]
        m["checks"] = list(dict.fromkeys(c for p in ps for c in p.get("checks") or [p["check"]]))
        m["n"] = sum(p["n"] for p in ps)
        m["where"] = list(dict.fromkeys(w for p in ps for w in p["where"]))[:8]
        rules = list(dict.fromkeys(p["_why_rule"] for p in ps if p.get("_why_rule")))
        revs = list(dict.fromkeys(p["_why_rev"] for p in ps if p.get("_why_rev")))
        m["why"] = (("; ".join(rules) + ((" Reviewer: " + " | ".join(revs)) if revs else "")) if rules or revs else
                    "; ".join(dict.fromkeys(p["why"] for p in ps if p.get("why"))))[:1500]
        m["why_not_auto"] = "; ".join(dict.fromkeys(p["why_not_auto"] for p in ps if p.get("why_not_auto")))
        m["parts"] = [x for p in ps for x in p.get("parts") or []]
        m["categories"] = list(dict.fromkeys(p["category"] for p in ps))
        cands = next((p["candidates"] for p in ps if p.get("candidates")), None)
        if cands:  # a broken key's candidate labels, from whichever symptom carries them
            m["candidates"] = cands
        specific: List[Dict[str, Any]] = []
        for p in ps:
            if p.get("specific") and p.get("suggestion_usable", True) and \
                    _norm_quote(p["suggestion"]) not in {_norm_quote(x["suggestion"]) for x in specific}:
                specific.append(p)
        rejected = [{"group": p["group"], "suggestion": p.get("rejected_suggestion"),
                     "problems": p.get("suggestion_problems")} for p in ps if p.get("suggestion_usable") is False]
        if rejected:
            m["rejected_suggestions"] = rejected
        kept = ("suggestion_check", "source_suggestion", "source_suggestion_problem", "trimmed_from", "suggestion_basis")
        for k in kept + ("suggestion_problems", "rejected_suggestion"):
            m.pop(k, None)
        if len(specific) == 1:
            m.update({k: specific[0][k] for k in ("suggestion",) + kept if k in specific[0]})
            m["suggestion_usable"], m["conflict"] = True, False
        elif len(specific) > 1 and _complementary(specific):
            # each wording changes other words of the sentence: all of them apply, none is a choice
            m["conflict"], m["complementary"] = False, True
            m["alternatives"] = [x["suggestion"] for x in specific]
            m["suggestion_usable"] = True
            m["suggestion"] = ("Apply all of these — each changes other words of the sentence (none is applied "
                               "automatically): " + " | ".join("(%d) %s" % (i, x["suggestion"])
                                                              for i, x in enumerate(specific, 1)))
        elif len(specific) > 1:
            m["conflict"] = True
            m["alternatives"] = [x["suggestion"] for x in specific]
            m["suggestion"] = ("Conflicting suggestions for this place — a person picks one (none is applied "
                               "automatically): " + " | ".join("(%d) %s" % (i, x["suggestion"])
                                                              for i, x in enumerate(specific, 1)))
        else:
            m["suggestion_usable"] = not rejected
            # every wording left a skeleton: the whole-sentence deletion the script offers stays offered
            falls = list(dict.fromkeys((p["suggestion"], p.get("source_suggestion")) for p in ps if p.get("_fallback")))
            if len(falls) == 1:
                m["suggestion"] = falls[0][0]
                if falls[0][1]:
                    m["source_suggestion"] = falls[0][1]
        m["severity"] = ps[0]["severity"]
        for p in ps:
            merged_away.add(id(p))
        out.append(m)
    return [p for p in items if id(p) not in merged_away] + out


# a reviewer's reason that asks to keep the re-run or the fix in the text: never relayed for narration
_KEEP_HISTORY_RE = re.compile(r"\b(?:keep|keeps|keeping|preserve|preserves|preserving|retain|retains|retaining|"
                              r"maintain|maintains|mention|mentions|state|states|note|notes|record|records|disclose|"
                              r"discloses|report|reports|acknowledge|acknowledges)\b[^.;]{0,160}?\b(?:re-?r[au]n\w*|"
                              r"repeat\w*|redo\w*|redid|redone|re-?execut\w*|correct\w*|fix\w*|bug\w*|histor\w*|"
                              r"updat\w*|patch\w*|again)\b", re.I)


def _plan_rationale(f: Dict[str, Any]) -> str:
    """The reviewer's reason as the plan shows it: for revision and review
    narration, never a request to keep the re-run or the fix in the text —
    and nothing at all for pure narration, whose fix is deleting it."""
    r = str(f.get("ruling_rationale") or "")
    if f.get("check") not in ("PROC-REVISION", "PROC-REVIEW") or not r:
        return r
    if f.get("pure_narration"):
        return ""
    return " ".join(x for x in re.split(r"(?<=[.;!?])\s+", r) if not _KEEP_HISTORY_RE.search(x)).strip()


def _manual_suggestion(p: Dict[str, Any], manual: Sequence[Dict[str, Any]], usage: Optional[str]) -> None:
    """The plan's suggestion for places of a fragment item no clean deletion
    takes: the heading without the hardware word for a person to reword, or
    the sentence exactly as the deletion would leave it (`after_deletion`) for
    a person to finish — a reviewer's usable wording stays the suggestion."""
    entry = next((m for m in manual if m.get("after")), manual[0] if manual else None)
    if entry is None:
        return
    if entry.get("sentence"):
        p["original"] = entry["sentence"][:_PLAN_ORIGINAL_MAX]
    p["manual_places"] = [m["where"] for m in manual if m.get("where")][:8]
    if p.get("suggestion_usable") and p.get("specific"):
        return
    if (usage or entry.get("usage")) == "title":
        p["suggestion"] = ("Reword the heading by hand; without the hardware word it reads: \"%s\"" % entry["after"]
                           if entry.get("after") else "Reword the heading by hand.")
    elif entry.get("after") is not None:
        p["after_deletion"] = entry["after"]
        p["suggestion"] = ("Delete the leak and reword what is left by hand — the deletion alone would leave: "
                           "\"%s\"" % entry["after"])
    for k in ("suggestion_problems", "rejected_suggestion", "source_suggestion"):
        p.pop(k, None)
    p["suggestion_usable"], p["specific"] = True, True


def build_fix_plan(findings: List[Dict[str, Any]], queue: List[Dict[str, Any]],
                   blocked: Optional[Dict[str, str]] = None,
                   context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """details.fix_plan: every live (WARN or BLOCK) group, so nothing left over
    is silent: where it is (file:line, PDF page, member, and the source
    spelling), the whole original sentence, its category, why it is a problem,
    why the loop does not fix it, and a suggested fix — the reviewer's wording
    after the deterministic filter (`suggestion_usable`, `suggestion_problems`;
    a wording that adds words lists them), mapped to the source when it can be
    (`source_suggestion`). Items at one place merge (`groups`, `checks`,
    `parts`; a `conflict` lists the alternatives). Every fix-queue item is
    listed as automatic (`auto: true`, `queue_group`) — including one whose
    findings are INFO — so the plan's automatic part matches the queue."""
    blocked = blocked or {}
    ctxd = context or {}
    queued = {g["group"]: g for g in queue}
    meta_q = queued.get("META")
    # a printed ?? or an undefined-reference line of the log is resolved by the queued
    # repair of its key, or (no key) when every broken source key is queued
    src_keys = {f["match"] for f in findings if f["check"] in ("XREF-SRC-REF", "XREF-SRC-CITE")
                and f["severity"] != INFO and not f.get("exempted_by")}
    queued_keys = {g["match"] for g in queue if g["fix_class"] in ("xref-ref", "xref-cite")}
    rebuild_all = bool(src_keys) and src_keys <= queued_keys or any(g["fix_class"] == "rebuild" for g in queue)

    def symptom_fixed(f: Dict[str, Any]) -> bool:
        return f["check"] in _XREF_SYMPTOMS and (f["match"] in queued_keys or (f["match"] not in src_keys
                                                                               and rebuild_all))
    sentence_items = [g for g in queue if g.get("fix_class") == "delete-sentence"]
    covered_by = {grp: g for g in sentence_items for grp in g.get("covers") or []}

    def taken_by_sentence(f: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """The queued sentence item whose deletion takes this finding's passage with it."""
        loc = f.get("location") or {}
        key = _norm_key(f.get("match"))
        for g in sentence_items:
            lines = {str(x) for x in g.get("lines") or []}
            if loc.get("file") and "%s:%s" % (loc.get("file"), loc.get("line")) in lines and key and \
                    key in _norm_key(g.get("deleted")):
                return g
        return None
    # a group every live occurrence of which a queued sentence deletion takes along (a date beside a clock time)
    taken: Dict[str, Optional[Dict[str, Any]]] = {}
    for f in findings:
        if f["severity"] == INFO or f.get("exempted_by") or f.get("layer") not in ("pdf", "tex"):
            if f.get("group") and f["severity"] != INFO and not f.get("exempted_by"):
                taken[f["group"]] = None
            continue
        g_ = taken_by_sentence(f) if sentence_items else None
        if f["group"] not in taken:
            taken[f["group"]] = g_
        elif taken[f["group"]] is not None and g_ is None:
            taken[f["group"]] = None
    out: Dict[str, Dict[str, Any]] = {}
    manual_by_group = ctxd.get("manual") or {}
    for f in findings:
        if f["severity"] == INFO or f.get("exempted_by") or f["check"].startswith("SKIP-"):
            continue
        grp = f["group"]
        q = queued.get(grp) or covered_by.get(grp) or (
            meta_q if f["check"] in _META_FIX_CHECKS or f.get("pdf_field") else None) or (
            queued.get("REPACK") if f["check"] in ("SUPP-META", "SUPP-GZIP", "SUPP-TAR") else None) or (
            {"fix_class": "rebuild"} if symptom_fixed(f) else None) or taken.get(grp)
        slot = grp
        if q is not None and f.get("hw_usage") and f["check"] in _DRAFT_CHECKS_HW and _fix_class(f) is None:
            # a metric of the study or a heading's wording in a group whose other places are queued
            q, slot = None, "%s/%s" % (grp, f["hw_usage"])
        elif q is not None and f.get("code_line") and f["check"] in ("SUPP-HW", "SUPP-TEXT") and _fix_class(f) is None:
            # a code line or a string the code uses, in a group whose notes elsewhere are queued
            q, slot = None, "%s/code" % grp
        p = out.get(slot)
        if p is None:
            chk = f["check"]
            cat = next((c for pre, c in _PLAN_CATEGORY if chk.startswith(pre)), "other")
            key = stable_key(chk, f["match"], f.get("region"), f.get("subregion"))
            why_not = None
            if q is None:
                why_not = (blocked.get(key) or
                           ("a reviewer's own finding: never applied automatically" if f.get("layer") == "review" else
                            "ruling flipped without new evidence: decide once" if f.get("ruling_flip") else
                            "ruled uncertain" if f.get("ruling") == "uncertain" else
                            "not reviewed" if f["certainty"] == CANDIDATE and f.get("ruling") in (None, "unreviewed")
                            else "a stop condition: numbers belong to /paper-claim-audit" if chk in STOP_CHECKS
                            else "user configuration" if chk.startswith(("ANON-LIST-", "ALLOW-", "CONFIG-"))
                            else "no unique label of the same kind to point at" if chk == "XREF-SRC-REF"
                            else "a single-key citation or a probable typo of an existing key" if chk == "XREF-SRC-CITE"
                            else "a regression of an earlier round: deliver a round without it (restore)"
                            if chk == "FIX-REGRESSION"
                            else "pure narration, but %s: a person deletes it" % f.get("unit_exclusion")
                            if f.get("pure_narration") and f.get("unit_exclusion")
                            else "a code line, or a string the code uses (a template it writes out, a prompt): the "
                                 "loop edits notes only — a person changes the code and what it wrote"
                            if f.get("code_line")
                            else "outside the conservative whitelist (a rewording, a rename, or an authors' decision)"))
            usage = f.get("hw_usage") if chk in _DRAFT_CHECKS_HW else None
            # the places the draft could not take belong to the group's own item, never to a code-line slot
            manual = manual_by_group.get(grp) if q is None and slot == grp else None
            if q is None and usage:
                why_not = ("the hardware word names a measured quantity of the study (a metric), not the machine the "
                           "authors ran on" if usage == "metric" else
                           "the hardware word sits in a heading: a person rewords the heading" if usage == "title"
                           else "the hardware word names a measured quantity of the study (a metric) or sits in a "
                                "heading: never deleted automatically")
            elif manual:
                why_not = "no clean deletion: %s" % manual[0]["why"]
            rewrite = f.get("rewrite") or ""
            rationale = _plan_rationale(f)
            rule = (f.get("rule") or "") + ((" Pure narration: %s." % f["pure_narration"])
                                            if f.get("pure_narration") else "")
            p = out[slot] = {
                "group": grp, "groups": [grp], "check": chk, "family": f["family"], "severity": f["severity"],
                "category": cat, "match": f["match"], "original": f.get("excerpt") or f["match"], "where": [], "n": 0,
                "why": rule + ((" Reviewer: " + rationale) if rationale else ""),
                "_why_rule": rule, "_why_rev": rationale,
                "ruling": f.get("ruling"), "auto": q is not None, "fix_class": q.get("fix_class") if q else None,
                "queue_group": q.get("group") if q else None,
                "why_not_auto": why_not,
                "suggestion": rewrite or f.get("suggestion") or CHECKS.get(chk, {}).get("fix", ""),
                "advice": _PLAN_ADVICE.get(cat)}
            p["parts"] = [{"group": grp, "check": chk, "severity": f["severity"], "why_not_auto": why_not,
                           "ruling": f.get("ruling"), "category": cat}]
            if ctxd and q is None:
                _analyze_plan_entry(p, f, ctxd)
            elif rewrite:
                p["suggestion_check"] = _vet_suggestion(rewrite, (f.get("match") or "") + " " + (f.get("excerpt") or ""))
            if q is None and usage and "metric" in usage:
                keep = ("Keep it: '%s' names a measured quantity of the study here (decide only whether the metric "
                        "itself belongs in the paper)" % f["match"])
                if "title" in usage:
                    keep += ("; where it sits in a heading, reword the heading by hand%s" % (
                        " — without the hardware word it reads: \"%s\"" % f["title_without"]
                        if f.get("title_without") else ""))
                p["suggestion"], p["suggestion_usable"] = keep, True
                for k_ in ("suggestion_problems", "rejected_suggestion", "source_suggestion"):
                    p.pop(k_, None)
            elif q is None and usage:
                _manual_suggestion(p, [{"usage": usage, "after": f.get("title_without"),
                                        "sentence": f.get("title_line"), "where": _where_str(f)}], usage)
            elif q is None and manual:
                _manual_suggestion(p, manual, None)
        p["n"] += 1
        p["severity"] = _sev_max(p["severity"], f["severity"])
        p["parts"][0]["severity"] = p["severity"]
        w = _where_str(f)
        mem_ = (f.get("location") or {}).get("member")
        if f.get("close_labels") and not p.get("candidates"):
            p["candidates"] = list(f["close_labels"])
        for w_ in ([w] if not (f.get("hw_usage") and mem_ and f.get("lines")) else
                   ["%s:%s" % (mem_, ln) for ln in f["lines"]]):
            if w_ and w_ not in p["where"] and len(p["where"]) < 8:
                p["where"].append(w_)
        for w_ in f.get("ref_places") or []:  # every place a broken key is referenced, once
            if not any(x == w_ or x.endswith(" " + w_) for x in p["where"]) and len(p["where"]) < 8:
                p["where"].append(w_)
    items = list(out.values())
    if ctxd:
        items = _merge_plan_sites(items)
    # the places of a queued fragment item no clean deletion takes: for a person, with the sentence as the
    # deletion would leave it
    for g in queue:
        if not g.get("manual"):
            continue
        cat = next((c for pre, c in _PLAN_CATEGORY if str(g["check"]).startswith(pre)), "other")
        why_m = "no clean deletion at these places: %s" % g["manual"][0]["why"]
        pm = {"group": g["group"], "groups": [g["group"]], "check": g["check"],
              "family": CHECKS.get(str(g["check"]).split("+")[0], {}).get("family", "ENG"),
              "severity": g["severity"], "category": cat, "match": g["match"], "original": g["match"],
              "where": [m["where"] for m in g["manual"]][:8], "n": len(g["manual"]),
              "why": CHECKS.get(str(g["check"]), {}).get("rule", ""), "ruling": None, "auto": False,
              "fix_class": None, "queue_group": None, "why_not_auto": why_m, "suggestion": "",
              "advice": _PLAN_ADVICE.get(cat),
              "parts": [{"group": g["group"], "check": g["check"], "severity": g["severity"], "why_not_auto": why_m,
                         "ruling": None, "category": cat}]}
        _manual_suggestion(pm, g["manual"], g["manual"][0].get("usage"))
        items.append(pm)
    # every queue item is in the plan (a META item whose findings are INFO included)
    listed = {p.get("queue_group") for p in items if p.get("auto")}
    for g in queue:
        if g["group"] in listed:
            continue
        cat = next((c for pre, c in _PLAN_CATEGORY if str(g["check"]).startswith(pre)), "other")
        items.append({"group": g["group"], "groups": [g["group"]], "check": g["check"],
                      "family": CHECKS.get(str(g["check"]).split("+")[0], {}).get("family", "META"),
                      "severity": g["severity"], "category": cat, "match": g["match"], "original": g["match"],
                      "where": list(g.get("where") or []), "n": g.get("n", 1),
                      "why": "queued for the automatic fix (%s)" % g["fix_class"], "ruling": None, "auto": True,
                      "fix_class": g["fix_class"], "queue_group": g["group"], "why_not_auto": None,
                      "suggestion": "", "advice": None,
                      "parts": [{"group": g["group"], "check": g["check"], "severity": g["severity"],
                                 "why_not_auto": None, "ruling": None, "category": cat}]})
    for p in items:
        for k in ("_site", "specific", "_why_rule", "_why_rev", "_fallback", "_result", "_sentence"):
            p.pop(k, None)
    rank = {r: i for i, r in enumerate(REASON_PRIORITY)}
    items = sorted(items, key=lambda p: (p["auto"], 0 if p["severity"] == BLOCK else 1,
                                         rank.get(REASON_BY_FAMILY.get(p["family"], ""), 99), p["group"]))
    for i, p in enumerate(items, 1):
        p["id"] = "P-%03d" % i
    for p in items:  # the page limit: which items change text of the main body
        if p.get("auto") or "PAGE-LIMIT" not in (p.get("checks") or [p["check"]]):
            continue
        end = _plan_page(p)
        body = sorted(((q["id"], pg) for q in items if q is not p and not q.get("auto")
                       for pg in [_plan_page(q)] if pg and end and pg <= end), key=lambda x: (x[1], x[0]))
        if body:
            p["body_items"] = ["%s (p.%d)" % x for x in body[:12]]
    return items


def _plan_page(p: Dict[str, Any]) -> Optional[int]:
    """The first PDF page a plan item names (its `where`), or None."""
    for w in p.get("where") or []:
        m = re.search(r"(?:^|\s)p\.(\d+)\b", str(w))
        if m:
            return int(m.group(1))
    return None


def fix_plan_check(plan: List[Dict[str, Any]], queue: List[Dict[str, Any]]) -> Dict[str, Any]:
    """The plan's self-check: every fix-queue group is listed as automatic."""
    want = {g["group"] for g in queue}
    have = {p.get("queue_group") for p in plan if p.get("auto") and p.get("queue_group")}
    return {"queue_groups": len(want), "listed": len(want & have), "ok": want <= have,
            "missing": sorted(want - have)}


def render_fix_plan(art: Dict[str, Any]) -> str:
    """FIX_PLAN.md: the modification list for a person (and the automatic
    fixes still open), from the same finalize call as the report."""
    det = art.get("details") or {}
    plan = det.get("fix_plan") or []
    person = [p for p in plan if not p.get("auto")]
    auto = [p for p in plan if p.get("auto")]
    lines = ["# Paper Hygiene Fix Plan", "",
             "**Verdict**: %s (`%s`) · mode: %s · generated: %s" % (art.get("verdict"), art.get("reason_code"),
                                                                     det.get("run_mode"), art.get("generated_at")),
             "", "The automatic `— fix` only deletes confirmed leak fragments, repairs verified references, adds "
             "metadata lines, and drops junk members. Everything below that is not marked automatic is for a person: "
             "change it in the sources (or the supplement), rebuild, and run `— recheck`. A suggested wording never "
             "adds a fact; when it adds words, they are listed — check them before you use it. A wording the script "
             "found unusable (it changes a number, drops a registration label or an ordering, still matches the "
             "check or tells the same story in other words, or leaves a skeleton) is shown as a hint, never as the "
             "fix.", ""]
    ae = det.get("auto_edits") or {}
    if ae.get("total"):
        lines += ["**Changed automatically in this run**: %d changed place(s)%s, %d rejected by the whitelist; "
                  "files: %s" % (ae.get("total", 0), (" from %d applied edit(s)" % ae["applied_edits"])
                                 if ae.get("applied_edits") else "", ae.get("rejected", 0),
                                 ", ".join(ae.get("files") or []) or "—"), ""]
    if det.get("deliver"):
        lines += ["**Round to deliver**: %s" % det.get("deliver"), ""]
    pc = det.get("fix_plan_check") or {}
    if pc:
        lines += ["**Automatic fixes still open**: %d queue item(s), %d listed below%s" % (
            pc.get("queue_groups", 0), pc.get("listed", 0),
            "" if pc.get("ok", True) else " — SELF-CHECK FAILED: missing %s" % ", ".join(pc.get("missing") or [])), ""]
    lines += ["## Summary", "", "| Id | Severity | Category | Where | Original |", "|---|---|---|---|---|"]
    for p in person:
        lines.append("| %s | %s | %s | %s | %s |" % (p["id"], p["severity"], _md_escape(p["category"]),
                                                     _md_escape("; ".join(p["where"][:3])),
                                                     _md_escape(p["original"])[:90]))
    lines.append("")
    lines += ["## For a person", ""]
    if not person:
        lines += ["Nothing.", ""]
    for p in person:
        groups = p.get("groups") or [p["group"]]
        lines += ["### %s [%s] %s — \"%s\"" % (p["id"], p["severity"], p["category"], _md_escape(p["match"])[:80]), "",
                  "- **Where**: %s" % (_md_escape("; ".join(p["where"])) or "—"),
                  "- **Original**: \"%s\"" % _md_escape(p["original"])[:_PLAN_ORIGINAL_MAX]]
        if p.get("source"):
            lines.append("- **Source** (%s:%s): `%s`" % (p["source"]["file"], p["source"]["line"],
                                                        _md_escape(p["source"]["text"])[:_PLAN_ORIGINAL_MAX]))
        if len(groups) > 1:
            lines.append("- **Checks**: %s (%s) — one place, one fix" % (", ".join(p.get("checks") or [p["check"]]),
                                                                        ", ".join(groups)))
        else:
            lines.append("- **Check**: %s (%s)" % (p["check"], p["group"]))
        lines += ["- **Why it is a problem**: %s" % _md_escape(p["why"])[:900],
                  "- **Why not automatic**: %s" % _md_escape(p["why_not_auto"] or "—")]
        if p.get("conflict"):
            lines.append("- **Conflicting suggestions** (a person picks one; none is applied automatically):")
            lines += ["  %d. %s" % (i, _md_escape(s)[:REWRITE_MAX]) for i, s in enumerate(p.get("alternatives") or [], 1)]
        elif p.get("complementary"):
            lines.append("- **Suggested fix — apply all of these** (each changes other words of the sentence):")
            lines += ["  %d. %s" % (i, _md_escape(s)[:REWRITE_MAX]) for i, s in enumerate(p.get("alternatives") or [], 1)]
        else:
            lines.append("- **Suggested fix**: %s" % _md_escape(p["suggestion"])[:REWRITE_MAX])
        if p.get("candidates"):
            lines.append("- **Candidate labels** (closest first; point every place above at the right one): %s"
                         % _md_escape(", ".join(p["candidates"])))
        if p.get("suggestion_basis"):
            lines.append("- **Why the whole sentence**: %s" % _md_escape(p["suggestion_basis"]))
        if p.get("trimmed_from"):
            lines.append("- **Shortened**: the reviewer's wording without its last clause, which says nothing: \"%s\""
                         % _md_escape(p["trimmed_from"])[:400])
        if p.get("source_suggestion"):
            lines.append("- **Suggested source edit**: `%s`" % _md_escape(p["source_suggestion"])[:REWRITE_MAX])
        elif p.get("source") and p.get("suggestion_usable") and p.get("suggestion_check"):
            lines.append("- **Note**: the wording follows the PDF text; carry it over to the source line above by hand%s"
                         % ((" (the script's source edit was left out: %s)" % p["source_suggestion_problem"])
                            if p.get("source_suggestion_problem") else ""))
        if p.get("body_items"):
            lines.append("- **Plan items in the main body**: %s — only cutting words there moves the end of the body; "
                         "a rewording of the same length does not" % ", ".join(p["body_items"]))
        sc = p.get("suggestion_check")
        if sc and not sc.get("delete_only") and p.get("suggestion_usable", True):
            lines.append("- **The suggestion adds words**: %s — check that they state no new fact" % _md_escape(
                " ".join(sc.get("added_words") or [])))
        if p.get("suggestion_problems"):
            lines.append("- **Not usable as written**: \"%s\" — %s" % (_md_escape(p.get("rejected_suggestion"))[:400],
                                                                      _md_escape("; ".join(p["suggestion_problems"]))))
        for r in p.get("rejected_suggestions") or []:
            lines.append("- **Not usable as written** (%s): \"%s\" — %s" % (
                r.get("group"), _md_escape(r.get("suggestion"))[:400], _md_escape("; ".join(r.get("problems") or []))))
        if p.get("manual_places"):
            lines.append("- **Places no clean deletion takes**: %s" % _md_escape("; ".join(p["manual_places"])))
        # a whole-sentence deletion is the fix: the general advice to cut only the fragment would contradict it
        if p.get("advice") and not str(p.get("suggestion") or "").startswith(("Delete the whole sentence",
                                                                              "Delete the narration")):
            lines.append("- **How**: %s" % p["advice"])
        lines.append("")
    if auto:
        lines += ["## Open automatic fixes (`— fix` handles them)", "",
                  "| Id | Class | Severity | Match | Where |", "|---|---|---|---|---|"]
        for p in auto:
            lines.append("| %s | %s | %s | %s | %s |" % (p["id"], p.get("fix_class"), p["severity"],
                                                         _md_escape(p["match"])[:80],
                                                         _md_escape("; ".join(p["where"][:3]))))
        lines.append("")
    return "\n".join(lines) + "\n"


def downgraded_blockers(findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Groups that would block but end INFO: a 'necessary' ruling on a
    candidate whose confirmed level is BLOCK (the reviewer kept it on purpose),
    the verbatim rule with no ruling, or an allow-list exemption of a BLOCK.
    The verdict no longer counts them, so the report names them for a person to
    look at once. A 'false_positive' ruling (not what the check targets) is not
    listed."""
    out: Dict[str, Dict[str, Any]] = {}
    for f in findings:
        if f["severity"] != INFO:
            continue
        why = None
        if f.get("exempted_by") and f.get("original_severity") == BLOCK:
            why = "exempted by %s" % f["exempted_by"]
        elif (f.get("confirm_severity") == BLOCK and f.get("ruling") == "necessary"
              and f.get("demoted") != "region"):  # a compute-section INFO was never a blocker
            why = "ruled %s%s" % (f["ruling"], (": " + f["ruling_rationale"]) if f.get("ruling_rationale") else "")
        elif f.get("confirm_severity") == BLOCK and f.get("demoted") == "verbatim" and not f.get("ruling"):
            why = "typeset verbatim in the sources (not reviewed)"
        elif f.get("ruling") == "necessary_by_policy" and f.get("reviewer_severity") == "blocking":
            why = "a reviewer's blocking finding the venue policy keeps (%s)" % (f.get("note") or "")[-160:]
        if why is None:
            continue
        g = out.setdefault(f["group"], {"group": f["group"], "check": f["check"], "match": f["match"], "n": 0,
                                        "why": why[:240], "where": []})
        g["n"] += 1
        w = _where_str(f)
        if w and w not in g["where"] and len(g["where"]) < 6:
            g["where"].append(w)
    return [out[k] for k in sorted(out)]


def _artifact_rows(scan: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for p in scan.get("inputs", {}).get("pdf", []):
        row = {"path": p.get("path"), "sha256": p.get("sha256"), "pages": p.get("pages")}
        for g in scan.get("page_geometry", []):
            if g.get("artifact") == p.get("path") and g.get("status") == "ok":
                row.update({k: g.get(k) for k in ("body_end_page", "fill", "lines_short")})
        rows.append(row)
    return rows


# ─── Fix-loop memory: snapshots, carried findings, reviewer batches ──────────

_SNAP_SRC_EXTS = (".tex", ".bib", ".sty", ".cls", ".bst", ".cfg", ".def", ".clo", ".ltx")
SUPP_BATCH_MEMBERS = 15
SUPP_BATCH_CHARS = 45000
SUPP_BATCH_MAX = 8
SUPP_CHECKLIST = {
    "engineering": "versions tied to a machine, accelerator or CPU inventories, hosts, servers, private paths, "
                   "commands of a private setup (environment-variable prefixes such as CUDA_VISIBLE_DEVICES=), "
                   "job or run ids, short commit hashes, clock times, worker or shard orchestration",
    "process": "revision, review, or run history: re-runs, rounds, phases, addenda, sealed or superseded plans, fixes, "
               "instructions about the manuscript",
    "dates": "calendar dates and clock times of the authors' own events, seeds shaped like a date",
    "identity": "names, affiliations, e-mails, user or host names, non-anonymous links",
    "unfinished": "work announced but not done: not yet evaluated, to be added, TBD, pending",
    "codenames": "internal project or code names, old or working-copy file names (_old, _now, _tmp), references to "
                 "files or folders the package does not ship",
}


def _safe_rel(rel: str) -> str:
    rel = str(rel).replace("\\", "/").replace("!/", "__in__/")
    parts = []
    for p in rel.split("/"):
        if p in ("", "."):
            continue
        parts.append("__up__" if p == ".." else re.sub(r"[^\w.\-]", "_", p))
    return "/".join(parts) or "_"


def write_snapshot(work_dir: str, paper_dir: str, paper_files: Sequence[str],
                   supp_caps: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Keep the text sources and supplementary text members this fix-round
    scan audited (WORK/snapshots/<id>/), so the change review can diff any
    round against round 0. Written once per content id; the manifest last.
    Each supplement also keeps its complete name list (`listed`, `containers`):
    whether a member is gone is judged from it, never from the members the
    scan budget happened to read."""
    paper: Dict[str, str] = {}
    for p in paper_files:
        with contextlib.suppress(OSError):
            paper[_rel(p, paper_dir)] = _sha256_file(p)
    supp = [{"archive": s.get("archive"), "members": dict(sorted((s["capture"].get("hashes") or {}).items())),
             "listed": dict(sorted((s["capture"].get("listed") or {}).items())),
             "containers": dict(sorted((s["capture"].get("containers") or {}).items()))}
            for s in supp_caps]
    ident = hashlib.sha1(json.dumps({"paper": paper, "supp": supp, "snapshot": 2},
                                    sort_keys=True).encode("utf-8")).hexdigest()[:12]
    sdir = os.path.join(work_dir, "snapshots", ident)
    man_path = os.path.join(sdir, "manifest.json")
    if not os.path.isfile(man_path):
        stored: Dict[str, str] = {}
        for p in paper_files:
            rel = _rel(p, paper_dir)
            if rel not in paper:
                continue
            dst_rel = "paper/" + _safe_rel(rel)
            os.makedirs(os.path.dirname(os.path.join(sdir, dst_rel)), exist_ok=True)
            shutil.copyfile(p, os.path.join(sdir, dst_rel))
            stored[rel] = dst_rel
        for k, s in enumerate(supp_caps):
            texts: Dict[str, str] = {}
            for member, data in sorted((s["capture"].get("texts") or {}).items()):
                dst_rel = "supp%d/%s" % (k, _safe_rel(member))
                os.makedirs(os.path.dirname(os.path.join(sdir, dst_rel)), exist_ok=True)
                with open(os.path.join(sdir, dst_rel), "wb") as fh:
                    fh.write(data)
                texts[member] = dst_rel
            supp[k]["texts"] = texts
        _write_atomic(man_path, json.dumps({"id": ident, "paper": paper, "paper_files": stored, "supp": supp},
                                           ensure_ascii=False) + "\n")
    return {"id": ident, "dir": _rel(sdir, paper_dir), "paper_files": len(paper),
            "supp_members": sum(len(s["members"]) for s in supp)}


def _snapshot_manifest(scan: Dict[str, Any], paper_dir: str) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    s = scan.get("snapshot") or {}
    if not s.get("dir"):
        return None, None
    d = s["dir"] if os.path.isabs(s["dir"]) else os.path.join(paper_dir, s["dir"])
    man = _load_json(os.path.join(d, "manifest.json"))
    return d, (man if isinstance(man, dict) else None)


def carried_findings(state: Dict[str, Any], page_norms: Sequence[Tuple[str, int, str]],
                     supp_norms: Sequence[Tuple[str, str]], supp_artifact: Optional[str] = None
                     ) -> List[Dict[str, Any]]:
    """Reviewer findings of the latest fix round (blocking or advisory) whose
    quotes are still in the text: offered to this run's reviewer (C-NNN) and
    carried by finalize until a ruling clears them with new evidence — a
    finding a fresh reviewer stays silent about never leaves the report."""
    out = []
    for i, rf in enumerate(state.get("reviewer_findings") or [], 1):
        q = _norm_quote(rf.get("quote") or "")
        if len(q) < 8:
            continue
        hit: Optional[Tuple[Any, ...]] = None
        if not rf.get("member"):
            hit = next((("page", art, pg) for art, pg, t in page_norms if q in t), None)
        if hit is None:
            hit = next((("member", m) for m, t in supp_norms if q in t), None)
        if hit is None:
            continue
        lens = {"LENS-ANONYMITY": "anonymity", "LENS-STATEMENTS": "statements"}.get(str(rf.get("check")), "engineering")
        c = {"id": "C-%03d" % i, "check": rf.get("check"), "family": rf.get("family"), "severity": rf.get("severity"),
             "reviewer_severity": rf.get("reviewer_severity"),
             "quote": rf.get("quote"), "lens": lens,
             "rationale": rf.get("rationale"), "rewrite": rf.get("rewrite"), "run": rf.get("run"), "key": rf.get("key"),
             "by": rf.get("by"), "artifact": rf.get("artifact"), "page": None, "member": None}
        if hit[0] == "member":
            c["member"] = hit[1]
            if supp_artifact:  # the supplement this run reads (the clean copy), not the one it was found in
                c["artifact"] = supp_artifact
        else:
            c["artifact"], c["page"] = hit[1], hit[2]
        out.append(c)
    return out


def supp_policy_lines(policy: Optional[Dict[str, Any]]) -> List[str]:
    """The venue policy as a batch reviewer reads it: what the authors keep on
    purpose is no finding (registration labels and orderings, precision,
    reproduction requirements), so a batch never reports what the policy keeps."""
    pol = policy or {}
    reg = str(pol.get("registration_labels") or REGISTRATION_POLICIES[0])
    prec = str(pol.get("precision_disclosure") or PRECISION_POLICIES[0])
    hw = str(pol.get("supp_hardware") or "info").lower()
    out = ["Venue policy (the authors' choices; rule consistently with them):"]
    if reg == "keep":
        out.append("  registration_labels: keep — amendment, addendum, and clarification labels and the ordering "
                   "statements of a registration ('specified before any output') are required disclosures, not "
                   "findings; a date, clock time, host, or path inside them still is one")
    else:
        out.append("  registration_labels: flag — amendment and addendum labels are revision history: report them; "
                   "a rewrite keeps the timing fact and drops the label")
    if prec == "exempt":
        out.append("  precision_disclosure: exempt — numeric precision and weight loading (bf16, fp8, dequantized) "
                   "are method parameters, not findings")
    else:
        out.append("  precision_disclosure: candidate — numeric precision and weight-loading detail are findings "
                   "unless a claim depends on them")
    if hw == "info":
        out.append("  supp_hardware: info — hardware, OS, and host words in these notes are not findings")
    else:
        out.append("  supp_hardware: %s — hardware, OS, and host words that narrate the authors' own runs are "
                   "findings; a stated reproduction requirement is not" % hw)
    return out


def write_supp_batches(work_dir: str, paper_dir: str, supp_docs: Sequence[Tuple[str, str, str]],
                       policy: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Split the supplementary texts the reviewer reads into batches (bounded
    in members and characters, at most SUPP_BATCH_MAX); each batch file opens
    with the category checklist and the venue policy. One fresh reviewer per
    batch."""
    bd = os.path.join(work_dir, "supp_batches")
    if os.path.isdir(bd):
        for fn in os.listdir(bd):
            if re.match(r"^batch_\d+\.txt$", fn):
                with contextlib.suppress(OSError):
                    os.remove(os.path.join(bd, fn))
    if not supp_docs:
        return []
    total = sum(len(t) for _n, _k, t in supp_docs)
    lim_chars = max(SUPP_BATCH_CHARS, -(-total // SUPP_BATCH_MAX))
    lim_members = max(SUPP_BATCH_MEMBERS, -(-len(supp_docs) // SUPP_BATCH_MAX))
    batches: List[List[Tuple[str, str, str]]] = []
    cur: List[Tuple[str, str, str]] = []
    chars = 0
    for d in supp_docs:
        if cur and (len(cur) >= lim_members or chars + len(d[2]) > lim_chars):
            batches.append(cur)
            cur, chars = [], 0
        cur.append(d)
        chars += len(d[2])
    if cur:
        batches.append(cur)
    os.makedirs(bd, exist_ok=True)
    out = []
    for i, b in enumerate(batches, 1):
        names = list(dict.fromkeys(n for n, _k, _t in b))
        body = ["=== supplementary batch %d of %d: %d member(s) ===" % (i, len(batches), len(names)),
                "Check EVERY member below for EVERY category, then list each member in members_checked:"]
        body += ["  %-12s %s" % (k, v) for k, v in SUPP_CHECKLIST.items()]
        body.append("")
        body += supp_policy_lines(policy)
        body.append("")
        for n, k, t in b:
            body += ["%s%s (%s) ===" % (_SUPP_DOC_HEADER, n, k), t, ""]
        fp = os.path.join(bd, "batch_%02d.txt" % i)
        _write_atomic(fp, "\n".join(body) + "\n")
        out.append({"file": _rel(fp, paper_dir), "members": names, "chars": sum(len(t) for _n, _k, t in b)})
    return out


# ─── Conservative fix: every edit since round 0, and the whitelist check ─────

_TOK_RE = re.compile(r"\s+|\w+|[^\w\s]")
_PROSE_SENT_RE = re.compile(r"(?<=[.!?。！？])\s+(?=\S)|\n\s*\n")
EDIT_FRAGMENT_MAX = 1200
EDIT_CONTEXT_MAX = 2000
APPLY_MAX_DELETED_WORDS = 80   # one edit removes a fragment or a sentence, never a paragraph


def _cap(s: str, n: int = EDIT_FRAGMENT_MAX) -> str:
    s = s.strip("\n")
    return s if len(s) <= n else s[:n - 1] + "…"


def _sent_spans(text: str) -> List[Tuple[int, int]]:
    spans, pos = [], 0
    for m in _PROSE_SENT_RE.finditer(text):
        if m.start() > pos:
            spans.append((pos, m.start()))
        pos = m.end()
    if pos < len(text):
        spans.append((pos, len(text)))
    return spans or [(0, len(text))]


def _span_at(spans: List[Tuple[int, int]], pos: int) -> int:
    i = bisect.bisect_right([s for s, _e in spans], pos) - 1
    return max(0, min(i, len(spans) - 1))


def prose_edits(old: str, new: str) -> List[Dict[str, Any]]:
    """Edits between two versions of a prose source: each cluster of changed
    sentences, with one neighbouring sentence on each side in both versions.
    The unshortened fragments stay under `_raw_*` for the whitelist check."""
    import difflib
    ol, nl = old.splitlines(True), new.splitlines(True)
    ost, nst = [0], [0]
    for x in ol:
        ost.append(ost[-1] + len(x))
    for x in nl:
        nst.append(nst[-1] + len(x))
    parts: List[Tuple[int, int, int, int]] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, ol, nl, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        oseg, nseg = "".join(ol[i1:i2]), "".join(nl[j1:j2])
        ot = [(m.start(), m.group(0)) for m in _TOK_RE.finditer(oseg)]
        nt = [(m.start(), m.group(0)) for m in _TOK_RE.finditer(nseg)]
        oo = [p for p, _ in ot] + [len(oseg)]
        no = [p for p, _ in nt] + [len(nseg)]
        sm = difflib.SequenceMatcher(None, [x for _, x in ot], [x for _, x in nt], autojunk=False)
        for t2, a1, a2, b1, b2 in sm.get_opcodes():
            if t2 != "equal":
                parts.append((ost[i1] + oo[a1], ost[i1] + oo[a2], nst[j1] + no[b1], nst[j1] + no[b2]))
    if not parts:
        return []
    osp, nsp = _sent_spans(old), _sent_spans(new)
    clusters: List[List[Any]] = []
    for a0, a1, b0, b1 in parts:
        oi0, oi1 = _span_at(osp, a0), _span_at(osp, max(a0, a1 - 1))
        ni0, ni1 = _span_at(nsp, b0), _span_at(nsp, max(b0, b1 - 1))
        if clusters and (oi0 <= clusters[-1][1] or ni0 <= clusters[-1][3]):
            c = clusters[-1]
            c[0], c[1], c[2], c[3] = min(c[0], oi0), max(c[1], oi1), min(c[2], ni0), max(c[3], ni1)
            c[4].append((a0, a1, b0, b1))
        else:
            clusters.append([oi0, oi1, ni0, ni1, [(a0, a1, b0, b1)]])
    items = []
    for oi0, oi1, ni0, ni1, ps in clusters:
        # The text around the changes is the same in both versions: both fragments
        # take the wider sentence-bounded margin of the two sides, so they hold the
        # same context and differ by the changes alone (a deleted sentence is never
        # paired with the unchanged sentence after it).
        a_first, b_first = ps[0][0], ps[0][2]
        a_last, b_last = max(x[1] for x in ps), max(x[3] for x in ps)
        pre = min(max(a_first - osp[oi0][0], b_first - nsp[ni0][0], 0), a_first, b_first)
        post = min(max(osp[oi1][1] - a_last, nsp[ni1][1] - b_last, 0), len(old) - a_last, len(new) - b_last)
        frag_o, frag_n = old[a_first - pre:a_last + post], new[b_first - pre:b_last + post]
        if _norm_quote(frag_o) == _norm_quote(frag_n):
            continue  # whitespace or line breaks only
        ctx_o = old[osp[max(0, oi0 - 1)][0]:osp[min(len(osp) - 1, oi1 + 1)][1]]
        ctx_n = new[nsp[max(0, ni0 - 1)][0]:nsp[min(len(nsp) - 1, ni1 + 1)][1]]
        items.append({"line": old.count("\n", 0, a_first - pre) + 1, "op": "edit",
                      "before_fragment": _cap(frag_o), "after_fragment": _cap(frag_n),
                      "before": _cap(ctx_o, EDIT_CONTEXT_MAX), "after": _cap(ctx_n, EDIT_CONTEXT_MAX),
                      "_raw_before": frag_o, "_raw_after": frag_n})
    return items


def line_edits(old: str, new: str, code: bool = False, member: str = "") -> List[Dict[str, Any]]:
    """Edits between two versions of a README or code file, by lines, with one
    line of context on each side; for code, whether a line that is not a note
    and nothing else changed (_code_note_lines, by the member's language: a
    template in a triple-quoted string is code)."""
    import difflib
    ol, nl = old.split("\n"), new.split("\n")
    ops = [op for op in difflib.SequenceMatcher(None, ol, nl, autojunk=False).get_opcodes() if op[0] != "equal"]
    clusters: List[List[int]] = []
    for _t, i1, i2, j1, j2 in ops:
        if clusters and i1 - clusters[-1][1] <= 2 and j1 - clusters[-1][3] <= 2:
            clusters[-1][1], clusters[-1][3] = i2, j2
        else:
            clusters.append([i1, i2, j1, j2])
    doc_o = _code_note_lines(old, member) if code else set()
    doc_n = _code_note_lines(new, member) if code else set()

    def narrative(lines: List[str], doc: Set[int], i: int) -> bool:
        return (i + 1) in doc
    items = []
    for i1, i2, j1, j2 in clusters:
        frag_o, frag_n = "\n".join(ol[i1:i2]), "\n".join(nl[j1:j2])
        if _norm_quote(frag_o) == _norm_quote(frag_n):
            continue
        it = {"line": i1 + 1, "op": "edit", "before_fragment": _cap(frag_o), "after_fragment": _cap(frag_n),
              "before": _cap("\n".join(ol[max(0, i1 - 1):min(len(ol), i2 + 1)]), EDIT_CONTEXT_MAX),
              "after": _cap("\n".join(nl[max(0, j1 - 1):min(len(nl), j2 + 1)]), EDIT_CONTEXT_MAX),
              "_raw_before": frag_o, "_raw_after": frag_n}
        if code:
            it["code_logic"] = (any(not narrative(ol, doc_o, i) for i in range(i1, i2))
                                or any(not narrative(nl, doc_n, j) for j in range(j1, j2)))
        items.append(it)
    return items


def _json_diff(a: Any, b: Any, path: str = "", out: Optional[List[str]] = None) -> List[str]:
    out = [] if out is None else out
    if len(out) > 40:
        return out
    if isinstance(a, dict) and isinstance(b, dict):
        out += ["removed key %s%s" % (path, k) for k in a if k not in b]
        out += ["added key %s%s" % (path, k) for k in b if k not in a]
        for k in a:
            if k in b and a[k] != b[k]:
                _json_diff(a[k], b[k], "%s%s." % (path, k), out)
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for x, y in zip(a, b):
            if x != y:
                _json_diff(x, y, path + "[*].", out)
    else:
        out.append("changed value %s" % (path.rstrip(".") or "(whole file)"))
    return out


def data_change_signature(old: str, new: str) -> Tuple[str, ...]:
    """What changed in a data member, without the values: removed or added
    keys and changed values by key path (JSON / JSONL), else the changed lines
    with digits masked."""
    import difflib
    try:
        return tuple(sorted(set(_json_diff(json.loads(old), json.loads(new)))))
    except ValueError:
        pass
    ol = [x for x in old.splitlines() if x.strip()]
    nl = [x for x in new.splitlines() if x.strip()]
    if len(ol) == len(nl):
        try:
            ch: List[str] = []
            for x, y in zip(ol, nl):
                if x != y:
                    _json_diff(json.loads(x), json.loads(y), "", ch)
            return tuple(sorted(set(ch)))
        except ValueError:
            pass
    sig = []
    for t, i1, i2, j1, j2 in difflib.SequenceMatcher(None, ol, nl, autojunk=False).get_opcodes():
        if t != "equal":
            sig += ["- " + re.sub(r"\d", "0", x.strip())[:120] for x in ol[i1:i2]]
            sig += ["+ " + re.sub(r"\d", "0", x.strip())[:120] for x in nl[j1:j2]]
    return tuple(sorted(set(sig)))[:20]


def _edit_fingerprint(it: Dict[str, Any]) -> str:
    raw = "|".join((str(it.get("kind")), str(it.get("op")), str(it.get("file") or it.get("archive") or ""),
                    str(it.get("member") or "") if it.get("op") != "data" else "",
                    _norm_quote(it.get("_raw_before") or it.get("before_fragment") or ""),
                    _norm_quote(it.get("_raw_after") or it.get("after_fragment") or "")))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _snap_text(sdir: str, rel: Optional[str]) -> Optional[str]:
    if not rel:
        return None
    p = os.path.join(sdir, rel)
    if not os.path.isfile(p):
        return None
    with open(p, "rb") as fh:
        return _decode_text(fh.read())[0]


def _member_kind(member: str) -> str:
    low = member.lower()
    if _DOC_RE.search(member):
        return "doc"
    if low.endswith(_DATA_EXTS):
        return "data"
    if _RUNLOG_RE.search(member):
        return "log"
    return "code"


def _is_leave_out_member(member: str) -> bool:
    """Junk, agent working files, and run logs: the only members the loop may leave out."""
    return bool(_JUNK_BLOCK_RE.search(member) or _JUNK_WARN_RE.search(member) or _ARIS_RE.search(member)
                or _RUNLOG_RE.search(member))


UNSCANNED_LIST_MAX = 30


def _member_state(side: Dict[str, Any], key: str, other: Dict[str, Any]) -> str:
    """Whether a member the `other` round holds is in this round's archive:
    'present' (read, or named by its container's directory though the scan
    budget skipped its bytes), 'gone' (the container that held it was listed in
    full here and does not name it, or that container is itself gone), or
    'unknown' (that container was not listed in full: its contents cannot be
    told apart from a removal). A snapshot without name lists (an older one) is
    judged by the members it read, as before."""
    if key in (side.get("members") or {}):
        return "present"
    listed = side.get("listed")
    if listed is None:
        return "gone"
    if key in listed:
        return "present"
    here = side.get("containers") or {}
    there = other.get("containers") or {}
    ckey: Optional[str] = (other.get("listed") or {}).get(key, "")
    seen: Set[str] = set()
    while ckey is not None and ckey not in seen:
        seen.add(ckey)
        rec = here.get(ckey)
        if ckey == "":
            return "gone" if (rec is None or rec.get("opened")) else "unknown"
        if rec is not None:
            return "gone" if rec.get("opened") else "unknown"
        ckey = (there.get(ckey) or {}).get("parent", "")  # the container is not here either: one level up
    return "unknown"


def diff_snapshots(bdir: str, bman: Dict[str, Any], cdir: str, cman: Dict[str, Any]
                   ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Every change between two snapshots (round 0 and now): prose clusters of
    the paper sources, line clusters of supplementary documents and code, data
    members by changed keys, renamed, removed, and added members. A member is
    removed or added only by the archives' complete name lists: one the scan
    budget skipped in either round is listed as not compared (`unreadable`),
    never as left out, so a re-pack that reorders the members cannot make
    one look removed. Returns (items, unreadable). Items are unredacted
    (`_raw_*` too): redact before writing them anywhere."""
    import difflib
    items: List[Dict[str, Any]] = []
    unreadable: List[Dict[str, Any]] = []
    for rel in sorted(set(bman["paper"]) | set(cman["paper"])):
        if bman["paper"].get(rel) == cman["paper"].get(rel):
            continue
        old = _snap_text(bdir, (bman.get("paper_files") or {}).get(rel)) or ""
        new = _snap_text(cdir, (cman.get("paper_files") or {}).get(rel)) or ""
        for it in prose_edits(old, new):
            it.update(kind="paper", file=rel, where="%s:%d" % (rel, it["line"]))
            items.append(it)
    for k in range(max(len(bman["supp"]), len(cman["supp"]))):
        bs = bman["supp"][k] if k < len(bman["supp"]) else {"members": {}, "texts": {}}
        cs = cman["supp"][k] if k < len(cman["supp"]) else {"members": {}, "texts": {}}
        arch = cs.get("archive") or bs.get("archive")
        bm, cm = bs.get("members") or {}, cs.get("members") or {}
        removed = sorted(m for m in bm if m not in cm and _member_state(cs, m, bs) == "gone")
        added = sorted(m for m in cm if m not in bm and _member_state(bs, m, cs) == "gone")
        gone, new_ = set(removed), set(added)
        unscanned = ([(m, "in this round") for m in sorted(bm) if m not in cm and m not in gone]
                     + [(m, "in round 0") for m in sorted(cm) if m not in bm and m not in new_])
        for m, when in unscanned[:UNSCANNED_LIST_MAX]:
            unreadable.append({"member": m, "archive": arch,
                               "why": "beyond the scan budget %s: the archive still holds it (not left out); its "
                                      "content was not compared — check it by hand" % when})
        if len(unscanned) > UNSCANNED_LIST_MAX:
            unreadable.append({"member": "(%d more)" % (len(unscanned) - UNSCANNED_LIST_MAX), "archive": arch,
                               "why": "more members beyond the scan budget, not compared"})
        by_hash: Dict[str, List[str]] = {}
        for m in added:
            by_hash.setdefault(cm[m], []).append(m)
        renamed: List[Tuple[str, str]] = []
        for m in list(removed):
            if by_hash.get(bm[m]):
                new_m = by_hash[bm[m]].pop(0)
                removed.remove(m)
                added.remove(new_m)
                renamed.append((m, new_m))
        old_txt = {m: _snap_text(bdir, (bs.get("texts") or {}).get(m)) for m in removed}
        new_txt = {m: _snap_text(cdir, (cs.get("texts") or {}).get(m)) for m in added}
        edited_renames: List[Tuple[str, str]] = []
        for m in list(removed):
            t0 = old_txt.get(m)
            if t0 is None or len(t0) > 200000 or _is_leave_out_member(m):
                continue
            l0 = t0.splitlines()
            best, best_r = None, 0.0
            for m2 in added:
                t1 = new_txt.get(m2)
                if t1 is None or len(t1) > 200000 or os.path.splitext(m2)[1] != os.path.splitext(m)[1]:
                    continue
                sm = difflib.SequenceMatcher(None, l0, t1.splitlines(), autojunk=False)
                if sm.real_quick_ratio() < 0.6 or sm.quick_ratio() < 0.6:
                    continue
                r = sm.ratio()
                if r > best_r:
                    best, best_r = m2, r
            if best is not None and best_r >= 0.6:
                removed.remove(m)
                added.remove(best)
                edited_renames.append((m, best))
        for m, new_m in renamed + edited_renames:
            items.append({"kind": "supplement", "op": "rename", "member": new_m, "archive": arch, "old_member": m,
                          "where": "%s -> %s" % (m, new_m), "line": None, "before_fragment": m,
                          "after_fragment": new_m, "before": "member %s" % m, "after": "member %s" % new_m})
        for m in removed:
            items.append({"kind": "supplement", "op": "remove", "member": m, "archive": arch, "where": m,
                          "line": None, "before_fragment": "member %s" % m, "after_fragment": "",
                          "before": "member %s is in the upload" % m, "after": "member %s is left out" % m})
        for m in added:
            items.append({"kind": "supplement", "op": "add", "member": m, "archive": arch, "where": m, "line": None,
                          "before_fragment": "", "after_fragment": "member %s" % m,
                          "before": "no member %s" % m, "after": "member %s is added" % m})
        data_groups: Dict[Tuple[str, ...], List[str]] = {}
        for m in sorted(x for x in bm if x in cm and bm[x] != cm[x]):
            old = _snap_text(bdir, (bs.get("texts") or {}).get(m))
            new = _snap_text(cdir, (cs.get("texts") or {}).get(m))
            if old is None or new is None:
                unreadable.append({"member": m, "archive": arch,
                                   "why": "binary, or larger than the snapshot limit: check it by hand"})
                continue
            kind = _member_kind(m)
            if kind in ("data", "log"):
                sig = data_change_signature(old, new)
                if sig:
                    data_groups.setdefault(sig, []).append(m)
                continue
            for it in line_edits(old, new, code=(kind == "code"), member=m):
                it.update(kind="supplement", member=m, archive=arch, member_kind=kind,
                          where="%s:%d" % (m, it["line"]))
                items.append(it)
        for sig, members in sorted(data_groups.items(), key=lambda x: x[1][0]):
            desc = "; ".join(sig[:8]) + (" …" if len(sig) > 8 else "")
            items.append({"kind": "supplement", "op": "data", "member": members[0], "archive": arch,
                          "where": "%s (+%d more data member(s))" % (members[0], len(members) - 1) if len(members) > 1
                          else members[0], "line": None, "members": members[:6], "n_members": len(members),
                          "_all_members": list(members),
                          "before_fragment": desc, "after_fragment": "(values not shown)",
                          "before": "%d data member(s) changed: %s" % (len(members), desc),
                          "after": "values are not shown; the change is described by key path"})
    for it in items:
        it["fingerprint"] = _edit_fingerprint(it)
        it["id"] = "E-" + it["fingerprint"][:8]
    return items, unreadable


# The whitelist check. An edit passes when, after undoing the operations the
# whitelist allows (a verified reference repair, a verified dangling-key drop,
# the content-free metadata lines, a literal \n turned into a space), the words
# it leaves are a subsequence of the words it found (whitespace and punctuation
# ignored) — it only deleted — and the deletion removed a fix-queue match. Any
# word it adds or replaces is a rewrite, and a rewrite is for a person.

_WORDS_RE = re.compile(r"\w+")
_META_CMD_RES = (re.compile(r"\\pdfsuppressptexinfo\s*=?\s*-1(?![\d])"), re.compile(r"\\pdfinfoomitdate\s*=?\s*1(?!\d)"),
                 re.compile(r"\\pdftrailerid\s*\{\s*\}"), re.compile(r"\\pdfgentounicode\s*=?\s*1(?!\d)"),
                 re.compile(r"\\input\s*\{\s*glyphtounicode\s*\}"))
_PDF_FIELD_RE = re.compile(r"\b(pdf(?:author|title|subject|keywords|creator|producer))\s*=\s*"
                           r"(\{(?:[^{}]|\{[^{}]*\})*\}|[^,}\n]*)", re.I)
_EMPTY_HYPERSETUP_RE = re.compile(r"\\hypersetup\s*\{\s*(?:pdf(?:author|title|subject|keywords|creator|producer)\s*="
                                  r"\s*(?:\{\s*\})?\s*,?\s*)*\}", re.I)
_ESC_SRC_RE = re.compile(r"\\textbackslash(?:\{\}|[ \t])?[ntr]|\$\\backslash\$\s?[ntr]")
_REF_CMD_RE = re.compile(r"\\(ref|Ref|cref|Cref|autoref|Autoref|eqref|pageref|nameref|Nameref|vref|Vref|cpageref|"
                         r"Cpageref|labelcref|namecref|nameCref|lcnamecref|zcref|zref|subref|thmref)\*?\s*"
                         r"(?:\[[^\]]*\]\s*)?\{([^{}]*)\}")
_CITE_CMD_RE = re.compile(r"\\((?:[Cc]ite[a-zA-Z]*|[a-z]*cite[a-z]*|nocite|[Pp]arencite|[Tt]extcite|[Aa]utocite|"
                          r"[Ff]ootcite|[Ss]martcite|[Ss]upercite|fullcite))\*?\s*(?:\[[^\]]*\]\s*){0,2}\{([^{}]*)\}")


def _wordlist(s: str) -> List[str]:
    return [w.casefold() for w in _WORDS_RE.findall(s or "")]


def _is_subseq(small: Sequence[str], big: Sequence[str]) -> bool:
    it = iter(big)
    return all(any(w == x for x in it) for w in small)


def _added_words(before_w: Sequence[str], after_w: Sequence[str]) -> List[str]:
    """The words `after_w` holds more often than `before_w`, in their order: a
    word that only moved is not added."""
    extra = Counter(after_w) - Counter(before_w)
    out: List[str] = []
    for w in after_w:
        if extra.get(w, 0) > 0:
            out.append(w)
            extra[w] -= 1
    return out


def _count_occ(words: Sequence[str], anchor: Sequence[str], slack: int = 3) -> int:
    """Non-overlapping occurrences of `anchor` in `words`, in order, each within a
    window of len(anchor) + slack words (markup words such as \\texttt or \\times
    may sit between the words of a PDF match)."""
    if not anchor:
        return 0
    n, i = 0, 0
    while i < len(words):
        if words[i] != anchor[0]:
            i += 1
            continue
        j, k = i + 1, 1
        limit = i + len(anchor) + slack
        while k < len(anchor) and j < min(len(words), limit):
            if words[j] == anchor[k]:
                k += 1
            j += 1
        if k == len(anchor):
            n += 1
            i = j
        else:
            i += 1
    return n


def _meta_fields(text: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for m in _PDF_FIELD_RE.finditer(text or ""):
        out[m.group(1).lower()] = m.group(2).strip().strip("{}").strip()
    return out


def _strip_meta(text: str) -> str:
    """The text without the content-free metadata lines a `meta` fix may add,
    with every PDF metadata field of \\hypersetup emptied."""
    t = text or ""
    for rx in _META_CMD_RES:
        t = rx.sub(" ", t)
    t = _PDF_FIELD_RE.sub(lambda m: m.group(1) + "={}", t)
    return _EMPTY_HYPERSETUP_RE.sub(" ", t)


_META_FIELD_NAMES = ("pdfauthor", "pdftitle", "pdfsubject", "pdfkeywords", "pdfcreator", "pdfproducer")
_HYPERSETUP_RE = re.compile(r"\\hypersetup\s*(?=\{)|\\usepackage\s*(?=\[[^\]]*\bpdf(?:author|title|subject|keywords|"
                            r"creator|producer)\s*=)")


def _meta_settings(text: str) -> List[Tuple[int, int, str]]:
    """(start, end, kind) of every \\hypersetup{…} group and hyperref option
    list that sets PDF metadata fields, outside comments."""
    out = []
    comments = _comment_mask(text)
    for m in _HYPERSETUP_RE.finditer(text):
        if any(a <= m.start() < b for a, b in comments):
            continue
        if m.group(0).startswith("\\hypersetup"):
            _body, end = _balanced_arg(text, m.end())
            if end > m.end():
                out.append((m.start(), end, "hypersetup"))
        else:
            k = text.find("[", m.end())
            close = text.find("]", k)
            if k >= 0 and close > k:
                out.append((m.start(), close + 1, "options"))
    return out


def meta_field_sites(paper_dir: str) -> List[Dict[str, Any]]:
    """Where the sources set PDF metadata fields: for each \\hypersetup (or
    hyperref option list) that sets a field with a value, the in-place edit
    that empties its fields — {file, line, before, after, fields}; the first
    \\hypersetup also takes the metadata fields it does not set yet, empty
    (`added`), so one edit clears every field and no override line follows."""
    out: List[Dict[str, Any]] = []
    try:
        mains = discover_inputs(paper_dir, [], [], False)["mains"]
    except Exception:  # noqa: BLE001
        return out
    seen: Set[str] = set()
    added_done = False
    for main_tex in mains:
        files = []
        with contextlib.suppress(Exception):
            files = expand_tex(main_tex, paper_dir)["files"]
        for path in files:
            rel = _rel(path, paper_dir)
            if rel in seen or not os.path.isfile(path):
                continue
            seen.add(rel)
            with open(path, "rb") as fh:
                text, enc = _decode_text(fh.read())
            if enc not in ("utf-8", "utf-8-sig", "gb18030"):
                continue
            for s, e, kind in _meta_settings(text):
                before = text[s:e]
                filled = [m.group(1).lower() for m in _PDF_FIELD_RE.finditer(before)
                          if m.group(2).strip().strip("{}").strip()]
                if not filled:
                    continue
                after = _PDF_FIELD_RE.sub(lambda m: m.group(1) + "={}", before)
                if text.count(before) != 1:
                    continue
                site = {"file": rel, "line": text.count("\n", 0, s) + 1, "before": before, "after": after,
                        "fields": sorted(set(filled))}
                present = {m.group(1).lower() for m in _PDF_FIELD_RE.finditer(before)}
                missing = [x for x in _META_FIELD_NAMES if x not in present]
                if kind == "hypersetup" and missing and not added_done and after.endswith("}"):
                    body = after[:-1].rstrip()
                    site["after"] = body + ("" if body.endswith(("{", ",")) else ",") + ",".join(
                        "%s={}" % x for x in missing) + "}"
                    site["added"], added_done = missing, True
                out.append(site)
    return out


def _identity_fields_left(text: str, red: Optional[Redactor]) -> List[str]:
    """Metadata fields a file still sets with an identifying value — an author
    (whatever line empties it later: the sources keep it), or any field that
    holds an identity term — outside comments."""
    out: Set[str] = set()
    for s, e, _kind in _meta_settings(text):
        for m in _PDF_FIELD_RE.finditer(text[s:e]):
            name, value = m.group(1).lower(), m.group(2).strip().strip("{}").strip()
            if value and (name == "pdfauthor" or (red is not None and red.redact(value) != value)):
                out.add(name)
    return sorted(out)


class EditCheck:
    """What the whitelist check needs: the labels and bibliography keys the
    sources define now, label kinds, the redactor, and the fix-queue anchors
    (the matches a deletion must remove) as (fix_class, words)."""

    def __init__(self, labels: Iterable[str] = (), types: Optional[Dict[str, str]] = None,
                 keys: Iterable[str] = (), bib_known: bool = False, red: Optional[Redactor] = None,
                 anchors: Iterable[Tuple[str, Sequence[str]]] = ()):
        self.labels = set(labels)
        self.types = dict(types or {})
        self.keys = set(keys)
        self.bib_known = bib_known
        self.red = red or Redactor()
        self.anchors = [(c, list(w)) for c, w in anchors if w]


def _align_replace(a: Sequence[Any], b: Sequence[Any]) -> List[Tuple[int, int]]:
    """Index pairs that a 1:1 'replace' of difflib aligns (equal-length blocks)."""
    import difflib
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, list(a), list(b), autojunk=False).get_opcodes():
        if tag == "replace" and i2 - i1 == j2 - j1:
            out += [(i1 + k, j1 + k) for k in range(i2 - i1)]
    return out


def _check_ref_repair(old: str, new: str, text_before: str, command: str, ec: EditCheck,
                      target: Optional[str]) -> Tuple[bool, str]:
    import difflib
    if target is not None and new != target:
        return False, "points the reference at %s, not at the label the script named" % new
    if new not in ec.labels:
        return False, "the new label %s is not defined" % new
    if old in ec.labels:
        return False, "the old label %s is still defined: it was no broken reference" % old
    kind_old = label_prefix_type(old) or ref_context_type(text_before, command)
    kind_new = ec.types.get(new) or label_prefix_type(new)
    if not kind_old or not kind_new:
        return False, "the kind of reference cannot be told (no prefix, no context word, no .aux type)"
    if kind_old != kind_new:
        return False, "a %s reference was pointed at a %s label" % (kind_old, kind_new)
    if difflib.SequenceMatcher(None, old, new).ratio() < 0.6:
        return False, "the new label is not close to the old key (a misspelling or rename is)"
    return True, "verified: an existing %s label close to the old key" % kind_new


def _normalize_refs(before: str, after: str, ec: EditCheck,
                    target: Optional[str] = None) -> Tuple[str, List[Dict[str, Any]], Optional[str]]:
    """`after` with every verified reference repair turned back into the old key,
    the repairs, and the first problem."""
    bm, am = list(_REF_CMD_RE.finditer(before)), list(_REF_CMD_RE.finditer(after))
    bk = [tuple(_split_keys(m.group(2))) for m in bm]
    ak = [tuple(_split_keys(m.group(2))) for m in am]
    changes: List[Dict[str, Any]] = []
    repl: List[Tuple[int, str]] = []
    for i, j in _align_replace(bk, ak):
        if len(bk[i]) != len(ak[j]):
            return after, changes, "a reference gained or lost keys"
        for old, new in zip(bk[i], ak[j]):
            if old == new:
                continue
            ok, why = _check_ref_repair(old, new, before[:bm[i].start()], bm[i].group(1), ec, target)
            changes.append({"old": old, "new": new, "ok": ok, "why": why})
            if not ok:
                return after, changes, why
        repl.append((j, bm[i].group(2)))
    out, pos = [], 0
    for j, arg in sorted(repl):
        out += [after[pos:am[j].start(2)], arg]
        pos = am[j].end(2)
    out.append(after[pos:])
    return "".join(out), changes, None


def _cite_problem(before: str, after: str, ec: EditCheck) -> Tuple[List[str], Optional[str]]:
    """Dropped citation keys and the first problem: a dropped key that has a
    bibliography entry (a citation is never removed), or a \\cite left empty."""
    from collections import Counter as _C
    bk = _C(k for m in _CITE_CMD_RE.finditer(before) for k in _split_keys(m.group(2)))
    ak = _C(k for m in _CITE_CMD_RE.finditer(after) for k in _split_keys(m.group(2)))
    dropped = sorted((bk - ak).elements())
    if not dropped:
        return [], None
    real = [k for k in dropped if k in ec.keys]
    if real:
        return dropped, "removes the citation %s, which has a bibliography entry" % ", ".join(real[:3])
    if not ec.bib_known:
        return dropped, "no bibliography to check that the dropped key resolves to nothing"
    for m in _CITE_CMD_RE.finditer(after):
        if not _split_keys(m.group(2)):
            return dropped, "a \\cite was left without keys"
    if len(list(_CITE_CMD_RE.finditer(before))) > len(list(_CITE_CMD_RE.finditer(after))):
        return dropped, "a whole \\cite was removed (a single-key citation is for a person)"
    return dropped, None


def verify_change(before: str, after: str, ec: EditCheck, kind: str = "paper", code_logic: bool = False,
                  target: Optional[str] = None, anchors: Optional[Sequence[Tuple[str, Sequence[str]]]] = None
                  ) -> Dict[str, Any]:
    """The whitelist verdict on one change of text: {'verdict': ok|rejected,
    'class': ..., 'why': ...}. `anchors` (default: the EditCheck's) are the
    fix-queue matches one of which the deletion must remove."""
    red = ec.red
    b, a = red.redact(before or ""), red.redact(after or "")
    classes: List[str] = []
    if kind == "supplement" and code_logic:
        return {"verdict": "rejected", "class": None, "why": "a code line changed (the loop edits notes only)"}
    if kind == "paper":
        bf, af = _meta_fields(b), _meta_fields(a)
        for field, val in af.items():
            if val and val != bf.get(field, ""):
                return {"verdict": "rejected", "class": None, "why": "the metadata field %s got a new value" % field}
        # a field that keeps its value and is emptied again by a later line: the value stays in the sources
        pairs = [(m.group(1).lower(), m.group(2).strip().strip("{}").strip()) for m in _PDF_FIELD_RE.finditer(a)]
        twice = sorted({k_ for k_, v_ in pairs if v_} & {k_ for k_, v_ in pairs if not v_})
        if twice:
            return {"verdict": "rejected", "class": None,
                    "why": "the metadata field %s keeps its value and gets an empty override after it: empty the "
                           "field where it is set" % ", ".join(twice)}
        bs, as_ = _strip_meta(b), _strip_meta(a)
        if (len(_wordlist(a)) - len(_wordlist(as_)) > len(_wordlist(b)) - len(_wordlist(bs))
                or any(bf.get(k_) and not af.get(k_) for k_ in bf)):
            classes.append("meta")  # metadata lines added, or metadata fields emptied
        b, a = bs, as_
        a2, refs, problem = _normalize_refs(b, a, ec, target)
        if problem:
            return {"verdict": "rejected", "class": "xref-ref", "why": problem}
        if refs:
            classes.append("xref-ref")
        a = a2
        dropped, problem = _cite_problem(b, a, ec)
        if problem:
            return {"verdict": "rejected", "class": "xref-cite", "why": problem}
        if dropped:
            classes.append("xref-cite")
    else:
        dropped = []
    wb, wa = _wordlist(b), _wordlist(a)
    if wa == wb:
        return {"verdict": "ok", "class": "+".join(classes) or "format",
                "why": "no word added or removed" if not classes else "verified %s" % ", ".join(classes)}
    if not _is_subseq(wa, wb):
        we = _wordlist(_ESC_SRC_RE.sub(" ", b)) if kind == "paper" else wb
        if we != wb and _is_subseq(wa, we) and not _is_subseq(wa, wb):
            classes.append("escape")
            wb = we
        else:
            added = _added_words(wb, wa)
            return {"verdict": "rejected", "class": None,
                    "why": "adds or replaces words: %s" % " ".join(added[:12]) if added else "reorders words"}
    if wa == wb:
        return {"verdict": "ok", "class": "+".join(classes), "why": "verified %s" % ", ".join(classes)}
    # a deletion: it must remove a fix-queue match (and stay within a sentence or two)
    n_del = len(wb) - len(wa)
    use = ec.anchors if anchors is None else [(c, list(w)) for c, w in anchors if w]
    if "xref-cite" in classes and n_del == sum(len(_wordlist(k_)) for k_ in dropped):
        return {"verdict": "ok", "class": "+".join(classes), "why": "verified %s" % ", ".join(classes)}
    hit = next((c for c, w in use if _count_occ(wb, w) > _count_occ(wa, w)), None)
    if hit is None:
        return {"verdict": "rejected", "class": "delete",
                "why": "a deletion no fix-queue item asked for (it removes no queued match)"}
    if n_del > APPLY_MAX_DELETED_WORDS:
        return {"verdict": "rejected", "class": "delete",
                "why": "deletes %d words: more than a fragment or a sentence" % n_del}
    cls = {"marker": "marker", "supp-delete": "supp-delete", "delete-sentence": "delete-sentence"}.get(hit, "delete")
    if kind == "supplement":
        cls = "supp-delete"
    residue = deletion_residue(b, a)
    if residue:
        # what is left must read as text: no stray mark, no word left without what it introduced
        return {"verdict": "rejected", "class": cls, "residue": residue,
                "why": "the deletion leaves residue: %s" % "; ".join(residue[:3])}
    return {"verdict": "ok", "class": "+".join(classes + [cls]), "why": "deletes a queued match (%s)" % hit}


def verify_edit(item: Dict[str, Any], ec: EditCheck) -> Dict[str, Any]:
    """The whitelist verdict on one item of diff_snapshots()."""
    op, kind = item.get("op"), item.get("kind")
    if kind == "supplement":
        m = str(item.get("member") or "")
        if op == "remove":
            if _is_leave_out_member(m):
                return {"verdict": "ok", "class": "supp-remove", "why": "junk, an agent file, or a run log"}
            return {"verdict": "rejected", "class": None,
                    "why": "a member was left out: only junk, agent files, and run logs may be"}
        if op in ("rename", "add"):
            return {"verdict": "rejected", "class": None,
                    "why": "a member was %s: renames and new files are for a person" % (
                        "renamed" if op == "rename" else "added")}
        if op == "data":
            return {"verdict": "rejected", "class": None, "why": "a data member changed: values are never edited"}
        return verify_change(item.get("_raw_before") or "", item.get("_raw_after") or "", ec, "supplement",
                             bool(item.get("code_logic")))
    return verify_change(item.get("_raw_before") or "", item.get("_raw_after") or "", ec, "paper")


FIX_HISTORY_NAME = "fix_history.json"   # every fix-queue item of the run (the anchors of later checks)
DRAFT_RECORD_NAME = "draft_record.json"  # the items `edits --from-queue` last drafted (what apply was then given)


def _discarded_keys(work_dir: Optional[str], run_mode: str, fix_round: Optional[int],
                    applied: Sequence[Tuple[int, str, Dict[str, Any]]]) -> Dict[str, str]:
    """Stable keys of the items `edits --from-queue` drafted for a round that
    `apply` never saw in that round — the executor dropped the draft: the item
    is kept for a person (the plan says so) and no later round drafts it again.
    Read by the finalize of that round (fix) and by the recheck."""
    if not work_dir or run_mode not in ("fix", "recheck"):
        return {}
    rec = _load_json(os.path.join(work_dir, DRAFT_RECORD_NAME))
    if not isinstance(rec, dict) or not isinstance(rec.get("drafted_from_round"), int):
        return {}
    rnd = rec["drafted_from_round"] + 1
    if run_mode == "fix" and (fix_round or 0) != rnd:
        return {}
    seen = [r for rn, _p, d in applied if rn == rnd for r in list(d.get("applied") or []) + list(d.get("rejected") or [])]
    keys = {r.get("key") for r in seen if r.get("key")}
    groups = {r.get("group") for r in seen if r.get("group")}
    out: Dict[str, str] = {}
    for it in rec.get("items") or []:
        k = it.get("key")
        if k and k not in keys and it.get("group") not in groups:
            out[k] = ("drafted for round %d and never given to apply: the executor kept it for a person (no later "
                      "round drafts it again)" % rnd)
    return out


def _item_anchors(g: Dict[str, Any]) -> List[str]:
    """The texts a deletion for this queue item must remove: what each
    occurrence matched (`anchors`), else the match itself."""
    return [str(x) for x in (g.get("anchors") or []) if x] or [str(g.get("match") or "")]


def _queue_anchors(items: Iterable[Dict[str, Any]], red: Optional[Redactor] = None) -> List[Tuple[str, List[str]]]:
    out = []
    for g in items:
        cls = g.get("fix_class")
        if cls in ("delete", "delete-sentence", "marker", "supp-delete"):
            for text in _item_anchors(g):
                words = _wordlist(text)
                if words:
                    out.append((cls, words))
    return out


def edit_check_for(srcs: Iterable[Dict[str, Any]], red: Redactor, history: Optional[Dict[str, Any]]) -> EditCheck:
    labels: Set[str] = set()
    types: Dict[str, str] = {}
    keys: Set[str] = set()
    bib_known = False
    for s in srcs:
        x = s.get("xref") or {}
        labels |= set(x.get("defined_labels") or [])
        keys |= set(x.get("defined_keys") or [])
        bib_known = bib_known or bool(x.get("bib_known"))
        types.update(s.get("label_types") or {})
    items = list(((history or {}).get("items") or {}).values()) if isinstance((history or {}).get("items"), dict) \
        else list((history or {}).get("items") or [])
    return EditCheck(labels, types, keys, bib_known, red, _queue_anchors(items))


def check_edits(items: List[Dict[str, Any]], ec: EditCheck, red: Redactor) -> Dict[str, Any]:
    """Verdicts for every edit since round 0 (redacted for the report), and the
    unredacted before/after of each (WORK only: `apply --undo` restores them)."""
    out_items, raw = [], {}

    def red_any(v_: Any) -> Any:
        if isinstance(v_, str):
            return red.redact(v_)
        if isinstance(v_, list):
            return [red.redact(x) if isinstance(x, str) else x for x in v_]
        return v_
    for it in items:
        v = verify_edit(it, ec)
        pub = {k: red_any(v_) for k, v_ in it.items() if not k.startswith("_") and k not in ("before", "after")}
        pub.update(verdict=v["verdict"], fix_class=v.get("class"), why=v["why"])
        out_items.append(pub)
        raw[it["id"]] = {"kind": it.get("kind"), "op": it.get("op"), "file": it.get("file"),
                         "member": it.get("member"), "archive": it.get("archive"),
                         "before": it.get("_raw_before"), "after": it.get("_raw_after")}
        if it.get("old_member"):
            raw[it["id"]]["old_member"] = it["old_member"]
        if it.get("_all_members"):
            raw[it["id"]]["members"] = it["_all_members"]
    rejected = [x for x in out_items if x["verdict"] != "ok"]
    return {"total": len(out_items), "ok": len(out_items) - len(rejected), "rejected": len(rejected),
            "items": out_items, "_raw": raw}


def _removed_phrases(before: str, after: str) -> List[str]:
    """Runs of at least three words a deletion removed (de-TeXed), for the
    supplement copy of the same phrase."""
    import difflib
    bw, aw = _detex_line(before or "").split(), _detex_line(after or "").split()
    out = []
    for tag, i1, i2, _j1, _j2 in difflib.SequenceMatcher(None, bw, aw, autojunk=False).get_opcodes():
        if tag in ("delete", "replace") and i2 - i1 >= 3:
            phrase = " ".join(bw[i1:i2]).strip(" ,;:.")
            if len(phrase) >= 12 and re.search(r"[A-Za-z]{3}", phrase):
                out.append(phrase)
    return out[:6]


def fix_edit_findings(check: Dict[str, Any], ctx: ScanContext) -> List[Dict[str, Any]]:
    out = []
    for it in check.get("items") or []:
        if it.get("verdict") == "ok":
            continue
        loc = {"artifact": it.get("archive"), "file": it.get("file"), "line": it.get("line"),
               "member": it.get("member")}
        f = make_finding(ctx, "FIX-EDIT", BLOCK, DEFINITE, "edit", "%s (%s)" % (it.get("why"), it.get("id")),
                         "before: %s | after: %s" % (str(it.get("before_fragment") or "")[:180],
                                                    str(it.get("after_fragment") or "")[:180]), loc)
        f["edit_id"] = it.get("id")
        out.append(f)
    return out


# ─── apply / undo / restore (the only way `— fix` changes a file) ────────────

APPLIED_NAME = "applied.r%d.json"


def _redactor_from_config(config_dir: str, anonymous: bool = True) -> Redactor:
    cfg = load_config(config_dir)
    identity = TermMatcher(cfg["identity_terms"] if anonymous else [])
    auto = TermMatcher([(str(i), t_) for i, t_ in enumerate(auto_identity_terms() if anonymous else [], 1)])
    deny = TermMatcher([(str(i), t_) for i, t_ in enumerate(cfg["policy"].get("extra_deny") or [], 1)])
    return Redactor(identity, auto, deny)


def _paper_sources(paper_dir: str) -> List[Dict[str, Any]]:
    out = []
    for main in discover_inputs(paper_dir, [], [], False)["mains"]:
        with contextlib.suppress(Exception):
            out.append(_load_sources(main, paper_dir, ScanContext(), {}))
    return out


def _applied_logs(work_dir: str) -> List[Tuple[int, str, Dict[str, Any]]]:
    out = []
    if os.path.isdir(work_dir):
        for fn in sorted(os.listdir(work_dir)):
            m = re.match(r"^applied\.r(\d+)\.json$", fn)
            if m:
                d = _load_json(os.path.join(work_dir, fn))
                if isinstance(d, dict):
                    out.append((int(m.group(1)), os.path.join(work_dir, fn), d))
    return sorted(out)


def _fix_log_row(rnd: int, rec: Dict[str, Any], red: Redactor) -> str:
    def cell(s: Any) -> str:
        return red.redact(_collapse_ws(str(s or "")))[:160].replace("|", "\\|") or "—"
    return "| %d | %s | %s | %s | %s | %s | %s |" % (rnd, rec.get("id"), rec.get("group"), rec.get("class"),
                                                     cell(rec.get("file") or rec.get("member")),
                                                     cell(rec.get("before")), cell(rec.get("after")))


FIX_LOG_HEADER = "| round | id | group | class | where | before | after |\n|---|---|---|---|---|---|---|\n"


def parse_fix_log(text: str) -> List[Dict[str, Any]]:
    """FIX_LOG.md rows as `apply` writes them: | round | id | group | class | where | before | after |."""
    rows = []
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", s.strip("|"))]
        if len(cells) < 7 or not re.match(r"^\d+$", cells[0]):
            continue
        rows.append({"round": int(cells[0]), "id": cells[1], "group": cells[2], "class": cells[3],
                     "where": cells[4], "before": cells[5], "after": " | ".join(cells[6:])})
    return rows


def _within(base: str, rel: str) -> Optional[str]:
    if not rel or os.path.isabs(rel) or ".." in rel.replace("\\", "/").split("/"):
        return None
    full = os.path.abspath(os.path.join(base, rel))
    return full if _is_within(full, base) else None


def run_apply(a: Any) -> Tuple[Dict[str, Any], int]:
    """Apply the executor's proposed edits for the fix queue, each checked
    against the whitelist first; an edit that fails is never applied. With
    --undo, put back applied edits (by id) or rejected edits the scan listed."""
    paper_dir = os.path.abspath(a.paper_dir)
    work_dir = os.path.abspath(a.work_dir)
    stage = os.path.abspath(a.supp_stage) if a.supp_stage else os.path.join(work_dir, "supp_stage")
    rnd = int(a.round)
    if getattr(a, "stage_only", False):
        # the staged copy alone (a round whose supplement items need no text edit: a re-pack,
        # members to leave out): made once from round 0's supplement, never from the user's files
        if os.path.isdir(stage):
            return {"tool": TOOL, "command": "apply", "round": rnd,
                    "staged": {"stage": _display_path(stage, paper_dir), "exists": True}}, 0
        src, why = _create_stage(stage, work_dir, paper_dir)
        staged = ({"stage": _display_path(stage, paper_dir), "from": _display_path(src, paper_dir)} if src else
                  {"stage": None, "why": why})
        return {"tool": TOOL, "command": "apply", "round": rnd, "staged": staged}, (0 if src else 1)
    log_path = os.path.join(work_dir, APPLIED_NAME % rnd)
    log = _load_json(log_path) or {"round": rnd, "applied": [], "rejected": [], "undone": []}
    audit_path = a.audit or os.path.join(paper_dir, "PAPER_HYGIENE_AUDIT.json")
    audit = _load_json(audit_path)
    if not isinstance(audit, dict) or audit.get("audit_skill") != SKILL_NAME:
        raise UsageError("cannot read the audit artifact %s (run finalize first)" % audit_path)
    det = audit.get("details") or {}
    red = _redactor_from_config(a.config_dir, bool(det.get("anonymous", True)))
    backup = os.path.join(work_dir, "backup_r%d" % rnd)

    def keep_copy(full: str, rel: str) -> None:
        dst = os.path.join(backup, _safe_rel(rel))
        if os.path.isfile(full) and not os.path.isfile(dst):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(full, dst)

    if a.undo:
        return _run_undo(a, paper_dir, work_dir, stage, rnd, log, log_path, red, keep_copy)
    proposals = _load_json(a.edits)
    if not isinstance(proposals, dict) or not isinstance(proposals.get("edits"), list):
        raise UsageError("--edits must hold {\"edits\": [...]} (group, file or member, before, after)")
    queue = {g["group"]: g for g in det.get("fix_queue") or [] if isinstance(g, dict) and g.get("group")}
    ec = edit_check_for(_paper_sources(paper_dir), red, None)
    new: List[Dict[str, Any]] = []
    rej: List[Dict[str, Any]] = []
    fix_log = []
    staged: Dict[str, Any] = {}
    # the staged copy is made for the first supplement edit, and for a queue whose
    # supplement items need none (a re-pack): `repack` then has a stage to pack
    if not os.path.isdir(stage) and (
            any(isinstance(e, dict) and e.get("member") for e in proposals["edits"])
            or any(g.get("fix_class") in ("supp-delete", "supp-remove", "repack") for g in queue.values())):
        src, why = _create_stage(stage, work_dir, paper_dir)
        staged = {"stage": _display_path(stage, paper_dir), "from": _display_path(src, paper_dir)} if src else \
            {"stage": None, "why": why}
    edits = [e for e in proposals["edits"] if isinstance(e, dict)]
    # metadata fields are emptied where they are set before any line is added: a line added first would
    # be refused while the old value still stands
    edits.sort(key=lambda e: 0 if (str(e.get("group")) == "META" and _PDF_FIELD_RE.search(str(e.get("before") or "")))
               else 1)
    for e in edits:
        res = _apply_one(e, queue, ec, paper_dir, stage, work_dir, rnd, keep_copy, det)
        if res.get("verdict") == "ok":
            res["id"] = "A%d-%03d" % (rnd, len(log["applied"]) + 1)
            log["applied"].append(res)
            new.append(res)
            fix_log.append(_fix_log_row(rnd, res, red))
        else:
            log["rejected"].append(res)
            rej.append(res)
    # after the round's edits, a sentence several deletions left as a skeleton goes as a whole
    for res in _round_skeleton_pass(log, queue, ec, paper_dir, work_dir, rnd, det):
        res["id"] = "A%d-%03d" % (rnd, len(log["applied"]) + 1)
        log["applied"].append(res)
        new.append(res)
        fix_log.append(_fix_log_row(rnd, res, red))
    _write_atomic(log_path, json.dumps(log, ensure_ascii=False, indent=1) + "\n")
    if fix_log:
        fl = os.path.join(work_dir, "FIX_LOG.md")
        old = _read_text(fl) if os.path.isfile(fl) else FIX_LOG_HEADER
        _write_atomic(fl, old.rstrip("\n") + "\n" + "\n".join(fix_log) + "\n")

    def pub(r: Dict[str, Any]) -> Dict[str, Any]:
        return {k: (red.redact(str(v)) if isinstance(v, str) else v) for k, v in r.items()
                if k not in ("before", "after", "left", "right")}
    doc = {"tool": TOOL, "command": "apply", "round": rnd, "applied": [pub(r) for r in new],
           "rejected": [pub(r) for r in rej], "log": _display_path(log_path, paper_dir),
           "files_changed": sorted({r.get("file") or ("supp:" + str(r.get("member"))) for r in new})}
    if staged:
        doc["staged"] = staged
    return doc, (1 if rej else 0)


def _create_stage(stage: str, work_dir: str, paper_dir: str) -> Tuple[Optional[str], Optional[str]]:
    """The staged supplement copy that supplement edits change, made once from
    round 0's supplement: its archive copy (WORK/rounds/) extracted, or its
    directory copied. Links, devices, and members that would land outside the
    stage are left out. Returns (source, None) or (None, why)."""
    rounds = (_load_json(os.path.join(work_dir, ROUNDS_NAME)) or {}).get("rounds") or []
    rec = next((r for r in rounds if isinstance(r, dict) and r.get("round") == 0), None)
    supps = (rec or {}).get("supplements") or []
    if len(supps) != 1:
        return None, ("no round-0 supplement: run the round-0 scan and finalize with --work-dir first" if not supps
                      else "%d supplements: stage each one yourself and pass --supp-stage" % len(supps))
    path = str(supps[0].get("path") or "")
    full = path if os.path.isabs(path) else os.path.join(paper_dir, path)
    copy = os.path.join(work_dir, supps[0]["copy"]) if supps[0].get("copy") else ""
    tmp = stage + ".part"
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        if copy and os.path.isfile(copy):
            src = copy
            if zipfile.is_zipfile(copy):
                with zipfile.ZipFile(copy) as zf:
                    for zi in zf.infolist():
                        dst = _within(tmp, zi.filename.rstrip("/"))
                        if zi.is_dir() or not dst or (zi.external_attr >> 16) & 0o170000 == 0o120000:
                            continue
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        with zf.open(zi) as fin, open(dst, "wb") as fout:
                            shutil.copyfileobj(fin, fout)
            else:
                with tarfile.open(copy, "r:*") as tf:
                    for ti in tf:
                        dst = _within(tmp, ti.name)
                        fin = tf.extractfile(ti) if ti.isfile() and dst else None
                        if fin is None:
                            continue
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        with fin, open(dst, "wb") as fout:
                            shutil.copyfileobj(fin, fout)
        elif os.path.isdir(full):
            src = full
            shutil.copytree(full, tmp, symlinks=True)
        else:
            return None, "the round-0 supplement %s is gone" % _display_path(full, paper_dir)
        os.makedirs(tmp, exist_ok=True)
        os.replace(tmp, stage)
    except (OSError, zipfile.BadZipFile, tarfile.TarError, zlib.error, lzma.LZMAError, EOFError, RuntimeError) as e:
        shutil.rmtree(tmp, ignore_errors=True)
        return None, "cannot stage the supplement: %s" % e
    return src, None


# ─── Skeleton sentences: what a deletion must not leave behind ───────────────
# After a leak fragment is deleted, the rest of its sentence may say nothing a
# reader needs: only the leak's own family (framework or library names,
# hardware, a host, a bare run time), only generic words ("To reproduce, call
# the scripts."), or a bare predicate ("… are stored."). Then the whole
# sentence goes — still a pure deletion — in `apply` and in the plan's advice.

_SKELETON_GENERIC = frozenset("""
a an the this that these those it its they them their there here we our us i you he she one ones
is are was were be been being has have had do does did done will would can could may might shall should must
of in on at by for with from to into onto via per as and or nor but so then also both all each every any some
about around approximately roughly nearly almost under over less more than up just only further additionally
which who whom whose what where when while once
implement implements implemented implementing run runs ran running launch launches launched launching
execute executes executed executing use uses used using call calls called calling store stores stored storing
keep keeps kept keeping save saves saved saving place placed host hosted locate located write writes written
conduct conducted perform performed take takes took taken taking reproduce reproduces reproduced reproducing
see refer follow follows followed following find found provide provides provided make makes made
experiment experiments script scripts code codes command commands file files log logs output outputs job jobs
result results setup environment system systems machine machines server servers node nodes software hardware
framework frameworks library libraries toolkit toolkits tool tools package packages instruction instructions
step steps detail details everything thing things
second seconds sec secs minute minutes min mins hour hours hr hrs day days week weeks
""".split())
_SKELETON_LIBS_RE = re.compile(r"(?<![\w-])(?:" + _STRONG_LIBS + r"|" + _WEAK_LIBS + r")(?![\w-])", re.I | _A)
_RUNTIME_PRED_RE = re.compile(
    r"\b(?:takes?|took|taking|requires?|required|needs?|needed|lasts?|lasted|runs?|ran|completes?|completed)\s+"
    r"(?:about|around|approximately|roughly|nearly|under|over|less\s+than|more\s+than|at\s+most|at\s+least|~)?\s*"
    r"\d[\d.,]*\s*(?:(?:-|–|to)\s*\d[\d.,]*\s*)?(?:s|sec|secs|seconds?|min|mins|minutes?|h|hrs?|hours?|days?|"
    r"weeks?|(?:GPU|CPU|TPU|node)[- ](?:hours?|days?))\b", re.I | _A)
_COMPARE_RE = re.compile(r"\b(?:faster|slower|than|speed-?ups?|compared|versus|vs|fewer|cheaper|reduc\w*|improv\w*|"
                         r"outperform\w*)\b|[%×]", re.I | _A)
_BARE_PRED_RE = re.compile(r"\b(?:is|are|was|were|be|been)\s+(?:stored|kept|saved|located|placed|hosted|run|"
                           r"launched|executed|done|performed|conducted|implemented|written)\s*[.;:!]?\s*$", re.I | _A)
_NOTE_MARK_RE = re.compile(r"(?m)^\s*(?:#+|//|%+|\*+|-{1,2}|>|;)\s?")
_SKELETON_STRIP = (_FW_RE, _HW_RE, _QTY_RE, _SKELETON_LIBS_RE, _OPS_C_RE, _PATH_RE, _HOST_SUFFIX_RE, _IPV4_RE)
# a generic instruction: an optional purpose clause, then "call / run the scripts (from there)"
_GENERIC_INSTRUCTION_RE = re.compile(
    r"(?:(?:to|in\s+order\s+to)\s+(?:reproduce|replicate|rerun|re-run|run|repeat)(?:\s+(?:it|this|them|the\s+"
    r"(?:results?|runs?|experiments?|analysis|analyses)))?(?:\s+(?:on|from|in)\s+(?:the\s+)?[\w-]+(?:\s+[\w-]+)?)?"
    r"\s*[,:]?\s*)?(?:(?:first|then|next|finally)\s*,?\s+)?(?:(?:change\s+(?:the\s+)?(?:working\s+)?directory|cd)"
    r"\s*(?:,\s*|\s+)(?:and|then)\s+)?(?:(?:and|then)\s+)?(?:call|run|execute|invoke|launch|start|use)\s+(?:the\s+|all\s+"
    r"(?:the\s+)?|these\s+|our\s+)?(?:scripts?|code|commands?|programs?|pipeline|notebooks?)(?:\s+(?:from|in)\s+"
    r"(?:there|here|that\s+directory|the\s+(?:same\s+)?(?:directory|folder)))?\s*[.;!]?", re.I | _A)
# what a supplementary note may hold beside its leak and still say nothing: a host, an account, how to get
# there, and a command that runs something (its script, flags, and arguments)
_NOTE_OPS_WORDS = frozenset("""
ssh scp sftp rsync cd ls login logon log logged account accounts shell terminal sudo export source then there
here original local remote same machine machines host hosts server servers node nodes box boxes workstation cluster
directory directories folder folders dir path paths run runs ran running call calls execute executes invoke launch
start use reproduce replicate first next finally change working open opens opened go access connect connected
enter navigate switch activate note notes lab nb tip remark
""".split())
# words about a machine or how to reach it: a command left beside one of them is part of the authors' setup
_NOTE_NAV_WORDS = frozenset("""
ssh scp sftp rsync cd login logon log logged account accounts shell terminal sudo host hosts server servers node
nodes box boxes workstation cluster machine machines remote connect connected access enter navigate switch activate
original
""".split())
_NOTE_COMMAND_RE = re.compile(r"(?:\bpython3?|\bbash|\bsh|\bsource|\bsudo|\btorchrun|\baccelerate\s+launch|"
                              r"\bdeepspeed|\bjupyter\s+nbconvert)\s+(?:-{1,2}[\w-]+\s+)*\S+(?:\s+(?:-{1,2}[\w-]+"
                              r"(?:[ =][^\s;&|]+)?|[^\s;&|-][^\s;&|]*))*", _A)


def note_skeleton_reason(text: str, original: Optional[str] = None) -> Optional[str]:
    """Why what is left of a supplementary note (a README sentence, a comment
    or docstring line) says nothing once its leak goes, or None: only a host,
    an account, how to get there ('ssh … then cd …'), a command that runs a
    script, and generic words are left — no number outside the command, no
    other content word. A command whose note (`original`, the note before the
    deletion; else what is left) says nothing about a machine or how to reach
    it is a usage example ("python run.py --grid a" once its environment
    prefix goes): it stays."""
    t = unicodedata.normalize("NFKC", _NOTE_MARK_RE.sub(" ", text or ""))
    if not _ANY_LETTER_RE.search(t):
        return "nothing but punctuation or numbers is left"
    had_command = bool(_NOTE_COMMAND_RE.search(t))
    t = _NOTE_COMMAND_RE.sub(" ", t)
    if had_command:
        around = _NOTE_COMMAND_RE.sub(" ", unicodedata.normalize("NFKC", original)) if original is not None else t
        if not set(w.lower() for w in re.findall(r"[A-Za-z]+", around)) & _NOTE_NAV_WORDS:
            return None
    t = re.sub(r"(?<![\w-])-{1,2}[A-Za-z][\w-]*(?:[ =][\w./:-]+)?", " ", t)       # flags
    t = re.sub(r"\S*[/\\]\S*|(?<![\w-])[\w.-]+\.(?:py|sh|ipynb|json|jsonl|ya?ml|txt|md|csv|cfg|toml)\b", " ", t)
    t = re.sub(r"&&|\|\||[;:|`'\"()\[\],.!?]", " ", t)
    if re.search(r"\d", t):
        return None
    words = [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z'-]*", t)]
    family = _UNIT_FAMILY_WORDS["eng"]
    content = [w for w in words if w not in _SKELETON_GENERIC and w not in _NOTE_OPS_WORDS and w not in family]
    if content:
        return None
    return "only a host, an account, a command, and generic words are left"


_ANY_LETTER_RE = re.compile(r"[^\W\d_]")   # a letter of any script (a CJK note is not punctuation)
_NEGATION_RE = re.compile(r"\b(?:no|not|never|none|nothing|neither|nor|only)\b|n't\b", re.I)


def _content_words(text: str) -> List[str]:
    # English words outside the generic list, and every run of letters of another script
    return [w for w in re.findall(r"[A-Za-z][A-Za-z'-]*|[^\W\d_A-Za-z]+", text)
            if w.lower().strip("'-") not in _SKELETON_GENERIC]


def skeleton_reason(text: str) -> Optional[str]:
    """Why what is left of a sentence says nothing a reader needs, or None."""
    t = unicodedata.normalize("NFKC", _NOTE_MARK_RE.sub(" ", _detex_line(text or "")))
    if not _ANY_LETTER_RE.search(t):
        return "nothing but punctuation or numbers is left"
    gi = _GENERIC_INSTRUCTION_RE.fullmatch(t.strip())
    if gi and not re.search(r"\d", t):
        # "To reproduce, call the scripts.", "To replicate, change directory and run the code in that directory."
        return "only a generic instruction is left ('%s')" % _collapse_ws(t)[:60]
    bp = _BARE_PRED_RE.search(t.strip())
    # a bare predicate ("The logs are stored."): one clause, no negation, at most two content words before it
    head = t.strip()[:bp.start()] if bp else ""
    if bp and not re.search(r"[;:,]", head) and not _NEGATION_RE.search(head) and len(_content_words(head)) <= 2:
        return "only a bare predicate is left ('%s')" % _collapse_ws(t)[-60:]
    rt = _RUNTIME_PRED_RE.search(t)
    if rt and not _COMPARE_RE.search(t) and len(_content_words(t[:rt.start()] + " " + t[rt.end():])) <= 5:
        return "only a run time is left ('%s'): compute accounting, the leak's own family" % _collapse_ws(rt.group(0))
    stripped, found = t, []
    for rx in _SKELETON_STRIP:
        found += [m.group(0) for m in rx.finditer(stripped)]
        stripped = rx.sub(" ", stripped)
    if _content_words(stripped):
        return None
    if found:
        return "only %s and generic words are left" % ", ".join("'%s'" % _collapse_ws(x) for x in found[:3])
    return "only generic words are left ('%s')" % _collapse_ws(t)[:60]


_SENT_TERM_RE = re.compile(r"[.!?][\"')\]}]*(?=\s|$)")
_PARA_BREAK_RE = re.compile(r"\n[ \t]*\n")
_UNSAFE_SPAN_RE = re.compile(r"\\(?:begin|end|item|section|subsection|subsubsection|paragraph|chapter|label|caption|"
                             r"footnote|input|include|newcommand|renewcommand|def)\b|\\\\|(?<!\\)&|(?<!\\)%")


def _sentence_span(text: str, a: int, b: int, kind: str) -> Tuple[int, int]:
    """The sentence that holds text[a:b]: within its paragraph (prose) or its
    line (a supplementary note); it starts after the previous sentence's end."""
    if kind == "supplement":
        lo = text.rfind("\n", 0, a) + 1
        hi = text.find("\n", b)
        hi = len(text) if hi < 0 else hi
    else:
        lo = 0
        for m in _PARA_BREAK_RE.finditer(text, 0, a):
            lo = m.end()
        m2 = _PARA_BREAK_RE.search(text, b)
        hi = m2.start() if m2 else len(text)
    s = lo
    for m in _SENT_TERM_RE.finditer(text, lo, a):
        s = m.end()
    m3 = _SENT_TERM_RE.search(text, b, hi)
    return s, (m3.end() if m3 else hi)


def _safe_sentence(span: str, kind: str) -> bool:
    """A sentence that may go as a whole: no structure (environments, items,
    headings, labels, captions, cells, line breaks, comments), balanced groups."""
    if kind == "paper":
        if _UNSAFE_SPAN_RE.search(span):
            return False
        if span.count("{") != span.count("}") or span.count("[") != span.count("]"):
            return False
        if (span.count("$") - span.count("\\$")) % 2:
            return False
    return 0 < len(_wordlist(span)) <= APPLY_MAX_DELETED_WORDS


def _tidy_deletion(text: str, at: int, kind: str, line_emptied: bool = True) -> str:
    """After a deletion at `at`: drop the line the deletion left empty (a blank
    line inside a paragraph would split it; an empty comment line is residue),
    else one doubled space or a space before punctuation. Words never change.
    `line_emptied` is False when the deletion took a line break itself (the
    blank line left is then the one that was there)."""
    lo = text.rfind("\n", 0, at) + 1
    hi = text.find("\n", at)
    hi = len(text) if hi < 0 else hi
    line = text[lo:hi]
    rest = _NOTE_MARK_RE.sub("", line) if kind == "supplement" else line
    if line_emptied and not rest.strip() and (line or (lo > 0 and hi < len(text))):
        if hi < len(text):
            out = text[:lo] + text[hi + 1:]
            # a paragraph of its own: one of the two blank lines around it goes too
            if lo >= 2 and text[lo - 2:lo] == "\n\n" and out[lo:lo + 1] == "\n":
                out = out[:lo] + out[lo + 1:]
            return out
        return text[:max(0, lo - 1)] + text[hi:]
    if 0 < at <= len(text) and text[at - 1] in " \t" and (at == len(text) or text[at] in " \t\n,.;:!?)"):
        return text[:at - 1] + text[at:]
    if at == lo and at < len(text) and text[at] in " \t":
        return text[:at] + text[at + 1:]
    return text


def _changed_region(old: str, new: str) -> Tuple[int, int, int]:
    """(start, end in old, end in new) of the one region two texts differ in."""
    n = min(len(old), len(new))
    p = 0
    while p < n and old[p] == new[p]:
        p += 1
    q = 0
    while q < n - p and old[len(old) - 1 - q] == new[len(new) - 1 - q]:
        q += 1
    return p, len(old) - q, len(new) - q


# ─── Residue: what a deletion must never leave behind (the apply gate) ───────
# A deletion is refused when the text it leaves holds more of any of these
# shapes than the text it replaced: the marks a deleted run leaves behind
# ("(, archived logs)", "4× -48GB"), an account or a command without its
# argument ("plee@ then", "cd &&"), a sentence that ends on the word that
# introduced what was deleted ("takes about."), two function words that now
# touch ("on a)"), a conjunction left before a preposition ("and on"), half a
# compound ("toy/ output", "no- check"), a sentence or a note line that now
# starts with a mark (". ;"), a verb left without its object ("use at"), a
# "per" without what it counted, two separators that touch ("note:,", "; ("),
# a doubled space. Only what the edit adds counts: a shape the
# text already had stays the authors' business. `apply` checks the result of
# every delete, supp-delete, and delete-sentence edit (the executor cannot turn
# it off), and the scan's change review (FIX-EDIT) checks every change since
# round 0 the same way.
_RESIDUE_DANGLING = (r"(?:about|approximately|around|roughly|nearly|almost|on|with|than|of|at|by|from|under|via|"
                     r"using|into|onto|the|a|an|and|or|takes|took|requires|needs|costs|lasts)")
_RESIDUE_OBJ_VERBS = r"(?:takes|took|requires|required|needs|needed|costs|lasts|lasted|consumes|consumed)"
_RESIDUE_RES: Tuple[Tuple[str, Any], ...] = (
    ("an opening bracket followed by a separator ('(,')", re.compile(r"[(\[（]\s*[,;，；]")),
    ("a separator right before a closing bracket (', )')", re.compile(r"[,;，；]\s*[)\]）]")),
    ("an empty pair of brackets ('()')", re.compile(r"\(\s*\)|\[\s*\]|（\s*）")),
    ("a hyphen left alone after a space ('4× -48GB')", re.compile(r"(?<=\s)-(?=[A-Za-z0-9])")),
    ("an '@' with nothing after it ('user@ then')", re.compile(r"[\w.-]@(?=[\s,;:)\]]|$)", re.M)),
    ("a sentence that ends on a dangling word ('takes about.')",
     re.compile(r"(?<![\w-])" + _RESIDUE_DANGLING + r"\s*[.;!?](?=[\s\"')\]}]|$)")),
    ("two function words that now touch ('on a)', 'with and')", re.compile(
        r"(?<![\w-])(?i:a|an|the)\s+(?:a|an|the|and|or|of|on|with|at|by|from|to|in|under|via|using|than)(?![\w-])"
        r"|(?<![\w-])(?i:on|with|of|at|by|from|under|via|using|into|than|about|as)\s+(?:and|or|but|on|with|of|at|by|"
        r"from|under|via|using|into|than)(?![\w-])"
        r"|(?<![\w-])(?:a|an|the|on|with|of|at|by|from|under|via|using|into|than|about|approximately)\s*[,;:)\]]")),
    ("a verb left without its object ('takes per arm')", re.compile(
        r"(?<![\w-])" + _RESIDUE_OBJ_VERBS + r"\s+(?:per|for|on|in|at|with|and|or|but)(?![\w-])"
        r"|(?<![\w-])" + _RESIDUE_OBJ_VERBS + r"\s*[,;:)\]]"
        r"|(?<![\w-])(?:use|uses|employ|employs)\s+(?:per|for|on|in|at|with|and|or|but)(?![\w-])")),
    ("a 'per' left without what it counted ('(per arm')", re.compile(r"(?:[(\[;,]|^)[ \t]*(?i:per)(?![\w-])",
                                                                     re.M)),
    ("two separators that now touch ('note:,')", re.compile(r"[,;:][ \t]*[,;:](?![:=])")),
    ("a separator left before a bracket ('; (')", re.compile(r"[,;][ \t]*[(\[]")),
    ("an article left before a verb ('the were')", re.compile(
        r"(?<![\w-])(?i:a|an|the)\s+(?:is|are|was|were|has|have|had|be|been|do|does|did|will|would|can|could|may|"
        r"might|should|must)(?![\w-])")),
    ("a conjunction left without what it joined ('and (', 'and on')", re.compile(
        r"(?<![\w-])(?:and|or|nor)\s*(?:[,;:)\]]|\()"
        r"|(?<![\w-])(?i:and|or|nor)\s+(?i:on|with|at|by|from|under|via|using|into|onto|of|than|in|to|for)(?![\w-])")),
    ("a slash left without its other half ('toy/ output')", re.compile(r"(?<=\w)/(?=[ \t]|$)", re.M)),
    ("a hyphen left before a space ('no- check')", re.compile(r"(?<=[A-Za-z])-(?=[ \t])")),
    ("a sentence or line that now starts with a mark ('. ;')", re.compile(
        r"(?m)^[ \t]*(?:#+|//|%+|\*)?[ \t]*[.;:,](?=[ \t]|$)|(?<=[.!?])[ \t]*[.;:,](?=[ \t]|$)")),
    ("a docstring that now starts with a space ('\"\"\" dry check')", re.compile(r"(?:\"\"\"|''')[ \t]+(?=\S)")),
    ("a doubled space", re.compile(r"(?<=\S) {2,}(?=\S)")),
    ("a space left between two CJK characters", re.compile("(?<=[" + _CJK_CLASS + "]) (?=[" + _CJK_CLASS + "])")),
    ("a command left without its argument ('cd &&', 'ssh then')",
     re.compile(r"(?<![\w.-])(?:cd|ssh|scp|sftp|rsync)\s*(?:&&|\|\||;|$|(?:and|then)(?![\w-]))", re.M)),
    ("an emptied markup group ('\\texttt{}')",
     re.compile(r"\\(?:emph|textbf|textit|texttt|textsc|path|url|code)\s*\{\s*[/\\.~]?\s*\}")),
    ("a sentence that now starts in lower case", re.compile(r"(?<=[.!?])[ \t\n]+(?=[a-z])")),
)


def _residue_here(rx: Any, before: str, after: str) -> str:
    """The words around the first place in `after` where `rx` finds a shape
    `before` did not have there (what a reader of the plan looks for)."""
    pick = None
    for m in rx.finditer(after):
        lo = after.rfind(" ", 0, max(0, m.start() - 10)) + 1
        hi = after.find(" ", min(len(after), m.end() + 10))
        hi = len(after) if hi < 0 else hi
        snippet = _collapse_ws(after[lo:hi])
        pick = pick or snippet
        if snippet not in _collapse_ws(before):
            return snippet[:80]
    return (pick or "")[:80]


def deletion_residue(before: str, after: str) -> List[str]:
    """The residue shapes `after` holds more of than `before` (empty: clean):
    each named with its example and, after "here:", the words of `after` it
    was found in."""
    out: List[str] = []
    for why, rx in _RESIDUE_RES:
        if len(rx.findall(after or "")) > len(rx.findall(before or "")):
            here = _residue_here(rx, before or "", after or "")
            out.append(re.sub(r" \('", " (like '", why, count=1) + (" — here: '%s'" % here if here else ""))
    for o, c in (("(", ")"), ("[", "]"), ("{", "}"), ("（", "）")):
        if abs((after or "").count(o) - (after or "").count(c)) > abs((before or "").count(o) - (before or "").count(c)):
            out.append("unbalanced brackets ('%s%s')" % (o, c))
    return out


def _residue_window(old: str, new: str) -> Tuple[str, str]:
    """The lines around the one region two texts differ in, in both texts (what
    the residue gate reads: a deletion's marks are next to it)."""
    s_, e_old, e_new = _changed_region(old, new)
    lo = old.rfind("\n", 0, s_) + 1
    hi_old = old.find("\n", e_old)
    hi_old = len(old) if hi_old < 0 else hi_old
    hi_new = hi_old - (e_old - e_new)
    return old[lo:hi_old], new[lo:max(lo, hi_new)]


_REG_RECORD_NAME_RE = re.compile(r"regist|amend|addend|clarif|errat", re.I)


def _reg_protected_member(member: str, policy: Optional[Dict[str, Any]]) -> bool:
    """A supplementary member that is a registration record while the policy
    keeps registration labels: its sentences never go as a whole."""
    keep = str((policy or {}).get("registration_labels") or "keep") != "flag"
    return keep and bool(_REG_RECORD_NAME_RE.search(member or ""))


def _whole_sentence_if_skeleton(text: str, new_text: str, pos: int, before: str, after: str, kind: str,
                                ec: EditCheck, anchors: Sequence[Tuple[str, Sequence[str]]],
                                member: str = "", det: Optional[Dict[str, Any]] = None,
                                rel: str = "", paper_dir: str = "") -> Optional[Tuple[str, str, int]]:
    """When the deletion leaves a skeleton of its sentence: the text with the
    whole sentence deleted instead (checked by the same whitelist), the reason,
    and where the sentence was; else None. Never where a pure-leak sentence
    may never go as a whole: end matter, a negation or qualifier in what is
    left, an ordering next to a registration word, a registration record of
    the supplement the policy keeps."""
    det = det or {}
    if kind == "supplement" and _reg_protected_member(member, det.get("policy")):
        return None
    if kind == "paper" and rel:
        if _STATEMENT_FILE_RE.search(os.path.splitext(os.path.basename(rel))[0]):
            return None
        if paper_dir:
            regions = det.setdefault("_regions", _source_regions(paper_dir))
            main, sub = regions.get((rel, text.count("\n", 0, pos) + 1), ("body", None))
            if main in ("end_matter", "references", "checklist"):
                return None
    s, e = _sentence_span(new_text, pos, pos + len(after), kind)
    rest = new_text[s:e]
    if not _NOTE_MARK_RE.sub("", rest).strip():
        return None  # the deletion already took the whole sentence
    # a note of the supplement may also be left with only a host, an account, and a command
    reason = skeleton_reason(rest) or (note_skeleton_reason(rest, text[s:e + (len(before) - len(after))])
                                       if kind == "supplement" else None)
    if not reason:
        return None
    s0, e0 = s, e + (len(before) - len(after))
    sentence = text[s0:e0]
    if not sentence.strip() or not _safe_sentence(sentence, kind):
        return None
    if kind == "supplement":
        # a line of a command that goes on (a trailing backslash), or that goes on from the line before, is
        # never taken alone: the rest of the command would be left without its head
        l0 = text.rfind("\n", 0, s0) + 1
        l1 = text.find("\n", max(s0, e0 - 1))
        l1 = len(text) if l1 < 0 else l1
        prev = text[text.rfind("\n", 0, max(0, l0 - 1)) + 1:max(0, l0 - 1)] if l0 > 0 else ""
        if re.search(r"\\[ \t]*$", text[l0:l1]) or re.search(r"\\[ \t]*$", prev):
            return None
    if kind == "paper":
        # the same structure a pure-leak sentence never goes beside: an environment, a footnote, a label, a
        # comment, a line break, the only sentence under a heading (a sentence the script cannot read whole
        # never goes either); and a reference or a citation, which points at what the paper keeps
        if _REF_CMD_RE.search(sentence) or _CITE_CMD_RE.search(sentence):
            return None
        t0 = s0 + (len(sentence) - len(sentence.lstrip()))
        rec_ = next((x for x in _tex_sentences(text) if x["start"] <= t0 < x["end"]), None)
        if rec_ is None or rec_["unsafe"] or (rec_["only"] and rec_["after_heading"]) or \
                rec_["end"] < e0 - (len(sentence) - len(sentence.rstrip())):
            return None
    if kind == "supplement" and _member_kind(member or "") == "doc":
        # a document's line can be half of a sentence a soft line break wraps: never only that half
        if (s0 == 0 or text[s0 - 1] == "\n") and _soft_wrap_start(text, s0, kind, member) != s0:
            return None
        nl = text.find("\n", e0)
        nxt = text[e0 + 1:nl if nl >= 0 else len(text)] if text[e0:e0 + 1] == "\n" else ""
        if nxt.strip() and not _SENT_END_RE.search(sentence) and not _ITEM_START_RE.match(nxt.lstrip()) \
                and not nxt.lstrip().startswith(("#", "|", "```")):
            return None
        # a heading is reworded by a person, never deleted; nor the only text under one
        if sentence.lstrip().startswith("#"):
            return None
        prev_lines = [x for x in text[:s0].split("\n") if x.strip()]
        next_lines = [x for x in text[e0:].split("\n") if x.strip()]
        if prev_lines and re.match(r"\s*#{1,6}\s", prev_lines[-1]) and (
                not next_lines or re.match(r"\s*#{1,6}\s", next_lines[0])):
            return None
    plain = _detex_line(sentence)
    if _UNIT_QUALIFIER_RE.search(_detex_line(rest)) or (
            _UNIT_REG_RE.search(plain) and (_UNIT_ANCHOR_RE.search(plain) or _UNIT_TIME_RE.search(plain))):
        return None
    if verify_change(sentence, "", ec, kind, False, anchors=anchors)["verdict"] != "ok":
        return None
    return text[:s0] + text[e0:], reason, s0


# ─── Pure-leak sentences and clauses (fix class `delete-sentence`) ───────────
# A sentence — or a clause of it set off by a comma or a semicolon — whose only
# content is a confirmed leak goes as a whole, still a pure deletion, decided by
# the script and recomputed by `apply` before it writes. The unit holds a Tier A
# ENG or PROC hit that is definite, or that a cross-family reviewer ruled leak
# or reword; once the leak goes, what is left is a skeleton: no number,
# reference, citation, formula, macro, or result word, and no content word
# beyond the leak's own family (tooling, hardware, hosts, storage; run and
# review vocabulary; times), or only a bare predicate (stored, implemented, run,
# read from the logs, completed) after a short subject. Never: end matter, a
# sentence inside any environment (table, figure, caption, equation, list,
# theorem, abstract), a footnote, a label, the only sentence under a heading;
# a sentence with a negation or a qualifier (only, not, no, except, unless,
# without); one that states an ordering (before, after, prior to,
# subsequently, a date) next to a registration, amendment, revision, or
# version word.

SENTENCE_FIX_CHECKS = ("ENG-VER", "ENG-FW", "ENG-HW", "ENG-QTY", "ENG-OPS", "ENG-PATH", "ENG-NET", "ENG-HASH",
                       "PROC-TIME", "PROC-REVIEW", "PROC-REVISION")
_UNIT_KIND = {"PROC-TIME": "time", "PROC-REVIEW": "narr", "PROC-REVISION": "narr"}  # every other check: "eng"
# words that state a result or a conclusion: a unit that holds one is never a skeleton
# (policy skeleton_result_words adds more)
SKELETON_RESULT_WORDS = tuple("""
improve improves improved improvement improvements outperform outperforms outperformed show shows shown showed
showing find finds finding findings found significant significantly higher lower equal equals equally better worse
best worst increase increases increased decrease decreases decreased reduce reduces reduced reduction gain gains
achieve achieves achieved yield yields yielded demonstrate demonstrates demonstrated indicate indicates indicated
confirm confirms confirmed reveal reveals revealed exceed exceeds exceeded surpass surpasses conclude concludes
concluded conclusion conclusions reproduce reproduces reproduced match matches matched agree agrees agreed
consistent correlate correlates correlated correlation predict predicts predicted accurate accuracy faster slower
fewer than compared versus vs prove proves proved establish establishes established effective robust
""".split())
_UNIT_NUMBER_WORDS = frozenset("""
zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen
eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety hundred hundreds thousand thousands million
millions billion billions dozen dozens twice thrice half first second third fourth fifth sixth seventh eighth ninth
tenth
""".split())
# the leak's own family: words a unit may hold beside the leak and still say nothing
_UNIT_FAMILY_WORDS = {
    "eng": frozenset("""
cluster clusters server servers machine machines host hosts hosted hosting workstation workstations internal shared
remote dedicated array arrays queue queued scheduler scheduled submitted partition partitions container containers
gpu gpus cpu cpus tpu tpus npu npus accelerator accelerators card cards device devices disk disks storage directory
directories folder folders copy copies copied working checkpoint checkpoints cache caches cached mounted offload
offloading offloaded serving served backend backends runtime runtimes driver drivers install installed installation
build builds compiled launcher launchers worker workers threads wall wall-clock wallclock independent separate calls
""".split()),
    "narr": frozenset("""
reviewer reviewers review reviews reviewed request requests requested asked suggestion suggestions suggested comment
comments commented feedback rebuttal round rounds previous prior earlier version versions revision revisions revised
draft drafts submission submissions resubmission response responses respond responded meta-review meta-reviewer
chair chairs area camera-ready fix fixes fixed fixing bug bugs hotfix bugfix patch patched corrected correction
corrections again rerun reruns re-run re-runs reran re-ran rerunning re-running relaunch relaunched repeat repeated
redo redid redone session user users wanted accommodate addressed concern concerns raised pointed
""".split()),
    "time": frozenset("""
utc gmt cst cest cet pst pdt est edt bst jst kst ist aest aedt hkt sgt aoe local time times timezone zone clock
morning afternoon evening night midnight noon am pm january february march april june july august september october
november december jan feb mar apr jun jul aug sep sept oct nov dec monday tuesday wednesday thursday friday saturday
sunday today yesterday date dates dated day days week weeks month months year years hour hours minute minutes between
until till
""".split()),
}
# a bare predicate whose complement was all leak: (what it says, pattern, most content words before it)
_UNIT_PRED_RES = (
    ("where it is stored", re.compile(
        r"\b(?:is|are|was|were|has\s+been|have\s+been|had\s+been|can\s+be|could\s+be|will\s+be)\s+(?:all\s+|also\s+)?"
        r"(?:stored|saved|kept|located|placed|hosted|cached|archived|written|logged|mounted|copied|uploaded|"
        r"persisted|found|available)\b", re.I), 5),
    ("what the code is written in", re.compile(
        r"\b(?:is|are|was|were)\s+(?:all\s+|also\s+)?(?:implemented|written|built|developed|coded|programmed)\b",
        re.I), 3),
    ("how or where it was run", re.compile(
        r"\b(?:is|are|was|were|has\s+been|have\s+been|had\s+been)\s+(?:all\s+|also\s+)?(?:run|executed|performed|"
        r"conducted|launched|submitted|scheduled|queued|completed|finished|done|started|served|computed|trained|"
        r"evaluated|processed|generated|carried\s+out)\b", re.I), 3),
    ("where the numbers were read", re.compile(
        r"\b(?:is|are|was|were)\s+(?:all\s+|also\s+)?(?:taken|obtained|read|derived|extracted|parsed|gathered|"
        r"pulled|copied|collected)\s+from\b", re.I), 3),
)
_UNIT_RUNTIME_PRED_RE = re.compile(r"\b(?:takes?|took|requires?|required|needs?|needed|costs?|lasts?|lasted)\s+"
                                   r"(?:about|around|approximately|roughly|nearly|under|over|less\s+than|"
                                   r"more\s+than|at\s+most|at\s+least|~)?\s*$", re.I | _A)
_UNIT_DET_ONE_RE = re.compile(r"\b(?:one|a\s+single)(?=\s+(?!of\b|or\b|and\b|to\b|by\b|in\b|on\b|at\b|(?:hours?|"
                              r"minutes?|seconds?|days?|weeks?|months?|years?|times?|GPUs?|CPUs?|nodes?|cores?|"
                              r"epochs?|steps?|percent|point|points)\b)[a-z])", re.I | _A)
_UNIT_PURPOSE_RE = re.compile(r"\b(?:to|in\s+order\s+to)\s+(?:reproduce|replicate)\b", re.I | _A)
_UNIT_QUALIFIER_RE = re.compile(r"\b(?:only|not|no|never|none|nothing|neither|nor|except|excepting|unless|without|"
                                r"cannot)\b|n't\b", re.I | _A)
_UNIT_ANCHOR_RE = re.compile(r"\b(?:before|after|prior\s+to|subsequent(?:ly)?|afterwards?|beforehand|earlier|later|"
                             r"previously|until|ahead\s+of|in\s+advance|preceding)\b", re.I | _A)
_UNIT_REG_RE = re.compile(r"\b(?:pre-?)?regist\w*|\bamend\w*|\baddend\w*|\berrat\w*|\brevis\w*|\bversions?\b|"
                          r"\bclarification\w*|\bpre-?specif\w*", re.I | _A)
_UNIT_TIME_RE = re.compile(_CLOCK_TZ_RE.pattern + r"|" + _DATE_RE.pattern + r"|" + _TIMEISH_RE.pattern
                           + r"|\(?\s*(?:UTC|GMT)\s*[+\-\u2212]\s*\d{1,2}(?::?\d{2})?\s*\)?", _A)
# openers of a clause that may go on its own: a leading adverbial clause, and a
# clause after a comma or a semicolon that hangs on the main clause
_UNIT_LEAD_RE = re.compile(r"(?:after|before|as|when|whenever|while|since|because|following|per|upon|once|given|"
                           r"on|using|with|via|under|in\s+response\s+to|at\s+the\s+request\s+of)\b", re.I)
_UNIT_TRAIL_RE = re.compile(r"(?:(?:and|but|yet)\s+)?(?:where|which|while|whereas|as|since|because|so|with|using|via|"
                            r"on|under|at|through|after|before|following|per|once|when|[a-z]+(?:ed|ing))\b"
                            r"|(?:and|but|yet)\s+(?:the|its|their|all|each|every|our|this|these|those|it|they|we)\b",
                            re.I)
_UNIT_SNAKE_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+")
_UNIT_NUM_TOKEN_RE = re.compile(r"(?<![\w.\-])\d")   # a number, never a digit inside a name (Stage-2, A100, box07)
_UNIT_ABBREV = frozenset("""e g i al fig figs eq eqs eqn sec secs sect tab ref refs app appx vs cf resp approx no nos vol
ch chap thm lem prop def alg cor mr mrs ms dr st jr prof inc ltd co viz ca est etc pp p l ll""".split())
_UNIT_TEXT_ARG_CMDS = frozenset("""emph textit textbf textsc textsl textup textrm textsf textnormal textmd underline
uline mbox text hbox""".split())
_UNIT_LITERAL_CMDS = frozenset("texttt path url code nolinkurl lstinline".split())
_UNIT_SILENT_CMDS = frozenset("""noindent centering raggedright raggedleft small footnotesize scriptsize tiny
normalsize large Large LARGE huge Huge hfill vfill par smallskip medskip bigskip quad qquad xspace relax protect
nobreak allowbreak ignorespaces unskip bfseries itshape rmfamily sffamily ttfamily mdseries upshape normalfont em
selectfont leavevmode null strut sloppy""".split())
_UNIT_SYMBOLS = {"times": "\u00d7", "ldots": "...", "dots": "...", "cdots": "...", "textasciitilde": "~",
                 "textbackslash": "\\", "textendash": "\u2013", "textemdash": "\u2014", "cdot": "\u00b7",
                 "textquotesingle": "'", "ss": "ss", "S": "\u00a7"}
_UNIT_UNSAFE_CMDS = frozenset("""footnote footnotetext marginpar caption captionof label item section subsection
subsubsection paragraph subparagraph chapter part input include includegraphics bibliography bibliographystyle
printbibliography newcommand renewcommand providecommand def begin end appendix maketitle newpage clearpage
tableofcontents vspace hspace todo""".split())
_UNIT_REF_NAMES = frozenset("""ref Ref cref Cref autoref Autoref eqref pageref nameref Nameref vref Vref cpageref
Cpageref labelcref namecref nameCref lcnamecref zcref zref subref thmref""".split())
_UNIT_CITE_NAME_RE = re.compile(r"^(?:[Cc]ite[a-zA-Z]*|[a-z]*cite[a-z]*|nocite|[Pp]arencite|[Tt]extcite|[Aa]utocite|"
                                r"[Ff]ootcite|[Ss]martcite|[Ss]upercite|fullcite)$")
_UNIT_CUT_RE = re.compile(r"\\(?:(?:section|subsection|subsubsection|paragraph|subparagraph|chapter|part)\*?"
                          r"|label|input|include|item|appendix|maketitle|newpage|clearpage|bibliography|"
                          r"bibliographystyle|printbibliography|tableofcontents|vspace\*?|bigskip|medskip|smallskip)"
                          r"(?![A-Za-z@])")
_UNIT_HEADING_CMD_RE = re.compile(r"\\(?:section|subsection|subsubsection|paragraph|subparagraph|chapter|part)\*?"
                                  r"(?![A-Za-z@])")
_UNIT_ENV_RE = re.compile(r"\\(begin|end)\s*\{([^{}]+)\}")
_RUNIN_OPEN_RE = re.compile(r"\\(?:textbf|textit|emph|textsc|underline)\s*\{\s*$")
_UNIT_MAX_SENTENCE_CHARS = 1200


def _skip_args(raw: str, j: int, opt: int = 2, req: int = 1) -> int:
    """Past up to `opt` [..] groups and `req` {..} groups after a command."""
    n = len(raw)
    for _ in range(opt):
        k = j
        while k < n and raw[k] in " \t":
            k += 1
        if k < n and raw[k] == "[":
            close = raw.find("]", k)
            if close < 0:
                return n
            j = close + 1
        else:
            break
    for _ in range(req):
        k = j
        while k < n and raw[k] in " \t\n":
            k += 1
        if k < n and raw[k] == "{":
            _body, end = _balanced_arg(raw, k)
            j = end if end > k else n
        else:
            break
    return j


def _tex_print(raw: str, base: int = 0) -> Tuple[str, List[int], List[int], List[Tuple[int, int, str]]]:
    """What a stretch of LaTeX prose prints, the source span of every printed
    character (start, end), and marks over the printed text: a reference or
    citation ('ref', 'cite'), inline math ('math'), a macro the script cannot
    read ('macro'), typewriter text ('tt'), and structure a sentence deletion
    never touches ('unsafe:<why>': a comment, a footnote, a label, a caption,
    display math, a line break, a heading or an environment)."""
    out: List[str] = []
    ps: List[int] = []
    pe: List[int] = []
    marks: List[Tuple[int, int, str]] = []
    n = len(raw)

    def emit(s: str, a: int, b: int) -> None:
        for ch in s:
            out.append(ch)
            ps.append(base + a)
            pe.append(base + b)

    def marked(s: str, a: int, b: int, kind: str) -> None:
        k = len(out)
        emit(s or " ", a, b)
        marks.append((k, len(out), kind))

    def math_print(body: str) -> str:
        t = re.sub(r"\\times(?![A-Za-z])", "\u00d7", body)
        t = re.sub(r"\\cdot(?![A-Za-z])", "\u00b7", t)
        t = re.sub(r"\\[%&_#$]", lambda m: m.group(0)[1], t)
        t = re.sub(r"\\[A-Za-z@]+\*?|\\.", "", t)
        return re.sub(r"[{}^_]", "", t).strip() or "x"

    i = 0
    while i < n:
        c = raw[i]
        if c == "%":
            j = raw.find("\n", i)
            j = n if j < 0 else j
            marked(" ", i, j, "unsafe:comment")
            i = j
            continue
        if c == "\\":
            if i + 1 >= n:
                i += 1
                continue
            d = raw[i + 1]
            if d.isalpha() or d == "@":
                m = re.match(r"\\([A-Za-z@]+)(\*?)", raw[i:])
                name, j = m.group(1), i + m.end()
                if name in _UNIT_REF_NAMES:
                    j = _skip_args(raw, j, 1, 1)
                    marked("\u00a7", i, j, "ref")
                elif _UNIT_CITE_NAME_RE.match(name):
                    j = _skip_args(raw, j, 2, 1)
                    marked("\u00a7", i, j, "cite")
                elif name in _UNIT_UNSAFE_CMDS:
                    j = _skip_args(raw, j, 1, 1 if name not in ("item", "appendix", "maketitle", "newpage",
                                                                "clearpage", "tableofcontents") else 0)
                    marked(" ", i, j, "unsafe:%s" % name)
                elif name in _UNIT_LITERAL_CMDS:
                    k = j
                    while k < n and raw[k] in " \t":
                        k += 1
                    if k < n and raw[k] == "{":
                        body, end = _balanced_arg(raw, k)
                        marked(_detex_literal(body or "") or " ", i, end, "tt")
                        j = end
                    else:
                        marked("\u00a7", i, j, "macro")
                elif name in _UNIT_TEXT_ARG_CMDS or name in _UNIT_SILENT_CMDS:
                    pass  # its group prints as prose (the braces are skipped below), or it prints nothing
                elif name in _UNIT_SYMBOLS:
                    emit(_UNIT_SYMBOLS[name], i, j)
                    if raw.startswith("{}", j):
                        j += 2
                elif name == "href":
                    k = _skip_args(raw, j, 0, 1)
                    marks.append((len(out), len(out), "tt"))
                    j = k  # the link text that follows prints as prose
                else:
                    j = _skip_args(raw, j, 2, 3)
                    marked("\u00a7", i, j, "macro")
                i = j
                continue
            if d == "\\":
                j = _skip_args(raw, i + 2, 1, 0)
                marked(" ", i, j, "unsafe:linebreak")
                i = j
                continue
            if d in "%&_#${}":
                emit(d, i, i + 2)
                i += 2
                continue
            if d in ",;: !>":
                emit(" ", i, i + 2)
                i += 2
                continue
            if d == "/" or d == "-":
                i += 2
                continue
            if d == "(":
                close = raw.find("\\)", i + 2)
                close = n if close < 0 else close
                marked(math_print(raw[i + 2:close]), i, min(n, close + 2), "math")
                i = min(n, close + 2)
                continue
            if d == "[":
                close = raw.find("\\]", i + 2)
                close = n if close < 0 else close
                marked(" ", i, min(n, close + 2), "unsafe:display math")
                i = min(n, close + 2)
                continue
            if d in "'`^\"~=.":  # an accent: the letter it decorates prints
                j = i + 2
                if j < n and raw[j] == "{":
                    body, end = _balanced_arg(raw, j)
                    emit((body or "")[:1], i, end)
                    i = end
                elif j < n:
                    emit(raw[j], i, j + 1)
                    i = j + 1
                else:
                    i = j
                continue
            i += 2
            continue
        if c == "$":
            if raw.startswith("$$", i):
                close = raw.find("$$", i + 2)
                close = n if close < 0 else close
                marked(" ", i, min(n, close + 2), "unsafe:display math")
                i = min(n, close + 2)
                continue
            k = i + 1
            while k < n and not (raw[k] == "$" and raw[k - 1] != "\\"):
                k += 1
            marked(math_print(raw[i + 1:k]), i, min(n, k + 1), "math")
            i = min(n, k + 1)
            continue
        if c in "{}":
            i += 1
            continue
        if c == "~":
            emit(" ", i, i + 1)
            i += 1
            continue
        if raw.startswith("---", i):
            emit("\u2014", i, i + 3)
            i += 3
            continue
        if raw.startswith("--", i):
            emit("\u2013", i, i + 2)
            i += 2
            continue
        if raw.startswith("``", i) or raw.startswith("''", i):
            emit('"', i, i + 2)
            i += 2
            continue
        if c in "\n\r\t":
            emit(" ", i, i + 1)
            i += 1
            continue
        emit(c, i, i + 1)
        i += 1
    return "".join(out), ps, pe, marks


def _comment_mask(text: str) -> List[Tuple[int, int]]:
    """(start, end) of every LaTeX comment (an unescaped % to the end of its line)."""
    spans = []
    pos = 0
    for line in text.split("\n"):
        k = len(strip_tex_comments(line))
        if k < len(line):
            spans.append((pos + k, pos + len(line)))
        pos += len(line) + 1
    return spans


def _tex_cut_spans(text: str) -> Tuple[Tuple[int, int], List[Tuple[int, int, str]]]:
    """The body of a .tex file (inside \\begin{document} when the file has one)
    and the stretches no sentence may cross: every environment but the
    document, comments, headings with their titles, labels, items, and the
    other structure commands."""
    comments = _comment_mask(text)

    def in_comment(p: int) -> bool:
        return any(a <= p < b for a, b in comments)
    lo, hi = 0, len(text)
    m = re.search(r"\\begin\s*\{document\}", text)
    if m and not in_comment(m.start()):
        lo = m.end()
        m2 = re.search(r"\\end\s*\{document\}", text)
        hi = m2.start() if m2 else len(text)
    cuts: List[Tuple[int, int, str]] = [(a, b, "comment") for a, b in comments]
    stack: List[Tuple[str, int]] = []
    for m in _UNIT_ENV_RE.finditer(text):
        if in_comment(m.start()) or m.group(2).strip() == "document":
            continue
        name = m.group(2).strip()
        if m.group(1) == "begin":
            stack.append((name, m.start()))
            continue
        k = len(stack) - 1
        while k >= 0 and stack[k][0] != name:
            k -= 1
        if k < 0:
            cuts.append((m.start(), m.end(), "environment"))
            continue
        start = stack[k][1]
        del stack[k:]
        if not stack:
            cuts.append((start, m.end(), "environment %s" % name))
    for name, start in stack:  # an environment left open runs to the end
        cuts.append((start, len(text), "environment %s" % name))
        break
    for m in _UNIT_CUT_RE.finditer(text):
        if in_comment(m.start()):
            continue
        cmd = m.group(0)
        nargs = 0 if any(cmd.startswith("\\" + x) for x in ("item", "appendix", "maketitle", "newpage", "clearpage",
                                                               "printbibliography", "tableofcontents", "bigskip",
                                                               "medskip", "smallskip")) else 1
        end = _skip_args(text, m.end(), 1, nargs)
        cuts.append((m.start(), end, "heading" if _UNIT_HEADING_CMD_RE.match(cmd) else "structure"))
    return (lo, hi), sorted(cuts)


def _tex_sentences(text: str) -> List[Dict[str, Any]]:
    """The prose sentences of a .tex file: each with its source span (start,
    end), its printed text, the source span of every printed character, its
    marks, whether it is the only sentence of its stretch, whether a heading
    opens that stretch, and why it may never go as a whole (`unsafe`)."""
    (lo, hi), cuts = _tex_cut_spans(text)
    # stretches: between blank lines and cuts, inside the body
    pieces: List[Tuple[int, int]] = []
    pos0 = lo
    for m in re.finditer(r"\n[ \t]*\n", text[lo:hi]):
        pieces.append((pos0, lo + m.start()))
        pos0 = lo + m.end()
    pieces.append((pos0, hi))
    stretches: List[Tuple[int, int, bool]] = []
    for a, b in pieces:
        pos, heading = a, False
        for c0, c1, why in cuts:
            if c1 <= a or c0 >= b or c1 <= pos:
                continue
            if c0 > pos and text[pos:c0].strip():
                stretches.append((pos, c0, heading))
                heading = why == "heading"
            else:  # a label after a heading keeps the heading in force
                heading = heading or why == "heading"
            pos = max(pos, c1)
        if pos < b:
            stretches.append((pos, b, heading))
    out: List[Dict[str, Any]] = []
    for a, b, heading in stretches:
        seg = text[a:b]
        if not seg.strip():
            continue
        printed, p_s, p_e, marks = _tex_print(seg, a)
        sents: List[Tuple[int, int]] = []
        start = 0
        for m in re.finditer(r"[.!?][\"'\u201d\u2019)\]]*(?=\s|$)", printed):
            nxt = re.match(r"\s*(\S)?", printed[m.end():])
            nch = nxt.group(1) if nxt else None
            word = re.search(r"([A-Za-z]+)\.?$", printed[start:m.start() + 1])
            prev = word.group(1) if word else ""
            if m.group(0).startswith(".") and (prev.lower() in _UNIT_ABBREV or (len(prev) == 1 and prev.isupper())):
                continue
            if nch is not None and nch.islower():
                continue
            sents.append((start, m.end()))
            start = m.end()
        tail = printed[start:].strip()
        complete = len(sents)
        if tail:
            sents.append((start, len(printed)))
        # a run-in heading ("\textbf{Setup.} …") is no sentence of the stretch: what follows it is under a heading
        runin = []
        for x in sents:
            body_x = printed[x[0]:x[1]].strip()
            if not body_x or len(_wordlist(body_x)) > 8:
                runin.append(False)
                continue
            x0 = x[0] + (len(printed[x[0]:x[1]]) - len(printed[x[0]:x[1]].lstrip()))
            r0, r1 = p_s[x0], p_e[x[1] - 1]
            runin.append(bool(_RUNIN_OPEN_RE.search(text[max(a, r0 - 16):r0])) and text[r1:r1 + 2].lstrip()[:1] == "}")
        body = [x for i_, x in enumerate(sents) if printed[x[0]:x[1]].strip() and not runin[i_]]
        for k, (s0, s1) in enumerate(sents):
            if runin[k]:
                heading = True
                continue
            while s0 < s1 and printed[s0].isspace():
                s0 += 1
            if s0 >= s1:
                continue
            raw_s, raw_e = p_s[s0], p_e[s1 - 1]
            unsafe = sorted({kind.split(":", 1)[1] for a_, b_, kind in marks
                             if kind.startswith("unsafe:") and a_ < s1 and s0 < b_})
            if k >= complete:
                unsafe.append("no sentence end")
            first = printed[s0:s0 + 1]
            if first.islower():
                unsafe.append("starts inside a sentence")
            if raw_e - raw_s > _UNIT_MAX_SENTENCE_CHARS:
                unsafe.append("too long")
            seg_raw = text[raw_s:raw_e]
            if seg_raw.count("{") != seg_raw.count("}"):
                unsafe.append("unbalanced braces")
            out.append({"start": raw_s, "end": raw_e, "printed": printed[s0:s1], "ps": p_s[s0:s1], "pe": p_e[s0:s1],
                        "marks": [(max(a_, s0) - s0, min(b_, s1) - s0, kind) for a_, b_, kind in marks
                                  if a_ < s1 and s0 < b_ or (a_ == b_ and s0 <= a_ < s1)],
                        "only": len(body) == 1, "after_heading": heading and (k == 0 or runin[k - 1]),
                        "unsafe": unsafe, "line": text.count("\n", 0, raw_s) + 1,
                        "last_line": text.count("\n", 0, raw_e) + 1})
    return out


_HW_LEFT_RE = re.compile(r"(?:(?:(?<![\w.])\d+|(?<![\w-])(?i:one|two|three|four|five|six|seven|eight|nine|ten|"
                         r"eleven|twelve|sixteen|thirty-two|sixty-four|single|dual|quad))\s*(?:[\u00d7x]\s*)?)?"
                         r"(?:(?:NVIDIA|AMD|Intel|Tesla|Google|Apple)\s+)?$", _A)
_HW_RIGHT_RE = re.compile(r"(?:[- ]?\d+\s*(?:GB|GiB|TB)\b)?(?:\s+(?:GPUs?|TPUs?|NPUs?|accelerators?|cards?|devices?|"
                          r"cores?|CPUs?|nodes?))?", _A)
_FW_RIGHT_RE = re.compile(r"(?:\s+[A-Z][\w-]*\d[\w-]*)?(?:\s+(?:inference|offloading|offload|serving|engine|backend|"
                          r"runtime|stage|plugin|launcher|scheduler|cluster|jobs?))*", _A)
_PATH_RIGHT_RE = re.compile(r"\s+(?:on|at)\s+[a-z][a-z-]*\d[a-z0-9-]*\b", _A)
# a finite re-run verb of the narration ("we re-ran X", "were re-run"), never a gerund subject ("Re-running X
# reproduces …" states a check): its object goes with it, up to a mark, a number, a result word, or a new clause
_REDO_HIT_RE = re.compile(r"\bre-?ran\b|\brelaunched\b|\bre-?executed\b|\b(?:we|to|was|were|been|be|had|have|has|"
                          r"then|must|should|could)\s+re-?run\b", re.I | _A)
_REDO_STOP_RE = re.compile(r"[,;:.!?()§]|\d|\b(?:and|but|which|that|where|while|whereas|because|so|to|"
                           + "|".join(sorted(_UNIT_NUMBER_WORDS)) + "|" + "|".join(sorted(SKELETON_RESULT_WORDS))
                           + r")\b", re.I)


def _unit_kind(check: str) -> str:
    return _UNIT_KIND.get(check, "eng")


def _expand_leak(p: str, s: int, e: int, check: str) -> Tuple[int, int]:
    """A confirmed hit widened over the words that belong to the same leak: the
    count and maker of a hardware model and its memory and device noun, the
    product name after a framework (Stage-2) and its feature words, a host
    after a path, the object of a re-run verb up to its clause end (never over
    a number)."""
    if check in ("ENG-HW", "ENG-QTY"):
        m = _HW_LEFT_RE.search(p[:s])
        s = m.start() if m else s
        m = _HW_RIGHT_RE.match(p, e)
        e = m.end() if m else e
    elif check == "ENG-FW":
        m = _FW_RIGHT_RE.match(p, e)
        e = m.end() if m else e
    elif check == "ENG-PATH":
        m = _PATH_RIGHT_RE.match(p, e)
        e = m.end() if m else e
    elif check == "PROC-REVISION" and _REDO_HIT_RE.search(p[s:e]):
        stop = _REDO_STOP_RE.search(p, e)
        e = stop.start() if stop else len(p)
    return s, e


def _clause_spans(p: str, marks: Sequence[Tuple[int, int, str]]) -> List[Tuple[int, int, str]]:
    """The clauses of a printed sentence: (start, end, separator before it)
    split at top-level commas and semicolons (never inside brackets, math,
    a reference, typewriter text, or a number such as 4,096)."""
    inside = [(a, b) for a, b, k in marks if k in ("math", "ref", "cite", "tt", "macro")]
    depth, cuts = 0, []
    for k, ch in enumerate(p):
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        elif ch in ",;" and depth == 0 and not any(a <= k < b for a, b in inside):
            if ch == "," and 0 < k < len(p) - 1 and p[k - 1].isdigit() and p[k + 1].isdigit():
                continue
            cuts.append(k)
    out, start, sep = [], 0, ""
    for k in cuts:
        out.append((start, k, sep))
        start, sep = k + 1, p[k]
    out.append((start, len(p), sep))
    return out


def unit_skeleton_reason(p: str, mask: Sequence[bool], kinds: Iterable[str],
                         marks: Sequence[Tuple[int, int, str]] = (), extra_words: Iterable[str] = ()
                         ) -> Optional[str]:
    """Why a printed sentence or clause says nothing once its leak goes (the
    characters `mask` marks), or None: no number, reference, citation,
    formula, macro, code identifier, or result word is left, and no content
    word beyond the leak's own family — or only a bare predicate (stored,
    implemented, run, read from the logs, completed) after a short subject."""
    kinds = set(kinds)
    for a, b, kind in marks:
        if kind in ("ref", "cite", "math", "macro") and any(not mask[k] for k in range(a, min(b, len(p)))):
            return None
    rest = "".join(" " if (k < len(mask) and mask[k]) else ch for k, ch in enumerate(p))
    rest0 = rest  # the masked text, position for position with p
    rest = unicodedata.normalize("NFKC", rest)
    if "time" in kinds:
        rest = _UNIT_TIME_RE.sub(" ", rest)
    for rx in _SKELETON_STRIP:
        rest = rx.sub(" ", rest)
    if _UNIT_NUM_TOKEN_RE.search(rest) or _UNIT_SNAKE_RE.search(rest):
        return None
    # "one" or "a single" before a noun is a determiner ("one toy sweep"), not a count; "one hour",
    # "one of the three" and a lone "one" are numbers
    counted = _UNIT_DET_ONE_RE.sub(" ", rest)
    words = [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z'-]*", counted)]
    if any(w in _UNIT_NUMBER_WORDS for w in words):
        return None
    family: Set[str] = set()
    for k_ in kinds:
        family |= _UNIT_FAMILY_WORDS.get(k_, frozenset())
    results = set(SKELETON_RESULT_WORDS) | {str(x).lower() for x in extra_words}

    def content(t: str) -> List[str]:
        return [w for w in _content_words(t) if w.lower() not in family]
    if _GENERIC_INSTRUCTION_RE.fullmatch(rest.strip(" ,;")):
        return "only a generic instruction is left ('%s')" % _collapse_ws(rest)[:80]
    pred = None
    for what, rx, most in _UNIT_PRED_RES:
        m = rx.search(rest)
        if m:
            pred = (what, m, most)
            break
    if pred is None:
        # a run-time predicate whose whole object is the leak ("one toy sweep takes about [2.5 GPU-hours]")
        m = _UNIT_RUNTIME_PRED_RE.search(rest)
        m0 = _UNIT_RUNTIME_PRED_RE.search(rest0)
        if m and m0 and any(mask[k] for k in range(m0.start(), min(len(mask), len(p)))):
            pred = ("a run time", m, 5)
    span_free = rest if pred is None else rest[:pred[1].start()] + " " + rest[pred[1].end():]
    # a purpose clause ("To reproduce the runs, …") states no result
    span_free = _UNIT_PURPOSE_RE.sub(" ", span_free)
    if any(w in results for w in (x.lower() for x in re.findall(r"[A-Za-z][A-Za-z'-]*", span_free))):
        return None
    if not content(rest):
        return "nothing but the leak and generic words is left ('%s')" % _collapse_ws(rest)[:80]
    if pred is not None:
        what, m, most = pred
        head, tail = rest[:m.start()], rest[m.end():]
        # the subject alone before the predicate: no clause of its own (no separator, no other verb)
        if (not re.search(r"[,;:]", head) and not re.search(r"\b(?:is|are|was|were|has|have|had|be|been)\b", head,
                                                              re.I)
                and len(content(head)) <= most and not content(tail)):
            return "only %s is left ('%s')" % (what, _collapse_ws(rest)[:80])
    return None


def _paragraph_context(text: str, start: int, end: int) -> str:
    """The paragraph around text[start:end] (between blank lines), without it."""
    lo = 0
    for m in _PARA_BREAK_RE.finditer(text, 0, start):
        lo = m.end()
    m2 = _PARA_BREAK_RE.search(text, end)
    hi = m2.start() if m2 else len(text)
    return text[lo:start] + " " + text[end:hi]


def _registration_order_elsewhere(context: str) -> bool:
    """The paragraph around a sentence (outside it) already states that a
    registration came before or after something ('the toy rule was registered
    ahead of every run'): the sentence does not carry it."""
    for m in _ORDER_ANCHOR_RE.finditer(_detex_line(context or "")):
        if re.search(r"regist", m.group(0), re.I):
            return True
    return False


def _unit_exclusion(p: str, mask: Sequence[bool], sent: Dict[str, Any], region: Tuple[Optional[str], Optional[str]],
                    drop: Optional[Sequence[Tuple[int, int]]] = None, context: str = "") -> Optional[str]:
    """Why a sentence never goes automatically, whatever its words: end
    matter, structure around it, a negation or qualifier outside the leak,
    or an ordering next to a registration, amendment, revision, or version
    word. The ordering is read on what goes (`drop`: the dropped clauses;
    None: the whole sentence): the part deleted may not state an ordering
    beside a registration word, nor take the date or time that orders a
    registration the kept part states without an ordering of its own — unless
    the paragraph around the sentence (`context`) states the registration's
    ordering already."""
    main, sub = region
    if main in ("end_matter", "references", "checklist") or sub in ("ai_use", "ethics", "reproducibility",
                                                                  "acknowledgments"):
        return "it is in the end matter"
    if sent.get("unsafe"):
        return "a structure around it (%s)" % ", ".join(sent["unsafe"][:3])
    if sent.get("only") and sent.get("after_heading"):
        return "it is the only sentence under its heading"
    outside = "".join(" " if (k < len(mask) and mask[k]) else ch for k, ch in enumerate(p))
    q = _UNIT_QUALIFIER_RE.search(outside)
    if q:
        return "it holds a negation or a qualifier ('%s')" % q.group(0)
    if drop is None or any(a <= 0 and b >= len(p) for a, b in drop):
        gone, kept = p, ""
    else:
        keep = [True] * len(p)
        for a, b in drop:
            for k in range(max(0, a), min(b, len(p))):
                keep[k] = False
        gone = " ".join(p[max(0, a):b] for a, b in drop)
        kept = "".join(ch if keep[k] else " " for k, ch in enumerate(p))
    anchor_gone = bool(_UNIT_ANCHOR_RE.search(gone))
    time_gone = bool(_UNIT_TIME_RE.search(gone))
    reg_gone = bool(_UNIT_REG_RE.search(gone))
    # a registration the kept part states without an ordering word of its own takes its order from what goes
    reg_kept = bool(_UNIT_REG_RE.search(kept)) and not _UNIT_ANCHOR_RE.search(kept)
    if reg_gone and anchor_gone:
        return "it states an ordering next to a registration, amendment, revision, or version word"
    if ((reg_gone and time_gone) or (reg_kept and (time_gone or anchor_gone))) and \
            not _registration_order_elsewhere(context):
        return "it states an ordering next to a registration, amendment, revision, or version word"
    return None


def _analyze_unit_sentence(text: str, sent: Dict[str, Any], confirmed: Dict[Tuple[str, str], Set[str]],
                           region: Tuple[Optional[str], Optional[str]], ctx: ScanContext,
                           extra_words: Iterable[str] = ()) -> Optional[Dict[str, Any]]:
    """The deletion one sentence allows: the whole sentence, its pure-leak
    clauses, or nothing — with the confirmed hits it holds, the skeleton
    reason, and the exclusion that stops it (None when it holds no confirmed
    hit). `confirmed` maps (check, key) to the groups of its confirmed
    occurrences in this sentence."""
    p, marks = sent["printed"], sent["marks"]
    hits = [h for h in detect_text(p, region[0] or "body", region[1], ctx, "tex")
            if h.check in SENTENCE_FIX_CHECKS and not h.plan_only and not h.usage
            and (h.check, _norm_key(h.match if h.match is not None else p[h.start:h.end])) in confirmed]
    if not hits:
        return None
    mask = [False] * len(p)
    kinds: Set[str] = set()
    leak = []
    for h in hits:
        s, e = _expand_leak(p, h.start, h.end, h.check)
        for k in range(s, min(e, len(p))):
            mask[k] = True
        kinds.add(_unit_kind(h.check))
        key = _norm_key(h.match if h.match is not None else p[h.start:h.end])
        leak.append({"check": h.check, "key": key, "groups": sorted(confirmed[(h.check, key)]),
                     "match": p[h.start:h.end], "start": h.start, "end": h.end,
                     "raw": sent["ps"][h.start]})
    clauses = _clause_spans(p, marks)
    # a leading adverbial clause that opens with the narration is the narration ("Per the rebuttal, …")
    for c0, c1, _sep in clauses[:-1] if len(clauses) > 1 else []:
        body = p[c0:c1]
        lead = len(body) - len(body.lstrip())
        if (c0 == 0 and _UNIT_LEAD_RE.match(body.lstrip())
                and any(x["check"] in ("PROC-REVISION", "PROC-REVIEW") and c0 <= x["start"] < c1
                        and len(_wordlist(p[c0:x["start"]])) <= 8 for x in leak)):
            for k in range(c0 + lead, c1):
                mask[k] = True
        break
    context = _paragraph_context(text, sent["start"], sent["end"])

    def clause_marks(c0: int, c1: int) -> List[Tuple[int, int, str]]:
        return [(max(a, c0) - c0, min(b, c1) - c0, kd) for a, b, kd in marks if a < c1 and c0 < b]

    whole = unit_skeleton_reason(p.rstrip(" .!?"), mask, kinds, marks, extra_words)
    if whole is None and len(clauses) > 1:
        per = [unit_skeleton_reason(p[c0:c1].rstrip(" .!?"), mask[c0:c1], kinds, clause_marks(c0, c1), extra_words)
               for c0, c1, _s in clauses]
        if all(per):
            whole = "every clause says nothing once the leak goes (%s)" % per[0]
    res: Dict[str, Any] = {"leak": leak, "kinds": sorted(kinds), "exclusion": None, "unit": None, "reason": None,
                           "skeleton": None, "drop": []}
    if whole:
        res.update(skeleton="sentence", reason=whole, drop=[(0, len(p))])
    else:
        drop = []
        for idx, (c0, c1, sep) in enumerate(clauses):
            if len(clauses) < 2 or not any(c0 <= x["start"] < c1 for x in leak):
                continue
            why = unit_skeleton_reason(p[c0:c1].rstrip(" .!?"), mask[c0:c1], kinds, clause_marks(c0, c1),
                                       extra_words)
            if not why:
                continue
            body = p[c0:c1].strip()
            last = idx == len(clauses) - 1
            if idx == 0 and clauses[1][2] == "," and _UNIT_LEAD_RE.match(body):
                span = (c0, clauses[1][0])                      # "As X asked, we …" -> "We …"
            elif idx == 0 and clauses[1][2] == ";":
                span = (c0, clauses[1][0])                      # "X; Y." -> "Y."
            elif last and sep in ",;" and (sep == ";" or _UNIT_TRAIL_RE.match(body)):
                end = c1
                while end > c0 and p[end - 1] in " .!?":
                    end -= 1
                span = (c0 - 1, end)                            # "X, served on Y." -> "X."
            elif not last and 0 < idx and sep == "," and clauses[idx + 1][2] == "," and (
                    _UNIT_TRAIL_RE.match(body) or _UNIT_LEAD_RE.match(re.sub(r"^(?:and|but)\s+", "", body))):
                span = (c0 - 1, c1)                             # "A, and as X asked, B" -> "A, B"
            else:
                continue
            if any(x["check"] == "PROC-REVISION" and c0 <= x["start"] < c1 for x in leak):
                # a fix or re-run clause may scope what the rest states ("after the fix, X rose to 91%"): it
                # goes on its own only beside a rest without numbers or results
                rest_txt = p[:max(0, span[0])] + " " + p[span[1]:]
                if _UNIT_NUM_TOKEN_RE.search(rest_txt) or any(
                        w.lower() in SKELETON_RESULT_WORDS for w in re.findall(r"[A-Za-z]+", rest_txt)):
                    continue
            drop.append((span, why))
            if any(x["check"] == "PROC-REVIEW" and c0 <= x["start"] < c1 for x in leak) and span[1] < len(p):
                # "As the reviewers asked, A also reports B": the "also" the request brought goes with it
                m_also = re.match(r"\s*(?:\S+\s+){0,3}?(also)\b", p[span[1]:span[1] + 60])
                if m_also and not re.search(r"[,;:]", m_also.group(0)):
                    a_ = span[1] + m_also.start(1)
                    drop.append(((a_ - 1, a_ + 4), why))
        if drop:
            keep = [True] * len(p)
            for (a, b), _w in drop:
                for k in range(max(0, a), min(b, len(p))):
                    keep[k] = False
            left = "".join(ch for k, ch in enumerate(p) if keep[k])
            if len(_wordlist(left)) >= 3 and not any(
                    x for x in leak if keep[x["start"]] and x["check"] in ("PROC-REVISION", "PROC-REVIEW")):
                res.update(skeleton="clause", reason=drop[0][1], drop=[sp for sp, _w in drop])
    # the exclusions read what goes: the whole sentence, or only the clauses dropped (an ordering is read
    # with the paragraph around the sentence)
    excl = _unit_exclusion(p, mask, sent, region, res["drop"] if res["skeleton"] else None, context)
    res["exclusion"] = excl
    for x in leak:
        x["covered"] = any(max(0, a) <= x["start"] < b for a, b in res["drop"])
    res["deleted"] = " … ".join(_collapse_ws(p[max(0, a):b]) for a, b in res["drop"])
    gone = sum(len(_wordlist(p[max(0, a):b])) for a, b in res["drop"])
    if res["skeleton"] and gone > APPLY_MAX_DELETED_WORDS:
        excl = excl or "it is longer than one edit may delete (%d words)" % gone
        res["exclusion"] = excl
    if res["skeleton"] and not excl:
        res["unit"] = res["skeleton"]
    return res


def _unit_edit(text: str, sent: Dict[str, Any], drop: Sequence[Tuple[int, int]]) -> Optional[Tuple[str, str]]:
    """(before, after) of a unit's deletion in the source: the sentence, and
    the sentence without its dropped clauses (their comma or semicolon and the
    space after them included, the new first word capitalized); after is ''
    for the whole sentence."""
    raw = text[sent["start"]:sent["end"]]
    p = sent["printed"]
    if len(drop) == 1 and drop[0] == (0, len(p)):
        return raw, ""
    cut: List[Tuple[int, int]] = []
    for a, b in drop:
        a = max(0, a)
        b = min(b, len(p))
        while b < len(p) and p[b] == " " and (a == 0 or p[a] in ",;"):
            b += 1                                              # the space after a leading clause goes too
        if a >= b:
            continue
        cut.append((sent["ps"][a] - sent["start"], sent["pe"][b - 1] - sent["start"]))
    out, pos = [], 0
    for a, b in sorted(cut):
        if a < pos:
            return None
        out.append(raw[pos:a])
        pos = b
    out.append(raw[pos:])
    after = "".join(out)
    if after.count("{") != after.count("}") or (after.count("$") - after.count("\\$")) % 2:
        return None
    if any(a == 0 for a, _b in drop):
        m = re.match(r"\s*(\S)", after)
        if not m or not (m.group(1).isalpha() or m.group(1) == "\\"):
            return None
        if m.group(1).islower():  # the new first word is capitalized like a sentence start
            after = after[:m.start(1)] + m.group(1).upper() + after[m.end(1):]
    after = re.sub(r"[ \t]{2,}", " ", after)
    return raw, after


def _source_regions(paper_dir: str) -> Dict[Tuple[str, int], Tuple[str, Optional[str]]]:
    """(file, line) -> (region, subregion) of the expanded sources, the way the
    scan reads them (body, appendix, references, checklist, end matter and its
    statements)."""
    tables = {k: [x.casefold() for x in v] for k, v in DEFAULT_HEADINGS.items()}
    out: Dict[Tuple[str, int], Tuple[str, Optional[str]]] = {}
    try:
        mains = discover_inputs(paper_dir, [], [], False)["mains"]
    except Exception:  # noqa: BLE001 — without sources there is no unit
        return out
    for main_tex in mains:
        main, sub = "body", None
        with contextlib.suppress(Exception):
            for ln in expand_tex(main_tex, paper_dir)["lines"]:
                text = ln["text"]
                for m in _TEX_REGION_RE.finditer(text):
                    if m.group(1):
                        main, sub = "appendix", None
                    elif m.group(2) or m.group(3):
                        main, sub = "references", None
                    elif m.group(5):
                        main, sub = "end_matter", "acknowledgments"
                    elif m.group(4) is not None:
                        hk = heading_kind(_detex_line(m.group(4)), main, tables, letter_ok=False)
                        if hk and hk[0] in ("references", "checklist"):
                            main, sub = hk[0], None
                        elif hk and hk[0] == "end_matter":
                            main, sub = "end_matter", hk[1]
                        elif hk and hk[0] in ("compute", "related_work"):
                            sub = hk[0]
                        elif hk and hk[0] == "appendix":
                            main, sub = "appendix", None
                        else:
                            sub = None
                if re.search(r"\\end\{thebibliography\}", text):
                    main = "body" if main == "references" else main
                out.setdefault((ln["file"], ln["line"]), (main, sub))
    return out


_STATEMENT_FILE_RE = re.compile(r"(?:^|[/_-])(?:ai[_-]?(?:use|statement)|ethic|reproducib|checklist|ack|"
                                r"statement|broader|impact|limitation)", re.I)


def pure_leak_units(findings: List[Dict[str, Any]], paper_dir: str, policy: Optional[Dict[str, Any]] = None,
                    reviewed_cross_family: bool = False, anonymous: bool = True,
                    texts: Optional[Dict[str, str]] = None, red: Optional[Redactor] = None) -> List[Dict[str, Any]]:
    """Every sentence of the sources that holds a confirmed ENG or PROC hit
    (definite, or ruled leak or reword by a cross-family reviewer), with the
    deletion it allows (`unit`: sentence, clause, or None), the skeleton reason,
    and the exclusion that stops it. `texts` (file -> text) replaces reading
    the files. A sentence that holds an identity term, a deny-list term, or a
    secret is never queued as text (the queue and the report stay redacted):
    its own finding goes to the plan."""
    pol = policy or {}
    extra = [str(x) for x in (pol.get("skeleton_result_words") or []) if str(x).strip()]
    occ: Dict[str, List[Tuple[int, str, str, str]]] = {}
    for f in findings:
        if f["check"] not in SENTENCE_FIX_CHECKS or f.get("layer") not in ("pdf", "tex"):
            continue
        if f.get("exempted_by") or f["severity"] == INFO or f.get("ruling_flip") or f.get("hw_usage") \
                or f.get("plan_only"):
            continue
        ok = f["certainty"] == DEFINITE or (reviewed_cross_family and f.get("ruling") in CONFIRMED_RULINGS)
        loc = f.get("location") or {}
        if not ok or not loc.get("file") or not loc.get("line"):
            continue
        with contextlib.suppress(TypeError, ValueError):
            occ.setdefault(str(loc["file"]), []).append((int(loc["line"]), f["check"], _norm_key(f["match"]),
                                                         str(f.get("group") or "")))
    if not occ:
        return []
    regions = _source_regions(paper_dir) if texts is None else {}
    ctx = _plan_ctx(pol, anonymous)
    out: List[Dict[str, Any]] = []
    for rel, items in sorted(occ.items()):
        full = _within(paper_dir, rel)
        if texts is not None and rel in texts:
            text = texts[rel]
        elif full and os.path.isfile(full) and full.lower().endswith(".tex"):
            with open(full, "rb") as fh:
                text, enc = _decode_text(fh.read())
            if enc not in ("utf-8", "utf-8-sig", "gb18030"):
                continue
        else:
            continue
        for sent in _tex_sentences(text):
            confirmed: Dict[Tuple[str, str], Set[str]] = {}
            for line, chk, key, grp in items:
                if sent["line"] <= line <= sent["last_line"]:
                    confirmed.setdefault((chk, key), set()).add(grp)
            if not confirmed:
                continue
            region = regions.get((rel, sent["line"]), ("body", None))
            if _STATEMENT_FILE_RE.search(os.path.splitext(os.path.basename(rel))[0]):
                region = ("end_matter", region[1])
            res = _analyze_unit_sentence(text, sent, confirmed, region, ctx, extra)
            if res is None:
                continue
            raw = text[sent["start"]:sent["end"]]
            res.update(file=rel, line=sent["line"], sentence=raw, printed=sent["printed"], region=list(region),
                       start=sent["start"], end=sent["end"])
            if res["unit"] and red is not None and (red.redact(raw) != raw or find_secrets(raw)):
                res["exclusion"] = "it holds an identity term, a deny-list term, or a secret (fixed by its own item)"
                res["unit"] = None
            if res["unit"]:
                ed = _unit_edit(text, sent, res["drop"])
                if ed is None or text.count(ed[0]) != 1:
                    res["exclusion"] = res["exclusion"] or "the source text cannot be cut cleanly or occurs twice"
                    res["unit"] = None
                else:
                    res["before"], res["after"] = ed
            res["groups"] = sorted({g for x in res["leak"] for g in x["groups"]})
            res["checks"] = sorted({x["check"] for x in res["leak"]})
            res["last_line"] = sent["last_line"]
            out.append(res)
    return out


def _unit_covering(units: Sequence[Dict[str, Any]], f: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The analysed sentence whose skeleton part (the whole sentence or a
    dropped clause) holds this finding's occurrence, or None."""
    loc = f.get("location") or {}
    try:
        line = int(loc.get("line") or 0)
    except (TypeError, ValueError):
        return None
    key = _norm_key(f.get("match"))
    for u in units:
        if u.get("file") != loc.get("file") or not (u["line"] <= line <= u.get("last_line", u["line"])):
            continue
        if any(x.get("covered") and x["check"] == f["check"] and x["key"] == key and f.get("group") in x["groups"]
               for x in u["leak"]):
            return u
    return None


def escalate_pure_narration(findings: List[Dict[str, Any]], units: Sequence[Dict[str, Any]],
                            cross_family: bool) -> List[Dict[str, Any]]:
    """Revision or review narration a cross-family reviewer ruled `reword` but
    whose sentence (or clause) says nothing once the narration goes is a leak:
    the check's confirmed level (BLOCK), never capped at WARN by the reword
    ruling — the fix is deleting it, not telling the story in other words."""
    if not cross_family:
        return []
    out = []
    for f in findings:
        if f["check"] not in ("PROC-REVISION", "PROC-REVIEW") or f.get("ruling") != "reword" or f.get("ruling_flip"):
            continue
        u = _unit_covering(units, f)
        if u is None:
            continue
        f["ruling_reviewer"], f["ruling"] = "reword", "leak"
        f["severity"] = f.get("confirm_severity") or BLOCK
        f["pure_narration"] = u["reason"]
        if not u.get("unit"):
            f["unit_exclusion"] = u.get("exclusion") or "no clean source edit"
            f["unit_text"] = u.get("deleted") or ""
        note = "pure narration: %s — a reword ruling does not keep it at WARN" % u["reason"]
        f["note"] = "; ".join(x for x in [re.sub(r"reword: keep the fact, reword the passage \(WARN at most\);? ?", "",
                                                 f.get("note") or "").strip("; ") or None, note] if x)
        out.append({"group": f["group"], "check": f["check"], "where": _where_str(f), "reason": u["reason"],
                    "unit": u.get("unit") or u.get("skeleton"), "automatic": bool(u.get("unit")),
                    "exclusion": u.get("exclusion")})
    return out


def _round_skeleton_pass(log: Dict[str, Any], queue: Dict[str, Dict[str, Any]], ec: EditCheck, paper_dir: str,
                         work_dir: str, rnd: int, det: Dict[str, Any]) -> List[Dict[str, Any]]:
    """After all edits of a round: every sentence of the paper sources the
    round's deletions changed is read again, and one that is now a skeleton
    (unit_skeleton_reason, with the leak families the round deleted) goes as
    a whole unless an exclusion stops it — checked against the round's first
    text by the same whitelist (only words leave, and a queued match left
    from that sentence). Several deletions in one sentence ("implemented in
    X 1.0 with Y 2.0") leave what a single one never shows."""
    import difflib
    out: List[Dict[str, Any]] = []
    by_file: Dict[str, List[Dict[str, Any]]] = {}
    for r in log.get("applied") or []:
        if r.get("undone") or not r.get("file") or r.get("class") not in ("delete", "delete-sentence", "marker"):
            continue
        by_file.setdefault(str(r["file"]), []).append(r)
    if not by_file:
        return out
    pol = det.get("policy") or {}
    extra = [str(x) for x in (pol.get("skeleton_result_words") or [])]
    regions: Optional[Dict[Tuple[str, int], Tuple[str, Optional[str]]]] = None
    for rel, recs in sorted(by_file.items()):
        full = _within(paper_dir, rel)
        old_path = os.path.join(work_dir, "backup_r%d" % rnd, _safe_rel("paper/" + rel))
        if not (full and os.path.isfile(full) and os.path.isfile(old_path)):
            continue
        with open(old_path, "rb") as fh:
            old, _e0 = _decode_text(fh.read())
        with open(full, "rb") as fh:
            new, enc = _decode_text(fh.read())
        if old == new or enc not in ("utf-8", "utf-8-sig", "gb18030"):
            continue
        kinds = {_unit_kind(c) for r in recs for c in str(r.get("check") or "").split("+")
                 if c in SENTENCE_FIX_CHECKS} or {"eng"}
        anchors: List[Tuple[str, List[str]]] = []
        for r in recs:
            g = queue.get(str(r.get("group"))) or {}
            anchors += [(str(g.get("fix_class") or "delete"), _wordlist(x)) for x in _item_anchors(g) if _wordlist(x)]
        # the changes as character spans: lines first (fast on a long file), then characters inside each
        # changed block of lines
        ol, nl = old.splitlines(True), new.splitlines(True)
        ost, nst = [0], [0]
        for x in ol:
            ost.append(ost[-1] + len(x))
        for x in nl:
            nst.append(nst[-1] + len(x))
        ops: List[Tuple[str, int, int, int, int]] = []
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, ol, nl, autojunk=False).get_opcodes():
            if tag == "equal":
                ops.append(("equal", ost[i1], ost[i2], nst[j1], nst[j2]))
                continue
            a_blk, b_blk = "".join(ol[i1:i2]), "".join(nl[j1:j2])
            for t2, a1, a2, b1, b2 in difflib.SequenceMatcher(None, a_blk, b_blk, autojunk=False).get_opcodes():
                ops.append((t2, ost[i1] + a1, ost[i1] + a2, nst[j1] + b1, nst[j1] + b2))

        def to_old(p_: int, end: bool) -> int:
            for _tag, i1, i2, j1, j2 in ops:
                if j1 <= p_ <= j2 and (_tag == "equal" or (end and p_ == j2) or (not end and p_ == j1)):
                    return i1 + (p_ - j1) if _tag == "equal" else (i2 if end else i1)
            return -1
        changed = [j1 for _tag, _i1, _i2, j1, _j2 in ops if _tag != "equal"]
        picks = []
        for sent in _tex_sentences(new):
            if not any(sent["start"] <= j <= sent["end"] for j in changed):
                continue
            o0, o1 = to_old(sent["start"], False), to_old(sent["end"], True)
            if o0 < 0 or o1 <= o0 or old[o0:o1] == new[sent["start"]:sent["end"]]:
                continue
            p = sent["printed"]
            reason = unit_skeleton_reason(p.rstrip(" .!?"), [False] * len(p), kinds, sent["marks"], extra)
            if not reason:
                continue
            if regions is None:
                regions = _source_regions(paper_dir)
            region = regions.get((rel, sent["line"]), ("body", None))
            if _STATEMENT_FILE_RE.search(os.path.splitext(os.path.basename(rel))[0]):
                region = ("end_matter", region[1])
            if _unit_exclusion(p, [False] * len(p), sent, region, None,
                               _paragraph_context(new, sent["start"], sent["end"])):
                continue
            if verify_change(old[o0:o1], "", ec, "paper", False, anchors=anchors)["verdict"] != "ok":
                continue
            picks.append((sent, reason))
        text = new
        for sent, reason in sorted(picks, key=lambda x: -x[0]["start"]):
            new_text = _tidy_deletion(text[:sent["start"]] + text[sent["end"]:], sent["start"], "paper", True)
            s_, e_old, e_new = _changed_region(text, new_text)
            own = next((r for r in recs if sent["line"] <= int(r.get("line") or 0) <= sent["last_line"]), recs[-1])
            out.append({"group": own.get("group"), "file": rel, "member": None, "class": "delete-sentence",
                        "key": own.get("key"), "check": own.get("check"), "verdict": "ok",
                        "before": text[s_:e_old], "after": new_text[s_:e_new],
                        "left": text[max(0, s_ - 60):s_], "right": text[e_old:e_old + 60],
                        "extended": "whole sentence once the round's deletions left a skeleton: %s" % reason,
                        "why": "the round's deletions left a skeleton of the sentence: %s" % reason,
                        "line": text.count("\n", 0, s_) + 1, "encoding": enc})
            text = new_text
        if text != new:
            _write_text_as(full, text, enc)
    return out


def _recheck_sentence_item(text: str, g: Dict[str, Any], det: Dict[str, Any]) -> Optional[str]:
    """Why a queued delete-sentence edit no longer holds on this text (None:
    the script still computes the same deletion of the same sentence)."""
    before = str(g.get("before") or "")
    pos = text.find(before)
    sent = next((s for s in _tex_sentences(text) if s["start"] == pos and s["end"] == pos + len(before)), None)
    if sent is None:
        return "the queued sentence is no longer a sentence of the file"
    confirmed: Dict[Tuple[str, str], Set[str]] = {}
    for chk, key in g.get("leaks") or []:
        confirmed.setdefault((chk, key), set()).update(g.get("groups") or [])
    pol = det.get("policy") or {}
    region = tuple(g.get("region") or ("body", None))
    res = _analyze_unit_sentence(text, sent, confirmed, (region[0], region[1]),
                                 _plan_ctx(pol, bool(det.get("anonymous", True))),
                                 [str(x) for x in (pol.get("skeleton_result_words") or [])])
    if res is None or not res.get("unit"):
        return "the script no longer computes a deletion here (%s)" % ((res or {}).get("exclusion") or "no skeleton")
    ed = _unit_edit(text, sent, res["drop"])
    if ed is None or ed != (before, str(g.get("after") or "")):
        return "the script computes another deletion here now"
    return None


def _apply_one(e: Dict[str, Any], queue: Dict[str, Dict[str, Any]], ec: EditCheck, paper_dir: str, stage: str,
               work_dir: str, rnd: int, keep_copy: Any, det: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    det = det or {}
    gid = str(e.get("group") or "")
    rec: Dict[str, Any] = {"group": gid, "file": e.get("file"), "member": e.get("member"),
                           "before": e.get("before"), "after": e.get("after")}

    def reject(why: str, whitelist: bool = True) -> Dict[str, Any]:
        rec.update(verdict="rejected", why=why, whitelist=whitelist)
        return rec
    g = queue.get(gid)
    if g is None:
        return reject("group %s is not in the fix queue (the script decides what a round fixes)" % gid)
    cls = g.get("fix_class")
    rec["class"], rec["key"], rec["check"] = cls, g.get("key"), g.get("check")
    if cls in ("undo", "rebuild", "repack"):
        return reject("a %s item needs no text edit (%s)" % (cls, {"undo": "apply --undo", "rebuild": "a full rebuild",
                                                                "repack": "apply --stage-only, then repack"}[cls]))
    if cls == "supp-remove":
        member = str(e.get("member") or "")
        full = _within(stage, member)
        if not full or not os.path.exists(full):
            return reject("member %s is not in the staged copy" % member, whitelist=False)
        if not _is_leave_out_member(member):
            return reject("only junk, agent files, and run logs may be left out")
        dst = os.path.join(work_dir, "attic_r%d" % rnd, _safe_rel(member))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(full, dst)
        rec.update(verdict="ok", why="left out of the staged copy", attic=_rel(dst, work_dir))
        return rec
    before, after = e.get("before"), e.get("after")
    if not isinstance(before, str) or not isinstance(after, str) or not before:
        return reject("an edit needs a non-empty 'before' and an 'after' (copied from the file)", whitelist=False)
    if cls == "delete-sentence" and (before != g.get("before") or after != g.get("after")
                                     or str(e.get("file") or "") != str(g.get("file") or "")):
        return reject("a delete-sentence item is applied exactly as queued (its file, before, and after; "
                      "`edits --from-queue` writes them)", whitelist=False)
    if cls == "supp-delete":
        full = _within(stage, str(e.get("member") or ""))
        kind = "supplement"
    else:
        full = _within(paper_dir, str(e.get("file") or ""))
        kind = "paper"
        if full and not full.lower().endswith((".tex", ".bib")):
            return reject("the loop edits .tex and .bib sources only")
    if not full or not os.path.isfile(full):
        return reject("file not found inside %s" % ("the staged copy" if kind == "supplement" else "the paper"),
                      whitelist=False)
    with open(full, "rb") as fh:
        raw_bytes = fh.read()
    text, enc = _decode_text(raw_bytes)
    if enc not in ("utf-8", "utf-8-sig", "gb18030"):
        return reject("the file's encoding (%s) cannot be written back unchanged" % enc, whitelist=False)
    n = text.count(before)
    if n != 1:
        return reject("the before text occurs %d times in the file (it must occur exactly once)" % n, whitelist=False)
    code_logic = False
    if kind == "supplement" and _member_kind(str(e.get("member"))) == "code":
        pos = text.index(before)
        first = text.count("\n", 0, pos) + 1
        code_logic = not _note_lines_ok(text, first, first + before.count("\n"), str(e.get("member")))
    # every text the item's occurrences matched (the actual prefix or hash, not a label for it)
    anchors = [(cls, _wordlist(x)) for x in _item_anchors(g) if _wordlist(x)]
    v = verify_change(before, after, ec, kind, code_logic, target=g.get("fix_target"),
                      anchors=anchors if cls in ("delete", "delete-sentence", "marker", "supp-delete") else [])
    allowed = {"delete": ("delete",), "delete-sentence": ("delete-sentence", "delete"),
               "marker": ("marker", "delete"), "supp-delete": ("supp-delete",),
               "escape": ("escape", "escape+delete"), "xref-ref": ("xref-ref",), "xref-cite": ("xref-cite",),
               "meta": ("meta",)}.get(cls, ())
    # a fragment that leaves residue may still go when what is left of its sentence is a skeleton (the
    # whole sentence then goes); the residue gate below reads the final text either way
    residue_only = (v["verdict"] != "ok" and bool(v.get("residue")) and cls in ("delete", "supp-delete"))
    if v["verdict"] != "ok" and not residue_only:
        return reject(v["why"])
    if v["class"] not in allowed and not (cls == "xref-cite" and "xref-cite" in str(v["class"])):
        return reject("the edit is a %s change, not the %s fix this item allows" % (v["class"], cls))
    if cls == "xref-cite":
        dropped, _p = _cite_problem(ec.red.redact(before), ec.red.redact(after), ec)
        if [k for k in dropped if k != g.get("match")]:
            return reject("drops another key than %s" % g.get("match"))
    if cls == "delete-sentence":
        why_not = _recheck_sentence_item(text, g, det)
        if why_not:
            return reject(why_not, whitelist=False)
    pos = text.index(before)
    new_text = text[:pos] + after + text[pos + len(before):]
    if cls == "meta" and kind == "paper" and det.get("anonymous", True):
        left_fields = _identity_fields_left(new_text, ec.red)
        if left_fields:
            # an empty override after the line that sets it keeps the value in the sources
            return reject("the file still sets %s with a value: empty the field where it is set (the meta item's "
                          "`inplace` edit), never with an override line after it" % ", ".join(left_fields),
                          whitelist=False)
    rel = _rel(full, paper_dir) if kind == "paper" else str(e.get("member"))
    keep_copy(full, ("paper/" + rel) if kind == "paper" else ("supp/" + rel))
    if cls == "delete-sentence":
        rec["extended"] = "%s: %s" % (g.get("unit") or "sentence", g.get("reason") or "pure leak")
        at = pos + len(after)
        new_text = _tidy_deletion(new_text, at, kind, line_emptied=not after)
    if cls in ("delete", "supp-delete", "marker"):
        at = pos + len(after)
        ext = (_whole_sentence_if_skeleton(text, new_text, pos, before, after, kind, ec, anchors,
                                           member=str(e.get("member") or ""), det=det,
                                           rel=rel if kind == "paper" else "", paper_dir=paper_dir)
               if cls != "marker" else None)
        if ext is not None:
            # what the deletion left of its sentence says nothing: the whole sentence goes (still only words leave)
            new_text, rec["extended"], at = ext[0], "whole sentence: %s" % ext[1], ext[2]
        new_text = _tidy_deletion(new_text, at, kind,
                                  line_emptied=ext is not None or not (before[:1] == "\n" or before[-1:] == "\n"))
    if cls in ("delete", "supp-delete", "delete-sentence", "marker"):
        # the residue gate, on the text as it would be written: no stray mark, no dangling word
        ob, nb = _residue_window(text, new_text)
        residue = deletion_residue(ob, nb)
        if residue:
            rec["residue"] = residue
            return reject("the deletion leaves residue: %s — the whole sentence may not go either (it says "
                          "more than the leak); re-draft with `edits --from-queue` or leave it for the plan"
                          % "; ".join(residue[:3]), whitelist=False)
    elif residue_only:
        return reject(v["why"])
    # the change as one replaced region of the file: what FIX_LOG shows and `apply --undo` puts back
    s_, e_old, e_new = _changed_region(text, new_text)
    if kind == "supplement" and not _region_is_notes(text, s_, e_old, str(e.get("member") or "")):
        # the region as finally written (a whole sentence or line included) stays inside the notes
        return reject("the change reaches a line that is not a note (a code line, or a template or other "
                      "string the code uses): the loop edits notes only")
    rec["before"], rec["after"] = text[s_:e_old], new_text[s_:e_new]
    rec["left"], rec["right"] = text[max(0, s_ - 60):s_], text[e_old:e_old + 60]
    _write_text_as(full, new_text, enc)
    rec.update(verdict="ok", why=v["why"] + ("; %s" % rec["extended"] if rec.get("extended") else ""),
               line=text.count("\n", 0, s_) + 1, encoding=enc)
    return rec


def _write_text_as(path: str, text: str, enc: str) -> None:
    """Write text back in the encoding it was read in (UTF-8, UTF-8 with BOM, GB18030)."""
    data = (codecs.BOM_UTF8 + text.encode("utf-8")) if enc == "utf-8-sig" else text.encode(
        "gb18030" if enc == "gb18030" else "utf-8")
    with open(path, "wb") as fh:
        fh.write(data)


def _round0_supplement(work_dir: str, paper_dir: str) -> Optional[str]:
    """The supplement round 0 audited: its copy in WORK/rounds/, or the
    directory it was (one supplement only)."""
    rounds = (_load_json(os.path.join(work_dir, ROUNDS_NAME)) or {}).get("rounds") or []
    rec = next((r for r in rounds if isinstance(r, dict) and r.get("round") == 0), None)
    supps = (rec or {}).get("supplements") or []
    if len(supps) != 1:
        return None
    if supps[0].get("copy") and os.path.isfile(os.path.join(work_dir, supps[0]["copy"])):
        return os.path.join(work_dir, supps[0]["copy"])
    path = str(supps[0].get("path") or "")
    full = path if os.path.isabs(path) else os.path.join(paper_dir, path)
    return full if os.path.exists(full) else None


def _container_bytes(blob: bytes, name: str) -> Optional[bytes]:
    """One member of a zip or tar given as bytes (None when absent)."""
    try:
        if blob[:2] == b"PK":
            with zipfile.ZipFile(io.BytesIO(blob)) as zf:
                try:
                    return zf.read(name)
                except KeyError:
                    return None
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:*") as tf:
            try:
                fh = tf.extractfile(name)
            except KeyError:
                return None
            return fh.read() if fh else None
    except (OSError, zipfile.BadZipFile, tarfile.TarError, zlib.error, lzma.LZMAError, EOFError, RuntimeError,
            ValueError):
        return None


def _top_member(archive: str, name: str) -> Optional[bytes]:
    """The stored bytes of a top-level member of a zip, a tar, or a directory."""
    try:
        if os.path.isdir(archive):
            p = _within(archive, name)
            if not p or not os.path.isfile(p):
                return None
            with open(p, "rb") as fh:
                return fh.read()
        with open(archive, "rb") as fh:
            return _container_bytes(fh.read(), name)
    except OSError:
        return None


def member_bytes(archive: str, key: str) -> Optional[bytes]:
    """The bytes of one member, read whole (no scan budget), by the key the
    snapshots use: 'a/b.json', 'x.tar.xz!/c.json' inside a nested archive, or
    'd.json' for the content of a member 'd.json.gz'. None when absent."""
    parts = key.split("!/")

    def top(name: str) -> Optional[bytes]:
        return _top_member(archive, name)

    def get(read: Any, name: str) -> Optional[bytes]:
        data = read(name)
        if data is not None:
            return data
        for ext, kind in ((".gz", "gz"), (".xz", "xz")):
            packed = read(name + ext)
            if packed is not None:
                inner, status = _bounded_decompress(packed, kind, MAX_SUPP_MEMBER_BYTES)
                return inner if status == "ok" else None
        return None
    data = get(top, parts[0])
    for name in parts[1:]:
        if data is None:
            return None
        blob = data
        data = get(lambda n, blob=blob: _container_bytes(blob, n), name)
    return data


def _undo_member_change(e: Dict[str, Any], stage: str, work_dir: str, paper_dir: str, rnd: int,
                        keep_copy: Any) -> Tuple[bool, str]:
    """Put a member change the whitelist refused back the way round 0 had it,
    in the staged copy: a member left out comes back, an added one goes to the
    attic, a renamed one gets its old name, a changed data member its round-0
    bytes. Re-pack afterwards."""
    if not os.path.isdir(stage):
        return False, "no staged copy: run `apply --stage-only` first, or restore the round's supplement"
    src = _round0_supplement(work_dir, paper_dir)
    if src is None:
        return False, "round 0's supplement is not recorded (rounds.json)"
    op = e.get("op")
    names = list(e.get("members") or []) or [str(e.get("member") or "")]
    if any("!/" in n for n in names + [str(e.get("old_member") or "")]):
        return False, "a member inside a nested archive: restore the round's supplement (`restore --part supp`)"
    if op == "add":
        full = _within(stage, names[0])
        if not full or not os.path.isfile(full):
            return False, "the added member is not in the staged copy"
        dst = os.path.join(work_dir, "attic_r%d" % rnd, "undo", _safe_rel(names[0]))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(full, dst)
        return True, "the added member left the staged copy"
    if op == "rename":
        old, new = str(e.get("old_member") or ""), names[0]
        f_new, f_old = _within(stage, new), _within(stage, old)
        if not (old and f_new and f_old and os.path.isfile(f_new)) or os.path.exists(f_old):
            return False, "the renamed member cannot be given its old name in the staged copy"
        os.makedirs(os.path.dirname(f_old), exist_ok=True)
        shutil.move(f_new, f_old)
        return True, "the member has its round-0 name again"
    for name in names:  # remove, data: the round-0 bytes, as stored (a .gz member stays packed)
        target, data = name, _top_member(src, name)
        for ext in (".gz", ".xz"):
            if data is None:
                target, data = name + ext, _top_member(src, name + ext)
        full = _within(stage, target)
        if data is None or not full:
            return False, "%s is not in round 0's supplement" % name
        if os.path.isfile(full):
            keep_copy(full, "undo/supp/" + _safe_rel(target))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as fh:
            fh.write(data)
    return True, "round 0's bytes are back in the staged copy"


def _run_undo(a: Any, paper_dir: str, work_dir: str, stage: str, rnd: int, log: Dict[str, Any], log_path: str,
              red: Redactor, keep_copy: Any) -> Tuple[Dict[str, Any], int]:
    """Put back applied edits (A<round>-NNN) or edits the scan rejected (E-xxxxxxxx)."""
    ids = [x.strip() for x in str(a.undo).split(",") if x.strip()]
    done, failed, raw_done = [], [], []
    records = {r["id"]: (rn, path, d, r) for rn, path, d in _applied_logs(work_dir) for r in d.get("applied") or []}
    raw = _load_json(os.path.join(work_dir, "edits_check.raw.json")) or {}
    # why finalize asked for each undo: a layout regression's undo never blocks the item for good
    audit = _load_json(a.audit or os.path.join(paper_dir, "PAPER_HYGIENE_AUDIT.json")) or {}
    kinds = {str(u.get("id")): u.get("kind") for u in ((audit.get("details") or {}).get("undo") or [])
             if isinstance(u, dict)}
    for i in ids:
        if i in records:
            rn, path, d, r = records[i]
            if r.get("undone"):
                failed.append({"id": i, "why": "already undone"})
                continue
            if r.get("class") == "supp-remove":
                src = os.path.join(work_dir, r.get("attic") or "")
                dst = _within(stage, str(r.get("member") or ""))
                if not (dst and os.path.exists(src)):
                    failed.append({"id": i, "why": "the left-out member cannot be found in the attic"})
                    continue
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.move(src, dst)
            else:
                base = paper_dir if r.get("file") else stage
                full = _within(base, str(r.get("file") or r.get("member") or ""))
                if not full or not os.path.isfile(full):
                    failed.append({"id": i, "why": "the file is gone"})
                    continue
                with open(full, "rb") as fh:
                    text, enc = _decode_text(fh.read())
                needle = (r.get("left") or "") + (r.get("after") or "") + (r.get("right") or "")
                if text.count(needle) != 1:
                    failed.append({"id": i, "why": "the text around the edit changed since; restore a round instead"})
                    continue
                keep_copy(full, "undo/" + _safe_rel(r.get("file") or r.get("member") or ""))
                text = text.replace(needle, (r.get("left") or "") + (r.get("before") or "") + (r.get("right") or ""), 1)
                _write_text_as(full, text, enc)
            r["undone"] = {"round": rnd, "reason": a.reason or "undone"}
            if kinds.get(i):
                r["undone"]["kind"] = kinds[i]
            _write_atomic(path, json.dumps(d, ensure_ascii=False, indent=1) + "\n")
            done.append({"id": i, "group": r.get("group"), "key": r.get("key")})
        elif i in raw:
            e = raw[i]
            if e.get("kind") != "paper" and e.get("op") != "edit":
                # a member change (left out, added, renamed, a data value): round 0's member, in the staged copy
                ok, why = _undo_member_change(e, stage, work_dir, paper_dir, rnd, keep_copy)
                if not ok:
                    failed.append({"id": i, "why": why})
                    continue
                done.append({"id": i, "op": e.get("op"), "how": why})
                raw_done.append({"id": i, "round": rnd, "reason": a.reason or "rejected member change"})
                continue
            base = paper_dir if e.get("kind") == "paper" else stage
            full = _within(base, str(e.get("file") or e.get("member") or ""))
            text, enc = (None, "utf-8")
            if full and os.path.isfile(full):
                with open(full, "rb") as fh:
                    text, enc = _decode_text(fh.read())
            if text is None or not e.get("after") or text.count(e["after"]) != 1:
                failed.append({"id": i, "why": "the edited text is not found exactly once; restore a round instead"})
                continue
            keep_copy(full, "undo/" + _safe_rel(e.get("file") or e.get("member") or ""))
            _write_text_as(full, text.replace(e["after"], e.get("before") or "", 1), enc)
            done.append({"id": i})
            raw_done.append({"id": i, "round": rnd, "reason": a.reason or "rejected edit"})
        else:
            failed.append({"id": i, "why": "unknown id"})
    if raw_done:  # re-read: the loop above may have rewritten this round's log
        cur = _load_json(log_path) or log
        cur.setdefault("undone", []).extend(raw_done)
        _write_atomic(log_path, json.dumps(cur, ensure_ascii=False, indent=1) + "\n")
    return {"tool": TOOL, "command": "apply", "round": rnd, "undone": done, "failed": failed}, (1 if failed else 0)


_DRAFT_PREP_RE = re.compile(r"(?:\b(?:on|with|using|via|under|in|at|from|by|into)\s+|,\s*)$", re.I)
_DRAFT_WRAP_RE = re.compile(r"\\(?:texttt|path|url|emph|textit|textbf|code)\{$")


def _unique_context(text: str, s: int, e: int, limit: int = 160) -> Tuple[int, int]:
    """The smallest stretch around text[s:e], grown by whole words, that occurs
    once in the text (an edit's `before` must)."""
    a, b = s, e
    while text.count(text[a:b]) != 1 and (a > 0 or b < len(text)) and (b - a) < limit + (e - s):
        m = re.search(r"\S+\s*$", text[max(0, a - 40):a])
        a = max(0, a - 40) + m.start() if m and a > 0 else max(0, a - 1)
        m2 = re.match(r"\s*\S+", text[b:b + 40])
        b = b + m2.end() if m2 else min(len(text), b + 1)
    return a, b


def _draft_deletion(text: str, s: int, e: int) -> Optional[Tuple[str, str]]:
    """(before, after) of deleting text[s:e] from a source: a wrapper command
    whose argument it is goes with it, so does a preposition or comma that
    leads it in, and one of the spaces around it; the before is unique."""
    if _DRAFT_WRAP_RE.search(text[max(0, s - 12):s]) and text[e:e + 1] == "}":
        s = s - len(_DRAFT_WRAP_RE.search(text[max(0, s - 12):s]).group(0))
        e += 1
    s, e = _pair_brackets(text, s, e)
    line_start = text.rfind("\n", 0, s) + 1
    m = _DRAFT_PREP_RE.search(text[line_start:s])
    lead = text[line_start:line_start + m.start()].rstrip() if m else ""
    if m and lead and not lead.endswith((".", ":", "!", "?")):  # never a sentence's first word
        s = line_start + m.start()
    if s > 0 and text[s - 1] in " \t" and (e >= len(text) or text[e] in " \t\n,.;:)"):
        s -= 1
    a, b = _unique_context(text, s, e)
    if text.count(text[a:b]) != 1:
        return None
    before = text[a:b]
    return before, before[:s - a] + before[e - a:]


# ─── Fragment drafts: the whole leak, its marks, one edit per sentence ───────
# A fragment item's draft takes the whole leak in the source, not the queue's
# anchor alone: the count, maker, memory, and device noun of a hardware model
# ("4$\times$ Acme Z9-48GB cards"), the quantifier of a compute amount ("about
# 2.5 GPU-hours"), a wrapper command, the host after a path ("on \texttt{box07}"),
# the product name after a framework; then the marks it leaves (a bracket pair it
# empties, the separator of a list it leaves: "(X, y)" -> "(y)", "(y, X)" ->
# "(y)"), and the article or preposition that introduced it ("on\na X"); a
# preposition that opens the sentence goes only with the comma that closes its
# phrase (the next word then starts the sentence), a later item of a list takes
# its "and" ("with A and X." -> "with A."), and a leak a conjunction joins to
# what follows ("on X and the grid on Y") is for a person, unless a verb follows
# ("on X and saved the logs"), as is one a conjunction joins to what precedes
# (on the line before too) when "and X" does not close a list without commas
# ("time and\nX on each arm", "A, B and X."). Every deletion of the queue in one sentence (a note's line in the
# supplement) is drafted as one edit. Before a draft is written, the sentence as
# it would be left is read: residue (deletion_residue, the apply gate) and what
# only a draft can see — a verb left without the place or the means it named
# ("… was served."), a preposition left at the start, a deletion joined to what
# follows by a conjunction — make the whole sentence go when what is left says
# nothing and no exclusion stops it (_whole_sentence_if_skeleton, as `apply`
# itself extends); otherwise there is no draft, and the item is listed
# (`unwritten`; finalize puts it in the plan) with the whole sentence as the
# deletion would leave it. A hardware word that names a measured quantity or
# sits in a heading is never drafted.
_SRC_TIMES = r"(?:\$\s*\\times\s*\$|\\texttimes(?:\{\})?|\\times(?![A-Za-z])|×|x)"
_HW_COUNT_WORDS = (r"(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|sixteen|thirty-two|"
                   r"sixty-four|single|dual|quad)")
_SRC_HW_LEFT_RE = re.compile(r"(?:(?<![\w.])(?:\d+|(?i:" + _HW_COUNT_WORDS + r"))\s*(?:" + _SRC_TIMES + r"\s*)?"
                             r"|(?<![\w-])(?:NVIDIA|Nvidia|AMD|Intel|Tesla|Google|Apple)\s+)$")
_SRC_HW_RIGHT_RE = re.compile(r"-\d+\s*(?:GB|GiB|TB)\b|[ \t]+\d+\s*(?:GB|GiB|TB)\b|[ \t]+(?:GPUs?|TPUs?|NPUs?|"
                              r"accelerators?|cards?|devices?|cores?|CPUs?|nodes?)\b")
_SRC_QTY_LEFT_RE = re.compile(r"(?<![\w-])(?:about|around|approximately|roughly|nearly|almost|~|\$\\sim\$|"
                              r"\\textasciitilde(?:\{\})?)\s*$", re.I)
_SRC_HOST_RIGHT_RE = re.compile(r"[ \t]+(?:on|at)[ \t]+(?:\\texttt\{)?[a-z][a-z-]*\d[a-z0-9-]*\}?", re.I)
_SRC_WRAP_RE = re.compile(r"\\(?:texttt|path|url|emph|textit|textbf|code)\s*\{$")
_SRC_ACCOUNT_LEFT_RE = re.compile(r"(?:(?<![\w.-])(?:ssh|scp|sftp|rsync)\s+(?:-{1,2}[\w-]+(?:\s+\S+)?\s+)*)?"
                                  r"(?<![\w.@-])[\w.-]+@$")
_LEAD_WORD_RE = re.compile(r"(?<![\w-])(on|using|with|via|under|across|over|at|from|by|into|in|a|an|the|one|single)"
                           r"(\s*\n[ \t]*(?:#+|//|%+)?[ \t]*|[ \t]+)$", re.I)
_LEAD_PREPOSITIONS = frozenset("on using with via under across over at from by into in".split())
_CONNECT_GAP_RE = re.compile(r"[\s,;]*(?:(?:and|or|with|&|\\&)[\s,;]*)?", re.I)
_DRAFT_CHECKS_HW = ("ENG-HW", "ENG-QTY", "SUPP-HW")
# a leak beside a coordinator (on the same line or across one line break): "… and X." takes its "and";
# "X and …" and "… and X on …" are for a person unless a verb follows
_COORD_AFTER_RE = re.compile(r"(?:[ \t]+|[ \t]*\n[ \t]*)(?:and|or|nor|but)(?![\w-])", re.I)
_COORD_AFTER_VERB_RE = re.compile(r"(?:[ \t]+|[ \t]*\n[ \t]*)(?:and|or)[ \t]+[a-z]+ed\b")
_COORD_BEFORE_RE = re.compile(r"[ \t]+(?:and|or)(?:[ \t]+|[ \t]*\n[ \t]*)$", re.I)
_CLAUSE_END_AFTER_RE = re.compile(r"[ \t~]*(?:[.,;:!?)\]}(\[]|\n|$|\\(?:ref|cite|eqref|autoref|cref|Cref)\b)")
# a word that needs the place or the means a deleted prepositional phrase named ("was served [on X].")
_NEEDS_COMPLEMENT_RE = re.compile(r"(?<![\w-])(?:[A-Za-z]+(?:ed|en)|run|runs|ran|sit|sits|sat|lie|lies|live|lives|"
                                  r"reside|resides|kept|built|put|set|held|hosted|stored|placed|located)\s*$")
_SRC_PATH_CHARS_RE = re.compile(r"[\w./~-]")
_SRC_CD_LEFT_RE = re.compile(r"(?<![\w.-])cd[ \t]+$")
_SPAN_PREP_RE = re.compile(r"(?:on|using|with|via|under|across|over|at|from|by|into|in)\s", re.I)
# a noun phrase the leak heads: a determiner and one or two words before it, and after it the end of the
# clause, a preposition, a conjunction, or a verb ("on the same X with …", "used the fast X.")
_DET_BEFORE_RE = re.compile(r"(?<![\w-])(?:the|a|an|this|that|these|those|its|their|our|each|every|no|any|some)"
                            r"[ \t]+(?:[\w-]+[ \t]+){1,2}$", re.I)
_HEAD_AFTER_RE = re.compile(r"[ \t]*(?:[.,;:!?)\]}]|\n|$|(?:with|on|at|in|for|of|to|by|from|and|or|is|are|was|"
                            r"were|has|have|had)(?![\w-]))", re.I)
# A bare hardware word (CPU, GPU, … with no count, maker, or model) is cut only where it stands apart from the
# grammar of its sentence: alone in brackets or as an item of a bracketed list, as the object of a preposition
# (which goes with it), or as the last item of a list at the clause end ("calls no model or GPU."). As a
# subject ("then the GPU writes …"), a modifier ("the GPU side", "no spare GPU slot"), or half a compound
# ("no-GPU", "toy/GPU") it is part of the sentence, and a person rewords it.
_BARE_HW_RE = re.compile(r"(?:CPU|GPU|TPU|NPU|accelerator|device|card|node|core)s?", re.I)
_BARE_LEAD_RE = re.compile(r"(?<![\w-])(?:on|using|with|via|under|across|over|at|by|from|into|in|without)"
                           r"(?:[ \t]*\n[ \t]*(?:#+|//|%+)?[ \t]*|[ \t]+)"
                           r"(?:(?:a|an|the|one|single|any|\d+|two|three|four|eight)\s+){0,2}$", re.I)
_BARE_COORD_RE = re.compile(r"(?<![\w-])(?:and|or|nor)\s+$", re.I)
_BARE_END_RE = re.compile(r"[ \t]*(?:[.,;:!?)\]）]|\\(?:ref|cite)\b|$|\n[ \t]*(?:\n|$))")


def _bare_hw_problem(text: str, s: int, e: int) -> Optional[str]:
    """Why the bare hardware word text[s:e] cannot be cut from its sentence
    (see above), or None. Its line and the line before it (a soft break of the
    same paragraph or note) are read."""
    if text[s - 1:s] in ("-", "/") or text[e:e + 1] in ("-", "/"):
        return "the hardware word is half of a compound word"
    lo = text.rfind("\n", 0, s) + 1
    if lo > 1 and text[lo - 2:lo - 1] != "\n":
        prev = text.rfind("\n", 0, lo - 1) + 1
        if text[prev:lo - 1].strip():
            lo = prev
    hi = text.find("\n", e)
    hi = len(text) if hi < 0 else hi
    before, after = text[lo:s], text[e:hi]
    lt, rt = before.rstrip(" \t"), after.lstrip(" \t")
    in_brackets = before.count("(") + before.count("[") > before.count(")") + before.count("]") and \
        re.search(r"[)\]]", after) is not None
    if in_brackets and lt[-1:] in ("(", "[", ",", ";") and rt[:1] in (")", "]", ",", ";"):
        return None
    if _BARE_LEAD_RE.search(before) or (_BARE_END_RE.match(text, e) and _BARE_COORD_RE.search(before)):
        return None
    return ("a bare hardware word is part of its sentence here (a subject, a modifier, a predicate): a person "
            "rewords it")


def _src_leak_span(text: str, s: int, e: int, check: str) -> Tuple[int, int]:
    """text[s:e] (a queue anchor in the source) widened over the whole leak it
    belongs to (see above)."""
    if "/" in text[s:e] or check in ("ENG-PATH", "SUPP-PATH"):
        # a path matched by its words: its slashes and dots go with it ("/home/u/w", not "home/u/w")
        while s > 0 and (text[s - 1] in "/~" or (text[s - 1] == "." and text[s:s + 1] in ("/", "."))):
            s -= 1
        while e < len(text) and _SRC_PATH_CHARS_RE.match(text[e]) and not (
                text[e] == "." and (e + 1 >= len(text) or text[e + 1].isspace())):
            e += 1
    for _ in range(3):  # a wrapper command whose argument it is
        m = _SRC_WRAP_RE.search(text, max(0, s - 14), s)
        if m and text[e:e + 1] == "}":
            s, e = m.start(), e + 1
        else:
            break
    if check in _DRAFT_CHECKS_HW:
        for _ in range(8):
            changed = False
            m = _SRC_HW_LEFT_RE.search(text, max(0, s - 40), s)
            if m and m.start() < s:
                s, changed = m.start(), True
            m = _SRC_HW_RIGHT_RE.match(text, e)
            if m and m.end() > e:
                e, changed = m.end(), True
            else:
                ws = re.match(r"[ \t]+", text[e:e + 4])
                hw = _HW_RE.match(text, e + ws.end()) if ws else None
                if hw and hw.end() > e:
                    e, changed = hw.end(), True
            if not changed:
                break
        m = _SRC_QTY_LEFT_RE.search(text, max(0, s - 24), s)
        if m:
            s = m.start()
    elif check == "ENG-FW":
        m = _FW_RIGHT_RE.match(text, e)
        if m:
            e = m.end()
    if check in ("ENG-PATH", "SUPP-PATH") or (check in ("SUPP-TEXT", "ENG-OPS") and "/" in text[s:e]):
        m = _SRC_HOST_RIGHT_RE.match(text, e)   # the host after a path ("… on box07")
        if m:
            e = m.end()
        m = _SRC_CD_LEFT_RE.search(text, max(0, s - 8), s)
        if m:  # "cd <path> && " goes as one: the command keeps nothing without its directory
            s = m.start()
            m2 = re.match(r"[ \t]*(?:&&|;)[ \t]*", text[e:e + 8])
            if m2:
                e += m2.end()
    if check in ("SUPP-TEXT", "ENG-NET", "ENG-OPS", "ENG-PATH"):
        # a host takes the account in front of it, and the command that logs in with it ("ssh ada@<host>")
        m = _SRC_ACCOUNT_LEFT_RE.search(text, max(0, s - 60), s)
        if m:
            s = m.start()
    return s, e


def _take_marks(text: str, s: int, e: int) -> Tuple[int, int]:
    """A deletion widened over the marks it would leave: a bracket pair it
    empties (and one space before it), the separator after it at the head of a
    bracketed list, the one before it at the end of a list or in its middle."""
    op = re.search(r"([(\[（])[ \t]*$", text[max(0, s - 4):s])
    cl = re.match(r"[ \t]*([)\]）])", text[e:e + 4])
    pairs = {"(": ")", "[": "]", "（": "）"}
    if op and cl and pairs[op.group(1)] == cl.group(1):
        s, e = s - len(op.group(0)), e + len(cl.group(0))
        if s > 0 and text[s - 1] in " \t" and op.group(1) != "（":
            s -= 1
        return s, e
    sep_after = re.match(r"[ \t]*[,;，；][ \t]*", text[e:e + 6])
    sep_before = re.search(r"[ \t]*[,;，；][ \t]*$", text[max(0, s - 6):s])
    if op and sep_after:
        return s, e + len(sep_after.group(0))         # "(X, y)" -> "(y)"
    if cl and sep_before:
        return s - len(sep_before.group(0)), e        # "(y, X)" -> "(y)"
    if sep_before and sep_after:
        return s - len(sep_before.group(0)), e        # "a, X, b" -> "a, b"
    return s, e


def _draft_cut(text: str, s: int, e: int, unit_start: int) -> Tuple[int, int, Optional[int], Optional[str]]:
    """A leak's deletion as a draft takes it: (start, end, the position of a
    letter to capitalize or None, why it cannot be cut cleanly or None).
    Beside a coordinator: a later item of a list without commas takes its "and"
    ("with A and X." -> "with A."); any other conjunction right before it (on
    the line before too) or right after it leaves the decision to a person,
    unless a verb follows ("on X and saved the logs"). Otherwise the article or preposition that
    introduced it goes with it (at most two words, across a line break of the
    same paragraph or note), and a comma before it; a preposition that opens
    the sentence goes only with the comma that closes its phrase (the next
    word is capitalized), else a person decides."""
    end_after = _CLAUSE_END_AFTER_RE.match(text, e)
    mb = _COORD_BEFORE_RE.search(text, max(unit_start, s - 16), s)
    if mb:
        if end_after and "," not in text[unit_start:mb.start()] and text[unit_start:mb.start()].strip():
            return mb.start(), e, None, None                   # "with A and X." -> "with A."
        # "time and X on each stream" -> "time and on each stream", "A, B and X." -> "A, B and.": the
        # conjunction loses what it joined, and only a rewrite ("A and B") mends the list
        return s, e, None, "a conjunction joins it to what precedes"
    # "with X and the rest" may join two objects or two clauses ("on X and the grid on Y"): a person reads it
    if _COORD_AFTER_RE.match(text, e) and not _COORD_AFTER_VERB_RE.match(text, e):
        return s, e, None, "a conjunction joins it to what follows"
    # a leak that is itself a prepositional phrase ("on one core") is the means or the place it names
    took_prep = _SPAN_PREP_RE.match(text, s) is not None
    for _ in range(2):
        m = _LEAD_WORD_RE.search(text, max(unit_start, s - 24), s)
        if not m:
            break
        lead = text[unit_start:m.start()].rstrip()
        lead = _NOTE_MARK_RE.sub("", lead).strip() if "\n" not in lead else lead
        if m.group(2).count("\n") > 1:
            break
        if not lead or lead.endswith((".", ":", "!", "?", "(", "[")):
            if m.group(1).lower() not in _LEAD_PREPOSITIONS:
                break                                          # "The X cluster runs …" -> "The cluster runs …"
            comma = re.match(r"[ \t]*,[ \t]*", text[e:])
            if comma and text[e + comma.end():e + comma.end() + 1].isalpha():
                k = e + comma.end()
                return m.start(), k, m.start(), None           # "On X, one sweep …" -> "One sweep …"
            return s, e, None, "a preposition would be left at the start of the sentence"
        s, took_prep = m.start(), took_prep or m.group(1).lower() in _LEAD_PREPOSITIONS
    m = re.search(r",[ \t]*$", text[max(unit_start, s - 3):s])
    if m and text[unit_start:s - len(m.group(0))].strip():
        s -= len(m.group(0))
    if took_prep and _CLAUSE_END_AFTER_RE.match(text, e) and \
            _NEEDS_COMPLEMENT_RE.search(text[max(unit_start, s - 40):s]):
        return s, e, None, "a verb would be left without the place or the means it named"
    if not took_prep and _DET_BEFORE_RE.search(text[max(unit_start, s - 40):s]) and _HEAD_AFTER_RE.match(text, e):
        # "on the same X, …", "used the fast X." -> "on the same, …": the leak was the noun its words described
        return s, e, None, "a noun phrase would lose its head"
    return s, e, None, None


def _one_space(text: str, s: int, e: int) -> Tuple[int, int]:
    """One of the spaces around a deleted run goes with it (both, between two
    CJK characters)."""
    if 0 < s and e < len(text) and text[s - 1] == " " and text[e] == " " and _CJK_RE.match(text[s - 2:s - 1] or "x") \
            and _CJK_RE.match(text[e + 1:e + 2] or "x"):
        return s - 1, e + 1
    if s > 0 and not text[text.rfind("\n", 0, s) + 1:s].strip() and e < len(text) and text[e] in " \t":
        return s, e + 1   # the first word of an indented line: the indentation stays, the space after goes
    if s > 0 and text[s - 1] in " \t" and (e >= len(text) or text[e] in " \t\n,.;:)]）"):
        return s - 1, e
    if (s == 0 or text[s - 1] in "\n(（[") and e < len(text) and text[e] in " \t":
        return s, e + 1
    return s, e


def _soft_wrap_start(text: str, u0: int, kind: str, place: str) -> int:
    """Where a document note's sentence really starts when its line goes on
    with a sentence begun on the line before (a soft line break of one
    paragraph): the start of that line; else u0."""
    if kind != "supplement" or _member_kind(place) != "doc" or u0 == 0 or text[u0 - 1] != "\n":
        return u0
    p0 = text.rfind("\n", 0, u0 - 1) + 1
    prev = text[p0:u0 - 1]
    nl = text.find("\n", u0)
    cur = text[u0:nl if nl >= 0 else len(text)]
    if not prev.strip() or _NOTE_END_RE.search(prev) or _ITEM_START_RE.match(cur.lstrip()) or \
            prev.lstrip().startswith(("#", "|", "```")):
        return u0
    return p0


def _note_line_ok(text: str, s: int, e: int, member: str) -> bool:
    """Every line text[s:e] touches is one the loop may edit: a document's
    line, or a line of code that is a note and nothing else (_code_note_lines:
    a comment line, a docstring line — never a template in a string)."""
    first = text.count("\n", 0, s) + 1
    last = text.count("\n", 0, max(s, e - 1)) + 1
    return _note_lines_ok(text, first, min(last, text.count("\n") + 1), member)


def _region_is_notes(text: str, s: int, e: int, member: str) -> bool:
    """The region text[s:e] a change removes or replaces lies on lines the loop
    may edit (_note_line_ok); a region that starts with the line break ending
    the line before it starts on the next line."""
    if e > s + 1 and text[s:s + 1] == "\n":
        s += 1
    return _note_line_ok(text, s, max(e, s + 1), member)


def _draft_unit_skeleton(text: str, new_text: str, a: int, n_after: int, checks: Iterable[str], rel: str,
                         paper_dir: str, det: Dict[str, Any], ec: EditCheck,
                         anchors: Sequence[Tuple[str, Sequence[str]]]) -> Optional[Tuple[str, str, int]]:
    """What `apply`'s pass after the round would do with a paper sentence the
    draft's deletion leaves: when the sentence is then a skeleton by the
    pure-leak rules (unit_skeleton_reason, the families of the deleted leaks)
    and no exclusion stops it, the text with the whole sentence deleted, the
    reason, and where it was (as _whole_sentence_if_skeleton); else None."""
    sent = next((x for x in _tex_sentences(new_text) if x["start"] <= a + n_after and a <= x["end"]), None)
    if sent is None or not (sent["start"] <= a <= sent["end"]):
        return None
    p = sent["printed"]
    kinds = {_unit_kind(c) for c in checks if c in SENTENCE_FIX_CHECKS} or {"eng"}
    extra = [str(x) for x in ((det.get("policy") or {}).get("skeleton_result_words") or [])]
    reason = unit_skeleton_reason(p.rstrip(" .!?"), [False] * len(p), kinds, sent["marks"], extra)
    if not reason:
        return None
    region: Tuple[Optional[str], Optional[str]] = ("body", None)
    if paper_dir and rel:
        region = det.setdefault("_regions", _source_regions(paper_dir)).get((rel, sent["line"]), ("body", None))
    if rel and _STATEMENT_FILE_RE.search(os.path.splitext(os.path.basename(rel))[0]):
        region = ("end_matter", region[1])
    if _unit_exclusion(p, [False] * len(p), sent, region, None,
                       _paragraph_context(new_text, sent["start"], sent["end"])):
        return None
    delta = len(text) - len(new_text)
    s0, e0 = sent["start"], sent["end"] + (delta if sent["end"] >= a + n_after else 0)
    sentence = text[s0:e0]
    if not sentence.strip() or _REF_CMD_RE.search(sentence) or _CITE_CMD_RE.search(sentence):
        return None
    if verify_change(sentence, "", ec, "paper", False, anchors=anchors)["verdict"] != "ok":
        return None
    return text[:s0] + text[e0:], reason, s0


def draft_fragment_units(text: str, occs: Sequence[Dict[str, Any]], kind: str, place: str, ec: EditCheck,
                         anchors: Sequence[Tuple[str, Sequence[str]]], det: Dict[str, Any],
                         paper_dir: str = "") -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """The drafts of every fragment item's occurrences in one file (`kind`
    paper) or member (supplement): (edits, manual). An edit is {group,
    covers, before, after, how}; a manual entry {groups, line, why, sentence,
    after} lists an occurrence no clean edit takes (residue the whole sentence
    cannot answer, a hardware word that is a metric or a heading's wording, a
    code line). `occs` are {group, check, s, e} in `text`."""
    edits: List[Dict[str, Any]] = []
    manual: List[Dict[str, Any]] = []
    units: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
    tex_sents = _tex_sentences(text) if kind == "paper" else []

    def unit_of(a_: int, b_: int) -> Tuple[int, int]:
        # a source sentence as the pure-leak rules read it (never a heading or a command before it), else the
        # stretch between sentence ends
        rec = next((x for x in tex_sents if x["start"] <= a_ < x["end"]), None)
        if rec is not None and b_ <= rec["end"]:
            return rec["start"], rec["end"]
        return _sentence_span(text, a_, b_, kind)
    for o in occs:
        s0, e0 = int(o["s"]), int(o["e"])
        if o["check"] in _DRAFT_CHECKS_HW:
            usage = _hw_usage(text, s0, e0, heading=None if (kind == "paper" or _member_kind(place) == "doc")
                              else False)
            if usage:
                u0, u1 = unit_of(s0, e0)
                hs, he = _one_space(text, *_take_marks(text, s0, e0))
                manual.append({"groups": [o["group"]], "line": text.count("\n", 0, s0) + 1,
                               "why": "the hardware word %s" % ("names a measured quantity (a metric of the study)"
                                                                if usage == "metric" else "sits in a heading"),
                               "usage": usage, "sentence": text[u0:u1].strip(),
                               "after": (text[u0:hs] + text[he:u1]).strip() if usage == "title" else None})
                continue
        s, e = _src_leak_span(text, s0, e0, o["check"])
        if o["check"] in _DRAFT_CHECKS_HW and _BARE_HW_RE.fullmatch(text[s:e]):
            why_bare = _bare_hw_problem(text, s, e)
            if why_bare:
                u0, u1 = unit_of(s, e)
                hs, he = _one_space(text, s, e)
                manual.append({"groups": [o["group"]], "line": text.count("\n", 0, s) + 1, "why": why_bare,
                               "sentence": text[u0:u1].strip(), "after": (text[u0:hs] + text[he:u1]).strip()})
                continue
        u = unit_of(s, e)
        units.setdefault(u, []).append(dict(o, s=s, e=e))
    for (u0, u1), sps in sorted(units.items()):
        sps.sort(key=lambda x: (x["s"], -x["e"]))
        merged: List[List[Any]] = []
        for sp in sps:
            if merged and (sp["s"] <= merged[-1][1] or _CONNECT_GAP_RE.fullmatch(text[merged[-1][1]:sp["s"]])):
                merged[-1][1] = max(merged[-1][1], sp["e"])
                if sp["group"] not in merged[-1][2]:
                    merged[-1][2].append(sp["group"])
            else:
                merged.append([sp["s"], sp["e"], [sp["group"]]])
        cuts: List[Tuple[int, int, bool]] = []
        groups: List[str] = []
        problems: List[str] = []
        floor = _soft_wrap_start(text, u0, kind, place)
        for s, e, gs in merged:
            s1, e1 = _take_marks(text, s, e)
            cap, prob = False, None
            if (s1, e1) == (s, e):  # no bracket or list mark around it: its coordinator, article, preposition
                s1, e1, cap_at, prob = _draft_cut(text, s, e, floor)
                cap = cap_at is not None
            s1, e1 = _pair_brackets(text, s1, e1)
            if not cap:
                s1, e1 = _one_space(text, s1, e1)
            if prob and prob not in problems:
                problems.append(prob)
            if cuts and s1 < cuts[-1][1]:
                s1 = cuts[-1][1]
            if s1 < e1:
                cuts.append((s1, e1, cap))
            groups += [g for g in gs if g not in groups]
        if not cuts:
            continue
        a, b = cuts[0][0], cuts[-1][1]
        if a < u0:  # a lead word on the line before (a soft line break): the unit starts with that line
            u0 = text.rfind("\n", 0, a) + 1
        if b > u1:
            nl = text.find("\n", b)
            u1 = len(text) if nl < 0 else nl
        new_region, pos, up = [], a, False
        for s, e, cap in cuts:
            piece = text[pos:s]
            new_region.append(piece[:1].upper() + piece[1:] if up else piece)
            pos, up = e, cap
        piece = text[pos:b]
        new_region.append(piece[:1].upper() + piece[1:] if up else piece)
        if up and not piece:  # the word to capitalize starts after the edit's end: take it into the edit
            m_w = re.match(r"\w", text[b:])
            if m_w:
                new_region[-1] = text[b].upper()
                b += 1
        before, after = text[a:b], "".join(new_region)
        new_text = text[:a] + after + text[b:]
        line_no = text.count("\n", 0, a) + 1
        n_u0, n_u1 = u0, u1 - (len(before) - len(after))
        old_unit, new_unit = text[u0:u1], new_text[n_u0:max(n_u0, n_u1)]
        if kind == "supplement" and not _note_line_ok(text, a, b, place):
            manual.append({"groups": groups, "line": line_no, "why": "a code line (the loop edits notes only)",
                           "sentence": old_unit.strip(), "after": new_unit.strip()})
            continue
        residue = deletion_residue(old_unit, new_unit)
        ext = _whole_sentence_if_skeleton(text, new_text, a, before, after, kind, ec, anchors,
                                          member=place if kind == "supplement" else "", det=det,
                                          rel=place if kind == "paper" else "", paper_dir=paper_dir)
        if ext is None and kind == "paper" and (residue or problems):
            # what apply's pass after the round would take: the sentence is a skeleton by the pure-leak rules
            ext = _draft_unit_skeleton(text, new_text, a, len(after), [str(sp["check"]) for sp in sps], place,
                                       paper_dir, det, ec, anchors)
        if ext is not None:
            gone = len(text) - len(ext[0])
            w0 = ext[2]
            if kind == "supplement" and not _region_is_notes(text, w0, w0 + gone, place):
                manual.append({"groups": groups, "line": line_no, "why": "a code line (the loop edits notes only)",
                               "sentence": old_unit.strip(), "after": new_unit.strip()})
                continue
            edits.append({"group": groups[0], "covers": groups[1:], "line": text.count("\n", 0, w0) + 1,
                          "s": w0, "e": w0 + gone, "whole": True,
                          "how": "whole sentence: %s" % ext[1]})
            continue
        if residue or problems:
            manual.append({"groups": groups, "line": line_no, "why": "the deletion would leave residue (%s) and "
                           "the rest of the sentence says more than the leak" % "; ".join((residue + problems)[:2]),
                           "sentence": old_unit.strip(), "after": new_unit.strip(), "residue": residue + problems})
            continue
        edits.append({"group": groups[0], "covers": groups[1:], "line": line_no, "s": a, "e": b, "after": after,
                      "how": "the whole leak%s" % (" of %d items, one sentence" % len(groups) if len(groups) > 1
                                                   else "")})
    for ed in edits:
        s, e = ed.pop("s"), ed.pop("e")
        after = "" if ed.pop("whole", False) else ed.pop("after")
        ed.pop("after", None)
        x0, x1 = _unique_context(text, s, e)
        if text.count(text[x0:x1]) != 1:
            manual.append({"groups": [ed["group"]] + ed["covers"], "line": ed["line"],
                           "why": "the text around it occurs more than once", "sentence": text[s:e].strip(),
                           "after": None})
            ed["drop"] = True
            continue
        ed["before"] = text[x0:x1]
        ed["after"] = text[x0:s] + after + text[e:x1]
    return [ed for ed in edits if not ed.get("drop")], manual


def _anchor_spans(text: str, anchor: str, lo: int, hi: int) -> List[Tuple[int, int]]:
    """Every occurrence of a matched text inside text[lo:hi], never inside a
    longer word ('CPU' is not the first letters of 'CPUs')."""
    if not anchor:
        return []
    pre = r"(?<![A-Za-z0-9_])" if anchor[:1].isalnum() else ""
    post = r"(?![A-Za-z0-9_])" if anchor[-1:].isalnum() else ""
    return [(m.start(), m.end()) for m in re.finditer(pre + re.escape(anchor) + post, text[:hi]) if m.start() >= lo]


def fragment_drafts(queue: Sequence[Dict[str, Any]], read_paper: Any, read_member: Any, ec: EditCheck,
                    det: Dict[str, Any], paper_dir: str = "") -> Dict[str, Any]:
    """Drafts of the queue's fragment items (`delete` in the paper, `supp-delete`
    in the supplement), every occurrence of every item in one file read at once
    (draft_fragment_units): {edits: [(place, kind, edit)], manual: [(place, kind,
    entry)], missing: [group]}. A fragment inside a queued delete-sentence item
    is taken by it and drafts nothing. `read_paper(rel)` and
    `read_member(member)` give a text or None."""
    taken = [(str(g.get("file")), {str(x) for x in g.get("lines") or []}, _norm_key(g.get("deleted")))
             for g in queue if g.get("fix_class") == "delete-sentence"]
    anchors_all = _queue_anchors([g for g in queue if g.get("fix_class") in ("delete", "supp-delete")])
    occ: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    texts: Dict[Tuple[str, str], str] = {}
    found: Set[str] = set()
    for g in queue:
        cls = g.get("fix_class")
        if cls == "delete":
            for rel, line in _where_lines(g):
                t_ = read_paper(rel)
                if t_ is None:
                    continue
                texts[("paper", rel)] = t_
                for anchor in _item_anchors(g):
                    if any(rel == f_ and "%s:%s" % (rel, line) in lines_ and _norm_key(anchor) in deleted
                           for f_, lines_, deleted in taken):
                        found.add(g["group"])
                        continue
                    loc = _locate(t_, anchor, line)
                    if loc is None:
                        continue
                    found.add(g["group"])
                    occ.setdefault(("paper", rel), []).append({"group": g["group"], "check": g.get("check"),
                                                               "s": loc[0], "e": loc[1]})
        elif cls == "supp-delete":
            for w in g.get("lines") or []:
                m = re.match(r"^(.*):(\d+)$", str(w))
                if not m:
                    continue
                member, line = m.group(1), int(m.group(2))
                t_ = read_member(member)
                if t_ is None:
                    continue
                texts[("supplement", member)] = t_
                starts = _line_starts(t_)
                if not 0 < line <= len(starts):
                    continue
                lo = starts[line - 1]
                hi = t_.find("\n", lo)
                hi = len(t_) if hi < 0 else hi
                for anchor in _item_anchors(g):
                    for s, e in _anchor_spans(t_, anchor, lo, hi):
                        found.add(g["group"])
                        occ.setdefault(("supplement", member), []).append(
                            {"group": g["group"], "check": g.get("check"), "s": s, "e": e})
    out: Dict[str, Any] = {"edits": [], "manual": [], "missing": []}
    for (kind, place), items in sorted(occ.items()):
        seen: Set[Tuple[str, int, int]] = set()
        uniq = []
        for o in items:
            k = (o["group"], o["s"], o["e"])
            if k not in seen:
                seen.add(k)
                uniq.append(o)
        edits, manual = draft_fragment_units(texts[(kind, place)], uniq, kind, place, ec, anchors_all, det,
                                             paper_dir)
        out["edits"] += [(place, kind, ed) for ed in edits]
        out["manual"] += [(place, kind, mn) for mn in manual]
    out["missing"] = [g["group"] for g in queue if g.get("fix_class") in ("delete", "supp-delete")
                      and g["group"] not in found]
    return out


def _locate(text: str, needle: str, line: Optional[int]) -> Optional[Tuple[int, int]]:
    """Where a printed match (PDF spelling) is in a source, near `line`: the
    words of the match with any LaTeX markup between them."""
    rx = _flex_re(re.findall(r"\w+", unicodedata.normalize("NFKC", needle or "")))
    if rx is None:
        return None
    lines = text.split("\n")

    def off(k: int) -> int:  # where 1-based line k starts
        return sum(len(x) + 1 for x in lines[:max(0, min(len(lines), k - 1))])
    if line:
        # its own line first (a match may run on to the next one), then the lines around it
        for a_, b_ in ((line, line + 1), (line - 1, line + 1)):
            m = rx.search(text, off(a_), off(b_ + 1) if b_ < len(lines) else len(text))
            if m and (a_ != line or m.start() < off(line + 1)):
                return m.start(), m.end()
    ms = list(rx.finditer(text))
    return (ms[0].start(), ms[0].end()) if len(ms) == 1 else None


def _where_lines(g: Dict[str, Any]) -> List[Tuple[str, Optional[int]]]:
    out = []
    for w in list(g.get("lines") or []) + list(g.get("where") or []):
        m = re.search(r"(?:^|\s)([^\s:]+\.(?:tex|bib|md|txt|rst|py|sh|ya?ml|json|cfg|ini|toml|r|R|m|jl|ipynb)|"
                      r"[^\s:]+/[^\s:]+):(\d+)$", str(w))
        if m and (m.group(1), int(m.group(2))) not in out:
            out.append((m.group(1), int(m.group(2))))
    return out


def run_edits_from_queue(a: Any) -> Tuple[Dict[str, Any], int]:
    """Draft the round's edits from the fix queue: the exact source edit of
    every delete-sentence item, the minimal deletion of every fragment item
    (with the preposition or comma that leads it in), the marker's note, the
    glued escape, the reference repair, the dangling cite key, the metadata
    fields emptied where they are set and the lines the item adds, the
    supplement's note fragments and junk members. Every draft is checked
    against the whitelist before it is written; what cannot be drafted is
    listed (`unwritten`) for the executor. The executor reads the draft, drops
    any edit it disagrees with, and passes the file to `apply`."""
    paper_dir = os.path.abspath(a.paper_dir)
    work_dir = os.path.abspath(a.work_dir) if a.work_dir else None
    audit_path = a.audit or os.path.join(paper_dir, "PAPER_HYGIENE_AUDIT.json")
    audit = _load_json(audit_path)
    if not isinstance(audit, dict) or audit.get("audit_skill") != SKILL_NAME:
        raise UsageError("cannot read the audit artifact %s (run finalize first)" % audit_path)
    det = audit.get("details") or {}
    red = _redactor_from_config(a.config_dir, bool(det.get("anonymous", True)))
    ec = edit_check_for(_paper_sources(paper_dir), red, None)
    stage = os.path.abspath(a.supp_stage) if getattr(a, "supp_stage", None) else (
        os.path.join(work_dir, "supp_stage") if work_dir else None)
    texts: Dict[str, Optional[str]] = {}

    def paper_text(rel: str) -> Optional[str]:
        if rel not in texts:
            full = _within(paper_dir, rel)
            texts[rel] = None
            if full and os.path.isfile(full):
                with open(full, "rb") as fh:
                    t_, enc = _decode_text(fh.read())
                texts[rel] = t_ if enc in ("utf-8", "utf-8-sig", "gb18030") else None
        return texts[rel]

    def member_text(member: str) -> Optional[str]:
        key = "supp:" + member
        if key not in texts:
            texts[key] = None
            data = None
            full = _within(stage, member) if stage else None
            if full and os.path.isfile(full):
                with open(full, "rb") as fh:
                    data = fh.read()
            elif work_dir:
                src = _round0_supplement(work_dir, paper_dir)
                data = member_bytes(src, member) if src else None
            if data is not None:
                texts[key] = _decode_text(data)[0]
        return texts[key]

    edits: List[Dict[str, Any]] = []
    unwritten: List[Dict[str, Any]] = []
    notes: List[str] = []
    # a fragment inside a queued sentence or clause deletion is taken with it: no draft of its own
    taken = [(str(g.get("file")), {str(x) for x in g.get("lines") or []}, _norm_key(g.get("deleted")))
             for g in det.get("fix_queue") or [] if g.get("fix_class") == "delete-sentence"]

    def inside_unit(rel: str, line: Optional[int], anchor: str) -> bool:
        return any(rel == f_ and "%s:%s" % (rel, line) in lines_ and _norm_key(anchor) in deleted
                   for f_, lines_, deleted in taken)

    def add(g: Dict[str, Any], where: Dict[str, Any], before: str, after: str, kind: str = "paper",
            how: str = "") -> None:
        cls = g["fix_class"]
        anchors = [(cls, _wordlist(x)) for x in _item_anchors(g) if _wordlist(x)]
        v = verify_change(before, after, ec, kind, False, target=g.get("fix_target"),
                          anchors=anchors if cls in ("delete", "delete-sentence", "marker", "supp-delete") else [])
        e = dict(where, group=g["group"], before=before, after=after)
        if v["verdict"] != "ok":
            unwritten.append({"group": g["group"], "class": cls, **where, "why": "the draft fails the whitelist: %s"
                              % v["why"]})
            return
        if any(x.get("group") == g["group"] and x.get("before") == before and x.get("file") == where.get("file")
               and x.get("member") == where.get("member") for x in edits):
            return
        e["draft"] = how or cls
        edits.append(e)

    queue_all = [g for g in det.get("fix_queue") or [] if isinstance(g, dict) and g.get("group")]
    by_group = {g["group"]: g for g in queue_all}
    # fragment items: the whole leak, its marks, one edit per sentence or note line, read before it is written
    frag = fragment_drafts(queue_all, paper_text, member_text, ec, dict(det), paper_dir)
    for place, kind, ed in frag["edits"]:
        g = by_group.get(ed["group"])
        if g is None:
            continue
        where = {"file": place} if kind == "paper" else {"member": place}
        n0 = len(edits)
        add(g, where, ed["before"], ed["after"], kind=kind, how=ed["how"])
        if len(edits) > n0 and ed.get("covers"):
            edits[-1]["covers"] = list(ed["covers"])
    for place, kind, mn in frag["manual"]:
        g = by_group.get(mn["groups"][0]) or {}
        unwritten.append({"group": mn["groups"][0], "groups": mn["groups"], "class": g.get("fix_class"),
                          ("file" if kind == "paper" else "member"): place, "line": mn.get("line"),
                          "why": "no clean deletion: %s" % mn["why"], "sentence": mn.get("sentence"),
                          "after_deletion": mn.get("after")})
    for gid in frag["missing"]:
        g = by_group.get(gid) or {}
        unwritten.append({"group": gid, "class": g.get("fix_class"), "where": g.get("where"),
                          "why": "the matched text was not found once near its line: write this edit by hand"})
    for g in queue_all:
        cls = g.get("fix_class")
        if cls == "delete-sentence":
            t_ = paper_text(str(g.get("file")))
            if t_ is None or t_.count(str(g.get("before"))) != 1:
                unwritten.append({"group": g["group"], "class": cls, "file": g.get("file"),
                                  "why": "the queued sentence is not found once in the file (re-run the scan)"})
                continue
            add(g, {"file": g["file"]}, g["before"], g["after"], how="%s: %s" % (g.get("unit"), g.get("reason")))
        elif cls == "marker":
            places = _where_lines(g)
            done = 0
            for rel, line in places:
                t_ = paper_text(rel)
                if t_ is None:
                    continue
                for anchor in _item_anchors(g):
                    if inside_unit(rel, line, anchor):
                        done += 1
                        continue
                    loc = _locate(t_, anchor, line)
                    if loc is None:
                        continue
                    s, e = loc
                    if cls == "marker":
                        op = t_.rfind("(", max(0, s - 4), s + 1)
                        cl = t_.find(")", e)
                        cmd = re.search(r"\\(?:todo|TODO|fixme|FIXME)\s*(?:\[[^\]]*\])?\s*\{$", t_[max(0, s - 20):s])
                        if op >= 0 and cl > 0 and "\n" not in t_[op:cl]:
                            s, e = op, cl + 1
                        elif cmd:
                            s = max(0, s - 20) + cmd.start()
                            _b, e = _balanced_arg(t_, t_.find("{", s))
                        else:
                            continue
                    d = _draft_deletion(t_, s, e)
                    if d:
                        add(g, {"file": rel}, d[0], d[1])
                        done += 1
            if not done:
                unwritten.append({"group": g["group"], "class": cls, "where": g.get("where"),
                                  "why": "the matched text was not found once near its line: write this edit by hand"})
        elif cls == "escape":
            done = 0
            places_e = list(_where_lines(g))
            if not places_e:
                # only the printed page is known: the one source spelling of a glued escape of this letter
                # ("see\textbackslash nTable") in the sources, if there is exactly one
                glued = str(g.get("match") or "").lstrip("\\")
                hits_e = []
                for main_tex in discover_inputs(paper_dir, [], [], False)["mains"]:
                    for path in expand_tex(main_tex, paper_dir)["files"]:
                        rel_e = _rel(path, paper_dir)
                        t_e = paper_text(rel_e) or ""
                        for m in _GLUED_ESC_SRC_WORD_RE.finditer(t_e):
                            if glued and (m.group(1) + m.group(2)).startswith(glued) and not _in_tt_arg(t_e, m.start()):
                                hits_e.append((rel_e, t_e.count("\n", 0, m.start()) + 1))
                hits_e = list(dict.fromkeys(hits_e))
                if len(hits_e) == 1:
                    places_e = hits_e
            for rel, line in places_e:
                t_ = paper_text(rel)
                if t_ is None:
                    continue
                lines = t_.split("\n")
                lo = sum(len(x) + 1 for x in lines[:max(0, line - 1)])
                hi = lo + len(lines[line - 1]) if 0 < line <= len(lines) else len(t_)
                for m in _GLUED_ESC_SRC_WORD_RE.finditer(t_, lo, hi):
                    a_, b_ = _unique_context(t_, max(lo, m.start() - 12), m.end())
                    before = t_[a_:b_]
                    after = before[:m.start() - a_] + " " + m.group(2) + before[m.end() - a_:]
                    add(g, {"file": rel}, before, after)
                    done += 1
            if not done:
                unwritten.append({"group": g["group"], "class": cls, "why": "no glued escape found on its line"})
        elif cls == "xref-ref":
            old, new_key = str(g.get("match") or ""), str(g.get("fix_target") or "")
            done = 0
            for rel, line in _where_lines(g):
                t_ = paper_text(rel)
                if t_ is None:
                    continue
                for m in _REF_CMD_RE.finditer(t_):
                    if old not in _split_keys(m.group(2)):
                        continue
                    a_, b_ = _unique_context(t_, m.start(), m.end())
                    before = t_[a_:b_]
                    keys = ",".join(new_key if k == old else k for k in _split_keys(m.group(2)))
                    after = before[:m.start(2) - a_] + keys + before[m.end(2) - a_:]
                    add(g, {"file": rel}, before, after)
                    done += 1
            if not done:
                unwritten.append({"group": g["group"], "class": cls, "why": "the reference was not found"})
        elif cls == "xref-cite":
            key = str(g.get("drop_key") or g.get("match") or "")
            done = 0
            for rel, line in _where_lines(g):
                t_ = paper_text(rel)
                if t_ is None:
                    continue
                for m in _CITE_CMD_RE.finditer(t_):
                    ks = _split_keys(m.group(2))
                    if key not in ks or len(ks) < 2:
                        continue
                    a_, b_ = _unique_context(t_, m.start(), m.end())
                    before = t_[a_:b_]
                    arg = m.group(2)
                    new_arg = re.sub(r"\s*,\s*" + re.escape(key) + r"(?=\s*(?:,|$))|" + re.escape(key) + r"\s*,\s*",
                                     "", arg, count=1)
                    after = before[:m.start(2) - a_] + new_arg + before[m.end(2) - a_:]
                    add(g, {"file": rel}, before, after)
                    done += 1
            if not done:
                unwritten.append({"group": g["group"], "class": cls, "why": "the multi-key citation was not found"})
        elif cls == "meta":
            want = {(x.get("file"), x.get("line")) for x in g.get("inplace") or []}
            for x in meta_field_sites(paper_dir):
                if (x["file"], x["line"]) in want:
                    add(g, {"file": x["file"]}, x["before"], x["after"],
                        how="meta: empty the fields where they are set")
            if g.get("lines"):
                mains = discover_inputs(paper_dir, [], [], False)["mains"]
                rel = _rel(mains[0], paper_dir) if mains else None
                t_ = paper_text(rel) if rel else None
                if t_ is not None and t_.count("\\begin{document}") == 1:
                    lines = [x for x in g["lines"] if not (x.startswith("\\hypersetup")
                                                           and "hyperref" not in t_ and "\\hypersetup" not in t_)]
                    if len(lines) < len(g["lines"]):
                        notes.append("the main file does not load hyperref: the \\hypersetup line is left out "
                                     "(add it by hand if a style loads hyperref)")
                    if lines:
                        add(g, {"file": rel}, "\\begin{document}", "\n".join(lines) + "\n\\begin{document}",
                            how="meta: add the item's lines to the preamble")
                else:
                    unwritten.append({"group": "META", "class": cls, "why": "no single \\begin{document} in the "
                                                                            "main file: add the lines by hand"})
        elif cls == "supp-remove":
            for member in g.get("members") or []:
                edits.append({"group": g["group"], "member": member, "draft": "leave out of the staged copy"})
        elif cls == "repack":
            notes.append("REPACK: no text edit — `apply --stage-only`, then `repack` the staged copy")
        elif cls == "rebuild":
            notes.append("%s: no text edit — a full rebuild" % g["group"])
        elif cls == "undo":
            notes.append("%s: `apply --undo %s`" % (g["group"], ",".join(g.get("undo_ids") or [])))
    doc = {"tool": TOOL, "command": "edits", "from_queue": _display_path(audit_path, paper_dir),
           "edits": edits, "unwritten": unwritten, "notes": notes}
    _write_atomic(a.out, json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
    if work_dir and isinstance(det.get("fix_round"), int) and det.get("run_mode") == "fix":
        # what was drafted, by stable key: the next finalize tells a dropped draft from an applied one
        items = []
        for e in edits:
            k = (by_group.get(e["group"]) or {}).get("key")
            if k and not any(x["key"] == k for x in items):
                items.append({"group": e["group"], "key": k, "where": e.get("file") or e.get("member")})
        os.makedirs(work_dir, exist_ok=True)
        _write_atomic(os.path.join(work_dir, DRAFT_RECORD_NAME), json.dumps({
            "version": 1, "drafted_from_round": det["fix_round"], "generated_at": _now(), "items": items},
            ensure_ascii=False, indent=1) + "\n")
    return {"tool": TOOL, "command": "edits", "out": _display_path(a.out, paper_dir), "drafted": len(edits),
            "unwritten": len(unwritten), "notes": notes}, (1 if unwritten else 0)


def run_edits(a: Any) -> Tuple[Dict[str, Any], int]:
    """Every change between the round-0 snapshot and this round's snapshot,
    with the whitelist verdict of each (redacted); with --from-queue, the
    draft edits of the fix queue (run_edits_from_queue)."""
    if getattr(a, "from_queue", False):
        return run_edits_from_queue(a)
    if not (a.before and a.after):
        raise UsageError("edits needs --before and --after (or --from-queue)")
    paper_dir = os.path.abspath(a.paper_dir)
    before, after = _load_json(a.before), _load_json(a.after)
    if not isinstance(before, dict) or not isinstance(after, dict):
        raise UsageError("cannot read --before / --after (scan JSON files)")
    bdir, bman = _snapshot_manifest(before, paper_dir)
    cdir, cman = _snapshot_manifest(after, paper_dir)
    if not (bman and cman):
        raise UsageError("both scans need a snapshot: run them with --run-mode fix --work-dir <WORK>")
    work_dir = os.path.abspath(a.work_dir) if a.work_dir else os.path.dirname(os.path.abspath(a.after))
    red = _finalize_redactor(after, paper_dir, a.config_dir)
    items, unreadable = diff_snapshots(bdir, bman, cdir, cman)
    ec = edit_check_for(_paper_sources(paper_dir), red, _load_json(os.path.join(work_dir, FIX_HISTORY_NAME)))
    check = check_edits(items, ec, red)
    raw = check.pop("_raw")
    doc = {"tool": TOOL, "command": "edits", "before_snapshot": (before.get("snapshot") or {}).get("id"),
           "after_snapshot": (after.get("snapshot") or {}).get("id"), "unreadable": unreadable, **check}
    _write_atomic(a.out, json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
    _write_atomic(os.path.splitext(a.out)[0] + ".raw.json", json.dumps(raw, ensure_ascii=False) + "\n")
    return {"tool": TOOL, "command": "edits", "out": _display_path(a.out, paper_dir), "total": check["total"],
            "ok": check["ok"], "rejected": check["rejected"]}, (1 if check["rejected"] else 0)


ROUNDS_NAME = "rounds.json"


def run_restore(a: Any) -> Tuple[Dict[str, Any], int]:
    """Put back the paper sources (and the re-packed supplement) of an earlier
    fix round from its snapshot; the files replaced are kept in WORK."""
    paper_dir = os.path.abspath(a.paper_dir)
    work_dir = os.path.abspath(a.work_dir)
    rounds = (_load_json(os.path.join(work_dir, ROUNDS_NAME)) or {}).get("rounds") or []
    rec = next((r for r in rounds if r.get("round") == int(a.round)), None)
    if rec is None or not rec.get("snapshot"):
        raise UsageError("round %s is not recorded in %s (finalize --fix-round writes it)" % (a.round, ROUNDS_NAME))
    sdir = os.path.join(work_dir, "snapshots", rec["snapshot"])
    man = _load_json(os.path.join(sdir, "manifest.json"))
    if not isinstance(man, dict):
        raise UsageError("the snapshot of round %s is missing" % a.round)
    keep = os.path.join(work_dir, "restore_backup_%s" % datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S"))
    part = getattr(a, "part", None) or "all"
    restored, same = [], 0
    for rel, dst_rel in sorted((man.get("paper_files") or {}).items() if part in ("all", "paper") else []):
        src = os.path.join(sdir, dst_rel)
        cur = _within(paper_dir, rel)
        if not cur or not os.path.isfile(src):
            continue
        if os.path.isfile(cur) and _sha256_file(cur) == _sha256_file(src):
            same += 1
            continue
        if os.path.isfile(cur):
            os.makedirs(os.path.dirname(os.path.join(keep, "paper", _safe_rel(rel))), exist_ok=True)
            shutil.copy2(cur, os.path.join(keep, "paper", _safe_rel(rel)))
        shutil.copyfile(src, cur)
        restored.append(rel)
    supp_restored, upload = [], []
    for s in (rec.get("supplements") or []) if part in ("all", "supp") else []:
        cur = s.get("path")
        cur = cur if (cur and os.path.isabs(cur)) else os.path.join(paper_dir, cur or "")
        upload.append(_display_path(cur, paper_dir))  # the archive this round audited is the one to upload
        copy = os.path.join(work_dir, s.get("copy") or "")
        if not s.get("copy") or not os.path.isfile(copy) or (os.path.isfile(cur) and _sha256_file(cur) == s.get("sha256")):
            continue
        if os.path.isfile(cur):
            os.makedirs(os.path.join(keep, "supp"), exist_ok=True)
            shutil.copy2(cur, os.path.join(keep, "supp", os.path.basename(cur)))
        shutil.copyfile(copy, cur)
        supp_restored.append(_display_path(cur, paper_dir))
    return {"tool": TOOL, "command": "restore", "round": int(a.round), "part": part, "paper_files_restored": restored,
            "unchanged": same, "supplements_restored": supp_restored, "supplement_to_upload": upload,
            "kept": _display_path(keep, paper_dir) if (restored or supp_restored) else None,
            "next": ("rebuild the PDF (full), then scan and finalize with --fix-round %s to confirm" % a.round
                     if part != "supp" else "scan and finalize with --supp %s to confirm" % (upload[0] if upload
                                                                                              else "<archive>"))}, 0


# ─── status ──────────────────────────────────────────────────────────────────

def run_status(a: Any) -> Tuple[Dict[str, Any], int]:
    """Does an existing PAPER_HYGIENE_AUDIT.json still describe the current
    bytes, and was it a read-only recheck that cleared them for upload? Exit 0
    only when it is current and upload_ready; 1 otherwise."""
    paper_dir = os.path.abspath(a.paper_dir)
    art_path = a.artifact or os.path.join(paper_dir, "PAPER_HYGIENE_AUDIT.json")
    try:
        art = json.loads(_read_text(art_path))
    except (OSError, ValueError) as e:
        raise UsageError("cannot read the audit artifact: %s" % e) from None
    if not isinstance(art, dict) or art.get("audit_skill") != SKILL_NAME:
        raise UsageError("%s is not a %s artifact" % (os.path.basename(art_path), SKILL_NAME))
    det = art.get("details") or {}
    changed, missing, not_audited = [], [], []
    for rel, rec in (art.get("audited_input_hashes") or {}).items():
        full = rel if os.path.isabs(rel) else os.path.join(paper_dir, rel)
        if not os.path.isfile(full):
            missing.append(rel)
        elif _sha256_file(full) != str(rec).split(":", 1)[-1]:
            changed.append(rel)
    audited = {x.get("sha256") for x in (det.get("artifacts") or []) + (det.get("supplements") or [])}
    for p in list(a.pdf or []) + list(a.supp or []):
        if not os.path.isfile(p) or _sha256_file(p) not in audited:
            not_audited.append(_display_path(p, paper_dir))
    current = not (changed or missing or not_audited)
    ready = bool(current and det.get("upload_ready"))
    reasons = det.get("reasons") or [art.get("reason_code")]
    audited_supp = [s.get("path") for s in det.get("supplements") or [] if s.get("path")]
    if ready:
        advice = "upload the audited bytes"
    elif not current:
        advice = "inputs changed since the audit: re-run /paper-hygiene-audit — recheck on the final files"
        if not_audited and audited_supp and a.supp:
            advice += "; the audited archive is %s — upload that one, not an earlier pack" % ", ".join(audited_supp)
    elif det.get("recheck_required"):
        advice = "this was a %s run: re-run with — recheck on the final PDF and archive" % det.get("run_mode")
    else:
        todo = [_STATUS_ADVICE.get(r, "fix %s" % r) for r in reasons if r not in ("clean", "advisory_only")]
        advice = "the recheck did not pass (%s): %s; then rebuild and recheck" % (
            ", ".join(reasons), "; ".join(dict.fromkeys(todo)) or "fix the findings")
    doc = {"tool": TOOL, "command": "status", "artifact": _display_path(art_path, paper_dir),
           "verdict": art.get("verdict"), "reason_code": art.get("reason_code"), "reasons": reasons,
           "run_mode": det.get("run_mode"),
           "generated_at": art.get("generated_at"), "state": "current" if current else "stale",
           "changed": changed, "missing": missing, "not_audited": not_audited, "audited_supplements": audited_supp,
           "upload_ready": ready, "advice": advice}
    return doc, 0 if ready else 1


# What the person does next, per reason (status advice names every reason).
_STATUS_ADVICE = {
    "identity_list_missing": "create .aris/paper-hygiene/anon-names.txt yourself (the executor never writes it)",
    "confirmed_leaks": "fix the reviewer-confirmed leaks that are still WARN (see FIX_PLAN.md)",
    "fix_regression": "undo the fix-loop edits the report lists (regressions, edits outside the whitelist), or "
                      "restore the round the report names, then rebuild",
    "ruling_flip": "a reviewer ruling flipped without new evidence: look at the listed group and decide",
    "carried_over": "the fix run left items that are still in the files (see 'Carried over'): fix or decide them",
    "unreviewed_candidates": "run the Tier B review (or a human rules on the candidates)",
    "coverage_gap": "provide the missing input or backend so every check can run, and read the supplementary "
                    "members the report lists as not covered (or split the supplement and recheck)",
    "anonymity_leak": "remove the identifying detail (see FIX_PLAN.md)",
    "engineering_leak": "delete the engineering detail (see FIX_PLAN.md), rebuild",
    "process_narration": "reword or delete the process narration (see FIX_PLAN.md), rebuild",
    "supplement_leak": "fix the staged supplement copy and re-pack it",
    "unresolved_refs": "resolve the ?? / missing citations (closest labels and keys in FIX_PLAN.md) and rebuild fully",
}


# ─── repack ──────────────────────────────────────────────────────────────────

def run_repack(a: Any) -> Tuple[Dict[str, Any], int]:
    src = os.path.abspath(a.src)
    out = os.path.abspath(a.out)
    if not os.path.isdir(src):
        raise UsageError("--src must be a directory")
    if _is_within(out, src):
        raise UsageError("--out must not be inside --src")
    if os.path.exists(out) and not a.force:
        raise UsageError("--out already exists (pass --force to replace it; inputs are never overwritten)")
    patterns = [p.strip().replace("\\", "/") for p in (a.exclude or []) if p.strip()]
    entries, excluded, by_pattern = [], [], []
    for root, dirs, files in os.walk(src):
        dirs.sort()
        for fn in sorted(files):
            full = os.path.join(root, fn)
            rel = _rel(full, src)
            if _JUNK_BLOCK_RE.search(rel) or _JUNK_WARN_RE.search(rel) or _ARIS_RE.search(rel):
                excluded.append(rel)
                continue
            if any(fnmatch.fnmatchcase(rel, p) or fnmatch.fnmatchcase(fn, p) or rel.startswith(p.rstrip("/") + "/")
                   for p in patterns):
                by_pattern.append(rel)  # e.g. run logs the reviewer ruled out; the source keeps them
                continue
            entries.append((rel, full))
    entries.sort()
    normalized: List[str] = []
    tar_normalized: List[str] = []
    grown: List[Dict[str, Any]] = []
    src_bytes = 0
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(out) or ".", suffix=".zip.part")
    os.close(fd)
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for rel, full in entries:
                zi = zipfile.ZipInfo(rel, date_time=(1980, 1, 1, 0, 0, 0))
                zi.compress_type = zipfile.ZIP_DEFLATED
                zi.external_attr = 0o100644 << 16
                zi.create_system = 3
                with open(full, "rb") as fh:
                    data = fh.read()
                before = len(data)
                src_bytes += before
                clean_t = None
                if not getattr(a, "keep_tar_metadata", False) and rel.lower().endswith(_TAR_NAMES):
                    clean_t = _normalized_tar(data, rel)
                    if clean_t is not None:
                        data = clean_t
                        tar_normalized.append(rel)
                if clean_t is None and not a.keep_gzip_headers and rel.lower().endswith(".gz"):
                    clean = _normalized_gzip(data)
                    if clean is not None and clean != data:
                        data = clean
                        normalized.append(rel)
                if len(data) > before * 1.01 + 1024:  # a re-compressed member came out larger: say by how much
                    grown.append({"member": rel, "before": before, "after": len(data)})
                zf.writestr(zi, data)
            zf.comment = b""
        os.chmod(tmp, 0o644)  # mkstemp creates 0600: an archive for upload is world-readable like any file
        os.replace(tmp, out)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(tmp)
        raise
    ctx = ScanContext()
    ctx.anonymous = not a.camera_ready
    if a.anon_names and os.path.isfile(a.anon_names):
        ctx.identity = TermMatcher(parse_identity_list(_read_text(a.anon_names))[0])
    ctx.redactor = Redactor(ctx.identity)
    findings, info = scan_supp(out, ctx, os.path.dirname(out))
    info.pop("docs", None)
    rc = 1 if any(f["severity"] == BLOCK for f in findings) else 0
    # the size to hold against the venue's upload limit (scan --supp-max-mb blocks past it)
    return {"tool": TOOL, "command": "repack", "out": os.path.basename(out), "sha256": _sha256_file(out),
            "size": os.path.getsize(out), "src_bytes": src_bytes, "grown": grown,
            "entries": len(entries), "excluded": excluded, "excluded_by_pattern": by_pattern,
            "gzip_normalized": normalized, "tar_normalized": tar_normalized,
            "scan": {"findings": [_public(f) for f in findings], "counts": _counts(findings)}}, rc


_TAR_NAMES = (".tar", ".tar.gz", ".tgz", ".tar.xz", ".txz", ".tar.bz2", ".tbz2")
MAX_TAR_NORMALIZE_BYTES = 256 * 1024 * 1024
# xz presets a re-pack tries in turn: the default first, the strongest when the
# default would make the member larger than it was (an archive packed with -9e
# can more than double at the default preset and pass an upload size limit)
_XZ_PRESETS = (6, 9 | lzma.PRESET_EXTREME)


def _xz_no_larger(raw: bytes, original_size: int) -> bytes:
    """`raw` as an xz stream: the default preset, or a stronger one when the
    default comes out larger than the member it replaces (the smallest wins)."""
    best = b""
    for preset in _XZ_PRESETS:
        out = lzma.compress(raw, preset=preset)
        if not best or len(out) < len(best):
            best = out
        if len(best) <= original_size:
            break
    return best


def _normalized_tar(data: bytes, name: str) -> Optional[bytes]:
    """The same tar members — names, types, link targets, contents, and the
    executable bit — without owner names and ids or times (0), with modes 0644
    (0755 for folders and executables), in name order, compressed like the
    original (gzip -n, xz, bz2). None when the archive cannot be read, holds
    special files, is too large, or nothing would change. The contents are
    verified to be identical after the rewrite."""
    import bz2
    import gzip as _gzip
    low = name.lower()
    comp = ("gz" if low.endswith((".tar.gz", ".tgz")) else "xz" if low.endswith((".tar.xz", ".txz"))
            else "bz2" if low.endswith((".tar.bz2", ".tbz2")) else "")

    def read(blob: bytes) -> Optional[List[Tuple[Any, Optional[bytes]]]]:
        try:
            with tarfile.open(fileobj=io.BytesIO(blob), mode=("r:" + comp) if comp else "r:") as tf:
                out, total = [], 0
                for ti in tf.getmembers():
                    if not (ti.isfile() or ti.isdir() or ti.issym() or ti.islnk()):
                        return None
                    payload = None
                    if ti.isfile():
                        total += ti.size
                        if total > MAX_TAR_NORMALIZE_BYTES:
                            return None
                        fh = tf.extractfile(ti)
                        payload = fh.read() if fh else b""
                    out.append((ti, payload))
                return out
        except (tarfile.TarError, OSError, EOFError, zlib.error, lzma.LZMAError, ValueError):
            return None
    members = read(data)
    if not members:
        return None
    if not any(ti.uid or ti.gid or ti.uname or ti.gname or ti.mtime
               or (ti.isfile() and (ti.mode & 0o777) not in (0o644, 0o755))
               or (ti.isdir() and (ti.mode & 0o777) != 0o755) for ti, _p in members):
        return None
    buf = io.BytesIO()
    fmt = tarfile.USTAR_FORMAT if all(len(ti.name) <= 100 and len(ti.linkname) <= 100 for ti, _p in members) \
        else tarfile.GNU_FORMAT
    with tarfile.open(fileobj=buf, mode="w", format=fmt) as out:
        for ti, payload in sorted(members, key=lambda x: x[0].name):
            n = tarfile.TarInfo(ti.name)
            n.type, n.linkname = ti.type, ti.linkname
            n.uid = n.gid = 0
            n.uname = n.gname = ""
            n.mtime = 0
            n.mode = 0o755 if (ti.isdir() or (ti.mode & 0o111)) else 0o644
            if payload is not None:
                n.size = len(payload)
                out.addfile(n, io.BytesIO(payload))
            else:
                out.addfile(n)
    raw = buf.getvalue()
    if comp == "gz":
        gz = io.BytesIO()
        with _gzip.GzipFile(filename="", mode="wb", fileobj=gz, mtime=0, compresslevel=9) as g:
            g.write(raw)
        raw = gz.getvalue()
    elif comp == "xz":
        raw = _xz_no_larger(raw, len(data))
    elif comp == "bz2":
        raw = bz2.compress(raw)
    back = read(raw)
    want = sorted((ti.name, ti.type, ti.linkname, _sha256_bytes(p) if p is not None else None) for ti, p in members)
    got = sorted((ti.name, ti.type, ti.linkname, _sha256_bytes(p) if p is not None else None) for ti, p in back or [])
    return raw if back and got == want else None


def _normalized_gzip(data: bytes) -> Optional[bytes]:
    """The same content as a gzip stream without FNAME, FCOMMENT, FEXTRA, or
    MTIME (`gzip -n`), or None when the member is not a single clean gzip
    stream. The decompressed bytes are verified to be identical."""
    hdr = _gzip_header(data)
    if hdr is None or not (hdr.get("fname") or hdr.get("comment") or hdr.get("mtime") or data[3] & 0x04):
        return None
    d = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        raw = d.decompress(data, MAX_SUPP_MEMBER_BYTES)
    except zlib.error:
        return None
    if d.unconsumed_tail or not d.eof or d.unused_data.strip(b"\x00"):
        return None  # truncated, too large, or several gzip members: copy it unchanged
    try:
        import gzip as _gzip
        buf = io.BytesIO()
        with _gzip.GzipFile(filename="", mode="wb", fileobj=buf, mtime=0, compresslevel=9) as g:
            g.write(raw)
        clean = buf.getvalue()
        back, st2 = _bounded_decompress(clean, "gz", MAX_SUPP_MEMBER_BYTES)
    except (OSError, ValueError, zlib.error):
        return None
    if st2 != "ok" or back is None or _sha256_bytes(back) != _sha256_bytes(raw):
        return None
    return clean


# ─── CLI ─────────────────────────────────────────────────────────────────────

def list_checks(fmt: str = "json") -> str:
    if fmt == "md":
        rows = ["| ID | Family | Layer | Certainty | Default | Confirmed | P | Route |",
                "|---|---|---|---|---|---|---|---|"]
        for cid, s in CHECKS.items():
            rows.append("| %s | %s | %s | %s | %s | %s | %s | %s |" % (
                cid, s["family"], s["layer"], s["certainty"], s["default"], s["confirm"] or "—", s["priority"],
                s["route"]))
        return "\n".join(rows) + "\n"
    return json.dumps([dict(id=cid, **s) for cid, s in CHECKS.items()], ensure_ascii=False, indent=2) + "\n"


def _stdout(text: str) -> None:
    """Write UTF-8 to stdout whatever the console code page is (a Windows
    redirect defaults to the locale encoding, which cannot encode U+2212 or
    U+FFFD). Printing never changes the exit code: the JSON file is the record."""
    data = (text if text.endswith("\n") else text + "\n").encode("utf-8")
    try:
        buf = getattr(sys.stdout, "buffer", None)
        if buf is not None:
            sys.stdout.flush()
            buf.write(data)
            buf.flush()
        else:
            sys.stdout.write(data.decode("utf-8"))
    except (OSError, ValueError, UnicodeError):
        pass


def _emit(doc: Dict[str, Any], json_out: Optional[str], md_out: Optional[str], final: bool) -> None:
    text = json.dumps(doc, ensure_ascii=False, indent=2)
    if json_out:
        _write_atomic(json_out, text + "\n")
    if md_out:
        _write_atomic(md_out, render_md(doc, final=final))
    _stdout(text)


def _error_doc(kind: str, msg: str, final: bool) -> Dict[str, Any]:
    if final:
        return {"audit_skill": SKILL_NAME, "verdict": "ERROR", "reason_code": "scanner_error",
                "summary": "ERROR (scanner_error): %s" % msg, "audited_input_hashes": {}, "trace_path": "",
                "agent_id": DETERMINISTIC_REVIEWER, "reviewer_model": DETERMINISTIC_REVIEWER,
                "reviewer_reasoning": "n/a", "generated_at": _now(), "details": {"error": msg, "kind": kind}}
    return {"tool": TOOL, "tool_version": TOOL_VERSION, "generated_at": _now(), "verdict_tier_a": "ERROR",
            "reason_code": "scanner_error", "summary": "ERROR (scanner_error): %s" % msg, "findings": [], "groups": [],
            "error": msg}


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="ARIS /paper-hygiene-audit deterministic scanner and verdict finalizer.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan", help="Tier A deterministic scan")
    s.add_argument("paper_dir", nargs="?", default=None, help="paper directory (default: paper/, or the --pdf dir)")
    s.add_argument("--pdf", action="append", help="PDF to audit (repeatable; one per language version)")
    s.add_argument("--main-tex", action="append", help="main .tex (repeatable; default: auto-detect, paired by stem)")
    s.add_argument("--no-sources", action="store_true", help="audit the artifacts only")
    s.add_argument("--log", help="build log (default: <stem>.log, else compile.log)")
    s.add_argument("--blg", help="BibTeX/Biber log (default: <stem>.blg)")
    s.add_argument("--log-wrap", type=int, default=79, help="TeX max_print_line (default 79)")
    s.add_argument("--supp", action="append", help="supplementary .zip/.tar(.gz|.xz) or directory (repeatable)")
    s.add_argument("--camera-ready", action="store_true", help="turn the ANON family off; metadata Author becomes INFO")
    s.add_argument("--config-dir", default=os.path.join(".aris", "paper-hygiene"))
    s.add_argument("--anon-names")
    s.add_argument("--allow")
    s.add_argument("--policy")
    s.add_argument("--no-auto-identity", action="store_true")
    s.add_argument("--page-limit", type=int)
    s.add_argument("--fill-page", type=int)
    s.add_argument("--fill-threshold", type=float)
    s.add_argument("--end-matter", help="'AI use statement|AI 使用声明;Ethics statement|伦理声明'")
    s.add_argument("--hardware", choices=sorted(HARDWARE_LEVELS), help="level of a confirmed hardware leak (default block)")
    s.add_argument("--framework", choices=sorted(HARDWARE_LEVELS), help="level of a confirmed framework leak (default warn)")
    s.add_argument("--supp-hardware", choices=sorted(HARDWARE_LEVELS),
                   help="hardware/OS/host words in the supplement: the level a reviewer-confirmed leak takes "
                        "(default: the --hardware level), or info (INFO, not reviewed)")
    s.add_argument("--precision-disclosure", choices=PRECISION_POLICIES,
                   help="bf16/fp8 and weight-loading detail: exempt (default: never reported) or candidate")
    s.add_argument("--registration-labels", choices=REGISTRATION_POLICIES,
                   help="registration amendment/addendum labels: keep (default: INFO) or flag (candidates)")
    s.add_argument("--style-ref", help="directory with the official .sty/.cls/.bst")
    s.add_argument("--supp-max-mb", type=float)
    s.add_argument("--baseline", help="round-0 scan.json (fix rounds, recheck after a fix run) or an earlier PDF")
    s.add_argument("--previous", help="the previous fix round's scan.json: FIX-REGRESSION names what this round broke")
    s.add_argument("--run-mode", choices=RUN_MODES, default="audit")
    s.add_argument("--no-freshness", action="store_true")
    s.add_argument("--checks", help="only these check ids/prefixes (comma-separated)")
    s.add_argument("--skip-checks", help="skip these check ids/prefixes (comma-separated)")
    s.add_argument("--backend", choices=("auto", "pymupdf", "poppler", "pypdf", "none"), default="auto")
    s.add_argument("--strict", action="store_true", help="surviving WARN findings block")
    s.add_argument("--work-dir", help="write pdf_text.<stem>.txt, review_input.json, supp_docs/ here")
    s.add_argument("--json-out")
    s.add_argument("--md-out")
    f = sub.add_parser("finalize", help="merge Tier B, compute the verdict, write the audit artifact")
    f.add_argument("--paper-dir", required=True)
    f.add_argument("--scan", required=True)
    f.add_argument("--review", help="reviewer's raw response (markdown with a fenced json block)")
    f.add_argument("--review-status", required=True, choices=("ok", "error", "unavailable", "skipped"))
    f.add_argument("--reviewer-model")
    f.add_argument("--reviewer-reasoning")
    g = f.add_mutually_exclusive_group()
    g.add_argument("--thread-id")
    g.add_argument("--agent-id")
    f.add_argument("--executor-model", required=True)
    f.add_argument("--trace-dir")
    f.add_argument("--config-dir", default=os.path.join(".aris", "paper-hygiene"),
                   help="fallback for the identity/deny lists that redact the reviewer's text")
    f.add_argument("--out-json", required=True)
    f.add_argument("--out-md", required=True)
    f.add_argument("--strict", action="store_true")
    f.add_argument("--run-mode", choices=RUN_MODES)
    f.add_argument("--fix-round", type=int)
    f.add_argument("--work-dir", help="WORK directory: keeps the rulings ledger, the fix state a later round or the "
                                      "recheck carries, the fix history, and rounds.json (off when omitted)")
    f.add_argument("--supp-review", action="append",
                   help="raw reply of a supplementary batch reviewer (repeatable, one per batch)")
    f.add_argument("--plan-out", help="write the fix plan for a person here (FIX_PLAN.md)")
    f.add_argument("--contest-edit", action="append",
                   help="a FIX-EDIT id (E-xxxxxxxx) the executor holds to be the scanner's mistake (repeatable): "
                        "finalize re-reads round 0's files and the audited ones and overturns it only when the bytes "
                        "show no such change or the change passes the whitelist; a claim alone overturns nothing")
    st = sub.add_parser("status", help="is the audit artifact current and upload-ready?")
    st.add_argument("--paper-dir", required=True)
    st.add_argument("--artifact", help="default: <paper-dir>/PAPER_HYGIENE_AUDIT.json")
    st.add_argument("--pdf", action="append", help="a file you will upload; it must be one of the audited bytes")
    st.add_argument("--supp", action="append", help="an archive you will upload; it must be one of the audited bytes")
    ap_ = sub.add_parser("apply", help="apply proposed fix-queue edits that pass the whitelist (or --undo edits)")
    ap_.add_argument("--paper-dir", required=True)
    ap_.add_argument("--work-dir", required=True)
    ap_.add_argument("--round", required=True, type=int)
    ap_.add_argument("--edits", help="JSON {\"edits\": [...]}, one or more per queue item: a text edit "
                                     "{group, file|member, before, after} (before: exact text found once; after: the "
                                     "same text minus what the item's class allows — for a meta item, the same text "
                                     "plus the item's lines); a member to leave out of the staged supplement "
                                     "{group, member}; a repack item needs no edit")
    ap_.add_argument("--audit", help="the finalize artifact whose fix_queue the edits follow "
                                     "(default: <paper-dir>/PAPER_HYGIENE_AUDIT.json)")
    ap_.add_argument("--supp-stage", help="the staged supplement copy (default: <work-dir>/supp_stage)")
    ap_.add_argument("--undo", help="comma-separated ids to put back: applied edits (A<round>-NNN) or edits the "
                                    "scan rejected (E-xxxxxxxx)")
    ap_.add_argument("--reason", help="why the edits are undone (recorded; the group then goes to the fix plan)")
    ap_.add_argument("--stage-only", action="store_true",
                     help="only make the staged supplement copy (<work-dir>/supp_stage) from round 0's supplement, "
                          "e.g. for a queue whose supplement items need no text edit (a re-pack)")
    ap_.add_argument("--config-dir", default=os.path.join(".aris", "paper-hygiene"))
    ed = sub.add_parser("edits", help="list every change since round 0 with its whitelist verdict, or "
                                      "(--from-queue) draft the round's edits from the fix queue")
    ed.add_argument("--paper-dir", required=True)
    ed.add_argument("--before", help="round-0 scan JSON (scan_r0.json, written with --work-dir)")
    ed.add_argument("--after", help="this round's scan JSON")
    ed.add_argument("--from-queue", action="store_true",
                    help="write draft edits ({\"edits\": [...]}, the apply format) for every item of the audit's "
                         "fix queue — whole-sentence and clause deletions included — each checked against the "
                         "whitelist; what cannot be drafted is listed under 'unwritten'")
    ed.add_argument("--audit", help="with --from-queue: the finalize artifact (default: "
                                    "<paper-dir>/PAPER_HYGIENE_AUDIT.json)")
    ed.add_argument("--supp-stage", help="with --from-queue: the staged supplement copy (default: <work-dir>/supp_stage)")
    ed.add_argument("--work-dir", help="WORK directory (fix history; round 0's supplement); default: the directory "
                                       "of --after")
    ed.add_argument("--config-dir", default=os.path.join(".aris", "paper-hygiene"))
    ed.add_argument("--out", required=True, help="where to write the edit list or the draft edits (JSON)")
    rs = sub.add_parser("restore", help="put back the sources and supplement of an earlier fix round")
    rs.add_argument("--paper-dir", required=True)
    rs.add_argument("--work-dir", required=True)
    rs.add_argument("--round", required=True, type=int)
    rs.add_argument("--part", choices=("all", "paper", "supp"), default="all",
                    help="restore only the paper sources or only the supplement (details.deliver names each part's "
                         "round: a supplement problem never takes the paper's fixes back, nor the reverse)")
    lc = sub.add_parser("list-checks", help="print the check table")
    lc.add_argument("--format", choices=("json", "md"), default="json")
    r = sub.add_parser("repack", help="deterministic zip of a supplementary directory")
    r.add_argument("--src", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--force", action="store_true")
    r.add_argument("--anon-names")
    r.add_argument("--camera-ready", action="store_true")
    r.add_argument("--exclude", action="append",
                   help="glob of members to leave out (repeatable; matched against the path and the file name)")
    r.add_argument("--keep-gzip-headers", action="store_true",
                   help="copy .gz members byte for byte (default: rewrite their headers like gzip -n)")
    r.add_argument("--keep-tar-metadata", action="store_true",
                   help="copy .tar(.gz|.xz|.bz2) members byte for byte (default: clear owners and times, 0644/0755)")
    return ap


__all__ = [
    "CHECKS", "CHECK_IDS", "REASON_CODES", "TermMatcher", "Redactor", "ScanContext", "fold_text", "find_secrets",
    "parse_identity_list", "parse_allow", "load_config", "auto_identity_terms", "strip_tex_comments", "expand_tex",
    "parse_aux", "parse_bib", "parse_bbl", "static_xref", "unwrap_log", "scan_log", "scan_blg", "parse_pdf_objects",
    "pdf_info", "scan_metadata", "scan_pdf_bytes", "nospace_stats", "copy_glue", "extract_pdf", "parse_bbox_xhtml",
    "normalize_pages", "normalize_text", "join_lines", "join_lines_tracked", "heading_kind", "detect_regions",
    "detect_text", "scan_pdf_text", "scan_text", "page_geometry", "parse_end_matter", "check_end_matter",
    "scan_supp", "number_multiset", "number_drift", "number_text", "clause_explained", "drift_context",
    "apply_allow", "group_findings", "decide_verdict", "verdict_reasons", "build_fix_queue", "downgraded_blockers",
    "cite_key_note", "tier_a_verdict", "final_verdict", "build_review_input", "render_md",
    "parse_review", "merge_review", "stale_other_audits", "run_scan", "run_finalize", "run_status", "run_repack",
    "run_apply", "run_edits", "run_restore", "verify_change", "verify_edit", "diff_snapshots", "build_fix_plan",
    "render_fix_plan", "list_checks", "main",
]


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = build_parser()
    a = ap.parse_args(argv)
    if a.cmd == "list-checks":
        _stdout(list_checks(a.format))
        return 0
    if a.cmd in ("repack", "status", "edits", "apply", "restore"):
        runner = {"repack": run_repack, "status": run_status, "edits": run_edits, "apply": run_apply,
                  "restore": run_restore}[a.cmd]
        try:
            doc, rc = runner(a)
        except UsageError as e:
            print("paper_hygiene_scan: %s" % e, file=sys.stderr)
            return 2
        _stdout(json.dumps(doc, ensure_ascii=False, indent=2))
        return rc
    if a.cmd == "scan":
        try:
            doc = run_scan(a)
        except UsageError as e:
            print("paper_hygiene_scan: %s" % e, file=sys.stderr)
            err = _error_doc("usage", str(e), final=False)
            _emit(err, a.json_out, a.md_out, final=False)
            return 2
        except Exception as e:  # noqa: BLE001 — always emit, never crash silently
            err = _error_doc("crash", "%s: %s" % (type(e).__name__, e), final=False)
            _emit(err, a.json_out, a.md_out, final=False)
            print("paper_hygiene_scan: scan crashed: %s: %s" % (type(e).__name__, e), file=sys.stderr)
            return 2
        _emit(doc, a.json_out, a.md_out, final=False)
        return VERDICT_EXIT[doc["verdict_tier_a"]]
    try:
        doc, rc = run_finalize(a)
    except UsageError as e:
        print("paper_hygiene_scan: %s" % e, file=sys.stderr)
        _emit(_error_doc("usage", str(e), final=True), a.out_json, a.out_md, final=True)
        return 2
    except Exception as e:  # noqa: BLE001
        _emit(_error_doc("crash", "%s: %s" % (type(e).__name__, e), final=True), a.out_json, a.out_md, final=True)
        print("paper_hygiene_scan: finalize crashed: %s: %s" % (type(e).__name__, e), file=sys.stderr)
        return 2
    _emit(doc, a.out_json, a.out_md, final=True)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
