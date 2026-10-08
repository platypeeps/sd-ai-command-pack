"""An optional Jev reading of the review tier, on wherever Jev can answer.

`sd_route.route` decides the tier from the policy and the changed paths, and it
stays the floor: this module is a second opinion over a diff shape the
policy's globs cannot see. It is experimental and additive. No output changes
unless a `jev` on `PATH` says it can answer on this machine.

**Jev may raise the tier, never lower it** (sd:2132). An answer below the
routed tier -- `skip` included -- keeps the routed tier and records what Jev
said as `below_routed`. Jev orders, routes and triages; it never removes a
review the policy asked for.

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

**No per-repository opt-in, unlike `bin/sd-docs-lint`.** That gate's reading
sends a repository's own prose, so it asks the local Kev only (sd:2762) unless
`.github/sd-docs-lint.json` opts in to hosted Jev (sd:1304). This one sends the
metadata above and no prose, so it keeps its default. What the two gates share
is unchanged and must stay so: `sd_lib.jev_stage_off` is the one kill switch,
which only ever subtracts, and an absent `jev` or `jev enabled` exiting 3 is
silent in both.

**Exit 0 is not an answer.** `--fallback` prints what it was given and exits 0
whenever Jev is switched off, unkeyed or failing, so the exit code alone cannot
tell a judgment from a shrug. The fallback here is `FALLBACK`, a token no tier
can be, and getting it back is read as "nothing was judged". `--unsure-below`
is the same shape for a judgment Jev made but does not stand behind.

**The routed tier is the baseline** (sd:2359). `jev` used to compute a row's
`changed` by comparing its answer with `--fallback`, and the fallback here is a
token no answer can equal, so every sd-review row in the judgment ledger said
`changed=yes` whatever Jev chose. `--baseline` hands over the tier `sd_route`
picked: `jev` records it as a second row under the same pair id and compares
its answer with that instead, so `changed` says whether Jev disagreed with the
routing and the ledger holds a paired sample. `--baseline-ms` is how long
`sd_route.route` took, when the caller timed it. Neither flag changes what Jev
prints or what this module does with it; the floor and every decline rule
below hold as they did.

A `jev` older than sd:2357 has no `--baseline` and its argparse refuses the
flag with exit 2 before anything is sent or recorded. That one refusal is asked
once more without the two baseline flags, and the answer is read as before.
Treated as a failure instead, it would have made every reading on such a machine
a loud decline. A refusal naming any other flag is a real fault and stays loud.
`jev choice` has no `--help` and `jev` no version verb to ask in advance, so the
refusal itself is the cheapest probe: a current `jev` never pays for it.

**Failure is never quiet and never looks like an answer.** A missing command, a
`jev` that declines, a non-zero exit, a timeout, the fallback token, `unsure`
and an answer outside the policy's tiers all land on the same line: keep the
routed tier, write one note to stderr saying which of those happened, and
return no record. A run with no record took no reading, and the caller's exit
code and findings are not this module's to change.

**Shadow stages live at the end of this file**: review-finding triage
(sd:2092) and the helpers `sd task add` uses for its duplicate hint (sd:2093).
They record Jev's answer and never read it, for public repositories only.
"""

from __future__ import annotations

import json
import pathlib
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
    root: str | None = None,
    baseline_ms: int | None = None,
) -> tuple[str, dict[str, Any] | None]:
    """The tier to review at, and the record of the reading that moved it.

    Returns the routed `tier` unchanged and `None` whenever the reading was not
    taken, which is every case but one. The record is `None` rather than a row
    saying "declined" on purpose: the caller puts it in its result object only
    when it exists, so a run that did not take a reading emits the same bytes
    it emitted before this module existed. `baseline_ms` is how long the
    routing that chose `tier` took, for the paired ledger row only.
    """

    note = sys.stderr if stream is None else stream
    if sd_lib.jev_stage_off(env.get(STAGE)):
        return tier, None
    binary = shutil.which(COMMAND, path=env.get("PATH"))
    if binary is None:
        return tier, None
    env = sd_lib.jev_env(env, CALLER)
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
    argv = _jev_argv(binary, fallback, options, _jev_subject(root), tier, baseline_ms)
    state = _jev_state(paths, lines, reason)
    answer = _jev_run(argv, env, state)
    if _jev_lacks_baseline(answer):
        answer = _jev_run(_jev_without_baseline(argv), env, state)
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
    if options.index(chosen) < options.index(tier):
        return tier, {"routed_tier": tier, "tier": tier, "moved": False, "source": "judged",
                      "below_routed": chosen}
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


