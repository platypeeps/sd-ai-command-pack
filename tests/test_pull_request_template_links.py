"""The pull-request template links only to files that exist (sd:10, criterion 22).

`tests/test_delivery_evidence.py` reads the template for its trailer block and
nothing else, so a path the template names could stop existing and no test
would say so. This walks every link in every pull-request template the
repository tracks and asserts that each one resolves.

What counts as a link, and what resolving means:

* An inline markdown link `[text](target)`, a reference definition
  `[label]: target`, and an HTML `href="target"`. A relative target resolves
  against the template's own directory, a target starting with `/` against the
  repository root, and either must be a tracked file or a directory holding one.
* A repository path written in prose, which is how the template actually names
  files (`.github/copilot-instructions.md` sits inside an HTML comment). A
  token is a path claim when its last segment carries a suffix some tracked
  file carries, or when its first segment is a tracked top-level entry, so
  `pack/Trellis` and `CI/review` are words and `bin/sd-status` is a path. It
  resolves against the repository root, the way the prose writes it.
* An anchor `#name` resolves to a heading, or to an HTML `id`/`name`, in the
  document it points into: the template itself for a bare `#name`, the target
  file otherwise.
* A URL is not a file. It is counted and not fetched; this test makes no
  network call.
* A token carrying a metavariable (`<id>`, `YYYY`) is a pattern, not a path,
  and is skipped by the same rule `bin/sd-docs-lint` rule 7 applies.

The link and metavariable grammar is `bin/sd-docs-lint`'s own
(`MARKDOWN_LINK_RE`, `METAVARIABLE_RE`), imported rather than restated. Rule 7
itself resolves only `docs/work/` paths, so the resolver here is new; it reads
the tracked set from git rather than the filesystem, so a file that exists only
in one checkout cannot make the test pass there and fail in CI.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import pathlib
import re
import subprocess
import tempfile
import unittest
from types import ModuleType
from typing import NamedTuple

ROOT = pathlib.Path(__file__).resolve().parents[1]
LINT_PATH = ROOT / "bin" / "sd-docs-lint"


def load_lint() -> ModuleType:
    """Import `bin/sd-docs-lint`, which has no .py suffix to import by name."""
    loader = importlib.machinery.SourceFileLoader("sd_docs_lint_links", str(LINT_PATH))
    spec = importlib.util.spec_from_loader("sd_docs_lint_links", loader)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


lint = load_lint()
MARKDOWN_LINK_RE: re.Pattern[str] = lint.MARKDOWN_LINK_RE
METAVARIABLE_RE: re.Pattern[str] = lint.METAVARIABLE_RE

#: GitHub reads a pull-request template from the root, `docs/` or `.github/`,
#: as one file named `pull_request_template.md` in any case, or as any markdown
#: file inside a `PULL_REQUEST_TEMPLATE/` directory there.
TEMPLATE_FILE_RE = re.compile(
    r"^(?:|docs/|\.github/)(?:pull_request_template\.md|pull_request_template/[^/]+\.md)$",
    re.IGNORECASE,
)
REFERENCE_DEFINITION_RE = re.compile(r"^[ ]{0,3}\[[^\]]+\]:[ \t]*<?([^\s>]+)>?", re.MULTILINE)
HREF_RE = re.compile(r"""\bhref=["']([^"']+)["']""", re.IGNORECASE)
HTML_ANCHOR_RE = re.compile(r"""\b(?:id|name)=["']([^"']+)["']""", re.IGNORECASE)
URL_RE = re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s<>()\[\]]+|\bmailto:\S+", re.IGNORECASE)
SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.-]*:", re.IGNORECASE)
PATH_TOKEN_RE = re.compile(r"(?<![\w:/.<>-])[\w./<>-]*[\w<>/-]")
ATX_HEADING_RE = re.compile(r"^[ ]{0,3}#{1,6}[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*$")
FENCE_RE = re.compile(r"^[ ]{0,3}(```|~~~)")


class Walk(NamedTuple):
    """What one template's walk read, and what of it did not resolve."""

    files: tuple[str, ...]
    anchors: tuple[str, ...]
    urls: tuple[str, ...]
    broken: tuple[str, ...]


def tracked_files(repo: pathlib.Path) -> frozenset[str]:
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--deduplicate"], cwd=repo,
        capture_output=True, text=True, check=True, timeout=60)
    return frozenset(name for name in listed.stdout.split("\0") if name)


def templates(tracked: frozenset[str]) -> list[str]:
    """Every tracked pull-request template, in path order."""
    return sorted(name for name in tracked if TEMPLATE_FILE_RE.match(name))


