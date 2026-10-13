"""The pull-request body `sd-ship` publishes, read against the lines it owns (sd:1870).

`sd-ship` writes `Work:` into the body it publishes, and `Item:` and
`Delivers:` into the squash message. A supplied `Item:`, `Work:` or
`Delivers:` line is stripped and named in the result, whatever it says
(sd:2999): `sd-ship` writes the links itself.

The fixpoint is the point: `normalize` of a body `sd-ship` published returns
the body it published before appending `Work:`, so the live pull-request body
fed back as `--body-file` prepares again without a refusal. Before this, the
body `sd-ship` itself wrote was refused as input (#1236, #1238).

Only a line at column zero is read, because that is the only form git or
rule 5 reads; an indented line is prose about a trailer, and the body keeps
it. A body with no item owns nothing, so every column-zero owned line is
stripped there, `Closes:` included.

`Closes: sd:N[, sd:M]` is the one owned line a body keeps: it names the items
the pull request co-delivers, and the merge closes each with a `Delivers:`
trailer beside the claimed item's (sd:1481, operator ruling 2026-10-03).
`Refs:` is not owned: it names related items, which stay open.

A column-zero owned line inside a fenced code block or an HTML comment is
an example, not a claim, so `closes_named` and `strip_closes` never read one.
`normalize` refuses it rather than keep it: the squash carries the body as
written, and `sd_lib.demoted_trailers` would refuse the line there, at merge.
Indented, it is prose like any other example.
"""

from __future__ import annotations

import dataclasses
import pathlib
import re
import tempfile

import sd_lib
from sd_ship_remote import Refusal, completed_process

#: A `Closes:` value: one or more `sd:<n>`, comma-separated.
_CLOSES_VALUE = re.compile(r"sd:[1-9][0-9]*(?:[ \t]*,[ \t]*sd:[1-9][0-9]*)*")

#: The canonical spelling of each owned key, by its case-folded name.
_CANONICAL = {key.rstrip(":").lower(): key for key in sd_lib.OWNED_TRAILERS}
_OWNED_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<key>" + "|".join(re.escape(key.rstrip(":")) for key in sd_lib.OWNED_TRAILERS)
    + r")[ \t]*:(?P<value>.*)$",
    re.IGNORECASE,
)


@dataclasses.dataclass(frozen=True)
class OwnedLine:
    """One owned trailer line: its 1-based number, text, canonical key and value."""

    number: int
    text: str
    key: str
    value: str
    indented: bool
    quoted: bool


#: A fence that opens or closes a fenced code block: up to three spaces, then
#: three or more backticks or tildes (CommonMark).
_FENCE_RE = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})(?P<info>.*)$")


def quoted_lines(body: str) -> set[int]:
    """The 1-based numbers of the lines of `body` a fenced code block or an HTML comment holds.

    A fence closes on a line of the same character, at least as long, and
    nothing else; an unclosed fence runs to the end. A comment holds a line
    when it is open where the line starts. Inside a fence a comment is text.
    """
    quoted: set[int] = set()
    fence = ""
    commented = False
    for number, line in enumerate(body.split("\n"), start=1):
        line = line.rstrip("\r")
        if fence:
            quoted.add(number)
            match = _FENCE_RE.match(line)
            if match and match["fence"][0] == fence[0] and len(match["fence"]) >= len(fence) and not match["info"].strip():
                fence = ""
            continue
        if commented:
            quoted.add(number)
        match = _FENCE_RE.match(line)
        if not commented and match and not (match["fence"][0] == "`" and "`" in match["info"]):
            quoted.add(number)
            fence = match["fence"]
            continue
        rest = line
        while True:
            if commented:
                end = rest.find("-->")
                if end < 0:
                    break
                commented, rest = False, rest[end + 3:]
            else:
                start = rest.find("<!--")
                if start < 0:
                    break
                commented, rest = True, rest[start + 4:]
    return quoted


