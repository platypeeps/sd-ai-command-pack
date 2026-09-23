"""What protects a branch, read from both of GitHub's mechanisms.

`repos/{slug}/branches/{b}/protection` is *classic* branch protection. A
branch a ruleset protects answers 404 there -- and so does every branch to a
token without `admin` on the repository: GitHub answers 404 `Not Found`
rather than 403 (home-assistant/core and gohugoio/hugo, both protected,
2026-09-22), while an admin of a bare branch gets 404 `Branch not
protected`. A 404 is "no classic protection" only from an admin. `sd-ship`'s
gate has that from `owned()` before it reads; `sd-status` asks the repository
object and reports the classic side unknown otherwise. And
`repos/{slug}/rules/branches/{b}` lists the rules every *ruleset* evaluates
for the branch while saying nothing about classic protection: measured
2026-09-22 on answerbook/mezmo_benchmark, whose classic object requires
reviews and the `CI Result` check, the rules endpoint listed only its
ruleset's `deletion` and `non_fast_forward`. A reader of either endpoint
alone is blind to the other (sd:1323, sd:1327), so the callers read classic
first and this module reads the rulesets when classic answers 404.

The rules come back one per applied rule, each with `type`, `ruleset_id`
and, for the rule types that carry any, `parameters`; sampled on
answerbook/log-distiller `main` (ruleset 21102575): a `pull_request` rule
with `required_approving_review_count`, `dismiss_stale_reviews_on_push`,
`require_code_owner_review`, `require_last_push_approval` and
`allowed_merge_methods`, and a `required_status_checks` rule with
`strict_required_status_checks_policy` and `required_status_checks:
[{context, integration_id}]`. The ruleset itself, `repos/{slug}/rulesets/{id}`,
carries `enforcement` and, only for a caller who can edit the ruleset,
`bypass_actors`: measured 2026-09-22, the key is absent on log-distiller read
with a token that has `maintain` but not `admin` there, and `[]` on
answerbook/mezmo-world-simulator 21772988 read with `admin`. An absent key is
therefore *unknown*, never "nobody": the synthesized object carries it as
`None` beside a real `[]`, and a gate refuses on it (sd:1327's review).

`synthesize` reduces the active rules to the classic shape every consumer
already reads -- `enforce_admins`, `required_pull_request_reviews`,
`required_status_checks` with `strict`, `contexts` and app-bound `checks` --
plus `source: "ruleset"` and the contributing rulesets, so `sd-ship`'s
`validate_protection`, `ready` and `still_gated` and `sd-status`'s
protection section read it unchanged.

The transport is the caller's, handed in as `fetch(path) -> (status, body)`:
`sd_ship_remote.GitHub.api_status` for the gate, and a wrapper over
`sd-pr-state`'s `gh_json` for `sd-status`.
"""

from __future__ import annotations

from typing import Any, Callable
from urllib.parse import quote

#: The `source` marker on a synthesized object. A classic object has none.
RULESET_SOURCE = "ruleset"

#: Rule types that gate what a merge lands. `deletion`, `non_fast_forward`,
#: `required_linear_history`, `required_signatures` and the rest constrain
#: how the branch moves, not what a pull request must satisfy, so a ruleset
#: carrying only those leaves the merge exactly as ungated as no ruleset at
#: all: a declared `unprotected` gap stays true beside one (sd:1323's second
#: note names four such repositories), and the gate keeps asking for it.
MERGE_GATING_RULES = frozenset({"pull_request", "required_status_checks"})

#: The one wording that separates "this plan has no branch protection" from
#: "you may not read it" in a 403: GitHub's `Upgrade to GitHub Pro or make
#: this repository public to enable this feature.` Matched case-insensitively
#: and on nothing else, so a permission refusal that mentions no upgrade
#: stays a permission refusal (sd:1327).
PLAN_LIMIT_MARKER = "upgrade to github"

