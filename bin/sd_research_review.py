#!/usr/bin/env python3
"""The mechanical half of the pre-publication adversarial review.

This checks the things a script can decide: that every rendered document carries
a provenance block, closes with a Status section separating what was verified
from what was not, and is rendered from a source no newer than its build. It
cannot judge whether a claim is true — that is the other half, and it is
printed as a checklist rather than pretending the green ticks cover it.

Deliberately not checked: citations of `90-scratch/`. The first cut flagged
them, and every hit was correct work — layout tables describing the folder, and
a registry entry naming a superseded pass *as* superseded, which the
conventions ask for. "Cites as evidence" and "names as superseded" are not
mechanically separable, and a check that fires on correct behaviour teaches
people to ignore the output.

Checked here but owned elsewhere: work items under `docs/work/`. They follow
`sd-plan`, not the research conventions, and `sd-docs-lint` is their linter —
but a repository following both standards used to get "Mechanical checks pass"
from this tool while the other one was failing, so the lint is run when the
directory exists.

Usage:  sd-research-kit review        # from inside the research repo

`review` takes no argument: it checks the repository you are standing in
(R10-D6, the same move `render` made). Exit 1 if any check fails.
"""
import datetime
import difflib
import os
import re
import subprocess
import sys
from typing import Any


def load_docs(repo):
    """The DOCS list out of research.conf.py, same way render.py reads it."""
    conf = os.path.join(repo, "research.conf.py")
    if not os.path.exists(conf):
        return None
    ns: dict[str, Any] = {}
    # nosec B102 - research.conf.py is a file in the repo being rendered, at the
    # same trust level as this script, and the format needs execution: at least
    # one live config builds its DOCS list with a loop.
    exec(compile(open(conf).read(), conf, "exec"), ns)  # nosec B102
    return ns.get("DOCS") or []


def provenance(text):
    """H1, then a non-empty paragraph, then `---`.

    The renderer strips everything above the rule, so this block exists only for
    readers of the markdown — which is exactly why it rots unnoticed.
    """
    lines = text.split("\n")
    if not lines or not lines[0].startswith("# "):
        return False, "no H1 on the first line"
    try:
        rule = next(i for i, line in enumerate(lines) if line.strip() == "---")
    except StopIteration:
        return False, "no `---` after the provenance block"
    body = [line for line in lines[1:rule] if line.strip()]
    if not body:
        return False, "provenance block is empty"
    return True, " ".join(body)[:80]


def status_section(text):
    """A closing section that says what is *not* settled.

    Heading names vary honestly — `## Status`, `## 9. Status`,
    `## Status and confidence`, `## 8. Evidence status` all do the same job — so
    the heading match is on the word anywhere in the title, not a prefix. It is
    the word `status` and nothing else: matching `evidence` or `confidence` too
    caught prose headings like "Evidence the thesis is landing" and reported
    them as defective Status sections, which is a worse error than missing one.

    The gate inside is one-sided on purpose. A document can express *verified* in
    a dozen ways ("read directly", "probed 2026-08-26", "first-party"), so
    requiring the word would fail good sections; but stating a limit takes a
    negative term, and the failure this check exists to catch is the section that
    only lists what went right. Whether the split is honest is the reader's job —
    this only asks that the other side is on the page at all.
    """
    HEAD = re.compile(r"^(#{2,3})\s+(?:\d+\.\s*)?(.+)$", re.M)
    NAME = re.compile(r"\bstatus\b", re.I)
    LIMIT = re.compile(r"\bnot verified\b|\bunverified\b|\buntested\b|"
                       r"\bunquantified\b|\bunproven\b|\bnot measured\b|"
                       r"\bnot replicated\b|\bmodelled\b|\bmodeled\b|"
                       r"\bassumed\b|\bnot confirmed\b|\bopen question", re.I)
    heads = [(m.start(), m.end(), len(m.group(1)), m.group(2).strip()) for m in HEAD.finditer(text)]
    found = None
    for i, (_, hend, level, title) in enumerate(heads):
        if not NAME.search(title):
            continue
        found = title
        # Bound the section, so a later section's caveats cannot vouch for this one.
        stop = next((s0 for s0, _, lv, _ in heads[i + 1:] if lv <= level), len(text))
        if LIMIT.search(text[hend:stop]):
            return True, title
    if found:
        return False, f"`{found}` does not say what is *not* settled"
    return False, "no Status section"


