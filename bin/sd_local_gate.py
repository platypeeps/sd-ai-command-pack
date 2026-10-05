"""The local CI gate: `sd-check` at the exact head, reported as a commit status.

A repository whose `repo.ci` row says `local` runs no GitHub Actions (sd:1843).
Its evidence is produced on this machine instead: `sd-ship merge` checks the
reviewed head out into a clean, detached `git worktree`, runs `sd-check` there,
and posts the result to that commit as the `sd/local-gate` status
(`sd_lib.LOCAL_GATE_CONTEXT`). `every_check` and `ready` in
`bin/sd_ship_remote.py` then read that status where they would have read the
`pull_request` workflow runs.

The run itself -- the worktree, the scrubbed environment, `SD_LOCAL_GATE=1`,
receipt reuse and the docs-only scope -- is `sd_gate_run`, which posts
nothing; `sd-review --gate-check` runs the same code for `sd-ship prepare`.

A success is posted only for the commit the worktree held when `sd-check`
finished. `post` refuses any other SHA, so a result cannot be carried to a
head that was never checked.

Every merge attempt posts a fresh status, from a run or from a receipt; a
reused pass says so in its description, and a run in full keeps `reuse_miss`,
why no receipt stood (sd:2602). The one exception is an accepted offload
receipt (sd:2704): the satellite's prepare posted the status, and the hub's
merge checks it instead of posting its own. The description carries
`inputs <digest>` as provenance: a digest of the head, the copied
`CLAUDE.local.md` (or its absence) and the pack's own `bin/` files. Anyone
with write access can post a status, so `local_gate_passed` trusts only one
the authenticated account posted.

This is a self-hosted runner, not a hermetic build. The gate guarantees a clean
tree at the exact head, a scrubbed Python environment and no virtualenv on
`PATH`. The rest of `PATH`, the interpreter running `sd-ship` and the system
tools are this machine's image; the repository's own `check` entrypoint owns a
hermetic environment if it needs one. When the checkout under test is the pack
itself and `sd-ship` runs from it, the gate's own `bin/` is that checkout.

`sd gate post --head SHA` (`post_head`, sd:1989) runs this same gate and post
outside `sd-ship merge`, for a repository's own merge path: a Dependabot merge
or a script that merges by itself gets no `sd/local-gate` otherwise, and its
required check never reports. It reads and writes no receipt, so it always runs.
"""

from __future__ import annotations

import pathlib
from typing import Any

import sd_lib
from sd_gate_run import (
    DESCRIPTION_LIMIT,
    WHOLE_OUTPUT,
    GateError,
    base_ref,
    check_in_worktree,
    gate_inputs,
)
from sd_ship_remote import GitHub, Refusal, git, slug
from sd_ship_review import FAILING_TAIL_CHARS, failing_check_tails

CONTEXT = sd_lib.LOCAL_GATE_CONTEXT
#: Who acts after the hub refuses a satellite's receipt, and what they run (sd:2704, design.md "Freshness").
HAND_BACK = ("On the satellite: git merge origin/{base} on the branch (or sd-ship prepare --catch-up), "
             "then sd gate check --base {base}, sd-ship prepare, and sd-ship lane request again.")
#: The trust rule's refusal codes, in clause order (design.md, "The trust rule"), each with its next action.
SATELLITE_REFUSALS = {
    "satellite_gate_off": "On the hub: opt the repository in with sd-db.sh repo satellite-gate <path> accept, "
                          "or merge without --satellite-gate, which runs the hub's own gate.",
    "base_moved": HAND_BACK,
    "satellite_receipt_missing": HAND_BACK,
    "satellite_receipt_invalid": HAND_BACK,
    "satellite_binding": HAND_BACK,
    "satellite_pack_mismatch": "Bring the satellite's pack checkout to the hub's revision. " + HAND_BACK,
    "satellite_receipt_expired": HAND_BACK,
    "satellite_status_missing": "On the satellite: sd-ship prepare again, which posts sd/local-gate from the "
                                "offload receipt, then sd-ship lane request again.",
    "local_gate_foreign": "On the satellite: authenticate gh as the hub's GitHub account, then sd-ship prepare "
                          "and sd-ship lane request again.",
}


def post_gate_status(api: Any, head: str, result: dict[str, Any], inputs: str) -> dict[str, Any]:
    """Post `result` as `sd/local-gate` on `head`, bound to `inputs`; refuse a SHA the run did not check."""
    if result.get("head") != head:
        raise Refusal(f"the local gate checked {str(result.get('head'))[:12]}, not {head[:12]}; "
                      "no status is posted for a commit that was not checked",
                      code="local_gate_mismatch", boundary="ci", state="retryable_failure",
                      next_action="Retry merge from the reviewed head.")
    state = "success" if result.get("status") == "success" else "failure"
    # The summary's local output path stays out of a status anyone who reads the repository sees (sd:2608).
    summary = str(result.get("summary") or state).split(WHOLE_OUTPUT, 1)[0]
    description = f"{head[:12]} inputs {inputs}: {summary}"[:DESCRIPTION_LIMIT]
    return api.api(f"{api.prefix}/statuses/{head}", method="POST",
                   body={"state": state, "context": CONTEXT, "description": description})


