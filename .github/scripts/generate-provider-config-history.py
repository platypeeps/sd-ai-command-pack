#!/usr/bin/env python3
"""Record every digest each `if-not-exists` template has ever shipped.

`install: if-not-exists` writes a file once and never touches it again, which
is right while the consumer owns the content and wrong the moment the shipped
default itself needs a correction: `install.py --force` reports `preserved`
and the fix reaches nobody.

Separating those two cases needs one fact the installer cannot otherwise
learn -- whether the bytes on disk are something this pack shipped, or
something a consumer wrote. A digest the pack published under its own name
answers that without asking the consumer to have recorded anything at install
time, which matters because the checkouts that need the fix recorded nothing.

This generator maintains that record. It runs in `prepare-release.py` before
the self-sync install, so a release that changes a template cannot ship
without adding the template's digest first, and the root `docs/` copy comes
from the install rather than a second write here.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "manifest.json"
ARTIFACT = ROOT / "templates/docs/sd-ai-command-pack-provider-config-history.json"
SCHEMA_VERSION = 1
IF_NOT_EXISTS = "if-not-exists"

sys.path.insert(0, str(ROOT))

from installer.fileops import source_digest  # noqa: E402


class GenerateError(RuntimeError):
    """A condition that must stop the release rather than ship a guess."""


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise GenerateError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def _repository_is_shallow() -> bool:
    return _git("rev-parse", "--is-shallow-repository").strip() == "true"


def historical_digests(source: str) -> list[str]:
    """Every distinct digest `source` has had, oldest first.

    Only ever called for a source the artifact has never seen. Once a source
    is recorded, its digests are appended to and never re-derived, so a later
    history rewrite cannot retract a digest a consumer is actually holding.
    """

    if _repository_is_shallow():
        raise GenerateError(
            f"cannot seed history for {source!r} from a shallow clone: the "
            "digests a consumer is holding may predate the graft point, and "
            "seeding a partial list would report those consumers as "
            "customized. Re-run with full history."
        )

    digests: list[str] = []
    seen: set[str] = set()
    commits = _git("log", "--follow", "--format=%H", "--reverse", "--", source).split()
    for commit in commits:
        blob = subprocess.run(
            ["git", "rev-parse", f"{commit}:{source}"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if blob.returncode != 0:
            # The path did not exist at this commit -- `--follow` reports
            # renames, so the pre-rename commits address the file under its
            # old name and simply have nothing at this one.
            continue
        content = subprocess.run(
            ["git", "cat-file", "blob", blob.stdout.strip()],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )
        if content.returncode != 0:
            raise GenerateError(f"cannot read blob for {source!r} at {commit}")
        digest = source_digest(content.stdout)
        if digest not in seen:
            seen.add(digest)
            digests.append(digest)
    return digests


def load_artifact() -> dict:
    if not ARTIFACT.exists():
        return {"schemaVersion": SCHEMA_VERSION, "sources": {}}
    try:
        artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise GenerateError(f"{ARTIFACT} is not valid JSON: {error}") from error
    version = artifact.get("schemaVersion")
    if version != SCHEMA_VERSION:
        raise GenerateError(
            f"{ARTIFACT} declares schemaVersion {version!r}; this generator "
            f"writes {SCHEMA_VERSION}. Migrate deliberately rather than "
            "overwriting a record consumers are matched against."
        )
    if not isinstance(artifact.get("sources"), dict):
        raise GenerateError(f"{ARTIFACT} has no 'sources' object")
    return artifact


def if_not_exists_records() -> list[dict]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return [
        record
        for record in manifest["files"]
        if record.get("install") == IF_NOT_EXISTS
    ]


def generate() -> bool:
    """Update the artifact in place. Returns whether it changed."""

    artifact = load_artifact()
    sources = artifact["sources"]
    before = json.dumps(artifact, sort_keys=True)

    for record in if_not_exists_records():
        source = record["source"]
        template = ROOT / source
        if not template.is_file():
            raise GenerateError(
                f"manifest declares {source!r} as {IF_NOT_EXISTS} but the "
                "template does not exist"
            )
        current = source_digest(template.read_bytes())

        entry = sources.get(source)
        if entry is None:
            entry = {
                "target": record["target"],
                "current": current,
                "digests": historical_digests(source),
            }
            sources[source] = entry
            print(
                f"provider config history: seeded {source} with "
                f"{len(entry['digests'])} digest(s) from git history"
            )

        # A source dropped from the manifest keeps its entry: a consumer can
        # still be holding what it shipped, and forgetting that would report
        # them as customized. Nothing here removes a digest or a source.
        if entry["target"] != record["target"]:
            entry["target"] = record["target"]
        # `current` is stated rather than inferred from the tail of `digests`.
        # A template that reverts to content it shipped before adds no new
        # digest, so the tail would then name the wrong bytes -- and the
        # consumer-side reader has no templates of its own to check against.
        entry["current"] = current
        if current not in entry["digests"]:
            entry["digests"].append(current)
            print(f"provider config history: recorded new digest for {source}")

    after = json.dumps(artifact, sort_keys=True)
    if after == before and ARTIFACT.exists():
        return False

    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return True


def main() -> int:
    try:
        changed = generate()
    except GenerateError as error:
        print(f"provider config history: {error}", file=sys.stderr)
        return 1
    print(
        "provider config history: "
        + ("updated " if changed else "unchanged ")
        + str(ARTIFACT.relative_to(ROOT))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
