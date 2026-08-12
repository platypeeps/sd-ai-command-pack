#!/usr/bin/env python3
"""Validate a pack release candidate against disposable fleet checkouts."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from sd_ai_command_pack_fleet_lib import (  # noqa: E402
    CANDIDATE_LEDGER_SCHEMA_VERSION,
    FleetConfigError,
    FleetConsumer,
    filesystem_candidate_validator_digest,
    filesystem_payload_digest,
    fleet_manifest_digest,
    load_fleet_consumers,
    load_json_object,
    manifest_version,
    validate_candidate_ledger,
)
from sd_ai_command_pack_lib import (  # noqa: E402
    CACHE_ENV_KEYS,
    CACHE_ROOT_ENV,
    CacheSetupError,
    build_tool_environment,
)

DEFAULT_FLEET_MANIFEST = ROOT / "docs/fleet/consumers.json"
DEFAULT_PACK_MANIFEST = ROOT / "manifest.json"
DEFAULT_LEDGER = ROOT / "docs/fleet/candidate-validation.json"
INSTALL_AUDIT = ROOT / "scripts/sd-ai-command-pack-install-audit.py"
COMMAND_OUTPUT_LINES = 30
INFRASTRUCTURE_TIMEOUT_SECONDS = 600

#: Where the thin artifact lane's machine install lands inside the run's
#: temporary directory, and where the thin per-consumer lane then points `HOME`.
#: These are one decision, not two: the install is only evidence that a thin
#: consumer's `~/.agents` lookups resolve to *this* candidate if the checks that
#: make those lookups actually read it.
MACHINE_HOME_DIRNAME = "home"
MACHINE_STATE_DIRNAME = "state"

#: The generated Claude plugin, relative to the pack root.
PLUGIN_DIRECTORY = "plugins/sd"

#: The three thin artifact steps, in the order a failure is most cheaply found.
#: Requirement 1 named a fourth -- a `claude --plugin-dir` load smoke -- which
#: is not implementable: it exits 0 against a directory that does not exist, so
#: it has no failure channel at all, and its only non-interactive form requires
#: a model call. `generate-plugin.py --check` covers what the smoke was reaching
#: for (does the built plugin match the committed one) deterministically and
#: offline. See the task's design.md D5.
ARTIFACT_STEP_PLUGIN_BUILD = "plugin build and drift check"
ARTIFACT_STEP_PLUGIN_VALIDATE = "plugin manifest validation"
ARTIFACT_STEP_MACHINE_INSTALL = "machine install into a scratch prefix"

#: A step that could not run because `claude` is not resolvable. It is not
#: `passed` and it is not a skip: requirement 5 makes an unrunnable validation
#: a failure, because the alternative is a release gate that reports success on
#: a machine where it never executed.
STATUS_UNAVAILABLE = "unavailable"
STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_BLOCKED = "blocked"


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    output: str
    duration_seconds: float


@dataclass(frozen=True)
class CandidateResult:
    consumer: FleetConsumer
    status: str
    base_commit: str | None
    detail: str
    duration_seconds: float
    #: Why this consumer is `blocked`, and empty for every other status. A
    #: `blocked` row with no reasons is rejected by the ledger validator: an
    #: unexplained skip is the failure mode the status exists to prevent.
    reasons: tuple[str, ...] = ()
    #: Recorded when the clone's pin and the registry's declared mode disagree.
    #: Not an error -- that is the documented window between a consumer's
    #: conversion PR merging and the registry flip landing.
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ArtifactStep:
    name: str
    status: str
    detail: str
    duration_seconds: float


@dataclass(frozen=True)
class ArtifactLaneResult:
    """The pack-side thin artifacts, validated once per run.

    Once, not once per consumer: the plugin and the machine payload do not vary
    by consumer, so running them eight times would multiply the cost of the
    slowest steps for no additional evidence. Its failure is likewise not
    attributed to a consumer -- nothing about a consumer caused it.
    """

    steps: tuple[ArtifactStep, ...]
    machine_home: Path | None
    machine_state: Path | None

    @property
    def ok(self) -> bool:
        return all(step.status == STATUS_PASSED for step in self.steps)

    @property
    def failures(self) -> tuple[ArtifactStep, ...]:
        return tuple(step for step in self.steps if step.status != STATUS_PASSED)


def command_environment(
    python_executable: Path,
    work_root: Path,
    *,
    machine_home: Path | None = None,
) -> dict[str, str]:
    """The environment every candidate subprocess runs under.

    `machine_home` is the thin lane's, and only the thin lane's. A fat
    consumer's registered checks are all repository-relative, so overriding
    `HOME` for them would perturb tool caches to no purpose. A *thin*
    consumer's pack helpers resolve through `~/.agents/bin`, and with the
    invoking `HOME` inherited those lookups reach whatever pack the developer
    or CI runner happens to have installed -- so the run would certify someone
    else's release rather than this candidate. Pointing `HOME` at the scratch
    prefix the artifact lane's machine install wrote is what makes the thin
    lane test the thing under test.
    """

    inherited = os.environ.copy()
    for variable in CACHE_ENV_KEYS:
        inherited.pop(variable, None)
    inherited[CACHE_ROOT_ENV] = str(work_root.resolve())
    if machine_home is not None:
        inherited["HOME"] = str(machine_home.resolve())
    try:
        env, _, _ = build_tool_environment(repo=ROOT, environ=inherited)
    except CacheSetupError as error:
        raise FleetConfigError(f"candidate cache setup failed: {error}") from None
    env.pop("COVERAGE_FILE", None)
    env.pop("COVERAGE_PROCESS_START", None)
    python_bin = str(python_executable.resolve().parent)
    inherited_path = env.get("PATH")
    env["PATH"] = (
        os.pathsep.join([python_bin, inherited_path]) if inherited_path else python_bin
    )
    env["SD_AI_COMMAND_PACK_CANDIDATE_CHECK"] = "1"
    return env


def run_command(
    command: Sequence[str],
    *,
    cwd: Path,
    timeout_seconds: int,
    env: dict[str, str],
) -> CommandResult:
    started = time.monotonic()
    try:
        result = subprocess.run(
            list(command),
            cwd=cwd,
            env=env,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=timeout_seconds,
        )
        return CommandResult(
            returncode=result.returncode,
            output=result.stdout,
            duration_seconds=time.monotonic() - started,
        )
    except subprocess.TimeoutExpired as error:
        output = error.stdout or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        return CommandResult(
            returncode=124,
            output=f"{output}\ncommand timed out after {timeout_seconds}s".strip(),
            duration_seconds=time.monotonic() - started,
        )
    except (OSError, UnicodeError) as error:
        return CommandResult(
            returncode=127,
            output=f"command failed to start or decode output: {error}",
            duration_seconds=time.monotonic() - started,
        )


def concise_failure(label: str, command: Sequence[str], result: CommandResult) -> str:
    lines = [line for line in result.output.splitlines() if line.strip()]
    tail = "\n".join(lines[-COMMAND_OUTPUT_LINES:])
    detail = (
        f"{label} failed with exit {result.returncode}: {shlex.join(command)}"
    )
    return f"{detail}\n{tail}" if tail else detail


def _installer_modules(pack_root: Path):
    """The conversion predicate and the resweep, loaded from the pack root.

    Imported rather than reimplemented. `thin_pin_state` is the same predicate
    `install.py` itself branches on, and the resweep script's bytes feed its own
    `classifierDigest` -- a second implementation of either would be a second
    thing to keep in step with a rule that already binds itself.
    """

    if str(pack_root) not in sys.path:
        sys.path.insert(0, str(pack_root))
    from installer import conversion, references, thin  # noqa: PLC0415

    return conversion, references, thin.load_resweep_module(pack_root)


def surviving_pack_defects(verdict: dict, *, clone: Path, references) -> list[str]:
    """The pack defects a conversion would not repoint on its way through.

    The resweep's `packDefects` bucket is a *pre-rewrite* measurement: it counts
    pack-owned content citing a path the conversion removes, and says so before
    the conversion has had its turn. But a conversion rewrites every kept text
    file through `THIN_PROFILE` first, and that rewrite exists precisely to
    repoint `scripts/sd-ai-command-pack-*` at `~/.agents/bin` and the manual at
    `~/.agents/docs`. Treating the raw count as a release blocker fails the pack
    for references the pack already handles -- measured at 15-17 per consumer
    across all eight, every one of which the rewrite repoints.

    So each entry is put through the conversion's own residue gate, which is the
    authoritative answer to "would this reference still be broken afterwards?".
    Only residue is a defect. An entry whose subject is not a readable file in
    the clone -- a synthetic marker like undeclared `codex` usage, or a
    surviving platform directory -- cannot be cleared by a text rewrite at all,
    so it stays a defect by default rather than being cleared by inspection that
    does not apply to it.
    """

    failures: list[str] = []
    seen: set[str] = set()
    for entry in verdict.get("packDefects") or ():
        subject = entry.get("file")
        if not isinstance(subject, str) or subject in seen:
            continue
        seen.add(subject)
        path = clone / subject
        if not path.is_file() or path.is_symlink():
            failures.append(f"{subject}: {entry.get('detail')}")
            continue
        try:
            text = path.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            failures.append(f"{subject}: unreadable pack target")
            continue
        rewritten = references.rewrite_text(
            text, profile=references.THIN_PROFILE, key=subject
        )
        try:
            references.check_text_residue(
                subject, rewritten, profile=references.THIN_PROFILE
            )
        except references.ReferenceRewriteError as error:
            failures.append(str(error))
    return failures


def resweep_reasons(verdict: dict) -> tuple[list[str], list[str]]:
    """Split one resweep verdict into what fails the pack and what blocks it.

    This is the policy answer, and it is the distinction `decide()` already
    draws: "the tree was dirty" and "the pack ships a broken reference" call
    for opposite responses. Pack-owned defects are handled by
    `surviving_pack_defects` above, which is stricter about what counts as one.
    Consumer-owned references, missing files, and a dirty worktree are
    conditions in repositories the pack does not own and cannot fix; failing on
    them would make every pack release hostage to eight consumer backlogs.
    """

    counts = verdict.get("counts") or {}
    failing: list[str] = []
    blocking: list[str] = []

    blockers = counts.get("blockers") or 0
    if blockers:
        blocking.append(
            f"{blockers} consumer-authored reference(s) to removed paths"
        )
    missing = len(verdict.get("missingFiles") or ())
    if missing:
        blocking.append(f"{missing} manifest file(s) missing from the checkout")
    if not verdict.get("worktreeClean", True):
        blocking.append("the checkout has uncommitted changes")

    return failing, blocking


def unresolvable_thin_checks(
    commands: Sequence[Sequence[str]],
    *,
    clone: Path,
    manifest_targets: frozenset[str],
) -> list[str]:
    """Registered commands a thin checkout cannot run, and why.

    A converted consumer keeps its own scripts but not the pack's: those move
    to `~/.agents/bin`. So a registry row that still invokes
    `scripts/sd-ai-command-pack-*.py` by repository-relative path names a file
    the conversion deleted. That is not a pack failure -- the pack built
    correctly and the install succeeded -- it is a registry record still
    describing the consumer's fat shape, and the fix belongs to that consumer's
    conversion PR. A missing path the pack does *not* own is a different thing
    entirely: the consumer's own check is broken, and that stays a failure.
    """

    reasons: list[str] = []
    for command in commands:
        for argument in command:
            if "/" not in argument and not argument.startswith("."):
                # A bare program name resolves through PATH, not the clone.
                continue
            candidate = (clone / argument).resolve()
            try:
                inside = candidate.is_relative_to(clone.resolve())
            except ValueError:  # pragma: no cover - defensive
                inside = False
            if not inside or candidate.exists():
                continue
            if argument not in manifest_targets:
                continue
            name = PurePosixPath(argument).name
            reasons.append(
                f"registered command {shlex.join(command)!r} names "
                f"{argument!r}, which a thin conversion relocates to "
                f"~/.agents/bin/{name}; the consumer's registry record still "
                "describes its fat shape"
            )
    return reasons


def run_thin_artifact_lane(
    *,
    pack_root: Path,
    work_root: Path,
    python_executable: Path,
    env: dict[str, str],
) -> ArtifactLaneResult:
    """Validate the pack-side artifacts a thin consumer resolves against.

    Three steps. The first builds the plugin from the surface partition and
    compares it against the committed tree, which catches both a generator
    failure and drift without writing anything -- `--check` is why this lane
    needs no scratch copy of the checkout, and a validator that rewrote its own
    input would be the same category of error as converting a consumer inside
    the loop. The second asks Claude Code itself whether the manifest is valid
    under `--strict`. The third installs the machine payload into a scratch
    prefix and hands that prefix back for the thin per-consumer lane.
    """

    steps: list[ArtifactStep] = []

    def record(name: str, command: Sequence[str], result: CommandResult) -> bool:
        passed = result.returncode == 0
        steps.append(
            ArtifactStep(
                name=name,
                status=STATUS_PASSED if passed else STATUS_FAILED,
                detail=(
                    shlex.join(command)
                    if passed
                    else concise_failure(name, command, result)
                ),
                duration_seconds=result.duration_seconds,
            )
        )
        return passed

    build_command = [
        str(python_executable),
        str(pack_root / ".github/scripts/generate-plugin.py"),
        "--check",
        "--root",
        str(pack_root),
    ]
    record(
        ARTIFACT_STEP_PLUGIN_BUILD,
        build_command,
        run_command(
            build_command,
            cwd=pack_root,
            timeout_seconds=INFRASTRUCTURE_TIMEOUT_SECONDS,
            env=env,
        ),
    )

    claude_executable = shutil.which("claude", path=env.get("PATH"))
    if claude_executable is None:
        steps.append(
            ArtifactStep(
                name=ARTIFACT_STEP_PLUGIN_VALIDATE,
                status=STATUS_UNAVAILABLE,
                detail=(
                    "the `claude` executable is not resolvable on PATH, so the "
                    "plugin manifest was never validated. This is a failure, "
                    "not a skip: a release gate that reports success where it "
                    "did not run is the defect the gate exists to prevent. "
                    "Install Claude Code on the machine that runs release-prep."
                ),
                duration_seconds=0.0,
            )
        )
    else:
        validate_command = [
            claude_executable,
            "plugin",
            "validate",
            str(pack_root / PLUGIN_DIRECTORY),
            "--strict",
        ]
        record(
            ARTIFACT_STEP_PLUGIN_VALIDATE,
            validate_command,
            run_command(
                validate_command,
                cwd=pack_root,
                timeout_seconds=INFRASTRUCTURE_TIMEOUT_SECONDS,
                env=env,
            ),
        )

    machine_home = work_root / MACHINE_HOME_DIRNAME
    machine_state = work_root / MACHINE_STATE_DIRNAME
    machine_home.mkdir(parents=True, exist_ok=True)
    machine_state.mkdir(parents=True, exist_ok=True)
    machine_command = [
        str(python_executable),
        str(pack_root / "install.py"),
        "--machine",
        "--home",
        str(machine_home),
        "--state-home",
        str(machine_state),
    ]
    installed = record(
        ARTIFACT_STEP_MACHINE_INSTALL,
        machine_command,
        run_command(
            machine_command,
            cwd=pack_root,
            timeout_seconds=INFRASTRUCTURE_TIMEOUT_SECONDS,
            env=env,
        ),
    )

    return ArtifactLaneResult(
        steps=tuple(steps),
        machine_home=machine_home if installed else None,
        machine_state=machine_state if installed else None,
    )


def validate_consumer(
    consumer: FleetConsumer,
    *,
    pack_root: Path,
    work_root: Path,
    python_executable: Path,
    machine_home: Path | None = None,
) -> CandidateResult:
    started = time.monotonic()
    source_checkout = Path(consumer.path_hint).expanduser()
    if not source_checkout.is_dir():
        return CandidateResult(
            consumer=consumer,
            status="failed",
            base_commit=None,
            detail=f"local checkout not found: {source_checkout}",
            duration_seconds=time.monotonic() - started,
        )

    env = command_environment(python_executable, work_root)
    origin_command = ["git", "-C", str(source_checkout), "remote", "get-url", "origin"]
    origin_result = run_command(
        origin_command,
        cwd=pack_root,
        timeout_seconds=60,
        env=env,
    )
    if origin_result.returncode != 0:
        return CandidateResult(
            consumer=consumer,
            status="failed",
            base_commit=None,
            detail=concise_failure("origin lookup", origin_command, origin_result),
            duration_seconds=time.monotonic() - started,
        )
    origin_url = origin_result.output.strip()
    if not origin_url:
        return CandidateResult(
            consumer=consumer,
            status="failed",
            base_commit=None,
            detail="origin lookup returned an empty URL",
            duration_seconds=time.monotonic() - started,
        )

    checkout = work_root / consumer.name
    clone_command = [
        "git",
        "clone",
        "--quiet",
        # Tags stay in: consumer gates may verify release-tag pin freshness
        # (sd-github-review validate:metadata) and fail in a tag-less clone.
        "--single-branch",
        "--",
        origin_url,
        str(checkout),
    ]
    clone_result = run_command(
        clone_command,
        cwd=work_root,
        timeout_seconds=INFRASTRUCTURE_TIMEOUT_SECONDS,
        env=env,
    )
    if clone_result.returncode != 0:
        return CandidateResult(
            consumer=consumer,
            status="failed",
            base_commit=None,
            detail=concise_failure("clone", clone_command, clone_result),
            duration_seconds=time.monotonic() - started,
        )

    head_command = ["git", "rev-parse", "HEAD"]
    head_result = run_command(
        head_command,
        cwd=checkout,
        timeout_seconds=60,
        env=env,
    )
    base_commit = head_result.output.strip() if head_result.returncode == 0 else None
    if base_commit is None:
        return CandidateResult(
            consumer=consumer,
            status="failed",
            base_commit=None,
            detail=concise_failure("base commit lookup", head_command, head_result),
            duration_seconds=time.monotonic() - started,
        )

    conversion, references, resweep = _installer_modules(pack_root)
    notes: list[str] = []
    reasons: list[str] = []

    # Branch on the clone's own pin, never on the registry's declared mode.
    # The registry records what the pack believes; the pin records what the
    # checkout is, and they disagree by design during the window between a
    # consumer's conversion PR merging and the registry flip landing. Branching
    # on the registry would aim a `--platform` install at a genuinely thin
    # checkout during precisely the skew the system is built to tolerate.
    pin_state = conversion.thin_pin_state(checkout)
    if pin_state == conversion.PIN_STATE_MALFORMED:
        return CandidateResult(
            consumer=consumer,
            status="failed",
            base_commit=base_commit,
            detail=(
                "the clone's provenance pin carries thin evidence that cannot "
                "be read as a pin (pin state: malformed); refusing to guess a "
                "shape, exactly as install.py refuses in both directions"
            ),
            duration_seconds=time.monotonic() - started,
        )
    is_thin = pin_state == conversion.PIN_STATE_THIN
    if is_thin != (consumer.mode == "thin"):
        notes.append(
            f"clone pin is {pin_state!r} while the registry declares "
            f"{consumer.mode!r}; this is the documented conversion skew, not "
            "an error"
        )

    if is_thin:
        if machine_home is None:
            return CandidateResult(
                consumer=consumer,
                status="failed",
                base_commit=base_commit,
                detail=(
                    "the clone is thin, but the run has no machine install to "
                    "resolve ~/.agents against; the thin artifact lane did not "
                    "complete"
                ),
                duration_seconds=time.monotonic() - started,
            )
        # A thin consumer's platform set is owned by its pin, so `--platform`
        # is rejected outright by the thin-refresh branch of install.py.
        install_command = [
            str(python_executable),
            str(pack_root / "install.py"),
            str(checkout),
            "--force",
        ]
    else:
        install_command = [
            str(python_executable),
            str(pack_root / "install.py"),
            str(checkout),
            "--force",
        ]
        for platform in consumer.platforms:
            install_command.extend(["--platform", platform])
    install_result = run_command(
        install_command,
        cwd=pack_root,
        timeout_seconds=INFRASTRUCTURE_TIMEOUT_SECONDS,
        env=env,
    )
    if install_result.returncode != 0:
        return CandidateResult(
            consumer=consumer,
            status="failed",
            base_commit=base_commit,
            detail=concise_failure("install", install_command, install_result),
            duration_seconds=time.monotonic() - started,
        )

    audit_command = [
        str(python_executable),
        str(pack_root / "scripts/sd-ai-command-pack-install-audit.py"),
        "--repo",
        str(checkout),
    ]
    if not is_thin:
        for platform in consumer.platforms:
            audit_command.extend(["--expected-platform", platform])
    else:
        # `--expected-platform` requires that platform's manifest targets to be
        # installed *in the repository*, which is precisely what a thin
        # consumer does not have -- its surfaces resolve from the machine
        # install. Passing the registry's platform list here would demand the
        # vendored footprint the conversion removed and fail every thin clone.
        #
        # The audit still runs, against whatever the clone's own receipt
        # implies. D3 called for a thin-aware audit taking platforms from the
        # pin; `install-audit.py` has no such mode today, and inventing one
        # belongs to whichever task adds it rather than to this loop. Recorded
        # as a note so the gap is visible in the ledger rather than implied by
        # a shorter command line.
        notes.append(
            "audited against the clone's own receipt; --expected-platform is "
            "omitted for a thin checkout because it requires the vendored "
            "footprint a conversion removes"
        )
    audit_result = run_command(
        audit_command,
        cwd=pack_root,
        timeout_seconds=INFRASTRUCTURE_TIMEOUT_SECONDS,
        env=env,
    )
    if audit_result.returncode != 0:
        return CandidateResult(
            consumer=consumer,
            status="failed",
            base_commit=base_commit,
            detail=concise_failure("install audit", audit_command, audit_result),
            duration_seconds=time.monotonic() - started,
        )

    # Resweep *after* the install, not before. The obvious ordering is the
    # wrong one: a pristine clone carries whatever pack version that consumer
    # last installed, so a resweep run there measures the previous release and
    # not the candidate. Measured, that is not theoretical -- sd-github-review's
    # vendored copy of the planning-adversarial-review contract still invoked
    # the `codex` CLI, a defect this pack had already fixed, and the candidate
    # was failed for it.
    #
    # Installing dirties the worktree, and a dirty worktree is a resweep
    # blocker, so the install is committed in the disposable clone first. That
    # is free and honest here: the clone exists to be thrown away, and
    # committing is what makes "the tree contains the candidate" a fact the
    # resweep can read rather than noise it must be told to ignore.
    for stage_command in (
        ["git", "add", "--all"],
        ["git", "-c", "user.name=candidate", "-c", "user.email=candidate@invalid",
         "commit", "--quiet", "--allow-empty", "-m", "candidate install"],
    ):
        stage_result = run_command(
            stage_command, cwd=checkout, timeout_seconds=120, env=env
        )
        if stage_result.returncode != 0:
            return CandidateResult(
                consumer=consumer,
                status="failed",
                base_commit=base_commit,
                detail=concise_failure(
                    "staging the candidate install", stage_command, stage_result
                ),
                duration_seconds=time.monotonic() - started,
            )

    try:
        verdict = resweep.resweep_consumer(consumer.name, checkout)
    except Exception as error:  # noqa: BLE001 - a resweep failure is a failure
        return CandidateResult(
            consumer=consumer,
            status="failed",
            base_commit=base_commit,
            detail=f"resweep failed: {error}",
            duration_seconds=time.monotonic() - started,
        )
    _unused, blocking = resweep_reasons(verdict)
    reasons.extend(blocking)
    failing = surviving_pack_defects(verdict, clone=checkout, references=references)
    raw_pack_defects = (verdict.get("counts") or {}).get("packDefects") or 0
    if raw_pack_defects and not failing:
        notes.append(
            f"the resweep counted {raw_pack_defects} pack-owned citation(s) of "
            "removed paths; every one is repointed by the conversion's own "
            "rewrite, so none is a release defect"
        )
    if failing:
        return CandidateResult(
            consumer=consumer,
            status="failed",
            base_commit=base_commit,
            detail="; ".join(failing),
            duration_seconds=time.monotonic() - started,
        )

    if is_thin:
        # From here on the consumer's own commands run, and a thin consumer's
        # pack helpers resolve through `~/.agents/bin`. Point HOME at the
        # scratch prefix the artifact lane installed into, or the checks would
        # silently exercise whatever pack this machine already has.
        env = command_environment(python_executable, work_root, machine_home=machine_home)
        manifest_targets = frozenset(
            str(row.get("target"))
            for row in (load_json_object(pack_root / "manifest.json", "pack manifest").get("files") or ())
            if isinstance(row, dict) and row.get("target")
        )
        unresolvable = unresolvable_thin_checks(
            [*consumer.candidate_prepare, *consumer.candidate_checks],
            clone=checkout,
            manifest_targets=manifest_targets,
        )
        if unresolvable:
            reasons.extend(unresolvable)
            return CandidateResult(
                consumer=consumer,
                status=STATUS_BLOCKED,
                base_commit=base_commit,
                detail=(
                    f"{len(unresolvable)} registered command(s) name pack-owned "
                    "paths a thin conversion removes"
                ),
                duration_seconds=time.monotonic() - started,
                reasons=tuple(reasons),
                notes=tuple(notes),
            )

    for prepare_index, command in enumerate(consumer.candidate_prepare, start=1):
        prepare_result = run_command(
            command,
            cwd=checkout,
            timeout_seconds=consumer.candidate_timeout_seconds,
            env=env,
        )
        if prepare_result.returncode != 0:
            return CandidateResult(
                consumer=consumer,
                status="failed",
                base_commit=base_commit,
                detail=concise_failure(
                    f"candidate preparation {prepare_index}",
                    command,
                    prepare_result,
                ),
                duration_seconds=time.monotonic() - started,
            )

    for check_index, command in enumerate(consumer.candidate_checks, start=1):
        check_result = run_command(
            command,
            cwd=checkout,
            timeout_seconds=consumer.candidate_timeout_seconds,
            env=env,
        )
        if check_result.returncode != 0:
            return CandidateResult(
                consumer=consumer,
                status="failed",
                base_commit=base_commit,
                detail=concise_failure(
                    f"candidate check {check_index}", command, check_result
                ),
                duration_seconds=time.monotonic() - started,
            )

    shape = "thin" if is_thin else "fat"
    detail = (
        f"{shape} install, audit, "
        f"{len(consumer.candidate_prepare)} preparation(s), and "
        f"{len(consumer.candidate_checks)} check(s) passed"
    )
    if reasons:
        # Every step above ran and succeeded, but the resweep found a
        # consumer-owned condition that would block this consumer's conversion.
        # Recording that as `passed` is the one answer that is certainly wrong:
        # it would put a row in the ledger claiming a thin validation that the
        # consumer's own repository cannot yet support.
        return CandidateResult(
            consumer=consumer,
            status=STATUS_BLOCKED,
            base_commit=base_commit,
            detail=detail,
            duration_seconds=time.monotonic() - started,
            reasons=tuple(reasons),
            notes=tuple(notes),
        )
    return CandidateResult(
        consumer=consumer,
        status=STATUS_PASSED,
        base_commit=base_commit,
        detail=detail,
        duration_seconds=time.monotonic() - started,
        notes=tuple(notes),
    )


def current_evidence(
    manifest_path: Path,
    fleet_path: Path,
) -> tuple[str, str, str, str, list[FleetConsumer]]:
    """The single producer of every expected ledger field.

    Both the ledger writer (`ledger_content`) and the ledger checker
    (`check_ledger`, which is what the surface check shells out to) read this
    one tuple. Computing the written field and the checked field in two places
    is how they drift.
    """
    manifest = load_json_object(manifest_path, "pack manifest")
    version = manifest_version(manifest)
    payload = filesystem_payload_digest(manifest_path)
    validator = filesystem_candidate_validator_digest(manifest_path.resolve().parent)
    try:
        fleet_bytes = fleet_path.read_bytes()
    except OSError as error:
        raise FleetConfigError(f"cannot read fleet manifest {fleet_path}: {error}") from None
    return (
        version,
        payload,
        fleet_manifest_digest(fleet_bytes),
        validator,
        load_fleet_consumers(fleet_path),
    )


def ledger_content(
    *,
    version: str,
    payload_digest: str,
    fleet_digest: str,
    validator_digest: str,
    results: list[CandidateResult],
) -> dict[str, object]:
    return {
        "schemaVersion": CANDIDATE_LEDGER_SCHEMA_VERSION,
        "validatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
            "+00:00", "Z"
        ),
        "packVersion": version,
        "payloadDigest": payload_digest,
        "fleetManifestDigest": fleet_digest,
        "validatorDigest": validator_digest,
        "consumers": [
            {
                "name": result.consumer.name,
                "github": result.consumer.github,
                "baseCommit": result.base_commit,
                "status": result.status,
                "prepares": [
                    list(command) for command in result.consumer.candidate_prepare
                ],
                "checks": [list(command) for command in result.consumer.candidate_checks],
                # Present for every row, empty for every non-blocked one. The
                # ledger validator rejects a `blocked` row whose reasons are
                # absent or empty, which is what keeps the status from becoming
                # a silent skip.
                "reasons": list(result.reasons),
            }
            for result in results
        ],
    }


def write_ledger(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
            errors="strict",
        )
        os.replace(temporary, path)
    except (OSError, UnicodeError) as error:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise FleetConfigError(f"cannot write candidate ledger {path}: {error}") from None


def check_ledger(
    *,
    manifest_path: Path,
    fleet_path: Path,
    ledger_path: Path,
) -> list[str]:
    version, payload, fleet_digest, validator, consumers = current_evidence(
        manifest_path, fleet_path
    )
    try:
        ledger = load_json_object(ledger_path, "candidate ledger")
    except FleetConfigError as error:
        return [str(error)]
    return validate_candidate_ledger(
        ledger,
        expected_version=version,
        expected_payload_digest=payload,
        expected_fleet_digest=fleet_digest,
        expected_validator_digest=validator,
        consumers=consumers,
    )


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Install the current pack candidate into disposable fleet clones, "
            "run compatibility checks, and write an all-pass release ledger."
        )
    )
    parser.add_argument("--fleet", type=Path, default=DEFAULT_FLEET_MANIFEST)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_PACK_MANIFEST)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument(
        "--consumer",
        action="append",
        help="limit diagnostics to this consumer; partial runs never write the ledger",
    )
    parser.add_argument(
        "--check-ledger",
        action="store_true",
        help="verify existing evidence without cloning or running consumer checks",
    )
    parser.add_argument("--json", action="store_true", help="print JSON results")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.check_ledger:
            if args.consumer:
                raise FleetConfigError("--check-ledger cannot be combined with --consumer")
            errors = check_ledger(
                manifest_path=args.manifest,
                fleet_path=args.fleet,
                ledger_path=args.ledger,
            )
            if errors:
                for error in errors:
                    print(f"candidate ledger error: {error}", file=sys.stderr)
                return 1
            print("candidate ledger: valid for the current pack payload and fleet")
            return 0

        version, payload, fleet_digest, validator, consumers = current_evidence(
            args.manifest, args.fleet
        )
        selected = set(args.consumer or [])
        if selected:
            known = {consumer.name for consumer in consumers}
            unknown = sorted(selected - known)
            if unknown:
                raise FleetConfigError(
                    f"unknown fleet consumer(s): {', '.join(unknown)}"
                )
            consumers = [consumer for consumer in consumers if consumer.name in selected]

        pack_root = args.manifest.resolve().parent
        with tempfile.TemporaryDirectory(prefix="sd-pack-fleet-candidate-") as tempdir:
            work_root = Path(tempdir)
            artifacts = run_thin_artifact_lane(
                pack_root=pack_root,
                work_root=work_root,
                python_executable=Path(sys.executable),
                env=command_environment(Path(sys.executable), work_root),
            )
            results = [
                validate_consumer(
                    consumer,
                    pack_root=pack_root,
                    work_root=work_root,
                    python_executable=Path(sys.executable),
                    machine_home=artifacts.machine_home,
                )
                for consumer in consumers
            ]

        if args.json:
            print(
                json.dumps(
                    {
                        "thinArtifacts": [
                            {
                                "name": step.name,
                                "status": step.status,
                                "durationSeconds": round(step.duration_seconds, 2),
                                "detail": step.detail,
                            }
                            for step in artifacts.steps
                        ],
                        "consumers": [
                            {
                                "name": result.consumer.name,
                                "github": result.consumer.github,
                                "rolloutPriority": result.consumer.rollout_priority,
                                "status": result.status,
                                "baseCommit": result.base_commit,
                                "durationSeconds": round(result.duration_seconds, 2),
                                "detail": result.detail,
                                "reasons": list(result.reasons),
                                "notes": list(result.notes),
                            }
                            for result in results
                        ],
                    },
                    indent=2,
                )
            )
        else:
            print(f"sd-ai-command-pack candidate: {version}")
            for step in artifacts.steps:
                print(f"{step.status:11} thin artifact: {step.name} ({step.duration_seconds:.1f}s)")
                print(f"  {step.detail}")
            for result in results:
                print(
                    f"{result.status:11} P{result.consumer.rollout_priority:02d} "
                    f"{result.consumer.github} ({result.duration_seconds:.1f}s)"
                )
                print(f"  {result.detail}")
                for reason in result.reasons:
                    print(f"  blocked: {reason}")
                for note in result.notes:
                    print(f"  note: {note}")

        # The artifact lane is pack-owned and consumer-independent, so its
        # failure is reported once and blamed on nobody. It also suppresses the
        # ledger on its own: a ledger written while the plugin does not validate
        # would certify consumer results against artifacts that were never good.
        if not artifacts.ok:
            for step in artifacts.failures:
                print(
                    f"thin artifact step {step.name!r} is {step.status}",
                    file=sys.stderr,
                )
            print(
                f"thin artifact validation failed for {len(artifacts.failures)} "
                "step(s); ledger was not updated",
                file=sys.stderr,
            )
            return 1

        # `blocked` is deliberately not a failure. It records a consumer-owned
        # precondition the pack cannot fix -- references the pack does not own,
        # a dirty worktree -- and failing on it would make every pack release
        # hostage to eight consumer backlogs. The ledger still records the row,
        # with its reasons, so nothing is certified that was not run.
        failures = [
            result
            for result in results
            if result.status not in (STATUS_PASSED, STATUS_BLOCKED)
        ]
        if failures:
            print(
                f"candidate validation failed for {len(failures)} consumer(s); "
                "ledger was not updated",
                file=sys.stderr,
            )
            return 1
        if selected:
            print("candidate diagnostics passed; partial run did not update the ledger")
            return 0

        write_ledger(
            args.ledger,
            ledger_content(
                version=version,
                payload_digest=payload,
                fleet_digest=fleet_digest,
                validator_digest=validator,
                results=results,
            ),
        )
        print(f"candidate ledger: wrote {args.ledger}")
        return 0
    except FleetConfigError as error:
        print(f"candidate validation error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