def local_gate(api: Any, root: pathlib.Path, head: str, *, base: str | None = None,
               database: pathlib.Path | None = None, offload: str | None = None) -> dict[str, Any]:
    """Run `sd-check` at `head`, or reuse its receipt, and post the result; `base` is the base branch.

    `offload` is the hub's use of a satellite's offload receipt (sd:2704). `require`, the merge's
    `--satellite-gate`, accepts one under clauses 3 to 8 of the trust rule and posts nothing, since the
    satellite's status stands; a failed clause refuses with its code and runs nothing. `fallback`, a
    plain merge in an opted-in repository, tries one after this machine's own receipt and runs the gate
    on any miss, which `reuse_miss` names.
    """
    inputs = gate_inputs(root, head)
    # The merge gate only reads prepare's receipt; its own pass records none (sd:2041).
    result = merge_gate_run(root, head, base, database, offload)
    if "offload_refused" in result:
        raise satellite_refusal(result["offload_refused"], base)
    if "satellite" in result:
        refused = status_refusal(api, head, inputs)
        if refused is None:
            return {**result, "inputs": inputs}
        if offload == "require":
            raise satellite_refusal(refused, base)
        result = merge_gate_run(root, head, base, database, None)
        result["reuse_miss"] = {**(result.get("reuse_miss") or {}), "offload": refused}
    post_gate_status(api, head, result, inputs)
    return {**result, "inputs": inputs}


def merge_gate_run(root: pathlib.Path, head: str, base: str | None, database: pathlib.Path | None,
                   offload: str | None) -> dict[str, Any]:
    """The merge gate's `check_in_worktree`: it reads receipts and records none."""
    try:
        return check_in_worktree(root, head, base=base_ref(base), database=database, record=False,
                                 slot_timeout=sd_lib.GATE_SLOT_SECONDS, offload=offload)  # sd:2611: queue apart
    except GateError as error:
        raise Refusal(str(error), code="command_failed", boundary="runtime", state="retryable_failure",
                      next_action="Inspect the command error, resolve its cause, then retry.") from None


def status_refusal(api: Any, head: str, inputs: str) -> dict[str, str] | None:
    """Clause 8: the newest `sd/local-gate` at `head` is this account's success, at this hub's `inputs`.

    The description must start `head[:12] inputs <inputs>`, the digest this hub would post itself, so a
    status from a run with another pack or another `CLAUDE.local.md` does not count.
    """
    statuses = api.pages(f"{api.prefix}/commits/{head}/statuses")
    try:
        api.local_gate_passed(head, statuses)
    except Refusal as refusal:
        foreign = refusal.workflow["blocker"]["code"] == "local_gate_foreign"
        return {"code": "local_gate_foreign" if foreign else "satellite_status_missing", "reason": str(refusal)}
    current = next(entry for entry in statuses if isinstance(entry, dict) and entry.get("context") == CONTEXT)
    if str(current.get("description") or "").startswith(f"{head[:12]} inputs {inputs}"):
        return None
    return {"code": "satellite_status_missing", "reason": f"{CONTEXT} at {head[:12]} says "
            f"{current.get('description')!r}, not this hub's inputs {inputs}"}


def satellite_refusal(refused: dict[str, str], base: str | None) -> Refusal:
    """A trust-rule refusal (sd:2704): its code, and the next action `SATELLITE_REFUSALS` gives it."""
    return Refusal(f"the hub does not accept the satellite's gate: {refused['reason']}", code=refused["code"],
                   boundary="ci", state="retryable_failure",
                   next_action=SATELLITE_REFUSALS[refused["code"]].format(base=base))


def post_head(root: pathlib.Path, head: str, *, base: str | None = None, api: Any = None) -> dict[str, Any]:
    """Run the gate at `head` and post `sd/local-gate` there: `sd gate post` (sd:1989).

    `head` is any name for a commit this checkout has; the status goes to its
    full SHA. `base` narrows the run to a declared docs-only scope against
    that branch, as `sd-ship merge` passes the PR's target. With no `base`
    every check runs: this verb does not know the PR's target, and a head
    bound for a release branch can read as docs-only against the default
    branch while carrying unchecked code. A base whose
    remote-tracking ref is missing refuses, since `sd-check --base` would fail
    and that failure would be posted as the gate's. `api` is the GitHub
    client, `origin`'s by default.
    """
    commit = sd_lib.git_output(["rev-parse", "--verify", "--quiet", f"{head}^{{commit}}"], root)
    if not commit:
        raise Refusal(f"{head} names no commit in this checkout; nothing is posted",
                      code="invalid_input", boundary="input", state="retryable_failure",
                      next_action="Fetch the commit, then retry with its SHA.")
    ref = base_ref(base)
    if ref and sd_lib.git_output(["rev-parse", "--verify", "--quiet", ref], root) is None:
        raise Refusal(f"the base {ref} is not in this checkout; nothing is posted",
                      code="invalid_input", boundary="input", state="retryable_failure",
                      next_action="Fetch origin or name another --base, then retry.")
    if api is None:
        api = GitHub(root, slug(git(root, "config", "--get", "remote.origin.url")))
    return local_gate(api, root, commit, base=base)


def refuse_failure(result: dict[str, Any], head: str, kept: str) -> None:
    """Refuse a failed gate naming each failing check and its own tail, and where the report is kept (sd:2066).

    The status description is cut to 140 characters, so `sd-check fail
    (check fail)` was all a merge said, and finding the failing step meant
    running the gate again. `kept` names the record that holds the whole report.
    """
    if result.get("status") != "failure":
        return
    named = failing_check_tails((result.get("report") or {}).get("checks"))
    stderr = str(result.get("stderr") or "").strip()
    said = "\n".join(named or [f"sd-check: {stderr[-FAILING_TAIL_CHARS:]}"] * bool(stderr))
    raise Refusal(f"repo.ci is local and {CONTEXT} is failure on {head}: {result.get('summary') or 'sd-check failed'}"
                  + (f"\n{said}" if said else "") + f"\nThe whole sd-check report is kept in {kept}.",
                  code="ci_not_passing", boundary="ci", state="retryable_failure",
                  next_action="Fix the failing check, push, then retry merge.")
