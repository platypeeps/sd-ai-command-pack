"""Which `if-not-exists` payload bytes this pack has previously shipped.

`if-not-exists` writes a file once and never again, so a consumer that never
touched it and a consumer that rewrote it are indistinguishable at install
time: both hold bytes that differ from the current template, and both are
reported `preserved`. That is correct for the second and useless for the
first -- a correction to a broken shipped default reaches nobody.

The digest history closes exactly that gap. Bytes matching something the pack
published under its own name are not a local decision, so replacing them
restores the pack's intent rather than discarding the consumer's. Bytes
matching nothing the pack ever shipped are a decision, and stay untouched.

Every failure here resolves toward `preserved`: a missing, malformed, or
unreadable history means the installer cannot prove the pack shipped these
bytes, and the cost of guessing wrong is overwriting work someone did.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Mapping

from installer.registry import ROOT

HISTORY_SOURCE = Path("templates/docs/sd-ai-command-pack-provider-config-history.json")
SUPPORTED_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ProviderConfigHistory:
    """Shipped digests keyed by install target, or the reason there are none."""

    digests_by_target: Mapping[str, frozenset[str]]
    unavailable_reason: str | None = None

    def shipped(self, target: Path, digest: str) -> bool:
        return digest in self.digests_by_target.get(target.as_posix(), frozenset())


_EMPTY_REASON = "provider config history is empty"


def _unavailable(reason: str) -> ProviderConfigHistory:
    return ProviderConfigHistory(digests_by_target={}, unavailable_reason=reason)


def _parse(raw: object, path: Path) -> ProviderConfigHistory:
    if not isinstance(raw, dict):
        return _unavailable(f"{path} is not a JSON object")
    version = raw.get("schemaVersion")
    if version != SUPPORTED_SCHEMA_VERSION:
        # An unknown major means the file was written by a newer pack whose
        # meaning we cannot assume. Refusing to read it preserves consumer
        # content; guessing at it could overwrite content this version has no
        # basis to classify.
        return _unavailable(
            f"{path} declares schemaVersion {version!r}, expected "
            f"{SUPPORTED_SCHEMA_VERSION}"
        )
    sources = raw.get("sources")
    if not isinstance(sources, dict):
        return _unavailable(f"{path} has no 'sources' object")

    digests_by_target: dict[str, frozenset[str]] = {}
    for entry in sources.values():
        if not isinstance(entry, dict):
            return _unavailable(f"{path} has a malformed source entry")
        target = entry.get("target")
        digests = entry.get("digests")
        if not isinstance(target, str) or not isinstance(digests, list):
            return _unavailable(f"{path} has a malformed source entry")
        if not all(isinstance(digest, str) for digest in digests):
            return _unavailable(f"{path} has a non-string digest")
        digests_by_target[target] = frozenset(digests)

    if not digests_by_target:
        return _unavailable(_EMPTY_REASON)
    return ProviderConfigHistory(digests_by_target=digests_by_target)


@lru_cache(maxsize=None)
def load_provider_config_history(root: Path = ROOT) -> ProviderConfigHistory:
    """Read the shipped digest history, cached per pack root.

    Cached because an install evaluates every payload file and only two of
    them can ever consult this; re-reading the artifact hundreds of times to
    answer two questions would be the wrong trade.
    """

    path = root / HISTORY_SOURCE
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _unavailable(f"{HISTORY_SOURCE.as_posix()} is missing")
    except (OSError, json.JSONDecodeError) as error:
        return _unavailable(f"{HISTORY_SOURCE.as_posix()} is unreadable: {error}")
    return _parse(raw, HISTORY_SOURCE)


__all__ = [
    "HISTORY_SOURCE",
    "ProviderConfigHistory",
    "SUPPORTED_SCHEMA_VERSION",
    "load_provider_config_history",
]