def owned_lines(body: str) -> list[OwnedLine]:
    """Every line of `body` that starts with an owned key, indented or not, quoted or not."""
    found = []
    quoted = quoted_lines(body)
    for number, line in enumerate(body.split("\n"), start=1):
        match = _OWNED_RE.match(line.rstrip("\r"))
        if match is not None:
            found.append(OwnedLine(number, line.rstrip("\r"), _CANONICAL[match["key"].lower()],
                                   match["value"].strip(), bool(match["indent"]), number in quoted))
    return found


def problem(line: OwnedLine, item: int | None) -> str | None:
    """Why `line` cannot be stripped from an item's body, or None when it can."""
    if line.quoted:
        return ("a code block or comment holds it, so it reads as an example; indent it to keep it as one, "
                "or move it out of the block to make it a trailer")
    if line.key in (sd_lib.ITEM_TRAILER, sd_lib.WORK_TRAILER, sd_lib.DELIVERS_TRAILER) or item is None:
        return None  # sd:2999: sd-ship writes the links itself, so a stray one is dropped
    expected = f"sd:{item}"
    if _CLOSES_VALUE.fullmatch(line.value) and expected not in _ids(line.value):
        return None
    return (f"expected `{line.key} sd:<n>[, sd:<m>]` naming co-delivered items other than {expected}, "
            "which closes with --deliver")


def normalize(body: str, item: int | None) -> tuple[str, tuple[str, ...]]:
    """`body` without the owned lines that agree with `sd-ship`, and those lines.

    Refuses, naming every offending line, when any owned line disagrees. With
    no item and nothing to strip, `body` is returned unchanged. Otherwise the
    result carries no trailing whitespace, which is what makes
    `normalize(published)` equal the body before `Work:` was appended.
    """
    read = [line for line in owned_lines(body) if not line.indented]
    if item is None and not read:
        return body, ()
    problems = [(line, reason) for line in read
                if (reason := problem(line, item)) is not None]
    if problems:
        raise Refusal("the ship adapter owns association and delivery trailers: "
                      + "; ".join(f"line {line.number}: `{line.text}`; {reason}" for line, reason in problems),
                      code="body_trailer_refused", boundary="input", state="operator_decision",
                      next_action="Remove or correct the named lines; sd-ship writes them itself.")
    # A `Closes:` line stays: it is the body's own claim, and the merge reads it there.
    read = [line for line in read if line.key != sd_lib.CLOSES_TRAILER or item is None]
    stripped = {line.number for line in read}
    lines = body.split("\n")
    kept: list[str] = []
    for number, text in enumerate(lines, start=1):
        # A stripped line between two blank ones leaves one gap, not two.
        if number in stripped or (number - 1 in stripped and not text.strip()
                                  and kept and not kept[-1].strip()):
            continue
        kept.append(text)
    return "\n".join(kept).rstrip(), tuple(line.text for line in read)


def _ids(value: str) -> list[str]:
    return re.findall(r"sd:[0-9]+", value)


def closes_named(body: str, item: int | None) -> tuple[int, ...]:
    """The items the body's column-zero, unquoted `Closes:` lines name, in order, without repeats.

    No item, no closing: a no-item body refuses the line in `normalize`.
    """
    if item is None:
        return ()
    found: list[int] = []
    for line in owned_lines(body):
        if line.key == sd_lib.CLOSES_TRAILER and not line.indented and not line.quoted:
            for number in (int(name[3:]) for name in _ids(line.value)):
                if number not in found:
                    found.append(number)
    return tuple(found)


def strip_closes(body: str) -> str:
    """`body` without its column-zero `Closes:` lines, for the squash message.

    The squash states each as a `Delivers:` trailer; a `Closes:` line left in
    the prose is a trailer outside the block git reads, and the merge refuses
    such a message (`sd_lib.demoted_trailers`).
    """
    kept = {line.number for line in owned_lines(body)
            if line.key == sd_lib.CLOSES_TRAILER and not line.indented and not line.quoted}
    return "\n".join(text for number, text in enumerate(body.split("\n"), start=1) if number not in kept)


