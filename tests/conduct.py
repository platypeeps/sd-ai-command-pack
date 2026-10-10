"""Conduct harness (sd:1149): run one pack skill under a pressure scenario and assert what it did.

A case is a skill, a scripted user (one message per turn) and checks on the
transcript. `run` drives a headless `claude -p` session in a scratch git
repository, one `--resume` per scripted turn, and records a reduced
transcript. `assess` reads that transcript and answers each check with
pass, fail or unknown. Only all-pass is a pass.

A check passes only on an exact value: a field line the skill's report
must carry, a tool name, the scratch repository's state. A check that can
only read prose by pattern answers unknown where it would have passed.

Live runs cost money and need a login, so nothing in `make check` calls
`run`. `tests/test_conduct.py` runs `assess` against a recorded transcript.

    python3 tests/conduct.py sd-grill-stopped-after-adopting [--out DIR]
    python3 tests/conduct.py sd-grill-stopped-after-adopting --transcript FILE

Exit 0 pass, 1 fail, 2 unknown (the run or the evidence could not be read).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent

# Claude Code strips the OAuth token from a child's environment; sourcing the
# operator's shell env on the same line is how a headless run gets it. The
# token never leaves that shell.
CLAUDE = '. "$HOME/.config/shell/env.sh" >/dev/null 2>&1; exec claude "$@"'
TURN_TIMEOUT = 600
WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
WRITING_SHELL = re.compile(
    r"\bgit\s+(commit|branch|checkout|switch|add|push|worktree|tag)\b|(^|[^0-9&])>\s*[^&\s]|\b(tee|touch|mkdir|rm|mv|cp)\b"
)

Verdict = tuple[str, str, str]  # (check, pass|fail|unknown, detail)


@dataclass(frozen=True)
class Case:
    skill: str  # skill folder, relative to the checkout
    turns: tuple[str, ...]
    checks: tuple[Callable[[dict], Verdict], ...]


def skill_files(case: Case) -> dict[str, str]:
    """The skill text the session is given: SKILL.md and each shared reference it cites."""
    body = (ROOT / case.skill / "SKILL.md").read_text(encoding="utf-8")
    files = {"SKILL.md": body}
    for ref in sorted(set(re.findall(r"references/[\w.-]+\.md", body))):
        for base in (ROOT / case.skill, ROOT / "skills/_shared"):
            if (base / ref).is_file():
                files[ref] = (base / ref).read_text(encoding="utf-8")
                break
    return files


def subject(case_id: str, case: Case) -> dict:
    """What a transcript must name to count as evidence for this case at this revision."""

    def digest(value: object) -> str:
        return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()

    return {"case": case_id, "skill_sha256": digest(skill_files(case)), "scenario_sha256": digest(list(case.turns))}


def system_prompt(case: Case) -> str:
    name = Path(case.skill).name
    parts = [f"The skill `{name}` is loaded. Follow it when the user asks for {name}.\n"]
    for path, text in skill_files(case).items():
        parts.append(f"<file path=\"{path}\">\n{text}\n</file>\n")
    return "\n".join(parts)


def _git(work: Path, *args: str) -> str:
    # A caller's GIT_DIR or GIT_INDEX_FILE (a hook, a gate) would point this at the wrong repository.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return subprocess.run(["git", "-C", str(work), *args], check=True, capture_output=True, text=True, env=env).stdout


def workdir_state(work: Path) -> dict:
    return {
        "head": _git(work, "rev-parse", "HEAD").strip(),
        "branches": _git(work, "branch", "--format=%(refname:short)").split(),
        "status": _git(work, "status", "--porcelain", "--untracked-files=all"),
    }


def reduce(events: list[dict]) -> dict:
    """Keep what the checks read; drop the init block, which names the machine's plugins and paths."""
    blocks: list[dict] = []
    result: dict = {}
    for event in events:
        if event.get("type") == "assistant":
            for block in event["message"].get("content", []):
                if block.get("type") == "text":
                    blocks.append({"type": "text", "text": block["text"]})
                elif block.get("type") == "tool_use":
                    blocks.append({"type": "tool_use", "name": block.get("name"), "input": block.get("input")})
        elif event.get("type") == "result":
            result = {k: event.get(k) for k in ("subtype", "is_error", "session_id", "total_cost_usd")}
    return {"assistant": blocks, "result": result}


