# Optional prose scores

A prose impression does not survive a revision. "Reads hedgy" cannot be
compared against yesterday's draft, thresholded, or handed to another
reviewer. This reference defines an optional scoring pass that turns the
judgment half of a prose review into numbers a caller can keep.

The pass is optional and off by default. A reader without the scorer reads a
complete skill: everything the owning skill does without this pass, it still
does, unchanged.

## What runs the pass

The scorer is `jev`, TypeSafe's System One model, reached through a command of
that name on `PATH`. It answers a narrow question about supplied state with a
type and a probability. It writes no prose and explains nothing.

Run the pass only when both conditions hold:

1. The user asks for prose scores, by name, in this session. Nothing infers
   the request, and no earlier session's request carries over.
2. `jev enabled` exits `0`. That command calls nothing and costs nothing, so
   it is safe to run first every time.

If `jev` is absent from `PATH`, or `jev enabled` exits `3`, say so in one
plain sentence and finish the review without scores. A missing scorer is a
reported gap, never a failure and never a stall.

## What leaves the machine, and what must not

Every scored call posts the draft text to a third party. Nothing else is sent:
no file path, no repository name, no branch, no surrounding conversation, no
credential, and no environment value.

**Do not score a confidential draft.** An unpublished security finding, an
embargoed announcement, a draft naming a customer, and anything carrying a
secret stay unscored. Lint them with the deterministic pass and the reading
pass alone, and say in the report that scoring was withheld.

The user's request to score is a request to score the text in front of you. It
is not permission to send anything that text does not contain.

## Keep the countable in code

Ask the model only for what code cannot count. A question a `grep` answers
spends tokens to learn what a pipe already knows, and it answers less reliably.

Code counts, and the scoring pass never asks about:

- words per sentence, with `wc -w` on a split, and the distribution across the
  draft;
- occurrences of an em dash, an en dash, a curly quote, or an emoji;
- runs of bold spans, heading capitalization, and list shape;
- every watched word and phrase the owning skill lists, as a literal match;
- hyphenated pairs, and whether each sits before or after its noun.

The model judges, and only the model can:

- whether a long sentence carries one idea or several joined ones;
- whether a hedge names a real limit or pads a claim the writer could state;
- whether a passive hides an actor the reader needs, or drops one nobody wants;
- whether a watched word is being used or is being quoted and discussed;
- whether a promotional adjective is supported anywhere in the draft.

The division is the point. A count tells you a word is present. A score tells
you whether its presence is a defect here.

## The dimensions

Each dimension is one question about the whole draft. Each is scored on the
ordered levels below, numbered from `0`. Levels describe situations rather
than degrees, because "moderately hedged" is not something two readers agree
on and "qualifiers stack inside single sentences" is.

Keep the dimensions independent. A level that mixes two of them produces a
number that means neither.

| Dimension | Question |
| --- | --- |
| `hedging` | How much of the draft is padded with qualifiers that narrow nothing? |
| `filler` | How many words could be cut without losing a claim? |
| `passive_actor` | Does the passive voice hide an actor the reader needs? |
| `signposting` | Does the draft announce what it will do instead of doing it? |
| `puffery` | Does the draft rate its subject's importance instead of describing it? |
| `overload` | Does each sentence carry a single idea? |

## The request

The dimensions are independent questions over one state, so they belong in a
single `ask` request. Questions in one request run in parallel and cannot read
each other's answers, which is what makes them cheap. A question that needed
an earlier answer would need a second call, and none of these does.

Write the draft to a file, write the block below to a file, then run:

```sh
jev ask --questions questions.json --state draft.txt
```

Both `--questions` and `--state` read stdin when given `-`, so at most one of
them can be `-` in a single call. Keep the draft in a file and pipe the
questions, or keep both in files as above.

`ask` takes a shared `--state` and nothing per question. It has no `--id`, no
`--json` and no `--gate`, and the question ids are the keys of the object
below. The model never sees them; only your code does.

This pass branches on `jev enabled` rather than passing `--fallback`. A
fallback prints an answer you supplied, and a supplied score is a number
nobody measured. An unscored review is honest; an invented score is a defect
that reads exactly like a measurement.

