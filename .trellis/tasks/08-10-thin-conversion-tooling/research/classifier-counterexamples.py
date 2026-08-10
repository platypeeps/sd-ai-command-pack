#!/usr/bin/env python3
"""Every counterexample the classification rule has been wrong about.

Nine adversarial review rounds produced a list of cases where an earlier
version of ``fleet-blocker-scan.py`` gave the wrong answer. Until round 9 that
list lived only in review prose, which meant "all counterexamples still pass"
was re-established by hand each round and could not survive a context break.
This file is that list, executable.

Two kinds of assertion:

* **Fleet** -- a real (consumer, file, line) whose bucket is asserted against a
  scan result. These are the measured cases; each names the round that found
  it. They depend on the consumer checkouts being present at the heads the scan
  recorded, so a mismatch is reported as ``skipped`` rather than silently
  passing.
* **Unit** -- a direct assertion on one classifier predicate, for cases whose
  point is the rule itself rather than a place it fires.

Run after any scanner change::

    .venv/bin/python .trellis/tasks/08-10-thin-conversion-tooling/research/\
classifier-counterexamples.py --scan /path/to/fleet-blocker-scan.json

Exit status is 0 only when every assertion passes and none was skipped.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCANNER = HERE / "fleet-blocker-scan.py"
REGISTRY = HERE.parents[3] / "docs/fleet/consumers.json"
DEFAULT_SCAN = HERE / "fleet-blocker-scan.json"


def load_scanner():
    spec = importlib.util.spec_from_file_location("fleet_blocker_scan", SCANNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# (consumer, file, line, expected bucket, round, why)
#
# `None` as the bucket means "in no bucket at all" -- the false-positive
# guards, where the whole point is that nothing fires.
FLEET_CASES: list[tuple[str, str, int | None, str | None, str, str]] = [
    (
        "rwbp-coordinator",
        ".github/prompts/sd-housekeeping.prompt.md",
        37,
        "packDefects",
        "W-1",
        "agent-executed pack surface telling an agent to run a removed script; "
        "the root-anchored directory allowlist called it advisory",
    ),
    (
        "rwbp-coordinator",
        ".github/prompts/sd-housekeeping.prompt.md",
        38,
        "packDefects",
        "W-1",
        "second hit in the same prompt",
    ),
    (
        "loadsmith",
        ".github/workflows/ci.yml",
        151,
        "blockers",
        "W-3",
        "addresses the removed population as scripts/sd-ai-command-pack-*.sh, "
        "naming no exact path and no basename",
    ),
    (
        "se-ai-command-pack",
        "repomix.config.json",
        57,
        "advisories",
        "W-3",
        "same glob form in a config file: detected, but a data file with no "
        "command context is advisory, not a blocker",
    ),
    (
        "sd-github-review",
        "test/metadata.test.js",
        490,
        "blockers",
        "H-0",
        "names .agents/skills/sd-status/SKILL.md without the pack name "
        "anywhere on the line -- invisible to a pack-name search",
    ),
    (
        "mezmo_benchmark",
        "CLAUDE.md",
        28,
        "blockers",
        "W-1",
        "root agent instruction file is an execution surface by proxy",
    ),
    (
        "anomaly-metric-creator",
        ".trellis/spec/amc/backend/testing-quality.md",
        288,
        "blockers",
        "R7-1",
        "imperative guidance -- 'Use `scripts/...` as the local review gate' -- "
        "with no runner token on the line",
    ),
    (
        "mezmo_benchmark",
        ".trellis/tasks/07-02-audit-s3-iam-runscope-kms/implement.md",
        83,
        "blockers",
        "R7-2",
        "unarchived task plan is a live plan; only archive/ is historical",
    ),
    (
        "rwbp-website",
        ".gitignore",
        165,
        "advisories",
        "R7-3",
        "'# Python bytecode from scripts/*.py' is a comment; the "
        "case-insensitive interpreter rule made it a blocker",
    ),
    (
        "hoa-manager",
        "scripts/update_repomix",
        8,
        None,
        "R7-4",
        "INCLUDE_PATTERNS globs keep selecting surviving files, so the script "
        "still works and needs no repoint",
    ),
    (
        "rwbp-website",
        ".gitignore",
        170,
        "packDefects",
        "R8-1/R8-2",
        "sentence-final citation inside the surviving obsidian-kb block: the "
        "period hid it entirely, then file-keyed block ownership called it "
        "scheduled",
    ),
    (
        "mezmo_benchmark",
        ".trellis/tasks/archive/2026-07/07-02-audit-adapter-retry-backoff/implement.md",
        81,
        "advisories",
        "R7-2/H10-5",
        "an archived task plan carries `bash scripts/<removed>.sh` in plain "
        "command position: advisory only because the archive prefix is "
        "historical. Mutation-testing found no fixture exercised that rule -- "
        "the review-learnings case stopped depending on it once R8-4 landed",
    ),
    (
        "anomaly-metric-creator",
        "docs/review-learnings.md",
        22,
        "advisories",
        "R8-4",
        "quoted review prose about a $((delay * 2)) defect is a record of "
        "something said, not an instruction",
    ),
    (
        "se-ai-command-pack",
        "templates/skills/se-help/SKILL.md",
        51,
        None,
        "U-2",
        "'Read `references/examples.md`' names its own sibling; matching it to "
        "a removed path elsewhere refused a conversion that should proceed",
    ),
    (
        "se-ai-command-pack",
        "templates/skills/se-author/SKILL.md",
        74,
        None,
        "R9-3",
        "'`review.md`: findings, decisions' names a runtime workspace artifact; "
        "the unambiguous-basename rule matched .claude/commands/sd/review.md",
    ),
    (
        "rwbp-coordinator",
        ".github/PULL_REQUEST_TEMPLATE.md",
        7,
        "packDefects",
        "V-2/H10-6",
        "force-preserved, so provenance never vouches it; ownership is decided "
        "by comparing the consumer's bytes against the pack's shipped "
        "template. Mutation-testing found no fixture exercised that proof",
    ),
    (
        "sd-github-review",
        ".github/PULL_REQUEST_TEMPLATE.md",
        15,
        "blockers",
        "V-2/H10-6",
        "the same file edited by the consumer: bytes differ from the shipped "
        "template, so it is consumer-owned and its stale command is theirs to "
        "fix. The two rows together are what make the proof falsifiable",
    ),
    (
        "loadsmith",
        "docs/repomix-map.md",
        1388,
        "blockers",
        "R11-C2",
        "`scripts/sd-ai-command-pack-check.py --json` sits on a shell "
        "continuation inside a ```bash fence. It carries no command token of "
        "its own; disabling either fence or continuation recognition loses it",
    ),
    (
        "sd-github-review",
        ".trellis/tasks/08-09-review-coordinator-stale-check/implement.md",
        139,
        "blockers",
        "R11-C2",
        "the same shape in a second consumer and a different file type, which "
        "is how the fleet writes nearly every long invocation",
    ),
    (
        "loadsmith",
        ".sd-ai-command-pack/manifest.json",
        None,
        "scheduled",
        "R11-C2",
        "generated bookkeeping: the manifest names every shipped target, so "
        "classifying it line-by-line produces 1055 citations per consumer, 93% "
        "of every advisory list. Reverting the rule moved `scheduled` from 182 "
        "to 179 and failed nothing",
    ),
    (
        "rwbp-coordinator",
        ".prism/rules.json",
        55,
        "blockers",
        "R10-C6",
        "a live Prism *required* rule naming three removed paths. A .json "
        "suffix reads as inert data while the contents are rules an agent "
        "obeys; it sat in advisories for ten rounds",
    ),
    (
        "se-ai-command-pack",
        ".prism/rules.json",
        43,
        "blockers",
        "R10-C6",
        "the same surface in a second consumer, naming "
        "scripts/sd-ai-command-pack-review-preflight.mjs. Two rows because one "
        "consumer's drift could be dismissed as that consumer's alone",
    ),
    (
        "rwbp-coordinator",
        ".github/copilot-instructions.md",
        26,
        "packDefects",
        "R9-2",
        "the pack's own managed block cites .agents/skills/sd-*/SKILL.md, a "
        "glob whose whole population the conversion removes; the discovery "
        "prefilter hid it for eight rounds",
    ),
]


def symlink_cases(module) -> list[tuple[str, str, object, object]]:
    """R9-C4: link forms that round 8 skipped instead of failing closed."""
    with tempfile.TemporaryDirectory() as raw:
        repo = Path(raw).resolve()
        (repo / "scripts").mkdir()
        (repo / "scripts/removed.sh").write_text("#!/bin/sh\n", encoding="utf-8")
        os.symlink(repo / "scripts/removed.sh", repo / "absolute-link")
        os.symlink("absolute-link", repo / "chained-link")
        os.symlink("/etc/hosts", repo / "outside-link")
        os.symlink("cycle-b", repo / "cycle-a")
        os.symlink("cycle-a", repo / "cycle-b")
        os.symlink("scripts/removed.sh", repo / "relative-link")
        # R10-C4: the failing shape was never a symlinked *leaf*. `alias` is a
        # symlinked directory, so `alias/full-check.sh` is a regular file and
        # the old lexical walk returned it verbatim -- naming a path the
        # removal set does not contain, and missing the removed one it
        # ultimately reaches.
        os.symlink("scripts", repo / "alias")
        os.symlink("alias/removed.sh", repo / "through-directory")
        os.symlink("scripts/never-existed.sh", repo / "broken-link")
        resolve = module.resolve_link
        return [
            (
                "R9-C4",
                "an absolute target inside the repository resolves",
                resolve(repo, "absolute-link"),
                "scripts/removed.sh",
            ),
            (
                "R9-C4",
                "a chain of links resolves to its end",
                resolve(repo, "chained-link"),
                "scripts/removed.sh",
            ),
            (
                "R8-6",
                "a relative target still resolves",
                resolve(repo, "relative-link"),
                "scripts/removed.sh",
            ),
            (
                "R9-C4",
                "a target outside the repository is unresolvable",
                resolve(repo, "outside-link"),
                None,
            ),
            (
                "R9-C4",
                "a cycle is unresolvable rather than an infinite loop",
                resolve(repo, "cycle-a"),
                None,
            ),
            (
                "R10-C4",
                "a link through a symlinked directory resolves to the real path",
                resolve(repo, "through-directory"),
                "scripts/removed.sh",
            ),
            (
                "R10-C4",
                "a broken chain is unresolvable, not its lexical target",
                resolve(repo, "broken-link"),
                None,
            ),
        ]


def enumeration_cases(module) -> list[tuple[str, str, object, object]]:
    """R11-C2: which files the scan is even allowed to see."""
    with tempfile.TemporaryDirectory() as raw:
        repo = Path(raw).resolve()
        for args in (
            ("init", "-q"),
            ("config", "user.email", "harness@example.invalid"),
            ("config", "user.name", "harness"),
        ):
            subprocess.run(
                ["git", "-C", str(repo), *args], check=True, capture_output=True
            )
        (repo / "tracked.sh").write_text("#!/bin/sh\n", encoding="utf-8")
        (repo / ".gitignore").write_text("ignored.sh\n", encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(repo), "add", "tracked.sh", ".gitignore"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-qm", "seed"],
            check=True,
            capture_output=True,
        )
        # Untracked and non-ignored: the conversion runs against the working
        # tree, so this file breaks exactly as hard as a committed one. Six
        # real `se-ai-command-pack` blockers lived in files like it.
        (repo / "untracked.sh").write_text("#!/bin/sh\n", encoding="utf-8")
        # Ignored: bound by `receiptOccupancyDigest` where it matters, and not
        # part of a conversion PR.
        (repo / "ignored.sh").write_text("#!/bin/sh\n", encoding="utf-8")
        found = set(module.enumerate_files(repo))
    return [
        (
            "R11-C2",
            "a tracked file is enumerated",
            "tracked.sh" in found,
            True,
        ),
        (
            "H10-1/R11-C2",
            "an untracked, non-ignored file is enumerated",
            "untracked.sh" in found,
            True,
        ),
        (
            "H10-1",
            "an ignored file is not",
            "ignored.sh" in found,
            False,
        ),
    ]


def bytes_cases(module) -> list[tuple[str, str, object, object]]:
    """R10-C5 and R10-C3: rules about bytes the scanner might never read."""
    cases: list[tuple[str, str, object, object]] = [
        (
            "R10-C5",
            "a NUL-bearing asset is binary",
            module.is_binary(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"),
            True,
        ),
        (
            "R10-C5",
            "a shell script with a Latin-1 comment is not binary",
            module.is_binary(
                "# r\N{LATIN SMALL LETTER E WITH ACUTE}sum\n"
                "bash scripts/sd-ai-command-pack-full-check.sh\n".encode("latin-1")
            ),
            False,
        ),
        (
            "R10-C5",
            "plain ASCII is not binary",
            module.is_binary(b"bash scripts/sd-ai-command-pack-full-check.sh\n"),
            False,
        ),
    ]

    with tempfile.TemporaryDirectory() as raw:
        repo = Path(raw).resolve()
        for args in (
            ("init", "-q"),
            ("config", "user.email", "harness@example.invalid"),
            ("config", "user.name", "harness"),
        ):
            subprocess.run(
                ["git", "-C", str(repo), *args], check=True, capture_output=True
            )
        hidden = repo / "hidden.sh"
        hidden.write_text("#!/bin/sh\necho before\n", encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(repo), "add", "hidden.sh"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-qm", "seed"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "update-index", "--skip-worktree", "hidden.sh"],
            check=True,
            capture_output=True,
        )
        flags = subprocess.run(
            ["git", "-C", str(repo), "ls-files", "-v"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        before = module.hidden_bytes_digest(repo, flags)
        # The whole point of the flag: this rewrite is invisible to `git
        # status`, `git ls-files -s`, and `git ls-files -v` alike.
        hidden.write_text(
            "#!/bin/sh\nbash scripts/sd-ai-command-pack-full-check.sh\n",
            encoding="utf-8",
        )
        after_flags = subprocess.run(
            ["git", "-C", str(repo), "ls-files", "-v"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        status = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        after = module.hidden_bytes_digest(repo, after_flags)
        cases += [
            (
                "R10-C3",
                "a skip-worktree rewrite is invisible to git status",
                status.strip(),
                "",
            ),
            (
                "R10-C3",
                "a skip-worktree rewrite is invisible to `git ls-files -v`",
                after_flags,
                flags,
            ),
            (
                "R10-C3",
                "a skip-worktree rewrite still moves hiddenBytesDigest",
                before != after,
                True,
            ),
        ]
    return cases


def unit_cases(module) -> list[tuple[str, str, bool, bool]]:
    """(round, description, actual, expected) for predicate-level cases."""
    registry_module = importlib.import_module("installer.registry")
    removed = frozenset(
        {
            "scripts/sd-ai-command-pack-full-check.sh",
            "scripts/sd_ai_command_pack_lib.py",
            "docs/SD_AI_COMMAND_PACK.md",
            ".agents/skills/sd-status/SKILL.md",
            ".claude/commands/sd/review.md",
            # R10-C2: without the colliding path in the removal set, the U-2
            # case below passed whether or not bare-suffix guessing was
            # restored -- there was nothing for a bad rule to collide with.
            ".agents/skills/sd-help/references/examples.md",
        }
    )
    # H10-2: `docs/review.md` used to be here, which made the R9-3 case
    # tautological -- a surviving `review.md` excluded the basename from
    # `unambiguous` regardless of the pack-name rule, so reverting R9-3 left
    # this harness green. The survivor set must not contain the basename the
    # case is about.
    survivors = frozenset({"README.md", "docs/notes.md", "scripts/local.sh"})
    unambiguous = module.unambiguous_basenames(removed, survivors)
    repo = Path("/nonexistent")

    def cites(token: str, relative_to: str = "README.md") -> bool:
        return module.cites_removed_path(
            token, removed, repo, relative_to, survivors, unambiguous
        )

    def commanded(line: str) -> bool:
        return bool(module.COMMAND_CONTEXT.search(line))

    return [
        (
            "R8-1",
            "a removed path at the end of a sentence keeps its period",
            cites("scripts/sd-ai-command-pack-full-check.sh."),
            True,
        ),
        (
            "R8-1",
            "a version number is not a path",
            cites("1.2.3."),
            False,
        ),
        (
            "R9-1",
            "a URL that ends in a removed path names a host, not a file",
            cites("//example.com/docs/SD_AI_COMMAND_PACK.md"),
            False,
        ),
        (
            "R8-5",
            "a distinctive bare basename resolves",
            cites("sd_ai_command_pack_lib.py"),
            True,
        ),
        (
            "R9-3",
            "an undistinctive bare basename does not",
            cites("review.md"),
            False,
        ),
        (
            "U-2",
            "a sibling-relative reference is not evidence about a path "
            "elsewhere in the tree",
            cites("references/examples.md", ".agents/skills/se-help/SKILL.md"),
            False,
        ),
        (
            "H-3",
            "the English word Python is not an interpreter invocation",
            commanded("# Python bytecode from scripts/*.py"),
            False,
        ),
        (
            "H-3",
            "a real interpreter invocation still matches",
            commanded("python3 scripts/sd-ai-command-pack-full-check.sh"),
            True,
        ),
        (
            "H-3/H10-4",
            "a capitalised runner word in prose is not an invocation",
            # The round-7 line this rule was written for -- "# Python bytecode
            # from scripts/*.py" -- stopped matching for a second reason (its
            # argument is not path-shaped), so it no longer exercises the
            # case-sensitivity itself. Mutation-testing caught that: reverting
            # `(?-i:` left the whole harness green. This line has a path-shaped
            # argument and fails only on case.
            commanded("Make ./scripts/sd-ai-command-pack-full-check.sh executable"),
            False,
        ),
        (
            "H-3/H10-4",
            "the same runner lowercase, with a path, is an invocation",
            commanded("make -f scripts/sd-ai-command-pack-full-check.sh all"),
            True,
        ),
        (
            "R9-C5",
            "a no-argument command substitution is still a command",
            commanded('tool="$(pwd)/scripts/sd-ai-command-pack-full-check.sh"'),
            True,
        ),
        (
            "R8-4",
            "quoted arithmetic expansion is not command substitution",
            commanded("PR #232 `scripts/x.sh`: `$((delay * 2))` overflows"),
            False,
        ),
        (
            "R7-1",
            "imperative guidance naming a runnable file is command context",
            commanded("Use `scripts/sd-ai-command-pack-full-check.sh` as the gate"),
            True,
        ),
        (
            "W-1",
            "a nested scripts/ path is an execution surface",
            module.is_executable_surface(
                HERE, "templates/skills/se-review-skills/scripts/skill_review.py"
            ),
            True,
        ),
        (
            "W-1",
            "a plain README is not",
            module.is_executable_surface(HERE, "docs/README.md"),
            False,
        ),
        (
            "R11-C2",
            "a runnable fence puts its lines in command position",
            module.command_lines(["```bash", "scripts/x.sh", "```"]) == {2},
            True,
        ),
        (
            "R11-C2",
            "a non-runnable fence does not",
            module.command_lines(["```json", '{"a": 1}', "```"]) == set(),
            True,
        ),
        (
            "R11-C2",
            "a shell continuation carries command position to the next line",
            module.command_lines(["bash toolchain.sh run-python -- \\", "  scripts/x.py"])
            == {2},
            True,
        ),
        (
            "R11-C2",
            "a trailing backslash after prose is not a continuation",
            module.command_lines(["a table cell ending in \\", "  scripts/x.py"]),
            set(),
        ),
        (
            "R11-C4",
            "the OpenCode command namespace is the registry's, plural",
            module.is_executable_surface(HERE, ".opencode/commands/custom.md"),
            True,
        ),
        (
            "R11-C4",
            "a platform absent from the old hand-written list is covered",
            module.is_executable_surface(HERE, ".zcode/commands/custom.md"),
            True,
        ),
        (
            "R11-C4",
            "every platform directory the registry defines has a prefix",
            sorted(
                info.directory
                for info in registry_module.PLATFORM_REGISTRY.values()
                if info.directory != ".github"
                and not any(
                    prefix == f"{info.directory}/"
                    for prefix in module.EXECUTABLE_PREFIXES
                )
            ),
            [],
        ),
        (
            "U-3/R7-6",
            "a repeated marker label is unresolvable ownership, not two blocks",
            module.block_spans(
                [
                    "# sd-ai-command-pack trellis-gitignore start",
                    "a",
                    "# sd-ai-command-pack trellis-gitignore end",
                    "# sd-ai-command-pack trellis-gitignore start",
                    "b",
                    "# sd-ai-command-pack trellis-gitignore end",
                ]
            )
            is None,
            True,
        ),
        (
            "R8-2",
            "two different pack labels in one file are two spans",
            len(
                module.block_spans(
                    [
                        "# sd-ai-command-pack trellis-gitignore start",
                        "a",
                        "# sd-ai-command-pack trellis-gitignore end",
                        "# sd-ai-command-pack obsidian-kb start",
                        "b",
                        "# sd-ai-command-pack obsidian-kb end",
                    ]
                )
                or []
            )
            == 2,
            True,
        ),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan", type=Path, default=DEFAULT_SCAN)
    args = parser.parse_args()

    module = load_scanner()
    failures: list[str] = []
    skipped: list[str] = []
    passed = 0

    for round_id, description, actual, expected in (
        unit_cases(module)
        + symlink_cases(module)
        + bytes_cases(module)
        + enumeration_cases(module)
    ):
        if actual == expected:
            passed += 1
        else:
            failures.append(f"unit  {round_id}: {description} -> {actual!r}")

    # R11-C1/R11-C2, both demonstrated. Two rounds tried to make a stored
    # result trustworthy -- H10-3 pinned the scanner's bytes, R10-C1 checked
    # each consumer's HEAD -- and a stored result still is not evidence about
    # the scanner on disk. Codex swapped one consumer's fresh row for the
    # committed one: same HEAD, 23 blockers recorded against 29 present, and
    # all 40 cases passed, because six of the missing ones live in *untracked*
    # files that no recorded binding covers. Reverting five separate scanner
    # rules likewise left the harness green.
    #
    # So the fleet cases no longer read a stored row. They call `scan()` on the
    # consumer, now, in this process, with the scanner that is on disk. There
    # is nothing left to go stale: the binding fields exist to make the
    # committed measurement re-derivable, not to certify a cached assertion.
    # The cost is about 11 seconds fleet-wide.
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    platforms = {
        entry["name"]: (Path(os.path.expanduser(entry["pathHint"])), entry["platforms"])
        for entry in registry["consumers"]
    }
    named = {case[0] for case in FLEET_CASES}
    rows: dict[str, dict] = {}
    for consumer in sorted(named):
        if consumer not in platforms:
            continue
        repo, consumer_platforms = platforms[consumer]
        if not repo.is_dir():
            continue
        rows[consumer] = module.scan(consumer, repo, frozenset(consumer_platforms))

    # The committed scan is still read, for one purpose: to say out loud when
    # the numbers in the planning artifacts were produced by different bytes
    # than the ones just asserted against.
    if args.scan.exists():
        stored = json.loads(args.scan.read_text(encoding="utf-8"))
        current = module.file_digest(SCANNER)
        if stored.get("scannerDigest") != current:
            skipped.append(
                f"committed scan {args.scan} came from a different scanner "
                f"({stored.get('scannerDigest')} != {current}); the assertions "
                "below ran live, but the artifacts' figures are stale"
            )
    buckets = ("blockers", "packDefects", "scheduled", "advisories")

    for consumer, relative, line, expected, round_id, why in FLEET_CASES:
        row = rows.get(consumer)
        if row is None or "error" in row:
            skipped.append(f"fleet {round_id}: {consumer} checkout unavailable")
            continue
        # R10-C2: a negative case names a file that must exist for its absence
        # from every bucket to mean anything. `.agents/skills/se-help/SKILL.md`
        # did not exist at the recorded head -- the real counterexample is
        # `templates/skills/se-help/SKILL.md` -- so the assertion passed by
        # naming nothing at all, for two rounds.
        repo = Path(row["repo"])
        full = repo / relative
        if not full.exists():
            failures.append(
                f"fleet {round_id}: {consumer}/{relative} does not exist; a "
                "case that names no file asserts nothing"
            )
            continue
        # R11-C2: and the *line* must exist too. Codex moved a negative case's
        # cited line to 999999 and the harness stayed green: "no bucket holds
        # this file at this line" is trivially true of a line that is not
        # there. Existence of the file was the same argument one level up.
        if line is not None:
            try:
                present = len(full.read_bytes().split(b"\n"))
            except OSError:
                present = 0
            if line > present:
                failures.append(
                    f"fleet {round_id}: {consumer}/{relative} has {present} "
                    f"lines; line {line} does not exist, so the case asserts "
                    "nothing"
                )
                continue
        found = {
            bucket
            for bucket in buckets
            for entry in row[bucket]
            if entry["file"] == relative and (line is None or entry["line"] == line)
        }
        where = f"{consumer}/{relative}" + (f":{line}" if line is not None else "")
        if expected is None:
            if found:
                failures.append(
                    f"fleet {round_id}: {where} should be in no bucket, "
                    f"found {sorted(found)} -- {why}"
                )
            else:
                passed += 1
        elif found == {expected}:
            passed += 1
        else:
            failures.append(
                f"fleet {round_id}: {where} expected {expected}, "
                f"found {sorted(found) or 'nothing'} -- {why}"
            )

    for failure in failures:
        print(f"FAIL {failure}")
    for entry in skipped:
        print(f"SKIP {entry}")
    print(
        f"{passed} passed, {len(failures)} failed, {len(skipped)} skipped "
        f"({len(FLEET_CASES)} fleet + "
        f"{len(unit_cases(module)) + len(symlink_cases(module)) + len(bytes_cases(module)) + len(enumeration_cases(module))}"
        " unit)"
    )
    return 1 if failures or skipped else 0


if __name__ == "__main__":
    raise SystemExit(main())
