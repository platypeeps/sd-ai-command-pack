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
first and this module reads the rulesets whatever classic answered: after a
404 the rulesets are the whole answer (`synthesize`), and beside a classic
object they are layered onto it (`combine`, sd:1419).

GitHub layers the two mechanisms: for each rule, the strictest source wins.
`combine` applies that per merge-gating rule, with three refinements the
operator decided on 2026-09-24. A source is *firm* for a rule when nobody can
bypass it: classic with `enforce_admins` on (and, for the review rule, no
bypass allowances), a ruleset whose `bypass_actors` was shown and is empty.
The effective requirement is the strictest among the firm sources; a stricter
source that is not firm is reported as `advisory` and never tightens it, so
it cannot turn a refusal into a grant. A bypass is *decisive* only when it
removes the last firm source of a rule; one beside a firm source is reported
as information (`bypass_info`) and refuses nothing. And administrators are
enforced on a rule when any source imposing it binds them; `enforce_admins`
is `True` only when that holds for every rule the branch requires.

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

#: The `source` marker on an object layered from classic protection and at
#: least one ruleset, each contributing a merge-gating rule (sd:1419).
COMBINED_SOURCE = "combined"

#: How `combine` names classic protection in `sources`; a ruleset is
#: `ruleset:<id>`.
CLASSIC_SOURCE = "classic"

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


def observed_state(protection: dict[str, Any] | None) -> dict[str, Any]:
    """The live protection object reduced to the facts an acknowledgement pins.

    `required_pull_request_reviews` is a boolean here on purpose: what the
    acknowledgement has to be able to say is *whether the object exists*, which
    is the difference between "a pull request is required and asks for no
    approvals" and "nothing requires a pull request".

    `protection` is `None` when the branch has no protection at all, and
    `branch_protection` is that same existence question asked of the object as
    a whole. Taking `None` rather than `{}` is deliberate: an empty dict is a
    protection object that enforces nothing, which is a different branch state
    from having no object, and the two must not reduce to the same facts.
    """
    protection = protection if isinstance(protection, dict) else None
    reviews = (protection or {}).get("required_pull_request_reviews")
    admins = (protection or {}).get("enforce_admins") or {}
    checks = (protection or {}).get("required_status_checks") or {}
    return {
        "branch_protection": protection is not None,
        # The actors an acknowledgement of the `bypass` gap accepted, by
        # name: one added later un-matches the entry and the gap returns.
        "bypass": bypass_words(protection or {}),
        # The administrators' own exemptions, per ruleset with the rules each
        # reaches: an acknowledgement of `enforce_admins` off that pins them
        # stops applying when a second ruleset grows one.
        "admin_bypass": bypass_words(protection or {}, True),
        "enforce_admins": (
            bool(admins.get("enabled")) if isinstance(admins, dict) else bool(admins)
        ),
        "required_approving_review_count": (
            int(reviews.get("required_approving_review_count") or 0)
            if isinstance(reviews, dict)
            else 0
        ),
        "required_pull_request_reviews": isinstance(reviews, dict),
        "strict": bool(checks.get("strict")) if isinstance(checks, dict) else False,
    }


#: The facts a merge requires an acceptance of each gap to pin (sd:1451). A
#: `strict` entry pins the bypass list too: checks that are not strict are
#: accepted beside the bypass that keeps moving the base, and a bypass added
#: or removed later un-matches the entry.
MERGE_PINS = {"bypass": ("bypass",), "strict": ("strict", "bypass")}


def matching_acceptance(entries: list[dict[str, Any]], gap: str, observed: dict[str, Any]) -> dict[str, Any] | None:
    """The first `accepted_gaps` entry for `gap` that pins the facts
    `MERGE_PINS` names for it and whose every pinned fact equals the live
    one, or `None`. `sd-status`'s matcher plus the pin requirement: a merge
    honours an acceptance only of the state it names, never one that pins
    some other fact (sd:1451)."""
    return next((entry for entry in entries
                 if entry.get("id") == gap
                 and all(fact in (entry.get("state") or {}) for fact in MERGE_PINS.get(gap, (gap,)))
                 and all(observed.get(fact) == value for fact, value in entry["state"].items())), None)


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
            for actor in entry.get("bypass_actors") or []
            if reaches_admins(actor) is reaching and decisive(value, entry, reaching)]


