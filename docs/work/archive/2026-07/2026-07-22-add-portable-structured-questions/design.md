# Design: host-adapted structured interaction

## Canonical Interaction Descriptor

Each decision point declares:

- stable decision ID and category;
- user-facing question and short header;
- recommended option and 1-2 alternatives;
- consequence text;
- single- or multi-select behavior;
- interactive fallback; and
- noninteractive stop/default behavior.

The descriptor is semantic metadata or a validated shared reference, not an
executable host-tool payload embedded independently in every skill.

## Capability Adaptation

The command-surface generator maps the descriptor to host guidance:

- Claude-capable adapters: invoke `AskUserQuestion` with the supported shape.
- Other structured-capable hosts: invoke their declared native capability.
- Interactive hosts without structured capability: ask one concise plain
  question and preserve the same options/consequences.
- Noninteractive hosts: execute only a predeclared safe default; otherwise stop
  with the decision ID and required user input.

Capability metadata is versioned and tested. Unknown capability is treated as
unavailable, never guessed from model identity.

## Question Economy

The policy minimizes interruptions:

1. Inspect repository evidence first.
2. Apply invocation authority and safe defaults.
3. Batch independent selections only when a batch materially reduces turns.
4. Ask only the highest-value unresolved decision.
5. Carry the answer through the current bounded workflow rather than asking it
   again unless scope or evidence changes.

## Security Boundary

Structured answers can narrow or select within existing authority. They cannot
authorize execution of untrusted checkout code, bypass failed gates, expand
merge authority, or approve destructive actions that require a separate
explicit workflow.

## Rollback

Removing host-specific generation returns to canonical plain questions. It must
not change the underlying decision authority or noninteractive stop behavior.
