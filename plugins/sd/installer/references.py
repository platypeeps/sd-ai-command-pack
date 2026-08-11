"""Relocated-resource reference rewriting, shared by the payload builders.

The pack authors its skills, commands, and reference documentation against a
vendored checkout: `bash scripts/sd-ai-command-pack-toolchain.sh ...`, `see
docs/SD_AI_COMMAND_PACK.md`. Two payloads relocate those resources out of the
repository, and each has to rewrite the references that name them:

* the **Claude Code plugin** (`.github/scripts/generate-plugin.py`) puts
  scripts on the Bash tool PATH, so `scripts/<name>` becomes the bare command;
* the **machine payload** (`installer.machinestage`) puts them under
  `~/.agents/bin`, so `scripts/<name>` becomes `~/.agents/bin/<name>` and
  `docs/SD_AI_COMMAND_PACK.md` becomes `~/.agents/docs/SD_AI_COMMAND_PACK.md`;
* a **thin conversion** (`installer.thin`) does not relocate anything -- it
  deletes the vendored copies and leaves the machine installation in place --
  but the repo-native files it *keeps* still name the deleted paths, so their
  text is rewritten in the consumer's own repository as the last step of the
  conversion.

The third profile is not a third payload, and it is the one with a constraint
the others do not have: its output is read back by the thin resweep, which
classifies path *suffixes*. `~/.agents/docs/SD_AI_COMMAND_PACK.md` ends with
the removed `docs/SD_AI_COMMAND_PACK.md` and would be reported as a citation
of it, so `THIN_PROFILE` names the directory and leaves the file to prose. The
machine payload keeps the fuller form because payload files are never scanned.

The rewrite rules, the residue gate, and the dependency-closure gate live here
once and are parameterized by a `RewriteProfile`, because the interesting part
is not the substitution: it is knowing which occurrences are *not* references
(a hyperlink into the source repository on GitHub, prose about pack-source-only
fleet tooling) and which rewritten references name something the payload does
not actually carry. Splitting that judgement across two implementations is how
one payload silently ends up shipping instructions the other has already
proven broken.

Scope, deliberately: only text surfaces are rewritten. Executables are copied
verbatim into both payloads and their repository-root literals are governed by
`BIN_LITERAL_ALLOWLIST` — every one of those is semantic data about *another*
filesystem (the repository being audited, the diff being classified), not a
path the script resolves to reach a sibling, which
`tests/test_script_sibling_resolution.py` forbids outright.

Callers pass their allowlists in rather than having them read from here, so a
test can patch the allowlist its consumer exposes and see the effect.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

PACK_DOC_NAME = "SD_AI_COMMAND_PACK.md"
PACK_DOC_REFERENCE = f"docs/{PACK_DOC_NAME}"

AGENTS_BIN_REFERENCE = "~/.agents/bin"
AGENTS_DOC_REFERENCE = f"~/.agents/docs/{PACK_DOC_NAME}"

_PACK_SCRIPT_NAME = (
    r"(?:sd-ai-command-pack-[A-Za-z0-9_-]+\.(?:py|sh|mjs)"
    r"|sd_ai_command_pack_[A-Za-z0-9_]+\.py)"
)
# A repository-root reference is one nothing else owns the prefix of: the
# lookbehind keeps `.../blob/main/scripts/<name>` in a hyperlink and
# `templates/scripts/<name>` in prose out of the rewrite, since neither names
# the copy the payload relocates.
_ROOT_RELATIVE = r"(?<![A-Za-z0-9_./-])"
SCRIPT_REFERENCE_RE = re.compile(rf"{_ROOT_RELATIVE}scripts/({_PACK_SCRIPT_NAME})")
DOC_REFERENCE_RE = re.compile(rf"{_ROOT_RELATIVE}{re.escape(PACK_DOC_REFERENCE)}")
# `node <name>.mjs` -> `<name>.mjs`: bash PATH-searches a slash-free operand,
# node does not, and every plugin bin/ entry carries a shebang plus an
# executable bit. Machine-scope references keep their runner: they name a path.
NODE_PREFIX_RE = re.compile(r"\bnode (sd-ai-command-pack-[A-Za-z0-9_-]+\.mjs)")

# Anything still naming a repository-root pack path after the rewrite. No
# lookbehind here on purpose: the residue gate is the last line of defense, so
# it reports the hyperlink form too and forces a written exemption rather than
# quietly agreeing with the rewrite's own judgement.
RESIDUE_RE = re.compile(r"scripts/sd[-_]ai[-_]command[-_]pack[A-Za-z0-9_.*-]*")
DOC_RESIDUE_RE = re.compile(re.escape(PACK_DOC_REFERENCE))
BARE_COMMAND_RE = re.compile(_PACK_SCRIPT_NAME)

# The one form nothing else sees: hard-wrapping a reference between the
# directory and the name it precedes hides it from the rewrite (the pattern
# needs both halves adjacent) and from the residue scan (same reason), while
# the closure gate finds only the bare name, which the payload usually does
# ship. The payload then carries an instruction naming a directory it does not
# install. The leading line is inspected in `check_wrapped_references` rather
# than matched here: a pattern that has to scan back over the line first is
# quadratic in line length, and payload text is not always hard-wrapped.
_WRAPPED_SCRIPT_RE = re.compile(rf"scripts/[ \t]*\n[ \t]*({_PACK_SCRIPT_NAME})")
_WRAPPED_DOC_RE = re.compile(rf"docs/[ \t]*\n[ \t]*({re.escape(PACK_DOC_NAME)})")

_RESIDUE_PREFIX = "scripts/"


class ReferenceRewriteError(Exception):
    """A rewrite, residue, or closure violation that fails the payload build."""


# file name -> (justification, literals that may appear in it).
#
# Every literal is semantic data about some *other* filesystem: a consumer
# repository being audited, a changed-path set being classified, the pack
# source repository's own tree, or a comment consumed by a linter. None of them
# resolves a helper the script then runs — functional sibling resolution is
# forbidden outright by tests/test_script_sibling_resolution.py, whose
# justifications these mirror.
BIN_LITERAL_ALLOWLIST: dict[str, tuple[str, frozenset[str]]] = {
    "sd-ai-command-pack-check.py": (
        "repo-scoped payload discovery: sd-check reports whether the repository "
        "under --repo carries the vendored helpers, so the paths describe that "
        "repository's layout, not this script's siblings",
        frozenset(
            {
                "scripts/sd-ai-command-pack-install-audit.py",
                "scripts/sd-ai-command-pack-pr-body-scope.py",
                "scripts/sd-ai-command-pack-review-preflight.mjs",
                "scripts/sd-ai-command-pack-review-scope.sh",
                "scripts/sd-ai-command-pack-update-spec-kb.py",
            }
        ),
    ),
    "sd-ai-command-pack-full-check.sh": (
        "pack-source-only release gate: the fleet candidate checker has no "
        "manifest row and only ever runs inside the pack source repository, "
        "whose own tree is the correct anchor",
        frozenset({"scripts/sd-ai-command-pack-fleet-candidate-check.py"}),
    ),
    "sd-ai-command-pack-housekeeping.sh": (
        "shellcheck source= directive: a static-analysis annotation, not a "
        "runtime path (the runtime load uses $SCRIPT_DIR)",
        frozenset({"scripts/sd-ai-command-pack-shell-lib.sh"}),
    ),
    "sd-ai-command-pack-install-audit.py": (
        "consumer-layout data: the audit describes where a vendored install "
        "puts payload files in the repository it inspects",
        frozenset(
            {
                "scripts/sd-ai-command-pack-",
                "scripts/sd-ai-command-pack-*",
                "scripts/sd-ai-command-pack-fleet-candidate-check.py",
                "scripts/sd-ai-command-pack-fleet-controller.py",
                "scripts/sd-ai-command-pack-fleet-finding-classify.py",
                "scripts/sd-ai-command-pack-fleet-preflight.py",
                "scripts/sd-ai-command-pack-fleet-publish.py",
                "scripts/sd-ai-command-pack-fleet-review-classify.py",
                "scripts/sd-ai-command-pack-fleet-timing.py",
                "scripts/sd-ai-command-pack-fleet-wave-plan.py",
                "scripts/sd-ai-command-pack-full-check.sh",
                "scripts/sd-ai-command-pack-housekeeping.sh",
                "scripts/sd-ai-command-pack-thin-resweep.py",
                "scripts/sd_ai_command_pack_fleet_lib.py",
                "scripts/sd_ai_command_pack_lib.py",
            }
        ),
    ),
    "sd-ai-command-pack-pr-body-scope.py": (
        "consumer-layout data: region globs classify changed paths in the "
        "repository whose PR body is being scoped",
        frozenset(
            {
                "scripts/sd-ai-command-pack-*.mjs",
                "scripts/sd-ai-command-pack-*.py",
                "scripts/sd-ai-command-pack-*.sh",
                "scripts/sd-ai-command-pack-full-check.sh",
                "scripts/sd-ai-command-pack-housekeeping.sh",
                "scripts/sd-ai-command-pack-install-audit.py",
                "scripts/sd-ai-command-pack-pr-body-scope.py",
                "scripts/sd-ai-command-pack-review-learnings.py",
                "scripts/sd-ai-command-pack-review-scope.sh",
                "scripts/sd-ai-command-pack-shell-lib.sh",
                "scripts/sd_ai_command_pack_*.py",
                "scripts/sd_ai_command_pack_lib.py",
            }
        ),
    ),
    "sd-ai-command-pack-review-learnings.py": (
        "changed-path classification: payload prefixes used to recognize pack "
        "files in a diff",
        frozenset({"scripts/sd-ai-command-pack-", "scripts/sd_ai_command_pack_"}),
    ),
    "sd-ai-command-pack-review-preflight.mjs": (
        "changed-path classification: copiedTemplateKind recognizes vendored "
        "payload paths in a diff",
        frozenset(
            {
                "scripts/sd-ai-command-pack-",
                "scripts/sd-ai-command-pack-review-scope.sh",
            }
        ),
    ),
    "sd-ai-command-pack-surface-check.py": (
        "pack-source-only validator: every path names the pack source "
        "repository's own tree, which is always a full checkout",
        frozenset(
            {
                "scripts/sd-ai-command-pack-fleet-candidate-check.py",
                "scripts/sd-ai-command-pack-full-check.sh",
                "scripts/sd-ai-command-pack-surface-check.py",
            }
        ),
    ),
    "sd-ai-command-pack-toolchain.sh": (
        "repository-state report: doctor tells the operator whether the "
        "repository it inspects carries a vendored full-check",
        frozenset({"scripts/sd-ai-command-pack-full-check.sh"}),
    ),
    "sd-ai-command-pack-update-spec-kb.py": (
        "generated-file provenance: the banner written into generated KB files "
        "names the generator by its canonical repository path",
        frozenset({"scripts/sd-ai-command-pack-update-spec-kb.py"}),
    ),
    "sd_ai_command_pack_fleet_lib.py": (
        "release-evidence layout data: CANDIDATE_VALIDATOR_SOURCES names the "
        "candidate validator's path in the pack source repository's own tree, "
        "the one tree a candidate ledger is ever recorded against. It is never "
        "resolved against this file's location -- the digest takes a "
        "caller-supplied loader so the same names can be read from a working "
        "tree or from a git commit's blobs",
        frozenset({"scripts/sd-ai-command-pack-fleet-candidate-check.py"}),
    ),
}

# (payload-relative Markdown path, bare command) -> justification for a
# reference the payload cannot satisfy from its relocated script directory.
# One dict per payload because the two name the same authored file
# differently; the shared justification is one fact, and both entries retire
# together when the skill text is fixed.
_FLEET_REVIEW_CLASSIFY_JUSTIFICATION = (
    "fleet-operator path: the fleet scripts have no manifest rows, so this "
    "reference is already absent from vendored consumer installs today; a "
    "follow-up task fixes the skill text and retires this entry"
)
_FLEET_REVIEW_CLASSIFY = "sd-ai-command-pack-fleet-review-classify.py"

PLUGIN_CLOSURE_ALLOWLIST: dict[tuple[str, str], str] = {
    ("skills/sd-review-pr/SKILL.md", _FLEET_REVIEW_CLASSIFY): (
        _FLEET_REVIEW_CLASSIFY_JUSTIFICATION
    ),
}

MACHINE_CLOSURE_ALLOWLIST: dict[tuple[str, str], str] = {
    (".agents/skills/sd-review-pr/SKILL.md", _FLEET_REVIEW_CLASSIFY): (
        _FLEET_REVIEW_CLASSIFY_JUSTIFICATION
    ),
}

# payload-relative text file -> (justification, script names that are not
# references to a relocated copy and therefore keep their repository path).
MACHINE_REFERENCE_EXEMPTIONS: dict[str, tuple[str, frozenset[str]]] = {
    PACK_DOC_REFERENCE: (
        "pack-source-only fleet tooling: the reference manual documents these "
        "scripts as source-only (one of them through a GitHub hyperlink), and "
        "they have no manifest row, so the pack source repository's path is "
        "where they actually live; rewriting would assert a machine location "
        "that never exists",
        frozenset(
            {
                "sd-ai-command-pack-fleet-controller.py",
                "sd-ai-command-pack-fleet-finding-classify.py",
                "sd-ai-command-pack-fleet-preflight.py",
                "sd-ai-command-pack-fleet-timing.py",
                "sd-ai-command-pack-fleet-wave-plan.py",
            }
        ),
    ),
}


@dataclass(frozen=True)
class RewriteProfile:
    """Where one payload relocates pack resources, and how it says so.

    `script_template` is formatted with `name`; `doc_template` is the literal
    replacement, or None for a payload that does not relocate the reference
    manual (the plugin does not carry it).
    """

    name: str
    script_template: str
    doc_template: str | None
    strip_node_prefix: bool
    residue_advice: str
    closure_subject: str
    closure_advice: str
    exemptions: Mapping[str, tuple[str, frozenset[str]]] = field(
        default_factory=dict
    )
    # Literal -> replacement, applied before the script and doc rules.
    #
    # Globs are here rather than in `SCRIPT_REFERENCE_RE` because they are not
    # script names: `_PACK_SCRIPT_NAME` requires a real `.py`/`.sh`/`.mjs`
    # ending, and `scripts/sd-ai-command-pack-*` has none. Widening that
    # pattern to accept `*` would also make it match inside the residue and
    # closure gates, which reason about names a payload either ships or does
    # not -- a glob is neither. Keeping them as literal pairs means each one is
    # written down, reviewable, and retired individually.
    literal_rewrites: Mapping[str, str] = field(default_factory=dict)


PLUGIN_PROFILE = RewriteProfile(
    name="plugin",
    script_template="{name}",
    doc_template=None,
    strip_node_prefix=True,
    residue_advice=(
        "the plugin ships no repository-root scripts/ directory, so extend the "
        "rewrite rules in .github/scripts/generate-plugin.py"
    ),
    closure_subject="which the plugin does not ship in bin/",
    closure_advice=(
        "add the script to the manifest, or record the reference in "
        "CLOSURE_ALLOWLIST with a written justification"
    ),
)

# The reference manual's relocated form, for text that a resweep reads.
#
# `MACHINE_PROFILE` says `~/.agents/docs/SD_AI_COMMAND_PACK.md`, which is the
# true location and is nonetheless wrong here. `cites_removed_path` matches
# path *suffixes* (thin-resweep.py:1225), so that string ends with the removed
# `docs/SD_AI_COMMAND_PACK.md` and is classified as a citation of it. The
# machine payload gets away with it because payload files are never scanned; a
# converted consumer's own files are. Naming the directory and leaving the file
# to prose is what clears the rule -- `~/.agents/docs` has no removed suffix.
AGENTS_DOC_DIRECTORY = "~/.agents/docs"
# The replacement is a bare path, carrying no Markdown of its own. Every
# occurrence being replaced already sits inside a code span, so a replacement
# containing backticks nests them and renders as literal backticks. It names
# the directory rather than the file for the suffix reason above; the manual is
# the only pack document there, and the surrounding prose already says so.
THIN_DOC_REFERENCE = AGENTS_DOC_DIRECTORY

THIN_PROFILE = RewriteProfile(
    name="thin",
    script_template=f"{AGENTS_BIN_REFERENCE}/{{name}}",
    doc_template=THIN_DOC_REFERENCE,
    strip_node_prefix=False,
    residue_advice=(
        "a converted consumer keeps this file but not the repository-root "
        f"scripts/ directory, so the reference must name {AGENTS_BIN_REFERENCE} "
        "instead; extend the rewrite rules in installer/references.py"
    ),
    closure_subject=(
        f"which a thin consumer does not have at {AGENTS_BIN_REFERENCE}"
    ),
    closure_advice=(
        "add the script to the manifest, or record the reference in "
        "THIN_CLOSURE_ALLOWLIST with a written justification"
    ),
    # The three globs in the Copilot managed block. A conversion removes the
    # whole population each one selects, and the resweep calls a glob broken
    # exactly when nothing it selects survives (thin-resweep.py:1218). So they
    # cannot be aimed at another repository directory -- there is no surviving
    # pack tree in the repository to aim at. Each is replaced by the location
    # that does survive, outside the repository.
    literal_rewrites={
        "`.agents/skills/sd-*/SKILL.md`": "`~/.agents/skills/sd-*/SKILL.md`",
        "`**/skills/trellis-*/**` and `**/skills/sd-*/**` under `.agents/`,": (
            "`**/skills/trellis-*/**` under `.agents/` (pack skills are not "
            "vendored in a thin checkout; they live at `~/.agents/skills`),"
        ),
        "`scripts/sd-ai-command-pack-*`, legacy `scripts/trellis-*.sh`, and": (
            "legacy `scripts/trellis-*.sh` and"
        ),
    },
)

THIN_CLOSURE_ALLOWLIST: dict[tuple[str, str], str] = {}

MACHINE_PROFILE = RewriteProfile(
    name="machine",
    script_template=f"{AGENTS_BIN_REFERENCE}/{{name}}",
    doc_template=AGENTS_DOC_REFERENCE,
    strip_node_prefix=False,
    residue_advice=(
        f"the machine payload installs pack scripts to {AGENTS_BIN_REFERENCE} "
        f"and the reference manual to {AGENTS_DOC_REFERENCE}, so extend the "
        "rewrite rules in installer/references.py, or record the literal in "
        "MACHINE_REFERENCE_EXEMPTIONS with a written justification if it names "
        "the pack source repository on purpose"
    ),
    closure_subject=(
        f"which the machine payload does not install to {AGENTS_BIN_REFERENCE}"
    ),
    closure_advice=(
        "add the script to the manifest, or record the reference in "
        "MACHINE_CLOSURE_ALLOWLIST with a written justification"
    ),
    exemptions=MACHINE_REFERENCE_EXEMPTIONS,
)


def exempt_names(profile: RewriteProfile, key: str) -> frozenset[str]:
    """Names this file may keep unrewritten, once the exemption is justified."""

    justification, names = profile.exemptions.get(key, ("", frozenset()))
    if names and not justification:
        raise ReferenceRewriteError(
            f"reference exemption for {key} has no justification"
        )
    return names


def rewrite_text(text: str, *, profile: RewriteProfile, key: str = "") -> str:
    """Point every relocated-resource reference at where the payload puts it."""

    exempt = exempt_names(profile, key)

    for literal, replacement in profile.literal_rewrites.items():
        text = text.replace(literal, replacement)

    def replace_script(match: re.Match[str]) -> str:
        name = match.group(1)
        if name in exempt:
            return match.group(0)
        return profile.script_template.format(name=name)

    rewritten = SCRIPT_REFERENCE_RE.sub(replace_script, text)
    doc_template = profile.doc_template
    if doc_template is not None and PACK_DOC_REFERENCE not in exempt:
        rewritten = DOC_REFERENCE_RE.sub(lambda _match: doc_template, rewritten)
    if profile.strip_node_prefix:
        rewritten = NODE_PREFIX_RE.sub(r"\1", rewritten)
    return rewritten


def _wrapped_pairs(text: str, directory: str, pattern: re.Pattern[str]) -> list[str]:
    """Wrapped references, skipping the ones that are directory listings.

    A `scripts/` line carrying nothing else is a tree above its contents, not
    an invocation that ran out of room, and reporting it would make writing a
    file listing impossible.
    """

    pairs = []
    for match in pattern.finditer(text):
        lead = text[text.rfind("\n", 0, match.start()) + 1 : match.start()]
        if lead.strip():
            pairs.append(f"{directory}/ + {match.group(1)}")
    return pairs


def check_wrapped_references(
    key: str, text: str, *, profile: RewriteProfile
) -> None:
    """A reference split across a line break is invisible to every other gate.

    Exemptions are not consulted: they name a script, and a wrapped occurrence
    is exactly the case where no gate can see the name. Joining the line puts
    the reference back in front of the rewrite, which then honors whatever the
    exemption says about it.
    """

    wrapped = _wrapped_pairs(text, "scripts", _WRAPPED_SCRIPT_RE)
    if profile.doc_template is not None:
        wrapped.extend(_wrapped_pairs(text, "docs", _WRAPPED_DOC_RE))
    if wrapped:
        raise ReferenceRewriteError(
            f"line-wrapped reference in {key}: "
            + ", ".join(sorted(set(wrapped)))
            + "; join the line so the rewrite and the residue gate can both see it"
        )


def check_text_residue(key: str, text: str, *, profile: RewriteProfile) -> None:
    """No rewritten text file may still name a repository-root pack resource."""

    check_wrapped_references(key, text, profile=profile)
    exempt = exempt_names(profile, key)
    found = {match.rstrip(".") for match in RESIDUE_RE.findall(text)}
    residue = sorted(
        literal
        for literal in found
        if literal.removeprefix(_RESIDUE_PREFIX) not in exempt
    )
    doc_template = profile.doc_template
    if doc_template is not None and PACK_DOC_REFERENCE not in exempt:
        # The relocated form contains the repository-root form as a substring,
        # so a rewritten reference would report itself as residue. Mask the
        # replacement rather than narrowing the pattern, which would also stop
        # it seeing the hyperlink form the rewrite deliberately leaves alone.
        scanned = text.replace(doc_template, "")
        residue.extend(sorted(set(DOC_RESIDUE_RE.findall(scanned))))
    if residue:
        raise ReferenceRewriteError(
            f"rewrite residue in {key}: "
            + ", ".join(residue)
            + "; "
            + profile.residue_advice
        )


def check_executable_residue(
    label: str,
    text: str,
    *,
    allowlist: Mapping[str, tuple[str, frozenset[str]]],
    name: str,
) -> None:
    """An executable keeps only the repository-root literals it can justify."""

    justification, allowed = allowlist.get(name, ("", frozenset()))
    found = {match.rstrip(".") for match in RESIDUE_RE.findall(text)}
    unexpected = sorted(found - allowed)
    if unexpected:
        raise ReferenceRewriteError(
            f"repository-root pack paths in {label}: "
            + ", ".join(unexpected)
            + "; convert functional sibling resolution to own-location "
            "resolution, or add the literal to BIN_LITERAL_ALLOWLIST "
            "with a written justification if it is layout data"
        )
    if allowed and not justification:
        raise ReferenceRewriteError(
            f"BIN_LITERAL_ALLOWLIST entry for {name} has no justification"
        )


def check_closure(
    key: str,
    text: str,
    *,
    profile: RewriteProfile,
    shipped_commands: frozenset[str],
    shipped_docs: frozenset[str],
    allowlist: Mapping[tuple[str, str], str],
) -> None:
    """Every relocated resource a text file names must travel with it."""

    exempt = exempt_names(profile, key)
    for command in sorted(set(BARE_COMMAND_RE.findall(text))):
        if command in shipped_commands or command in exempt:
            continue
        if not allowlist.get((key, command)):
            raise ReferenceRewriteError(
                f"{key} references {command}, {profile.closure_subject}; "
                + profile.closure_advice
            )
    doc_template = profile.doc_template
    if doc_template is not None and doc_template in text:
        if PACK_DOC_NAME not in shipped_docs:
            raise ReferenceRewriteError(
                f"{key} references {doc_template}, which the payload does not "
                "install; add the reference manual to the payload, or drop the "
                "reference"
            )


__all__ = [
    "AGENTS_BIN_REFERENCE",
    "AGENTS_DOC_DIRECTORY",
    "AGENTS_DOC_REFERENCE",
    "BARE_COMMAND_RE",
    "BIN_LITERAL_ALLOWLIST",
    "DOC_REFERENCE_RE",
    "DOC_RESIDUE_RE",
    "MACHINE_CLOSURE_ALLOWLIST",
    "MACHINE_PROFILE",
    "MACHINE_REFERENCE_EXEMPTIONS",
    "NODE_PREFIX_RE",
    "PACK_DOC_NAME",
    "PACK_DOC_REFERENCE",
    "PLUGIN_CLOSURE_ALLOWLIST",
    "PLUGIN_PROFILE",
    "RESIDUE_RE",
    "SCRIPT_REFERENCE_RE",
    "ReferenceRewriteError",
    "RewriteProfile",
    "THIN_CLOSURE_ALLOWLIST",
    "THIN_DOC_REFERENCE",
    "THIN_PROFILE",
    "check_closure",
    "check_executable_residue",
    "check_text_residue",
    "check_wrapped_references",
    "exempt_names",
    "rewrite_text",
]