#: The rules endpoint pages its answer, thirty rules a page by default. The
#: size is sent explicitly so a full page means the same to the server and to
#: the loop that reads until a page comes back short. A reader that took the
#: first page for the whole list would see a *weaker* branch than the real
#: one -- a `required_status_checks` rule on the second page missing from
#: the comparison -- which is the direction a gate must not fail in
#: (sd:1327 review, finding 2).
PAGE_SIZE = 30

#: Pages read before the reader gives up on a list that never comes back short.
MAX_PAGES = 100

Fetch = Callable[[str], tuple[int, Any]]


def plan_limited(message: object) -> bool:
    """Whether a 403's message says the feature needs a plan upgrade."""
    return PLAN_LIMIT_MARKER in str(message or "").lower()


def rules_path(prefix: str, branch: str, page: int = 1) -> str:
    return f"{prefix}/rules/branches/{quote(branch, safe='')}?per_page={PAGE_SIZE}&page={page}"


def ruleset_path(prefix: str, ruleset_id: int) -> str:
    return f"{prefix}/rulesets/{ruleset_id}"


def read_rulesets(fetch: Fetch, prefix: str, branch: str) -> dict[str, Any]:
    """The rules GitHub evaluates for `branch`, and each ruleset they cite.

    Returns `{"rules": [...], "rulesets": {id: object}, "error": str}`.
    `error` is non-empty when something could not be observed -- the rules
    endpoint did not answer 200 with a list, or a cited ruleset did not
    answer 200 with an object -- and then `rules` and `rulesets` hold what
    was read before the fault. A caller that gates a merge refuses on it; a
    caller that reports names it. Only a 200 is an answer here: the rules
    endpoint answers `[]` for a branch no ruleset touches, so a 404 or 403
    from it is a repository this reader could not see into, never "no rules".

    The rules are read page by page until a page comes back shorter than
    `PAGE_SIZE`; a page that fails is the same fault as the first one
    failing, and a list still full at `MAX_PAGES` is a fault too rather
    than a partial answer.
    """
    rules: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        status, body = fetch(rules_path(prefix, branch, page))
        if status != 200 or not isinstance(body, list):
            message = body.get("message") if isinstance(body, dict) else None
            return {"rules": rules, "rulesets": {},
                    "error": f"{message or 'branch rulesets could not be observed'} (HTTP {status})"}
        rules.extend(rule for rule in body if isinstance(rule, dict))
        if len(body) < PAGE_SIZE:
            break
    else:
        return {"rules": rules, "rulesets": {},
                "error": f"branch rulesets ran past {MAX_PAGES} pages of {PAGE_SIZE} rules"}
    rulesets: dict[int, dict] = {}
    cited: set[int] = {rule["ruleset_id"] for rule in rules if isinstance(rule.get("ruleset_id"), int)}
    for ruleset_id in sorted(cited):
        status, value = fetch(ruleset_path(prefix, ruleset_id))
        if status != 200 or not isinstance(value, dict):
            message = value.get("message") if isinstance(value, dict) else None
            return {"rules": rules, "rulesets": rulesets,
                    "error": f"ruleset {ruleset_id}: {message or 'could not be observed'} (HTTP {status})"}
        rulesets[ruleset_id] = value
    return {"rules": rules, "rulesets": rulesets, "error": ""}


def active_rules(rules: list, rulesets: dict[int, dict]) -> list[dict]:
    """The rules whose ruleset is `enforcement: active`.

    An `evaluate` or `disabled` ruleset enforces nothing, and a rule citing a
    ruleset that was not read is not known to be enforced, so neither counts.
    """
    active = []
    for rule in rules:
        ruleset_id = rule.get("ruleset_id") if isinstance(rule, dict) else None
        if isinstance(ruleset_id, int) and (rulesets.get(ruleset_id) or {}).get("enforcement") == "active":
            active.append(rule)
    return active


def _parameters(rule: dict) -> dict[str, Any]:
    raw = rule.get("parameters")
    return raw if isinstance(raw, dict) else {}