def work_items(repo):
    """Work items belong to `sd-docs-lint`; saying nothing about them is the bug.

    A repository can follow both standards at once: `sd-research-repo` governs
    the documents named in `research.conf.py`, `sd-plan` governs the items under
    `docs/work/`. Nothing connected the two linters, so `review` could print
    "Mechanical checks pass" in a repository whose work items were failing
    `sd-docs-lint` — a sentence true about this tool's own scope and false about
    the repository the reader is standing in. That is the shape of failure this
    file exists to prevent, so it should not ship one.

    The lint is run rather than merely advertised, because a gate nobody invokes
    is not a gate. A repository with no `docs/work/` never pays for it.
    """
    work = os.path.join(repo, "docs", "work")
    if not os.path.isdir(work):
        return 0
    lint = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sd-docs-lint")
    if not os.path.exists(lint):
        # A gate that cannot run is not a gate that passed. Reporting this as a
        # warning and returning 0 would reproduce the exact defect this function
        # exists to fix, one level down: the repository would print a clean
        # review because the linter was missing, which is the least trustworthy
        # moment to claim cleanliness. Partial installs are the likely cause, so
        # the message names the remedy rather than only the symptom.
        print("  FAIL docs/work/ exists, but sd-docs-lint is not beside this "
              f"script ({os.path.dirname(lint)}) — install it alongside "
              "sd-research-kit, or the work items go unchecked")
        return 1
    done = subprocess.run(
        [sys.executable, lint], cwd=repo, capture_output=True, text=True
    )
    if done.returncode == 0:
        print("  ok   docs/work/: sd-docs-lint clean")
        return 0
    # Exit 2 is "not a git repository", which is the caller's situation rather
    # than a defect in the documents — report it, do not count it as a failure.
    if done.returncode != 1:
        detail = (done.stderr or done.stdout).strip().splitlines()
        print(f"  WARN docs/work/: sd-docs-lint exited {done.returncode}"
              f"{': ' + detail[-1] if detail else ''}")
        return 0
    failures = [
        line[len("FAIL "):] for line in done.stderr.splitlines()
        if line.startswith("FAIL ")
    ]
    # sd-docs-lint reports absolute paths; this output is read next to
    # repo-relative document names, so make the two agree. The lint resolves its
    # root through git, which returns the real path, while `repo` came from the
    # caller's cwd -- on macOS those differ for anything under /tmp (/var vs
    # /private/var) and they differ for any symlinked checkout, so a plain prefix
    # strip silently does nothing. Try the resolved prefix as well; failing to
    # shorten a path is cosmetic, so an unrecognised one is printed whole.
    prefixes = {repo + os.sep, os.path.realpath(repo) + os.sep}
    for failure in failures:
        for prefix in prefixes:
            if failure.startswith(prefix):
                failure = failure[len(prefix):]
                break
        print("  FAIL " + failure)
    return len(failures) or 1


TEMPLATE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "skills", "sd-research-repo", "templates", "CLAUDE.md",
)

# The template's own substitution marker. It survives inside fenced examples, so
# a repo that filled one in and a repo that kept the placeholder both match.
SLOT = re.compile(r"<[^<>\n]+>")

# What a repo legitimately writes where the template describes a value: the
# Notion folder URL, the absolute path of a document, a `file:///` link. These
# are the only substitutions the template invites that are not `<...>` slots,
# and they are recognisable as values rather than as prose.
LOCAL_VALUE = re.compile(r"https?://\S+|file:///\S+|/(?:Users|home|opt|srv|var|mnt)/\S+")

