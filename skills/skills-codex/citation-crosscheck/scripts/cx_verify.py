#!/usr/bin/env python3
"""cx_verify.py — the deterministic verifier gate for /citation-crosscheck.

Requirement 4 of `shared-references/fan-out-pattern.md` requires a fan-out skill to
end at "a single cross-model jury step -- OR a deterministic verifier gate -- that is
identical across all three tiers". `citation-crosscheck` has no cross-model jury (it is
an evidence instrument, not an acquittal step), so THIS SCRIPT is that gate.

It is a real external process, not an LLM self-report: it decides field equality by
string normalization plus a declared venue-alias table, and it FAILS CLOSED. Only two
outcomes are decided here --

    MATCH   every field equal after declared normalization (cosmetic differences only)
    MINOR   the sole difference is preprint-vs-published venue for the same work

-- and EVERYTHING else becomes

    ESCALATE  routed to the main agent's own primary-source fetch (Step 4)

`MISMATCH` is never emitted by this script. A discrepancy becomes a finding only when
the main agent reproduces it against the publisher of record. That keeps the accept
path mechanical and the reject path externally evidenced.

Usage:
    python3 cx_verify.py --a cx_A_ourbib.json --b cx_B_web.json --c cx_C_fielddiff.json \
            --expect <CITED_KEY_COUNT> --expect-keys /tmp/cx_dedup_keys.txt \
            --json /tmp/cx_gate.json
    python3 cx_verify.py --selftest            # built-in cases (verify + build_entry), exit 2 on failure

Exit codes: 0 = ran (read the verdicts); 1 = bad/empty/incomplete input, or A/B/C
dedup_key sets disagree (a broken run, NOT a clean bill of health); 2 = selftest failure.

Trust model (this is the point of the rewrite):
  * The gate RECOMPUTES the field diff from A's and B's raw records itself. C is a model
    shard, so a faulty/adversarial C that omits a differing field or forges `blind:true`
    could otherwise obtain a MATCH — the exact shard-trust flaw the gate exists to remove.
  * B's `blind` attestation is read PER-SHARD from B's own artifact header, never from C.
  * C's per-entry `flags` (`url_only_source_unqueried`, `degraded_search`, `web_record_absent`)
    are the ONLY thing C contributes to the verdict; C never states the diff.

Artifact schemas the gate reads:
  A: {"shard_id":"A", "entries":[{"dedup_key","key","bibtex"}, …]}
  B: {"shard_id":"B", "blind":<bool>,
      "entries":[{"dedup_key","title_queried","found","source_url","bibtex","sources_tried","note"}, …]}
  C: {"shard_id":"C",
      "entries":[{"dedup_key","key","found","sources_tried","url","flags":[…],
                  "fields":{"<field>":{"status":"same|differs|absent","ours","web"}}}, …]}
Keep these in sync with both SKILL.md files.
"""

import argparse
import hashlib
import json
import re
import sys
import unicodedata

# --------------------------------------------------------------- normalization
# LaTeX accent forms: \"o, \'e, \^{a}, \~n, \c{c}, \v{s} ...
# accent macros only: symbol forms (\`o \'e \^a \"u \~n \=o \.z) and the
# letter-named accents (\c{c} \v{s} \u{g} \H{o} \k{a} \r{u} \t{oo} \d{h} \b{t}). A
# blanket \\[a-z]+\{X\} would eat \sqrt{x}/\vec{x} and erase math from a title.
ACCENT = re.compile(r"\\[`'\"^~=.]\s*\{?([A-Za-z])\}?|\\[cvuHkrtdb]\{([A-Za-z])\}")
BRACES = re.compile(r'[{}]')
NONALNUM = re.compile(r'[^a-z0-9]+')


def _alnum(s):
    """Unicode-aware 'keep only alphanumerics'. Unlike NONALNUM ([^a-z0-9]) it preserves
    non-Latin scripts, so a CJK/Cyrillic surname is not erased to '' (which silently
    dropped the coauthor). Used for author tokens; ASCII-id fields still use NONALNUM.
    """
    return ''.join(c for c in (s or '') if c.isalnum())


def _fold(s):
    """Lowercase, strip LaTeX accents/braces, drop combining marks."""
    s = ACCENT.sub(lambda m: m.group(1) or m.group(2), s or '')
    s = BRACES.sub('', s)
    s = unicodedata.normalize('NFKD', s)
    return ''.join(c for c in s if not unicodedata.combining(c)).lower()


_TEXT_SEP = re.compile(r'[\s\-‐-―_.,;:!?()\[\]{}\'"`/\\]+')


def norm_text(s):
    """Title/venue comparison form.

    Collapses case, whitespace and *separator* punctuation, but KEEPS every
    alphanumeric and non-ASCII character. A blanket `[^a-z0-9]+` strip would fold
    'C++' and 'C#' together, and would erase CJK/Cyrillic titles entirely so two
    unrelated non-ASCII titles compared equal -- both are wrong-accepts.

    Digit-adjacent punctuation is KEPT SIGNIFICANT: a single separator char sitting
    directly between two digits is a version number / range / decimal ('Model 4.1' vs
    'Model 4-1', '10.5' vs '10-5'), not formatting -- collapsing it to a space folded
    substantively different titles together. Every other separator run still collapses.
    """
    s = _fold(s)

    def _repl(m):
        run = m.group(0)
        if run.strip() == '':
            return ' '                      # pure whitespace is always formatting
        if len(run) == 1:
            before = s[m.start() - 1] if m.start() > 0 else ''
            after = s[m.end()] if m.end() < len(s) else ''
            if before.isdigit() and after.isdigit():
                return run                  # e.g. '4.1' / '4-1' — keep it verbatim
        return ' '

    s = _TEXT_SEP.sub(_repl, s)
    return re.sub(r'\s+', ' ', s).strip()


def norm_id(s):
    """Year / volume / pages.

    Dash STYLE is cosmetic ('12-20' == '12--20' == '12–20'), but the range BOUNDARY is
    not: collapsing every separator turns '1-234' and '12-34' both into '1234' and the
    gate accepts a wrong page range. So normalize each dash run to a single '-' and keep
    it, rather than deleting it.
    """
    s = _fold(s)
    s = re.sub(r'\s+', '', s)               # only whitespace is pure formatting; '_' is significant
    # Dash STYLE is cosmetic ('12-20' == '12--20' == '12–20'); collapse a dash RUN to one
    # '-' and keep it (incl. a trailing one: '12-' is not the single page '12').
    s = re.sub(r'[\-‐-―]+', '-', s)
    # '.'/',' are NOT formatting inside a number: '20.24' != '2024', '1.2' != '12',
    # 'e1.23' != 'e123'. Keep every other char verbatim.
    return s


def norm_ident(s):
    """Strict identifier form for url / eprint / isbn / issn and any UNKNOWN field.

    Truly fail-closed: collapse only leading/trailing whitespace; keep case, diacritics,
    and every other character EXACTLY. It deliberately does NOT call `_fold` -- URL paths
    are case-sensitive ('/Method.pdf' != '/method.pdf') and diacritics are meaningful
    ('Resume' != 'Résumé'), so folding them would let an ordinary wrong value pass. Inner
    whitespace is preserved too (rare in an id; if present, a difference should surface).
    This is the default for any field the gate does not specifically understand, so an
    unmodelled field can never reach MATCH through a lossy normalizer -- only `title` gets
    the lenient norm_text treatment.
    """
    return (s or '').strip()


def norm_doi(s):
    """DOI / arXiv id -> 'namespace:bare-id', or '' if there is no id at all.

    Inner punctuation is SIGNIFICANT: '10.5555/abc-def' and '10.5555/abcdef' are
    different DOIs, so they must not fold together.

    The namespace is KEPT. Stripping both the doi.org and the arxiv.org wrappers to a
    bare id made 'https://arxiv.org/abs/2301.1' and 'https://doi.org/2301.1' compare
    equal -- two different identifier spaces accepted as the same id.

    A wrapper with nothing after it ('doi:', 'https://doi.org/') yields '', and an empty
    identifier must never satisfy the identifier requirement -- callers treat '' as absent.
    """
    s = _fold(s).strip()
    ns = 'doi'
    m = re.match(r'^(?:https?://arxiv\.org/abs/|arxiv:\s*)(.*)$', s)
    if m:
        ns, s = 'arxiv', m.group(1)
    else:
        m = re.match(r'^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)(.*)$', s)
        if m:
            s = m.group(1)
        elif re.match(r'^\d{4}\.\d{4,5}(v\d+)?$', s):
            ns = 'arxiv'          # bare arXiv id
    s = re.sub(r'\s+', '', s)
    return ('%s:%s' % (ns, s)) if s else ''


# Generational suffixes are not surnames; nobiliary particles belong TO the surname.
SUFFIXES = {'jr', 'sr', 'ii', 'iii', 'iv'}  # NOT phd/md: they collide with real given names (e.g. 'Md Ali')
PARTICLES = {'van', 'von', 'der', 'den', 'de', 'del', 'della', 'di', 'da', 'dos', 'das',
             'du', 'la', 'le', 'ter', 'ten', 'al', 'bin', 'ibn', 'st', 'mac', 'mc', 'o'}
# "and others" / "et al." are conventional truncation markers, not a person. Match
# 'others' only in its conventional trailing position, never as a bare surname -- a real
# author surnamed 'Others' must not be erased.
# 'et al.'/'and others' are truncation markers ONLY when terminal (optionally followed by
# punctuation) — 'and Others, Ann' is a real coauthor named Others, not a truncation, and
# must NOT be erased (that would let a dropped coauthor compare equal).
ETAL = re.compile(r'[,;]?\s*\b(?:et\s+al|and\s+others)\b\s*\.?\s*$', re.I)


def _split_bib_and(s):
    """Split an author field on a whitespace-delimited ` and ` at brace depth 0 ONLY.

    This is the BibTeX rule, and getting it right closes two wrong-accepts:
      * A `{...}`-grouped `and` is NOT a separator — a corporate author
        `{Research and Development Team}` (or double-braced `{{...}}`) is ONE author,
        not two people. Folding braces away *before* the split (the old bug) let a
        corporate author normalize to the same list as two split names.
      * `;` and `&` are NOT BibTeX separators — `Alice Smith & Bob Jones` is one
        (malformed) author, not two clean ones. The old `re.split(..|;|&)` split them.
    Splitting the RAW string (braces intact) and folding each chunk afterwards is what
    makes both hold.
    """
    parts, buf, depth, i, n = [], [], 0, 0, len(s)
    while i < n:
        c = s[i]
        if c == '{':
            depth += 1; buf.append(c); i += 1
        elif c == '}':
            depth = max(0, depth - 1); buf.append(c); i += 1
        elif depth == 0 and c.isspace():
            m = re.match(r'\s+and\s+', s[i:], re.I)
            if m and ''.join(buf).strip():
                parts.append(''.join(buf)); buf = []; i += m.end()
            else:
                buf.append(c); i += 1
        else:
            buf.append(c); i += 1
    if ''.join(buf).strip():
        parts.append(''.join(buf))
    return parts