def synthesize(rules: list, rulesets: dict[int, dict]) -> dict[str, Any] | None:
    """The classic-shaped object the active, merge-gating rules amount to.

    `None` when no active rule on the branch gates a merge: no ruleset, a
    ruleset that is not active, or one carrying only `deletion`-class rules.
    Where two rulesets both carry a rule, GitHub applies the stricter one, so
    review counts take the maximum, booleans the disjunction, and required
    checks the union.

    `enforce_admins` is `bypass_actors` asked the classic way round, in
    three states rather than two: `False` when any contributing ruleset
    names an actor an administrator merges as (`reaches_admins`); `None`
    when any did not show its list at all -- GitHub withholds
    `bypass_actors` from a caller who cannot edit the ruleset, and a list
    this reader was not shown is not an empty one -- or names a repository
    role, whose numeric id this reader cannot resolve to admin or not; and
    `True` otherwise. An actor that does not reach administrators leaves it
    `True`: an app or a team bypassing the ruleset exempts nobody who
    merges as admin, and reporting it as `enforce_admins` off was a false
    security finding on a repository whose administrators are subject to
    every rule. That bypass is the caller's own finding, read from
    `bypass_pairs`. The contributing rulesets travel on the object under
    `rulesets`, each with its `bypass_actors` as read (`None` for
    withheld), so a refusal can name the one with the bypass or the one
    that hid it.
    """
    gating = [rule for rule in active_rules(rules, rulesets) if rule.get("type") in MERGE_GATING_RULES]
    if not gating:
        return None
    contributing = _contributing(sorted({rule["ruleset_id"] for rule in gating}), rulesets, gating)
    value: dict[str, Any] = {
        "source": RULESET_SOURCE,
        "rulesets": contributing,
        "enforce_admins": {"enabled": _admins_subject([entry["bypass_actors"] for entry in contributing])},
    }
    reviews = _reviews([_parameters(rule) for rule in gating if rule.get("type") == "pull_request"])
    if reviews is not None:
        value["required_pull_request_reviews"] = reviews
    checks = _checks([_parameters(rule) for rule in gating if rule.get("type") == "required_status_checks"])
    if checks is not None:
        value["required_status_checks"] = checks
    return value


def _contributing(ids: list[int], rulesets: dict[int, dict], gating: list) -> list[dict[str, Any]]:
    """Each cited ruleset with the merge-gating rule types it contributes:
    a bypass of one ruleset reaches those rules and no other ruleset's, so
    a finding that names the bypass names the rules with it (`scope`)."""
    return [{"id": ruleset_id,
             "name": str(rulesets[ruleset_id].get("name") or ruleset_id),
             "enforcement": rulesets[ruleset_id].get("enforcement"),
             "bypass_actors": _bypass_actors(rulesets[ruleset_id]),
             "rules": sorted({str(rule["type"]) for rule in gating if rule.get("ruleset_id") == ruleset_id})}
            for ruleset_id in ids]


def _bypass_actors(ruleset: dict) -> list | None:
    """The ruleset's bypass list as shown, or `None` when it was not shown."""
    actors = ruleset.get("bypass_actors")
    return list(actors) if isinstance(actors, list) else None


def reaches_admins(actor: Any) -> bool | None:
    """Whether a bypass actor is one an administrator merges as.

    `True` for `OrganizationAdmin`. `None` for a `RepositoryRole`: the
    actor carries a numeric role id, which role that id names is not
    confirmed here, and no ruleset a registered token can read carries one
    to measure against -- so whether it is the admin role, and the
    administrators' exemption, or a lesser one is unknown, and is reported
    as unknown rather than as either. A constant guessed here would decide
    which of two sentences an operator reads, and the wrong guess reads as
    reassurance. `False` for an app, a team, a deploy key or a user, which
    bypass the ruleset without reaching the administrators, who stay
    subject to every rule.
    """
    if not isinstance(actor, dict):
        return False
    kind = actor.get("actor_type")
    if kind == "OrganizationAdmin":
        return True
    return None if kind == "RepositoryRole" else False