```json
{
  "hedging": {
    "type": "score",
    "instructions": "How much of this draft is padded with qualifiers that narrow nothing?",
    "criteria": [
      "Claims stand unqualified. Where a qualifier appears it names a real limit: a date, a sample size, or a condition the reader can check.",
      "One or two claims carry a softener the writer could have dropped. The draft still commits to its main points.",
      "Most paragraphs soften a claim without naming what limits it. Words like 'may', 'often' and 'in many cases' appear where nothing narrows.",
      "Qualifiers stack inside single sentences, as in 'could potentially possibly'. No sentence states anything a reader could disagree with."
    ]
  },
  "filler": {
    "type": "score",
    "instructions": "How many words in this draft could be cut without losing a claim?",
    "criteria": [
      "Every phrase carries a claim. Sentences open on their subject.",
      "A few stock phrases restate a shorter form, such as 'in order to' or 'at this point in time'.",
      "Sentences routinely open with a throat-clearing phrase before the claim, such as 'It is important to note that'.",
      "Whole sentences carry no claim. Cutting them would lose nothing a reader needs."
    ]
  },
  "passive_actor": {
    "type": "score",
    "instructions": "Does the passive voice in this draft hide an actor the reader needs?",
    "criteria": [
      "Passive appears only where the actor is unknown or beside the point, and naming one would add nothing.",
      "One or two passive sentences drop an actor the reader can still infer from the surrounding text.",
      "Several main claims name no actor. The reader has to guess who performs the action.",
      "Agentless passives carry the argument throughout, as in 'The results are preserved automatically' or 'The decision was made last quarter'."
    ]
  },
  "signposting": {
    "type": "score",
    "instructions": "Does this draft announce what it will do instead of doing it?",
    "criteria": [
      "Sections open on their content. A heading is followed by the first real claim.",
      "One transition narrates the structure rather than carrying the argument forward.",
      "Several sections open with a line that restates the heading before the content starts.",
      "The draft repeatedly announces itself, with phrases such as 'Let us dive in' or 'Here is what you need to know'."
    ]
  },
  "puffery": {
    "type": "score",
    "instructions": "Does this draft rate the importance of its subject instead of describing it?",
    "criteria": [
      "Claims are specific and checkable. Nothing in the draft rates its own significance.",
      "One sentence calls the subject important without evidence, and the rest describes it plainly.",
      "Promotional adjectives recur, such as 'vibrant' or 'renowned', and nothing in the draft supports them.",
      "The draft frames its subject as a milestone throughout, with phrases such as 'stands as a testament' or 'marks a pivotal moment'."
    ]
  },
  "overload": {
    "type": "score",
    "instructions": "Does each sentence in this draft carry a single idea?",
    "criteria": [
      "Each sentence states one idea. A long sentence is long because its one idea is long.",
      "A few sentences join two ideas, and a reader can still separate them.",
      "Most sentences carry two or more ideas, often joined by a trailing clause beginning with an '-ing' word.",
      "Ideas chain across clause after clause. No single claim is stated on its own anywhere in the draft."
    ]
  }
}
```

`jev ask` prints the whole response. Each dimension answers with a `score`, a
probability distribution over the levels, a `confidence`, and a `legend`
mapping each level number back to its description.

## Count the answers, not the questions

Report how many dimensions answered and how many were asked, as two numbers,
every time the pass runs. Then name any dimension that did not come back.

A summary counting what you sent says the same thing whether every dimension
answered or none did. That line stays green after the pass has stopped
working, which is how a dead check goes unnoticed for months. Counting what
came back cannot do that: a call that answered nothing reports `0`, and a
reader sees it.

A response missing a dimension is not a zero on that dimension. Leave it out
of the composite and say it is missing, because a score of `0` on `hedging`
means the draft hedges nothing, and that is the opposite of what happened.

## Record the raw scores, decide policy separately

Put every dimension's raw `score` and `confidence` in the report, unrounded.
Those numbers are the expensive part, and they are reusable: a reader who
disagrees with a threshold or a weight can change it and re-read the same
numbers without paying for inference again.

Do not report a single verdict in place of the dimensions. A composite that
hides its inputs cannot be argued with, and the argument is the value.

Normalize before combining. Divide each raw score by the highest level number,
so every dimension lands on `0` to `1` and a dimension with more levels does
not outweigh one with fewer.

Weights and thresholds are policy, and policy belongs to whoever owns the
prose. State the weighting you used beside the composite, so a reader can
apply different weights to the same scores. A release note and an internal
design page do not deserve the same weighting, and neither deserves one baked
into this file.

A low `confidence` on a dimension means the model spread its probability
across levels. Read it as "this dimension did not separate here", not as a
middling score, and say so rather than reporting the number alone.

## Tracking a draft across revisions

Scores earn their cost on the second run. Record the dimension scores against
the revision they describe, then score the revision that follows. A dimension
that moved is evidence the edit worked. A dimension that did not move is the
finding the reading pass should have caught and did not.

Compare only scores taken with the levels above unchanged. Editing a level
changes what the number means, so a comparison across an edit is a comparison
of two different measurements.
