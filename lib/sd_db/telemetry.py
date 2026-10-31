"""Build runs as OTLP traces, read from the store (pack sd:6943).

`sd-db telemetry export` turns each ended build run into one trace for the
Phoenix project `sd-workflow`: a root span for the run, then its claim,
build, each review round, enqueue, lane and merge, as far as the run's row,
its notes and its cost rows record them. The run id is the trace id and each
span id hashes the run id and the span's name, so a second export sends the
same spans again and the collector keeps one copy: the export backfills
history and is safe to run every night.

Metadata only: item ids and titles, the repository, the model, cost and
tokens, the review round, the outcome and a failure class. No note body,
prompt or `detail` text leaves the store: those hold local paths and review
prose. A missing collector is a skip, never a failure.

The lane's prepare and gate steps live in the lane's own files, not here:
the `lane` span runs from the enqueue to the merge or the run's end.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from datetime import datetime

from . import build

PROJECT = "sd-workflow"
#: `genai-traces.sh`'s OTLP/HTTP port; `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` overrides it.
ENDPOINT = "http://127.0.0.1:4338/v1/traces"
BATCH = 50

#: The failure classes, first match wins, read from a run's outcome and detail.
CLASSES = (
    ("lost_run", re.compile(r"supervisor lost|lost at step|lost .* a second time")),
    ("timed_out", re.compile(r"ran past \d+ s")),
    ("review_blockers", re.compile(r"review rounds left blockers|local review blocking")),
    ("review_no_answer", re.compile(r"review gave no answer")),
    ("db_locked", re.compile(r"database is locked|did not answer", re.I)),
    ("conflict", re.compile(r"conflict")),
    ("line_too_long", re.compile(r"lines? too long|\(limit 72\)")),
    ("leak_guard", re.compile(r"leak-guard")),
    ("no_closes_trailer", re.compile(r"Closes:")),
    ("denied_tool", re.compile(r"permission denied")),
    ("flake", re.compile(r"flak", re.I)),
    ("gate_failed", re.compile(r"gate failed|make check")),
    ("no_commit", re.compile(r"left no commit")),
    ("lint_refused", re.compile(r"sd-docs-lint refused")),
)


def failure_class(outcome: str | None, detail: str | None) -> str | None:
    """None for a run that merged; else the first class whose pattern the detail matches, or `other`."""
    if outcome in (None, "done"):
        return None
    if outcome == "cancelled":
        return "cancelled"
    text = detail or ""
    return next((name for name, pattern in CLASSES if pattern.search(text)), "other")


def _nanos(stamp: str) -> int:
    return int(datetime.fromisoformat(stamp).timestamp()) * 1_000_000_000


def _span_id(run: str, name: str) -> str:
    return hashlib.sha256(f"{run}/{name}".encode()).hexdigest()[:16]


def _value(value) -> dict:
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, int):
        return {"intValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    return {"stringValue": str(value)}


def _attributes(values: dict) -> list[dict]:
    return [{"key": key, "value": _value(value)} for key, value in values.items() if value is not None]


def _span(run: str, name: str, start: str, end: str, attributes: dict, *, root: bool = False,
          error: str | None = None) -> dict:
    span = {"traceId": run, "spanId": _span_id(run, name), "name": name.split("#")[0], "kind": 1,
            "startTimeUnixNano": str(_nanos(start)), "endTimeUnixNano": str(_nanos(max(start, end))),
            "attributes": _attributes(attributes),
            "status": {"code": 2, "message": error} if error else {"code": 1}}
    if not root:
        span["parentSpanId"] = _span_id(run, "build_run")
    return span


def run_spans(connection, row: dict) -> list[dict]:
    """One ended run's spans, the root first."""
    ident, start, end = row["id"], row["created_at"], row["released_at"]
    members = build.run(connection, ident)["members"]
    items = [member["item"] for member in members]
    marks = ", ".join("?" for _ in items)
    titles = [title for (title,) in connection.execute(
        f"SELECT title FROM item WHERE id IN ({marks}) ORDER BY id", items)]
    notes = [dict(note) for note in connection.execute(
        f"SELECT item, timestamp, body FROM note WHERE item IN ({marks}) AND timestamp >= ? "
        f"AND timestamp <= ? ORDER BY timestamp, id", (*items, start, end))]
    cost = connection.execute("SELECT SUM(usd), SUM(tokens_in), SUM(tokens_out) FROM cost WHERE pass = ?",
                              (ident,)).fetchone()
    failure = failure_class(row["outcome"], row["detail"])
    common = {"sd.build_run": ident, "sd.repo": row["repo"], "sd.items": ",".join(map(str, items))}
    reports = [note["timestamp"] for note in notes if note["body"].startswith(f"Build run {ident} report:")]
    enqueued = next((note for note in notes if note["body"].startswith(f"Build run {ident} enqueued ")), None)
    merged = enqueued and next((note for note in notes if note["timestamp"] >= enqueued["timestamp"]
                                and note["body"].startswith("Code delivery ")), None)
    spans = [_span(ident, "build_run", start, end, {
        **common, "openinference.span.kind": "CHAIN", "sd.item_titles": " | ".join(titles),
        "sd.branch": row["branch"], "sd.model": row["model"], "llm.model_name": row["model"],
        "sd.cost_usd": float(cost[0]) if cost[0] is not None else None,
        "sd.tokens_in": cost[1], "sd.tokens_out": cost[2], "sd.review_round": row["review_round"],
        "sd.step": row["step"], "sd.outcome": row["outcome"], "sd.failure_class": failure}, root=True, error=failure),
        _span(ident, "claim", start, start, common)]
    building = reports[0] if reports else (enqueued["timestamp"] if enqueued else end)
    spans.append(_span(ident, "build", start, building, common))
    for number, (since, until) in enumerate(zip(reports, reports[1:], strict=False), start=1):
        spans.append(_span(ident, f"review_round#{number}", since, until, {**common, "sd.review_round": number}))
    if enqueued:
        entry = re.search(r"as entry (\S+)", enqueued["body"])
        lane = {**common, "sd.lane_entry": entry.group(1) if entry else None}
        spans.append(_span(ident, "enqueue", enqueued["timestamp"], enqueued["timestamp"], lane))
        spans.append(_span(ident, "lane", enqueued["timestamp"], merged["timestamp"] if merged else end, lane,
                           error=None if merged else failure))
    if merged:
        pull = re.search(r"/pull/(\d+)", merged["body"])
        commit = re.search(r"\bat ([0-9a-f]{40})\b", merged["body"])
        spans.append(_span(ident, "merge", merged["timestamp"], merged["timestamp"], {
            **common, "sd.pr": int(pull.group(1)) if pull else None, "sd.commit": commit.group(1) if commit else None}))
    return spans