def _jev_subject(root: str | None) -> str | None:
    """The judged change, for the ledger only (sd:2107): `jev --subject` records it
    as the row's question id and never sends it. None past the ledger's 96 characters."""

    head = sd_lib.github_head(root) if root else None
    subject = f"sd-review-tier:{head[0]}.{head[1]}:{head[2][:12]}" if head else ""
    return subject if 0 < len(subject) <= 96 else None


def _jev_argv(binary: str, fallback: str, options: Sequence[str],
              subject: str | None = None, baseline: str | None = None,
              baseline_ms: int | None = None) -> list[str]:
    """The one place the `jev` command line is written, and it is checked.

    `choice` takes its instructions positionally and its named set in
    `--criteria`; the state it judges over arrives on stdin, which is where
    `--state -` reads it. `--fallback` exits 0 with `fallback` on stdout rather
    than failing, so the caller above reads that token and not the exit code.
    `--baseline` is the routed tier, for the ledger's paired row (sd:2359); it
    comes last with its timing so `_jev_without_baseline` can drop both.
    """

    return [binary, "choice", "How deeply should this code change be reviewed?",
            "--criteria", _jev_criteria(options),
            "--unsure-below", UNSURE_BELOW,
            "--state", "-", "--state-format", "json", "--caller", CALLER,
            "--id", "sd-review-tier", "--stage", STAGE, "--fallback", fallback,
            *(["--subject", subject] if subject else []),
            *(["--baseline", baseline] if baseline is not None else []),
            *(["--baseline-ms", str(baseline_ms)]
              if baseline is not None and baseline_ms is not None else [])]


#: The flags a `jev` from before sd:2357 does not know, each taking one value.
BASELINE_FLAGS = ("--baseline", "--baseline-ms")


def _jev_lacks_baseline(answer: subprocess.CompletedProcess[str]) -> bool:
    """Whether `jev` refused the baseline flags and nothing else.

    Exit 2 with argparse's `unrecognized arguments:` line is a refusal made
    before any request or ledger row, so asking again cannot double-count.
    Every word it lists must be a baseline flag or a value that came with one;
    an older `jev` that also lacks some other flag is a fault, and stays loud.
    """

    if answer.returncode != 2:
        return False
    lines = [line for line in (answer.stderr or "").splitlines()
             if "unrecognized arguments:" in line]
    if not lines:
        return False
    words = lines[-1].split("unrecognized arguments:", 1)[1].split()
    flags = [word for word in words if word.startswith("--")]
    return bool(flags) and all(flag in BASELINE_FLAGS for flag in flags)


def _jev_without_baseline(argv: Sequence[str]) -> list[str]:
    """`argv` less each baseline flag and the value that follows it."""

    kept: list[str] = []
    skip = False
    for word in argv:
        if skip:
            skip = False
        elif word in BASELINE_FLAGS:
            skip = True
        else:
            kept.append(word)
    return kept


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
    """Run one bounded command, turning every way it can fail into an exit code.
    Bytes that do not decode are replaced, never raised (review of 46529bae2)."""

    try:
        return subprocess.run(list(argv), env=dict(env), input=state, capture_output=True,
                              text=True, errors="replace", timeout=TIMEOUT_SECONDS, check=False)
    except (OSError, subprocess.SubprocessError) as error:
        return subprocess.CompletedProcess(list(argv), 1, "", str(error))


