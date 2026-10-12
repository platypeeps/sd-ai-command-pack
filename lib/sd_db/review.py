"""One review queue, made of rows the store already has (sd:3635).

The design is system's `docs/work/2026-10-12-review-queue/design.md`. A
repository or an experiment files a batch of small questions; the operator
answers each with one option; the producer exports the labels with their
provenance. No table is new:

- A **batch** is one task filed under the ref `review:<queue>:<batch>`, the
  key `sd task add --ref` files under, so the unique index on `(source,
  external_id)` makes a second filing find the first.
- Its first comment is the **header**: queue, batch, schema, source, mode,
  the seal in sealed mode, the question count and the digest of the batch
  file. A note is append-only, so the header is what binds; the item's title
  and body may change and bind nothing.
- A **question** is a `question` note in the Decisions format (one `Option:`
  line per choice), plus one `Subject:` line and up to five `Evidence:` lines.
  The batch's questions are the header's count of question notes after it;
  a question added by hand later is not one of them.
- A **label** is the Decisions ruling, `Ruling on note #N: <option>`, written
  with the question's resolution in one transaction; **undo** is a
  `Withdrawn: ruling #M on note #N` decision with the question reopened; a
  **comment** is `On note #N: <text>`.

Modes: `open` shows everything; `blind` asks the reader to show the text and
options only (the dashboard's job, not this module's); `sealed` is blind plus
a key the producer keeps outside the store, whose SHA-256 the header holds.
A sealed export refuses another key and an open question, and commits the
batch's close before it parses the key. A batch once closed refuses every
ruling and withdrawal through `rule` and `withdraw`. Every label, and whether
a question is open, is read from the note history up to the first close and
never from a question's `resolved_at`: a note written after the close by
another path (`sd task note`, a reopen) is read as `late` and moves nothing.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import sqlite3
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from . import workflow, writes
from .database import transaction
from .writes import add_note, reopen_note, resolve_note

__all__ = ["ReviewError", "apply", "export", "file", "read", "rule", "withdraw", "write"]

#: The batch file's one schema.
SCHEMA = 1
#: The `item.source` `sd task add --ref` files under (`bin/sd_work.py`
#: `REF_SOURCE`), so a batch is found by the same ref either way.
REF_SOURCE = "task-ref"
MODES = ("open", "blind", "sealed")
#: A batch's ceiling; a larger set splits into batches.
LIMIT = 500
OPTION_COUNT = range(2, 10)
OPTION_CHARS = 80
TEXT_BYTES = 4096
EVIDENCE_LINES = 5
SUBJECT_CHARS = 200
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
SHA256 = re.compile(r"[0-9a-f]{64}")
KEYS = frozenset({"schema", "queue", "batch", "title", "repo", "source", "mode", "limit", "seal", "questions"})
QUESTION_KEYS = frozenset({"subject", "text", "evidence", "options"})
#: A question note's tagged lines; every other line is the question text.
TAGGED = re.compile(r"^[ \t]*(Option|Subject|Evidence):[ \t]*(.*?)[ \t]*$")
HEADER = "Review batch"
RULING = re.compile(r"Ruling on note #(\d+): (.+)")
WITHDRAWN = re.compile(r"Withdrawn: ruling #(\d+) on note #(\d+)")
COMMENT = re.compile(r"On note #(\d+): (.+)", re.DOTALL)
#: The `status_change` note `writes.transition` writes when an item closes.
CLOSE = re.compile(r"\S+ -> done by ")
#: The nightly queue's options, the ref prefix of the task an approval
#: files, and how long an unruled suggestion waits (operator, 2026-10-12).
APPROVE, REJECT = "Approve", "Reject"
APPROVED = "review-approved"
EXPIRE_DAYS = 7
EXPIRED = "Expired, not ruled"
#: How long a rejected subject keeps a suggestion out of its queue.
SUPPRESS_DAYS = 90
UNKNOWN = "unknown"


class ReviewError(workflow.WorkflowError):
    """A batch, a ruling or an export the queue refuses; nothing was written."""


# ---------------------------------------------------------------- the batch file


def _line(value: Any, name: str, *, limit: int | None = None) -> str:
    """One line of text, as filed: no padding, no line break, no NUL."""
    if (not isinstance(value, str) or not value or value != value.strip() or "\x00" in value
            or len(value.splitlines()) != 1):
        raise ReviewError(f"{name} must be one line of text with no padding")
    if limit is not None and len(value) > limit:
        raise ReviewError(f"{name} is {len(value)} characters; the limit is {limit}")
    return value


def _name(value: Any, name: str) -> str:
    if not isinstance(value, str) or not NAME.fullmatch(value):
        raise ReviewError(f"{name} must be letters, digits, dots, dashes or underscores, at most 64")
    return value


def _question(found: Any, where: str) -> dict:
    if not isinstance(found, dict) or set(found) - QUESTION_KEYS or not {"subject", "text", "options"} <= set(found):
        raise ReviewError(f"{where} must hold subject, text and options, and evidence at most")
    subject = _line(found["subject"], f"{where} subject", limit=SUBJECT_CHARS)
    text = found["text"]
    if not isinstance(text, str) or not text.strip() or "\x00" in text:
        raise ReviewError(f"{where} text must be text")
    text = text.strip()
    if len(text.encode("utf-8")) > TEXT_BYTES:
        raise ReviewError(f"{where} text is over {TEXT_BYTES} bytes")
    if any(TAGGED.match(line) for line in text.splitlines()):
        raise ReviewError(f"{where} text has a line that starts Option:, Subject: or Evidence:")
    evidence = found.get("evidence", [])
    if not isinstance(evidence, list) or len(evidence) > EVIDENCE_LINES:
        raise ReviewError(f"{where} evidence must be a list of at most {EVIDENCE_LINES} lines")
    options = found["options"]
    if not isinstance(options, list) or len(options) not in OPTION_COUNT:
        raise ReviewError(f"{where} needs {OPTION_COUNT.start} to {OPTION_COUNT.stop - 1} options")
    options = [_line(option, f"{where} option", limit=OPTION_CHARS) for option in options]
    if len(set(options)) != len(options):
        raise ReviewError(f"{where} repeats an option")
    return {"subject": subject, "text": text, "options": options,
            "evidence": [_line(line, f"{where} evidence") for line in evidence]}


def _checked(batch: Any) -> dict:
    """The batch file's fields, or a refusal naming the first that is wrong."""
    if not isinstance(batch, dict):
        raise ReviewError("a batch is a JSON object")
    unknown = set(batch) - KEYS
    if unknown:
        raise ReviewError(f"a batch takes no {', '.join(sorted(unknown))}")
    missing = {"schema", "queue", "batch", "title", "source", "mode", "questions"} - set(batch)
    if missing:
        raise ReviewError(f"a batch needs {', '.join(sorted(missing))}")
    if type(batch["schema"]) is not int or batch["schema"] != SCHEMA:
        raise ReviewError(f"schema must be {SCHEMA}")
    if batch["mode"] not in MODES:
        raise ReviewError(f"mode must be one of {', '.join(MODES)}")
    limit = batch.get("limit")
    if limit is not None and (type(limit) is not int or not 1 <= limit <= LIMIT):
        raise ReviewError(f"limit must be a whole number from 1 to {LIMIT}")
    seal = batch.get("seal")
    if (batch["mode"] == "sealed") != (seal is not None):
        raise ReviewError("a sealed batch needs a seal, and only a sealed batch takes one")
    if seal is not None and (not isinstance(seal, dict) or set(seal) != {"sha256", "name"}
                             or not isinstance(seal["sha256"], str) or not SHA256.fullmatch(seal["sha256"])):
        raise ReviewError("seal must be {\"sha256\": <64 lowercase hex>, \"name\": <the key file's name>}")
    repo = batch.get("repo")
    if repo is not None and not isinstance(repo, str):
        raise ReviewError("repo must be a registered checkout's path")
    questions = batch["questions"]
    if not isinstance(questions, list) or not questions:
        raise ReviewError("questions must be a list of at least one")
    if limit is None and len(questions) > LIMIT:
        raise ReviewError(f"{len(questions)} questions; a batch holds at most {LIMIT}, so split it or set a limit")
    checked = [_question(found, f"question {number}") for number, found in enumerate(questions, 1)]
    subjects = [found["subject"] for found in checked]
    if len(set(subjects)) != len(subjects):
        raise ReviewError("a subject appears twice; each is unique in its batch")
    return {"queue": _name(batch["queue"], "queue"), "batch": _name(batch["batch"], "batch"),
            "title": _line(batch["title"], "title"), "source": _line(batch["source"], "source"),
            "mode": batch["mode"], "limit": limit or LIMIT, "repo": repo,
            "seal": None if seal is None else {"sha256": seal["sha256"], "name": _line(seal["name"], "seal name")},
            "questions": checked}