def github_slug(heading: str) -> str:
    """The anchor GitHub gives a heading: lowercased, punctuation dropped,
    spaces made hyphens. Duplicates are numbered by `anchors_of`."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", heading).strip().lower()
    return re.sub(r"[^\w\- ]", "", text).replace(" ", "-")


def anchors_of(text: str) -> frozenset[str]:
    """Every anchor a markdown document offers: its ATX headings outside fenced
    code, numbered the way GitHub numbers repeats, and any HTML id or name."""
    found: set[str] = set()
    seen: dict[str, int] = {}
    fenced = False
    for line in text.splitlines():
        if FENCE_RE.match(line):
            fenced = not fenced
            continue
        heading = None if fenced else ATX_HEADING_RE.match(line)
        if heading is None:
            continue
        slug = github_slug(heading.group(1))
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        found.add(slug if count == 0 else f"{slug}-{count}")
    found.update(HTML_ANCHOR_RE.findall(text))
    return frozenset(found)


def is_tracked_path(relative: str, tracked: frozenset[str]) -> bool:
    prefix = relative.rstrip("/") + "/"
    return relative in tracked or any(name.startswith(prefix) for name in tracked)


def walk(repo: pathlib.Path, template: str, tracked: frozenset[str]) -> Walk:
    """Read every link in `template` and resolve each against `tracked`."""
    text = (repo / template).read_text(encoding="utf-8")
    files: list[str] = []
    anchors: list[str] = []
    urls: list[str] = []
    broken: list[str] = []
    root = repo.resolve()
    top_level = {name.split("/", 1)[0] for name in tracked}
    suffixes = {pathlib.PurePosixPath(name).suffix for name in tracked} - {""}

    def resolve(target: str, base: pathlib.Path, form: str) -> None:
        if METAVARIABLE_RE.search(target):
            return
        if SCHEME_RE.match(target):
            urls.append(target)
            return
        path, _, anchor = target.partition("#")
        document = template
        if path:
            joined = root / path.lstrip("/") if path.startswith("/") else base / path
            try:
                document = joined.resolve().relative_to(root).as_posix()
            except ValueError:
                broken.append(f"{form} {target!r} leaves the repository")
                return
            files.append(document)
            if not is_tracked_path(document, tracked):
                broken.append(f"{form} {target!r} names no tracked file ({document})")
                return
        if anchor:
            anchors.append(f"{document}#{anchor}")
            if document.endswith(".md") and (repo / document).is_file():
                offered = anchors_of((repo / document).read_text(encoding="utf-8"))
            else:
                offered = frozenset()
            if anchor not in offered:
                broken.append(f"{form} {target!r} names no heading in {document}")

    template_dir = (root / template).parent
    linked = MARKDOWN_LINK_RE.findall(text)
    if text.count("](") != len(linked):
        broken.append(
            f"{text.count('](')} inline link opener(s) but {len(linked)} parsed; "
            "a link this walk cannot read is not a link it has checked")
    for target in linked:
        resolve(target, template_dir, "link")
    for target in REFERENCE_DEFINITION_RE.findall(text):
        resolve(target, template_dir, "reference")
    for target in HREF_RE.findall(text):
        resolve(target, template_dir, "href")

    prose = URL_RE.sub(" ", MARKDOWN_LINK_RE.sub("] ", text))
    prose = HREF_RE.sub(" ", REFERENCE_DEFINITION_RE.sub(" ", prose))
    for match in URL_RE.finditer(MARKDOWN_LINK_RE.sub("] ", text)):
        urls.append(match.group(0))
    for token in PATH_TOKEN_RE.findall(prose):
        token = token.rstrip(".")
        if "/" not in token and "." not in token:
            continue
        first = token.lstrip("/").split("/", 1)[0]
        if pathlib.PurePosixPath(token).suffix in suffixes or first in top_level:
            resolve("/" + token.lstrip("/"), root, "path")
    return Walk(tuple(files), tuple(anchors), tuple(urls), tuple(broken))


class TemplateLinkTests(unittest.TestCase):
    """The repository's own templates."""

    def test_every_link_in_every_pull_request_template_resolves(self) -> None:
        tracked = tracked_files(ROOT)
        found = templates(tracked)
        self.assertIn(".github/PULL_REQUEST_TEMPLATE.md", found)
        for template in found:
            with self.subTest(template=template):
                result = walk(ROOT, template, tracked)
                self.assertEqual((), result.broken, "\n".join(result.broken))
                # A walk that read nothing passes on nothing.
                self.assertTrue(result.files or result.anchors or result.urls,
                                f"{template}: the walk read no link at all")


def fixture_repo(files: dict[str, str]) -> tuple[tempfile.TemporaryDirectory, pathlib.Path]:
    holder = tempfile.TemporaryDirectory()
    repo = pathlib.Path(holder.name)
    for name, body in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(body, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, timeout=60)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, timeout=60)
    return holder, repo