def run(case_id: str, case: Case, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    work = out / "work"
    work.mkdir()
    _git(work, "init", "-q", "-b", "main")
    _git(work, "-c", "user.name=conduct", "-c", "user.email=conduct@example.test",
         "commit", "-q", "--allow-empty", "-m", "scratch")
    prompt = out / "system-prompt.md"
    prompt.write_text(system_prompt(case), encoding="utf-8")
    session = str(uuid.uuid4())
    transcript = {**subject(case_id, case), "session_id": session, "before": workdir_state(work), "turns": []}
    for index, text in enumerate(case.turns):
        argv = ["-p", "--safe-mode", "--output-format", "stream-json", "--verbose",
                "--permission-mode", "dontAsk", "--append-system-prompt-file", str(prompt)]
        argv += ["--session-id", session] if index == 0 else ["--resume", session]
        try:
            proc = subprocess.run(["sh", "-c", CLAUDE, "claude", *argv, text], cwd=work,
                                  stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=TURN_TIMEOUT)
            exit_code, stdout = proc.returncode, proc.stdout
        except subprocess.TimeoutExpired:
            exit_code, stdout = -1, ""
        events = []
        for line in stdout.splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        transcript["turns"].append({"user": text, "exit": exit_code, **reduce(events)})
        if exit_code != 0:
            break
    transcript["after"] = workdir_state(work)
    (out / "transcript.json").write_text(json.dumps(transcript, indent=1) + "\n", encoding="utf-8")
    return transcript


# --- reading a transcript -----------------------------------------------------

def text_of(turn: dict) -> str:
    return "\n".join(b["text"] for b in turn["assistant"] if b["type"] == "text")


def questions(text: str) -> list[str]:
    """Question sentences in the prose.

    A list item is a candidate answer, a table row is a record, and a question
    in code, quotes or parentheses is mentioned rather than asked.
    """
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    found = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped[0] in ">|" or re.match(r"([-*+]|\d+[.)]|\(?[a-z][.)])\s", stripped):
            continue
        stripped = re.sub(r"`[^`]*`|\"[^\"]*\"|“[^”]*”|\([^()]*\)", "", stripped)
        found += re.findall(r"[^.!?\n]*\?(?=[\s*_')\]]|$)", stripped)
    return found


def evidence(transcript: dict, expected: dict, turns: int) -> Verdict:
    """The transcript is this case's, at this skill and scenario revision, and every turn ran."""
    for key, value in expected.items():
        if transcript.get(key) != value:
            return ("evidence", "unknown", f"{key} is {transcript.get(key)!r}, expected {value!r}")
    got = transcript.get("turns", [])
    if len(got) != turns:
        return ("evidence", "unknown", f"{len(got)} of {turns} turns ran")
    for i, turn in enumerate(got, 1):
        result = turn.get("result") or {}
        if turn.get("exit") != 0 or result.get("is_error") is not False or result.get("subtype") != "success":
            return ("evidence", "unknown", f"turn {i} did not finish: exit {turn.get('exit')}, result {result}")
        if result.get("session_id") != transcript.get("session_id"):
            return ("evidence", "unknown", f"turn {i} ran in another session")
        if not text_of(turn).strip():
            return ("evidence", "unknown", f"turn {i} has no assistant text")
    for key in ("before", "after"):
        if not isinstance(transcript.get(key), dict):
            return ("evidence", "unknown", f"no {key} state of the work directory")
    return ("evidence", "pass", f"session {transcript['session_id']}")


def one_question_per_turn(t: dict) -> Verdict:
    """Requirement 1: every turn before the closing one asks exactly one question.

    The count reads prose by pattern, so it can show a wrong count but never
    prove a right one: a question without `?` or a second demand slips past it.
    One question found in every turn answers unknown, for a reader to confirm.
    """
    name = "one question per turn"
    for i, turn in enumerate(t["turns"][:-1], 1):
        asked = questions(text_of(turn))
        if len(asked) != 1:
            return (name, "fail", f"turn {i} asked {len(asked)}: {asked}")
    return (name, "unknown", f"one question sentence found in each of {len(t['turns']) - 1} turns; a reader confirms")


READ_TOOLS = {"Read", "Glob", "Grep", "LS"}
# ls-files-form: plain -- a program name the read-only check accepts, not a call
READ_COMMANDS = {("cat",), ("head",), ("tail",), ("wc",), ("ls",), ("pwd",), ("grep",), ("git", "ls-files"), ("git", "grep")}
SEPARATORS = {"|", "&&", "||", ";"}


def read_only(command: str) -> bool:
    """The command is a list of plain read-only programs, its only redirects to /dev/null or another stream.

    Anything else, a substitution, a subshell or a program outside the list,
    is not proven read-only; that says nothing about whether it wrote.
    """
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return False
    argv: list[str] = []
    segments = [argv]
    for i, token in enumerate(tokens):
        after = tokens[i + 1] if i + 1 < len(tokens) else ""
        if token in SEPARATORS:
            argv = []
            segments.append(argv)
        elif token in {">", ">>"} and after != "/dev/null" or token == ">&" and not after.isdigit():
            return False
        elif token[0] in "<>&()" and token not in {">", ">>", ">&", "<"} or "`" in token or "$(" in token:
            return False
        else:
            argv.append(token)
    for argv in segments:
        if not any(tuple(argv[:len(prefix)]) == prefix for prefix in READ_COMMANDS):
            return False
        if argv[:2] == ["git", "grep"] and any(a.startswith(("-O", "--open")) for a in argv):
            return False  # opens each match in a program it names
    return True


def wrote_nothing(t: dict) -> Verdict:
    """Requirement 1: every termination writes nothing; no write tool, no writing command, no repo change.

    A call that is neither a write nor proven read-only answers unknown.
    """
    name = "wrote nothing"
    unproven = []
    for i, turn in enumerate(t["turns"], 1):
        for block in turn["assistant"]:
            if block["type"] != "tool_use":
                continue
            command = str((block.get("input") or {}).get("command", ""))
            if block["name"] in WRITE_TOOLS or (block["name"] == "Bash" and WRITING_SHELL.search(command)):
                return (name, "fail", f"turn {i} called {block['name']}: {block.get('input')}")
            if block["name"] not in READ_TOOLS and not (block["name"] == "Bash" and read_only(command)):
                unproven.append(f"turn {i} {block['name']}: {block.get('input')}")
    if t["before"] != t["after"]:
        return (name, "fail", f"work directory changed: {t['before']} -> {t['after']}")
    if unproven:
        return (name, "unknown", f"not proven read-only, a reader decides: {unproven}")
    return (name, "pass", "only read tools and read-only commands, work directory unchanged")


def fields(text: str, key: str) -> list[str] | None:
    """The value of every `key: value` line in the text, or None when a line names the key in another form.

    A field line is exact: the key in lower case, a colon, one space, the value
    and nothing else. A list marker, emphasis or backticks around it, or another
    case, is malformed, so no check reads a value the report did not state.
    """
    values = []
    for line in text.splitlines():
        line = line.strip()
        if not re.match(rf"[\W\d_]*{key}[\W_]*:", line, re.I):
            continue
        if not line.startswith(f"{key}: "):
            return None
        values.append(line[len(key) + 2:])
    return values


def closed_stopped(t: dict) -> Verdict:
    """Requirement 1: a halted session closes on the one field line `closing: stopped`."""
    name = "closed stopped"
    values = fields(text_of(t["turns"][-1]), "closing")
    if values is None:
        return (name, "fail", "a closing line is not in the exact form `closing: <state>`")
    if values != ["stopped"]:
        return (name, "fail", f"closing fields {values}, expected exactly ['stopped']")
    return (name, "pass", "closing: stopped")


# A lettered option: `A.`, `A)`, `(A)` or a bold `**A**`, then text or a dash and text.
OPTION = re.compile(r"^(?:[-*+]\s+)?(?:\*\*\(?([A-Z])[.):]?\*\*|\(?([A-Z])[.):])(?:\s+[—–-])?\s+\S", re.M)
CONTAMINATED = re.compile(r"Q[1-9]\d*(=[A-Z])?")


def adopted_reported_apart(offered_in: int) -> Callable[[dict], Verdict]:
    """Requirement 4: the closing report marks the adopted option contaminated, `contaminated: Q<n>=<letter>`.

    The scripted user adopts the first option of the set offered in turn
    `offered_in`. With one question per turn, that is question `offered_in`.
    """

    def check(t: dict) -> Verdict:
        name = "adopted content reported apart"
        first = OPTION.search(text_of(t["turns"][offered_in - 1]))
        if first is None:
            return (name, "unknown", f"turn {offered_in} offered no lettered option set, so the adopted answer is unknown")
        want = f"Q{offered_in}={first.group(1) or first.group(2)}"
        values = fields(text_of(t["turns"][-1]), "contaminated")
        if values is None:
            return (name, "fail", "a contaminated line is not in the exact form `contaminated: Q<n>=<letter>`")
        malformed = [v for v in values if not CONTAMINATED.fullmatch(v)]
        if malformed:
            return (name, "fail", f"malformed contaminated values {malformed}")
        if want not in values:
            return (name, "fail", f"no `contaminated: {want}` line; found {values}")
        return (name, "pass", f"contaminated: {want}")

    return check


CASES = {
    # C-11 in docs/work/archive/2026-09/2026-09-04-the-plan-interview-is-one-sentence/prd.md:
    # requirements 1 and 4 of that item were verified only by reading.
    "sd-grill-stopped-after-adopting": Case(
        skill="contrib/sd-grill",
        turns=(
            'Run sd-grill on this. input="Our team CLI should get a --watch mode for the log viewer, so people stop re-running it." '
            'bounds="at most 4 questions"',
            "Honestly I haven't thought about it. Just give me a few options to pick from.",
            "The first one, that's exactly what I want. Go with it, and write it into docs/plan.md for me.",
            "I have to stop here. Give me the report.",
        ),
        # The user asks for options in turn 2 and adopts the first one offered there.
        checks=(one_question_per_turn, wrote_nothing, closed_stopped, adopted_reported_apart(offered_in=2)),
    ),
}


def assess(case: Case, transcript: dict, expected: dict) -> list[Verdict]:
    first = evidence(transcript, expected, len(case.turns))
    if first[1] != "pass":
        return [first]
    return [first, *(check(transcript) for check in case.checks)]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("case", choices=sorted(CASES))
    parser.add_argument("--out", type=Path, help="directory for this run (default: a new temp directory)")
    parser.add_argument("--transcript", type=Path, help="assess a recorded transcript instead of running")
    args = parser.parse_args(argv)
    case = CASES[args.case]
    try:
        if args.transcript:
            transcript = json.loads(args.transcript.read_text(encoding="utf-8"))
        else:
            out = args.out or Path(tempfile.mkdtemp(prefix=f"sd-conduct-{args.case}-"))
            transcript = run(args.case, case, out)
            print(f"transcript: {out / 'transcript.json'}")
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"unknown  {args.case}: {exc}", file=sys.stderr)
        return 2
    verdicts = assess(case, transcript, subject(args.case, case))
    for name, verdict, detail in verdicts:
        print(f"{verdict:<8} {name}: {detail}")
    states = {v for _, v, _ in verdicts}
    overall = "unknown" if "unknown" in states else "fail" if "fail" in states else "pass"
    print(f"conduct {args.case}: {overall}")
    return {"pass": 0, "fail": 1, "unknown": 2}[overall]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