def _digest(batch: dict) -> str:
    return hashlib.sha256(json.dumps(batch, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


def _header_body(found: dict, digest: str, count: int) -> str:
    lines = [HEADER, f"Queue: {found['queue']}", f"Batch: {found['batch']}", f"Schema: {SCHEMA}",
             f"Source: {found['source']}", f"Mode: {found['mode']}"]
    if found["seal"] is not None:
        lines.append(f"Seal: {found['seal']['sha256']} {found['seal']['name']}")
    return "\n".join([*lines, f"Questions: {count}", f"Digest: {digest}"])


def _question_body(found: dict) -> str:
    return "\n".join([found["text"], f"Subject: {found['subject']}",
                      *(f"Evidence: {line}" for line in found["evidence"]),
                      *(f"Option: {option}" for option in found["options"])])


# ---------------------------------------------------------------- reading a batch


def _parse_header(body: str) -> dict | None:
    lines = body.splitlines()
    if not lines or lines[0] != HEADER:
        return None
    fields = dict(line.split(": ", 1) for line in lines[1:] if ": " in line)
    if not {"Queue", "Batch", "Schema", "Source", "Mode", "Questions", "Digest"} <= set(fields):
        return None
    seal, _, name = fields.get("Seal", "").partition(" ")
    return {"queue": fields["Queue"], "batch": fields["Batch"], "schema": fields["Schema"],
            "source": fields["Source"], "mode": fields["Mode"], "seal": seal or None, "seal_name": name or None,
            "questions": int(fields["Questions"]) if fields["Questions"].isdigit() else -1,
            "digest": fields["Digest"]}


def _parse_question(note: dict) -> dict:
    text, subject, evidence, options = [], None, [], []
    for line in note["body"].splitlines():
        tagged = TAGGED.match(line)
        if tagged is None:
            text.append(line)
        elif tagged[1] == "Option":
            options.append(tagged[2])
        elif tagged[1] == "Evidence":
            evidence.append(tagged[2])
        elif subject is None:
            subject = tagged[2]
    return {"note": note["id"], "subject": subject, "text": "\n".join(text).strip(), "evidence": evidence,
            "options": options, "sha256": hashlib.sha256(note["body"].encode("utf-8")).hexdigest(),
            "asked_at": note["timestamp"]}


def _batch(row: dict, notes: list[dict]) -> dict:
    """The batch an item's row and notes hold, or a refusal when they hold none."""
    notes = sorted(notes, key=lambda note: note["id"])
    first = next((note for note in notes if note["kind"] == "comment"), None)
    header = None if first is None else _parse_header(first["body"])
    if (first is None or header is None or row["source"] != REF_SOURCE
            or row["external_id"] != f"review:{header['queue']}:{header['batch']}"):
        raise ReviewError(f"sd:{row['id']} is not a review batch")
    asked = [note for note in notes if note["kind"] == "question" and note["id"] > first["id"]]
    if len(asked) < header["questions"] or header["questions"] < 0:
        raise ReviewError(f"sd:{row['id']}'s header counts {header['questions']} questions; "
                          f"{len(asked)} follow it")
    questions = {note["id"]: {**_parse_question(note), "rulings": [], "comments": [], "late": [], "expired": False}
                 for note in asked[:header["questions"]]}
    # Every label is read from this note history up to the first close, never
    # from a question's `resolved_at`, which a writer may change after it: a
    # ruling, withdrawal or comment written after the close is kept as `late`
    # and moves nothing (lane review on 2ab91c11d).
    closed = next((note["id"] for note in notes if note["kind"] == "status_change"
                   and CLOSE.match(note["body"] or "")), None)
    rulings: dict[int, dict] = {}
    for note in notes:
        body = note["body"] or ""
        late = closed is not None and note["id"] > closed
        if note["kind"] == "decision" and (ruled := RULING.fullmatch(body)):
            question = questions.get(int(ruled[1]))
            if question is None or ruled[2] not in question["options"]:
                continue
            if late:
                question["late"].append({"note": note["id"], "body": body, "at": note["timestamp"]})
                continue
            rulings[note["id"]] = {"ruling": note["id"], "question": question["note"], "option": ruled[2],
                                   "by": note["session"], "at": note["timestamp"], "withdrawal": None}
            question["rulings"].append(rulings[note["id"]])
        elif note["kind"] == "decision" and (pulled := WITHDRAWN.fullmatch(body)):
            ruling = rulings.get(int(pulled[1]))
            if ruling is None or ruling["question"] != int(pulled[2]) or ruling["withdrawal"] is not None:
                continue
            if late:
                questions[ruling["question"]]["late"].append({"note": note["id"], "body": body,
                                                              "at": note["timestamp"]})
                continue
            ruling.update(withdrawal=note["id"], withdrawn_at=note["timestamp"])
        elif note["kind"] == "comment" and note["id"] > first["id"] and (said := COMMENT.fullmatch(body)):
            question = questions.get(int(said[1]))
            if question is not None and late:
                question["late"].append({"note": note["id"], "body": body, "at": note["timestamp"]})
            elif question is not None:
                question["expired"] = question["expired"] or said[2] == EXPIRED
                question["comments"].append({"note": note["id"], "text": said[2], "by": note["session"],
                                             "at": note["timestamp"]})
    for question in questions.values():
        standing = [ruling for ruling in question["rulings"] if ruling["withdrawal"] is None]
        live = standing[-1] if standing else None
        question.update(label=live and live["option"], ruling=live and live["ruling"],
                        ruled_by=live and live["by"], ruled_at=live and live["at"],
                        position=live and question["options"].index(live["option"]) + 1,
                        open=live is None and not question["expired"])
    found = list(questions.values())
    return {"item": row, "ref": row["external_id"], "header": header, "questions": found, "closed": closed,
            "open": sum(question["open"] for question in found),
            "labels": sum(question["label"] is not None for question in found)}


def read(connection: sqlite3.Connection, item: int) -> dict:
    """The batch `item` holds: its header, and each question with its standing label."""
    state = workflow.item_state(connection, item)
    return _batch(state["item"], state["notes"])


def _queue(connection: sqlite3.Connection, queue: str) -> list[dict]:
    prefix = f"review:{queue}:"
    rows = connection.execute(
        "SELECT id FROM item WHERE source = ? AND substr(external_id, 1, ?) = ? ORDER BY id",
        (REF_SOURCE, len(prefix), prefix)).fetchall()
    return [read(connection, row["id"]) for row in rows]


def _moment(now: str | None) -> datetime:
    moment = datetime.now(UTC) if now is None else datetime.fromisoformat(now)
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


# ---------------------------------------------------------------- filing


def _rejected(connection: sqlite3.Connection, queue: str, since: str) -> dict[str, str]:
    """Each subject the queue's standing rulings rejected at or after `since`, and where."""
    found = {}
    for batch in _queue(connection, queue):
        for question in batch["questions"]:
            if question["label"] == REJECT and question["ruled_at"] >= since:
                found[question["subject"]] = (f"rejected by ruling #{question['ruling']} in "
                                              f"sd:{batch['item']['id']} at {question['ruled_at']}")
    return found


def _difference(filed: dict, found: dict) -> str:
    """The first field in which the filed batch and the file differ, as far as the store can tell."""
    header = filed["header"]
    given = {"schema": str(SCHEMA), "source": found["source"], "mode": found["mode"],
             "seal": found["seal"] and found["seal"]["sha256"]}
    for name, value in given.items():
        if header[name] != value:
            return f"{name} is {header[name]!r} in the header and {value!r} in the file"
    questions = {question["subject"]: question for question in found["questions"]}
    for question in filed["questions"]:
        other = questions.get(question["subject"])
        if other is None:
            return f"question {question['subject']} is not in the file"
        for name in ("text", "evidence", "options"):
            if question[name] != other[name]:
                return f"question {question['subject']}: the {name} differ ({question[name]!r} filed)"
    return ("the title, repo, limit or a question that was not filed differs "
            f"(digest {header['digest']} filed)")


def file(connection: sqlite3.Connection, batch: Any, *, who: str, now: str | None = None) -> dict:
    """File `batch` (the parsed batch file): the item, the header and each question, in one transaction.

    The same file again finds its item and writes nothing; another file under
    the same queue and batch is refused, naming the first difference. A
    subject whose question the queue rejected in the last 90 days is dropped,
    then questions past `limit` are; each drop is returned with its reason.
    """
    found = _checked(batch)
    digest = _digest(batch)
    ref = f"review:{found['queue']}:{found['batch']}"
    since = (_moment(now) - timedelta(days=SUPPRESS_DAYS)).isoformat(timespec="seconds")
    with transaction(connection):
        held = writes.item_by_external(connection, REF_SOURCE, ref)
        if held is not None:
            filed = read(connection, held["id"])
            if filed["header"]["digest"] != digest:
                raise ReviewError(f"{ref} is filed as sd:{held['id']} with other content: "
                                  f"{_difference(filed, found)}")
            return {"item": held["id"], "ref": ref, "created": False, "filed": len(filed["questions"]),
                    "dropped": []}
        rejected = _rejected(connection, found["queue"], since)
        kept = [question for question in found["questions"] if question["subject"] not in rejected]
        dropped = [{"subject": question["subject"], "reason": rejected[question["subject"]]}
                   for question in found["questions"] if question["subject"] in rejected]
        dropped += [{"subject": question["subject"], "reason": f"past the limit of {found['limit']}"}
                    for question in kept[found["limit"]:]]
        kept = kept[:found["limit"]]
        if not kept:
            return {"item": None, "ref": ref, "created": False, "filed": 0, "dropped": dropped}
        item = workflow.capture_task(connection, title=found["title"], repo=found["repo"], who=who,
                                     body=f"Review batch {ref}; its questions are the notes.")["item"]["id"]
        writes.set_item_fields(connection, item, source=REF_SOURCE, external_id=ref)
        add_note(connection, item, "comment", _header_body(found, digest, len(kept)), session=who)
        for question in kept:
            add_note(connection, item, "question", _question_body(question), session=who)
    return {"item": item, "ref": ref, "created": True, "filed": len(kept), "dropped": dropped}


# ---------------------------------------------------------------- ruling and undo


def _open_batch(connection: sqlite3.Connection, item: int, expected_revision: str) -> tuple[dict, dict]:
    state = workflow.item_state(connection, item)
    if state["revision"] != expected_revision:
        raise workflow.StaleItem(f"item {item} changed; reload it before applying this change")
    found = _batch(state["item"], state["notes"])
    if state["item"]["status"] == "done" or found["closed"] is not None:
        raise ReviewError(f"sd:{item} is closed; a batch once closed takes no ruling or withdrawal")
    return state, found


def rule(connection: sqlite3.Connection, item: int, note: int, option: str, *,
         expected_revision: str, who: str) -> dict:
    """Label question `note` of batch `item` with `option`: the Decisions ruling, under the item revision."""
    with transaction(connection):
        _, found = _open_batch(connection, item, expected_revision)
        question = next((question for question in found["questions"] if question["note"] == note), None)
        if question is None:
            raise ReviewError(f"note {note} is not a question of sd:{item}")
        if not question["open"]:
            raise ReviewError(f"note {note} is settled: ruled by note #{question['ruling']}"
                              if question["ruling"] else f"note {note} is settled: it expired")
        if option not in question["options"]:
            raise ReviewError(f"note {note} offers no option {option!r}")
        ruled = workflow.add_item_note(connection, item, kind="decision", who=who,
                                       body=f"Ruling on note #{note}: {option}", expected_revision=expected_revision)
        state = workflow.resolve_item_note(connection, note, who=who, expected_revision=ruled["revision"])
        state["ruling"] = ruled["note"]
        return state


def withdraw(connection: sqlite3.Connection, item: int, ruling: int, *,
             expected_revision: str, who: str) -> dict:
    """Undo `ruling`: a withdrawal note and its question reopened, in one transaction."""
    with transaction(connection):
        _, found = _open_batch(connection, item, expected_revision)
        question = next((question for question in found["questions"]
                         if any(held["ruling"] == ruling for held in question["rulings"])), None)
        if question is None:
            raise ReviewError(f"note {ruling} is not a ruling on a question of sd:{item}")
        held = next(held for held in question["rulings"] if held["ruling"] == ruling)
        if held["withdrawal"] is not None:
            raise ReviewError(f"ruling #{ruling} was withdrawn by note #{held['withdrawal']}")
        if question["ruling"] != ruling:
            raise ReviewError(f"ruling #{ruling} is not the standing label on note #{question['note']}")
        pulled = workflow.add_item_note(connection, item, kind="decision", who=who,
                                        body=f"Withdrawn: ruling #{ruling} on note #{question['note']}",
                                        expected_revision=expected_revision)
        reopen_note(connection, question["note"])
        state = workflow.item_state(connection, item)
        state["withdrawal"] = pulled["note"]
        return state


# ---------------------------------------------------------------- export


def _key_rows(key: bytes) -> dict[str, dict]:
    """The key's rows by subject: CSV, its first column naming the subject."""
    try:
        reader = csv.DictReader(io.StringIO(key.decode("utf-8-sig"), newline=""))
        names = reader.fieldnames
        if not names or not all(names) or len(set(names)) != len(names):
            raise ReviewError("the key needs a header row of unique, named columns; the first names the subject")
        column, rows = names[0], {}
        for row in reader:
            if row[column] in rows:
                raise ReviewError(f"the key names subject {row[column]!r} more than once")
            rows[row[column]] = row
    except (UnicodeDecodeError, csv.Error) as failure:
        raise ReviewError(f"the key is not CSV text: {failure}") from None
    return rows


def _pack_commit() -> str:
    """The commit of the pack checkout this library runs from, or `unknown`."""
    root = Path(__file__).resolve().parents[2]
    if not (root / ".git").exists():
        return UNKNOWN
    try:
        done = subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", "HEAD^{commit}"],
                              capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return UNKNOWN
    commit = done.stdout.strip()
    return commit if done.returncode == 0 and re.fullmatch(r"[0-9a-f]{40,64}", commit) else UNKNOWN


def _lines(found: dict, key: bytes | None, rows: dict[str, dict] | None, now: str | None) -> list[dict]:
    header = found["header"]
    questions = found["questions"]
    manifest = {
        "kind": "manifest", "schema": SCHEMA, "batch": found["item"]["id"], "ref": found["ref"],
        "queue": header["queue"], "name": header["batch"], "title": found["item"]["title"],
        "closed": found["closed"], "source": header["source"], "mode": header["mode"],
        "seal": header["seal"], "digest": header["digest"],
        "exported_by": f"sd-ai-command-pack@{_pack_commit()}",
        "exported_at": _moment(now).astimezone(UTC).isoformat(timespec="seconds"),
        "questions": len(questions), "labels": found["labels"], "open": found["open"],
    }
    if rows is not None and key is not None:
        subjects = {question["subject"] for question in questions}
        manifest["key"] = {"sha256": hashlib.sha256(key).hexdigest(), "rows": len(rows),
                           "unmatched": sum(subject not in subjects for subject in rows)}
    lines = [manifest]
    for question in questions:
        line = {"kind": "question", "note": question["note"], "subject": question["subject"],
                "question_sha256": question["sha256"], "evidence": question["evidence"], "options": question["options"],
                "label": question["label"], "position": question["position"], "ruling": question["ruling"],
                "ruled_by": question["ruled_by"], "ruled_at": question["ruled_at"],
                "expired": question["expired"],
                "withdrawn": [{"ruling": held["ruling"], "option": held["option"], "withdrawal": held["withdrawal"],
                               "at": held["withdrawn_at"]}
                              for held in question["rulings"] if held["withdrawal"] is not None],
                "comments": question["comments"], "late": question["late"]}
        if rows is not None:
            line["key"] = rows.get(question["subject"])
        lines.append(line)
    return lines


def export(connection: sqlite3.Connection, item: int, *, who: str, key: bytes | None = None,
           now: str | None = None) -> list[dict]:
    """The batch's labels as JSONL lines: a manifest, then one line per question.

    With `key` (a sealed batch's key file, as bytes) the export refuses a key
    whose SHA-256 is not the header's seal and refuses while a question is
    open; then it closes the batch, in its own committed transaction, and only
    then joins the key's row for each subject into the lines. A rerun on the
    closed batch with the same key exports again.
    """
    rows = None
    if key is not None:
        with transaction(connection):
            found = read(connection, item)
            header = found["header"]
            if header["mode"] != "sealed":
                raise ReviewError(f"sd:{item} is not sealed; export it without a key")
            digest = hashlib.sha256(key).hexdigest()
            if digest != header["seal"]:
                raise ReviewError(f"the key's SHA-256 {digest} is not the seal {header['seal']} in sd:{item}'s "
                                  f"header: it is another batch's key, or this key changed")
            if found["open"]:
                count = found["open"]
                raise ReviewError(f"sd:{item} has {count} question{'s' if count != 1 else ''} open; "
                                  f"a sealed export waits until every question is ruled")
            if found["closed"] is None:
                workflow.change_status(connection, item, "done", who=who,
                                       reason="sealed export: closed before the key is read")
        rows = _key_rows(key)
    return _lines(read(connection, item), key, rows, now)


def write(lines: list[dict], out: Path | str) -> None:
    """Write the export to `out` through `<out>.part` and a rename, owner-only."""
    out = Path(out)
    part = out.with_name(out.name + ".part")
    text = "".join(json.dumps(line, sort_keys=True, ensure_ascii=False) + "\n" for line in lines)
    descriptor = os.open(part, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(part, out)
    except BaseException:
        part.unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------- apply


def _approved_task(connection: sqlite3.Connection, batch: dict, question: dict, who: str) -> int | None:
    """File the task an approval asks for, once: None when its ref is filed already."""
    ref = f"{APPROVED}:{question['note']}"
    with transaction(connection):
        if writes.item_by_external(connection, REF_SOURCE, ref) is not None:
            return None
        body = "\n".join([question["text"], *(f"Evidence: {line}" for line in question["evidence"]),
                          f"Approved by ruling #{question['ruling']} on note #{question['note']} "
                          f"of sd:{batch['item']['id']} ({batch['ref']})."])
        task = workflow.capture_task(connection, title=question["text"].splitlines()[0], body=body,
                                     repo=batch["item"]["repo"], who=who)["item"]["id"]
        writes.set_item_fields(connection, task, source=REF_SOURCE, external_id=ref)
        return task


def _expire(connection: sqlite3.Connection, item: int, note: int, who: str) -> bool:
    """Settle one unruled question as expired; False when a ruling or a close landed first."""
    with transaction(connection):
        found = read(connection, item)
        if found["closed"] is not None or not any(q["note"] == note and q["open"] for q in found["questions"]):
            return False
        add_note(connection, item, "comment", f"On note #{note}: {EXPIRED}", session=who)
        resolve_note(connection, note)
        return True


def _close(connection: sqlite3.Connection, item: int, who: str, reason: str) -> bool:
    """Close the batch when nothing is open and every approval has its task; False otherwise."""
    with transaction(connection):
        found = read(connection, item)
        waiting = any(question["label"] == APPROVE
                      and writes.item_by_external(connection, REF_SOURCE, f"{APPROVED}:{question['note']}") is None
                      for question in found["questions"])
        if found["open"] or waiting or found["closed"] is not None:
            return False
        workflow.change_status(connection, item, "done", who=who, reason=reason)
        return True


def apply(connection: sqlite3.Connection, queue: str, *, who: str, now: str | None = None) -> dict:
    """The nightly queue's deterministic step: approvals to tasks, then close or expire each batch.

    Each approval files one task under `review-approved:<question note>`, in
    its own transaction; a ref already filed is skipped and never updated. A
    batch with no open question closes. A batch older than 7 days resolves
    each open question as expired, one transaction each, then closes. Every
    step finds what an earlier stopped run left and finishes it.
    """
    _name(queue, "queue")
    moment = _moment(now)
    batches = [found for found in _queue(connection, queue) if found["closed"] is None]
    for found in batches:
        for question in found["questions"]:
            if question["options"] != [APPROVE, REJECT]:
                raise ReviewError(f"sd:{found['item']['id']} in queue {queue} asks note #{question['note']} with "
                                  f"other options; apply acts only on questions that offer Approve and Reject")
    result: dict[str, list] = {"tasks": [], "existing": [], "expired": [], "closed": []}
    for found in batches:
        item = found["item"]["id"]
        for question in found["questions"]:
            if question["label"] != APPROVE:
                continue
            task = _approved_task(connection, found, question, who)
            if task is None:
                result["existing"].append(question["note"])
            else:
                result["tasks"].append({"note": question["note"], "item": task, "subject": question["subject"]})
        opened = _moment(found["item"]["created_at"])
        if found["open"] and opened > moment - timedelta(days=EXPIRE_DAYS):
            continue
        for question in found["questions"]:
            if question["open"] and _expire(connection, item, question["note"], who):
                result["expired"].append(question["note"])
        reason = "every question ruled" if not found["open"] else f"unruled after {EXPIRE_DAYS} days"
        if _close(connection, item, who, f"review apply: {reason}"):
            result["closed"].append(item)
    return result