def decisive(value: dict[str, Any], entry: dict[str, Any], reaching: bool | None = False) -> bool:
    """Whether a bypass of ruleset `entry` removes the last enforcement of a
    rule it carries. Always, outside a combined object. Inside one, a bypass
    by an actor that does not reach administrators (`reaching` `False`) is
    decisive when a rule of `entry` has no firm source; an administrators'
    exemption, or a role nothing resolves, when a rule of `entry` has no
    source binding them. A bypass beside a firm source is information
    (`bypass_info`), not a finding and not a refusal (sd:1419, Q2)."""
    if value.get("source") != COMBINED_SOURCE:
        return True
    rules = entry.get("rules") or []
    if reaching is False:
        return any(not (value.get("firm") or {}).get(rule) for rule in rules)
    return any((value.get("admins") or {}).get(rule) is not True for rule in rules)


def unknown_admins_words(value: dict[str, Any], default_branch: str) -> str:
    """Why `enforce_admins` is unknown, each reason named: the rulesets that
    withheld their bypass list, and the role bypasses nothing here resolves.
    Unknown is a statement about this reader's knowledge; the alternative
    sentences are claims about the repository, and neither is made."""
    reasons: list[str] = []
    hidden = ", ".join(scope(entry) for entry in hidden_bypass(value, admins=True))
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


def hidden_bypass(value: dict[str, Any], admins: bool = False) -> list[dict[str, Any]]:
    """The contributing rulesets whose `bypass_actors` GitHub did not show.
    In a combined object only the decisive ones: those whose rules have no
    firm source, or with `admins` no source binding administrators."""
    return [entry for entry in value.get("rulesets") or []
            if isinstance(entry, dict) and entry.get("bypass_actors") is None
            and decisive(value, entry, None if admins else False)]


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


# --------------------------------------------------------------------------
# Classic protection and rulesets together (sd:1419)
# --------------------------------------------------------------------------


def combine(classic: dict[str, Any], rules: list, rulesets: dict[int, dict]) -> dict[str, Any]:
    """Classic protection and the branch's rulesets, layered the way GitHub
    layers them: for each merge-gating rule, the strictest source wins.

    A single contributing source keeps today's object: `classic` itself when
    no active ruleset gates the merge, and `synthesize`'s object when classic
    carries neither a review nor a checks requirement. Otherwise the object
    is classic-shaped, marked `source: "combined"`, and carries per rule:
    `sources` (every source imposing it, `classic` or `ruleset:<id>`),
    `firm` (the ones nobody can bypass) and `admins` (whether a source
    binds administrators: `True`, `False` or `None` for unknown). The
    requirement itself is the strictest among the firm sources, or among
    all of them when none is firm -- a rule whose every source can be
    bypassed, which the gate refuses and `sd-status` reports as `bypass`.
    `advisory` names a stricter source that is not firm; `bypass_info` names
    a bypass that is not decisive. `enforce_admins` is `True` only when
    every rule has a source binding administrators, `False` when one has
    none that could, and `None` otherwise.
    """
    synthesized = synthesize(rules, rulesets)
    if synthesized is None:
        return classic
    classic_source = _classic_source(classic)
    if not classic_source["rules"]:
        return synthesized
    gating = [rule for rule in active_rules(rules, rulesets) if rule.get("type") in MERGE_GATING_RULES]
    sources = [classic_source] + [_ruleset_source(entry, gating) for entry in synthesized["rulesets"]]
    value: dict[str, Any] = {"source": COMBINED_SOURCE, "rulesets": synthesized["rulesets"],
                             "sources": {}, "firm": {}, "admins": {}, "advisory": []}
    for rule in sorted(MERGE_GATING_RULES):
        _layer_rule(value, rule, [source for source in sources if rule in source["rules"]], classic_source)
    verdicts = list(value["admins"].values())
    value["enforce_admins"] = {"enabled": False if False in verdicts else (None if None in verdicts else True)}
    value["bypass_info"] = _bypass_info(value)
    return value


