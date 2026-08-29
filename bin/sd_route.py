"""Review routing: which providers see a change, and why.

One pure function. ``route`` takes the paths a change touches, how many lines it
moves, whether the pull request is a draft, and a policy dictionary the caller
loaded from JSON. It returns a :class:`Plan`. It reads no files, runs no
subprocesses, and asks no network -- everything it decides is a function of its
arguments, so a fixture is a dict and a plan is comparable with ``==``.

The policy is data on purpose. Which categories exist, which paths are sensitive,
which tier each category starts at, and which providers each tier chains are all
per-repository choices; the rules for combining them are not.

Policy shape (every key optional unless noted)::

    {
      "tier_order": ["skip", "cheap", "standard", "deep"],
      "tiers": {"skip": [], "cheap": ["codex"], "deep": ["codex", "prism"]},
      "default_tier": "standard",
      "categories": [
        {"name": "installer", "required": true, "paths": ["installer/**"],
         "tier": "deep"}
      ],
      "docs_skip": ["docs/**", "*.md"],
      "never_skip": ["docs/spec/**"],
      "sensitive": [".github/workflows/**"],
      "large_change_lines": 800
    }
"""

from __future__ import annotations

import re
from typing import Any, Mapping, NamedTuple, Sequence

DEFAULT_TIER_ORDER: tuple[str, ...] = ("skip", "cheap", "standard", "deep")
DEFAULT_LARGE_CHANGE_LINES = 800


class Plan(NamedTuple):
    """The routing decision for one change."""

    tier: str
    providers: tuple[str, ...]
    category: str | None
    reason: str


def route(
    paths: Sequence[str],
    lines: int,
    draft: bool,
    policy: Mapping[str, Any],
) -> Plan:
    """Decide which review tier a change gets, and which providers run in it.

    The order below is the whole contract, and each step can only be reached
    when the one before it did not settle the question:

    1. Categories match required-first, so a repository can guarantee that
       "touches the installer" outranks "is mostly documentation" no matter
       which order the two appear in the file. The matched category names the
       starting tier; without a match the policy default starts it.
    2. A change whose every path is in the ``docs_skip`` allow-list plans
       ``skip`` -- unless any path is in the ``never_skip`` deny-list, which
       always wins. That deny-list is why the allow-list is safe to widen: a
       repository can say "documentation is free" and still keep one directory
       inside it reviewed.
    3. A sensitive path or a change past the line threshold escalates one tier
       each, up to the top of the chain.
    4. A draft asks for the cheapest tier that still reviews something: drafts
       are re-reviewed when they open, so paying the deep chain twice buys
       nothing. A plan that already reached ``skip`` stays there, being cheaper.
    """

    order = _tier_order(policy)
    tiers = policy.get("tiers") or {}
    ordered_paths = tuple(paths)

    category, category_tier = _match_category(ordered_paths, policy, order)
    tier = category_tier or _clamp(str(policy.get("default_tier") or order[-1]), order)
    reasons: list[str] = []
    if category:
        reasons.append(f"category {category} starts at tier {tier}")
    else:
        reasons.append(f"no category matched; default tier {tier}")

    blocked = _first_match(ordered_paths, policy.get("never_skip"))
    skippable = _all_match(ordered_paths, policy.get("docs_skip"))

    if skippable and blocked is None and "skip" in order:
        tier = "skip"
        reasons.append("every path is in the docs-skip allow-list")
    else:
        if skippable and blocked is not None:
            reasons.append(f"{blocked} is in the never-skip deny-list, so skip is not available")

        sensitive = _first_match(ordered_paths, policy.get("sensitive"))
        if sensitive is not None:
            tier = _escalate(tier, order)
            reasons.append(f"{sensitive} is a sensitive path, escalated to {tier}")

        threshold = _threshold(policy)
        if lines > threshold:
            tier = _escalate(tier, order)
            reasons.append(f"{lines} lines is above the {threshold}-line threshold, escalated to {tier}")

    if draft and tier != "skip":
        cheapest = _cheapest_reviewing_tier(order)
        if cheapest != tier:
            tier = cheapest
            reasons.append(f"draft pull request, reduced to the cheapest reviewing tier {tier}")
        else:
            reasons.append("draft pull request, already at the cheapest reviewing tier")

    providers = tuple(str(name) for name in tiers.get(tier, ()))
    return Plan(tier=tier, providers=providers, category=category, reason="; ".join(reasons))


def _tier_order(policy: Mapping[str, Any]) -> tuple[str, ...]:
    declared = policy.get("tier_order")
    if isinstance(declared, Sequence) and not isinstance(declared, (str, bytes)):
        order = tuple(str(name) for name in declared)
        if order:
            return order
    return DEFAULT_TIER_ORDER


def _threshold(policy: Mapping[str, Any]) -> int:
    declared = policy.get("large_change_lines")
    if isinstance(declared, bool) or not isinstance(declared, int):
        return DEFAULT_LARGE_CHANGE_LINES
    return declared


def _clamp(tier: str, order: tuple[str, ...]) -> str:
    return tier if tier in order else order[-1]


def _escalate(tier: str, order: tuple[str, ...]) -> str:
    try:
        index = order.index(tier)
    except ValueError:
        return order[-1]
    return order[min(index + 1, len(order) - 1)]


def _cheapest_reviewing_tier(order: tuple[str, ...]) -> str:
    for name in order:
        if name != "skip":
            return name
    return order[-1]


def _match_category(
    paths: Sequence[str], policy: Mapping[str, Any], order: tuple[str, ...]
) -> tuple[str | None, str | None]:
    declared = policy.get("categories") or ()
    categories = [item for item in declared if isinstance(item, Mapping)]
    for required in (True, False):
        for category in categories:
            if bool(category.get("required")) is not required:
                continue
            if _first_match(paths, category.get("paths")) is None:
                continue
            name = str(category.get("name") or "")
            tier = category.get("tier")
            return (name or None, _clamp(str(tier), order) if tier else None)
    return (None, None)


def _first_match(paths: Sequence[str], patterns: Any) -> str | None:
    """The first path matching any pattern, in the order the caller gave them."""
    compiled = _compile(patterns)
    if not compiled:
        return None
    for path in paths:
        if any(pattern.match(path) for pattern in compiled):
            return path
    return None


def _all_match(paths: Sequence[str], patterns: Any) -> bool:
    """True when there is at least one path and every one of them matches."""
    compiled = _compile(patterns)
    if not compiled or not paths:
        return False
    return all(any(pattern.match(path) for pattern in compiled) for path in paths)


def _compile(patterns: Any) -> list[re.Pattern[str]]:
    if not isinstance(patterns, Sequence) or isinstance(patterns, (str, bytes)):
        return []
    return [_glob_to_regex(str(pattern)) for pattern in patterns]


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Translate a path glob, giving ``**`` and ``*`` their usual different reach.

    ``fnmatch`` cannot be used here: its ``*`` crosses directory separators, so
    ``docs/*`` would match ``docs/spec/index.md`` and a deny-list written one
    level deep would silently cover the whole tree.
    """
    out: list[str] = []
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "*":
            if pattern.startswith("**", index):
                index += 2
                if pattern.startswith("/", index):
                    index += 1
                    out.append("(?:.*/)?")
                else:
                    out.append(".*")
                continue
            out.append("[^/]*")
        elif char == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(char))
        index += 1
    return re.compile(f"^{''.join(out)}$")
