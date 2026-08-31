---
name: sd-prose-lint
description: Use when prose written on the user's behalf — skill bodies, docs, README text, commit or PR text, release notes, outbound drafts — needs a prose lint, style lint, or AI-tell check before it is committed or sent; runs the deterministic Vale gate where it exists and assigns every finding a disposition, degrading gracefully where Vale is absent.
---

# SE Prose Lint

Check prose deterministically before it is committed or sent. Where the Vale
gate exists, run it and work every finding to a disposition; where it does
not, say so in one plain sentence and continue with the judgment pass. This
skill reports and dispositions — it never rewrites. Rewriting is
`sd-humanizer`.

## When to use

Use before committing or posting prose produced on the user's behalf:
skill and agent bodies, checked-in docs and README sections, commit
messages, PR and issue text, release notes, and outbound drafts. Also use
when the user asks for a prose lint, a style check, or an AI-tell sweep by
name.

Do not use for:

- rewriting flagged prose into something human — that is `sd-humanizer`;
- a full editorial review of a technical draft — that is
  `sd-technical-editor`;
- linting code, schemas, or configuration — the gate scopes to prose.

## Arguments

None. Targets arrive as free text; without an explicit target, lint the
changed prose in the working tree rather than the whole repository.

This skill takes no `key=value` arguments.
Unknown argument names are an error — stop and report them before starting.

## Workflow

1. Probe the gate before judging anything. Look for a `make prose-lint`
   target, and treat the target as authoritative over a local
   `vale --version`: the target may reach a pinned, vendored, or
   containerized Vale that a bare binary probe never sees, so where a
   target exists, run it and let its own failure classify the state. Four
   states:
   - **full gate** — the target runs: take its verdict for repository
     prose. It lints the corpus the repository configured, not the subset
     under review, so read its findings against the target files and say
     which alerts fall outside them. A draft that is not yet a file is
     invisible to it: lint that through Vale on stdin and report both;
   - **binary only** — Vale and a config exist without the Make target: run
     Vale directly on the target files, or on stdin for drafts that are not
     yet files;
   - **target only** — the repository gates on prose but this environment
     has no Vale: name that gap explicitly, since a skipped gate is not a
     clean one, and say that installing Vale is what closes it. Then
     continue with the judgment pass;
   - **absent** — no Vale in this repository.
2. Where the deterministic gate cannot run, degrade gracefully: report the
   gap in one plain sentence, naming which of the two reasons applies —
   no gate in this repository, or a gate this environment cannot run —
   and move on. Never fail, block, or stall the session over a missing
   gate; the hard requirement lives in the gating repository's own CI, not
   in this skill.
3. Run the deterministic pass over the scoped targets and collect findings
   by file, line, rule, and severity. Prefer changed files and changed
   sections; a whole-repository sweep needs an explicit request.
4. Give every error-level finding exactly one disposition — an error with
   no disposition is unfinished work:
   - **fix** — the rule is right and the correction is mechanical, fully
     determined by the rule itself: delete the hedge, cut the AI-tell.
     Anything needing the sentence re-composed is rewrite-shaped and goes
     to `sd-humanizer` under step 7, which is what "never rewrites" above
     means;
   - **suppress** — the rule is right in general and wrong for this span;
     suppress inline with a written justification recorded at the
     suppression site, never a bare suppression;
   - **promote** — the rule is wrong everywhere in this repository; propose
     the config or style change to whoever owns the gate rather than
     silently editing shared configuration.
   Judge warning- and suggestion-level findings in context; do not force
   them through the disposition protocol.
5. Respect the RFC-2119 carve-out: `MUST`, `SHOULD`, `MAY` and their
   negations are intentional normative vocabulary. Never reword them and
   never let a capitalization rule flag them — that is a suppression with
   justification, not a fix.
6. Run the judgment pass regardless of gate state: read the scoped prose
   for tells no rule covers — hedging stacks, filler, formulaic
   transitions, promotional puffery — and judge by clusters of tells, not
   isolated hits.
7. Hand rewrite-shaped findings to `sd-humanizer` with the finding list
   attached, so the rewrite pass does not re-derive the deterministic
   results.

## Safety rules

- Never fail a session because a repository lacks Vale. Absence is a
  reported gap plus the judgment pass, nothing more.
- Report and disposition; never rewrite. The rewrite belongs to
  `sd-humanizer`, and posting or sending on the user's behalf is never
  authorized from here.
- Never suppress a finding without a justification recorded at the
  suppression site.
- Do not install Vale, change gate configuration, or edit shared style
  rules without an explicit request; promotion findings are proposals.
- Skip code blocks, generated content, quoted verbatim text, and
  intentional examples of bad prose unless the user asks to lint them.
- This skill gates prose, not changes: review verdict authority stays with
  the sd-review lane.

## Final report

- **Gate state** — full gate, binary only, target only, or absent, with
  the gap stated plainly when the deterministic pass could not run;
- **Deterministic findings** — per file: rule, severity, and the
  disposition each error received (fix, suppress, promote);
- **Suppressions** — every suppression with its recorded justification;
- **Judgment-pass findings** — tells found beyond the rules, with
  locations;
- **Handoffs** — findings passed to `sd-humanizer` and proposed config
  promotions awaiting the gate owner; and
- **Residue** — anything left unlinted and why.