FENCE_LINE = re.compile(r"^\s*```")

#: The section where a repo declares the template blocks it deliberately states
#: differently. Without it the detector has no word for a *substitution*: it can
#: tell an addition (local content, left alone) from a deletion (drift), but a
#: repo that replaces a template block with a better one for its situation looks
#: exactly like a repo that fell behind. Two of the five research repos do
#: exactly that -- they publish to a team Notion space, so the template's
#: personal `file:///` Source header would put an absolute path on a page read by
#: people who have no such checkout -- and they had no way to say so. A detector
#: that reports a repo forever for doing the right thing is a detector that gets
#: switched off, which is the failure this whole check exists to prevent.
OVERRIDES_HEADING = "Local overrides of the shared template"

#: One entry in that section: the template section it replaces, then why.
#: The section is named exactly as a finding names it, so a reader can move a
#: `FAIL ... `## X`` line into the list by copying the backticked part across.
OVERRIDE_ENTRY = re.compile(r"^-\s+`##\s+(?P<head>[^`\n]+)`\s*(?P<reason>.*)$", re.S)


def sections(text):
    """(heading, body) pairs, split on `##` headings outside code fences.

    The fence tracking is not decoration: both files carry fenced markdown
    examples whose content begins `## 1. First section`, and splitting on those
    invents a section that exists in neither document.
    """
    out: list[tuple[str, str]] = []
    buf: list[str] = []
    head, fence = "", False
    for line in text.split("\n"):
        if FENCE_LINE.match(line):
            fence = not fence
        elif not fence and line.startswith("## "):
            out.append((head, "\n".join(buf)))
            head, buf = line[3:].strip(), []
            continue
        buf.append(line)
    out.append((head, "\n".join(buf)))
    return out


def blocks(body):
    """Blank-line-separated blocks, with fenced code kept whole."""
    out: list[str] = []
    buf: list[str] = []
    fence = False
    for line in body.split("\n"):
        if FENCE_LINE.match(line):
            fence = not fence
            buf.append(line)
            continue
        if not line.strip() and not fence:
            if buf:
                out.append("\n".join(buf).strip())
            buf = []
            continue
        buf.append(line)
    if buf:
        out.append("\n".join(buf).strip())
    return [b for b in out if b.strip()]


def flat(block):
    return re.sub(r"\s+", " ", block).strip()


def fills_a_slot(template_block, repo_block):
    """True if the repo block is the template block with its `<...>` slots filled."""
    if not SLOT.search(template_block):
        return False
    pattern = ".+?".join(re.escape(part) for part in SLOT.split(template_block))
    return re.fullmatch(pattern, repo_block, re.S) is not None


def only_a_local_value(template_block, repo_block):
    """True if the two differ only where the repo wrote a local value.

    This is the line between template drift and intended local content inside a
    section both files carry. Every span where the repo departs from the
    template is looked at: if what the repo put there is a URL or an absolute
    path — a Notion folder, a `file:///` document link — the departure is the
    repo filling in its own identity, which is what the template asks for. If
    what the repo put there is prose, the repo is carrying a wording the
    template no longer has, which is drift.
    """
    left, right = template_block.split(), repo_block.split()
    matcher = difflib.SequenceMatcher(None, left, right, autojunk=False)
    for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if not LOCAL_VALUE.search(" ".join(right[j1:j2])):
            return False
    return True


# Below this, the nearest repo block is a different block rather than an edited
# one, so the template block is reported as gone instead of as reworded. It
# changes the wording of a finding, never whether one is reported.
REWORDED_FLOOR = 0.40


