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

Usage:  research-kit review [repo_dir ...]
Exit 1 if any check fails.
"""
import datetime
import os
import re
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
    return bad


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
       handling restrictions survived the mirror.

  The second reader
    9. Run the independent pass through the `codex` CLI, from the repo, with
       the document in the working tree or the branch diff. The framing is
       shared, not retyped -- `adversarial-gate render --lens research-brief`
       prints it, from local-adversarial-gate in the `system` repo:

         codex exec -s read-only "This is a markdown research brief, not code.
           Review the uncommitted working-tree changes as an adversarial reader.
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
