"""The pull-request body `sd-ship` publishes, read against the lines it owns (sd:1870).

`sd-ship` writes `Work:` into the body it publishes, and `Item:`, `Delivers:`
and the authorship lines into the squash message. A supplied body that says
the same thing is not a conflict, so such a line is stripped and named in the
result. A line that says something else -- another item, a delivery nobody
claimed, an author no registry knows, a pre-squash sha -- is refused by line
number, with the value `sd-ship` would have written.

The fixpoint is the point: `normalize` of a body `sd-ship` published returns
the body it published before appending `Work:`, so the live pull-request body
fed back as `--body-file` prepares again without a refusal. Before this, the
body `sd-ship` itself wrote was refused as input (#1236, #1238).

A body with no item owns nothing: every owned line refuses there, indented
or not, and nothing is stripped. With an item, only a line at column zero is
read, because that is the only form git or rule 5 reads; an indented line is
prose about a trailer, and the body keeps it.
"""

from __future__ import annotations

import dataclasses
import functools
import pathlib
import re
import tempfile

import sd_lib
from sd_ship_remote import Refusal, completed_process

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


def owned_lines(body: str) -> list[OwnedLine]:
    """Every line of `body` that starts with an owned key, indented or not."""
    found = []
    for number, line in enumerate(body.split("\n"), start=1):
        match = _OWNED_RE.match(line.rstrip("\r"))
        if match is not None:
            found.append(OwnedLine(number, line.rstrip("\r"), _CANONICAL[match["key"].lower()],
                                   match["value"].strip(), bool(match["indent"])))
    return found


def registries() -> list:
    """The operator's registry and the pack's own `providers.yaml`, each that reads."""
    import sd_registry  # noqa: PLC0415 - only a body naming an author needs it
    found = []
    home, reason = sd_registry.read_or_report()
    if not reason:
        found.append(home)
    try:
        found.append(sd_registry.read_file(sd_registry.shipped_path(pathlib.Path(__file__).resolve().parent.parent)))
    except sd_registry.RegistryError:
        pass
    return found


def known_author(value: str, readers: list) -> bool:
    """Whether `value` is a reserved author or the `<entry>/<vendor>` a registry resolves."""
    if value in sd_lib.RESERVED_AUTHORS.values():
        return True
    entry, separator, _vendor = value.partition("/")
    for registry in readers:
        try:
            if separator and sd_lib.attribution_value(entry, registry) == value:
                return True
        except sd_lib.TrailerError:
            continue
    return False


def problem(line: OwnedLine, item: int, deliver: bool, readers: list | None) -> str | None:
    """Why `line` cannot be stripped from an item's body, or None when it can."""
    expected = f"sd:{item}"
    if line.key in (sd_lib.ITEM_TRAILER, sd_lib.WORK_TRAILER):
        return None if line.value == expected else f"expected `{line.key} {expected}`"
    if line.key == sd_lib.DELIVERS_TRAILER:
        if not deliver:
            return "expected no line: delivery is claimed with --deliver, never by the body"
        return None if line.value == expected else f"expected `{line.key} {expected}`"
    if line.key == sd_lib.AUTHORED_TRAILER:
        if known_author(line.value, registries() if readers is None else readers):
            return None
        return (f"expected `{line.key} {sd_lib.HUMAN_AUTHOR}` or an `<entry>/<vendor>` the provider "
                f"registry resolves; the commits decide authorship")
    if line.key == sd_lib.ATTRIBUTES_TRAILER:
        return "expected no line: it names a pre-squash sha, and the squash carries authorship from the commits"
    return f"expected no line: `{line.key}` rides a later merge or an empty commit, never this body"


