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
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCANNER = HERE / "fleet-blocker-scan.py"
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
        None,
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
        ".agents/skills/se-help/SKILL.md",
        None,
        None,
        "U-2",
        "'Read `references/examples.md`' names its own sibling; matching it to "
        "a removed path elsewhere refused a conversion that should proceed",
    ),
    (
        "se-ai-command-pack",
        "templates/skills/se-author/SKILL.md",
        None,
        None,
        "R9-3",
        "'`review.md`: findings, decisions' names a runtime workspace artifact; "
        "the unambiguous-basename rule matched .claude/commands/sd/review.md",
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
        ]


def unit_cases(module) -> list[tuple[str, str, bool, bool]]:
    """(round, description, actual, expected) for predicate-level cases."""
    removed = frozenset(
        {
            "scripts/sd-ai-command-pack-full-check.sh",
            "scripts/sd_ai_command_pack_lib.py",
            "docs/SD_AI_COMMAND_PACK.md",
            ".agents/skills/sd-status/SKILL.md",
            ".claude/commands/sd/review.md",
        }
    )
    survivors = frozenset({"README.md", "docs/review.md", "scripts/local.sh"})
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
        unit_cases(module) + symlink_cases(module)
    ):
        if actual == expected:
            passed += 1
        else:
            failures.append(f"unit  {round_id}: {description} -> {actual!r}")

    scan = json.loads(args.scan.read_text(encoding="utf-8"))
    rows = {row["consumer"]: row for row in scan["consumers"]}
    buckets = ("blockers", "packDefects", "scheduled", "advisories")

    for consumer, relative, line, expected, round_id, why in FLEET_CASES:
        row = rows.get(consumer)
        if row is None or "error" in row:
            skipped.append(f"fleet {round_id}: {consumer} not in the scan")
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
        f"{len(unit_cases(module)) + len(symlink_cases(module))} unit)"
    )
    return 1 if failures or skipped else 0


if __name__ == "__main__":
    raise SystemExit(main())
