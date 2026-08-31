# Argument vocabulary

The canonical `key=value` argument vocabulary shared across skills. Identical
concepts use identical names and value sets, so a name learned on one skill
transfers to the next instead of hard-stopping. Author new argument bullets
against this reference; reuse a canonical name and its value set before
inventing a new one.

Two argument names carry an enforced value ladder; the rest reserve a name to a
concept without constraining its per-skill values. Value ladders are checked as
**set membership**, not order — a skill lists its values default-first and may
expose any subset of the ladder.

## Enforced axes (name + value ladder)

### Verbosity — `depth=brief|standard|deep`

How much the skill produces. `brief` is a tight, skimmable result; `standard`
is the default working depth; `deep` is exhaustive. Declare a subset
default-first (for example `depth=standard|brief|deep`). A skill that needs an
exact length instead of a tier takes a separate `target_words=` argument rather
than a numeric `depth=`.

### Redaction — `sensitivity=minimal|restricted|standard`

How much source detail the output may expose. `minimal` strips identifying or
sensitive detail hardest; `restricted` withholds named sensitive material;
`standard` applies ordinary handling. This is content redaction, distinct from
`privacy=` (who may receive the result).

## Reserved names (name → concept, values per-skill)

These names are bound to one concept each. Reuse the name for that concept; do
not repurpose it for another, and do not coin a synonym.

- `input=` — the primary artifact or subject the skill acts on (the thing being
  transformed), as opposed to reference material consulted.
- `sources=` — reference material to consult. A distinct concept from `input=`;
  already consistent across skills.
- `min_sources=` — a minimum source count (a number), distinct from the
  `sources=` material list.
- `coverage=` — editorial coverage of a pass (for example `full|focused`),
  distinct from verbosity `depth=`.
- `target_words=` — an exact output length in words, when a tier is too coarse.
- `privacy=` — distribution or audience ceiling (who may receive the result),
  distinct from `sensitivity=` content redaction.
- `evidence=` — authorized supporting material for a claim, distinct from
  general reference `sources=`.
- `format=` — output shape or structure (for example `ledger|memo`). Structural
  shapes stay `format=`; a pure density choice belongs on `depth=`.
- `mode=` — a skill's operating mode.
- `scope=` — the extent of work the skill covers.
- `audience=` — who the output is written for.

Skill-owned argument names outside this list keep their own per-skill meaning;
this reference governs the shared vocabulary, not every private argument.