def drift(template_text, repo_text):
    """Template-owned blocks this repo no longer carries.

    One-directional on purpose. The template is a floor, not a ceiling: what it
    states, the repo should state. What the repo adds — whole local sections,
    local paragraphs inside a shared section — is the repo doing its job, and is
    counted but never reported as a defect. A detector that called every
    difference drift would fire on all five research repos forever and be
    switched off within a week.
    """
    findings: list[tuple[str, str, str]] = []
    local = 0
    repo_sections: dict[str, str] = {}
    for head, body in sections(repo_text):
        repo_sections.setdefault(head, body)
    seen = set()

    for head, body in sections(template_text):
        seen.add(head)
        name = f"`## {head}`" if head else "the opening"
        if head not in repo_sections:
            findings.append((name, "section is missing", ""))
            continue
        candidates = [flat(b) for b in blocks(repo_sections[head])]
        matched = set()
        for block in blocks(body):
            want = flat(block)
            best, ratio = "", 0.0
            for candidate in candidates:
                score = difflib.SequenceMatcher(None, want, candidate).ratio()
                if score > ratio:
                    best, ratio = candidate, score
            if best and (
                best == want
                or fills_a_slot(want, best)
                or only_a_local_value(want, best)
            ):
                matched.add(best)
                continue
            how = "reworded" if ratio >= REWORDED_FLOOR else "gone"
            findings.append((name, how, want))
        local += len([c for c in candidates if c not in matched])

    local += len([h for h, _ in sections(repo_text) if h not in seen])
    return findings, local


def declared_overrides(repo_text):
    """Template sections this repo says it states differently, and why.

    Returns `{section heading: reason}`, with an empty reason for an entry that
    gave none -- reported as a failure rather than honoured, because an override
    with no reason is indistinguishable from drift someone wanted to stop
    hearing about, and that is the one use of this section that would break it.
    """

    body = next((text for head, text in sections(repo_text)
                 if head == OVERRIDES_HEADING), "")
    found: dict[str, str] = {}
    for block in blocks(body):
        # Split the bullet list back into bullets, keeping each entry's
        # continuation lines with it: a reason wraps, and the wrapped half is
        # the half that says why.
        for entry in re.split(r"\n(?=\s*-\s)", block):
            match = OVERRIDE_ENTRY.match(entry.strip())
            if match:
                reason = flat(match.group("reason")).strip(" —-:")
                found[match.group("head").strip()] = reason
    return found


def override_faults(declared, template_heads):
    """The override entries that cannot be honoured, as printable failures.

    A stale entry is worth catching for the same reason the drift check is: it
    is a claim about the template that nothing re-reads. An override naming a
    section the template no longer has is silently covering nothing, and the day
    the template grows a section by that name it would start covering it.
    """

    faults = []
    for head in sorted(declared):
        if head not in template_heads:
            faults.append(
                f"  FAIL CLAUDE.md `## {head}`: declared a local override of a "
                "section the template does not have — fix the name, or drop the "
                "entry now that the template has moved on")
        elif not declared[head]:
            faults.append(
                f"  FAIL CLAUDE.md `## {head}`: declared a local override with "
                "no reason — say why this repo states it differently, or delete "
                "the entry and re-sync the section")
    return faults


def apply_overrides(findings, repo_text, template_text):
    """Drop the findings this repo has declared, print those and any faults.

    Returns the findings that survive and how many declared entries could not be
    honoured. Split out of `template_drift` rather than written inline: the
    decision about which findings count is one thing, and printing the report is
    another, and holding both in one function put it over the complexity
    ceiling. The ceiling was right — this is easier to read apart.
    """

    declared = declared_overrides(repo_text)
    template_heads = {head for head, _ in sections(template_text) if head}
    faults = override_faults(declared, template_heads)
    honoured = {head for head in declared if head in template_heads and declared[head]}

    # The cost of an override is that the template's blocks in that section stop
    # being compared, so a later change to the template lands there unseen. That
    # cost is printed on every run, with the count, rather than being paid
    # quietly: an override is a standing decision and should keep asking to be
    # re-read, not disappear into a clean report.
    for head in sorted(honoured):
        skipped = len([f for f in findings if f[0] == f"`## {head}`"])
        print(f"  ok   CLAUDE.md `## {head}`: overridden locally "
              f"({skipped} template block(s) not compared) — {declared[head]}")
    for line in faults:
        print(line)

    silenced = {f"`## {head}`" for head in honoured}
    return [f for f in findings if f[0] not in silenced], len(faults)