def norm_authors(s):
    """Order-PRESERVING surname list.

    'Vaswani, Ashish and Shazeer, Noam' -> ['vaswani','shazeer']
    'Ashish Vaswani and Noam Shazeer'   -> ['vaswani','shazeer']
    'van der Berg, Jan' == 'Jan van der Berg' -> ['vanderberg']
    'Smith, John Jr.'   == 'John Smith Jr.'   -> ['smith']

    Order is preserved deliberately: a re-ordered author list is one of the exact
    defects this skill exists to catch, so it must NOT normalize to equal.

    Truncation markers ('and others', 'et al.') are dropped, so a truncated `.bib`
    list and a full web list compare on the names they share. That means truncation
    alone does not escalate -- but it also cannot hide a *changed* name, because every
    listed position is still compared in order.
    """
    s = s or ''
    # Strip a TERMINAL truncation marker ('et al.'/'and others') BEFORE splitting, so a
    # truncated .bib list and a full web list compare on the names they share (a sentinel
    # below still stops a truncated list matching a complete one). Split on a brace-depth-0
    # ` and ` only — braces protect a corporate author's internal 'and', and ';'/'&' are
    # not separators — then fold each chunk.
    stripped = ETAL.sub(' ', s)
    truncated = _fold(stripped) != _fold(s)   # a terminal 'et al.'/'and others' was stripped
    out = []
    for raw_chunk in _split_bib_and(stripped):
        chunk = _fold(raw_chunk).strip(' .,')
        if not chunk:
            continue
        # Pull generational suffixes out of the WHOLE name first, so a suffix is captured
        # whether it sits by the surname ("John Smith Jr.") or after the given name in
        # comma form ("Smith, John Jr."). A CONFLICTING suffix is a different person.
        suffix = ''.join(sorted(_alnum(w) for w in chunk.split()
                                if _alnum(w) in SUFFIXES))
        if ',' in chunk:                      # "Last, First" -> surname is before the comma
            surname_words = chunk.split(',')[0].split()
            given = chunk.split(',', 1)[1]
        else:                                 # "First M. Last" -> surname is the tail
            words = [w for w in chunk.split() if w]
            words = [w for w in words if _alnum(w) not in SUFFIXES] or words
            # Walk left from the tail while the preceding word is a nobiliary particle,
            # so "jan van der berg" yields "van der berg", not "berg".
            i = len(words) - 1
            while i > 0 and _alnum(words[i - 1]) in PARTICLES:
                i -= 1
            surname_words = words[i:]
            given = ' '.join(words[:i]) if i > 0 else ''
        # A surname that is ENTIRELY a suffix token — a real surname like 'Ii' (井伊), 'III',
        # or 'Jr' — must NOT be filtered to nothing: doing so dropped the whole author and let
        # a missing coauthor compare equal (a false MATCH). Keep the token when nothing remains.
        surname_words = [w for w in surname_words if _alnum(w) not in SUFFIXES] or surname_words
        surname = _alnum(''.join(surname_words))
        # Surname alone accepts 'John Smith' vs 'Jane Smith' and 'Plato' vs 'John
        # Plato', so carry the given name too and let authors_equal decide what is
        # cosmetic (abbreviation and dropped middles) versus a real difference.
        given = ' '.join(w for w in given.split() if _alnum(w) not in SUFFIXES)
        # Keep the full given-name token sequence. Comparison (authors_equal) decides
        # what is cosmetic: it tolerates abbreviation and a DROPPED middle name, but a
        # PRESENT-on-both-sides middle name must agree ('John P. Smith' vs 'John Q.
        # Smith' is a different person), and a given name absent on one side while the
        # other spells one out is a real difference, not a wildcard.
        g = '.'.join(_alnum(w) for w in given.split() if _alnum(w))
        # Keep the FULL given name, not just the initial. Comparison below downgrades to
        # initial-only when EITHER side is abbreviated, so 'J. Smith' still matches 'John
        # Smith' while 'John Smith' vs 'Jane Smith' now differs.
        if surname:
            out.append(surname + '|' + g + '|' + suffix)
    if truncated:
        # The list claimed MORE authors than it named. Carry that as a sentinel entry so a
        # truncated list never compares equal to a complete list of the same visible names
        # (which would hide a dropped/extra coauthor). Two truncated lists still agree.
        out.append('|||truncated')
    return out


def _looks_abbreviated(tok):
    """A one-character Latin token is a typical initial abbreviation ('J.' -> 'j').
    A one-character NON-LATIN token is not: '伟' is a full CJK given name, not an
    abbreviation of '伟明'. Comparing those by first character alone silently accepted
    dropped/changed CJK given-name characters."""
    return len(tok) == 1 and 'a' <= tok <= 'z'


def _given_eq(gx, gy):
    """Compare two dot-joined given-name token sequences.

    Tolerated as cosmetic:
      - Latin abbreviation:  'j'      vs 'john'         -> equal
      - dropped middles:     'john'   vs 'john.a'       -> equal
    NOT tolerated:
      - different name:      'john'   vs 'jane'         -> differ
      - both middles present and different: 'john.p' vs 'john.q' -> differ
      - one side names nobody while the other does: '' vs 'jane' -> differ
      - one-char NON-LATIN vs longer non-Latin: '伟' vs '伟明' -> differ (see
        `_looks_abbreviated`).
    """
    if not gx and not gy:
        return True
    if not gx or not gy:
        # A given name on one side and none on the other is a real difference: 'Smith'
        # is not evidence for 'Jane Smith'. Treating the empty side as a wildcard let a
        # wrong author through.
        return False
    tx, ty = gx.split('.'), gy.split('.')
    # First given name must agree; abbreviation is cosmetic ONLY for Latin initials.
    fx, fy = tx[0], ty[0]
    if _looks_abbreviated(fx) or _looks_abbreviated(fy):
        if fx[0] != fy[0]:
            return False
    elif fx != fy:
        return False
    # Dropped-middle tolerance is a Latin-name convention (a .bib legitimately omits a
    # middle name or initial: 'John Smith' vs 'John A. Smith'). For a CJK-style given name
    # like '伟' vs '伟明' — or '伟' vs '伟 明' — a difference in the token count IS the
    # name difference and must not be tolerated as a dropped middle. Detect that any token
    # on either side contains a non-Latin letter and require equal token counts then.
    def _any_non_latin(toks):
        return any(any(c.isalpha() and not ('a' <= c <= 'z') for c in t) for t in toks)
    if (_any_non_latin(tx) or _any_non_latin(ty)) and len(tx) != len(ty):
        return False
    # Middles: for the positions BOTH sides supply, they must agree (Latin abbreviation
    # is cosmetic, non-Latin must match exactly).
    for mx, my in zip(tx[1:], ty[1:]):
        if _looks_abbreviated(mx) or _looks_abbreviated(my):
            if mx[0] != my[0]:
                return False
        elif mx != my:
            return False
    return True


def authors_equal(a, b):
    """Compare two norm_authors() lists. Order matters; abbreviation is cosmetic."""
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        px, py = x.split('|'), y.split('|')
        sx, gx, sufx = px[0], px[1] if len(px) > 1 else '', px[2] if len(px) > 2 else ''
        sy, gy, sufy = py[0], py[1] if len(py) > 1 else '', py[2] if len(py) > 2 else ''
        if sx != sy or not _given_eq(gx, gy):
            return False
        # A conflicting generational suffix is a different person (Jr vs Sr); a suffix
        # present on one side only is a tolerable omission.
        if sufx and sufy and sufx != sufy:
            return False
    return True


# DECLARED venue alias classes. Same class => same event, so differing wording is
# cosmetic. This table is deliberately explicit and small: a venue pair that is NOT
# in it escalates rather than being guessed at.
#
# Membership is WHOLE-STRING equality against a class, never substring containment.
# Substring matching silently collapses distinct conferences -- 'acl' is a substring of
# 'naacl' and of 'eacl', so ACL/NAACL/EACL would all become one class and a wrong-venue
# citation would be ACCEPTED. That is the one direction this gate must never fail in.
VENUE_ALIASES = [
    {'neurips', 'nips', 'advances in neural information processing systems',
     'conference on neural information processing systems'},
    {'icml', 'international conference on machine learning'},
    {'iclr', 'international conference on learning representations'},
    {'cvpr', 'ieee conference on computer vision and pattern recognition',
     'computer vision and pattern recognition',
     'ieee cvf conference on computer vision and pattern recognition'},
    {'iccv', 'international conference on computer vision'},
    {'eccv', 'european conference on computer vision'},
    {'acl', 'annual meeting of the association for computational linguistics'},
    {'naacl', 'north american chapter of the association for computational linguistics',
     'conference of the north american chapter of the association for computational linguistics'},
    {'eacl', 'european chapter of the association for computational linguistics'},
    {'emnlp', 'conference on empirical methods in natural language processing'},
    {'aaai', 'aaai conference on artificial intelligence'},
    {'ijcai', 'international joint conference on artificial intelligence'},
    {'jmlr', 'journal of machine learning research'},
    {'tmlr', 'transactions on machine learning research'},
]
PREPRINT = {'arxiv', 'arxiv preprint', 'corr', 'openreview', 'preprint', 'biorxiv'}

# A satellite/secondary track is NOT the main conference. Without this, 'ICML Workshop
# on Foo' would alias to ICML and a workshop-vs-main-track error would be accepted.
SUBVENUE = re.compile(r'\b(workshop|workshops|companion|demo|demos|tutorial|tutorials|'
                      r'short\s+papers|student|doctoral|findings|track|symposium|poster)\b')

# A difference in any of these is never cosmetic.
IDENTIFYING = ('authors', 'year', 'doi', 'arxiv', 'title')  # differing here is never cosmetic
COMPARED = ('title', 'year', 'doi', 'arxiv', 'volume', 'pages')
DOI_LIKE = ('doi', 'arxiv')          # inner punctuation significant
NUM_LIKE = ('year', 'volume', 'pages', 'issue', 'number', 'chapter')  # dash-style cosmetic, rest significant


