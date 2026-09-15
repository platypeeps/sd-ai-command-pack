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
    "(ubuntu-latest, 3.13)` and `lint`. `bin/sd_ship_remote.py` reads those "
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
        key=Key(ident="secrets-outside-env",
                path=f"{WORKFLOWS}/tests.yml",
                route="/jobs/unittest",
                feature="secrets.SYSTEM_REPO_TOKEN"),
        reason=(
            "Accepted, and this is the one of the three worth re-reading when "
            "anything about the job changes. The audit wants the secret behind "
            "a GitHub environment, so that environment protection rules govern "
            "who can start a run that reads it. Two things stand in for that "
            "here. The token is read by one step -- a checkout of "
            "`platypeeps/system` at a pinned commit -- and that step sets "
            "`persist-credentials: false`, so it is not written into the "
            "workspace's git config for the steps after it. And the workflow "
            "runs on `pull_request` and on `push` to `main`: GitHub hands no "
            "secret to a `pull_request` run from a fork, so the only heads that "
            "reach this token are heads in this repository, pushed by somebody "
            "who can already push here. An environment would narrow that to "
            "\"and approved by a named reviewer\", at the price of a manual "
            "approval on every run of the default test lane, which is declined "
            "while the two populations are the same one. What would reopen it: "
            "this repository taking fork pull requests with secrets, this job "
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
        parts.append(str(next(iter(component.values()))))
    return "/" + "/".join(parts)


def primary(finding: dict) -> dict:
    """The one location a finding points at.

    A finding carries `Related` and `Hidden` locations too -- `secrets-outside-env`
    hands back the whole job as context -- and those move with any edit inside
    them. Exactly one `Primary` is the shape every audit produces; anything
    else is a zizmor whose output this script has not been read against, which
    is a stop, not a guess.
    """

    locations = [location for location in finding.get("locations", [])
                 if location.get("symbolic", {}).get("kind") == "Primary"]
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
        determinations = finding.get("determinations", {})
        persona = str(determinations.get("persona", ""))
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
    """

    completed = subprocess.run(
        [zizmor, "--offline", "--persona=auditor", "--format=json-v1",
         "--no-progress", WORKFLOWS],
        cwd=root, capture_output=True, text=True, check=False)
    try:
        findings = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise SystemExit(
            f"check-zizmor-personas: {zizmor} printed no JSON (exit {completed.returncode}): "
            f"{error}\n{completed.stderr.strip()}") from error
    if not isinstance(findings, list):
        raise SystemExit(
            f"check-zizmor-personas: {zizmor} printed {type(findings).__name__}, not a list")
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

    found = gated(run_zizmor(zizmor, root))
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
