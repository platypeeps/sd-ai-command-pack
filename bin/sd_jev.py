"""An optional Jev reading of the review tier, on wherever Jev can answer.

`sd_route.route` decides the tier from the policy and the changed paths, and it
stays the decision: this module is a second opinion over a diff shape the
policy's globs cannot see. It is experimental and additive. No output changes
unless a `jev` on `PATH` says it can answer on this machine.

`jev` lives in a private companion repository and is absent on most machines.
Absence is the ordinary case and not a fault, so it is silent: a module that
announced a missing optional companion would put a line in every review on
every machine that does not have it, forever. `jev enabled` exiting 3 is the
same not-configured case, however `jev` reached it, and is equally silent.
Any other failure is loud on stderr, because a lane that quietly stops running
is the defect this rule exists to prevent.

**What leaves the machine**, and only when the reading is taken: the tier names
the *running* checkout's policy declares -- the four standard ones with a fixed
description, any tier a repository invented as a bare name, so that name is the
whole of what arrives -- the repository-relative paths the change touches (at
most `MAX_PATHS` of them, then a count), the number of lines the change moves,
and the routing reason `sd_route` composed from those same inputs. No absolute
path, no repository or branch name, no author, no commit message, no file
contents and no diff text.

**Exit 0 is not an answer.** `--fallback` prints what it was given and exits 0
whenever Jev is switched off, unkeyed or failing, so the exit code alone cannot
tell a judgment from a shrug. The fallback here is `FALLBACK`, a token no tier
can be, and getting it back is read as "nothing was judged". `--unsure-below`
is the same shape for a judgment Jev made but does not stand behind.

**Failure is never quiet and never looks like an answer.** A missing command, a
`jev` that declines, a non-zero exit, a timeout, the fallback token, `unsure`
and an answer outside the policy's tiers all land on the same line: keep the
routed tier, write one note to stderr saying which of those happened, and
return no record. A run with no record took no reading, and the caller's exit
code and findings are not this module's to change.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from typing import Any, Mapping, Sequence, TextIO

import sd_lib

#: This stage's switch. **Unset means on**, and it only ever subtracts: setting
#: it cannot make a reading happen that `jev` itself would decline. It used to
#: have to be `1`, which is the defaulted-to-off failure -- a keyed machine ran
#: none of this, for want of an export nobody had written.
STAGE = "JEV_SD_REVIEW"

#: Resolved on the ``PATH`` of the environment the run was handed, never from a
#: path written down here: this repository is public and has no fixed relative
#: path to a private companion.
COMMAND = "jev"
#: This lane's name in the judgment ledger, beside `STAGE` (sd:1253).
CALLER = "sd-review"

#: Both calls are bounded. The gate answers locally and the judgment is a
#: single request, so a run that hangs is a fault and not slow progress.
TIMEOUT_SECONDS = 20

#: How many changed paths the state carries before it says how many were cut.
MAX_PATHS = 40

#: Below this confidence `choice` prints `UNSURE` instead of a tier, which is
#: read here as no answer. A tier picked on a coin flip is worse than the
#: deterministic routing it would displace.
UNSURE_BELOW = "0.6"
UNSURE = "unsure"

#: What `--fallback` prints when Jev is off, unkeyed or failing. It exits 0
#: either way, so this token is the only thing separating "judged" from "did
#: not run"; `_jev_fallback` keeps it impossible for a policy tier to collide.
FALLBACK = "sd-review-took-no-reading"

#: Each tier as a criterion Jev can judge against. A bare name judges worse
#: than a described one, so the four standard tiers carry a description and a
#: tier a repository invented falls back to its bare name. No description may
#: contain `,` or `=`, which separate the criteria.
TIER_CRITERIA = {
    "skip": "no review is warranted because the change cannot alter behaviour",
    "cheap": "one quick read is enough because the change is small and local",
    "standard": "an ordinary careful review of the changed logic",
    "deep": "the change is risky or wide-reaching or touches security"
            " and needs the most thorough review",
}


def jev_tier(
    tier: str,
    order: Sequence[str],
    paths: Sequence[str],
    lines: int,
    reason: str,
    env: Mapping[str, str],
    stream: TextIO | None = None,
) -> tuple[str, dict[str, Any] | None]:
    """The tier to review at, and the record of the reading that moved it.

    Returns the routed `tier` unchanged and `None` whenever the reading was not
    taken, which is every case but one. The record is `None` rather than a row
    saying "declined" on purpose: the caller puts it in its result object only
    when it exists, so a run that did not take a reading emits the same bytes
    it emitted before this module existed.
    """

    note = sys.stderr if stream is None else stream
    if sd_lib.jev_stage_off(env.get(STAGE)):
        return tier, None
    binary = shutil.which(COMMAND, path=env.get("PATH"))
    if binary is None:
        return tier, None
    gate = _jev_run([binary, "enabled", STAGE, "--record", "--caller", CALLER], env)
    # 3 is "cannot answer here" and nothing narrower: `jev` collapses switched
    # off, no key, a placeholder key and a malformed timeout into this one code
    # on purpose. The same not-configured case as an absent binary, and silent
    # for the same reason.
    if gate.returncode == 3:
        return tier, None
    if gate.returncode != 0:
        return _jev_declined(tier, note, f"`{COMMAND} enabled` exited {gate.returncode}")
    options = [str(name) for name in order]
    fallback = _jev_fallback(options)
    answer = _jev_run(_jev_argv(binary, fallback, options), env,
                      _jev_state(paths, lines, reason))
    chosen = (answer.stdout or "").strip()
    if answer.returncode != 0:
        return _jev_declined(tier, note, f"`{COMMAND}` exited {answer.returncode}")
    if chosen == fallback:
        why = (answer.stderr or "").strip().splitlines()
        return _jev_declined(tier, note, f"Jev judged nothing: {why[-1] if why else 'no reason given'}")
    if chosen == UNSURE and UNSURE not in options:
        return _jev_declined(tier, note, f"Jev was unsure below {UNSURE_BELOW} confidence")
    if chosen not in options:
        return _jev_declined(tier, note, f"answer {chosen!r} is not one of {', '.join(options)}")
    return chosen, {"routed_tier": tier, "tier": chosen, "moved": chosen != tier, "source": "judged"}


def _jev_fallback(options: Sequence[str]) -> str:
    """A fallback token no declared tier can be, so the two never read alike."""

    token = FALLBACK
    while token in options:
        token += "-x"
    return token


def _jev_declined(tier: str, stream: TextIO, why: str) -> tuple[str, None]:
    """Keep the routed tier and say why the reading the operator asked for failed."""

    stream.write(f"sd-review: no Jev tier reading was taken: {why}; "
                 f"keeping the routed tier {tier} (set {STAGE}=0 to stop asking)\n")
    return tier, None


def _jev_argv(binary: str, fallback: str, options: Sequence[str]) -> list[str]:
    """The one place the `jev` command line is written, and it is checked.

    `choice` takes its instructions positionally and its named set in
    `--criteria`; the state it judges over arrives on stdin, which is where
    `--state -` reads it. `--fallback` exits 0 with `fallback` on stdout rather
    than failing, so the caller above reads that token and not the exit code.
    """

    return [binary, "choice", "How deeply should this code change be reviewed?",
            "--criteria", _jev_criteria(options),
            "--unsure-below", UNSURE_BELOW,
            "--state", "-", "--state-format", "json", "--caller", CALLER,
            "--id", "sd-review-tier", "--stage", STAGE, "--fallback", fallback]


def _jev_criteria(options: Sequence[str]) -> str:
    """The tiers as `name=description` pairs, bare for a tier this file cannot describe."""

    return ",".join(
        f"{name}={TIER_CRITERIA[name]}" if name in TIER_CRITERIA else str(name)
        for name in options)


def _jev_state(paths: Sequence[str], lines: int, reason: str) -> str:
    """The state, and the whole of what leaves this machine besides the tiers."""

    shown = [str(path) for path in paths][:MAX_PATHS]
    return json.dumps({
        "changed_paths": shown,
        "changed_paths_omitted": len(paths) - len(shown),
        "path_count": len(paths),
        "lines_moved": lines,
        "deterministic_routing_said": reason,
    }, sort_keys=True)


def _jev_run(argv: Sequence[str], env: Mapping[str, str],
             state: str | None = None) -> subprocess.CompletedProcess[str]:
    """Run one bounded command, turning every way it can fail into an exit code."""

    try:
        return subprocess.run(list(argv), env=dict(env), input=state, capture_output=True,
                              text=True, timeout=TIMEOUT_SECONDS, check=False)
    except (OSError, subprocess.SubprocessError) as error:
        return subprocess.CompletedProcess(list(argv), 1, "", str(error))
