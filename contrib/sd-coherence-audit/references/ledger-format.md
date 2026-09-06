# Ledger format

The report shape: the audit contract, the coverage block, the findings ledger,
the observations, then the limits. Coverage precedes the ledger because a ledger
read without knowing what was skipped is read as complete. There is no separate
resolutions section — `resolution` is a field of each finding, so a proposal
travels with the finding it belongs to instead of being restated apart from it.

## Coverage block

State three sets explicitly. An empty set is written `none`, never omitted.

| Set | What it records |
|---|---|
| read in full | every file read end to end |
| sampled | file, which portion was read, and why the rest was not |
| skipped | file and the reason: size, binary, unreadable, excluded |

A corpus that could not be audited in full is reported as **partially audited**
with the unaudited remainder named. Coverage is never inferred from the number
of findings.

## Finding schema

| Field | Rule |
|---|---|
| `id` | `C-1`, `M-2`, `V-3`, `B-2`, `R-4` — class letter and a number, stable within one report |
| `class` | contradiction, missing-precedence, vagueness, bandaid, or redundancy. `missing-precedence` is an outcome of the contradiction detector, not a separate `classes=` value |
| `severity` | blocking, high, medium, or low |
| `locations` | every `path:line`; contradiction, missing-precedence, and redundancy require at least two |
| `quotes` | the verbatim text at each location, never paraphrased. A secret-shaped value inside a quote is redacted and said to be; `sensitivity=` may withhold a quote entirely, and the finding is then marked unquotable. Neither is a paraphrase, and neither drops the finding |
| `precedence` | on a conflict finding only: the ordering that was checked and what it settled, or `undeclared`, or `irrelevant` with why no ordering could settle it |
| `criterion` | the named criterion from `references/detector-criteria.md` that it satisfies |
| `why` | what a reader acting on this passage would get wrong |
| `resolution` | the proposed fix, stated as a proposal and never applied |
| `confidence` | high or medium; a low-confidence finding is dropped, not reported |

## Severity

Severity is scored by consequence, not by how many locations a finding touches.
Three duplicated passages that currently agree are `low`; one contradiction on a
destructive action is `blocking`.

- **blocking** — a reader following the corpus would take a wrong, hard-to-undo
  action. Opposite actions on one trigger are not blocking by themselves;
  they are blocking when acting on the wrong one is costly to reverse.
- **high** — load-bearing guidance that a competent reader will plausibly
  misread.
- **medium** — a real defect on a low-blast-radius or rarely-reached path.
- **low** — drift risk with no present-tense wrong outcome, such as a duplicate
  whose copies still agree.

## Worked examples

One per class. Each shows the evidence the schema requires.

### Contradiction

No ordering could settle it, because both passages sit at one authority. Here
they share a single block of one file, so there is no ranking left to invoke —
two separately owned blocks of one file would rank against each other, and this
would be a missing precedence instead.

```
C-1  contradiction  blocking  confidence: high
  criterion: direct-negation
  docs/release.md:41
    "Tag the release before the gate runs, so the gate sees the tag."
  docs/release.md:88
    "Never tag until the gate is green."
  precedence: irrelevant — one file, one authority; no ordering can retire
       either sentence
  why: a release cannot be both tagged before the gate and untagged until it is
       green, so whoever cuts one takes an action the same file forbids, and
       retagging a published release is costly to undo.
  resolution: delete or rewrite one of the two sentences. Nothing outside the
       file can choose between them.
```

### Missing precedence

An ordering could settle it, but none that is declared reaches both sides. The
absent ordering is the finding; each passage may be correct under its own
authority.

```
M-1  missing-precedence  high  confidence: high
  criterion: conflicting-order
  docs/release.md:12
    "Release notes are written after the tag, from the tag's commit range."
  CONTRIBUTING.md:31
    "Write the release notes before tagging, and tag the commit that adds them."
  precedence: undeclared
  why: either sequence is workable on its own, so this is settled by saying
       which file governs release procedure — and the corpus never does.
  resolution: declare which file governs release procedure, and have the other
       point at it.
```

### Vagueness

```
V-2  vagueness  high  confidence: high
  criterion: undefined-gate
  docs/deploy.md:17
    "Deploy once the change is production-ready."
  why: "production-ready" is the pass condition and is defined nowhere in the
       corpus, so a reader cannot tell whether the gate is met.
  resolution: replace with the checks that must pass, or point at their
       definition.
```

### Bandaid

```
B-1  bandaid  medium  confidence: medium
  criterion: expired-interim
  scripts/README.md:63
    "For now, re-run the importer twice; the first pass drops rows."
  why: a defect is being worked around with no recorded cause and no exit
       condition, so the workaround is read as the permanent procedure.
  resolution: record the root cause and the condition under which the second
       pass stops being required.
```

### Redundancy

```
R-3  redundancy  low  confidence: high
  criterion: paraphrase-duplicate
  CONTRIBUTING.md:12
    "Every pull request needs one approving review."
  docs/process.md:47
    "A pull request merges after one reviewer approves."
  why: the same rule in two places; editing one copy converts this into a
       contradiction.
  resolution: keep the rule in one file and have the other cite it.
```

## Memo format

`format=memo` reorders the same report for a reader who will not read a table.
It drops no field and no finding: the audit contract and coverage become a short
opening paragraph, each finding becomes a paragraph naming its id, class,
severity, locations, and criterion, with the quotes kept verbatim and set off
from the prose, and the observations and limits close it. A memo that omits a
quote, a location, or the coverage sets is a defect, not a shorter format.

## Observations

Three things are reported outside the ledger, because none of them is a corpus
defect:

- `resolved-by-precedence` — a conflict that a declared ordering settles. Record
  both sides, the ordering, and which one wins.
- the count of candidates dropped below `confidence: medium`, reported in every
  run. A silent drop is indistinguishable from having found nothing, so the
  count is not optional; the candidates themselves are listed only at
  `depth=deep`.
- near-misses, listed only at `depth=deep` — candidates dropped by a near-miss
  rule, with the rule that dropped them. These show the audit's reach without
  inflating the ledger.
