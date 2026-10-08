"""The Jev shadow stages, outside the review lane's line cap: they record Jev's answer and never read it."""

from __future__ import annotations

import json
import pathlib
import shutil
import sys
from typing import Any, Mapping, Sequence, TextIO

import sd_jev
import sd_lib

# --------------------------------------------------------------------------
# Shadow stages: review triage (sd:2092), and the `sd task add` duplicate
# hint in `bin/sd_work.py` (sd:2093), which shares these helpers.
#
# A shadow call passes `--shadow`: `jev` prints the answer handed to it, exits
# 0, and records its own judgment beside it in the ledger. Nothing reads that
# judgment back, so no output, exit code or status changes.
#
# **Local Kev by default** (`--local-only`), as `bin/sd-docs-lint` does: a
# public origin does not make a review summary or a tracker title public.
# Hosted Jev needs `SD_JEV_SHADOW_HOSTED=1` in the machine's environment, which
# no commit can set. A failed local call sends nothing and is never retried.
#
# **Hosted Jev reads public repositories only.** GitHub is asked only under the
# opt-in, after `jev enabled` answers, so the local path asks it nothing. No
# github.com `origin`, no `gh`, a failing `gh` and `private: true` all read as
# private, silently. A `jev` that fails is loud and stops the stage.
# --------------------------------------------------------------------------

TRIAGE_STAGE = "JEV_SD_REVIEW_TRIAGE"
HOSTED_OPT_IN = "SD_JEV_SHADOW_HOSTED"
#: sd-review classifies no finding itself, so its shadow answer is no
#: criterion: Jev's pick is counted, not compared.
UNTRIAGED = "untriaged"
#: Findings triaged per review, one bounded call each; characters per text sent.
MAX_TRIAGE = 10
MAX_TEXT = 1000
TRIAGE_CRITERIA = {
    "correctness": "the finding names a defect that makes the code give a wrong result",
    "robustness": "the finding names a failure under unusual input or load or environment",
    "style": "the finding is about wording or naming or layout and changes no behaviour",
    "likely-wrong": "the finding misreads the code and its claim does not hold",
}


def shadow_ready(stage: str, caller: str, root: str | pathlib.Path, env: Mapping[str, str],
                 stream: TextIO) -> tuple[str, tuple[str, str, str], list[str]] | None:
    """`(jev, github head, scope)` when a shadow reading may be taken for `root`; hosted, for a public one only.

    The switch and `jev` come first, so a stage that is off probes nothing."""

    binary = shutil.which(sd_jev.COMMAND, path=env.get("PATH"))
    if sd_lib.jev_stage_off(env.get(stage)) or binary is None:
        return None
    head = sd_lib.github_head(root)
    if head is None:
        return None
    scope = [] if env.get(HOSTED_OPT_IN, "").strip() == "1" else ["--local-only"]
    env = sd_lib.jev_env(env, caller)
    gate = sd_jev._jev_run([binary, "enabled", stage, "--record", "--caller", caller, *scope], env)
    if gate.returncode not in (0, 3):
        sd_jev.shadow_stopped(stream, caller, stage, f"`{sd_jev.COMMAND} enabled` exited {gate.returncode}")
    if gate.returncode != 0:
        return None
    if scope:
        return binary, head, scope
    gh = shutil.which("gh", path=env.get("PATH"))
    if gh is None:
        return None
    # Pinned: `GH_HOST` would ask another host, whose public namesake vouches for nothing.
    visible = sd_jev._jev_run([gh, "api", "--hostname", "github.com", f"repos/{head[0]}/{head[1]}",
                               "--jq", ".private"], env)
    return (binary, head, scope) if visible.returncode == 0 and visible.stdout.strip() == "false" else None


def shadow_ask(binary: str, question: str, criteria: str, state: str, env: Mapping[str, str],
               stream: TextIO, *, caller: str, stage: str, answer: str, subject: str,
               scope: Sequence[str]) -> bool:
    """Ask one shadow `choice`; say so on `stream` and return False when it failed."""

    argv = [binary, "choice", question, "--criteria", criteria, "--state", "-",
            "--state-format", "json", "--caller", caller, "--id", stage.lower(), "--stage", stage,
            "--shadow", answer, *(["--subject", subject] if len(subject) <= 96 else []), *scope]
    code = sd_jev._jev_run(argv, sd_lib.jev_env(env, caller), state).returncode
    if code != 0:
        sd_jev.shadow_stopped(stream, caller, stage, f"`{sd_jev.COMMAND}` exited {code}")
    return code == 0


def shadow_safely(caller: str, stage: str, stream: TextIO, stage_body: Any, *args: Any) -> None:
    """Run one shadow stage; any exception it raises is a note, never the command's outcome."""

    try:
        stage_body(*args)
    except Exception as error:  # noqa: BLE001 -- a shadow stage must not change what the command does
        sd_jev.shadow_stopped(stream, caller, stage, f"{type(error).__name__}: {error}")


def record_triage(findings: Sequence[Mapping[str, Any]], env: Mapping[str, str],
               root: str | pathlib.Path, stream: TextIO | None = None) -> None:
    """Record Jev's kind for each of the first `MAX_TRIAGE` findings; return nothing.

    Sent per finding: its severity, disposition, family, repository-relative
    path and summary. No diff, no file contents, no author.
    """

    note = sys.stderr if stream is None else stream
    shadow_safely(sd_jev.CALLER, TRIAGE_STAGE, note, _triage, findings, env, root, note)


def _triage(findings: Sequence[Mapping[str, Any]], env: Mapping[str, str],
            root: str | pathlib.Path, note: TextIO) -> None:
    ready = shadow_ready(TRIAGE_STAGE, sd_jev.CALLER, root, env, note) if findings else None
    if ready is None:
        return
    binary, head, scope = ready
    criteria = ",".join(f"{name}={text}" for name, text in TRIAGE_CRITERIA.items())
    for index, finding in enumerate(findings[:MAX_TRIAGE], 1):
        state = json.dumps({key: str(finding.get(key, ""))[:MAX_TEXT] for key in
                            ("severity", "disposition", "family", "path", "summary")}, sort_keys=True)
        if not shadow_ask(binary, "What kind of code review finding is this?", criteria, state, env, note,
                          caller=sd_jev.CALLER, stage=TRIAGE_STAGE, answer=UNTRIAGED, scope=scope,
                          subject=f"sd-review-triage:{head[0]}.{head[1]}:{head[2][:12]}:{index}"):
            return
