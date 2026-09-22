# Domain packs

A domain pack is a repository that registers itself with the pack and then
extends the framework from outside it. It keeps its own manifest, its own
`<prefix>-*` skills, its own tools, and its rows in the shared database. The
pack installs nothing into it and reads nothing out of it except the manifest.

Three exist:

| Prefix | Repository | Declares |
|---|---|---|
| `sdw` | `sd-writing-pack` | three `kinds`, a vault `store`, three `config` keys, twelve `sdw-*` skills, four templates |
| `sys` | `system` | four `dashboard.actions` and nothing else |
| `hoa` | `hoa` | `issues`, two `config` keys, seven `hoa-*` skills, no kinds |

The three differ that widely on purpose. A domain pack declares the surfaces it
uses and leaves the rest absent; absence is the default everywhere, and every
optional block refuses at *registration* rather than at use time when it is
present and malformed.

## Registration

```bash
sd plugin add ~/repos/<repo>      # the checkout, or its sd-plugin.json
sd plugin list                    # what every registered root declares, read now
```

`add` validates the whole manifest and appends the checkout to `plugins` in the
machine config — `$XDG_CONFIG_HOME/sd-ai-command-pack/config.json`, else
`~/.config/…` (`source:bin/sd_lib.py::machine_config_path`). Nothing else is
written, and nothing is copied.

Two consequences worth knowing before you go looking for a re-register verb:

- **`list` re-reads the manifest every time** (`source:bin/sd::describe`), so an
  edit to `sd-plugin.json` takes effect with no second command. A manifest that
  has gone bad since registration is reported as a row with an error, not
  dropped silently.
- **A root already registered refuses** (`source:bin/sd::add`), as does a prefix
  another root holds. There is no `remove`: a root leaves by editing the
  machine config.

## The manifest

`sd-plugin.json`, at the root of the checkout. The vocabulary is closed —
R11-D14 — and enforced in one reader, so a key outside it refuses by name
rather than being ignored.

| Key | Required | What it buys | Validator |
|---|---|---|---|
| `prefix` | yes | two to five lowercase letters, unique across registered plugins; `sd` and `se` are reserved | `validate_prefix` |
| `interface` | no | the integer `sd plugin lock` pins alongside the manifest digest | `compute_lock` |
| `kinds` | no | notes this plugin stores, their fields and their status ladders | `validate_kinds` |
| `store` | no | which driver holds those kinds, and where | `validate_store` |
| `config` | no | the settings this plugin will accept, declared up front | `validate_config` |
| `issues` | no | `repo`, as `owner/name`, so a reader of `sd plugin list` need not guess | `validate_issues` |
| `dashboard` | no | a `tile` plus its `tabs`, and `actions` the dashboard may offer | `validate_dashboard`, `validate_actions` |
| `vendor` | no | upstream content this checkout carries a copy of, named and hashed | `validate_vendor` |

All validators are in `bin/sd`. An empty block is refused rather than treated as
absent — `"kinds": {}` is a block somebody meant to fill.

### `kinds`

Eight keys describe one kind, and a ninth spelling is a typo that refuses by
name. `fields` and `initial-status` are the two a kind cannot be missing; the
other six are optional and the verb that needs one refuses at use time.

| Key | Means |
|---|---|
| `fields` | the frontmatter keys the note carries, each `^[A-Za-z0-9_-]+$` — **no spaces**, so "care interval" is `care-interval` |
| `initial-status` | the status `sd store add` creates the note in |
| `transitions` | the status graph, as `{from: [to, …]}`. A self-transition refuses: it is a move that reads as a state change and does nothing |
| `human-only` | `{action: status}` for transitions a machine may not make. `sd store set` refuses them and says so |
| `protected-fields` | fields no machine may ever write. For a human judgement — `sdw` protects `my-rating` — not for a fact an agent should be able to record |
| `unique-fields` | fields whose value may not repeat across notes of the kind |
| `floor` | a numeric minimum per field |
| `sections` | `order`, the `## ` headings in sequence, plus `template`, a file inside the checkout. Either alone is unusable |

Cross-checks run at registration, and they are the ones worth designing around:
`protected-fields`, `unique-fields` and `floor` may name only declared `fields`;
`initial-status` and every `human-only` target must be a status some transition
mentions. A ladder therefore needs `status` in `fields` to act on — declaring
`transitions` without it refuses.

### `store`

```json
"store": {"driver": "vault", "root": "$OBSIDIAN_VAULT",
          "bases": {"tip": "System/Databases/Tips and Tricks"}}
```

