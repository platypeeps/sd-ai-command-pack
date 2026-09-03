# Dispatching subagents, and what they cannot write

Two rules about the harness rather than about any one subject. They were written
inside a research-repo standard, where they applied to six repositories; they are
properties of Claude Code, so they hold wherever a skill fans work out.

## Fan-out, and the filenames a subagent cannot write

Reading fans out; writing does not. Investigation, source extraction, tracker
checks and web sweeps parallelise freely across read-only subagents. Anything
that mutates a checkout stays in one lane, because two agents editing one
checkout is how a document loses a paragraph nobody notices.

A subagent's findings come back **as text**, in its final response. That is the
default, and for most fan-out it is the whole story. Where a report is too long
to hand back that way, it goes in a scratch location the orchestrator names, and
the main thread lifts what it needs into a real document.

**One filename rule, and it is not a matter of taste.** Claude Code's `Write`
tool refuses, inside a subagent, any file whose basename matches:

```
/^(REPORT|SUMMARY|FINDINGS|ANALYSIS).*\.md$/i
```

Verified in the 2.1.259 binary: the check reads `agentId && <regex>` and returns
"Subagents should return findings as text, not write report files." It is
compiled in, so no permission entry, settings file or hook disables it, and it
fires only under a subagent — the same path from the main thread succeeds, which
is what makes it confusing when it hits.

So when a subagent must write:

- Name the file for its subject, with the qualifier last: `spec-claims.md`,
  `jira-state.md`, `rmcp-notes.md`. Never `report-spec.md` or `summary-jira.md`.
- `.txt` also passes, and a heredoc through Bash bypasses the tool entirely.
  Both are escape hatches, not the convention — a well-named file needs neither.

**Watch for collisions with a legitimate prefix.** Four blocked words are also
words a naming scheme may already use for a real document type. In the research
repos, `30-brief/SUMMARY-*` is a documented prefix and
`SUMMARY-external-validation.md` is a real file that no subagent could have
created. Documents there are written by the main thread, so the prefix stays —
but a fan-out plan that ends "and have the agent write the SUMMARY-" fails at the
last step, every time.

## Use the file tools, not the shell

Read a document with **Read**, change it with **Edit** or **Write**, search it
with **Grep** or **Glob**. Not `cat`, not `sed -n`, not a `python3` heredoc, not
a `>` redirect. This holds even where a session is running a general directive
that prefers the shell: that directive is about command work, and editing prose
documents is not command work.

Two reasons, and the second is the one that matters.

**Approval churn.** The file tools run under the file permissions already
granted. Their shell equivalents need a matching `Bash(...)` allow rule per verb,
and a compound command is split on `;`, `&&` and `|` with every segment checked
on its own. One unlisted `echo` turns a routine read into an approval prompt. A
session that does its file work through pipelines spends its day asking
permission to look at files.

**Silent corruption.** `Edit` requires that the file was read first, and refuses
when the old string is not unique. A `sed -i` or a rewritten heredoc has neither
guard: it will happily match twice, replace the wrong paragraph, or drop the tail
of a document, and report success. An unquoted heredoc adds its own failure —
the shell expands backticks and `$` inside the text being written, so a sentence
quoting a command silently loses it. For prose that carries citations and a
Status section, a partial write is worse than a failed one, because nothing
announces it. Prefer the tool that fails loudly.

The shell keeps the work it is actually good at: running the repository's own
entrypoints, `git`, counting across many files where a pipeline genuinely is the
right instrument, and anything with no tool equivalent. Writing a scratch file
from a subagent is the standing exception — a heredoc is the documented way
around the `Write` restriction above, and it should be quoted (`<<'EOF'`) so the
shell leaves the content alone.