def ended_runs(connection) -> list[dict]:
    """Every ended build run, oldest first: the whole history, each export."""
    return [dict(row) for row in connection.execute(
        "SELECT runner_run.* FROM runner_run JOIN assignment ON assignment.id = runner_run.assignment "
        "WHERE assignment.scope = ? AND runner_run.released_at IS NOT NULL AND runner_run.outcome IS NOT NULL "
        "ORDER BY runner_run.created_at, runner_run.id", (build.SCOPE,))]


def payload(spans: list[dict]) -> dict:
    """The OTLP/JSON request body for `spans`."""
    resource = _attributes({"service.name": PROJECT, "openinference.project.name": PROJECT})
    return {"resourceSpans": [{"resource": {"attributes": resource},
                               "scopeSpans": [{"scope": {"name": "sd_db.telemetry"}, "spans": spans}]}]}


def export(connection, endpoint: str = ENDPOINT, *, timeout: float = 10.0) -> dict:
    """Send every ended run; `{"runs", "spans", "skipped"}`. `skipped` names why nothing was sent, else None.

    A refused or unreachable collector is a skip; an HTTP error from a reached one raises, it is a fault.
    """
    runs = ended_runs(connection)
    spans = [run_spans(connection, row) for row in runs]
    sent = 0
    for first in range(0, len(spans), BATCH):
        batch = [span for group in spans[first:first + BATCH] for span in group]
        request = urllib.request.Request(endpoint, data=json.dumps(payload(batch)).encode(), method="POST",
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=timeout):
                pass
        except urllib.error.HTTPError:
            raise
        except (urllib.error.URLError, OSError) as failure:
            return {"runs": len(runs), "spans": sent, "skipped": f"no collector at {endpoint}: {failure}"}
        sent += len(batch)
    return {"runs": len(runs), "spans": sent, "skipped": None}