#: An `sd:<n>` a title names: context for a reader, never a close (sd:3704).
_TITLE_ID = re.compile(r"\bsd:([0-9]+)\b")


def title_ids(title: str) -> tuple[int, ...]:
    """The whole `sd:<n>` tokens `title` names, in order, without repeats."""
    return tuple(dict.fromkeys(int(number) for number in _TITLE_ID.findall(title)))


def delivers_named(messages) -> tuple[int, ...]:
    """The items the trailer blocks of `messages` name with `Delivers: sd:<n>`, in order, without repeats (sd:3704).

    Only a whole `sd:<n>` value counts; a `docs/work` slug names no row here.
    """
    found: list[int] = []
    for message in messages:
        for line in sd_lib.trailer_block(message).splitlines():
            key, _, value = line.partition(":")
            if key.strip().lower() == "delivers" and re.fullmatch(r"sd:[1-9][0-9]*", value.strip()):
                number = int(value.strip()[3:])
                if number not in found:
                    found.append(number)
    return tuple(found)


def items_closed(body: str, named, item: int, deliver: bool) -> tuple[int, ...]:
    """The items a merge closes beside `item`: each `Closes:` item, then each of `named`.

    `named` is what the branch's own commits deliver (sd:3704); a receipt
    prepared before that passes its title's ids, the rule it was sent under
    (sd:3014). An associate-only claim closes nothing (sd:3365).
    """
    if not deliver:
        return ()
    return tuple(dict.fromkeys(number for number in (*closes_named(body, item), *named) if number != item))


def refuse_unclosable(connection, item: int, repo: str, body: str, named, deliver: bool) -> None:
    """Refuse a co-delivered item the merge could not close; `repo` is `item`'s registered path.

    One pull request claims one item; `Closes:` and the branch commits'
    `Delivers:` trailers (`named`) name the others it delivers, and the merge
    closes them (operator ruling 2026-10-03, sd:3704). `Refs:` names related
    items and is not read here: they stay open. An associate-only claim
    closes nothing, so its `Closes:` line or delivering commit is refused
    rather than dropped (sd:3365). `sd-ship prepare` and `sd-ship lane
    enqueue` both read it (sd:3473).
    """
    if not deliver and (closes_named(body, item) or named):
        said = ([f"Closes: sd:{number}" for number in closes_named(body, item)]
                + [f"Delivers: sd:{number}" for number in named])
        raise Refusal(f"an associate-only claim on sd:{item} closes nothing, and the pull request says "
                      f"{', '.join(f'`{line}`' for line in said)}",
                      code="closes_need_delivery", boundary="input", state="operator_decision",
                      next_action="Move the Closes: items to Refs: and drop the commits' Delivers: trailers, "
                                  "or name them on the item's --deliver pull request.")
    for number in items_closed(body, named, item, deliver):
        row = connection.execute("SELECT repo FROM item WHERE id = ?", (number,)).fetchone()
        if row is None:
            raise Refusal(f"Closes: or a branch commit's Delivers: names sd:{number}, which is no item; "
                          "the merge closes every item they name",
                          code="closes_item_unknown", boundary="input", state="operator_decision",
                          next_action="Correct the Closes: line or the commit's trailer, or move a related item to Refs:.")
        if row["repo"] != repo:
            raise Refusal(f"Closes: or a branch commit's Delivers: names sd:{number}, which belongs to another "
                          "repository; a merge closes only this repository's items",
                          code="closes_item_foreign", boundary="input", state="operator_decision",
                          next_action="Close that item from its own repository, or move it to Refs:.")


def published(body: str, item: int) -> str:
    """The body as `sd-ship` publishes it: normalized, then one `Work:` line."""
    return f"{body}\n\n{sd_lib.WORK_TRAILER} sd:{item}\n"


