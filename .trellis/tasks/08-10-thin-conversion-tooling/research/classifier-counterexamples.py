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
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCANNER = HERE / "fleet-blocker-scan.py"
REGISTRY = HERE.parents[3] / "docs/fleet/consumers.json"
AUDIT = HERE.parents[3] / "scripts/sd-ai-command-pack-install-audit.py"
SYNTHETIC_VERSION = "0.64.0"
SYNTHETIC_BOOKKEEPING = (
    ".sd-ai-command-pack/installed-targets.txt",
    ".sd-ai-command-pack/manifest.json",
    ".sd-ai-command-pack/provenance.json",
)
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
        ".codex",
        None,
        "blockers",
        "R12-C1",
        "undeclared codex usage: the registry declares claude/gemini/github/"
        "opencode, and `retainVendoredFor` intersects *declared* platforms, so "
        "conversion deletes `.agents/**` out from under a Codex user who "
        "cannot consume the machine plugin at all",
    ),
    (
        "sd-github-review",
        ".codex",
        None,
        "blockers",
        "R13-C1",
        "the demonstration itself: this consumer's whole Codex surface is a "
        "project-scoped `.codex/config.toml`, which round 12's exemption list "
        "covered -- so it was the one consumer with no marker at all, while "
        "its receipt carries the `.agents/skills/**` that `retainVendoredFor` "
        "keeps only for a declared codex or pi consumer",
    ),
    (
        "se-ai-command-pack",
        ".codex",
        None,
        "blockers",
        "R12-C1/R13-C1",
        "round 12 exempted this consumer because its `.codex/` holds only "
        "paths on `trellis_local_only`, and round 13 demonstrated that the "
        "exemption is wrong in both directions: `.codex/config.toml` is on "
        "that list, so `sd-github-review`'s entire real Codex surface was "
        "invisible, while an empty Trellis-local directory blocked anyway. "
        "Whoever wrote these files runs Codex here, and conversion deletes "
        "`.agents/**` whatever wrote them, so `prd.md:19` is unqualified",
    ),
    (
        "se-ai-command-pack",
        "$CODEX_HOME",
        None,
        "blockers",
        "R12-C1",
        "and the environment marker fires on the same consumer anyway. The "
        "pair is what makes the three markers falsifiably separate: `prd.md:204` "
        "requires three fixtures because one combined case would pass while two "
        "markers were never implemented",
    ),
    (
        "sd-github-review",
        "$CODEX_HOME",
        None,
        None,
        "R12-C1",
        "the one consumer with neither marker: a Trellis-local `.codex/` and no "
        "surviving $CODEX_HOME reference. Without this row, a marker rule that "
        "fired on everything would look correct",
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


def _synthetic_consumer(raw: str, build) -> Path:
    """A disposable consumer with a real receipt, so `scan()` can run on it.

    R12-C2/C3/C4. Several rules the scanner claims fail closed -- an unreadable
    unmanaged file, a symlinked receipt target, malformed markers, an empty
    `.codex/`, a NUL-bearing executable -- describe filesystem states no fleet
    consumer is in. Codex reverted three of them and the harness stayed at
    63/0/0, because there was no way to *reach* them: every fixture was either a
    pure predicate or a real consumer. A consumer the harness builds is the
    missing third thing.

    R13-C4: the receipt is the one the production installer would have written,
    not the smallest one `scan()` accepts. Round 12's fixture listed three
    targets, omitted the three generated bookkeeping files, gave `manifest.json`
    no `files` list and `provenance.json` an empty map -- so the production
    structural audit rejected it with five errors. Assertions about `scan()` on
    a repository `--thin` would refuse to touch prove less than they appear to,
    so `audit_cases()` now runs that audit against this fixture and requires it
    to pass.
    """
    repo = Path(raw).resolve()
    for args in (
        ("init", "-q"),
        ("config", "user.email", "harness@example.invalid"),
        ("config", "user.name", "harness"),
    ):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    (repo / ".sd-ai-command-pack").mkdir()
    (repo / "scripts").mkdir()
    (repo / ".github").mkdir()
    (repo / "scripts/sd-ai-command-pack-full-check.sh").write_text(
        "#!/bin/sh\n", encoding="utf-8"
    )
    (repo / ".github/copilot-instructions.md").write_text(
        "consumer guidance\n", encoding="utf-8"
    )
    (repo / ".gitignore").write_text("nothing\n", encoding="utf-8")
    payload = (
        "scripts/sd-ai-command-pack-full-check.sh",
        ".github/copilot-instructions.md",
        ".gitignore",
    )
    (repo / ".sd-ai-command-pack/installed-targets.txt").write_text(
        "".join(f"{target}\n" for target in sorted(payload + SYNTHETIC_BOOKKEEPING)),
        encoding="utf-8",
    )
    (repo / ".sd-ai-command-pack/provenance.json").write_text(
        json.dumps(
            {
                "pack": "sd-ai-command-pack",
                "version": SYNTHETIC_VERSION,
                # Production provenance does not vouch a managed-block or
                # force-preserved target -- that is why the scanner has three
                # separate ownership proofs -- so neither does this. Vouching
                # `.github/copilot-instructions.md` here would have made the
                # malformed-marker fixture assert the wrong rule.
                "files": {
                    target: "sha256:"
                    + hashlib.sha256((repo / target).read_bytes()).hexdigest()
                    for target in payload
                    if target == "scripts/sd-ai-command-pack-full-check.sh"
                },
            }
        ),
        encoding="utf-8",
    )
    (repo / ".sd-ai-command-pack/manifest.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "name": "sd-ai-command-pack",
                "version": SYNTHETIC_VERSION,
                "files": [
                    {
                        "platform": "shared",
                        "kind": "script",
                        "source": "templates/scripts/sd-ai-command-pack-full-check.sh",
                        "target": "scripts/sd-ai-command-pack-full-check.sh",
                        "install": "always",
                    },
                    {
                        "platform": "github",
                        "kind": "instructions",
                        "source": "templates/.github/copilot-instructions.md",
                        "target": ".github/copilot-instructions.md",
                        "install": "always",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    build(repo)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-qm", "synthetic"],
        check=True,
        capture_output=True,
    )
    return repo


BINDINGS = (
    "head",
    "indexDigest",
    "indexFlagsDigest",
    "hiddenBytesDigest",
    "worktreeDigest",
    "worktreeClean",
    "receiptOccupancyDigest",
    "executableBitsDigest",
    "symlinkTargetsDigest",
    "binaryFiles",
    "missingFiles",
    "scannedBytesDigest",
)


def synthetic_cases(module) -> list[tuple[str, str, object, object]]:
    """Rules whose triggering state no real consumer is in."""
    cases: list[tuple[str, str, object, object]] = []
    platforms = frozenset({"claude", "github"})

    def scan_with(build):
        with tempfile.TemporaryDirectory() as raw:
            repo = _synthetic_consumer(raw, build)
            return module.scan("synthetic", repo, platforms)

    def baseline(repo):
        (repo / "run.sh").write_text(
            "#!/bin/sh\nbash scripts/sd-ai-command-pack-full-check.sh\n",
            encoding="utf-8",
        )

    base = scan_with(baseline)
    cases.append(
        (
            "R12-C2",
            "the synthetic baseline blocks on its one real citation",
            [(e["file"], e["line"]) for e in base["blockers"]],
            [("run.sh", 2)],
        )
    )

    # R12-C2: an empty directory. Every file-oriented binding is blind to it.
    def with_codex(repo):
        baseline(repo)

    # Both scans run against the *same* checkout, inside its lifetime: the only
    # difference is the declared platform set. A second `scan_with` would build
    # a second repository and the comparison would be about two trees.
    with tempfile.TemporaryDirectory() as raw:
        repo = _synthetic_consumer(raw, with_codex)
        clean = module.scan("synthetic", repo, platforms)
        # Created *after* the commit, and left empty: git tracks no directory,
        # so this is the change no file-oriented binding can see.
        (repo / ".codex").mkdir()
        codex = module.scan("synthetic", repo, platforms)
        declared = module.scan("synthetic", repo, platforms | {"codex"})

    def marker_fired(result):
        return any(
            "undeclared codex" in (entry.get("detail") or "")
            for entry in result["blockers"]
        )

    cases += [
        (
            "R12-C1/R12-C2",
            "an undeclared .codex/ blocks",
            marker_fired(codex),
            True,
        ),
        (
            "R12-C2",
            "and it moves platformMarkerDigest, which no other binding sees",
            codex["platformMarkerDigest"] != clean["platformMarkerDigest"],
            True,
        ),
        (
            "R12-C2",
            "while every other recorded binding stays byte-identical",
            [key for key in BINDINGS if codex[key] != clean[key]],
            [],
        ),
        (
            "R12-C1",
            "declaring the platform clears the marker on the same checkout",
            marker_fired(declared),
            False,
        ),
    ]

    # R12-C4: a NUL byte does not mean "cannot execute".
    def with_nul_script(repo):
        baseline(repo)
        (repo / "nul.sh").write_bytes(
            b"#!/bin/sh\n# \x00 marker\nbash scripts/sd-ai-command-pack-full-check.sh\n"
        )

    nul = scan_with(with_nul_script)
    cases.append(
        (
            "R12-C4",
            "a NUL-bearing shell script is still classified, not skipped as an asset",
            any(entry["file"] == "nul.sh" for entry in nul["blockers"]),
            True,
        )
    )

    # R12-C3: an unreadable unmanaged file is a tree the scan did not read.
    def with_unreadable(repo):
        baseline(repo)
        secret = repo / "unreadable.sh"
        secret.write_text("#!/bin/sh\n", encoding="utf-8")

    with tempfile.TemporaryDirectory() as raw:
        repo = _synthetic_consumer(raw, with_unreadable)
        (repo / "unreadable.sh").chmod(0o000)
        readable_anyway = os.access(repo / "unreadable.sh", os.R_OK)
        result = module.scan("synthetic", repo, platforms)
        (repo / "unreadable.sh").chmod(0o644)
    if not readable_anyway:
        cases += [
            (
                "R8-3/R12-C3",
                "an unreadable unmanaged file is missing, not binary",
                result["missingFiles"],
                ["unreadable.sh"],
            ),
            (
                "R8-3/R12-C3",
                "and a tree the scan could not read is blocked",
                result["verdict"],
                "blocked",
            ),
        ]

    # R12-C3: a symlinked receipt target is unresolvable ownership.
    def with_symlinked_target(repo):
        baseline(repo)
        (repo / "scripts/sd-ai-command-pack-full-check.sh").unlink()
        (repo / "real-check.sh").write_text("#!/bin/sh\n", encoding="utf-8")
        os.symlink(
            "../real-check.sh", repo / "scripts/sd-ai-command-pack-full-check.sh"
        )
        (repo / ".github/copilot-instructions.md").unlink()
        os.symlink("../real-check.sh", repo / ".github/copilot-instructions.md")

    symlinked = scan_with(with_symlinked_target)
    cases.append(
        (
            "R12-C3",
            "a symlinked receipt target is a pack defect, not a silent skip",
            any(
                entry["file"] == ".github/copilot-instructions.md"
                for entry in symlinked["packDefects"]
            ),
            True,
        )
    )

    # R12-C3: malformed markers are unresolvable ownership, so pack-owned.
    def with_malformed_markers(repo):
        baseline(repo)
        (repo / ".github/copilot-instructions.md").write_text(
            f"{module.COPILOT_GUIDANCE_START}\n"
            "run scripts/sd-ai-command-pack-full-check.sh\n",
            encoding="utf-8",
        )

    malformed = scan_with(with_malformed_markers)
    cases.append(
        (
            "U-3/R12-C3",
            "an unterminated marker fails closed to a pack defect, not a blocker",
            any(
                entry["file"] == ".github/copilot-instructions.md"
                for entry in malformed["packDefects"]
            ),
            True,
        )
    )

    # R11-C4: .github is the host's shared directory, not one agent's.
    def with_issue_template(repo):
        baseline(repo)
        (repo / ".github/ISSUE_TEMPLATE").mkdir(parents=True, exist_ok=True)
        (repo / ".github/ISSUE_TEMPLATE/bug.md").write_text(
            "Paste the output of scripts/sd-ai-command-pack-full-check.sh here\n",
            encoding="utf-8",
        )

    issue = scan_with(with_issue_template)
    cases.append(
        (
            "R11-C4/R12-C3",
            "an issue template is not an execution surface, so it stays advisory",
            [
                bucket
                for bucket in ("blockers", "packDefects", "advisories")
                for entry in issue[bucket]
                if entry["file"] == ".github/ISSUE_TEMPLATE/bug.md"
            ],
            ["advisories"],
        )
    )

    # R13-C4: the fixture is only evidence if production would accept it.
    with tempfile.TemporaryDirectory() as raw:
        repo = _synthetic_consumer(raw, baseline)
        audit = subprocess.run(
            [sys.executable, str(AUDIT), "--repo", str(repo)],
            capture_output=True,
            text=True,
        )
    cases.append(
        (
            "R13-C4",
            "the production structural audit accepts the synthetic consumer",
            (audit.returncode, [
                line for line in audit.stdout.splitlines() if line.startswith("error")
            ]),
            (0, []),
        )
    )

    # R13-C1, demonstrated against a real consumer. Round 12 exempted paths on
    # `PlatformInfo.trellis_local_only`, and `.codex/config.toml` is on that
    # list -- so `sd-github-review`, whose entire Codex surface is a
    # project-scoped `config.toml` and whose receipt carries `.agents/skills/**`,
    # returned `clear`. Whoever wrote that file runs Codex there; the conversion
    # deletes `.agents/**` regardless of which tool wrote it.
    def with_trellis_local_codex(repo):
        (repo / ".codex").mkdir()
        (repo / ".codex/config.toml").write_text("[project]\n", encoding="utf-8")

    local_codex = scan_with(with_trellis_local_codex)
    cases += [
        (
            "R13-C1",
            "a .codex/ holding only Trellis-local paths still blocks",
            marker_fired(local_codex),
            True,
        ),
        (
            "R13-C1",
            "and that is the whole verdict, not a citation somewhere else",
            local_codex["verdict"],
            "blocked",
        ),
    ]

    # R13-C1/R13-C2: pi. The old exclusion matched `.pi/skills/trellis-*/` with
    # a literal `startswith`, so the glob never matched -- and the adapter
    # branch had no fixture at all: Codex disabled it and the harness stayed at
    # 78/0/0. The registry's marker paths are the pack's own statement of what a
    # pi adapter looks like.
    def with_pi_adapter(repo):
        (repo / ".pi/prompts").mkdir(parents=True)
        (repo / ".pi/prompts/trellis-continue.md").write_text("go\n", encoding="utf-8")

    pi = scan_with(with_pi_adapter)
    cases += [
        (
            "R13-C1",
            "an undeclared .pi/ directory blocks",
            any(
                "undeclared pi usage" in (entry.get("detail") or "")
                for entry in pi["blockers"]
            ),
            True,
        ),
        (
            "R13-C2",
            "and the registry's adapter marker is a separate, own entry",
            [
                entry["file"]
                for entry in pi["blockers"]
                if "adapter file" in (entry.get("detail") or "")
            ],
            [".pi/prompts/trellis-continue.md"],
        ),
    ]

    # R13-C5: the content half of the execution surface. `notes.dat` is not an
    # executable path, so round 12's fix does not reach it -- but line 2 is in
    # command position, and command position executes what follows whatever the
    # file is called.
    def with_nul_data(repo):
        (repo / "notes.dat").write_bytes(
            b"binary \x00 payload\nbash scripts/sd-ai-command-pack-full-check.sh\n"
        )

    nul_data = scan_with(with_nul_data)
    cases += [
        (
            "R13-C5",
            "a NUL-bearing data file still blocks on a command-position line",
            [(e["file"], e["line"]) for e in nul_data["blockers"]],
            [("notes.dat", 2)],
        ),
        (
            "R13-C5",
            "while its weaker citation forms stay suppressed as asset noise",
            [e for e in nul_data["advisories"] if e["file"] == "notes.dat"],
            [],
        ),
    ]

    # R13-C3, constructed: a clean filter maps any worktree content to the
    # committed blob, so `git status` stays empty and `worktreeDigest` -- which
    # hashes only the paths git reports dirty -- sees nothing, while the scanner
    # reads the real bytes.
    def with_clean_filter(repo):
        subprocess.run(
            ["git", "-C", str(repo), "config", "filter.blank.clean", "true"],
            check=True,
            capture_output=True,
        )
        (repo / ".gitattributes").write_text(
            "notes.txt filter=blank\n", encoding="utf-8"
        )
        (repo / "notes.txt").write_text("placeholder\n", encoding="utf-8")

    with tempfile.TemporaryDirectory() as raw:
        repo = _synthetic_consumer(raw, with_clean_filter)
        before = module.scan("synthetic", repo, platforms)
        (repo / "notes.txt").write_text(
            "bash scripts/sd-ai-command-pack-full-check.sh\n", encoding="utf-8"
        )
        # The clean filter already makes the converted content identical to the
        # committed blob, but `git status` reports the file modified until the
        # stat cache is refreshed. `git add` refreshes it and stages nothing --
        # after this the tree is clean by every measure git offers, and the
        # worktree still holds the citation.
        subprocess.run(
            ["git", "-C", str(repo), "add", "notes.txt"],
            check=True,
            capture_output=True,
        )
        status = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        after = module.scan("synthetic", repo, platforms)

    cases += [
        (
            "R13-C3",
            "a clean filter hides changed worktree bytes from git entirely",
            (status, before["worktreeDigest"] == after["worktreeDigest"]),
            ("", True),
        ),
        (
            "R13-C3",
            "the hidden bytes still change the verdict",
            (before["verdict"], after["verdict"]),
            ("clear", "blocked"),
        ),
        (
            "R13-C3",
            "and scannedBytesDigest is the binding that records them",
            [key for key in BINDINGS if before[key] != after[key]],
            ["scannedBytesDigest"],
        ),
    ]
    return cases


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
        + synthetic_cases(module)
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
        # `$CODEX_HOME` is a synthetic key, not a path: the environment marker
        # aggregates references across many files, and anchoring it to whichever
        # one `git ls-files` sorted first would anchor it to nothing.
        if not relative.startswith("$") and not full.exists():
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
        f"{len(unit_cases(module)) + len(symlink_cases(module)) + len(bytes_cases(module)) + len(enumeration_cases(module)) + len(synthetic_cases(module))}"
        " unit)"
    )
    return 1 if failures or skipped else 0


if __name__ == "__main__":
    raise SystemExit(main())