def venue_class(v):
    n = norm_text(v)
    if not n:
        return None
    # SUBVENUE first: 'arXiv Workshop on Foo' is a satellite event, not the arXiv
    # preprint server, and must not take the PREPRINT shortcut into a MINOR verdict.
    if SUBVENUE.search(n):
        return 'SUB:' + n        # satellite track: only ever equal to itself
    # PREPRINT only for the exact preprint-server names, not any string beginning 'arxiv'
    # ('arXiv Press' is a different venue). arXiv-with-an-id ('arxiv 2301.00001') is also
    # a preprint -- but the EMBEDDED ID must be kept, or two different arXiv ids in the
    # venue string ('arXiv:2401.00001' vs 'arXiv:2401.99999') both map to bare PREPRINT and
    # compare equal (different works accepted as MATCH). norm_text preserves a dot BETWEEN
    # digits (so '2401.00001' survives) but spaces out ':' and a leading dot, so accept
    # either a dot or whitespace between the two digit groups and rejoin the id.
    m = re.match(r'^arxiv[\s:.]*(\d{4})[\s.]*(\d{4,5})(?:[\s.]*(v\d+))?$', n)
    if m:
        return 'PREPRINT:%s.%s%s' % (m.group(1), m.group(2), m.group(3) or '')
    if n in PREPRINT:
        return 'PREPRINT'          # a bare 'arXiv preprint' with no id: only equal to itself
    for i, cls in enumerate(VENUE_ALIASES):
        if n in cls:             # WHOLE-STRING membership; see the note above
            return 'V%d' % i
    return 'RAW:' + n            # unknown to the table -> only ever equal to itself


REQUIRED_KEYS = ('dedup_key', 'key', 'found', 'fields')

# --------------------------------------------------------------- BibTeX parsing
# The gate recomputes the field diff from A's and B's RAW records; it does not trust C's
# restatement (C is a model shard — a faulty/adversarial C that omits a differing field or
# forges `blind` could otherwise obtain a MATCH, which is the exact shard-trust flaw the
# gate exists to remove). C is consulted ONLY for routing flags.

# @type{key, field = {value} | "value" | bareword, ...}
_BIB_ENTRY = re.compile(r'@\s*([A-Za-z]+)\s*\{\s*([^,\s]*)\s*,(.*)\}\s*$', re.S)


def _split_bib_fields(body):
    """Yield (name, raw_value) from a bibtex entry body, respecting nested {} and quotes."""
    i, n = 0, len(body)
    while i < n:
        # field name
        m = re.compile(r'([A-Za-z][A-Za-z0-9_-]*)\s*=\s*').match(body, i)
        if not m:
            i += 1
            continue
        name = m.group(1).lower()
        i = m.end()
        if i >= n:
            break
        if body[i] == '{':
            depth, j = 0, i
            while j < n:
                if body[j] == '{':
                    depth += 1
                elif body[j] == '}':
                    depth -= 1
                    if depth == 0:
                        j += 1
                        break
                j += 1
            val = body[i + 1:j - 1]
            i = j
        elif body[i] == '"':
            # Inside "..." bibtex still recognizes {...} groups. A `"` inside a brace
            # group is text, not a value terminator. Track brace depth to close at the
            # right `"` — otherwise `"M{\"u}ller..."` truncates at the inner quote.
            j, depth = i + 1, 0
            while j < n:
                c = body[j]
                if c == '{':
                    depth += 1
                elif c == '}':
                    depth = max(0, depth - 1)
                elif c == '"' and depth == 0:
                    break
                j += 1
            val = body[i + 1:j]
            i = j + 1
        else:                                   # bareword (number / macro)
            m2 = re.compile(r'[^,]*').match(body, i)
            val = m2.group(0).strip()
            i = m2.end()
        # Handle bibtex string concatenation: value # value # value ...
        while True:
            k = i
            while k < n and body[k] in ' \t\r\n':
                k += 1
            if k >= n or body[k] != '#':
                break
            k += 1
            while k < n and body[k] in ' \t\r\n':
                k += 1
            if k >= n:
                break
            if body[k] == '{':
                depth, j = 0, k
                while j < n:
                    if body[j] == '{':
                        depth += 1
                    elif body[j] == '}':
                        depth -= 1
                        if depth == 0:
                            j += 1
                            break
                    j += 1
                val += body[k + 1:j - 1]
                i = j
            elif body[k] == '"':
                j, depth = k + 1, 0
                while j < n:
                    c = body[j]
                    if c == '{':
                        depth += 1
                    elif c == '}':
                        depth = max(0, depth - 1)
                    elif c == '"' and depth == 0:
                        break
                    j += 1
                val += body[k + 1:j]
                i = j + 1
            else:
                # bareword: read to the next , or #
                j = k
                while j < n and body[j] not in ',#':
                    j += 1
                val += body[k:j].strip()
                i = j
        yield name, val.strip()
        # advance past the trailing comma
        while i < n and body[i] in ' \t\r\n,':
            i += 1


# Normalize the many bibtex venue/id field names to the gate's canonical field set.
_FIELD_ALIASES = {
    'journal': 'venue', 'booktitle': 'venue', 'venue': 'venue',
    'eprint': 'arxiv', 'archiveprefix': None, 'primaryclass': None,
    'url': 'url', 'doi': 'doi', 'author': 'authors', 'authors': 'authors',
    'title': 'title', 'year': 'year', 'date': 'year', 'volume': 'volume',
    'number': 'issue', 'issue': 'issue',        # both mean 'issue-of-journal'
    'pages': 'pages', 'chapter': 'chapter',
    'publisher': 'publisher', 'editor': 'editor', 'isbn': 'isbn', 'issn': 'issn',
    'howpublished': 'howpublished', 'note': 'note', 'month': 'month', 'series': 'series',
}


def _put_field(out, conflicts, canon, val):
    """First value for a canonical field wins (matching the historical parser behaviour),
    but a DIFFERING duplicate is recorded as a conflict rather than silently dropped: two
    disagreeing `author=` (or any field) lines in one entry are ambiguous evidence and must
    ESCALATE, not vanish. Recorded conflicts surface via build_entry as a routing flag."""
    if not val:
        return
    if canon in out:
        if out[canon] != val:
            conflicts.add(canon)
    else:
        out[canon] = val


def parse_bibtex(bibtex):
    """Parse a single bibtex record -> {canonical_field: value}. Unknown fields are kept
    under their own lowercased name so the gate still compares them (fail-closed).

    Duplicate fields with differing values are recorded under the reserved `__conflicts__`
    key (a list of conflicted canonical field names), which build_entry turns into an
    ESCALATE-forcing flag.

    Strict: if we cannot find a well-formed `@type{key, ...}` entry, return {}. An
    old permissive fallback parsed the whole string, so a stray '}' or an @string{...}
    macro definition produced phantom fields (e.g. '2020}' as year, 'tcs: TCS' as field).
    An unparseable record is not evidence.
    """
    if not bibtex:
        return {}
    m = _BIB_ENTRY.search(bibtex.strip())
    if not m:
        return {}                # not a real bibtex record; caller sees empty -> ESCALATE
    kind = m.group(1).lower()
    if kind == 'string':         # @string{FOO = "…"} is a MACRO defn, not an entry
        return {}
    body = m.group(3)
    out, conflicts, archive_prefix, eprint_raw = {}, set(), None, None
    for name, val in _split_bib_fields(body):
        if name == 'archiveprefix':
            if archive_prefix is not None and archive_prefix != val:
                conflicts.add('arxiv')
            archive_prefix = val
            continue
        if name == 'primaryclass':
            continue
        if name == 'eprint':
            if eprint_raw is not None and eprint_raw != val:
                conflicts.add('eprint')
            eprint_raw = val
            continue
        canon = _FIELD_ALIASES.get(name, name)     # unknown -> its own name (still compared)
        if canon is None:
            continue
        _put_field(out, conflicts, canon, val)
    # Route `eprint` by its archivePrefix. `arxiv` for arXiv; anything else (HAL, bioRxiv,
    # OSF, …) is kept as `eprint:<prefix>:<id>` so two different eprint spaces do NOT compare
    # equal. Without a prefix, only an obvious arXiv id form gets the arxiv namespace.
    if eprint_raw:
        pfx = (archive_prefix or '').strip().lower()
        if pfx == 'arxiv' or (not pfx and re.match(r'(?i)^arxiv', eprint_raw)):
            _put_field(out, conflicts, 'arxiv', eprint_raw if re.match(r'(?i)^arxiv', eprint_raw)
                                     else 'arXiv:' + eprint_raw)
        elif not pfx and re.match(r'^\d{4}\.\d{4,5}(v\d+)?$', eprint_raw):
            _put_field(out, conflicts, 'arxiv', 'arXiv:' + eprint_raw)
        else:
            _put_field(out, conflicts, 'eprint', '%s:%s' % (pfx or 'unknown', eprint_raw))
    if conflicts:
        out['__conflicts__'] = sorted(conflicts)
    return out


def build_entry(dedup_key, key, a_rec, b_rec, blind, found, flags):
    """Assemble the {fields:{status,ours,web}} entry verify() consumes, from A and B RAW
    records (parsed here) -- NOT from C. `blind` comes from B; `flags`/`found` route."""
    ours = parse_bibtex(a_rec)
    web = parse_bibtex(b_rec)
    # A duplicate field whose two values disagree is ambiguous evidence -> force ESCALATE
    # (never silently keep the first). Carried as a flag, which verify() escalates on.
    conflicts = sorted(set(ours.pop('__conflicts__', [])) | set(web.pop('__conflicts__', [])))
    fields = {}
    for f in sorted(set(ours) | set(web)):
        ev = {}
        if f in ours:
            ev['ours'] = ours[f]
        if f in web:
            ev['web'] = web[f]
        fields[f] = ev
    all_flags = list(flags or [])
    if conflicts:
        all_flags.append('field_conflict:' + ','.join(conflicts))
    return {'dedup_key': dedup_key, 'key': key, 'found': found, 'blind': blind,
            'flags': all_flags, 'fields': fields}