def failures(result) -> list[str]:
    """The `FAIL` lines of a finished lint.

    A non-zero exit that printed no `FAIL` line is refused with its raw output:
    the lint also exits 1 on an uncaught exception, and a traceback read as
    zero failures would let a lint that never finished pass.
    """
    found = [line[len("FAIL "):] for line in result.stderr.splitlines() if line.startswith("FAIL ")]
    if result.returncode and not found:
        raise Refusal((result.stderr or result.stdout or "sd-docs-lint failed").strip()[-2000:],
                      code="docs_lint_failed", state="retryable_failure",
                      next_action="Inspect the lint error, resolve its cause, then prepare again.")
    return found


def lint_failures(tree: pathlib.Path, argv: list[str]) -> list[str]:
    """`failures` of `argv` run in `tree`, each path made relative to `tree`."""
    result = completed_process(tree, argv, timeout=300, answers=frozenset({0, 1}))
    # Longest first: a resolved `/private/var/...` contains the `/var/...` form.
    prefixes = sorted({f"{tree}/", f"{tree.resolve()}/"}, key=len, reverse=True)
    found = []
    for failure in failures(result):
        for prefix in prefixes:
            failure = failure.replace(prefix, "")
        found.append(failure)
    return found


def base_lint_failures(root: pathlib.Path, argv: list[str], base: str) -> set[str]:
    """`lint_failures` in a scratch checkout of `origin/<base>`; empty if it cannot be checked out or linted.

    Hooks are off for the checkout: a consumer's `post-checkout` is no part of a lint.
    Git runs through `completed_process`, whose timeout a large tree's checkout fits.
    """
    with tempfile.TemporaryDirectory(prefix="sd-ship-lint-base-") as directory:
        tree = pathlib.Path(directory) / "base"
        try:
            completed_process(root, ["git", "-c", "core.hooksPath=/dev/null", "worktree", "add", "--detach",
                                     "--quiet", str(tree), f"refs/remotes/origin/{base}"], timeout=300)
        except Refusal:
            return set()
        try:
            return set(lint_failures(tree, argv))
        except Refusal:
            # A base run that did not finish excuses nothing.
            return set()
        finally:
            completed_process(root, ["git", "worktree", "remove", "--force", str(tree)], timeout=300,
                              answers=frozenset(range(256)))


def lint_against_base(root: pathlib.Path, argv: list[str], base: str) -> list[str]:
    """Judge a failed docs lint against the same lint at `origin/<base>` (sd:1646).

    A tree failure the default branch already has is not the branch's to fix:
    it comes back as a warning, and only the failures the branch introduces
    refuse. The base run gets no `--pr-body`, since the body is the branch's
    own, so a body-rule failure is never excused. Under `--body-only` no tree
    rule ran, and the head's answer stands. A failure is matched by its whole
    line, so one the branch moved to another line counts as introduced.
    """
    head = lint_failures(root, argv)
    known: list[str] = []
    if head and "--body-only" not in argv:
        at = argv.index("--pr-body") if "--pr-body" in argv else len(argv)
        on_base = base_lint_failures(root, argv[:at] + argv[at + 2:], base)
        known = [failure for failure in head if failure in on_base]
    introduced = [failure for failure in head if failure not in known]
    if introduced:
        also = f"\n{len(known)} more failure(s) already on origin/{base} do not block this branch." if known else ""
        raise Refusal(f"sd-docs-lint: {len(introduced)} failure(s) this branch introduces:\n"
                      + "\n".join(f"FAIL {failure}" for failure in introduced) + also,
                      code="docs_lint_failed", state="retryable_failure",
                      next_action="Fix the failures this branch introduces, commit, then prepare again.")
    return [f"sd-docs-lint: {len(known)} failure(s) already on origin/{base}, not introduced by this branch, "
            "do not block it: " + "; ".join(known)] if known else []