def _layer_rule(value: dict[str, Any], rule: str, imposing: list[dict[str, Any]],
                classic_source: dict[str, Any]) -> None:
    """One rule of `combine`: its sources, its firm ones, its administrators,
    the requirement the firm sources set, and the stricter asks they do not."""
    if not imposing:
        return
    firm = [source for source in imposing if _firm(source, rule)]
    effective = _strictest(rule, [source["rules"][rule] for source in firm or imposing])
    value["sources"][rule] = [source["name"] for source in imposing]
    value["firm"][rule] = [source["name"] for source in firm]
    value["admins"][rule] = _rule_admins([source["admins"] for source in imposing])
    if firm:
        value["advisory"].extend(
            f"{source['label']} [{rule}] asks for more than the firm sources, but {source['why']}, "
            "so it is advisory and the requirement is theirs"
            for source in imposing
            if source not in firm and _strictest(rule, [effective, source["rules"][rule]]) != effective)
    if rule != "pull_request":
        value["required_status_checks"] = effective
        return
    allowances = classic_source["allowances"]
    if not firm and classic_source in imposing and allowances:
        effective = dict(effective, bypass_pull_request_allowances=allowances)
    value["required_pull_request_reviews"] = effective


def _classic_source(classic: dict[str, Any]) -> dict[str, Any]:
    """Classic protection as one source: its two merge-gating rules in the
    normalized shape `_reviews` and `_checks` give a ruleset's."""
    admins = classic.get("enforce_admins")
    enforced = (admins.get("enabled") if isinstance(admins, dict) else admins) is True
    found: dict[str, Any] = {}
    reviews = classic.get("required_pull_request_reviews")
    allowances: dict[str, Any] = {}
    if isinstance(reviews, dict):
        count = reviews.get("required_approving_review_count")
        found["pull_request"] = {
            "required_approving_review_count": count if isinstance(count, int) else 0,
            "dismiss_stale_reviews": reviews.get("dismiss_stale_reviews") is True,
            "require_code_owner_reviews": reviews.get("require_code_owner_reviews") is True,
            "require_last_push_approval": reviews.get("require_last_push_approval") is True,
        }
        raw = reviews.get("bypass_pull_request_allowances")
        if isinstance(raw, dict) and any(raw.get(name) for name in ("users", "teams", "apps")):
            allowances = raw
    checks = classic.get("required_status_checks")
    if isinstance(checks, dict) and checks:
        contexts = [str(name) for name in checks.get("contexts") or []]
        bound = [{"context": str(entry["context"]), "app_id": entry.get("app_id")}
                 for entry in checks.get("checks") or [] if isinstance(entry, dict) and entry.get("context")]
        found["required_status_checks"] = {"strict": checks.get("strict") is True,
                                           "contexts": contexts, "checks": bound}
    why = "enforce_admins is off" if not enforced else "it has pull-request bypass allowances"
    return {"name": CLASSIC_SOURCE, "label": "classic protection", "rules": found, "admins": enforced,
            "allowances": allowances, "why": why}


def _ruleset_source(entry: dict[str, Any], gating: list[dict]) -> dict[str, Any]:
    """One contributing ruleset as a source, its rules reduced on their own."""
    mine = [rule for rule in gating if rule.get("ruleset_id") == entry["id"]]
    found: dict[str, Any] = {}
    reviews = _reviews([_parameters(rule) for rule in mine if rule.get("type") == "pull_request"])
    if reviews is not None:
        found["pull_request"] = reviews
    checks = _checks([_parameters(rule) for rule in mine if rule.get("type") == "required_status_checks"])
    if checks is not None:
        found["required_status_checks"] = checks
    actors = entry.get("bypass_actors")
    why = ("its bypass list was not shown" if actors is None
           else "it can be bypassed by " + ", ".join(actor_words(actor) for actor in actors))
    return {"name": f"ruleset:{entry['id']}", "label": f"{entry.get('name')} (#{entry.get('id')})",
            "rules": found, "admins": _admins_subject([actors]), "actors": actors, "why": why}