def template_drift(repo):
    """Report where this repo's `CLAUDE.md` has fallen behind the pack's template.

    Nothing looked before. Three findings in the 2026-09-10 fleet review were
    all one divergence between this template and the copies in the research
    repos, and it had been there six weeks because the only thing that would
    have caught it was a person reading two files side by side.
    """
    local_copy = os.path.join(repo, "CLAUDE.md")
    if not os.path.exists(TEMPLATE):
        # Same reasoning as `work_items`: a gate that cannot run has not passed.
        # `sd-research-kit conventions` already assumes `skills/` sits beside
        # `bin/`, so a missing template means a partial install, and the message
        # names that rather than only the symptom.
        print(f"  FAIL CLAUDE.md: the template is not at {TEMPLATE} — install "
              "the pack's skills/ alongside its bin/, or drift goes unchecked")
        return 1
    if not os.path.exists(local_copy):
        print("  FAIL CLAUDE.md: missing — every research repo carries one, "
              f"descended from {os.path.relpath(TEMPLATE, os.path.dirname(os.path.dirname(TEMPLATE)))}")
        return 1

    with open(TEMPLATE, encoding="utf-8", errors="replace") as handle:
        template_text = handle.read()
    with open(local_copy, encoding="utf-8", errors="replace") as handle:
        repo_text = handle.read()
    findings, local = drift(template_text, repo_text)
    findings, faults = apply_overrides(findings, repo_text, template_text)

    if not findings and not faults:
        print(f"  ok   CLAUDE.md: in sync with the template"
              f"{f'; {local} local block(s)/section(s) left alone' if local else ''}")
        return 0
    for where, how, excerpt in findings:
        detail = f": {excerpt[:72]}…" if excerpt else ""
        print(f"  FAIL CLAUDE.md {where}: {how}{detail}")
    if findings:
        print(f"  ---- {len(findings)} template block(s) drifted; {local} local "
              "block(s)/section(s) were left alone. Re-sync from "
              "skills/sd-research-repo/templates/CLAUDE.md keeping the local "
              "ones, or — if this repo states a section differently on purpose "
              f"— say so under `## {OVERRIDES_HEADING}`.")
    return len(findings) + faults


#: The marker `references/conventions.md` puts on the one document a reader
#: enters a research project through, under **Main document — START HERE**.
#: The rule is stated there and nowhere else; this is the marker itself, not a
#: second statement of the rule.
MAIN_TITLE = "START HERE — "


def h1(text):
    """The document's `# ` heading, or None. A fenced `# ` is a comment."""
    fenced = False
    for line in text.splitlines():
        if FENCE_LINE.match(line):
            fenced = not fenced
        elif not fenced and line.startswith("# "):
            return line[2:].strip()
    return None


