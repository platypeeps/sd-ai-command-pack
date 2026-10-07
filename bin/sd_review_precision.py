"""Reviewer precision, read from ship receipts: `sd providers precision` (sd:1832, sd:1788).

Every local review `sd-ship` runs lands in a ship receipt, the newest
`checkpoint` row of a `ship:` or `ship-review-no-item:` key. Each pass in it
carries the review report, and each finding there names its reviewer
(`backend`), `severity`, `family` and the review's own `disposition`:
`blocking` or `advisory`. What happened to a blocking finding afterwards is
recorded in two places, and this module reads both; it writes nothing.

- **rebutted** or **parked**: an accepted adjudication (`sd-ship adjudicate`)
  names the finding by its digest, under the `ship-adjudication:` or
  `ship-adjudication-no-item:` key beside the receipt. Every accepted
  revision counts, because each one adjudicates a different head.
- **fixed**: no adjudication names it, and a later pass of the same receipt
  reviewed a different head. A blocking finding stops the ship, so a new head
  under review means a commit answered it. This is inferred, not stated: a
  commit that answers a different finding reads the same.
- **undecided**: blocking, never adjudicated, and no later head was reviewed:
  an abandoned branch, or a report a re-review of the same head replaced.
- **advisory**: the review did not block on it, and nothing records whether
  anybody acted on it.

Precision is held / decided: held is fixed plus parked, since a parked
finding was accurate and only its fix was deferred; decided adds rebutted.
Undecided and advisory findings carry no decision, so they stay out of both.

Out of scope: reviews run outside `sd-ship` leave no receipt, so they are not
counted. Passes imported into a no-item record (`historical_passes`) are
untrusted evidence and are skipped. The receipt names the registry entry, not
its model, so a provider whose model changed reads as one provider.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from typing import Any

import sd_handoff_rows
from sd_ship_dispositions import digest

#: Receipt key prefix -> the adjudication key prefix beside it; the suffix is shared.
RECEIPTS = {"ship:": "ship-adjudication:", "ship-review-no-item:": "ship-adjudication-no-item:"}
OUTCOMES = ("fixed", "parked", "rebutted", "undecided", "advisory")
DEFINITION = "precision = (fixed + parked) / (fixed + parked + rebutted)"


def _latest(connection: Any, prefix: str) -> list[tuple[str, dict]]:
    rows = connection.execute(
        "SELECT key, body FROM state s WHERE kind = 'checkpoint' AND key LIKE ? AND id = "
        "(SELECT max(id) FROM state t WHERE t.kind = 'checkpoint' AND t.key = s.key) ORDER BY id",
        (prefix + "%",)).fetchall()
    return [(row[0], json.loads(row[1])) for row in rows]


def _adjudicated(connection: Any) -> dict[str, dict[str, tuple[str, str]]]:
    """Adjudication key -> {finding digest: (response disposition, reason)} over every accepted revision."""
    found: dict[str, dict[str, tuple[str, str]]] = {}
    for prefix in RECEIPTS.values():
        for key, body in connection.execute(
                "SELECT key, body FROM state WHERE kind = 'checkpoint' AND key LIKE ? ORDER BY id", (prefix + "%",)):
            value = json.loads(body)
            if value.get("decision") != "accepted":
                continue
            for row in (value.get("proposal") or {}).get("findings") or []:
                found.setdefault(key, {})[row.get("finding_digest")] = (row.get("response_disposition"), row.get("reason"))
    return found


def finding_outcomes(connection: Any) -> list[dict]:
    """One row per finding in every receipt's passes, set-aside passes first, each with its outcome."""
    adjudicated = _adjudicated(connection)
    rows = []
    for prefix, acceptance in RECEIPTS.items():
        for key, state in _latest(connection, prefix):
            decided = adjudicated.get(acceptance + key.removeprefix(prefix), {})
            passes = [run for review in state.get("superseded_reviews") or [] for run in review.get("passes") or []]
            passes += state.get("passes") or []
            pull = state.get("pull_request") or {}
            for index, run in enumerate(passes):
                if not isinstance(run.get("report"), dict):
                    continue
                later = {other.get("head") for other in passes[index + 1:]} - {run.get("head")}
                for finding in run["report"].get("findings") or []:
                    outcome, reason = decided.get(digest(finding), (None, None))
                    if finding.get("disposition") != "blocking":
                        outcome = "advisory"
                    elif outcome is None:
                        outcome = "fixed" if later else "undecided"
                    rows.append({
                        "provider": finding.get("backend"), "severity": finding.get("severity"),
                        "family": finding.get("family"), "review_disposition": finding.get("disposition"),
                        "outcome": outcome, "reason": reason, "repository": state.get("repository"),
                        "pull_request": pull.get("number"), "item": state.get("item"),
                        "review_id": state.get("review_id"), "branch": state.get("branch"),
                        "head": run.get("head"), "started_at": run.get("started_at"),
                        "path": finding.get("path"), "line": finding.get("line"),
                        "summary": finding.get("summary"), "receipt": key})
    return rows


def summary(rows: list[dict]) -> list[dict]:
    """Counts per outcome and precision, per provider and severity, then per provider over every severity."""
    counts: dict[tuple[str, str], Counter] = {}
    for row in rows:
        for severity in (str(row["severity"]), "all"):
            counts.setdefault((str(row["provider"]), severity), Counter())[row["outcome"]] += 1
    table = []
    for (provider, severity), count in sorted(counts.items(), key=lambda entry: (entry[0][0], entry[0][1] == "all", entry[0][1])):
        held, decided = count["fixed"] + count["parked"], count["fixed"] + count["parked"] + count["rebutted"]
        table.append({"provider": provider, "severity": severity, "raised": sum(count.values()),
                      **{outcome: count[outcome] for outcome in OUTCOMES},
                      "precision": round(held / decided, 3) if decided else None})
    return table


def render_table(rows: list[dict], table: list[dict]) -> str:
    receipts = len({row["receipt"] for row in rows})
    lines = [f"reviewer precision over {len(rows)} finding(s) in {receipts} ship receipt(s); {DEFINITION}"]
    header = ("provider", "severity", "raised", *OUTCOMES, "precision")
    cells = [header] + [(*(str(entry[name]) for name in header[:-1]),
                         "-" if entry["precision"] is None else f"{entry['precision']:.0%}") for entry in table]
    widths = [max(len(cell[column]) for cell in cells) for column in range(len(header))]
    lines += ["  ".join(cell[column].ljust(widths[column]) for column in range(len(header))).rstrip() for cell in cells]
    return "\n".join(lines)


def precision_command(args: argparse.Namespace) -> int:
    connection = sd_handoff_rows.connect(sd_handoff_rows.library(), write=False)
    try:
        rows = finding_outcomes(connection)
    finally:
        connection.close()
    rows = [row for row in rows if (args.repository is None or row["repository"] == args.repository)
            and (args.since is None or str(row["started_at"] or "") >= args.since)]
    table = summary(rows)
    if args.json:
        print(json.dumps({"definition": DEFINITION, "summary": table, "findings": rows}, ensure_ascii=False))
    else:
        print(render_table(rows, table))
    return 0


def register_precision(verbs: Any) -> None:
    command = verbs.add_parser("precision", help="each reviewer's findings by outcome, and its precision, "
                                                 "per severity, read from ship receipts")
    command.set_defaults(handler=precision_command)
    command.add_argument("--json", action="store_true", help="the summary plus one row per finding")
    command.add_argument("--repository", metavar="OWNER/NAME", help="only this repository's receipts")
    command.add_argument("--since", metavar="DATE", help="only passes started at or after DATE (YYYY-MM-DD)")