def normalize(body: str, item: int | None, *, deliver: bool = False,
              readers: list | None = None) -> tuple[str, tuple[str, ...]]:
    """`body` without the owned lines that agree with `sd-ship`, and those lines.

    Refuses, naming every offending line, when any owned line disagrees. With
    no item, every owned line disagrees and `body` is returned unchanged.
    With an item, the result carries no trailing whitespace, which is what
    makes `normalize(published)` equal the body before `Work:` was appended.
    """
    found = owned_lines(body)
    if item is None:
        if found:
            raise Refusal("no-item publication cannot carry item or caller-supplied authorship trailers: "
                          + "; ".join(f"line {line.number}: `{line.text.strip()}`" for line in found))
        return body, ()
    read = [line for line in found if not line.indented]
    problems = [(line, reason) for line in read
                if (reason := problem(line, item, deliver, readers)) is not None]
    if problems:
        raise Refusal("the ship adapter owns association and delivery trailers: "
                      + "; ".join(f"line {line.number}: `{line.text}`; {reason}" for line, reason in problems),
                      code="body_trailer_refused", boundary="input", state="operator_decision",
                      next_action="Remove or correct the named lines; sd-ship writes them itself.")
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


def published(body: str, item: int) -> str:
    """The body as `sd-ship` publishes it: normalized, then one `Work:` line."""
    return f"{body}\n\n{sd_lib.WORK_TRAILER} sd:{item}\n"


@functools.cache
def docs_lint():
    """`sd-docs-lint` as a module, loaded once: rule 8 is the one reading of scope."""
    return sd_lib.sibling("sd_docs_lint_scope", "sd-docs-lint")


def lint_failures(tree: pathlib.Path, argv: list[str]) -> list[str]:
    """The `FAIL` lines `argv` prints in `tree`, each path made relative to `tree`.

    A non-zero exit that printed no `FAIL` line is refused with its raw output:
    the lint also exits 1 on an uncaught exception, and a traceback read as
    zero failures would let a lint that never finished pass.
    """
    result = completed_process(tree, argv, timeout=300, answers=frozenset({0, 1}))
    # Longest first: a resolved `/private/var/...` contains the `/var/...` form.
    prefixes = sorted({f"{tree}/", f"{tree.resolve()}/"}, key=len, reverse=True)
    failures = []
    for line in result.stderr.splitlines():
        if line.startswith("FAIL "):
            failure = line[len("FAIL "):]
            for prefix in prefixes:
                failure = failure.replace(prefix, "")
            failures.append(failure)
    if result.returncode and not failures:
        raise Refusal((result.stderr or result.stdout or f"{argv[0]} failed").strip()[-2000:],
                      code="docs_lint_failed", state="retryable_failure",
                      next_action="Inspect the lint error, resolve its cause, then prepare again.")
    return failures


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


def pull_paths(files: list) -> list[str]:
    """Every path a pull request's `files` listing touches, both ends of a rename.

    GitHub lists a moved file under its new name and keeps the old one in
    `previous_filename`. Rule 8 reads both, as `git diff --no-renames` does,
    so a workflow moved out of `.github/` still demands its scope line.
    """
    paths: list[str] = []
    for row in files:
        for key in ("previous_filename", "filename"):
            name = row.get(key) if isinstance(row, dict) else None
            if isinstance(name, str) and name and name not in paths:
                paths.append(name)
    return paths


def demanded_scope(root: pathlib.Path, body: str, changed: list[str]) -> list[dict]:
    """Each scope line `changed` demands: the line, the first path demanding it, and whether `body` has it.

    The classes, the glob match and the line match are rule 8's own, read from
    `sd-docs-lint`, so this answer and the lint's verdict cannot disagree. An
    empty list is a diff that demands nothing, or a repository with no policy.
    """
    lint = docs_lint()
    demanded = []
    for line, globs in lint.scope_classes(root) or []:
        path = next((name for name in changed if any(lint.matches_scope(name, glob) for glob in globs)), None)
        if path is not None:
            demanded.append({"line": line, "path": path, "present": lint.scope_line_present(body, line)})
    return demanded