def main_document(repo, docs):
    """Exactly one configured document carries the `START HERE — ` title.

    This checks the half of the convention that is inside the checkout: the
    Markdown H1, and the `title`/`h1` the config renders it under. The README's
    entry link and the Notion page title are the other half, they are in no
    file this kit reads, and they stay in the checklist -- which is why the ok
    line names what it covered instead of reporting a bare pass. A check that
    printed `ok` after reading two of the four surfaces would manufacture the
    confidence it exists to earn.

    Scope is the configured documents, not the tree. `90-scratch/` holds
    superseded drafts that are never cited and never mirrored, so one still
    carrying an old marker is not a duplicate -- and it is not configured.
    """
    if not docs:
        # A repo that configures no documents has no main document to name, and
        # `init-claude-md` lays the standard into exactly that repo. Demanding
        # one before there is anything to title would fail every repo on the
        # day it is set up, which is the day the standard is meant to arrive.
        return 0
    carriers, bad = [], 0
    for cfg in docs:
        src = os.path.join(repo, cfg["src"])
        if not os.path.exists(src):
            continue
        with open(src, encoding="utf-8", errors="replace") as handle:
            title = h1(handle.read())
        if title is None or not title.startswith(MAIN_TITLE):
            continue
        carriers.append(cfg["src"])
        for key in ("title", "h1"):
            rendered = str(cfg.get(key, title)).strip()
            if rendered != title:
                print(f"  FAIL {cfg['src']}: H1 is {title!r} but `{key}` renders "
                      f"it as {rendered!r} -- the standard is one title across "
                      "the H1, `title` and `h1`")
                bad += 1
    if not carriers:
        print("  FAIL main document: no configured document's H1 starts with "
              f"`{MAIN_TITLE}` -- every project has exactly one")
        return bad + 1
    if len(carriers) > 1:
        print(f"  FAIL main document: {len(carriers)} carry `{MAIN_TITLE}` "
              f"({', '.join(sorted(carriers))}) -- exactly one may")
        return bad + 1
    print(f"  ok   main document: {carriers[0]}, H1 and rendered title. Its "
          "README link and Notion title are the checklist's half")
    return bad


def check(repo):
    repo = os.path.abspath(repo)
    name = os.path.basename(repo)
    docs = load_docs(repo)
    if docs is None:
        print(f"{name}: no research.conf.py — not a research repo")
        return 0
    bad = 0
    print(f"\n== {name}")
    for cfg in docs:
        src = os.path.join(repo, cfg["src"])
        label = cfg["src"]
        if not os.path.exists(src):
            print(f"  FAIL {label}: source is missing")
            bad += 1
            continue
        text = open(src, encoding="utf-8", errors="replace").read()

        ok, detail = provenance(text)
        if not ok:
            print(f"  FAIL {label}: {detail}")
            bad += 1

        ok, detail = status_section(text)
        if not ok:
            print(f"  FAIL {label}: {detail}")
            bad += 1

        out = os.path.join(repo, "build", cfg.get("out", "") + ".html")
        if not os.path.exists(out):
            print(f"  WARN {label}: not rendered yet")
        elif os.path.getmtime(src) > os.path.getmtime(out):
            when = datetime.date.fromtimestamp(os.path.getmtime(src)).isoformat()
            print(f"  FAIL {label}: edited {when}, newer than its build — re-render")
            bad += 1

    if not bad:
        print(f"  ok   {len(docs)} document(s): provenance, Status, build freshness")
    return bad + main_document(repo, docs) + template_drift(repo) + work_items(repo)