def _firm(source: dict[str, Any], rule: str) -> bool:
    """Whether nobody can bypass `source` for `rule`."""
    if source["name"] == CLASSIC_SOURCE:
        return source["admins"] is True and (rule != "pull_request" or not source["allowances"])
    return source.get("actors") == []


def _rule_admins(verdicts: list[bool | None]) -> bool | None:
    """Administrators on one rule: bound when any source imposing it binds
    them, exempt when every source lets them past, else unknown (Q1)."""
    if True in verdicts:
        return True
    return None if None in verdicts else False


def _strictest(rule: str, parameter_sets: list[dict[str, Any]]) -> dict[str, Any]:
    """The normalized requirement for `rule` that satisfies every set given."""
    if rule == "pull_request":
        return {
            "required_approving_review_count": max(p["required_approving_review_count"] for p in parameter_sets),
            "dismiss_stale_reviews": any(p["dismiss_stale_reviews"] for p in parameter_sets),
            "require_code_owner_reviews": any(p["require_code_owner_reviews"] for p in parameter_sets),
            "require_last_push_approval": any(p["require_last_push_approval"] for p in parameter_sets),
        }
    contexts: list[str] = []
    checks: list[dict[str, Any]] = []
    for parameters in parameter_sets:
        for context in parameters["contexts"]:
            if context not in contexts:
                contexts.append(context)
        for entry in parameters["checks"]:
            if entry["context"] not in [known["context"] for known in checks]:
                checks.append(dict(entry))
    return {"strict": any(p["strict"] for p in parameter_sets), "contexts": contexts, "checks": checks}


def _bypass_info(value: dict[str, Any]) -> list[str]:
    """The bypasses of a combined object that remove no last enforcement:
    `main (#42) [pull_request]: Integration 77 (pull_request)`, and a
    withheld list as `... : bypass_actors not shown`. Information, sorted."""
    words = []
    for entry in value.get("rulesets") or []:
        actors = entry.get("bypass_actors")
        if actors is None:
            if not decisive(value, entry, False):
                words.append(f"{scope(entry)}: bypass_actors not shown")
            continue
        words.extend(f"{scope(entry)}: {actor_words(actor)}" for actor in actors
                     if not decisive(value, entry, reaches_admins(actor)))
    return sorted(words)


def combined_admins_words(value: dict[str, Any], default_branch: str) -> str:
    """`enforce_admins` off on a combined object: the rules no source binds
    administrators on, each with why every source lets them past, then the
    rules a source still binds them on."""
    names = {"classic": "classic protection (enforce_admins off)"}
    for entry in value.get("rulesets") or []:
        actors = [actor_words(actor) for actor in entry.get("bypass_actors") or [] if reaches_admins(actor)]
        names[f"ruleset:{entry.get('id')}"] = f"{scope(entry)} by {', '.join(actors) or 'an actor'}"
    exempt = [rule for rule, verdict in sorted((value.get("admins") or {}).items()) if verdict is False]
    binding = [rule for rule, verdict in sorted((value.get("admins") or {}).items()) if verdict is True]
    detail = "; ".join(f"{rule}: " + ", ".join(names.get(name, name) for name in value["sources"][rule])
                       for rule in exempt)
    words = (f"enforce_admins is off on {default_branch} for {', '.join(exempt)}: every source of "
             f"{'that rule' if len(exempt) == 1 else 'those rules'} exempts the admins who do the merging "
             f"({detail}). Protection that exempts admins is prose, not authority.")
    if binding:
        words += f" Still binding them: {', '.join(binding)}."
    return words
