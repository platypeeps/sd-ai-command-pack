---
name: sd-docs-bustest
description: Use when documentation must survive a cold read — checking that a newcomer with no prior context can execute a README, runbook, setup guide, or handoff doc exactly as written, when docs are created or changed, or when asked to bus-test docs.
---

# SE Docs Bus Test

Check documentation against the bus test: if the author disappeared
tomorrow, could a newcomer with no context pick up the document and
execute it cold? The test is not about style. It asks whether the
information exists, whether the steps actually run, and whether the
reader ever has to guess.

Read the document as its least-informed intended reader — a contributor
who knows the domain but not this project, or a fresh session with zero
prior context — and execute it mentally command by command, flagging
every point where cold execution would stall.

## When to use

Use when documentation is created or materially changed, when a document
is about to become someone's only guide (onboarding, runbook, handoff,
release procedure), or when the user asks whether docs are good enough
for a newcomer.

Do not use for prose style or tone — that is `sd-prose-lint`. Do not use for pre-merge scope and coherence probes over
the surrounding change — that is `sd-gate-probes`, which routes
checked-in docs changes here. The review verdict on a docs-touching pull
request stays with the sd-review lane.

## Arguments

None. The documents to test are those changed in the current diff or
named with the invocation; confirm the set before starting.

This skill takes no `key=value` arguments.
Unknown argument names are an error — stop and report them before starting.

## Workflow

1. Fix the reader: name the least-informed audience the document claims
   to serve, and hold every probe to that reader's knowledge — nothing
   the document does not state or link may be assumed.
2. Walk the document top to bottom as that reader and score five probes,
   each with cited evidence:
   1. *Commands run as written* — every command is copy-pastable and
      succeeds verbatim in the stated environment. Say for each whether
      you ran it or only read it, and score a command you could not run —
      because it needs a credential, a placeholder value, or an
      environment you do not have — as UNVERIFIED with that reason, never
      as PASS. UNVERIFIED is not by itself a defect: a placeholder the
      document marks as one and tells the reader how to fill is correct
      documentation that this reader has no way to execute. An
      unannounced placeholder, one with no stated source for its value,
      or a command that fails for any other reason is a FAIL. A reasoned
      guess that a command works is exactly the assumption this probe
      exists to catch: correct paths, real flags, no pseudo-commands, no
      "run the tests" hand-waving.
   2. *No undefined prerequisites* — every tool, account, credential,
      dependency, and prior artifact a step needs is stated (or linked)
      before the step that needs it.
   3. *No unstated environment assumptions* — operating system, shell,
      working directory, versions, network access, and required
      environment variables are explicit wherever they change the
      outcome.
   4. *Placeholders visibly marked* — every value the reader must
      substitute is unmistakably a placeholder (`<project-id>`,
      `YOUR_TOKEN`), never an example value a cold reader would paste
      literally; the text says what to substitute and where it comes
      from.
   5. *Ordering actually executable* — steps work in the order written:
      nothing is used before it is created, no step silently depends on
      a later one, and forward references are explicit.
3. Grade each finding by how hard it stops the cold reader:
   - **P1** — cold execution fails: a command errors as written, a
     required step or prerequisite is missing, or the document
     contradicts the current state of the code.
   - **P2** — cold execution stalls: the information exists but the
     reader must hunt for it, infer it, or already know it.
   - **P3** — polish: clearer examples, cross-links, tightened wording.
4. After any docs edits made in the same session, re-read each edited
   document end to end. Section-level edits that look fine in isolation
   can leave a patchwork: repeated context, contradictory statements,
   broken flow. The document must read as one coherent narrative.
5. Deliver the report. When the changed docs contain user-facing prose,
   suggest `sd-prose-lint` as a follow-up, marked
   `not run`.

## Safety rules

- Bus-testing is read-only: report findings, do not rewrite the
  documents unless the user separately asks for fixes.
- Judge against the reader defined in step 1. Never let your own context
  about the project stand in for what the document actually says — if
  you needed knowledge the document does not provide, that is a finding.
- Verify claims against the current code and configuration before filing
  a P1; a suspected contradiction that was not checked is reported as
  unverified, not as a P1.
- Never fabricate an execution result. If a command cannot be checked in
  this environment, say what was checked (syntax, paths, flags) and what
  was not.
- Findings inform the change; they are not a review verdict. Approval of
  a docs-touching pull request stays with the sd-review lane.
- Route only to surfaces this pack ships: sibling `sd-*` skills by their
  final names and the sd-review lane.

## Final report

- **Documents and reader** — the documents tested and the cold reader
  they were tested against;
- **Probe results** — the five probes, each PASS, FAIL, or UNVERIFIED
  with cited evidence (file and section or line). UNVERIFIED names what
  blocked the check; it never stands in for a pass;
- **Findings** — P1, then P2, then P3, one line each: file, location,
  what stops or stalls the cold reader;
- **Bus-test verdict** — survives cold execution, survives with
  friction, or fails cold execution, in one sentence;
- **Coherence check** — for edited documents, confirmation of the
  end-to-end re-read or the gaps it found;
- **Suggested next steps** — follow-up routes such as `sd-prose-lint`,
  each marked `not run`.