CHECKLIST = """
The half no script can do — work it before publishing, per document:

  The information
    1. List the load-bearing claims. If the conclusion survives without a claim,
       it is not load-bearing; if it does not, that claim carries the document.
    2. For each, open the cited source again and read it. Default to refuted:
       a claim stands only if the source actually says it, not merely that it
       is consistent with it.
    3. Numbers: check the unit, the date and the denominator, not the digits.
       A rate without its base has not been checked.
    4. A claim no source supports is cut, or moved to Status as explicitly
       unverified. It never stays in the body, where a reader will assume it
       was checked.
    5. Say what you could not check and why. A stated gap is useful; a silent
       one is a defect.

  The product
    6. Read the rendered page as someone who has not seen the source material.
       Does the conclusion follow from what is on the page, or only from what
       you happen to know?
    7. Look for the load-bearing thing left implicit — the assumption doing the
       work that the document never states.
    8. Check the Notion mirror matches the source after the update, and that
       handling restrictions survived the mirror. Include the main document's
       other two surfaces, which no check above reaches: the README's entry
       link and table, and the Notion page title and parent. `review` read its
       H1 and rendered title and said so; these two nothing read.

  The second reader
    9. Run the independent pass through the `codex` CLI, from the repo, with
       the document still UNCOMMITTED -- the prompt below points it at
       working-tree changes, so committed work shows it an empty diff without
       saying so. Already committed on a branch: name the comparison in the
       prompt instead ("review `git diff main...HEAD`"). The framing is
       shared, not retyped -- `adversarial-gate render --lens research-brief`
       prints it, from local-adversarial-gate in the `system` repo:

         codex exec -s read-only "This is a markdown research brief, not code.
           Review the uncommitted working-tree changes (git status, git diff,
           plus untracked new files) as an adversarial reader.
           Attack the argument, not the syntax: unsupported load-bearing claims,
           numbers missing a unit/date/denominator, the assumption the document
           never states. Cite file and line. Do not modify any files."

       `-s read-only` is not optional -- it is what stops an adversarial reader
       editing the work it reviews. Run it in the background for anything past
       a page; it buffers, so no output until it exits.

       Not the `/codex:*` slash commands. The `codex@openai-codex` plugin is
       not a dependency of this kit and may not be installed; the CLI is the
       supported path. `codex doctor` says whether it is available and logged
       in. It sees the repo, not the sources, so it does not discharge step 2.
       Unavailable is a Status line, not a silent skip.

  Then record the outcome in the Status section: what was verified and how,
  what was not, what was cut, and the Codex pass — what it raised, what
  changed, what was rejected and why. A review that found nothing says so, and
  says what it checked.
"""


def init_main() -> int:
    """Lay the pack's `CLAUDE.md` into a research repo that has none.

    This is the whole of "install the template", and the narrowness is the
    point. The template reached five repositories by a route nobody wrote down
    (sd:518), and the tempting fix -- a verb that re-syncs an existing
    `CLAUDE.md` -- is the one that must not be built: two of those five
    deliberately replace the template's personal `file:///` Source header
    because their Notion space is read by people with no such checkout, and a
    writer that merged the template back over them would undo that silently and
    put an absolute path on a team page. Laying the *first* copy has no such
    ambiguity, because there is nothing local to lose.

    So the operation this kit supports is: create once here, and from then on
    `review` reports where the copy and the template disagree while
    `## Local overrides of the shared template` records the disagreements that
    are on purpose. Refusing to overwrite is not a missing feature.
    """

    repo = os.getcwd()
    local_copy = os.path.join(repo, "CLAUDE.md")
    if not os.path.exists(TEMPLATE):
        print(f"sd-research-kit: the template is not at {TEMPLATE} — install "
              "the pack's skills/ alongside its bin/", file=sys.stderr)
        return 1
    if not os.path.exists(os.path.join(repo, "research.conf.py")):
        print("sd-research-kit: no research.conf.py here — init-claude-md "
              "writes into a research repo, and this is not one", file=sys.stderr)
        return 1
    if os.path.exists(local_copy):
        print("sd-research-kit: CLAUDE.md already exists here; this verb lays "
              "the first copy and never overwrites one.\n"
              "  `sd-research-kit review` reports where it has drifted from the "
              "template, and anything\n"
              "  this repo states differently on purpose belongs under "
              f"`## {OVERRIDES_HEADING}`.", file=sys.stderr)
        return 1

    with open(TEMPLATE, encoding="utf-8", errors="replace") as handle:
        text = handle.read()
    with open(local_copy, "w", encoding="utf-8") as handle:
        handle.write(text)
    print(f"wrote CLAUDE.md from {TEMPLATE}")
    print("  Fill in the `<...>` slots and the Notion folder URL, then run "
          "`sd-research-kit review`.")
    return 0


def main() -> int:
    # R10-D6: the repository is the one the caller is standing in. This took
    # `review [repo_dir ...]` before the kit moved into the pack.
    bad = check(os.getcwd())
    print(CHECKLIST)
    if bad:
        print(f"{bad} mechanical check(s) failed — fix before publishing.")
        return 1
    print("Mechanical checks pass. They are the floor, not the review.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