All three keys are required together, `vault` is the only driver, and `root` must
be an environment-variable reference (`^\$[A-Z][A-Z0-9_]*$`) — never a literal
path, because a committed absolute path with a username in it is portable to one
machine. Coverage is checked both ways: a base naming an undeclared kind, or a
kind with no base, each refuse. The bases themselves are **not** checked for
existence — a vault may be unmounted or behind a TCC grant, and refusing
registration for that would fail a correct manifest.

`store` without `kinds` refuses.

### `config`

```json
"config": {"google_account": {"description": "…", "pattern": "^[^@\\s]+@…$"}}
```

`description` is required — `sd config list <prefix>` prints it, and the skills
that read a setting are told to show that output rather than paraphrase it.
`pattern` is optional and must compile at registration, so a bad regex cannot
wait for the first `set` to be discovered.

Values are not in the manifest. They live in the machine config under
`config.<prefix>` (`source:bin/sd::SETTINGS_KEY`), namespaced so a plugin cannot
shadow a root key, and are read back with `sd config get <prefix>.<key>`.

**This is where a machine fact goes.** Anything carrying a home directory, a
Google account, a Drive id or a mount point is a setting; the tree holds the key
name and never the value. What it cannot express is a rule spanning two keys —
`sdw`'s "the publishing folder and the writing folder must differ" is business
logic and stays with the plugin.

### `issues`, `dashboard`, `vendor`

- `issues.repo` is printed by `sd plugin list` and read by nothing else. That is
  the point: a reader of the listing should not have to guess where a plugin's
  issues live.
- `dashboard.tile` declares the command and `dashboard.tabs` the names it is
  invoked with, once per tab under its own budget; `dashboard.actions` are
  `{id, label, run}` the dashboard may offer. `sys` declares four. **Check
  before declaring one:** the local dashboard finds document roots on disk and
  does not open plugin manifests, so on this machine an action is printed and
  not run.
- `vendor.<name>` takes `source` and `path`, both required, the path inside the
  checkout — an absolute path, a `..` segment, or a symlink that resolves out of
  it all refuse. `sd plugin lock` hashes exactly what is declared.

### `sd-plugin.lock`

`sd plugin lock` writes the interface number, the manifest digest — of the bytes
on disk, so a reordered key is drift — and a hash per vendored tree.
`sd plugin lock --check` is the half with a consumer: a plugin's own CI asserting
that neither moved without the lock moving with them. A domain pack with no CI
gets nothing from the file; `system` carries one, `sd-writing-pack` and `hoa` do
not.

## The halves that are not the manifest

**Project-local skills.** `<repo>/.claude/skills/<prefix>-*/SKILL.md`, one
directory each: twelve in `sd-writing-pack`, seven in `hoa`. They are the
domain's own verbs and the pack never installs, renders or lists them —
`skills/paths.json` governs this repository's `sd-*` skills and says nothing
about a domain repo's. Name them `<prefix>-<verb>` so a reader of the directory
can tell them from the machine-wide ones.

**Templates.** One file per kind with `sections`, anywhere inside the checkout;
`sd-writing-pack` keeps them in `templates/`. The path is checked at
registration and must be a regular file — a directory there satisfies "it is
there" and fails when somebody renders a note.

**Tests.** The interesting thing to test is not the manifest, which the
validators already cover, but whether the skills still describe commands that
run. `hoa/tools/check-skills.py` extracts every command block from its seven
`SKILL.md` files and executes them; the manifest regression described below is
exactly what it caught, three runs before anyone read the line.

**Rows.** A domain repo's work reaches `sd today` and the dashboard through the
shared database, by repository path. That needs no manifest key. `kinds` and
`store` are for notes the plugin keeps *outside* the database, in a vault.

## What a domain pack may not do

- Take the prefix `sd` or `se`, or one another root holds.
- Use a driver other than `vault`, or a literal path as `store.root`.
- Reach outside its own checkout in `vendor.*.path` or `sections.template`.
- Write into this repository. The pack renders out; nothing renders in.

## The failure this page exists to prevent

On 2026-09-21 the `hoa` manifest was rewritten and lost its `config` block. The
three skills that run `sd config get hoa.google_account` as a real step began
refusing with `hoa declares no config keys`; the value was in the machine config
the whole time, so nothing was lost but the declaration. `check-skills.py`
printed `FAIL(1)` three times a run and nobody read it.

A manifest has no checker beyond registration and, until this page, no document
to be read against. Two smaller versions of the same thing are on record in
`hoa`'s own log: a `protected-fields` entry that made a fact an agent should
record unwritable, and field names with spaces that `FIELD_PATTERN` refuses.
Declare the surface you use, read `sd plugin list` after editing, and run the
commands your skills claim.
