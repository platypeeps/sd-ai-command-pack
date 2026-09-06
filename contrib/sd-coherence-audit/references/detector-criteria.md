# Detector criteria

Four classes. Each states what **qualifies**, the **evidence required**, and at
least one **near-miss** that must not be reported. A finding names the criterion
it satisfies; a passage that matches no listed criterion is not a finding.

The near-miss rules are load-bearing. This skill's primary failure mode is
confident pairing of passages that are not actually opposed, so a candidate that
matches a near-miss is dropped even when the pairing looks compelling.

## Contradiction

Two passages that cannot both be followed.

**Qualifies**

- `direct-negation` — one passage requires what another forbids, on the same
  subject and the same trigger.
- `incompatible-threshold` — two passages set values, limits, counts, or
  deadlines for the same measured thing that **cannot both hold**. Merely
  different numbers do not qualify on their own: a floor below its ceiling, or a
  default and an override, are compatible. Compare the values, not their roles —
  a floor above its ceiling admits nothing and does qualify.
- `conflicting-order` — two passages demand different sequences for the same
  steps, or each claims authority over the other.
- `exclusive-trigger` — the same observable condition routes to two mutually
  exclusive actions.

**Evidence required**: at least two `path:line` locations and the verbatim text
of every side. A contradiction reported from one location is not reportable. As
everywhere else, `sensitivity=` may redact or withhold the text of a side you
read; the locations stay, and the finding is marked unquotable rather than
dropped.

**Near-misses — do not report**

- Two passages with different numbers for the same thing that are compatible:
  a minimum beside a maximum, a default beside an explicit override, or a
  guideline beside a hard limit.
- Two rules whose scopes are stated and do not overlap. "Force-push is forbidden
  on the default branch" and "force-push the rebased branch with a pinned lease"
  govern different branches; they only look opposed.
- A general rule and a passage that marks itself an explicit exception to it.
- Two passages that conflict but where a declared precedence settles which wins.
  That is `resolved-by-precedence`, an observation, not a defect.
- The same requirement stated at different strengths where the stricter one is
  clearly the ceiling and neither forbids the other.

## Vagueness

A directive with nothing a reader can act on or check.

**Qualifies**

- `no-threshold` — a quantitative demand with no measurable value ("keep it
  fast", "don't use too much memory").
- `no-actor` — an obligation with no one who owes it ("this should be reviewed").
- `unresolvable-referent` — "this", "the above", "the other file" with no
  antecedent a reader can resolve from the passage.
- `undefined-gate` — an undefined term used as a pass/fail condition ("ship when
  it is production-ready").
- `missing-failure-branch` — a required check whose failure leaves a reader with
  a real choice the corpus never makes: block, warn, retry, or proceed. A check
  whose failure stops the step it gates does not qualify.
- `open-list-terminator` — "etc.", "and so on", "among others" carrying load in a
  list a reader must act from exhaustively.

**Evidence required**: one `path:line`, the verbatim directive, and the specific
decision a reader cannot make from it.

**Near-misses — do not report**

- Deliberate latitude the passage itself marks as a judgment call ("use your
  judgment here; there is no fixed threshold"). Named discretion is a decision.
- A term left undefined locally but defined elsewhere in the corpus, when the
  passage points at that definition.
- Prose that describes or motivates rather than directs. Only directives and
  assertions are in scope.

## Bandaid

Guidance shaped as a patch rather than a rule.

**Qualifies**

- `no-root-cause` — a workaround with no recorded cause and no pointer to one.
- `expired-interim` — "for now", "temporarily", "until we fix X" where the stated
  date, release, or condition has passed, or where none was ever stated.
- `stacked-exception` — an exception to an exception, so the governing rule can
  only be derived by chaining three or more passages.
- `retry-as-fix` — retry, ignore, restart, or re-run standing in for a fix,
  with no condition under which it stops being the answer.
- `todo-as-policy` — a TODO, FIXME, or open question sitting where a rule belongs
  and being followed as one.

**Evidence required**: one `path:line`, the verbatim text, and which marker of
patch-shape it carries — except `stacked-exception`, which is a property of a
chain and so requires every passage in it, each with its own `path:line` and
verbatim text, in the order a reader must chain them.

**Near-misses — do not report**

- A documented, owned, dated interim measure with its root cause recorded and an
  exit condition. That is a decision, not a bandaid.
- A workaround for a named external defect that links the upstream issue.
- A rule that reads defensively but has a stated rationale.

## Redundancy

The same rule in more than one place. Copies that agree today still qualify —
what makes redundancy a defect is that editing one leaves the others behind, not
that they have already diverged.

**Qualifies**

- `verbatim-duplicate` — the same directive stated in two or more locations.
- `paraphrase-duplicate` — the same requirement in different words, where editing
  one copy would leave the other wrong.
- `overlapping-authority` — two passages both claiming to be the rule for the
  same subject, with no canonical relationship declared.
- `restating-file` — a file whose content restates another file rather than
  pointing at it.

**Evidence required**: at least two `path:line` locations and the verbatim text
of each copy. Redundancy reported from one location is not reportable.

**Near-misses — do not report**

- An intentional summary, index, or table of contents that points at its
  canonical source.
- A worked example that instantiates a rule stated elsewhere.
- Two passages that share vocabulary but govern different subjects.
- A deliberate restatement the corpus marks as such ("repeated here for
  emphasis"), while the copies still agree. Copies that have drifted apart are
  reported: as **redundancy** at raised severity when the versions can still
  both be followed, and as a **contradiction** only when they cannot. Drift is
  not by itself a contradiction — a copy that gained a clarification its
  original lacks has drifted without conflicting.