def actor_words(actor: Any) -> str:
    """`Integration 77 (pull_request)`: the actor's type, its id when it
    carries one, and when the bypass applies."""
    if not isinstance(actor, dict):
        return str(actor)
    kind = str(actor.get("actor_type") or "actor")
    mode = str(actor.get("bypass_mode") or "always")
    ident = actor.get("actor_id")
    return f"{kind} {ident} ({mode})" if ident is not None else f"{kind} ({mode})"


def bypass_pairs(value: dict[str, Any], reaching: bool | None) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Every (ruleset, actor) pair whose actor `reaches_admins` answers
    `reaching`: `False` for the bypasses that do not reach administrators,
    the `bypass` finding; `None` for the repository roles nothing here
    resolves, one reason `enforce_admins` reads unknown."""
    return [(entry, actor)
            for entry in value.get("rulesets") or [] if isinstance(entry, dict)
            for actor in entry.get("bypass_actors") or [] if reaches_admins(actor) is reaching]


def unknown_admins_words(value: dict[str, Any], default_branch: str) -> str:
    """Why `enforce_admins` is unknown, each reason named: the rulesets that
    withheld their bypass list, and the role bypasses nothing here resolves.
    Unknown is a statement about this reader's knowledge; the alternative
    sentences are claims about the repository, and neither is made."""
    reasons: list[str] = []
    hidden = ", ".join(scope(entry) for entry in hidden_bypass(value))
    if hidden:
        reasons.append(
            f"whether anyone can bypass the ruleset protecting {default_branch} is unknown: GitHub "
            f"did not show bypass_actors for {hidden}, which it withholds from a caller who cannot "
            "edit the ruleset. A bypass list not shown is not an empty one.")
    roles = "; ".join(f"{scope(entry)} lets {actor_words(actor)} bypass it"
                      for entry, actor in bypass_pairs(value, None))
    if roles:
        reasons.append(
            f"whether administrators can bypass the ruleset protecting {default_branch} is unknown: "
            f"{roles}, and which role that id names is not confirmed here. The admin role would be "
            "their exemption; a lesser role would not; neither is claimed.")
    return " ".join(reasons) or f"whether anyone can bypass the ruleset protecting {default_branch} is unknown."


def bypass_words(value: dict[str, Any], reaching: bool = False) -> list[str]:
    """`main (#42) [pull_request]: Integration 77 (pull_request)`, one a
    bypass whose `reaches_admins` is `reaching`, sorted: with `False` the
    words the `bypass` finding prints and the fact an acknowledgement of it
    pins; with `True` the administrators' own exemptions, the `admin_bypass`
    fact an acknowledgement of `enforce_admins` pins per ruleset, so one
    added on a second ruleset un-matches the entry."""
    return sorted(f"{scope(entry)}: {actor_words(actor)}"
                  for entry, actor in bypass_pairs(value, reaching))


def scope(entry: dict[str, Any]) -> str:
    """One ruleset for a sentence, with the merge-gating rules it carries:
    `main (#42) [pull_request]`. GitHub layers rulesets, and a bypass of
    one exempts its holder from that ruleset's rules and from no other's,
    so a bypass named without the rules it reaches reads as wider than it
    is (Codex on #521: "every rule below" said of a branch whose checks
    ruleset still bound the administrators). An entry without `rules` --
    `_contributing` records them; a hand-shaped one may not -- is named
    without the brackets."""
    named = f"{entry.get('name')} (#{entry.get('id')})"
    rules = entry.get("rules")
    return f"{named} [{', '.join(str(rule) for rule in rules)}]" if rules else named


def ruleset_states(value: dict[str, Any]) -> list[dict[str, Any]]:
    """Each contributing ruleset with `admins`: `exempt` when a shown actor
    reaches administrators, `unknown` when its list was withheld or a shown
    actor is a role nothing resolves and none reaches them, `enforced` when
    the list was shown and none does. Kept apart per ruleset: the one
    `enforce_admins` boolean `_admins_subject` gives the object answers
    "subject to every rule", and says nothing about which."""
    states = []
    for entry in value.get("rulesets") or []:
        if not isinstance(entry, dict):
            continue
        verdict = _admins_subject([entry.get("bypass_actors")])
        states.append({**entry, "admins": "unknown" if verdict is None else ("enforced" if verdict else "exempt")})
    return states


def exempt_admins_words(value: dict[str, Any], default_branch: str) -> str:
    """`enforce_admins` off, the ruleset way round: which ruleset exempts
    administrators, through which actor, from which rules -- then the
    rulesets still binding them, then the ones not known either way.
    "Every rule below" is said only when no ruleset is left in either: a
    review ruleset the admins bypass beside a checks ruleset nobody does
    leaves the CI requirement enforced, and a sentence exempting them from
    everything is a false finding on it."""
    states = ruleset_states(value)
    binding = "; ".join(scope(entry) for entry in states if entry["admins"] == "enforced")
    unknown = "; ".join(scope(entry) for entry in states if entry["admins"] == "unknown")
    named = "; ".join(f"{scope(entry)} by {actor_words(actor)}" for entry, actor in bypass_pairs(value, True))
    words = f"enforce_admins is off on {default_branch}: {named}. "
    if not binding and not unknown:
        return words + ("Every rule below stops collaborators and exempts the admins who do the "
                        "merging. Protection that exempts admins is prose, not authority.")
    words += "The rules in brackets stop collaborators and exempt the admins who do the merging."
    if binding:
        words += f" Still binding them: {binding}."
    if unknown:
        words += (f" Not known either way: {unknown}, whose bypass list was withheld or names a "
                  "role nothing here resolves.")
    return words


def _admins_subject(lists: list[list | None]) -> bool | None:
    """`False` when a shown actor reaches administrators; `None` when a list
    was withheld, or a shown actor is a role nothing here resolves, and no
    shown actor reaches them; `True` when every list was shown and none
    does either. An actor that does not reach them leaves this alone: that
    bypass is the caller's finding, not the administrators' exemption."""
    verdicts = [reaches_admins(actor) for actors in lists if actors for actor in actors]
    if any(verdict is True for verdict in verdicts):
        return False
    if any(actors is None for actors in lists) or any(verdict is None for verdict in verdicts):
        return None
    return True


def hidden_bypass(value: dict[str, Any]) -> list[dict[str, Any]]:
    """The contributing rulesets whose `bypass_actors` GitHub did not show."""
    return [entry for entry in value.get("rulesets") or []
            if isinstance(entry, dict) and entry.get("bypass_actors") is None]


def _reviews(parameter_sets: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The `required_pull_request_reviews` object of the `pull_request` rules, stricter wins."""
    if not parameter_sets:
        return None
    counts = [parameters.get("required_approving_review_count") for parameters in parameter_sets]
    return {
        "required_approving_review_count": max([count for count in counts if isinstance(count, int)] or [0]),
        "dismiss_stale_reviews": any(p.get("dismiss_stale_reviews_on_push") is True for p in parameter_sets),
        "require_code_owner_reviews": any(p.get("require_code_owner_review") is True for p in parameter_sets),
        "require_last_push_approval": any(p.get("require_last_push_approval") is True for p in parameter_sets),
    }


def _checks(parameter_sets: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The `required_status_checks` object of those rules: the union of the
    named checks, `integration_id` carried as `app_id`, strict if any is."""
    if not parameter_sets:
        return None
    contexts: list[str] = []
    checks: list[dict[str, Any]] = []
    for parameters in parameter_sets:
        for entry in parameters.get("required_status_checks") or []:
            if not isinstance(entry, dict) or not entry.get("context") or str(entry["context"]) in contexts:
                continue
            contexts.append(str(entry["context"]))
            checks.append({"context": str(entry["context"]), "app_id": entry.get("integration_id")})
    return {"strict": any(p.get("strict_required_status_checks_policy") is True for p in parameter_sets),
            "contexts": contexts, "checks": checks}


def rule_types(rules: list, rulesets: dict[int, dict]) -> list[str]:
    """The distinct active rule types on the branch, sorted, for a report."""
    return sorted({str(rule.get("type")) for rule in active_rules(rules, rulesets)})