def recompute_routing_flags(a_rec, b_entry):
    """Routing flags RE-DERIVED from A's and B's own raw artifacts, so the gate never
    depends on C to raise them (C is a model shard; see assemble_flags):
      * web_record_absent          — B's own `found` is not true.
      * degraded_search            — B's own `sources_tried` marks a source down/rate-limited.
      * url_only_source_unqueried  — A carries a url/howpublished but no arXiv id / DOI, B did
        not confirm, and B never queried a general-web/landing source (only indexers that
        structurally cannot see that url). This forces the main-agent url fetch in Step 4.
    """
    b_entry = b_entry if isinstance(b_entry, dict) else {}
    flags = set()
    found = b_entry.get('found') is True
    sources = b_entry.get('sources_tried')
    joined = (' '.join(str(x) for x in sources) if isinstance(sources, list)
              else str(sources or '')).lower()
    # Broad on purpose: a MISSED degradation token is the dangerous direction (a genuinely
    # degraded search reads as a clean not-found / clean match), so over-flag rather than
    # under-flag. Covers HTTP 4xx/5xx and the common bot-block / quota / transport failures.
    if re.search(r'(4\d\d|5\d\d|\bdown\b|time.?d?.?out|\berror\b|rate.?limit|throttl|block|'
                 r'unavailable|unreachable|refused|reset|forbidden|captcha|quota|denied|'
                 r'exceeded|\bssl\b|handshake|\bfail)', joined):
        flags.add('degraded_search')
    if not found:
        flags.add('web_record_absent')
        ours = parse_bibtex(a_rec)
        has_url = bool(ours.get('url') or ours.get('howpublished'))
        has_id = bool(ours.get('arxiv') or ours.get('doi'))
        queried_web = bool(re.search(r'(\bweb\b|\burl\b|landing|google|bing|duckduckgo|http)', joined))
        if has_url and not has_id and not queried_web:
            flags.add('url_only_source_unqueried')
    return flags


def assemble_flags(c_entry, a_rec, b_entry):
    """Final routing flags = C's advisory flags (sanitized) ∪ flags recomputed from A/B.

    C is NOT in the trust path: a C that OMITS a flag cannot wave an entry through, because
    recompute_routing_flags re-derives from A/B what the routing conditions actually are; and
    a C SCHEMA VIOLATION (`flags` not a list, or a non-string/empty item) fails CLOSED by
    adding `c_schema_invalid` (→ ESCALATE) instead of being silently coerced to no-flags.
    """
    raw = c_entry.get('flags', []) if isinstance(c_entry, dict) else None
    flags, bad = set(), False
    if isinstance(raw, list):
        for x in raw:
            if isinstance(x, str) and x.strip():
                flags.add(x.strip())
            else:
                bad = True                # non-string / empty flag item is a schema violation
    elif raw not in (None, ''):
        bad = True                        # `flags` present but not a list is a schema violation
    if bad:
        flags.add('c_schema_invalid')
    flags |= recompute_routing_flags(a_rec, b_entry)
    return sorted(flags)


def read_sides(entry):
    """Extract {field: value} for each provenance from C's DOCUMENTED schema.

    Step 3 emits nested per-field evidence:
        {"fields": {"<field>": {"status": ..., "ours": ..., "web": ...}}}
    Read exactly that. (An earlier revision of this gate read top-level `ours`/`web`
    dicts, which do not exist in a conforming artifact -- every entry escalated, so the
    gate was inert. Keep the shapes in sync: schema change here means schema change in
    both SKILL.md files.)
    """
    ours, web = {}, {}
    for fname, ev in (entry.get('fields') or {}).items():
        if not isinstance(ev, dict):
            continue
        if ev.get('ours') not in (None, ''):
            ours[fname] = ev.get('ours')
        if ev.get('web') not in (None, ''):
            web[fname] = ev.get('web')
    return ours, web


def verify(entry):
    """-> (verdict, reason, per_field_status). verdict in MATCH|MINOR|ESCALATE."""
    fields = {}

    # Schema validation is part of the gate: a malformed entry is not evidence, so it
    # escalates rather than being silently treated as "nothing differs".
    if not isinstance(entry, dict):
        return 'ESCALATE', 'entry is not an object', fields
    missing = [k for k in REQUIRED_KEYS if k not in entry]
    if missing:
        return 'ESCALATE', 'entry missing required key(s): ' + ','.join(missing), fields
    if not isinstance(entry.get('fields'), dict) or not entry['fields']:
        return 'ESCALATE', 'entry has no per-field evidence', fields

    flags = entry.get('flags') or []
    if flags:
        return 'ESCALATE', 'flags: ' + ','.join(sorted(flags)), fields
    if entry.get('found') is not True:
        return 'ESCALATE', 'web_record_absent (B did not confirm)', fields

    ours, web = read_sides(entry)
    if not ours or not web:
        return 'ESCALATE', 'one provenance carries no fields at all', fields
    differs, absent, cosmetic = [], [], []

    # Compare EVERY field either side carries, not just a hardcoded list. A field the gate
    # does not know about (issue, number, editor, publisher, chapter, ...) is compared as
    # text and, if it differs, escalates — otherwise a wrong `issue`/`number` would pass
    # silently just because it is not in COMPARED. `authors`/`venue` have bespoke handling
    # below, so they are excluded here.
    for f in sorted((set(ours) | set(web)) - {'authors', 'venue'}):
        o, w = ours.get(f), web.get(f)
        if not o or not w:
            if o or w:
                fields[f] = 'absent'
                absent.append(f)
            continue
        n = (norm_doi if f in DOI_LIKE else norm_id if f in NUM_LIKE
             else norm_text if f == 'title' else norm_ident)
        if not n(o) or not n(w):
            # A value that normalizes to nothing (a bare 'doi:' resolver, a
            # punctuation-only title like '---') is not evidence of anything. Treat it as
            # absent -- which escalates -- rather than letting '' == '' read as agreement.
            fields[f] = 'absent'
            absent.append(f)
            continue
        if n(o) == n(w):
            fields[f] = 'same'
            if o != w:
                cosmetic.append(f)
        else:
            fields[f] = 'differs'
            differs.append(f)

    ao, aw = norm_authors(ours.get('authors')), norm_authors(web.get('authors'))
    if not ao or not aw:
        fields['authors'] = 'absent'
        absent.append('authors')
    elif authors_equal(ao, aw):
        fields['authors'] = 'same'
    else:
        fields['authors'] = 'differs'
        differs.append('authors')

    co, cw = venue_class(ours.get('venue')), venue_class(web.get('venue'))
    if co is None or cw is None:
        fields['venue'] = 'absent'
        absent.append('venue')
    elif co == cw:
        fields['venue'] = 'same'
        if norm_text(ours.get('venue')) != norm_text(web.get('venue')):
            cosmetic.append('venue')
    elif (co.startswith('PREPRINT') or cw.startswith('PREPRINT')) and (
            str(co).startswith('V') or str(cw).startswith('V')):
        # Preprint (bare or id-bearing) on one side, a KNOWN published venue on the other
        # -> the benign preprint-vs-published case. arXiv vs an unknown/RAW venue
        # ('arXiv Press') is NOT this; it falls through and escalates. Two DIFFERENT
        # preprint ids ('PREPRINT:2401.00001' vs 'PREPRINT:2401.99999') are caught by the
        # `co == cw` test above failing, so they reach the `differs` branch -> ESCALATE.
        fields['venue'] = 'preprint_vs_published'
    elif co.startswith(('RAW:', 'SUB:')) or cw.startswith(('RAW:', 'SUB:')):
        fields['venue'] = 'differs_unknown_alias'
        return 'ESCALATE', 'venue pair not resolvable from the declared alias table', fields
    else:
        fields['venue'] = 'differs'
        differs.append('venue')

    # Fail-closed ladder: anything not provably cosmetic leaves as ESCALATE.
    # A one-sided ABSENCE is not evidence of agreement — the two records simply were not
    # compared on that field, so calling it MATCH would overstate what the gate checked.
    # Only the fields both provenances carry can support an accept, and the identifying
    # set must be fully covered on both sides.
    if differs:
        kind = 'identifying' if any(f in IDENTIFYING for f in differs) else 'secondary'
        return 'ESCALATE', '%s field differs: %s' % (kind, ','.join(differs)), fields
    if absent:
        kind = 'identifying' if any(f in IDENTIFYING for f in absent) else 'secondary'
        return 'ESCALATE', '%s field absent on one side: %s' % (kind, ','.join(absent)), fields
    # Core identity must be covered on both sides. `doi` and `arxiv` are ALTERNATIVES
    # (a venue paper has a DOI, a preprint an arXiv id, rarely both), so require at
    # least one of them rather than every one.
    missing_core = [f for f in ('title', 'authors', 'year', 'venue') if f not in fields]
    if missing_core:
        return 'ESCALATE', 'no evidence for core field(s): ' + ','.join(missing_core), fields
    if not ({'doi', 'arxiv'} & set(fields)):
        return 'ESCALATE', 'no identifier evidence (neither doi nor arxiv)', fields
    if fields.get('venue') == 'preprint_vs_published':
        # Reached only when nothing else differs and nothing is absent, so this really
        # is the sole difference.
        return 'MINOR', 'preprint vs published venue is the only difference', fields
    if cosmetic:
        return 'MATCH', 'cosmetic only: ' + ','.join(cosmetic), fields
    return 'MATCH', 'all compared fields identical', fields


# ------------------------------------------------------ coverage manifest + I/O safety
def _safe(s):
    """Strip control chars (newline, ANSI ESC, etc.) from shard-derived text before it is
    printed, so a crafted cite key / field value cannot inject terminal escapes or forge a
    log line. Ordinary printable content (incl. non-ASCII) is preserved."""
    return re.sub(r'[\x00-\x1f\x7f]', ' ', str(s))


def manifest_title_hash(title):
    """Stable title fingerprint for the Step-1 coverage manifest.

    Computed by --build-manifest from the .bib at Step 1 AND from A's parsed title at verify
    time — both via THIS function and THIS parser — so a drop-and-substitute that preserves
    the ordinal *set* still changes the (cite_key, title_hash) MAPPING and fails the gate.
    Case/whitespace-insensitive so cosmetic .bib reflow does not spuriously fail coverage.
    """
    t = re.sub(r'\s+', ' ', (title or '').strip().lower())
    return hashlib.sha1(t.encode('utf-8')).hexdigest()[:16]


def iter_bib_entries(text):
    """Yield (cite_key, raw_entry_text) for each brace-matched @type{key,...} in a .bib.
    @string/@comment/@preamble macro blocks are skipped (not real entries)."""
    i, n = 0, len(text)
    while i < n:
        at = text.find('@', i)
        if at < 0:
            break
        m = re.match(r'@\s*([A-Za-z]+)\s*\{', text[at:])
        if not m:
            i = at + 1
            continue
        kind = m.group(1).lower()
        depth, j = 0, at + m.end() - 1        # j = index of the opening '{'
        while j < n:
            if text[j] == '{':
                depth += 1
            elif text[j] == '}':
                depth -= 1
                if depth == 0:
                    j += 1
                    break
            j += 1
        raw, i = text[at:j], j
        if kind in ('string', 'comment', 'preamble'):
            continue
        km = re.match(r'@\s*[A-Za-z]+\s*\{\s*([^,\s]+)\s*,', raw)
        if km:
            yield km.group(1), raw