TEMPLATE = ".github/PULL_REQUEST_TEMPLATE.md"
GUIDE = "docs/guide.md"
GUIDE_BODY = "# Guide\n\n## Review scope\n\n## Review scope\n\n```\n# not a heading\n```\n"


class WalkerTests(unittest.TestCase):
    """Each link form, green and red, on a fixture repository."""

    def broken(self, template_body: str, extra: dict[str, str] | None = None) -> tuple[str, ...]:
        holder, repo = fixture_repo({TEMPLATE: template_body, GUIDE: GUIDE_BODY, **(extra or {})})
        self.addCleanup(holder.cleanup)
        return walk(repo, TEMPLATE, tracked_files(repo)).broken

    def test_links_that_resolve_pass(self) -> None:
        body = (
            "See [the guide](../docs/guide.md#review-scope-1) and [root](/docs/guide.md).\n"
            "<!-- as described in docs/guide.md and in docs/ -->\n"
            "Jump to [the top](#summary).\n\n## Summary\n\n"
            "[ref]: ../docs/guide.md#guide\n"
            '<a href="/docs/guide.md#review-scope">x</a>\n'
            "Words like pack/Trellis, CI/review and e.g. are not paths.\n"
            "[Claude Code](https://claude.com/claude-code) https://claude.ai/code/session_<id>\n"
            "Pattern docs/work/<YYYY-MM-DD>-<slug>/prd.md is a pattern.\n"
        )
        self.assertEqual((), self.broken(body))

    def test_an_inline_link_to_a_missing_file_fails(self) -> None:
        self.assertEqual(1, len(self.broken("[gone](../docs/gone.md)\n")))

    def test_a_link_that_leaves_the_repository_fails(self) -> None:
        self.assertEqual(1, len(self.broken("[out](../../../etc/hosts)\n")))

    def test_an_untracked_file_does_not_count_as_existing(self) -> None:
        holder, repo = fixture_repo({TEMPLATE: "Read docs/later.md.\n", GUIDE: GUIDE_BODY})
        self.addCleanup(holder.cleanup)
        (repo / "docs" / "later.md").write_text("# Later\n", encoding="utf-8")
        self.assertEqual(1, len(walk(repo, TEMPLATE, tracked_files(repo)).broken))

    def test_a_prose_path_to_a_missing_file_fails(self) -> None:
        self.assertEqual(1, len(self.broken("<!-- as described in docs/gone.md. -->\n")))

    def test_a_prose_path_without_a_suffix_under_a_tracked_directory_fails(self) -> None:
        self.assertEqual(1, len(self.broken("Run docs/missing-tool first.\n")))

    def test_a_reference_definition_to_a_missing_file_fails(self) -> None:
        self.assertEqual(1, len(self.broken("[ref]: ../docs/gone.md\n")))

    def test_an_href_to_a_missing_file_fails(self) -> None:
        self.assertEqual(1, len(self.broken('<a href="/docs/gone.md">x</a>\n')))

    def test_an_anchor_to_a_missing_heading_in_another_file_fails(self) -> None:
        self.assertEqual(1, len(self.broken("[x](../docs/guide.md#review-scope-2)\n")))

    def test_an_anchor_inside_a_code_fence_is_not_a_heading(self) -> None:
        self.assertEqual(1, len(self.broken("[x](../docs/guide.md#not-a-heading)\n")))

    def test_an_anchor_to_a_missing_heading_in_the_template_fails(self) -> None:
        self.assertEqual(1, len(self.broken("[x](#nowhere)\n\n## Summary\n")))

    def test_a_link_the_grammar_cannot_read_fails_rather_than_passing(self) -> None:
        broken = self.broken('[x](../docs/guide.md "a title")\n')
        self.assertIn("1 inline link opener(s) but 0 parsed", "\n".join(broken))

    def test_every_template_location_is_walked(self) -> None:
        holder, repo = fixture_repo({
            TEMPLATE: "x\n",
            ".github/PULL_REQUEST_TEMPLATE/feature.md": "x\n",
            "docs/pull_request_template.md": "x\n",
            "pull_request_template.md": "x\n",
            "docs/notes/pull_request_template.md": "not a location GitHub reads\n",
        })
        self.addCleanup(holder.cleanup)
        self.assertEqual(
            [
                ".github/PULL_REQUEST_TEMPLATE.md",
                ".github/PULL_REQUEST_TEMPLATE/feature.md",
                "docs/pull_request_template.md",
                "pull_request_template.md",
            ],
            templates(tracked_files(repo)),
        )


if __name__ == "__main__":
    unittest.main()