# --------------------------------------------------------------------------
# Shadow stages: review triage here (sd:2092), and the `sd task add` duplicate
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
# **Public repositories only**, on either path. GitHub is asked after
# `jev enabled` answers, so a machine without Jev asks it nothing. No
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
    """`(jev, github head, scope)` when a shadow reading may be taken for public `root`.

    The switch and `jev` come first, so a stage that is off probes nothing."""

    binary = shutil.which(COMMAND, path=env.get("PATH"))
    if sd_lib.jev_stage_off(env.get(stage)) or binary is None:
        return None
    head = sd_lib.github_head(root)
    if head is None:
        return None
    scope = [] if env.get(HOSTED_OPT_IN, "").strip() == "1" else ["--local-only"]
    env = sd_lib.jev_env(env, caller)
    gate = _jev_run([binary, "enabled", stage, "--record", "--caller", caller, *scope], env)
    if gate.returncode not in (0, 3):
        shadow_stopped(stream, caller, stage, f"`{COMMAND} enabled` exited {gate.returncode}")
    gh = shutil.which("gh", path=env.get("PATH"))
    if gate.returncode != 0 or gh is None:
        return None
    # Pinned: `GH_HOST` would ask another host, whose public namesake vouches for nothing.
    visible = _jev_run([gh, "api", "--hostname", "github.com", f"repos/{head[0]}/{head[1]}",
                        "--jq", ".private"], env)
    return (binary, head, scope) if visible.returncode == 0 and visible.stdout.strip() == "false" else None


def shadow_ask(binary: str, question: str, criteria: str, state: str, env: Mapping[str, str],
               stream: TextIO, *, caller: str, stage: str, answer: str, subject: str,
               scope: Sequence[str]) -> bool:
    """Ask one shadow `choice`; say so on `stream` and return False when it failed."""

    argv = [binary, "choice", question, "--criteria", criteria, "--state", "-",
            "--state-format", "json", "--caller", caller, "--id", stage.lower(), "--stage", stage,
            "--shadow", answer, *(["--subject", subject] if len(subject) <= 96 else []), *scope]
    code = _jev_run(argv, sd_lib.jev_env(env, caller), state).returncode
    if code != 0:
        shadow_stopped(stream, caller, stage, f"`{COMMAND}` exited {code}")
    return code == 0


def shadow_safely(caller: str, stage: str, stream: TextIO, stage_body: Any, *args: Any) -> None:
    """Run one shadow stage; any exception it raises is a note, never the command's outcome."""

    try:
        stage_body(*args)
    except Exception as error:  # noqa: BLE001 -- a shadow stage must not change what the command does
        shadow_stopped(stream, caller, stage, f"{type(error).__name__}: {error}")


def shadow_stopped(stream: TextIO, caller: str, stage: str, why: str) -> None:
    stream.write(f"{caller}: the Jev shadow reading stopped: {why}; nothing it does "
                 f"changed (set {stage}=0 to stop asking)\n")


def jev_triage(findings: Sequence[Mapping[str, Any]], env: Mapping[str, str],
               root: str | pathlib.Path, stream: TextIO | None = None) -> None:
    """Record Jev's kind for each of the first `MAX_TRIAGE` findings; return nothing.

    Sent per finding: its severity, disposition, family, repository-relative
    path and summary. No diff, no file contents, no author.
    """

    note = sys.stderr if stream is None else stream
    shadow_safely(CALLER, TRIAGE_STAGE, note, _triage, findings, env, root, note)


def _triage(findings: Sequence[Mapping[str, Any]], env: Mapping[str, str],
            root: str | pathlib.Path, note: TextIO) -> None:
    ready = shadow_ready(TRIAGE_STAGE, CALLER, root, env, note) if findings else None
    if ready is None:
        return
    binary, head, scope = ready
    criteria = ",".join(f"{name}={text}" for name, text in TRIAGE_CRITERIA.items())
    for index, finding in enumerate(findings[:MAX_TRIAGE], 1):
        state = json.dumps({key: str(finding.get(key, ""))[:MAX_TEXT] for key in
                            ("severity", "disposition", "family", "path", "summary")}, sort_keys=True)
        if not shadow_ask(binary, "What kind of code review finding is this?", criteria, state, env, note,
                          caller=CALLER, stage=TRIAGE_STAGE, answer=UNTRIAGED, scope=scope,
                          subject=f"sd-review-triage:{head[0]}.{head[1]}:{head[2][:12]}:{index}"):
            return
