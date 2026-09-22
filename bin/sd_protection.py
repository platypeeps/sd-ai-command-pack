"""What protects a branch, read from both of GitHub's mechanisms.

`repos/{slug}/branches/{b}/protection` is *classic* branch protection. A
branch a ruleset protects answers 404 there, and
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

Fetch = Callable[[str], tuple[int, Any]]


def plan_limited(message: object) -> bool:
    """Whether a 403's message says the feature needs a plan upgrade."""
    return PLAN_LIMIT_MARKER in str(message or "").lower()


def rules_path(prefix: str, branch: str) -> str:
    return f"{prefix}/rules/branches/{quote(branch, safe='')}"


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
    """
    status, body = fetch(rules_path(prefix, branch))
    if status != 200 or not isinstance(body, list):
        message = body.get("message") if isinstance(body, dict) else None
        return {"rules": [], "rulesets": {},
                "error": f"{message or 'branch rulesets could not be observed'} (HTTP {status})"}
    rules = [rule for rule in body if isinstance(rule, dict)]
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
    three states rather than two: `True` when every contributing ruleset
    showed an empty list, `False` when any names someone, and `None` when
    any did not show its list at all -- GitHub withholds `bypass_actors`
    from a caller who cannot edit the ruleset, and a list this reader was
    not shown is not an empty one. The contributing rulesets travel on the
    object under `rulesets`, each with its `bypass_actors` as read (`None`
    for withheld), so a refusal can name the one with the bypass or the one
    that hid it.
    """
    gating = [rule for rule in active_rules(rules, rulesets) if rule.get("type") in MERGE_GATING_RULES]
    if not gating:
        return None
    contributing = _contributing(sorted({rule["ruleset_id"] for rule in gating}), rulesets)
    value: dict[str, Any] = {
        "source": RULESET_SOURCE,
        "rulesets": contributing,
        "enforce_admins": {"enabled": _nobody_bypasses([entry["bypass_actors"] for entry in contributing])},
    }
    reviews = _reviews([_parameters(rule) for rule in gating if rule.get("type") == "pull_request"])
    if reviews is not None:
        value["required_pull_request_reviews"] = reviews
    checks = _checks([_parameters(rule) for rule in gating if rule.get("type") == "required_status_checks"])
    if checks is not None:
        value["required_status_checks"] = checks
    return value


def _contributing(ids: list[int], rulesets: dict[int, dict]) -> list[dict[str, Any]]:
    return [{"id": ruleset_id,
             "name": str(rulesets[ruleset_id].get("name") or ruleset_id),
             "enforcement": rulesets[ruleset_id].get("enforcement"),
             "bypass_actors": _bypass_actors(rulesets[ruleset_id])}
            for ruleset_id in ids]


def _bypass_actors(ruleset: dict) -> list | None:
    """The ruleset's bypass list as shown, or `None` when it was not shown."""
    actors = ruleset.get("bypass_actors")
    return list(actors) if isinstance(actors, list) else None


def _nobody_bypasses(lists: list[list | None]) -> bool | None:
    """`True` only when every list was shown and empty; `False` when one
    names anyone; `None` when one was withheld and none names anyone."""
    if any(lists):
        return False
    return None if any(actors is None for actors in lists) else True


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
