#!/usr/bin/env python3
"""The findings zizmor's default persona gates out, enumerated and decided.

`zizmor --offline .github/workflows/` is the gate, and it has been reporting

    No findings to report. Good job! (3 suppressed)

for as long as anyone has looked. That parenthesis is not a decision this
repository made. There is no zizmor configuration file here and no
`# zizmor: ignore[...]` comment in any workflow, so nothing was suppressed by
hand: three findings simply carry a persona above the default one, and the
default persona drops them. Nobody had to agree with any of them for the gate
to be green, and nothing said what the three were except a sentence in a
tracked-work note, which is a list and goes stale the moment a workflow moves.

So this asks zizmor. It runs the auditor persona, which is the widest one,
keeps every finding whose own `persona` is not `Regular` -- exactly the set the
gate drops -- and requires that set to be the set named in `DECIDED` below,
in both directions:

* a persona-gated finding with no decision fails, so a workflow edit that
  earns a fourth one cannot pass in silence;
* a decision with no finding fails, so a decision outlives neither the line it
  was about nor an upgrade that retires the audit.

The key is the audit's identifier, the workflow, the YAML route to the thing
it points at, and the text it matched -- not a line number, because a line
number moves whenever anything above it is edited and would make this a gate
on where the findings are rather than on what they are. The concrete line is
printed, never matched.

Run by `make audit` (so by `make check`) and by the `lint` job of
`.github/workflows/tests.yml`, in both cases next to the plain gate whose
count it explains.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import pathlib
import shutil
import subprocess
import sys

#: The persona every finding the default gate reports carries. Anything else
#: is dropped by that gate and is what this script is about.
DEFAULT_PERSONA = "Regular"

WORKFLOWS = ".github/workflows"

#: The two route components zizmor emits, and what each carries. A component
#: this does not know is a shape the script has not been read against, and
#: rendering its value anyway would key findings on a guess.
ROUTE_VARIANTS = {"Key": str, "Index": int}


@dataclasses.dataclass(frozen=True)
class Key:
    """What identifies a finding across edits: never a line, never a column."""

    ident: str
    path: str
    route: str
    feature: str

    def __str__(self) -> str:
        return f"{self.ident} {self.path}{self.route} -> {self.feature}"


@dataclasses.dataclass(frozen=True)
class Decision:
    """A persona-gated finding this repository has looked at, and the reason."""

    key: Key
    reason: str


#: What a job with no `name:` is called: `anonymous-definition` is about these
#: two and nothing else, so the reason is written once and cited twice.
JOB_NAME_REASON = (
    "Kept. A job with no `name:` is reported under its YAML key, which is what "
    "both of this repository's gating status contexts are -- `unittest "
    "(ubuntu-latest, 3.14)` and `lint`. `bin/sd_ship_remote.py` reads those "
    "contexts off the branch protection object before it reads a pull "
    "request's checks, and `CONTRIBUTING.md` says the consequence in as many "
    "words: \"requiring a name no job produces would pin a context that never "
    "reports and block every pull request\". So a `name:` that reads better "
    "than the key renames the context and breaks the merge path, and a `name:` "
    "equal to the key is the same word twice. Informational, and zizmor's own "
    "persona for it is Pedantic.")

#: Every finding zizmor's default persona drops, with why it stays dropped.
#: Add to this only after reading the audit's documentation; an entry whose
#: finding is gone fails, so nothing here can be a leftover.
#:
#: What is deliberately not here: `self-repository`, the audit zizmor 1.30.0
#: added for a `uses: ./...` reference. It is answered by the reference, not
#: by a decision. `.github/workflows/sd-review-route.yml` names the pack's
#: action as `$/actions/review-route` since item 839, and the audit is what
#: that was for: `./` resolves against the runner's workspace, which the
#: checkout step above it fills with the pull request's head, so the pull
#: request would supply the action that routes it. And it could not be here
#: even if it were wanted, because it is not a persona-gated finding: zizmor
#: reports it at the default persona, so on a `./` reference it reddens the
#: plain gate beside this script, and a `Decision` for it would reconcile as
#: "decided but not found" at every version. The pin in
#: `requirements-security.txt` is at or above 1.30.0 so the gate can see the
#: audit at all; `tests/test_zizmor_persona_decisions.py` holds that floor and
#: the reference's shape, and either moving fails by name (item 933).
DECIDED: tuple[Decision, ...] = (
    Decision(
        key=Key(ident="anonymous-definition",
                path=f"{WORKFLOWS}/tests.yml",
                route="/jobs/unittest",
                feature="unittest"),
        reason=JOB_NAME_REASON),
    Decision(
        key=Key(ident="anonymous-definition",
                path=f"{WORKFLOWS}/tests.yml",
                route="/jobs/lint",
                feature="lint"),
        reason=JOB_NAME_REASON),
    Decision(
        key=Key(ident="anonymous-definition",
                path=f"{WORKFLOWS}/tests.yml",
                route="/jobs/sd-db-main-canary",
                feature="sd-db-main-canary"),
        reason=JOB_NAME_REASON),
    Decision(
        key=Key(ident="secrets-outside-env",
                path=f"{WORKFLOWS}/tests.yml",
                route="/jobs/sd-db-main-canary",
                feature="secrets.SYSTEM_REPO_TOKEN"),
        reason=(
            "The same acceptance as the unittest job's use of this token, on "
            "the same trusted-writer threat model: the canary (sd:1542) runs "
            "on the same triggers, reads the same private repository with "
            "the same token and `persist-credentials: false`, and differs "
            "only in checking out system `main` instead of the pin. A fork's "
            "pull request receives no secret, so every run that reads it "
            "starts from a head a writer here pushed.")),
    Decision(
        key=Key(ident="secrets-outside-env",
                path=f"{WORKFLOWS}/tests.yml",
                route="/jobs/unittest",
                feature="secrets.SYSTEM_REPO_TOKEN"),
        reason=(
            "Accepted on a trusted-writer threat model, which is named here "
            "rather than implied, and this is the one of the three worth "
            "re-reading when anything about the job changes. The audit wants "
            "the secret behind a GitHub environment, so that environment "
            "protection rules govern who can start a run that reads it. What "
            "stands in for that is the population who can start such a run, "
            "and nothing narrower. The workflow runs on `pull_request` and on "
            "`push` to `main`, and GitHub hands no secret to a `pull_request` "
            "run from a fork, so every head that reaches this token is a head "
            "in this repository pushed by somebody who already has write "
            "access. Such a writer controls the workflow YAML on their own "
            "branch and can therefore print the secret whatever this job does "
            "with it, so the acceptance is exactly this: every writer here is "
            "trusted with it. The mitigations inside the job are real but do "
            "not carry that weight and are not offered as if they did -- the "
            "token is referenced by one step, a checkout of "
            "`platypeeps/system` at a pinned commit, and `persist-credentials: "
            "false` keeps that checkout's credential out of the workspace's "
            "git config for the steps after it, which stops a later step "
            "picking it up by accident and stops nothing a later step does on "
            "purpose. An environment would narrow the population to \"and "
            "approved by a named reviewer\", at the price of a manual approval "
            "on every run of the default test lane, which is declined while "
            "every writer is trusted. What would reopen it: a writer this "
            "repository does not trust with a `platypeeps/system` token, this "
            "repository taking fork pull requests with secrets, this job "
            "running a third party's code, or the token being read anywhere "
            "but that one pinned checkout.")),
)


@dataclasses.dataclass(frozen=True)
class Found:
    """A finding from the run: its key, and where it was this time."""

    key: Key
    persona: str
    severity: str
    line: int

    def __str__(self) -> str:
        return f"{self.key} ({self.severity.lower()}, persona {self.persona}, {self.path_line})"

    @property
    def path_line(self) -> str:
        return f"{self.key.path}:{self.line}"


def render_route(route: object) -> str:
    """`[{"Key": "jobs"}, {"Key": "lint"}]` as `/jobs/lint`, indexes included."""

    if not isinstance(route, list):
        raise ValueError(f"route is not a list: {route!r}")
    parts = []
    for component in route:
        if not isinstance(component, dict) or len(component) != 1:
            raise ValueError(f"route component is not a single-key object: {component!r}")
        [(variant, value)] = component.items()
        carries = ROUTE_VARIANTS.get(variant)
        # `bool` is an `int` to Python and is not an index to zizmor.
        if carries is None or isinstance(value, bool) or not isinstance(value, carries):
            raise ValueError(
                f"route component is not a `Key` of text or an `Index` of a number: "
                f"{component!r}")
        parts.append(str(value))
    return "/" + "/".join(parts)


def primary(finding: dict) -> dict:
    """The one location a finding points at.

    A finding carries `Related` and `Hidden` locations too -- `secrets-outside-env`
    hands back the whole job as context -- and those move with any edit inside
    them. Exactly one `Primary` is the shape every audit produces; anything
    else is a zizmor whose output this script has not been read against, which
    is a stop, not a guess.

    A finding or a location that is not an object at all -- `[null]`, say --
    is the same stop rather than an `AttributeError` from inside a `.get()`:
    the entrypoint promises a named refusal, and it can only keep that promise
    for the failures the helpers actually name.
    """

    if not isinstance(finding, dict):
        raise ValueError(f"finding is not an object: {finding!r}")
    locations = [location for location in finding.get("locations") or []
                 if isinstance(location, dict)
                 and (location.get("symbolic") or {}).get("kind") == "Primary"]
    if len(locations) != 1:
        raise ValueError(
            f"{finding.get('ident')!r} has {len(locations)} primary locations, not 1; "
            "zizmor's output shape has changed and this script must be re-read")
    return locations[0]


def key_of(finding: dict) -> Key:
    """The stable identity of `finding`, from its primary location."""

    location = primary(finding)
    symbolic = location["symbolic"]
    return Key(
        ident=str(finding["ident"]),
        path=str(symbolic["key"]["Local"]["verbatim_path"]),
        route=render_route(symbolic["route"]["route"]),
        feature=str(location["concrete"]["feature"]))


def gated(findings: list) -> list[Found]:
    """Every finding the default persona drops, in the order zizmor reported."""

    found = []
    for finding in findings:
        if not isinstance(finding, dict):
            raise ValueError(f"finding is not an object: {finding!r}")
        determinations = finding.get("determinations", {})
        persona = determinations.get("persona") if isinstance(determinations, dict) else None
        if not isinstance(persona, str):
            # Defaulting a missing or renamed field to "" would call the
            # finding gated, and a gated finding whose key is already decided
            # reconciles to zero -- reporting agreement about a persona this
            # never read. Which findings the gate drops is the whole question,
            # so a run that cannot answer it stops.
            raise ValueError(
                f"{finding.get('ident')!r} has no string `determinations.persona` "
                f"({persona!r}); zizmor's output shape has changed and this script "
                "must be re-read")
        if persona == DEFAULT_PERSONA:
            continue
        location = primary(finding)
        found.append(Found(
            key=key_of(finding),
            persona=persona,
            severity=str(determinations.get("severity", "")),
            # zizmor counts rows from zero and prints them from one.
            line=int(location["concrete"]["location"]["start_point"]["row"]) + 1))
    return found


def reconcile(found: list[Found],
              decided: tuple[Decision, ...]) -> tuple[list[Found], list[Decision]]:
    """The findings nobody decided, and the decisions nothing found."""

    found_keys = {item.key for item in found}
    decided_keys = {decision.key for decision in decided}
    return ([item for item in found if item.key not in decided_keys],
            [decision for decision in decided if decision.key not in found_keys])


def run_zizmor(zizmor: str, root: pathlib.Path) -> list:
    """The auditor persona's findings over `.github/workflows/`, as JSON.

    `--offline` matches the gate beside it: no network, so no run of this
    depends on whether GitHub answered. The exit status is deliberately not
    checked -- zizmor exits non-zero whenever it has findings, and having
    findings is the normal case here.

    Raises `ValueError` for anything it cannot read, which `main()` turns into
    a named message and exit 2 rather than a traceback.
    """

    completed = subprocess.run(
        [zizmor, "--offline", "--persona=auditor", "--format=json-v1",
         "--no-progress", WORKFLOWS],
        cwd=root, capture_output=True, text=True, check=False)
    try:
        findings = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"printed no JSON (exit {completed.returncode}): {error}"
            f"\n{completed.stderr.strip()}") from error
    if not isinstance(findings, list):
        raise ValueError(f"printed {type(findings).__name__}, not a list of findings")
    return findings


def locate(given: str | None) -> str | None:
    """The zizmor to run: the one named, else one on PATH, else nothing.

    A name is accepted both as a path to a file and as something on PATH, so
    the two callers -- `make audit`, which hands over the pinned copy in the
    virtualenv, and the `lint` job, where the pinned copy is what PATH already
    resolves to -- reach the same binary the gate beside them ran.
    """

    if given:
        return given if pathlib.Path(given).is_file() or shutil.which(given) else None
    return shutil.which("zizmor")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zizmor", default=None,
                        help="the zizmor to run; the one on PATH by default")
    parser.add_argument("--root", default=None, help="the checkout to audit")
    args = parser.parse_args(argv[1:])

    root = pathlib.Path(args.root) if args.root else pathlib.Path(__file__).resolve().parents[2]
    zizmor = locate(args.zizmor)
    if zizmor is None:
        # Not a skip. Both callers reach this only down an arm that already
        # found zizmor, so a miss here means the binary moved between the gate
        # and this, and a warning-and-zero would report the enumeration green
        # having enumerated nothing.
        print(f"error: {args.zizmor or 'zizmor'} is neither a file nor on PATH; "
              "the persona enumeration cannot run.", file=sys.stderr)
        return 2

    try:
        found = gated(run_zizmor(zizmor, root))
    except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError) as error:
        # The entrypoint contract: a tool that moved, a zizmor whose JSON this
        # has not been read against, a shape `primary()` refuses. Each is a
        # reason this could not be answered, and each reads as one line rather
        # than as a traceback -- and never as agreement.
        print(f"error: {zizmor} could not be enumerated: "
              f"{type(error).__name__}: {error}", file=sys.stderr)
        return 2

    undecided, unfound = reconcile(found, DECIDED)

    print(f"check-zizmor-personas: {len(found)} finding(s) the default persona drops, "
          f"{len(DECIDED)} decided")
    for item in found:
        print(f"  {item}")

    for item in undecided:
        print(f"error: no decision for {item}\n"
              f"       read {item.key.ident} at {item.path_line}, then add it to DECIDED in "
              f"{pathlib.Path(__file__).name} with the reason it stays.", file=sys.stderr)
    for decision in unfound:
        print(f"error: decided but not found: {decision.key}\n"
              "       the finding is gone; delete the decision rather than leaving a "
              "reason for nothing.", file=sys.stderr)
    return 1 if undecided or unfound else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