def build_manifest(bib_path, keymap_path, out_path):
    """Emit the Step-1 coverage manifest `dedup_key<TAB>cite_key<TAB>title_hash` from the
    .bib + the ordinal->cite_key keymap, using the gate's own parser so the gate can later
    verify A against it as a MAPPING (not just a set)."""
    try:
        text = open(bib_path, encoding='utf-8', errors='replace').read()
    except OSError as exc:
        print('ERROR: cannot read --bib %s: %s' % (bib_path, exc), file=sys.stderr)
        return 1
    by_key = {}
    for key, raw in iter_bib_entries(text):
        by_key.setdefault(key, raw)           # first definition wins (bibtex behaviour)
    try:
        km = open(keymap_path, encoding='utf-8').read()
    except OSError as exc:
        print('ERROR: cannot read --keymap %s: %s' % (keymap_path, exc), file=sys.stderr)
        return 1
    lines, missing = [], []
    for raw_line in km.splitlines():
        if not raw_line.strip():
            continue
        parts = raw_line.split('\t')
        if len(parts) < 2 or not parts[0].strip() or not parts[1].strip():
            print("ERROR: --keymap line is not '<dedup_key>\\t<cite_key>': %r" % raw_line, file=sys.stderr)
            return 1
        dk, ck = parts[0].strip(), parts[1].strip()
        raw = by_key.get(ck)
        if raw is None:
            missing.append(ck)
            th = ''
        else:
            th = manifest_title_hash(parse_bibtex(raw).get('title') or '')
        lines.append('%s\t%s\t%s' % (dk, ck, th))
    if missing:
        print('ERROR: --build-manifest: cite key(s) not found in %s: %s'
              % (bib_path, ','.join(missing)), file=sys.stderr)
        return 1
    try:
        open(out_path, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    except OSError as exc:
        print('ERROR: cannot write --out-manifest %s: %s' % (out_path, exc), file=sys.stderr)
        return 1
    print('wrote %s (%d entries)' % (out_path, len(lines)))
    return 0


def load_manifest(path):
    """Read a `dedup_key<TAB>cite_key<TAB>title_hash` manifest -> {dedup_key:(cite_key,hash)}."""
    try:
        raw = open(path, encoding='utf-8').read()
    except OSError as exc:
        print('ERROR: cannot read --expect-manifest %s: %s' % (path, exc), file=sys.stderr)
        return None
    want = {}
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = line.split('\t')
        if len(parts) < 3:
            print('ERROR: --expect-manifest line is not 3 tab-separated columns: %r' % line, file=sys.stderr)
            return None
        want[parts[0].strip()] = (parts[1].strip(), parts[2].strip())
    return want


def manifest_mismatches(want, ai):
    """Verify A against the Step-1 manifest as a MAPPING: same dedup_key set, and for each
    ordinal the SAME cite key and SAME title hash. Catches a drop-and-substitute that keeps
    the count/ordinal set identical (which --expect / --expect-keys cannot)."""
    errs = []
    if set(want) != set(ai):
        miss = sorted(set(want) - set(ai))
        extra = sorted(set(ai) - set(want))
        if miss:
            errs.append('dedup_key(s) in manifest missing from A: ' + ','.join(miss))
        if extra:
            errs.append('dedup_key(s) in A not in manifest: ' + ','.join(extra))
    for dk in sorted(set(want) & set(ai)):
        exp_key, exp_hash = want[dk]
        a_e = ai[dk]
        a_key = str(a_e.get('key') or '').strip()
        a_hash = manifest_title_hash(parse_bibtex(a_e.get('bibtex')).get('title') or '')
        if a_key != exp_key:
            errs.append('%s: cite key A=%r manifest=%r (substituted downstream?)' % (dk, _safe(a_key), _safe(exp_key)))
        elif a_hash != exp_hash:
            errs.append('%s (%s): title hash A=%s manifest=%s (entry changed downstream?)'
                        % (dk, _safe(a_key), a_hash, exp_hash))
    return errs


# --------------------------------------------------------------------- selftest
def _entry(ours, web, found=True, flags=None, key='k', blind=True):
    """Build a SCHEMA-CONFORMING entry (nested fields.<f>.ours/web).

    The fixtures deliberately use the same shape Step 3 documents. An earlier revision
    of this selftest used flat top-level ours/web dicts, so it passed while the gate was
    inert against real artifacts -- do not reintroduce that shape.

    `blind` defaults True so these field-diff cases exercise the comparison logic; the
    blindness-enforcement path has its own dedicated cases below.
    """
    fields = {}
    for f in set(ours) | set(web):
        ev = {'status': 'same' if ours.get(f) == web.get(f) else 'differs'}
        if f in ours:
            ev['ours'] = ours[f]
        if f in web:
            ev['web'] = web[f]
        if f not in ours or f not in web:
            ev['status'] = 'absent'
        fields[f] = ev
    e = {'dedup_key': '01', 'key': key, 'found': found, 'fields': fields, 'blind': blind}
    if flags:
        e['flags'] = flags
    return e


FULL = ('title', 'authors', 'year', 'venue', 'doi')


def _both(**kw):
    """ours == web on every identifying field unless overridden via web_*.

    A non-core field named in kw (e.g. pages='1-234') is placed on BOTH sides, so a
    fixture testing that field's comparison does not accidentally test one-sided absence.
    """
    ours = {f: kw.get(f, 'X') for f in FULL}
    for k, v in kw.items():
        if not k.startswith('web_'):
            ours[k] = v
    web = dict(ours)
    for k, v in kw.items():
        if k.startswith('web_'):
            web[k[4:]] = v
    return ours, web


SELFTEST = [
    ("identical", _entry(*_both(title='Attention Is All You Need', authors='Vaswani, Ashish and Shazeer, Noam',
                                year='2017', venue='NeurIPS', doi='10.1/a')), 'MATCH'),
    ("brace/case cosmetic", _entry(*_both(title='{BERT}: Pre-training', web_title='BERT: Pre-Training',
                                          authors='Devlin, Jacob', web_authors='Jacob Devlin',
                                          year='2019', venue='NAACL', doi='10.1/b')), 'MATCH'),
    ("venue alias is cosmetic", _entry(*_both(venue='Advances in Neural Information Processing Systems',
                                              web_venue='NeurIPS', authors='Smith, A', web_authors='A Smith',
                                              year='2020', doi='10.1/c')), 'MATCH'),
    ("latex accent in surname", _entry(*_both(authors=r'Schl{\"o}gl, Anna', web_authors='Anna Schlogl',
                                              year='2021', venue='ACL', doi='10.1/d')), 'MATCH'),
    ("nobiliary particle", _entry(*_both(authors='van der Berg, Jan', web_authors='Jan van der Berg',
                                         year='2020', venue='ICML', doi='10.1/e')), 'MATCH'),
    ("generational suffix", _entry(*_both(authors='Smith, John Jr.', web_authors='John Smith Jr.',
                                          year='2020', venue='ICML', doi='10.1/f')), 'MATCH'),
    ("truncated author list", _entry(*_both(authors='Vaswani, Ashish and others', web_authors='Ashish Vaswani et al.',
                                            year='2017', venue='NeurIPS', doi='10.1/g')), 'MATCH'),
    ("NAACL long form aliases", _entry(*_both(venue='NAACL', authors='A, B', web_authors='B A', year='2021', doi='10.1/h',
                                              web_venue='North American Chapter of the Association for Computational Linguistics')), 'MATCH'),
    ("preprint vs published", _entry(*_both(venue='arXiv preprint', web_venue='ICML', authors='A, B',
                                            web_authors='B A', year='2020', doi='10.1/i')), 'MINOR'),
    # --- must ESCALATE (fail-closed) ---
    ("dropped author", _entry(*_both(authors='Smith, A', web_authors='A Smith and B Jones')), 'ESCALATE'),
    ("reordered authors", _entry(*_both(authors='Zhang, X and Li, Y', web_authors='Y Li and X Zhang')), 'ESCALATE'),
    ("changed name in truncated list", _entry(*_both(authors='Smith, J and others', web_authors='J Jones et al.')), 'ESCALATE'),
    ("wrong year", _entry(*_both(year='2019', web_year='2020')), 'ESCALATE'),
    ("wrong doi", _entry(*_both(doi='10.5555/abc-def', web_doi='10.5555/abcdef')), 'ESCALATE'),
    ("title word changed", _entry(*_both(title='Deep Residual Learning', web_title='Deep Residual Networks')), 'ESCALATE'),
    ("ACL vs NAACL is not an alias", _entry(*_both(venue='ACL', web_venue='NAACL')), 'ESCALATE'),
    ("ACL vs EACL is not an alias", _entry(*_both(venue='ACL', web_venue='EACL')), 'ESCALATE'),
    ("workshop is not the main track", _entry(*_both(venue='ICML', web_venue='ICML Workshop on Foo')), 'ESCALATE'),
    ("NeurIPS track is not main", _entry(*_both(venue='NeurIPS', web_venue='NeurIPS Datasets and Benchmarks Track')), 'ESCALATE'),
    ("findings is not main", _entry(*_both(venue='EMNLP', web_venue='Findings of EMNLP')), 'ESCALATE'),
    ("different event", _entry(*_both(venue='ICML', web_venue='ICLR')), 'ESCALATE'),
    ("Cpp vs Csharp title", _entry(*_both(title='C++ Patterns', web_title='C# Patterns')), 'ESCALATE'),
    ("distinct CJK titles", _entry(*_both(title='深度学习', web_title='机器学习')), 'ESCALATE'),
    ("identifying absent one side", _entry({'title': 'T', 'authors': 'A, B', 'year': '2020', 'venue': 'ICML', 'doi': '10.1/x'},
                                           {'title': 'T', 'year': '2020', 'venue': 'ICML', 'doi': '10.1/x'}), 'ESCALATE'),
    ("secondary absent one side", _entry({'title': 'T', 'authors': 'A, B', 'year': '2020', 'venue': 'ICML', 'doi': '10.1/x', 'pages': '1-9'},
                                          {'title': 'T', 'authors': 'B A', 'year': '2020', 'venue': 'ICML', 'doi': '10.1/x'}), 'ESCALATE'),
    ("no evidence for an identifying field", _entry({'title': 'T', 'authors': 'A, B', 'year': '2020'},
                                                    {'title': 'T', 'authors': 'B A', 'year': '2020'}), 'ESCALATE'),
    ("flag present", _entry(*_both(), flags=['url_only_source_unqueried']), 'ESCALATE'),
    ("not found", _entry(*_both(), found=False), 'ESCALATE'),
    ("no per-field evidence", {'dedup_key': '01', 'key': 'k', 'found': True, 'fields': {}}, 'ESCALATE'),
    ("missing required key", {'dedup_key': '01', 'found': True, 'fields': {'title': {'status': 'same', 'ours': 'T', 'web': 'T'}}}, 'ESCALATE'),
    # --- round-4 wrong-accept regressions. Each of these once returned MATCH/MINOR.
    ("page range boundary moved", _entry(*_both(pages='1-234', web_pages='12-34')), 'ESCALATE'),
    ("dash style is still cosmetic", _entry(*_both(pages='12-20', web_pages='12--20')), 'MATCH'),
    ("arxiv wrapper vs doi wrapper", _entry(*_both(doi='https://arxiv.org/abs/2301.00001',
                                                   web_doi='https://doi.org/2301.00001')), 'ESCALATE'),
    ("doi resolver prefix is cosmetic", _entry(*_both(doi='https://doi.org/10.1/abc', web_doi='10.1/abc')), 'MATCH'),
    ("empty identifier is not an identifier", _entry(*_both(doi='doi:', web_doi='https://doi.org/')), 'ESCALATE'),
    ("same-initial given names differ", _entry(*_both(authors='Smith, John', web_authors='Jane Smith')), 'ESCALATE'),
    ("abbreviated given name still matches", _entry(*_both(authors='Smith, J.', web_authors='John Smith')), 'MATCH'),
    ("surname 'Others' is not a truncation marker", _entry(*_both(authors='Others, Ann', web_authors='Ann Others')), 'MATCH'),
    # --- blindness enforcement: an accept that is not blind-attested must NOT certify.
    ("clean match but not blind-attested downgrades",
     _entry(*_both(title='T', authors='A, B', year='2020', venue='ICML', doi='10.1/x'), blind=False), 'ESCALATE'),
    ("blind flag absent downgrades",
     {'dedup_key': '01', 'key': 'k', 'found': True,
      'fields': {'title': {'status': 'same', 'ours': 'T', 'web': 'T'},
                 'authors': {'status': 'same', 'ours': 'A, B', 'web': 'B A'},
                 'year': {'status': 'same', 'ours': '2020', 'web': '2020'},
                 'venue': {'status': 'same', 'ours': 'ICML', 'web': 'ICML'},
                 'doi': {'status': 'same', 'ours': '10.1/x', 'web': '10.1/x'}}}, 'ESCALATE'),
    ("a real discrepancy still ESCALATEs even when not blind",
     _entry(*_both(authors='Smith, A', web_authors='A Smith and B Jones'), blind=False), 'ESCALATE'),
    ("middle initial is cosmetic", _entry(*_both(authors='Smith, John A.', web_authors='John Smith')), 'MATCH'),
    ("initials vs full given name", _entry(*_both(authors='Smith, J A', web_authors='John Andrew Smith')), 'MATCH'),
    ("same-initial permutation still differs",
     _entry(*_both(authors='Smith, J and Doe, J', web_authors='J Doe and J Smith')), 'ESCALATE'),
    # --- round-5 wrong-accept regressions.
    # --- round-6 wrong-accept regressions (all were once MATCH/MINOR).
    # --- round-7 wrong-accepts (found by cross-model re-check on blind-attested fixtures).
    # --- round-8 STRUCTURAL wrong-accepts (ordinary input, cross-model round 7).
    ("different arXiv ids embedded in venue", _entry(*_both(venue='arXiv:2401.00001', web_venue='arXiv:2401.99999')), 'ESCALATE'),
    ("same arXiv id in venue, cosmetic form", _entry(*_both(venue='arXiv:2401.00001', web_venue='arxiv 2401.00001')), 'MATCH'),
    ("preprint-with-id vs known published", _entry(*_both(venue='arXiv:2401.00001', web_venue='ICML')), 'MINOR'),
    ("url path case is significant", _entry(*_both(url='http://x/Method.pdf', web_url='http://x/method.pdf')), 'ESCALATE'),
    ("diacritics in an id are significant", _entry(*_both(eprint='Resume', web_eprint='Résumé')), 'ESCALATE'),
    ("wrong url punctuation", _entry(*_both(url='https://arxiv.org/abs-2401/00001',
                                            web_url='https://arxiv.org/abs/2401.00001')), 'ESCALATE'),
    ("wrong eprint punctuation", _entry(*_both(eprint='2401-00001', web_eprint='2401.00001')), 'ESCALATE'),
    ("false truncation hides a coauthor",
     _entry(*_both(authors='Rivera, Elena and Patel, Omar and others', web_authors='Elena Rivera and Omar Patel')), 'ESCALATE'),
    ("both truncated still match",
     _entry(*_both(authors='Vaswani, A and others', web_authors='A Vaswani et al.')), 'MATCH'),
    ("conflicting generational suffix Jr vs Sr", _entry(*_both(authors='Smith, John Jr.', web_authors='John Smith Sr.')), 'ESCALATE'),
    ("dropped coauthor named Others", _entry(*_both(authors='Smith, A and Others, Ann', web_authors='A Smith')), 'ESCALATE'),
    ("underscore in year is significant", _entry(*_both(year='20_24', web_year='2024')), 'ESCALATE'),
    ("underscore in pages is significant", _entry(*_both(pages='e1_23', web_pages='e123')), 'ESCALATE'),
    ("unknown field (issue) differing escalates", _entry(*_both(issue='2', web_issue='3')), 'ESCALATE'),
    ("arXiv vs arXiv Press is not preprint-vs-published", _entry(*_both(venue='arXiv', web_venue='arXiv Press')), 'ESCALATE'),
    ("differing spelled middle name", _entry(*_both(authors='Smith, John Peter', web_authors='John Paul Smith')), 'ESCALATE'),
    ("abbreviated middle still cosmetic", _entry(*_both(authors='Smith, John P.', web_authors='John Peter Smith')), 'MATCH'),
    ("year dot is significant", _entry(*_both(year='20.24', web_year='2024')), 'ESCALATE'),
    ("volume dot is significant", _entry(*_both(volume='1.2', web_volume='12')), 'ESCALATE'),
    ("arXiv Press is not the preprint server", _entry(*_both(venue='arXiv Press', web_venue='ICML')), 'ESCALATE'),
    ("open-ended page range", _entry(*_both(pages='12-', web_pages='12')), 'ESCALATE'),
    ("bare surname is not a wildcard", _entry(*_both(authors='Smith', web_authors='Jane Smith')), 'ESCALATE'),
    ("differing middle initial", _entry(*_both(authors='Smith, John P.', web_authors='John Q. Smith')), 'ESCALATE'),
    ("same-first-initial reorder", _entry(*_both(authors='Smith, Alex A and Smith, Alex B',
                                                 web_authors='Alex B Smith and Alex A Smith')), 'ESCALATE'),
    ("punctuation-only title is not evidence", _entry(*_both(title='---', web_title='...')), 'ESCALATE'),
    ("arXiv workshop is not the preprint server",
     _entry(*_both(venue='arXiv Workshop on Foo', web_venue='ICML')), 'ESCALATE'),
    ("dropped middle is still cosmetic", _entry(*_both(authors='Smith, John A.', web_authors='John Smith')), 'MATCH'),
    ("lying status is recomputed, not trusted",
     {'dedup_key': '01', 'key': 'liar', 'found': True,
      'fields': {'title': {'status': 'same', 'ours': 'Real Title', 'web': 'Different Title'},
                 'authors': {'status': 'same', 'ours': 'A, B', 'web': 'B A'},
                 'year': {'status': 'same', 'ours': '2020', 'web': '2020'},
                 'venue': {'status': 'same', 'ours': 'ICML', 'web': 'ICML'},
                 'doi': {'status': 'same', 'ours': '10.1/x', 'web': '10.1/x'}}}, 'ESCALATE'),
    # --- round-9 wrong-accept regressions (each once returned MATCH/MINOR). ---
    ("version-number title punctuation is significant",
     _entry(*_both(title='Model 4.1', web_title='Model 4-1')), 'ESCALATE'),
    ("version-number title case-fold still matches",
     _entry(*_both(title='Model 4.1', web_title='MODEL 4.1')), 'MATCH'),
    ("decimal vs integer title token differs",
     _entry(*_both(title='Scaling to 10.5 B', web_title='Scaling to 105 B')), 'ESCALATE'),
    ("corporate braced author is one unit, not two people",
     _entry(*_both(authors='{{Research and Development Team}}', web_authors='Research and Development Team')), 'ESCALATE'),
    ("ampersand is not an author separator",
     _entry(*_both(authors='Alice Smith and Bob Jones', web_authors='Alice Smith & Bob Jones')), 'ESCALATE'),
    ("semicolon is not an author separator",
     _entry(*_both(authors='Alice Smith and Bob Jones', web_authors='Alice Smith; Bob Jones')), 'ESCALATE'),
    # --- round-10: suffix-token surname must not delete a coauthor (adversarial false-accept). ---
    ("suffix-token surname coauthor is not dropped",
     _entry(*_both(authors='Tanaka, Hiro and Ii, Naosuke', web_authors='Hiro Tanaka')), 'ESCALATE'),
    ("roman-numeral surname coauthor is not dropped",
     _entry(*_both(authors='Smith, Alice and III, Robert', web_authors='Alice Smith')), 'ESCALATE'),
    ("suffix-vs-published does not hide a dropped coauthor",
     _entry(*_both(authors='Tanaka, H and Ii, N', web_authors='H Tanaka', venue='arXiv', web_venue='ICML')), 'ESCALATE'),
    ("identical suffix-like surname still matches",
     _entry(*_both(authors='Ii, Naosuke', web_authors='Ii, Naosuke')), 'MATCH'),
]


def classify(entry):
    """verify() + blindness enforcement — the SINGLE decision path used by both the CLI
    and the selftest, so the selftest covers exactly what runs. A MATCH/MINOR that is not
    blind-attested downgrades to ESCALATE: flag, never certify.
    """
    verdict, reason, fields = verify(entry)
    if verdict in ('MATCH', 'MINOR') and (not isinstance(entry, dict) or entry.get('blind') is not True):
        reason = 'not blind-attested (B may have seen the .bib) — would be %s: %s' % (verdict, reason)
        verdict = 'ESCALATE'
    return verdict, reason, fields


# A+B recompute path: (name, a_bibtex, b_bibtex, b_blind, found, flags, want). These build
# the entry the SAME way main() does -- from A and B RAW records via build_entry -- so the
# parser and the "C is not trusted" property are covered by --selftest, not just by hand.
AB_SELFTEST = [
    ("recompute clean match",
     "@article{k, title={Deep Nets}, author={Smith, Alice and Jones, Bob}, year={2020}, journal={ICML}, doi={10.1/x}}",
     "@misc{w, title={Deep Nets}, author={Alice Smith and Bob Jones}, year={2020}, journal={ICML}, doi={10.1/x}}",
     True, True, [], 'MATCH'),
    ("recompute catches a diff C could have hidden (pages)",
     "@article{k, title={T}, author={Smith, A}, year={2020}, journal={ICML}, pages={1--9}, doi={10.1/x}}",
     "@misc{w, title={T}, author={A Smith}, year={2020}, journal={ICML}, pages={10--19}, doi={10.1/x}}",
     True, True, [], 'ESCALATE'),
    ("recompute catches a dropped coauthor",
     "@article{k, title={T}, author={Smith, A and Jones, B}, year={2020}, journal={ICML}, doi={10.1/x}}",
     "@misc{w, title={T}, author={A Smith}, year={2020}, journal={ICML}, doi={10.1/x}}",
     True, True, [], 'ESCALATE'),
    ("recompute: eprint bibtex field -> arxiv id, wrong id escalates",
     "@article{k, title={T}, author={Smith, A}, year={2020}, journal={ICML}, eprint={2401.00001}, archivePrefix={arXiv}}",
     "@misc{w, title={T}, author={A Smith}, year={2020}, journal={ICML}, eprint={2401.99999}, archivePrefix={arXiv}}",
     True, True, [], 'ESCALATE'),
    ("recompute: b_blind false never certifies",
     "@article{k, title={T}, author={Smith, A}, year={2020}, journal={ICML}, doi={10.1/x}}",
     "@misc{w, title={T}, author={A Smith}, year={2020}, journal={ICML}, doi={10.1/x}}",
     False, True, [], 'ESCALATE'),
    ("recompute: a flag escalates",
     "@article{k, title={T}, author={Smith, A}, year={2020}, journal={ICML}, doi={10.1/x}}",
     "@misc{w, title={T}, author={A Smith}, year={2020}, journal={ICML}, doi={10.1/x}}",
     True, True, ['url_only_source_unqueried'], 'ESCALATE'),
    # --- round-12 parser bug regressions
    ("quoted-form braced accent parses full author list",
     r"""@article{k, author="M{\"u}ller, Anna and Smith, Bob", title={T}, year=2020, journal={ICML}, doi={10.1/x}}""",
     r"""@misc{w, author={M{\"u}ller, Anna}, title={T}, year=2020, journal={ICML}, doi={10.1/x}}""",
     True, True, [], 'ESCALATE'),  # A has 2 authors, B has 1 -> dropped-coauthor caught
    ("HAL eprint != arXiv eprint",
     r"@article{k, title={T}, author={Smith, A}, year=2020, journal={ICML}, doi={10.1/x}, eprint={hal-12345}, archivePrefix={HAL}}",
     r"@misc{w, title={T}, author={A Smith}, year=2020, journal={ICML}, doi={10.1/x}, eprint={2401.00001}, archivePrefix={arXiv}}",
     True, True, [], 'ESCALATE'),
    ("string concatenation preserved",
     r"@article{k, title={Robust} # { and Reliable}, year=2020, author={Smith, A}, journal={ICML}, doi={10.1/x}}",
     r"@misc{w, title={Wrong Method}, year=2020, author={A Smith}, journal={ICML}, doi={10.1/x}}",
     True, True, [], 'ESCALATE'),  # A concat = 'Robust and Reliable', differs from 'Wrong Method'
    ("CJK given-name integrity: 伟 vs 伟明 differ",
     "@article{k, author={李, 伟}, title={T}, year=2020, journal={ICML}, doi={10.1/x}}",
     "@misc{w, author={伟明 李}, title={T}, year=2020, journal={ICML}, doi={10.1/x}}",
     True, True, [], 'ESCALATE'),
    ("CJK spaced-middle substitution: 伟 vs 伟 明",
     "@article{k, author={李, 伟}, title={T}, year=2020, journal={ICML}, doi={10.1/x}}",
     "@misc{w, author={伟 明 李}, title={T}, year=2020, journal={ICML}, doi={10.1/x}}",
     True, True, [], 'ESCALATE'),
    ("CJK given-name identity: 伟 vs 伟 match",
     "@article{k, author={李, 伟}, title={T}, year=2020, journal={ICML}, doi={10.1/x}}",
     "@misc{w, author={伟 李}, title={T}, year=2020, journal={ICML}, doi={10.1/x}}",
     True, True, [], 'MATCH'),
    ("month contradiction is not silently discarded",
     r"@article{k, title={T}, author={Smith, A}, year=2020, month={May}, journal={ICML}, doi={10.1/x}}",
     r"@misc{w, title={T}, author={A Smith}, year=2020, month={November}, journal={ICML}, doi={10.1/x}}",
     True, True, [], 'ESCALATE'),
    ("recompute: found false escalates",
     "@article{k, title={T}, author={Smith, A}, year={2020}, journal={ICML}, doi={10.1/x}}",
     "", True, False, [], 'ESCALATE'),
    # --- round-9 parser regressions ---
    ("recompute: duplicate conflicting author field escalates (not silently first-wins)",
     "@article{k, title={T}, author={Smith, Alice}, author={Jones, Bob}, year={2020}, journal={ICML}, doi={10.1/x}}",
     "@misc{w, title={T}, author={Alice Smith}, year={2020}, journal={ICML}, doi={10.1/x}}",
     True, True, [], 'ESCALATE'),
    ("recompute: corporate braced author is not two people",
     "@article{k, title={T}, author={{OpenAI and Friends}}, year={2020}, journal={ICML}, doi={10.1/x}}",
     "@misc{w, title={T}, author={OpenAI and Friends}, year={2020}, journal={ICML}, doi={10.1/x}}",
     True, True, [], 'ESCALATE'),
    ("recompute: identical duplicate field is not a conflict",
     "@article{k, title={T}, author={Smith, A}, author={Smith, A}, year={2020}, journal={ICML}, doi={10.1/x}}",
     "@misc{w, title={T}, author={A Smith}, year={2020}, journal={ICML}, doi={10.1/x}}",
     True, True, [], 'MATCH'),
]


# Routing-flag recompute path (C is advisory, A/B are authoritative):
# (name, c_entry, a_bibtex, b_entry, want_flags). Exercises assemble_flags directly so the
# "C not trusted / fail-closed on C schema" property is covered by --selftest, not just prose.
_DOI_REC = "@article{k, title={T}, author={Smith, A}, year={2020}, journal={ICML}, doi={10.1/x}}"
_MISC_URL_REC = "@misc{k, title={T}, author={Smith, A}, year={2020}, url={http://example.org/tr}}"
FLAG_SELFTEST = [
    ("flags clean: no routing flags", {}, _DOI_REC,
     {'found': True, 'sources_tried': ['arxiv', 'crossref']}, []),
    ("recompute degraded_search from B even if C omits it", {}, _DOI_REC,
     {'found': True, 'sources_tried': ['arxiv', 'semantic-scholar(429)']}, ['degraded_search']),
    ("recompute web_record_absent from B.found even if C omits it", {}, _DOI_REC,
     {'found': False, 'sources_tried': ['arxiv', 'crossref']}, ['web_record_absent']),
    ("recompute url_only for a url-bearing misc B could not index", {}, _MISC_URL_REC,
     {'found': False, 'sources_tried': ['arxiv', 'dblp']}, ['url_only_source_unqueried', 'web_record_absent']),
    ("C flags as a string fails closed (schema violation)", {'flags': 'url_only_source_unqueried'}, _DOI_REC,
     {'found': True, 'sources_tried': ['arxiv']}, ['c_schema_invalid']),
    ("C flags with a non-string item fails closed but keeps valid flags", {'flags': ['degraded_search', 123]}, _DOI_REC,
     {'found': True, 'sources_tried': ['arxiv']}, ['c_schema_invalid', 'degraded_search']),
    ("valid C advisory flag is honored", {'flags': ['url_only_source_unqueried']}, _DOI_REC,
     {'found': True, 'sources_tried': ['arxiv']}, ['url_only_source_unqueried']),
    # --- round-10: broadened degradation tokens C might omit (403/forbidden/captcha/quota/reset). ---
    ("recompute degraded from a 403/forbidden token C omitted", {}, _DOI_REC,
     {'found': True, 'sources_tried': ['arxiv', 'crossref(403 forbidden)']}, ['degraded_search']),
    ("recompute degraded from captcha/quota/reset tokens C omitted", {}, _DOI_REC,
     {'found': True, 'sources_tried': ['s2(quota exceeded)', 'web(captcha)', 'dblp(connection reset)']}, ['degraded_search']),
]


def _amanifest(key, title):
    """A-index entry fixture (key + bibtex) for the manifest selftest."""
    return {'key': key, 'bibtex': '@article{%s, title={%s}, author={Smith, A}, year={2020}}' % (key, title)}


# Coverage-manifest path: (name, want_manifest, a_index, expect_clean). Verifies the gate
# catches a drop-and-substitute the ordinal-set check cannot (blocker #4).
MANIFEST_SELFTEST = [
    ("manifest clean mapping",
     {'01': ('foo', manifest_title_hash('Deep Nets')), '02': ('bar', manifest_title_hash('Wide Nets'))},
     {'01': _amanifest('foo', 'Deep Nets'), '02': _amanifest('bar', 'Wide Nets')}, True),
    ("manifest catches a substituted cite key (same ordinal set)",
     {'01': ('foo', manifest_title_hash('Deep Nets')), '02': ('bar', manifest_title_hash('Wide Nets'))},
     {'01': _amanifest('foo', 'Deep Nets'), '02': _amanifest('baz', 'Wide Nets')}, False),
    ("manifest catches a changed title under the same key",
     {'01': ('foo', manifest_title_hash('Deep Nets'))},
     {'01': _amanifest('foo', 'Deep Networks')}, False),
    ("manifest catches a dropped ordinal",
     {'01': ('foo', manifest_title_hash('Deep Nets')), '02': ('bar', manifest_title_hash('Wide Nets'))},
     {'01': _amanifest('foo', 'Deep Nets')}, False),
    ("manifest title hash tolerates whitespace/case",
     {'01': ('foo', manifest_title_hash('Deep   NETS'))},
     {'01': _amanifest('foo', 'Deep Nets')}, True),
]


def selftest():
    bad = 0
    for name, entry, want in SELFTEST:
        got, reason, _ = classify(entry)
        ok = got == want
        bad += 0 if ok else 1
        print('%s %-38s -> %-9s (%s)' % ('PASS' if ok else 'FAIL', name, got, reason))
    for name, a_rec, b_rec, blind, found, flags, want in AB_SELFTEST:
        entry = build_entry('01', 'k', a_rec, b_rec, blind, found, flags)
        got, reason, _ = classify(entry)
        ok = got == want
        bad += 0 if ok else 1
        print('%s %-38s -> %-9s (%s)' % ('PASS' if ok else 'FAIL', name, got, reason))
    for name, c_e, a_rec, b_e, want in FLAG_SELFTEST:
        got = assemble_flags(c_e, a_rec, b_e)
        ok = got == sorted(want)
        bad += 0 if ok else 1
        print('%s %-38s -> %-9s (%s)' % ('PASS' if ok else 'FAIL', name, 'FLAGS', ','.join(got) or '(none)'))
    for name, want, ai, expect_clean in MANIFEST_SELFTEST:
        errs = manifest_mismatches(want, ai)
        ok = (errs == []) == expect_clean
        bad += 0 if ok else 1
        print('%s %-38s -> %-9s (%s)' % ('PASS' if ok else 'FAIL', name, 'MANIFEST',
                                         'clean' if not errs else '; '.join(errs)))
    total = len(SELFTEST) + len(AB_SELFTEST) + len(FLAG_SELFTEST) + len(MANIFEST_SELFTEST)
    print('\n%d/%d passed' % (total - bad, total))
    return 0 if bad == 0 else 2


def _load(path, label):
    try:
        with open(path) as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        print('ERROR: cannot read %s (%s): %s' % (path, label, exc), file=sys.stderr)
        return None
    ents = data.get('entries') if isinstance(data, dict) else None
    if not isinstance(ents, list):
        print('ERROR: %s (%s) has no "entries" list' % (path, label), file=sys.stderr)
        return None
    return data


def main():
    ap = argparse.ArgumentParser(description='Deterministic verifier gate for /citation-crosscheck.')
    ap.add_argument('--a', dest='a', help="path to cx_A_ourbib.json (A: local .bib records)")
    ap.add_argument('--b', dest='b', help="path to cx_B_web.json (B: web records, blind)")
    ap.add_argument('--c', dest='c', help="path to cx_C_fielddiff.json (C: routing flags only)")
    ap.add_argument('--json', dest='out', help='write machine-readable verdicts here')
    ap.add_argument('--expect', type=int, default=None,
                    help="CITED_KEY_COUNT from Step 1; errors if the entry count differs")
    ap.add_argument('--expect-keys', default=None,
                    help="file of whitespace-separated dedup_keys from Step 1; errors if the "
                         "set differs (catches a substitution that --expect's count cannot)")
    ap.add_argument('--expect-manifest', default=None,
                    help="Step-1 coverage manifest (dedup_key<TAB>cite_key<TAB>title_hash). The "
                         "gate verifies the ordinal->cite_key/title MAPPING against A, catching a "
                         "drop-and-substitute that --expect-keys' set check cannot. PREFERRED "
                         "coverage arg; build it with --build-manifest.")
    ap.add_argument('--build-manifest', action='store_true',
                    help='build the Step-1 coverage manifest from --bib + --keymap into --out-manifest')
    ap.add_argument('--bib', default=None, help='path to the .bib (with --build-manifest)')
    ap.add_argument('--keymap', default=None,
                    help='TSV of dedup_key<TAB>cite_key in resolved order (with --build-manifest)')
    ap.add_argument('--out-manifest', default=None, help='manifest output path (with --build-manifest)')
    ap.add_argument('--selftest', action='store_true', help='run built-in cases and exit')
    args = ap.parse_args()

    if args.selftest:
        return selftest()
    if args.build_manifest:
        if not (args.bib and args.keymap and args.out_manifest):
            ap.error('--build-manifest requires --bib, --keymap and --out-manifest')
        return build_manifest(args.bib, args.keymap, args.out_manifest)
    if not (args.a and args.b and args.c):
        ap.error('all of --a, --b, --c are required (or use --selftest). The gate recomputes '
                 'from A and B raw records and uses C only for flags; it will not trust C alone.')
    if not (args.expect_manifest or args.expect_keys):
        print('ERROR: coverage is MANDATORY — pass --expect-manifest (preferred, checks the '
              'ordinal->key/title mapping) or --expect-keys. The gate must not run coverage-blind: '
              'a dropped/substituted citation would otherwise read as "clean".', file=sys.stderr)
        return 1

    A, B, C = _load(args.a, 'A'), _load(args.b, 'B'), _load(args.c, 'C')
    if A is None or B is None or C is None:
        return 1

    # Index each shard by dedup_key, catching duplicates PER shard (a duplicate is a broken
    # join and must not silently overwrite).
    def index(data, label):
        idx, dupes = {}, set()
        for e in data['entries']:
            if not isinstance(e, dict):
                print('ERROR: %s has a non-object entry' % label, file=sys.stderr)
                return None, None
            k = str(e.get('dedup_key') or '').strip()
            if not k:
                print('ERROR: %s has an entry with empty/whitespace/null dedup_key' % label, file=sys.stderr)
                return None, None
            if k in idx:
                dupes.add(k)
            idx[k] = e
        return idx, dupes

    ai, ad = index(A, 'A'); bi, bd = index(B, 'B'); ci, cd = index(C, 'C')
    if ai is None or bi is None or ci is None:
        return 1
    alldupes = ad | bd | cd
    if alldupes:
        print('ERROR: duplicate dedup_key(s) within a shard: %s — the Step-2 join is broken.'
              % ','.join(_safe(x) for x in sorted(alldupes)), file=sys.stderr)
        return 1

    # The THREE shards must cover the SAME dedup_key set — a key present in one and missing
    # in another means the join dropped or invented a citation.
    if not (set(ai) == set(bi) == set(ci)):
        miss_b = sorted(set(ai) - set(bi)); miss_a = sorted(set(bi) - set(ai))
        miss_c = sorted((set(ai) | set(bi)) - set(ci)); extra_c = sorted(set(ci) - (set(ai) | set(bi)))
        print('ERROR: A/B/C dedup_key sets disagree — the Step-2 join is broken.', file=sys.stderr)
        for lbl, v in (('in A not B', miss_b), ('in B not A', miss_a),
                       ('missing from C', miss_c), ('only in C', extra_c)):
            if v:
                print('  %s: %s' % (lbl, ','.join(_safe(x) for x in v)), file=sys.stderr)
        return 1

    keys = ai  # same set as bi/ci
    if not keys:
        print('ERROR: zero entries — a shard produced nothing. Re-run; do NOT treat this as '
              '"no problems found".', file=sys.stderr)
        return 1
    if args.expect is not None and len(keys) != args.expect:
        print('ERROR: coverage mismatch — %d entries but --expect %d cited keys. A citation '
              'was dropped between Step 1 and the shards.' % (len(keys), args.expect), file=sys.stderr)
        return 1
    if args.expect_keys:
        try:
            want = {k.strip() for k in open(args.expect_keys).read().split() if k.strip()}
        except OSError as exc:
            print('ERROR: cannot read --expect-keys %s: %s' % (args.expect_keys, exc), file=sys.stderr)
            return 1
        got = set(keys)
        if got != want:
            missing, extra = sorted(want - got), sorted(got - want)
            print('ERROR: dedup_key set mismatch vs Step 1.', file=sys.stderr)
            if missing:
                print('  missing (dropped): ' + ','.join(_safe(x) for x in missing), file=sys.stderr)
            if extra:
                print('  unexpected (invented downstream): ' + ','.join(_safe(x) for x in extra), file=sys.stderr)
            return 1
    if args.expect_manifest:
        want_map = load_manifest(args.expect_manifest)
        if want_map is None:
            return 1
        errs = manifest_mismatches(want_map, ai)
        if errs:
            print('ERROR: coverage manifest mismatch vs Step 1 — a citation was dropped and/or '
                  'substituted downstream (the ordinal set alone would not catch this):', file=sys.stderr)
            for e in errs:
                print('  ' + e, file=sys.stderr)
            return 1

    # B's blindness attestation is authoritative and read PER SHARD from B itself (a single
    # bool for the whole B run), never from C. If B did not attest blindness, nothing
    # certifies.
    b_blind = B.get('blind') is True

    results, counts = [], {'MATCH': 0, 'MINOR': 0, 'ESCALATE': 0}
    downgraded = 0
    for k in sorted(keys):
        a_e, b_e, c_e = ai[k], bi[k], ci[k]
        # A supplies the local .bib key + record; B the web record + found; C ONLY flags.
        cite_key = a_e.get('key') or c_e.get('key')
        a_rec = a_e.get('bibtex')
        b_rec = b_e.get('bibtex')
        found = b_e.get('found') is True
        # C's flags are ADVISORY only: recompute routing from A/B raw artifacts and fail
        # closed on a C schema violation, so a faulty/omitting/adversarial C cannot route.
        flags = assemble_flags(c_e, a_rec, b_e)
        entry = build_entry(k, cite_key, a_rec, b_rec, b_blind, found, flags)
        verdict, reason, fields = classify(entry)
        if verdict == 'ESCALATE' and 'not blind-attested' in reason:
            downgraded += 1
        counts[verdict] += 1
        results.append({'dedup_key': k, 'key': cite_key, 'verdict': verdict,
                        'reason': reason, 'fields': fields, 'blind': b_blind})
        print('%-10s %-28s %s' % (verdict, _safe(cite_key)[:28], _safe(reason)))

    print('\nMATCH=%(MATCH)d MINOR=%(MINOR)d ESCALATE=%(ESCALATE)d' % counts)
    if not b_blind:
        print('B did not attest blindness (blind != true) — NO entry is certified; this run '
              'FLAGS but does not CERTIFY.')
    elif downgraded:
        print('%d entr%s downgraded to ESCALATE for lack of a blindness attestation.'
              % (downgraded, 'y' if downgraded == 1 else 'ies'))
    print('ESCALATE entries REQUIRE the main agent\'s own primary-source fetch (Step 4).')
    print('This gate recomputes the diff from A and B directly (C supplies only flags) and '
          'never emits MISMATCH; only a main-agent fetch can produce one.')

    if args.out:
        with open(args.out, 'w') as fh:
            json.dump({'gate': 'cx_verify.py', 'deterministic': True, 'recomputed_from': 'A+B',
                       'b_blind': b_blind, 'counts': counts, 'entries': results}, fh, indent=2)
        print('wrote %s' % args.out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
