---
title: Design — artifacts as product
item: 2026-08-29-artifacts-as-product
---

# Design record

Consolidated from planning rounds r1–r9c plus R10/R11 amendments (2026-08-29). Every
round ran as an adversarially-reviewed multi-agent workflow; the round artifacts are
session scratch and not committed. Section numbering follows the accepted plan.

## Honest critique (what to stop believing)

1. Trellis's value is the triad + spec KB + archive-on-done. Its runtime (hooks, phases,
   `get_context.py`, journals, jsonl manifests, 17-platform adapters) is ceremony.
2. sd-github-review is 30k LOC JS (9,390 of 13,867 src unreachable) to choose among 4 tiers; only
   Copilot is used. Its consumer footprint is the largest P6 violation. Its *routing model* is
   worth keeping — as opt-in config, not mandatory infrastructure (round 3).
3. Committed derived state is permanent staleness. Derive at run time or don't exist.
4. Local gates stricter than GitHub but enforced by prose produce "approved by a lane that never
   ran". Merge authority is GitHub branch protection **wherever protection is actually enforcing**;
   local tooling mirrors it read-only and never claims more than the config provides. Protection
   that exempts admins is prose, not authority: it stops collaborators and leaves the one author
   who does 100% of the merging entirely ungated. So the doctrine is conditional by construction —
   `sd-status` reads the live protection object per repo and reports every enforcement dimension
   that is missing — the same set the step-3b brief specifies: no protection at all ·
   `enforce_admins: false` · `strict: false` (so a green check on a stale base still merges) ·
   required contexts that do not match the jobs CI actually runs · no PR-review requirement. Any
   one of them missing is a *reported gap*, never a silent assumption of safety.
5. Release train + fleet rollout for a single machine is pure overhead. Machine-scope install from
   one checkout removes versions, ledgers, PATH shadows, fleet refresh.

## Target architecture

### One repo, machine-scope install

```
sd-ai-command-pack/
  install.py            --user renders skills/agents to ~/.claude (all sd-*, one prefix),
                        ~/.codex/skills, ~/.config/opencode/commands, and (probe-gated, r9b)
                        Antigravity skills as verbatim SKILL.md copies — D1 revised: Claude +
                        Codex + OpenCode rendered + parity-tested; Antigravity AGENTS.md-native
                        now, render behind probe P1. No sd-* skill/command renders as TOML anywhere.
                        --pull (ff-only, refuses off-main), --status (banner +
                        legacy/residue detectors), --adopt-legacy (receipt-gated, migration only),
                        --repo (CLAUDE.local.md marked block), --uninstall; owns only names it
                        renders (installed.json: checkout, commit, branch, dirty, platformHomes,
                        owned[], hashes) — incl. the one SessionStart stanza it adds to
                        ~/.claude/settings.json for sd-handoff-restore (R10-D3) — the single
                        user-settings edit the installer ever makes, recorded in owned[],
                        removed on --uninstall; ensures ONE global-excludes line `CLAUDE.local.md`;
                        never edits AGENTS.md or any tracked repo file
  skills/sd-*/SKILL.md  11 commands + the sd-help skill (a catalog, not a command
                        — R11-D15) + templates (prd, design, implement, decision,
                        work-README)
  skills/sd-*/SKILL.md  + 64 merged skills, renamed se-* → sd-* at fold (67 on disk − 3 retired:
                        se-help, se-brand-voice, se-humanizer — retired under old names)
  agents/               sd-rust-write/fill/reviewer, sd-claim-verifier, sd-source-reader —
                        each carrying a declared `tools:` key. The vendoring half of this row was
                        struck at P2 (2026-08-30): every kimi and codex agent turned out
                        to be a wrapper over plugin-owned machinery, so vendoring the
                        markdown would have shipped surfaces that resolve and then refuse
  bin/                  sd_lib.py (detection, derive_status), sd_route.py, sd-check, sd-docs-lint,
                        sd-pr-state, sd-review(+-local), sd-status, sd-spec, sd-map, sd-handoff,
                        sd-trackers, sd-handoff-restore (hook), sd CLI (plugin|store|issue|config groups),
                        migrate-* (temp)
  dashboard/            stdlib HTTP server + one JS file (≤4,300 total and ≤2,300 carrying
                        code -- R11-D24 split the ceiling in two). The `sd-dashboard` CLI in
                        front of it is listed under bin/ and charges there, so the two caps
                        do not overlap
  actions/              docs-lint + review-route composite actions (SHA/tag-pinned, opt-in only)
  docs/work|spec|decisions   dogfood
  tests/                ~3k lines: install, docs-lint, route fixtures, store invariants,
                        renderer parity across 3 platforms (+Antigravity once P1 passes), verb-inventory, LOC caps
```

**LOC discipline (one decision record, restated after the feasibility audit):** bin/ ceiling
**14,000** (R11-D15, 2026-08-31). The itemisation below derived the superseded **8,000** (accepted
by user 2026-08-29) and is kept as the record of that derivation, not as a claim about the
ceiling. Itemized: core (sd_lib, sd_route, sd-check, docs-lint, pr-state, status, spec,
trackers incl. ~90 lifted Jira LOC) ~1,800 · review lane **1,700 sub-cap** (R11-D8) · r2 dashboard
glue/index +900 · r4 sd-map +400 · r5 plugin/store **1,400 sub-cap** · r7 Lane B handoff +120 ·
R10-D3 packet writer + restore hook + identity checks +250 · R10-D1 worktree/codex-exec/budget/
draft-PR lane +450 · R10-D2 draft-convert +40 · 45-day sweep +40 · google.accounts resolution
+50 · env reads +20 = **~7,170**, leaving ~830 headroom — *superseded as a prediction by the
count in R11-D13: `bin/` core is already at 7,492 with seven commands unbuilt. The itemisation
stands as the record of how 8,000 was derived, not as a claim about today.* The earlier 6,000 and 6,500 figures
were both busted on paper, and on 2026-08-29 the record called 8,000 the honest number at
"still <1/11 of today's 95k". *8,000 was busted too. R11-D15 re-derived the ceiling at 14,000
from built code — roughly a seventh of the 95k rather than an eleventh.*
Temporary `migrate-*` is **outside** the cap (deleted at steps 7/11), tracked by its own 1,500
ceiling until then. *(2026-09-02: `migrate-trellis` went at step 7 as planned. The schedule's
other half is spent -- step 11 moves nothing, so `migrate-golden-corpus` is deleted when 10b
lands instead. It is the only `migrate-*` left, at 360 lines of the 1,500.)* dashboard/ ≤ **4,300 total and ≤ 2,300 carrying code** (*R11-D24 re-derived
and split it at 6b-7; the 4,000 below is what it replaced.* R11-D17 had re-derived it at 6b-3 from files that exist:
2,488 measured plus R11-D13's 763-line lift and two estimates. The old 2,500 rested on "credible:
457 lifted + one JS file", and R11-D13 measured that lift at 763*). Caps are CI tests; a cap is
never raised in the PR that busts it — 4,000 was set in its own record by a change that fit under
2,500, and 4,300 in its own record by a change that fit under 4,000. *`bin/`'s 14,000 may only move
downward, untouched. The dashboard total may be re-derived with an itemisation, once R11-D24 spent
that clause on it; its **code** half inherited the clause and is the one that may only fall.* Still <1/10 of today's 54k scripts + 30k router + 11k installer.

### Commands (11 — grown from 8, each growth carried by a decision record; `sd-help` left at
R11-D15, being a catalog rather than a command)

| Command | Purpose |
|---|---|
| `sd-plan <slug>` | Interview → `<work>/<date>-<slug>/prd.md` (+design/implement when warranted); ends with `sd-review --scope planning` (codex second-model lane, r8) writing `## Review`; `planning → ready` only with no open BLOCKING line; creates branch, records `branch:`; first commit sweeps merged items — and items idle in `planning` >45 days with no `branch:` (R10-D1) — to `archive/YYYY-MM/`. Flags: `--decision`, `--work-dir`, `--worktree`, `--from gh:o/r#N\|jira:KEY`, `--from-suggestion`, `--from-proposal` |
| `sd-check` | Typed deterministic runner over repo-native entrypoints (`check:` in local block, else autodetect Makefile/Taskfile/package.json/Cargo/pyproject) |
| `sd-review` | sd-check → route() → local providers on exact diff; findings dispositioned locally, never posted; `--scope worktree\|branch\|pr\|planning`, `--challenge` (kimi-challenge or codex adversarial prompt), `--explain`, `--dry-run`, `setup-github` subcommand (opt-in CI routing, r3) |
| `sd-ship` | Verify acceptance → sd-spec → docs-lint → commit (enumerated paths only, never `add -A`) → push → PR with `Work:` line → request Copilot once per head → settle loop → `gh pr merge --squash -t "<title> (#N)" -b "<body>"` (wip-eraser, r7). **No write after settled-green.** `--pr N`, `--backlog` (ported work-backlog loop, r6 D12), `--agent claude\|codex` + `--jobs N` + `--cap N` + `--dry-run` (autonomous lane, R10-D1), `--tier`, `--no-github` |
| `sd-spec` | Update `docs/spec/**` on the PR branch; `--retro` appends review-learnings |
| `sd-status` | Read-only: derived status, open PRs, detected setup + protection gaps — enforcement state first (`enforce_admins`, required contexts vs the jobs CI runs, PR-review requirement), then squash-message + rebase-merge flags (r7), resumable-handoff section (pending local packet for this directory + Lane B branches derived from origin), backend availability, legacy residue with exact removal commands, pack banner |
| `sd-deps` | Batch-triage dependabot/renovate PRs |
| `sd-suggest` | File framework improvements to the configured tracker (gh dedup via list API; local draft deleted on successful filing) — r2 N7 |
| `sd-skill-adopt <path\|url\|->` | One-command skill intake: safety pre-screen → lint → canonical transform → provenance → write per `--scope pack\|user`; `--from-repo --list` for external-repo survey (report-only) — r2 N8 |
| `sd-map` | Supporting artifacts (repomix/index/kb) into `~/.local/share/sd-ai-command-pack/<repo-id>/artifacts/` — out-of-tree by construction, flock'd, never a gate, never scheduled — r4 |
| `sd-handoff [--push] [--park] [--show]` | **Default (R10-D3, Lane A):** write the local session packet for this directory, no git touched; then `/clear` restores it. `--show` prints the pending packet (the load path for Codex/OpenCode sessions, which have no SessionStart hook). `--push` (Lane B): additionally append `handoff:` to `## Log`, commit+push WIP to carrier branch, print restart one-liner; `--park` applies to Lane B only. Guards: settled-green refusal, branch-scoped stash check, open-PR draft+no-re-review (R10-D2). 60-day deletion criteria on both lanes |

CLIs (not skills): `install.py`, `sd-dashboard serve|install|index [--dump]|item set-status|export
--obsidian`, `sd plugin|store|issue|config` verb groups (r5), temporary `migrate-trellis`
(deleted at step 7). `migrate-vault` was listed here until 2026-09-02 and was never written.
The verb inventory is a CI-tested invariant; any change is a decision record.

**Taxonomy (r6 §1, restated here because it governs every row above).** A surface is a
**COMMAND** only when its invocation pre-authorizes external side effects without further
prompting — "invocation is explicit approval"; deliberate invocation only, thin entry (≤~50
lines) that parses args, states the approved scope, loads a skill. A **SKILL** is knowledge or
procedure loaded when relevant, with no standing side-effect authority — any write it guides is
gated by an in-flow approval, not by loading; also the home for reference material. An **AGENT**
is a bounded worker needing context isolation, tool restriction, or fan-out (read-only
reviewer/verifier, patch-only writer, single-task specialist) and must declare `tools:`.
Stated exception: help/catalog surfaces (`sd-help`) are skills. Behavioral consequence, enforced
by the render: commands set `disable-model-invocation`, skills do not, agents carry `tools:`;
the parity test asserts each rendered file carries its kind marker, and the step-5 collision
check is keyed on kind. The vendored-agent carve-out (upstream names kept, the one-prefix rule
covering only merged se-* surfaces) is retained for a future vendored agent, but as of P2 it has
no members: see the P2 record in `implement.md` for why kimi-* and codex-rescue were dropped
rather than vendored.

### Consuming-repo layout (the entire tracked footprint)

```
<work>/README.md + <date>-<slug>/prd.md [design.md implement.md]   (+ archive/YYYY-MM/)
docs/decisions/  (only if no ADR location exists)
docs/spec/       (or link index to existing ARCHITECTURE.md)
.github/workflows/docs-lint.yml | sd-review-route.yml    OPT-IN only
.github/sd-review.json                                   OPT-IN (routing policy, pairs with sd-review-route.yml)
sd-plugin.json + sd-plugin.lock                          only in repos that ARE plugins (r5)
```

**Sessions stick to their repos (R10-D6, mechanism not principle):** every sd-* command resolves
its repo from cwd only — no command accepts a repo-path argument, and the verb-inventory test
asserts it. Today's fleet-style `sd-status` that walks every installed checkout is **dropped**;
the dashboard is the only cross-repo view, and it reads, never acts. A work item whose `branch:`
resolves to a different checkout is a refusal with the path printed, not a silent `cd`.

Untracked, machine-side only: `CLAUDE.local.md` marked block (canonical per-repo local config,
globally ignored via one excludes line; worktrees resolve to main worktree's copy via
`--git-common-dir`), repo entry in `~/.config/sd-ai-command-pack/config.json`. Nothing under
`.claude/`, `.trellis/`, `.sd-ai-command-pack/`; no hooks, labels, variables, secrets, managed
gitignore blocks, or bookkeeping commits. Platform coverage of the local block (r2 + r9b):
Claude native; OpenCode via global `instructions` entry; **Codex, Copilot CLI, and Antigravity
out of v1** (no untracked-file import mechanism — D15/D16/R9b-D4; Antigravity compensates by
natively reading tracked `AGENTS.md` hierarchically, zero machinery). **Partial fallback
(R10-D7):** in the lanes the pack itself invokes — `sd-review` codex/antigravity providers,
planning review, `sd-ship --backlog --agent codex` — the local block's content is prepended to
the prompt the pack builds, so per-repo conventions do reach those runs without any import
mechanism. Only *interactive* Codex/Antigravity sessions remain uncovered in v1.

### Gates (5 lint rules, unchanged; one enforcement point per repo)

1 Shape · 2 Ready (acceptance criteria + no open BLOCKING; `in_progress` needs `branch:`) ·
3 Decision shape · 4 Spec index · 5 PR link (`Work:` resolving to item with 0 unchecked boxes, or
`Work: none - <reason>` under 800 lines + no sensitive path; reads post-`never_skip` routing; also
hard-fails any PR diff touching `CLAUDE.local.md`). **Author-scoped in CI (R10-D5):** when
`docs-lint.yml` runs, rules 1–4 are advisory (annotations only) and rule 5 hard-fails **only for
PRs whose author is listed in the planned `sd-review.json` policy file (under `.github/`, not yet present) `authors[]`** — for anyone else the check
reports and passes, so a non-adopting collaborator can never be blocked by the framework.
Locally, `sd-ship` enforces all five for you regardless. `mode: minimal` and `guest` refuse
`sd-review setup-github`, so shared and OSS repos cannot grow the workflow at all. Merge
authority = GitHub branch protection **where it is enforcing** (critique 4); where it is not, the
pack reports the gap and the honest statement is that nothing enforces merge authority in that repo.
The backbone ships nothing on UserPromptSubmit/PreToolUse/pre-push and exactly one SessionStart
hook, `sd-handoff-restore` (R10-D3), which gates nothing. Machine-level hooks outside the pack
(send guard, aaif guard, cbm-*, rtk, claude-mem) are unchanged except the day-0 guard retarget. `## Log` gains a schema by template,
not lint (r7): only machine-matched token is a tail `- <date> handoff:` line.

Standing rules: (1) no new gate/ledger/hook/rule without a linked incident + deletion criterion —
extended to dashboard tabs, stores, index columns, RUN_ALLOWLIST ids, adapters, store verbs;
(2) rule count is 5 and the plugin-kind vocabulary is 8 keys; changes are decision records.

### Storage doctrine (r2 + r5 + r6 + r7, reconciled)

**Every fact has exactly one writable home; everything else is a rebuildable cache or one-way
projection nothing reads as input.**

| Fact | Writable home |
|---|---|
| Work items, decisions, spec, review dispositions, Lane B handoffs | consumer git (`<work>/`, `## Review`, `## Log`) |
| Local session handoff packet (Lane A, R10-D3) | `~/.local/state/sd-ai-command-pack/handoff/<digest>.json` — written only by an explicit `sd-handoff`, consumed once by `sd-handoff-restore`, 14-day expiry, one per directory (newest wins); never read by any other command |
| PR/CI/review state | GitHub (derived, never stored) |
| Decision queues (tips/ideas/topics/market-watch/skill-proposals) | **Obsidian vault stays system-of-record** (R5-D1); accessed via `sd store` with vault driver; queries read the vault (never stale); SQLite is index only |
| Framework-native kinds (runs, review ledger rows, routed issues, divergence) | `~/.cache/.../index.sqlite` — observability only, never an enforcement input; `rm` loses time only (r7 D13 demotion rule: non-derivable rows land in git homes first) |
| Status-flip intents (dashboard) | `~/.local/state/.../intents/` — applied by next sd-plan/sd-ship sweep; dashboard **never** touches a working tree |
| Per-repo local config | `CLAUDE.local.md` marked block |
| Machine config | `~/.config/sd-ai-command-pack/config.json`. **D-C1 decided (user, 2026-08-29): every pack-owned config/manifest file is JSON** — machine config, the planned `sd-review.json` policy file (under `.github/`, not yet present) policy, `sd-plugin.json` + `sd-plugin.lock`. YAML rejected (PyYAML not stdlib), TOML rejected (no tomllib on /usr/bin/python3 3.9.6, verified r2). External tools keep their own formats (~/.codex/config.toml, .gito/config.toml); prd frontmatter + local-block fence stay as the 20-line flat-scalar subset parser |
| Ambient session memory | claude-mem (unmodified plugin, r6 D10a); backbone never cross-reads; no sd-* command may depend on it (r7 D14) |
| Personal PKM, Prompts DB, TaskNotes | vault, untouched — leave-alone list per r5 §2 claim test |

### Dashboard (r2, staged replacement of system/local-project-dashboard)

Stdlib ThreadingHTTPServer + one vanilla JS file; ~457 LOC lifted verbatim from dashboard.py
(*superseded: R11-D13 enumerates the backbone-side lift at 763 — 79 collector lines plus 684 of JS.
How much of that is liftable verbatim rather than rewritten is not separately measured*). Tabs:
Now · Work · PRs · Issues · Repos · Queues · Suggestions · Skills · Sessions · plugin tabs
*(R11-D21 later moved Queues to a plugin tab, and R11-D22 took Suggestions out of the backbone list until `sd-suggest` exists to fill it)*
(a registered manifest declares `dashboard.tile` and `dashboard.tabs`, and the loader
invokes that one tile once per declared tab name — R11-D16; the
`dashboard.d/*.py` spelling this record used until 6b-2 landed never existed, because a loader
that globs a directory would be the disk scan the interface refuses). Now screen = externally derived facts only. Every UI
mutation maps 1:1 to a bin/ command (RUN_ALLOWLIST); server never commits/pushes/runs agents.
Sessions tab = `git worktree list` + running sd-* processes (replaces Trellis `.runtime/sessions`
— the Trellis-hooks answer: **no hook carries over**). Lands on **:8768 beside** the system
dashboard; per-tab parity checklist gates the swap to :8767 at step 6b. *(Taken at 6b-8:
`DEFAULT_PORT` is 8767, and the LaunchAgent carries the tailnet bind.)* Deferred behind standing
rule 1: FTS/Search, log streaming, session launcher. Phone access is **decided as (c)** — see
R11-D10 below; the swap at 6b carries today's tailnet reach and its token-gated writes rather
than regressing them. A plugin tab may also return **alert rows for Now** — see R11-D12; a
render-only tile would strip Now of most of what it alerts on.

### Review routing + pluggable backends (r3; revises D4)

D4 stands for the *mandatory* footprint: Action, receipt protocol, consumer installer, labels,
variables retired. The routing model survives as one config table + pure
`route(paths, lines, draft, policy) → Plan`: categories (required-first, and matched by the
direction they move the tier — any path to hold or raise it, every path to lower it, R11-D9),
docs-skip as allow-list minus a non-removable `never_skip` deny-list, 800-line threshold,
sensitive globs, draft policy, tier chains. Backends on the existing Provider seam:

| Backend | Kind | Cost | Default role |
|---|---|---|---|
| codex | local CLI (hardened invocation verbatim from review-local.py:1983-2018) | $0 (ChatGPT sub; **rate-limited outcome distinct from unavailable**, r8). **Subscription only, never API billing (R10-D4, user 2026-08-29):** verified precedence in codex-rs `load_auth()` is `CODEX_API_KEY` env → ephemeral → `CODEX_ACCESS_TOKEN` env → `auth.json`; `OPENAI_API_KEY` is *not* read by the CLI. This machine: `auth_mode: chatgpt`, no key in auth.json, `codex login status` = "Logged in using ChatGPT". Preflight before every codex call (review, planning, `--agent codex`): scrub `CODEX_API_KEY`/`CODEX_ACCESS_TOKEN` from the subprocess env (`build_tool_environment` inherits `os.environ` today), assert auth.json `auth_mode == chatgpt`, refuse otherwise — a run can never silently fall over to metered billing | heads every chain; default planning-review provider |
| prism | openai-compatible | ~low | standard fallback |
| gito | openai-compatible | per-file | deep fallback |
| kimi | argv row (`kimi -p <prompt> --output-format text`); the vendored-agent half was struck at P2 — the plugin's agents were hook-gated and its setup had never been run on this machine | low | `--challenge`, fan-out |
| antigravity (replaces gemini, r9b) | local CLI: `agy -p --output-format json --json-schema` on exact diff | $0 conditional on V1′ (paid sub on active account) + V2′ (training opt-out); gated on probe P2 (non-TTY stdout gotcha — P2 fail → pty wrapper → else delete row, per R9b-D2); local-only lane, never in setup-github CI | planning/branch diversity; personal/platypeeps repos only until employer policy check; preflight refuses on active-account mismatch |
| local exo :52415 (R11-D1, user 2026-08-29 — replaces llama.cpp row) | openai-compatible adapter (`/v1`, verified live: MiniMax-M2.7-4bit, Qwen3-Coder-480B-A35B-4bit) | $0 | **probe-gated** (severity-floor probe; graveyard predicts failure) — cheap tiers only; model pinned by name in config, preflight refuses if not in `/v1/models` |
| copilot | github-kind | credits | remote default (opt-in `enabled_repos`) |
| greptile | github-kind | per-PR | opt-in; preflight requires `skipReview:"AUTOMATIC"` |
| baseten | openai-compatible | metered | **shipped disabled, gap-gated** (r8b) |
| openrouter | — | — | design note only: build-on-first-outage fallback |

Cost: soft caps in config; enforcement from GitHub-observable facts (`max_requests_per_pr`,
confirmed request landings); ledger is observability only. Docs/design PRs plan `skip` at $0.
Opt-in CI path: `sd-review setup-github` (preflight, refuses over legacy footprint without
`--remove-legacy`; policy read at base-sha; new filename `sd-review-route.yml`).

### Plugin interface (r5 — backbone + repo-specific packs)

Committed `sd-plugin.json` manifest (JSON per D-C1) + the `sd` CLI as sole service surface. Manifest declares
`prefix`, `interface = 1` (experimental marker; only promises: exit codes 0/1/2 and
`sd store get --json` returns fields + full body), `kinds.*` objects (closed 8-key invariant
vocabulary — plugin-declared, backbone-enforced generically), `issues.repo`, `vendor.*` +
`sd plugin lock`, optional `dashboard.tile` (5s/64KB contract). Registration only via
`sd plugin add` — no disk scanning, no repo writes.

**The eight keys, written down (R11-D14, 2026-08-31).** Standing rule 2 fixes the kind vocabulary
at eight and makes any change a decision record, and until now this repository never said which
eight — the enumeration existed only in the r5 round artifact, in a scratchpad under `/private/tmp`
that no backup covers. A closed vocabulary nobody can recite is not enforceable, and a rule
against growing it has nothing to measure growth from. They are:

| Key | What it carries |
|---|---|
| `fields` | the kind's frontmatter fields |
| `initial-status` | status a newly added item starts in |
| `protected-fields` | fields the store refuses to overwrite |
| `transitions` | status moves a machine caller may make |
| `human-only` | per-kind action → status map; seeded verbatim from `task-actions.sh`, not a hardcoded accept/decline pair |
| `unique-fields` | fields that must not collide within the kind |
| `floor` | numeric minimum |
| `sections` | ordered H2 list plus the template path in the plugin repo |

Recorded verbatim from the r5 ruling, with one carry-over noted rather than silently converted:
r5 wrote these as TOML `[kinds.<name>]` tables and **D-C1 later made every pack-owned manifest
JSON**, so they become object keys. The kebab-case spellings are kept exactly as ruled — renaming
them to snake_case while transcribing would be a vocabulary change wearing the clothes of a
format change, and standing rule 2 says that is a decision record. Repo-scoped skills ARE the contract (no
`sd plugin sync` copy machinery). **sd-writing-pack is the first plugin**: pack.py 2,532 → ~2,000
LOC (store verbs and `config` deleted; `gh`, `review`, pieces, build-html and the companion ledger
stay). Restated from ~1,250 at step 10b, where the deletion was measured rather than estimated.
Two corrections, in order of size. The original figure counted `gh` and `review adversarial` as
deleted, and both still have live callers, so what 10b-iv can actually remove is 519 lines -- 493 of
function bodies plus 26 of argparse wiring inside `main` -- and pack.py lands at 2,013. Granting the
assumption anyway only reaches 1,863, because the floor was never the verbs: `pieces` is 214 lines
addressing git files under `content/<year>/<slug>/`, which `store.driver = vault` cannot reach at
all; `main` is 198 today and 172 once its wiring goes, carrying the whole argparse tree; and 769
more are imports, constants
and module-level code. ~1,250 was never available under any deletion this rollout makes.

Vault-side callers (intel-brief, intel-weekly, tips-weekly, tips-accept,
aaif-brief-compile, and `settings.vault.json`) retargeted **before** any deletion (step 9);
`market-watch` was named here for a year and contains no `pack.py` reference at all. pp-* is the named
second consumer that validates the interface before any freeze.

**Where a kind is kept: the `store` block (R11-D26, 2026-09-01).** A sibling of `dashboard`,
never a ninth `kinds.*` key — the eight describe what a kind *is*, and none of that changes when
the same kind is kept somewhere else.

```json
"store": {
  "driver": "vault",
  "root": "$OBSIDIAN_VAULT",
  "bases": { "blog-idea": "System/Databases/Blog Ideas" }
}
```

| Key | Rule |
|---|---|
| `driver` | a closed set, `vault` today; a typo refuses by name rather than falling through to the only default there is |
| `root` | an environment-variable reference, `^\$[A-Z][A-Z0-9_]*$`; a literal path refuses (incident: `pack.py:146`), and there is no default |
| `bases` | one entry per declared kind and no others, relative to the root; **not** checked for existence, because a vault may be unmounted or behind a TCC grant while the manifest is correct |

`sd store list|get` read the vault at every invocation — no index, no cached manifest, nothing to
sync — which is R5-D1's system-of-record promise made checkable. The driver probes the root in a
bounded child before reading it (`VAULT_PROBE_SECONDS` = 15, carried from
`local-project-dashboard/collectors.py:173-227`): macOS answers an ungranted `~/Documents` read by
waiting rather than failing, and a driver that told "missing" from "present" apart and nothing
else would inherit a 1605-second hang.

### Session handoff (r7)

**Two handoff lanes, split by what they actually solve (R10-D3, user 2026-08-29).**

**Lane A — local session packet (default).** The driver is same-machine session replacement: a
session becomes context-compromised and must be killed and restarted against the same repo.
Nothing here touches git, GitHub, or CI.

*Where it lives — the working directory is the key (user, 2026-08-29).* Sessions are ephemeral
and their ids are worthless across a restart; the directory is the one thing both sessions share.
`~/.local/state/sd-ai-command-pack/handoff/<digest>.json`, where `<digest>` = sha256 of the
**normalized worktree root**, resolved as hook payload `.cwd` → `$PWD` → `CLAUDE_PROJECT_DIR` **last**, then `git rev-parse
--show-toplevel`. Order matters: `CLAUDE_PROJECT_DIR` is the *launch* directory, fixed per
session, so after EnterWorktree the writer (cwd = worktree) and a restorer preferring the env
var (= main checkout) would compute different digests and never meet. The existing PostToolUse
hook prefers the env var, but it only needs *some* root, not a stable key.
Normalizing to the root rather than hashing raw cwd is what makes a session started in `src/foo`
find the packet a session started at the root wrote. Inside a worktree `--show-toplevel` returns
the worktree root, so two worktrees of one repo get distinct packets for free — correct, since
they hold different work. Outside a git repo the raw directory path is the identity, so packets
work in non-repo directories too.

This deliberately **diverges from `repository_identity()`** (`work-loop.py:327`), which hashes
root + canonical remote: for a local packet the remote adds only a way to break things, since
adding or changing `origin` would orphan a live packet, and a repo with no remote is first-class
here. Same state root and same digest-keyed layout as the existing `work-loops/`,
`fleet-timing/`, `fleet-campaigns/` dirs — reused convention, different (simpler) input.

*Hash on path, verify on content (user, 2026-08-29 — "pwd as a fallback or extra check").* Path-
only hashing has one real collision: a **different project at a reused path** (finish A in
`~/repos/scratch`, delete it, clone B there — A's packet would auto-inject into B). So the packet
records identity fields it does not hash, and restore checks them before injecting:
`root` (plain text, so a mismatch is diagnosable rather than an opaque hash), `cwd_raw` (the pwd
at write time), and `remote` (canonical origin, recorded but **never hashed**). Rules: recorded
`root` missing, or not a prefix of the resolved cwd → **refuse**; recorded `head_sha` **not present as an object** in the current repo (`git cat-file -e`) →
**refuse and say why** — that is the reused-path / different-project case, and it is decisive
where a remote comparison is not (switching `origin` to your fork keeps the history, so the
fork-first flow passes this test); recorded `remote` differing from the current one → inject
with a warning line, never refuse on it alone; `head_sha` *divergence* (present but not HEAD)
is normal and is context, not a check. Belt and braces, each doing what it is good at: the path keeps the key
stable and GitHub-free, the recorded remote catches the one case the path cannot.

*What it holds* (JSON per D-C1, hard **8 KB** cap — the cap is the anti-journal mechanism):
`schema`, `created`, `expires` (created + 14d), `consumed` (null or ISO); `repo` {root, cwd_raw, remote, label,
branch, head_sha} (root/cwd_raw/remote recorded and verified on restore; label/branch/head_sha
context only; only the normalized root is hashed); `item` (work-item dir, or **null** — packets work with no work item at all);
`summary` (≤600 chars); `next[]` (≤5); `dont[]` (≤5 — dead ends already tried, the field that
saves the most rework); `questions[]` (≤3); `files[]`, derived mechanically from `git status
--porcelain` + `git diff --name-only`, never typed by hand; optional `stash_ref` pointing at
`refs/sd-handoff/<id>` — a local-only ref, outside `refs/heads`, so it is never pushed and never
seen by a remote.

*Collecting.* `sd-handoff` writes the packet and stops. No commit, no push, no PR, no CI, working
tree left exactly as it stands. The agent fills `summary`/`next`/`dont` from the session; the
mechanical fields derive themselves.

*Loading back — automatic.* One SessionStart hook, `sd-handoff-restore`, on matchers
`startup|clear` **only** — never `compact` or `resume`: a context-compromised session is by
definition near auto-compact, and a `compact` matcher would consume the packet into the dying
session so the following `/clear` finds nothing; `resume` continues old context and has no use
for it. `clear` is literally the kill-and-restart event. It resolves the digest from cwd. It exits silently when `SD_HANDOFF_RESTORE=0` is in its env —
`cron-jobs.sh` exports that one line for every `claude -p` job (two run in `~/repos/system`,
twelve in the vault, all git repos: without the guard a packet written there is eaten at
3 a.m.) — or when no unconsumed, unexpired packet exists, at zero cost; otherwise it emits the packet as
`additionalContext`, stamped with its age so a stale packet can be discounted, and marks it
consumed via atomic rename (so two sessions racing in one directory cannot both claim it).
Injected exactly once, then inert. Codex/OpenCode sessions have no SessionStart hook: there
the load path is `sd-handoff --show` (prints and consumes the packet), and the rendered `sd-plan`
skill reads a pending packet when reattaching. `clear` is the load-bearing matcher — it is the deliberate
kill-and-restart gesture, and a packet reaching it is seconds old; `startup` is where the age
stamp earns its keep.

*Why this is not the journals coming back.* The journals were unconditional, continuous,
committed, and unbounded — 389 `chore: record journal` commits and ~16 KB injected every session.
This is written only on an explicit `sd-handoff`, stored outside the repo, capped at 8 KB,
consumed once, expired at 14 days, one file per directory (a new packet overwrites the old — last writer wins, which is the right
semantics: a superseded packet is stale by definition; the atomic rename protects the *read*),
and free when absent. **But it is
honestly a doctrine reversal**: r7 listed "handoff packet files" and "SessionEnd hooks" under
deliberately-not-built, and the gate section said nothing runs on SessionStart. That carve-out is
now explicit rather than eroded silently. What stays banned: no SessionEnd or PreCompact hook
writes a packet — writing stays an explicit act, because auto-writing every session is exactly
how the journals started.

*The gesture is two steps, and cannot be one.* `sd-handoff` then `/clear` — the SessionStart
`clear` matcher then restores into the fresh session in the same directory. Writing cannot be
automated away: a hook is a subprocess with no access to the conversation, so it can snapshot
mechanical facts (branch, head, changed files) but can never produce `summary`, `next`, or
`dont`. Those need the model, which means an explicit `sd-handoff` call. That constraint is
convenient — it is also the thing keeping this from becoming an automatic journal.

*Known gap, named not papered over:* a session that dies without anyone running `sd-handoff`
(surprise auto-compact, crash) leaves no packet, and for the reason above no hook can fully close
it. A PreCompact hook could at most stash the mechanical half; deliberately not built — revisit
only if the manual flow measurably fails.

*Deletion criterion (standing rule 1).* Incident: context-compromised sessions requiring restart,
user-reported 2026-08-29. Criterion: if after 60 days fewer than 5 packets have been auto-loaded,
or the median packet age at load exceeds 7 days (meaning it is not serving live restarts), delete
the hook; `sd-handoff --show` stays as the manual load path (no 13th verb).

**Lane B — git carrier branch (`sd-handoff --push`, opt-in).** The r7 design, retained for the
cross-machine and cross-tool cases and no longer the default. The work item is the artifact:
`## Log` entry, WIP commit on the `branch:` carrier, restart one-liner; `sd-status` lists
resumable branches derived live from origin. Guest-mode items ride the fork's integration branch
(T1-g). Cross-tool resumption needs no machinery — D1's render makes a Claude handoff resumable
from codex/opencode (and Antigravity once P1 passes). `sd-ship` merges with explicit `-t`/`-b` so
`wip:` subjects never reach main; sd-status flags the two merge-settings gaps.

**CI exposure of Lane B (R10-D2, measured 2026-08-29).** Surveyed all 9 repos carrying workflows:
every `push:` trigger is scoped to `main`/`master`, so a `wip:` push to a carrier branch with **no
open PR fires nothing**. When a PR is already open it is not free: all 18 `pull_request` triggers
include `synchronize` (explicit in 10, default in 8), and only 3 workflows guard on
`pull_request.draft`. So `--push`, on finding an open PR for the carrier branch, converts it to
draft before pushing, **suppresses the Copilot re-request** (the once-per-head rule would
otherwise fire on the moved head — a real gap in the r7 design), and says CI will run. No repo's
CI config is edited to accommodate this (P6). Lane A sidesteps all of it.

### Work modes + OSS participation

Per-repo `mode:` in local config: `full` (own repos), `minimal` (shared: advisory lint, no
auto-Copilot, no thread replies, no archive sweep), `guest` (OSS: zero artifacts in their tree —
triad lives on the fork's integration branch; commit/PR style derived from their conventions;
framework never posts reviews/labels there). Fork-first: patch stack on long-lived fork branch,
local use from the fork, upstreaming = cherry-pick onto clean branch cut from upstream/main;
divergence tracked in the local store + dashboard, never in their tree. Prototyping = prd-only
profile, relaxed lint; research = sd-research/brief flows (renamed from se-*) with findings in
the vault/store.

### Model economics (r8/r8b)

Codex subscription, ranked uses: (1) default second-model planning review in sd-plan (deletes both
planning-adversarial-review prose contracts); (2) parallel review provider (already enabled;
gains planning scope + rate-limit visibility); (3) backlog burn-down via
`sd-ship --backlog --agent codex` (R10-D1 — a flag on the existing loop, not a README recipe); (4) manual `/codex:rescue`; (5) stop-gate stays off. Local models: **exo**
only runtime (R8-D10 revised, user 2026-08-29 — llama.cpp not in use); step zero = OpenRouter spend export — under ~$20/month the
verdict is "local saves trivial dollars; experiment only"; gito swap gated behind 30-min smoke +
1-hour severity-floor probe. claude-mem summarizer stays on subscription until quota pressure.
Engaged subscriptions: Antigravity (after V1′/V2′ + P2, r9b), HF + you.com (research sources), Jira MCP (tracker
mapping), Notion (opt-in publish mirror only). NO GOOD USE: Slack (framework), HeyGen (framework),
Groq/DeepInfra/MiniMax (retire keys after V4 enumeration), Baseten dedicated endpoints, Bedrock
token (V4 first). **OmniRoute removed entirely (R11-D2, user 2026-08-29)**: no backend row,
no config key, no leave-alone entry; residue is user-owned removal, listed under M3.

**R11-D3 (user, 2026-08-29) — protection is enforced where it can be, and the doctrine says so.**
The merge-authority claim was audited against the live GitHub config rather than against the prose
that asserted it. Result across the 24 non-archived platypeeps repos and the 5 active personal ones:

- **10 platypeeps repos carry branch protection**; three of them exempted admins
  (`sd-ai-command-pack`, `sd-github-review`, `sd-review-control-plane`). `enforce_admins` was
  **enabled on all three**; all 10 now read `enforce_admins: true`. This reverses the explicit
  earlier decision in `docs/work/archive/2026-07/2026-07-09-main-push-server-side-guard/design.md`
  ("Do not enable `enforce_admins`") and the same-day enable/disable recorded in
  `docs/work/archive/2026-07/2026-07-03-chore-push-scope-guard/prd.md`. The incident forcing the reversal: a docs-only commit
  was pushed straight to `main` of this repo on 2026-08-29 in violation of its own CONTRIBUTING,
  and nothing server-side stopped it — an admin exemption for the only account that merges is not
  a safety valve, it is the absence of the gate.
- **13 platypeeps repos have no protection at all**, and protection is deliberately **not** added
  to them, because for each the cost is real and the benefit is not: `system`, `sven-delmas-vault`,
  `sd-writing-pack`, and `sdelmas-llm-wiki` take direct pushes from cron/launchd writers (100
  commits / 0 merge commits in 60 days each — a PR requirement would break the ~30 launchd jobs and
  15 vault routines that D-doctrine says stay system-owned); `www_platypeeps_com`,
  `copper-hugo-platypeeps`, `godocs-hugo-platypeeps`, `doc_platypeeps_com`, `company`, and
  `company-public` are dormant (last commit 2022–2025); `sd-github-review-pilot` and
  `sd-review-test` are retired at step 4; `testme` has no default branch.
  `platypeeps/google_workspace_mcp` was left as the one open call — the amendment at the end
  of this record resolves it and corrects the reason it was open.
- **All 5 active personal `sdelmas/*` repos are forks** (Trellis, prism, marketplace,
  google_workspace_mcp, SREGym). Fork-first doctrine governs: a fork's `main` tracks upstream and
  the patch stack lives on integration branches, so protecting it would fight the flow it exists
  to serve. No protection added.
- **No employer/mezmo repo was read or touched** (D7 freeze; collaborators never affected).

Consequence for the prose, and the reason this is a decision and not a chore: the doctrine is now
stated conditionally everywhere it appears (critique 4, the gates section, the autonomous lane, prd
requirement 2, this repo's CONTRIBUTING). "Merge authority is branch protection" is true only while
protection enforces; where it does not, `sd-status` reports the gap (folded into the step-3b brief)
and no document claims a guarantee the config does not provide.

**R11-D3 amendment (user, 2026-08-31) — `platypeeps/google_workspace_mcp` stays unprotected,
deliberately; and the activity number that made it an open call was wrong.**

The user's answer is *deliberate*: no protection. Recorded here rather than left as an open call,
so nothing later reads the absence as an oversight and adds it.

The original record justified leaving it open with "active PR flow (41 merges/60d)". That figure
does not reproduce and the shape it implied is not the shape of this repo. Measured 2026-08-31:

| Claimed | Measured |
|---|---|
| 41 merges / 60d, read as this repo's PR flow | 62 merge commits / 60d on `main`, but **4 pull requests in the repo's entire history**, 2 of them merged in that window |
| — | 154 commits / 60d, **117 of them authored by the upstream maintainer** |
| — | `fork: false`, no parent — a detached copy, 200 behind and 5 ahead of `taylorwilsdon/google_workspace_mcp` |

So the merge commits are upstream history arriving, not review happening. The repo is a vendored
copy of somebody else's project that tracks upstream by pushing merges to `main` directly, with
five local commits of our own on top. That is fork-first doctrine in substance even though GitHub
does not label it a fork, and it lands in the same bucket as the five `sdelmas/*` forks in the
bullet below: a required-PR gate on `main` would block the upstream sync, which is the one thing
`main` is for here.

Two things this amendment is careful not to claim. It does **not** say protection would be
harmful in general — it says it would break *this* flow, which is the only argument standing
rule 1 accepts for a gap. And the honest consequence under R11-D3's own doctrine still applies:
**nothing enforces merge authority in this repo**, and `sd-status` reports that gap rather than
implying safety. The decision is to accept the gap knowingly, not to deny it exists.

How the wrong number got in: 60 days of merge commits were counted on `main` and read as pull
requests, without checking who authored them or asking GitHub how many pull requests the repo has
ever had. Both checks are one API call. The lesson generalizes past this row — a merge count is
not a review count in any repo that syncs an upstream.

### Autonomous backlog lane — `sd-ship --backlog --agent codex` (R10-D1)

The r8 codex burn-down was a README recipe; recipes that need to be remembered do not get run.
It becomes one worker choice on the loop that already exists, so `--backlog` keeps its meaning
(select ready items) and only *who does the work* and the terminal state change: `claude` lands
the PR, `codex` stops at a draft PR.

```
sd-ship --backlog [--agent claude|codex] [--jobs N] [--cap N] [--dry-run]
```

`--agent claude` (default) = today's behaviour, this session works items serially.
`--agent codex` = each item runs as a non-interactive `codex exec --sandbox workspace-write`
in its own fresh worktree. `--jobs` sets concurrent worktrees (default 1, hard ceiling 3);
`--cap` bounds items per invocation (default 3) against subscription quota. `--dry-run` prints
the selected items, their worktree paths, and the resolved budget, and exits.

Per item: select next ready item (acceptance criteria present, no open BLOCKING) → `git worktree
add` off `origin/main` at the item's `branch:` → prompt built **from the item's own artifacts**
(prd + design + implement + `## Log` tail — the same context a reattaching session reads, no
bespoke prompt file) → run under a wall-clock budget → `sd-check` in the worktree → green opens a
**draft** PR carrying the `Work:` line; red, timeout, or rate-limit appends a `handoff:` entry to
`## Log` and leaves the worktree standing for inspection.

Bounds, each mapping to an existing doctrine rather than new policy:
- **Never merges, never marks ready-for-review.** Merge authority stays GitHub branch protection
  where it is enforcing (critique 4) — and the lane's refusal to merge does not depend on that:
  it never merges even in a repo with no protection at all, which is exactly the repo where the
  distinction matters; the lane produces reviewable drafts and nothing else. Settling is a human running
  `sd-ship --pr N`. Draft status also makes route() plan the cheap tier, so the lane does not
  spend review budget on work nobody has looked at yet.
- **One writer per checkout** (Parallelism rule 1) — worktree isolation is the mechanism, and
  `--jobs` is capped because the merge lane is serial regardless.
- **No silent death** (Parallelism rule 4) — every item gets an explicit wall-clock budget;
  exceeding it is a reported failure with a `## Log` entry, never a silent skip.
- **Rate-limited ≠ unavailable** (r8) — a quota stop ends the run cleanly with the remaining
  items untouched and named; it does not retry-thrash or fall through to another provider.
- `--agent` is the extension point: a future `kimi` worker is a row, not a new flag.

Incident + deletion criterion (standing rule 1): the incident is the measured backlog — 217 open
item directories in the 7 platypeeps repos re-counted 2026-08-29 (~306 fleet-wide at r1), 2% of PRs ending in a `feat` commit. Criterion: if 60 days after
it lands fewer than 5 items have reached a merged PR through `--agent codex`, delete the flag and
keep the plain loop.

Aging (folds in the intake half): `sd-plan`'s existing archive sweep also parks any item sitting
in `planning` past 45 days with no `branch:`, so the backlog drains whether or not a worker runs.
Parked items keep their directory under `archive/YYYY-MM/` and are recoverable by `git mv`. **Parked ≠ hidden (user, 2026-08-29):** the sweep writes `parked: <date> age-sweep` into the item's frontmatter; `sd-status --parked` and the dashboard Work tab's *Parked* filter list them (derived from that field, never a separate ledger); each sweep prints the items it parked. Threshold 45 days confirmed.

### Google Workspace, multi-account (r9, rev 2 — full addendum: scratchpad r9/04.md)

**Grounding (verified 2026-08-29).** workspace-mcp is the multi-account backbone: launchd service
on :8083, per-call `user_google_email` with no silent fallback; 3 token files in
`~/.google_workspace_mcp/credentials/`. Account choice today is three ad-hoc mechanisms (sdw
config `google_account`, hardcoded email in aaif-brief-compile SKILL.md:82, notify.sh
`EMAIL_FROM`). claude.ai Gmail/Calendar/Drive connectors are single-account, account-opaque.
**The recipient send-guard was dead at review time** — its matcher named retired
`mcp__gmail__send_email` while live `send_gmail_message` fell through (fixed day-0, see
Enforcement below).

**Account model — one resolution home.** `config.json` `google.accounts` map: alias → {email,
roles}; `personal` (mail_send) + `work` (drive_write); **no default account** — every caller
names an alias. Resolution: `--account` flag → plugin/repo config (`sd config get
sdw.google_account` returns an alias; local block may set `google_account:`) → interactive ask →
headless **refuse**. Roles = closed 2-key vocabulary, each with a mechanical consumer:
`mail_send` (guard-enforced), `drive_write` (advisory + sdw's existing folder-identity check).
Read roles rejected as theater. Drive folder IDs live beside their owning alias (composite fact).
Egress rule: `work` reads may summarize into vault/Notion briefs; `work` writes = exactly the sdw
Drafts/Published loop; nothing sends as `work`.

**Enforcement — day-0 — EXECUTED 2026-08-29** (guard rewritten and keyed on `tool_name`, matcher retargeted to the 4 live send paths, `--tools gmail drive calendar` live — roster 33 tools: gmail 12 / drive 12 / calendar 7, `import_to_google_sheets|slides` kept as Drive-owned; 3 dead `mcp__gmail__*` grants deleted; `config.json` `google.accounts` created; backups `*.pre-r9`). Remaining for steps 9/10: sd-writing-pack's stale names, `~/.claude.json` `disabledMcpServers: ["gmail"]`, aaif guard's dead alternation. **Original design:** retarget + extend
existing `gmail-send-guard.py` (~15 lines, incident lineage in its docstring — not a new hook):
matcher → live `send_gmail_message` + claude.ai connector send/reply/forward (fail-closed);
sender branch denies unmapped `user_google_email`, alias without `mail_send`, or mismatched
`from_email`. Plus one env-line narrowing: `WORKSPACE_MCP_EXTRA_ARGS="--tools gmail drive
calendar"` — Chat/Apps Script/Sheets/Tasks/Forms stop being served at all (R9-D7; re-adding a
service = decision record).

**Lanes:** sdw Drive review loop (plugin-side, alias `work`, steps 9/10 retarget) · research
reads (per-flow alias) · calendar = interactive read lane (~9 sd-* research flows, ask-the-user
resolution, never automated) · Drive publish mirror deferred until first real request ·
sd-status `workspace auth` line = **live probe per alias** (token-file inspection can't see
refresh-token death) · vault routines untouched.

**Single write path doctrine:** workspace-mcp is the only Google write path. Connectors =
interactive conveniences; no installed skill/routine/command may name `mcp__claude_ai_Gmail|
Google_*` tools (sd-skill-adopt pre-screen flags them + `mcp__gmail__*` ghosts); connector sends
guard-denied in hooked sessions. One credential silo; `~/.gemini`, connector bindings
join the leave-alone list.

**Not built:** no backbone email automation, no calendar machinery, no Sheets ledgers, no Apps
Script (unserved), no Drive-write hook without incident, no new Workspace hooks (R10-D3's
SessionStart hook is outside this section).

**Amendments:** day-0 guard+env change · `google.accounts` schema · step 9 extended
(aaif-brief-compile alias lookup; delete dead `mcp__gmail__*` grants + both `disabledMcpServers:
["gmail"]` blocks) · step 10 extended (sdw stale tool names in SKILL.md:26,29 + settings +
permissions.md; folder IDs into composite block) · notify.sh raw-curl bypass documented.

**Decisions:** R9-D1 **reversed (user, 2026-08-29): keep** the `sven.delmas@gmail.com` token — nothing references it, but it stays; joins the leave-alone list · R9-D2
2-key roles · R9-D3 day-0 guard extension · R9-D4 Drive mirror deferred · R9-D5 live-probe auth
line · R9-D6 connector doctrine · R9-D7 served set = gmail/drive/calendar.

**Verification (V-G1..G8):** zero `mcp__gmail__` refs post-migration (incl. `~/.claude.json`
`"gmail"` grep) · addresses in skills prose = 0 (resolution-home invariant; machine-wide zero not
claimed) · hooked-session deny dry-runs (bad recipient / work-alias send / unmapped sender / connector
send, draftId, replyAll) — **18-case matrix green 2026-08-29**; the tool has no `from_email`,
sender identity is `user_google_email` · sdw resolves alias via `sd config`, `config.json` file deleted · credentials dir
matches map exactly (2 files) · service.env names checked (never values) · token-aside +
revoked-grant probe flags · Apps Script/Chat tools absent from served roster. All eight attacks
accepted (1 blocking, 4 major); residual risk named: served-but-unguarded Drive share/trash tools
blocked from unattended use by grant absence, hooked only on real incident.

### Cron / scheduled-job ownership (explicit)

The system repo (`local-cron-jobs`, ~30 launchd jobs) and the vault (`System/Scheduled Tasks`,
15 routines) keep owning all scheduling. **The backbone ships no scheduler and schedules
nothing**: no sd command is cron-run (sd-map never scheduled, lint never scheduled, dashboard
refresher runs only `index`, vault export manual-only). Sole pack-owned LaunchAgent =
`sd-dashboard install`, which at 6b replaces the system dashboard's plist. Only touch to existing
jobs is retargeting ones that call retired machinery (3d skill-proposal-accept, step 9 pack.py
callers, sdw meter retires per R5-D4). Repos retain full ownership of their own cron/CI
schedules — the framework never registers, edits, or removes repo automation.

Generalized (user-confirmed 2026-08-29): **system views stay system-owned and plug into the
framework dashboard** via plugin tabs declared in a registered manifest — **five of them: Toolbox,
Briefs, Vault, Research, and Ports** (R11-D12 gave Ports its own tab). This record said "Jira
personal" for a year of drafts and there is no such tab: the system dashboard's fifteen tabs,
enumerated from `dashboard.py` rather than from this list, are `attention work projects research
repos issues areas toolbox briefs ports` plus five `db-*`, and Jira appears only *inside* `issues`,
which R3-D13 already migrates to the backbone and which `dashboard/jira.py` already serves. A
plugin tab that does not exist cannot be ported, and a phantom in the count is one more tab 6b-3
would have gone looking for — code + pinned actions live in `~/repos/system`. Only the
dashboard shell + framework-native facts fold into the backbone; Issues is the one migrating view
(r3 tracker mapping, R3-D13). Repo packs contribute via the r5 manifest tile contract.

Cron visibility (r9c, verified): the cron view **already exists** — dashboard.py
`collect_toolbox()` parses `launchctl list` for `com.sven.*` (PID, last exit), job schedules,
last-run/log-age, `next_run`, failures.log tail. It ports as the Toolbox **plugin tab** in the
3c→6b parity checklist — no new build. Failure surfacing stays system-owned, three existing
channels: `cron-jobs.sh notify_failure()` (banner + failures.log + ntfy on rc≠0), `watchdog-daily`
(stale-log detection → email+ntfy — the only catch for silent non-firing), dashboard tab (pull).
Named gaps carried honestly, not fixed by the backbone: rc=0 degraded runs (vault routines that
report errors in-note and exit 0), lock-skip silence, powered-off missed slots, non-cron
LaunchAgents outside notification entirely. If any gap graduates to an incident, the fix lands in
`local-cron-jobs` (system-side), never as backbone machinery.

### Environment preferences (user, 2026-08-29)

`config.json` gains a small `env` object — preferences, not machinery:
- `editor = "zed"` — sd-handoff's printed restart one-liner uses it (`zed <worktree>` instead of
  `$EDITOR prd.md`); dashboard "open" links use the `zed://file/<path>[:line]` URL scheme.
- `browser = "chrome"` — dashboard/PWA and PR links open in Chrome; matches the existing
  claude-in-chrome automation lane. No new integration built for either; both are single config
  reads wherever a command prints an open/edit hint.

### Google AI lane = Antigravity (r9b; Gemini CLI EOL)

Verified: Gemini CLI stopped serving Pro/Ultra/free accounts 2026-06-18; `which gemini` fails on
this machine; successor `agy` 1.1.22 installed, authenticated, first-class headless
(`agy -p --output-format json --json-schema`, exit codes). Consequences:
- **R9b-D1** `~/.gemini/commands/sd` TOML renderer deleted (no consumer). Antigravity skill format
  is byte-identical Claude SKILL.md → install.py renders verbatim copies (~30 LOC), but only after
  **probe P1** resolves which of three candidate skill roots `agy` actually loads
  (`~/.gemini/antigravity-cli/skills/` per docs, vs `~/.gemini/config/`, vs `~/.gemini/skills/`);
  until P1 passes: zero-render, AGENTS.md-native support only. Parity test: count = 12 or 0, never
  partial.
- **R9b-D2** review backend row `gemini` → `antigravity` (see backend table). V1 auth-flip is
  obsolete (agy is OAuth-native); V1′ = verify paid sub on the `google_accounts.json` active
  account (names only). V2′ = training opt-out via Gemini Apps Activity (forum-sourced, medium
  confidence — recorded as such). V3′ = plan-wide 5h-refresh quota treated as one shared budget;
  silent model-downgrade runs flagged degraded. **P2 gate** before wiring: non-TTY stdout smoke;
  fail → try pty wrapper → else delete the row (diversity from codex/kimi/local instead).
- **R9b-D3** step P1 (the platform sweep, renamed from `3a` on 2026-08-30):
  delete 19 gemini TOMLs, re-render 0 (`test ! -e ~/.gemini/commands/sd`);
  OpenCode delete 19 / render 12; also sweep the three candidate skill roots for auto-converted
  `sd-*` residue (expect 0).
- **R9b-D4** R2-D22 reversed: Antigravity **supported** (backend + probe-gated render). N5
  local-config gemini row deleted, not re-gated — Antigravity has no untracked-file import; joins
  Codex/Copilot out-of-N5 list.
- **R9b-D5** account-switching hazard: Antigravity active account can change silently → config
  records expected account name; review-lane preflight compares names (never values) and refuses
  on mismatch. Feeds the r9 multi-account model.
- **R9b-D6** residue: verify Antigravity ignores `~/.gemini/settings.json` hook stanzas
  (Gemini-CLI-era, likely orphaned) and retire them via owning installers; fix system repo's
  "Antigravity has no CLI" comment (false); after this addendum, `grep -rn 'which gemini\|gemini
  CLI\|commands/sd (TOML)'` over the plan = 0.

### Issue-tracker mapping (r3)

`trackers.github`: 4 GraphQL `involves:@me` searches unioned with `why[]`, watermark+1h overlap.
`trackers.jira`: ~90 LOC lifted from dashboard.py (`jira_search`/`jira_me`/`collect_jira`).
Per-repo attribution in config; rows to the index; Dashboard Issues tab + "Needs you"; `sd-plan
--from gh:...|jira:...` seeds `## References`.

### Rollout (r4 — the friction point, in detail)

Steady state = four surfaces, one command each: **update** `install.py --user --pull`;
**new machine** `git clone && install.py --user`; **adopt repo** `cd repo && sd-plan <slug>`
(consent on first run; in-tree writes = `<work>/` only); **migrate consumer**
`migrate-trellis --consumer` → one PR (run-time reference enumeration, never pre-baked lists) —
stated plainly: every existing consumer gets exactly one *removal* PR (M2); that is the only
non-local touch the rollout makes, and it deletes footprint rather than adding any.
Update discovery: throttled fetch + one banner line; advisory, never auto-runs. This machine
migrates via M0–M3: **M0** tombstone plugin 0.72.0 (last legacy release — the only reach-back
signal a second machine can ever get); **M1** `--adopt-legacy` (receipt-driven: overwrite the 10
colliding renders, delete 28 successor-less ones); **M2** consumer PRs with both stacks coexisting
(disjoint namespaces, mutual refusal with pointers); **M3** receipt-driven machine cleanup
(underscore-safe; deletes **only the legacy subdirs by name** — `work-loops/`, `fleet-timing/`,
`fleet-campaigns/`, `machine/` — under the state root, plus cache + plugin rows; **never**
`handoff/` or `intents/`, which share that root; D7 freeze for mezmo_benchmark). **OmniRoute residue (R11-D2), user-owned, listed not
automated:** `~/repos/ai/OmniRoute`, `~/repos/system/local-OmniRoute`,
`~/repos/platypeeps/omniroute-test`, their `~/.claude.json` project entries, and any
OMNIROUTE_* env names in the shell env (names checked, never values); M3 prints the list, deletion
is a manual step.
Serving-root discipline: pack dev in worktrees, serving checkout clean main (D-R4-8).

## Decisions

**Decided in session:** D1 platforms **revised by r9b**: Claude+Codex+OpenCode rendered +
parity-tested; Antigravity AGENTS.md-native now, skill render behind probe P1 (Gemini CLI EOL,
TOML renderer deleted). D2 backlog = bulk-park. D4 = retire router footprint (routing model
survives as opt-in config, r3). D6 = merge all se (re-based to 64+5). R2-D15 Codex out of
local-config v1. R2-D16 Copilot CLI out. R3-D12 local-evidence lowering only in non-opted-in
repos. R6-D12 work-backlog → `sd-ship --backlog`. R9b-D1..D6 (Antigravity lane) as specified in
their section. **R10-D1 (user, 2026-08-29): the codex backlog lane is `sd-ship --backlog
--agent codex`** — flag on the existing loop, draft PRs only, never merges; with the 45-day
planning-age sweep as its intake counterpart. **R10-D2: sd-handoff drafts the PR + suppresses the
Copilot re-request when the carrier branch already has one open.** **R10-D5: rule 5 hard-fails in CI only for listed authors; minimal/guest refuse setup-github.**
**R10-D6: sd-* resolve repo from cwd only; fleet-walk sd-status dropped.** **R10-D7: local block
prepended in pack-invoked codex/antigravity lanes.** **R10-D4: codex lanes are subscription-only — env scrub + `auth_mode == chatgpt` preflight, refuse on
mismatch.** **R10-D3: `sd-handoff`
defaults to a local session packet under `~/.local/state/.../handoff/<digest>.json`,
auto-restored by one SessionStart hook — no git, no CI; `--push` opts into the carrier
branch. Explicit doctrine carve-out to the no-SessionStart rule.** Environment: editor=zed, browser=chrome.
**One prefix (user, 2026-08-29): all
merged se-* skills/agents rename to sd-* at step 5** — single namespace, collision check vs the
11 commands, old se-* renders deleted; retired skills keep historical se- names in records only.

**Proposed defaults — all accepted by user 2026-08-29 (R11-D0), now decided as written; exceptions noted inline:**
- D3 import 386 archived tasks under `docs/work/archive/` · D5 protection: report + opt-in
  `--set-protection` · D7 mezmo_benchmark deferred (freeze shim) · D8 planning checklist = 10
  dimensions via codex lane · D9 journals: give up cross-references
- R2: D12 queue dispositions (Skill Proposals → files, rest keep) · D13 suggestion tracker =
  GitHub issues on pack repo · **D14 phone access (a/b/c — (c) keeps today's PWA writes)** ·
  D17 intents vs immediate commit · D19 Sessions tab + claude-mem · D22 superseded by R9b-D4
  (Antigravity supported)
- R3: D10/D-C1 **decided: JSON** for all pack-owned config/manifests (see storage table) · D13
  system collectors → index · D16 **revised (user, 2026-08-29): pack first, then the other `mode: full` repos in the same initial trial** — pack PR proves the route action green once, then one `setup-github` PR per remaining full-mode platypeeps repo lands in the same step-3-c wave; no prolonged single-repo trial — **revised again (user, 2026-08-30): `setup-github` leaves
  the 3-c wave and becomes step 3-d.** The pairing blocked a removal that was ready on a
  subcommand that is unbuilt (`bin/sd-review:69` is a seam), and it welded an opt-in CI lane
  to the largest deletion PR of the rollout so the two could not be reverted apart. The
  ordering D16 argued for survives inside 3-d: pack first, then one PR per remaining
  full-mode repository, no prolonged single-repo trial · D20 fork/dependabot red-check
- R5: D1 vault SoR · D3 sdw adversarial gate deletes only after round-3 review ships · D7
  two-machine vault: migrate personal machine only
- R6: **D10 claude-mem keep-whole (a)** vs fork-trim (b) · D11 vendor kimi/codex agents then
  uninstall plugins · D13 aura-tui/mezmo conversions as backlog items
- R7: D10 sd-handoff as 12th command (with deletion criterion) · D12 wip auto-push →
  **superseded by R10-D3** (push is opt-in `--push`) · D15 --park semantics (Lane B only) · D16
  guest carrier = fork integration branch
- R8: D10 **decided: exo** is the only local runtime (llama.cpp never in use) · D11 gito local experiment three-gate (expect probe fail) · D13 codex
  default planning provider (cloud-exec trial superseded by R10-D1's local worktree lane) · D14 **decided: OmniRoute removed** (R11-D2)
- R8b: D8b.1 superseded by R9b-D2 (Antigravity V1′/V2′ sequence; no mezmo repos until policy
  check) · D8b.2 Baseten disabled/gap-gated · D8b.4 key retirements after V4 enumeration
- R9: D1 **decided: keep** the unused gmail token (user 2026-08-29) · D2 2-key role vocabulary · **D3 day-0 guard retarget — DONE 2026-08-29** · D4–D7 per
  Workspace section

**R11-D9 (2026-08-30) — a category escalates on one path and lowers only on all of them.**

Found by running step 3's own end-to-end for the first time rather than by review, which is the
whole argument for the check that had been skipped.

`_match_category` matched every category on *any* path, while `docs_skip` required *all* of them.
For a category that lowers the tier the asymmetry is a defect: the built-in `docs` category sits at
`cheap`, below the `standard` default, so a single markdown file in a source change matched it and
took the change down a tier. Measured on the default policy, `['src/greet.py']` planned `standard`
with `[codex, prism]` and `['src/greet.py', 'README.md']` planned `cheap` with `[codex]` — adding
documentation to a change removed a reviewer from it. Because every `sd-plan` work item lives under
`docs/work/`, that is the shape of nearly every change made through this framework: it was
systematically under-routing the changes it exists to govern, and printing a plan that said so.

The rule is now one sentence, stated by direction: a category that holds or raises the tier matches
on any path; one that lowers it matches only when every path is in it. Escalating on one path is the
safe direction — the worst it costs is a review nobody needed, whereas lowering on one path costs
a review someone did. `required` still controls ordering only, so "touches the installer outranks is
mostly documentation" is unchanged; the phrase "is mostly documentation" now has to mean mostly.

Why no test caught it, which is the part worth carrying forward: the one mixed-path fixture pairs
`docs/guide.md` with `installer/registry.py` and passes because the fixture policy's **required**
`installer` category rescues the mix. It proved required-first ordering and was read as proving
any/all semantics. The default policy has no required category, so the mixed case was uncovered
entirely. A fixture that passes for a different reason than the one you have in mind is worse than
no fixture, because it answers the question you meant to ask with a yes.

Observed in the wild, not only in a fixture. The six routed pull requests of the 3-d wave all
touch `.github/workflows/**`, a sensitive path that escalates a tier. Five printed `tier deep`.
`hoa-manager#300` printed `tier standard` — its diff also carried a documentation file, which
matched the `docs` category on one path and took the change down a tier before the sensitive-path
escalation put it back up one. That is the defect, in the wave that was being used to prove the
lane, visible in the check output the whole time and read by nobody until the figure was checked
against the other five.

Landed in #620, proven to bite by reintroducing the defect: `AssertionError: 'cheap' != 'standard'
: category docs starts at tier cheap`. Blast radius named honestly: the six installed consumer
lanes are report-only and pin an older commit, so nothing was mis-gated — the cost was a wrong
plan printed, not a missed review.

**R11-D8 (2026-08-30) — the review lane's sub-cap is 1,700, and the guard now measures the lane.**

Raised in a change that does not need the room, which is the only honest time to raise a cap.
The 1,400 sub-cap was set before `setup-github` was designed, and the itemization above never
budgeted the installer on a line of its own: it was assumed to fit inside the review lane's
share. It does not. `bin/sd-review` is 1,367 lines and `bin/sd_setup_github.py` is 294, so the
lane is **1,661** against a 1,400 budget.

The reason this was invisible is the defect worth recording. The guard was
`test_the_review_lane_stays_under_its_sub_cap`, and it measured `bin/sd-review` — one file,
while naming a lane. So when step 3-d split the installer into its own module, the number fell
from 1,589 to 1,367 and the guard went green on a lane that had grown by 294 lines. The split
was right for its own reason — `tests/test_sd_review_boundary.py` proves `bin/sd-review` never
writes and never posts by reading that file structurally, and an installer inside it would have
made the proof unprovable — but a cap you can duck by adding a second file is not a cap.

Two things therefore change together, and the order matters: the guard is corrected first to
enumerate the lane from the import graph (`bin/sd-review` plus every `bin/` module it imports
that is not shared core), and *then* the number is set to what the corrected guard measures plus
room for one more small module. Setting 1,700 while the guard still read one file would have
been a number with nothing behind it.

Two neighbouring guards were wrong in the same way and are fixed in the same change, since the
fault is one habit rather than three bugs:

- `test_bin_stays_under_its_ceiling` summed **every** file in `bin/`, including
  `bin/migrate-trellis`. The paragraph above places `migrate-*` outside the ceiling with its own
  1,500 budget, so the migration tool was spending 1,250 lines of the backbone's 8,000. Excluding
  it moves the measured total from 7,526 to **6,276** — and that slack is real rather than
  invented, which matters because the next two commands (`sd-spec`, `sd-map`) would otherwise
  have busted a ceiling they were always inside.
- `migrate-*`'s own 1,500 ceiling was promised here and **had no test at all**. It has one now;
  `bin/migrate-trellis` is 1,250.

Parked, with a trigger rather than a date: the core line above reads ~1,800 for eight commands,
and the ones that exist already total 2,811 (2,776 until #620) — `bin/sd-status` alone is 978. The itemization is
stale, not the ceiling, and re-deriving it against a half-built `bin/` would replace one estimate
with another. Trigger: the next command to land under `bin/` re-derives the core line from the
files that exist, with the same enumerate-then-assert shape used here. Owner: whoever lands it.

**R11-D16 (2026-08-31) — the tile's output shape is written down, a plugin that goes dark
becomes a row, and the dashboard cap is on the same trajectory `bin/` was.**

6b-2 is the plugin loader. Three things came out of building it, and only the first was expected.

**One. The tile contract named a budget but never a payload.** `dashboard.tile` is specified
throughout this document as a command under 5s and 64KB, and nowhere as a command that returns
anything in particular. A budget is not an interface: the system repo cannot write a tab against
"under 64KB". So the shape is fixed here, and it is the smallest one that carries what R11-D12
requires:

The manifest names the tabs; the loader runs the tile **once per name**, passing the name as its
argument, and each call answers for that one tab:

```json
// sd-plugin.json
{"dashboard": {"tile": "./bin/dashboard-tile", "tabs": ["toolbox", "ports", "areas"]}}

// `./bin/dashboard-tile toolbox` prints:
{"title": "Toolbox", "html": "<table>…</table>", "rows": [{"rank": 0, "kind": "cron-exit",
 "id": "com.sven.x", "what": "job failed", "detail": "rc=2"}]}
```

**Per-tab invocation is forced by the budget, and it took a measurement to see it.** The first
draft of this record fixed the payload at a single tab per plugin. Starting 6b-3 against it found
that a repository has one manifest and therefore one `dashboard.tile`, while `~/repos/system` owns
**five** of the views being folded in — so the payload was changed to carry a list of tabs. That
was still wrong, and only timing the real collectors showed why:

| collector | seconds | data |
|---|---|---|
| `collect_toolbox` | 3.78 | 17.0 KB |
| `collect_ports` | 2.84 | 1.7 KB |
| `collect_areas` | 0.03 | 2.2 KB |
| `collect_briefs` | 0.01 | 28.8 KB |
| `collect_jira` | 0.00 | 0.1 KB |
| **sum** | **6.66** | **49.8 KB** |

Every one fits a 5s budget. Run in sequence behind a single command, Toolbox and Ports alone spend
6.62s and the tile is killed on **every** load, permanently — a dashboard that never once showed a
system tab, with the budget doing exactly what it was told. The 49.8 KB is collector data and not
rendered markup, so the 64 KB half is likely breached too; that is stated as likely rather than
measured, because only the seconds were timed.

Three consequences, and the third is why this is the right shape rather than a bigger number:

- **The budget keeps meaning one thing.** 5s per tab is the same promise whether a plugin serves
  one tab or twelve. A per-tile budget scaled to tab count is a number nobody can reason about,
  and it gets revisited the moment a sixth tab lands.
- **Failure is per tab.** `collect_toolbox` at 3.78s can no longer starve the four tabs that cost
  nothing between them. This is the same rule the loader already applies to rows and to tabs one
  level out; making the *process* per tab is what completes it rather than an addition to it.
- **Tabs run concurrently**, bounded at four workers, so wall clock is the slowest tab and not the
  sum. A plugin declaring thirty tabs does not get to decide how many processes the dashboard
  starts.

`dashboard.tabs` is validated at registration, not at load: a name must match
`^[a-z][a-z0-9-]{0,31}$` — it reaches the tile as a command-line argument, and a name with a
leading dash would arrive as a flag — and a repeated name is refused there, since two tabs under
one name is a tab nobody can reach. A `tile` with no `tabs` is refused for the same reason it
would be useless: the loader has nothing to ask for.

`title` is **optional** and renames only what the operator sees; the declared name is the identity
and the fallback. `html` is markup rendered into that tab. `rows` is R11-D12's optional key,
unchanged in field names from the `add()` calls it replaces, and each row is stamped
`<prefix>/<name>` so several tabs behind one prefix are several sources.

`rank` must be a non-negative integer. Rank 0 is the top of the view *and* where the loader writes
the row saying a tab has gone dark, so a row above it would let a plugin sort the notice of its own
failure underneath its own rows — the outcome the failure row exists to prevent. Found in review.

A plugin that registers for its `kinds` and declares no tile at all is working, and is deliberately
not reported as a failure.

**`html` is markup and `rows` are data, and the split is the trust boundary.** A tile has always
rendered arbitrary markup into its own tab — R11-D12 said so when it noted that placement, not
privilege, is what changes when a plugin reaches Now. Rows go into the backbone's most prominent
view, so they are typed fields rendered as text, never markup, and they carry no destination at
all: R11-D19 removed the `href` this paragraph once confined to an in-page anchor, and the
backbone resolves a row's panel from `source` instead. A row cannot navigate the operator
anywhere.

**Two. The loader must make its own failure loud, and this is an addition to R11-D12.** That
record established that three plugin-bound sources own every rank-0 and rank-1 alert the view can
emit. The consequence it did not draw: if the loader treats a failed tile as "no rows", then a
plugin crashing looks exactly like a plugin with nothing to report, and Now renders calm while
cron is on fire. That is the same failure R11-D12 caught in the tile-only design, one layer down.

So every way a tab can fail — non-zero, timed out, oversized, unparseable, or emitting a title,
markup or row the contract refuses — produces a **rank-0 row written by the loader**, naming the
tab and the reason. Silence is not an available outcome. Refusal is per item at every level: a bad
row loses that row, a bad tab loses that tab, a failed invocation loses that one tab and not its
siblings, and each gets its own rank-0 row. The registry itself failing to read is a rank-0 row
too, and it is the only one with no plugin to name.

Both bounds are enforced **while reading**, not checked afterwards. A 64KB limit applied to output
already in memory is a limit on what gets rendered, not on what a plugin can make the dashboard
allocate; and the deadline kills the tile's process group rather than the command it named, or a
tile that backgrounds work outlives the timeout and goes on holding the pipe. Both are tested
against a real subprocess, because neither survives being mocked.

**Read, not coerced.** `root` and `prefix` were passed through `str()` before being checked for
emptiness, so a corrupt registry entry with `"root": 7` became the non-empty string `"7"` — passing
the check and leaving `Path("7")` as a relative working directory the plugin never named. Coercion
that turns an invalid value into a plausible one is the quiet failure wearing a different hat: the
check is now for the type the contract states, not for something that can be spelled as text. Found
in review.

**The four-worker ceiling is machine-wide, and it is worth knowing why.** Raised in review as
`TAB_WORKERS * plugins`, since the pool is created per plugin. It is not, because `load` reads
plugins serially and `cached_load` allows one load at a time — so four is the real ceiling on
concurrent tiles. It is also incidental rather than enforced: the day plugin reading is
parallelised the ceiling multiplies, which is recorded beside the constant rather than pre-empted
with a semaphore for a code path that does not exist.

**One fan-out at a time, and not repeated for callers arriving together.** The server is threaded,
so `/api/plugins` started a fresh fan-out of tile subprocesses on every request: a page refreshing
quickly, or two of them, multiplied the tiles by the number of readers, and the module that exists
to bound one plugin's cost had no bound on its own. A lock makes concurrent callers wait on one
load, and a five-second window keeps a refresh loop from re-running tiles that answered a moment
ago. Deliberately not the state cache's twenty seconds — a plugin row is what an operator is
watching change. Found in review.

**The loader validates the tab names it is handed, even though registration already did.** A name
arrives at the tile as a command-line argument, so `--anything` would arrive as a flag, and a name
declared twice would invoke the same tab twice and produce two identical dark rows. Both are
refused at load, each as a tab that says why it was never invoked rather than one that quietly
vanishes. This is a second copy of the registration rule, and it is deliberate: the loader trusts
no payload it did not write, including one from the pack's own CLI. Found in review, along with the
`cannot run` message, which now names the working directory — "no such file or directory" for a
tile that exists says nothing until you know which directory it was looked for in.

**The registry read has no plugin above it, so it carries the net itself.** `select` and `os.read`
raise `OSError` and `InterruptedError` on their own account, outside the module's own `Bounded`
vocabulary. Uncaught in a tab that costs one tab; uncaught in the registry read it costs the whole
view. The same wrapper the per-tab worker got now sits there too. And `readable` is checked against
`True` rather than for truthiness — a registry spelling it `"false"` hands over a string, a string
is truthy, and the loader would have run a tile for a manifest that never parsed. Both found in
review.

**`null` is absent, and it is absent for every optional key alike.** Raised in review as a possible
quiet loss on `{"rows": null}`. It is not one: a tile spelling "nothing to show" as `null` rather
than by omission has lost nothing, and complaining about one spelling while accepting the other for
`title` and `html` would be a rule about JSON style rather than about what reached the operator.
Kept, pinned by a test, and stated here so it is a decision rather than a coincidence of `.get`.

The registry's own row stopped saying "unreadable" in the same pass: the registry now also reports
entries it had to drop, so a perfectly readable registry can fail there, and a row naming the wrong
failure misdirects whoever reads it.

**An entry the loader cannot identify is not one it may run.** A registry entry with an empty root
would have resolved to `Path("")` — the dashboard's own working directory — so a plugin's tile would
have run somewhere its plugin never asked for, and an empty prefix stamps every row of every tab as
`/<name>`. Refused, which is the answer the rest of this module gives to a payload it cannot trust.
Found in review.

**The registry says what it dropped.** Non-object elements in the listing were skipped and success
was reported, so a corrupt registry would lose plugins with nothing said — the same quiet, in the
loader's own reading of its own CLI. The readable entries still come back, because losing the rest
of the fleet to one bad element is the same mistake pointed the other way; what changes is that the
count of what was dropped is now a rank-0 row. Found in review.

**One of the tests could not fail, and that is worth recording.** The process-group kill was checked
by a tile that backgrounds a child which writes a marker after six seconds, with the assertion
reading the marker one and a half seconds later. The marker could not exist either way, so the test
passed whether or not the kill worked — a green check over an unexercised guarantee, which is worse
than no test because it is believed. The child's sleep now sits between the deadline that kills it
and a wait long enough that a survivor would certainly have written. Verified by replacing
`os.killpg` with `proc.kill` and watching it fail. Found in review.

**A tab's failure stays inside that tab, including the failure nobody predicted.** `json.loads`
decodes bytes before it parses them, so output that is not UTF-8 raises `UnicodeDecodeError` —
which is not a `JSONDecodeError` and so missed every guard in the parse path. Raised inside a
worker it surfaced when the pool's results were collected, and one plugin's bad bytes took the
whole load with it: no plugin reporting at all, which is the failure this module exists to prevent
arriving through the mechanism built to prevent it. The decode error is now named, and the worker
is wrapped so that an exception nobody predicted becomes a row naming the tab rather than an empty
dashboard. Catching broadly is usually how errors get hidden; here the alternative is losing every
tab, and the error is reported where an operator sees it. Found in review.

**Printing nothing is not printing `{}`.** Every key in the payload is optional, so `{}` is a
legitimate answer from a tab with nothing to show — and the loader read *silence* as that answer,
handing the view a successful tab that was quiet about its own failure. The same substitution sat
one level up, where an empty read from `sd plugin list --json` became an empty registry, so a
misbehaving CLI looked exactly like a machine with no plugins. Both refuse now. This is the
module's own rule applied to itself: R11-D12's complaint is that a failure indistinguishable from
calm is the failure, and a default supplied for missing output is how that gets reintroduced by
accident. Found in review.

**The deadline covers two failures, and the row says which.** A tile that never wrote and a tile
that wrote and then stopped both hit the same timeout. Calling the second "no stdout" sends whoever
reads the row looking for a tile that never started, so the message names the bytes already in hand.
(Both messages said "output" until R11-D18 gave them a stderr tail to carry; the wording is
corrected there rather than here, since this record is about the split, not the noun.)
The test keeps stdout open, which is what separates this path from the one where a tile closes the
pipe and hangs — that is still `did not exit`. Found in review.

Also raised in review and deliberately not acted on: `select` on a pipe and `os.killpg` do not work
on Windows. Neither does the rest of this pack. It installs LaunchAgents, resolves
`~/.local/state`, shells out to POSIX tools, and its CI is Linux with a macOS leg pending restore
at step 7. A Windows-safe bounded reader here would be portability for one file inside a pack that
has none, and unexercised code paths are how this repository grew the 9,390 unreachable lines the
diagnosis counts. Named so the next reviewer does not have to find it again.

**A dark plugin is named by what the loader actually has.** A manifest that will not read has no
prefix in it, so the first version called every such plugin `?` — and two broken plugins became one
row an operator cannot act on, identical in source, id and text, with no way to see there were two.
The root is available in every case, so the row falls back to it. The same review found the sibling
conflation: `if not tile` treated an empty tile string as no tile declared, which is the one
condition that is deliberately *not* a failure. Absent is now the only spelling of absent, and a
declared-but-empty tile refuses like any other malformed declaration. Both found in review.

**The registry answers to its own budget, not a plugin's.** The loader reads `sd plugin list
--json` through the same bounded reader, and the first implementation borrowed the tile's 64KB for
it — which made the size a registry is allowed to be a function of how much output *one plugin* may
print. A machine registering enough plugins to pass 64KB of listing would have reported a broken
registry on every load, permanently, with nothing wrong with it: the one failure the loader cannot
attribute to a plugin, caused by a constant that has nothing to do with the registry. Separate
ceiling, 1MB, and the test registers enough roots to exceed a tile's. Found in review.

**The exit status is inside the budget, and closing stdout is not exiting.** A tile that prints
good JSON and then fails has failed, so the loader waits for the process within the same deadline
and refuses a non-zero status even when the output parsed. This is worth stating because the
obvious implementation gets it backwards: killing the process on the way out of the *success* path
records `-SIGKILL` as the status, and a loader that reads its own kill as a clean exit accepts the
output of every tile that dies after writing. The kill therefore runs only on refusal paths. Found
in review of this record's own implementation.

**No second manifest parser.** The loader reads no manifests. It shells out to `sd plugin list
--json` — the CLI is the plugin service surface by design, R11-D13 pulled it forward precisely so
this would exist, and calling it is what stops a fourth copy of a reader from being the thing that
ships. It also gets the no-disk-scanning rule for free: the loader cannot glob because it never
looks at a directory.

**Three. The dashboard cap is heading where `bin/` went, and this is the count.** Measured, not
projected: `dashboard/` is **2,067 of 2,500 — 433 lines left**. The loader cost **568** (560 in
`plugins.py`, 8 wiring the endpoint), against the **~240** R11-D13 left for *the loader and
`RUN_ALLOWLIST` together*. It is more than twice that slice, by itself.

R11-D13 enumerated the backbone-side lift from the system dashboard at **763**. 763 against 433
does not fit, before `RUN_ALLOWLIST` is counted at all — so `dashboard/` lands at roughly **2,830,
330 over**, and that is the optimistic figure. The shape is identical to the one that produced
R11-D15: a cap itemised from unwritten scope, and the first piece actually built comes in over its
share.

**The cap is not raised here, and the test still passes at 2,067.** Raising it in the change that
revealed the problem is the move this pack has already made three times with `bin/`, and the
number that comes out is another estimate. Trigger, matching R11-D15's: the landing that carries
the backbone renders re-derives `dashboard/` from files that exist, once, and may set the ceiling
in its own record. Owner: whoever lands it.

One thing worth saying about the 560 rather than letting it pass as inevitable: roughly half is
code and the rest is comments and docstrings, which is this repository's convention and not an
accident of this file. The convention is not being revisited here; it is named so the
re-derivation does not mistake a house style for a measurement.

**R11-D15 (user, 2026-08-31) — the `bin/` cap is 14,000, derived from built code; and `sd-help`
leaves `bin/` because the taxonomy already said it is not a command.**

R11-D13 said the cap would be re-derived from an itemised count at the landing that measured the
overrun rather than raised on an estimate. 6b-1 is that landing: `bin/sd` came in at 264 lines,
taking core to 7,756 of 8,000 with **244 left and seven commands then counted as unbuilt**, when
the smallest command already built is 279. The trigger has fired. (Seven is what that count found;
the reclassification below takes `sd-help` out of `bin/`, so every projection in this record works
from **six**.)

**Why this number is different from the last three.** 6,000, 6,500 and 8,000 were each derived by
itemising work that did not exist yet — adding up guesses about unwritten commands. All three were
busted, the last one before even half the commands were written. This one is derived from the five
commands that exist:

| | Lines |
|---|---|
| Shared support — `sd_lib`, `sd_route`, installer, `setup_github`, docs-lint, pr-state, trackers, dashboard CLI, restore hook | 3,720 |
| Five built commands — `sd-check` 279, `sd-handoff` 434, `sd-skill-adopt` 631, `sd-status` 1,060, `sd-review` 1,368 | 3,772 |
| `bin/sd`, registration slice | 264 |
| **Today** | **7,756** |
| Six remaining commands at the built mean of 754 | 4,524 |
| `sd store\|issue\|config`, the design's own sub-cap | 1,400 |
| Three missing `sd-dashboard` verbs | 300 |
| **Derived** | **13,980 → cap 14,000** |

*(**The itemisation is stale as of 2026-09-01, and the cap is not.** `bin/sd`
is **1,553 lines** at this commit -- close to six times the 264 the third row
records -- because step 8 grew it by
manifest enforcement, `sd plugin lock`, `sd config` and the vault driver. 264
was true when written and is the measurement 6b-1 landed on, so it stays;
what is corrected is the claim that these rows still sum to the number below
them. The cap itself is unaffected and was never derived from this table alone
-- `bin/` measures **9,574** against 14,000, and `tests/test_loc_caps.py`
enforces it by enumerating `git ls-files`, never from a list written here. The
`sd store|issue|config` row was re-measured at the same time and holds: 167
lines of config plus 294 of vault driver and store verbs, 461 of 1,400, with
`sd issue` and the store write verbs still unwritten. Superseded in part by
8-iv, which wrote the store write verbs: `bin/sd` is 2,096 lines at this
commit and `bin/` measures 10,117 against the same 14,000 cap. `sd issue`
remains unwritten.)*

Bounds rather than a point estimate, because a mean over five samples spanning 279 to 1,368 is a
weak instrument and saying so is part of the derivation: at the *smallest* built command, `sd-check`
at 279, the six land at 1,674 and the total at **11,130**; at the *largest*, `sd-review` at 1,368,
they land at 8,208 and the total at **17,664**. **Every version of
this clears 8,000 by thousands**, which is the robust part of the finding. 14,000 is the middle of
a range the evidence supports, not a number chosen to be comfortable, and it is roughly a seventh
of today's 95k — 95,000 over 14,000 is 6.8, so the original "<1/11" framing goes with the old
number rather than being quietly carried onto the new one.

**Standing rule 1 applied to a raise.** A cap that moves whenever it binds is not a cap. So: this
is re-derived **once more, from counts and not projections, when the last of the six lands**, and
that re-derivation may only lower it. If the final count comes in under 14,000 the cap follows the
count down. It never rises again without a new incident, and "the PR in front of me does not fit"
is not an incident — the rule that a cap is never raised in the PR that busts it stands untouched.

**The scope half turned out to be a documentation defect, not a scope decision.** Before raising
a ceiling it is worth asking whether everything under it earns its place, so the seven remaining
commands were re-read against the taxonomy's own test: a surface is a COMMAND only when invocation
pre-authorises external side effects. Six pass plainly — `sd-plan` writes and branches, `sd-ship`
merges, `sd-spec` writes, `sd-deps` triages other people's PRs, `sd-suggest` files issues,
`sd-map` writes artifacts. `sd-deps` was the one worth challenging on size (thirty-six characters
of specification) and it survives on the test rather than on the spec: triaging somebody else's
dependency PRs is exactly a pre-authorised external side effect.

`sd-help` fails the test — a catalog reads and prints and authorises nothing — **and the rollout
settled that at step 5b, not here.** `skills/sd-help/SKILL.md` exists, `tests/test_skill_
frontmatter.py` pins the tree to eleven commands plus skills, and `sd-skill-adopt`'s collision
check was corrected to eleven when it landed. What was never corrected is **this document**: the
command table at line 88 still listed `sd-help` as one of twelve, four sections above the taxonomy
paragraph stating it is a skill, and three other places recited the twelve. That is fixed here.

So the count of eleven is not decided by this record — it is *recorded* by it, having been true in
the code and the tests for some time while design.md said otherwise. The correction is worth
making precisely because the design document is the thing a reader consults to learn what the
surfaces are, and it has been wrong about that since step 5b. It changes no budget: the derivation
above counts six remaining commands, never seven.

**R11-D13 (2026-08-31) — plugin registration moves ahead of 6b, and the dashboard cap is
re-derived from the split rather than from the estimate that set it.**

Two findings from the same look, both about the master sequence rather than about a design.

**One. The 6b plugin loader depends on machinery step 8 builds, and step 8 is scheduled after
it.** The tile contract says *"Registration only via `sd plugin add` — no disk scanning, no repo
writes"*, so the loader cannot glob `dashboard.d/*.py`; it has to read a registry that something
else writes. Enumerating `bin/` finds no `sd` at all — no verb groups, no manifest parser, no
registry format — and step 8 is where all of that is scheduled. R11-D12 flipped the order inside
6b; this crosses steps, so it changes the master sequence.

The fix is the smallest slice that unblocks the loader: **`sd plugin add|list` plus the manifest
read, pulled forward as 6b's first PR.** Not `sd store`, not `sd config`, not the vault driver,
not `sd plugin lock` — those stay at step 8 with the consumer that needs them. What moves is
exactly what the `dashboard.tile` key requires in order to be found.

**What the slice's parser does, and does not do (user, 2026-08-31).** It reads the **whole**
manifest into an object and validates **only the keys it uses** — `prefix` and `dashboard.tile`.
`kinds.*`, `issues.repo` and `vendor.*` are read and carried, not enforced. Step 8 then adds
enforcement to a reader that already exists rather than writing a second one, which is the failure
this pack has already paid for four times over in duplicated scripts.

It is also the only option that is honest right now: `kinds.*` validation means checking against
the closed 8-key vocabulary, and until R11-D14 (recorded in the Plugin
interface section above, where the schema it belongs to lives) that vocabulary was not written
down anywhere in this repository. A parser cannot enforce a list it cannot read, and enforcing it a
step early would have meant inventing the list at the keyboard.

The alternative considered and rejected: let the loader read a registry file of its own at 6b and
fold it into `sd plugin` at step 8. That defines the same disk format twice and hands step 8 a
migration, and it buys nothing except not touching the sequence. The deeper reason to reject it
is that it would make one consumer an exception to "no disk scanning" — and an exception granted
to the first consumer is how the rule stops being a rule.

**Two. The dashboard cap's justification is off, in the direction that matters.** `dashboard/`
is capped at 2,500 LOC, justified in this document as *"credible: 457 lifted + one JS file"*. The
6b enumeration splits both system files by where the code lands after the swap:

| | Lines | Fate |
|---|---|---|
| `dashboard.py` collectors, plugin-bound (toolbox, areas, ports, rtk, briefs, jira) | 301 | leaves the cap — `~/repos/system` |
| `dashboard.py` collectors the pack already has (repos, issues, github_issues, prs) | 124 | already built |
| `dashboard.py` collectors still to build (queues, research, work) | 79 | counts |
| `dashboard.js` plugin-bound renders (Toolbox 171, Briefs 71, Ports 41, Areas 34) | 317 | leaves the cap |
| `dashboard.js` backbone renders, shell and `attentionItems()` | 829 | counts, less the pack's existing 145 |

So the backbone-side lift is **763**, not 457. *(Later: none of the 79 is still to build against this cap. `research` shipped as a plugin tab in 6b-4 and R11-D21 moved `queues` to one, so both left `dashboard/` altogether, and `work` was built in 6b-5a and is inside the measured total. The table above is left as counted; subtracting the 79 again is the error this note exists to stop.)* Against 1,499 tracked today and a 2,500 cap, that
leaves roughly **240 lines** for the two remaining things with no system counterpart: the loader
and `RUN_ALLOWLIST`. The three missing `sd-dashboard` verbs are **not** in that number —
`tests/test_loc_caps.py`'s `test_the_dashboard_stays_under_its_ceiling` charges `bin/sd-dashboard` to the `bin/` ceiling on purpose, so that
the two caps do not overlap and neither means less than it says. The first draft of this record
charged them here, which is the same mistake in the other direction.

**And `bin/` is the tighter of the two.** Enumerated rather than taken from the itemisation:
`bin/` core is at **7,492 against its 8,000 cap — 508 lines of headroom** (`migrate-*` sits under
its own 1,500 ceiling and is excluded, which is why the raw 8,742 total passes).
*(Later: this is what closed the record's own escape hatch below — the three did not fit, and
R11-D15 re-derived the ceiling at **14,000** from built code in its own record. Both numbers in
this sentence are spent: re-measured 2026-08-31 at 6b-7, `bin/` core is **7,925 of 14,000**. The
count is left as it was taken, because it is the evidence R11-D15 was derived from.)* The itemisation
above predicts **~7,170 for the finished pack, leaving ~830**. That is the comparison worth
making, and it is worse than a headroom shortfall: 7,492 is what is built **today**, so the pack
has already passed the total its own itemisation predicted for the *complete* twelve-command set,
by 322 lines, with seven of those commands not yet written. What still has to fit in the 508:

- **seven of the twelve commands are unbuilt** — `sd-plan`, `sd-ship`, `sd-spec`, `sd-deps`,
  `sd-help`, `sd-suggest`, `sd-map`. *(R11-D15 later moved `sd-help` out of `bin/` as a skill,
  leaving six and eleven commands; the seven stands as what this count found.)* Five exist (`sd-check` 279, `sd-review` 1,368, `sd-status`
  1,060, `sd-skill-adopt` 631, `sd-handoff` 434);
- the entire `sd` CLI — `plugin`, `store`, `issue`, `config` verb groups — of which R11-D13's
  registration slice is the first piece;
- the three missing `sd-dashboard` verbs.

That does not fit, and saying so now is the point of enumerating it. It does not change this
decision — registration has to precede the loader whatever the ceiling says — but it does mean
the `bin/` cap, not the dashboard cap, is the one the rollout will hit first, and it will hit it
inside 6b. The same discipline applies: measure at the next landing, and re-derive from an
itemised list in its own record rather than raising a number to fit the PR in front of it. The
8,000 was itself the third attempt after 6,000 and 6,500 were both busted on paper; a fourth
estimate is worth less than one count.

The cap is **not raised here**, and deliberately. Raising a cap against an estimate is how the
6,000 and 6,500 `bin/` figures were busted twice before 8,000 was derived from an itemised list;
the honest move is to measure first. The loader is the smallest of the three unknowns and it now
comes first anyway, so **its PR reports its own line count against the remaining headroom**. If
the three fit, the cap stands and this record is the measurement that says so. If they do not,
the cap is re-derived from the itemised split in its own decision record — written before the
tabs start, never in the PR that trips `tests/test_loc_caps.py`.

What is recorded either way: the 457 figure is superseded by 763, so the cap's stated
justification no longer matches its number even though the number may still be right.

**Consequence for the sequence.** 6b's order, already flipped once by R11-D12, is now:
registration slice → the tile loader → the five plugin tabs → backbone tabs → Now →
`RUN_ALLOWLIST` and `sd-dashboard install` → swap to :8767 → delete `dashboard.py`.
*(R11-D21 later moved Queues out of the backbone tabs and made it a **sixth** plugin tab that
lands after the write path rather than with the other five, so "the five plugin tabs" is the
count this order was written against and not the count that shipped.)* Step 8 keeps
everything else and loses only what moved.

**Standing rule 1 does not apply to either half.** No gate, ledger, hook or rule is added: the
first half moves scheduled work earlier, and the second half declines to change a number.

**R11-D12 (2026-08-31) — a plugin tab contributes alert rows to Now, not only a rendered tile.**

Found while writing the 6b parity checklist, and it is a regression the design as written would
have shipped silently.

`attentionItems()` in the system dashboard's `assets/dashboard.js` builds the Needs-you view from
six sources: `toolbox`, `repos`, `queues`, `prs`, `ports`, `areas`. **Three of those six —
`toolbox`, `ports`, `areas` — are destined to be plugin tabs**, system-owned behind their own
manifest, and they own **nine of the thirteen rows** the view can emit — five from
`toolbox`, three from `areas`, one from `ports`; the backbone keeps two `repos` rows, one `prs`
row and one `queues` row.

What they contribute is not decoration, and the ranks say so. `attentionItems()` sorts by rank,
0 highest. **Every rank-0 and rank-1 row in the view comes from a plugin-bound source**: cron job
exited non-zero (`toolbox`, rank 0), vault collector errored (`areas`, rank 0), cron silent
(`toolbox`, rank 1), cron failure logged (`toolbox`, rank 1), task overdue (`areas`, rank 1). Of
the four rank-2 rows three are plugin-bound as well — cron job missing, machine drift, and a port
`CLASH`/`BUSY` — leaving the backbone one rank-2 row, and that one only when a PR is older than
fourteen days. Below rank 2 the tail is mixed rather than backbone-only: `repos` ahead/dirty,
`prs` and `queues` at ranks 3-4, plus one more plugin row (a vault inbox note untouched for a
week, rank 3).

The contract as specified is a **tile** — `dashboard.tile`, 5s, 64KB — which renders itself into
its own tab. A tile cannot put a row in somebody else's view. So the swap at 6b, executed against
the design as written, would leave Now alerting on `repos`, `queues` and `prs` alone — that is,
**with no rank-0 or rank-1 row left at all**, and a rank-2 row only while some PR is over
fourteen days old. Port conflicts, cron failures and vault rot would go silently. Nothing would report the loss, because Now would still render.

**The change is one optional key.** A plugin tab's collector may return, alongside whatever it
renders, a list of rows shaped exactly like the ones `add()` already takes — `{rank, kind, id,
what, detail}` *(this list carried a sixth key, `href`, until R11-D19 removed it: the anchor had
no reachable target and nothing read it)* — and Now merges plugin rows with backbone rows. The 5s/64KB budget covers
both halves; the row list is bounded by the same cap. No new machinery, no second call, no new
verb.

Consequences recorded rather than left implicit:

- **Ordering.** Now cannot be built before the plugin loader exists, because three of its six
  sources arrive through it. 6b's sequence is therefore plugin contract first, then the tabs,
  then Now, then the swap — not the tab-by-tab order the parity checklist's table might suggest.
- **Trust boundary.** Plugin rows land in the backbone's most prominent view, so a plugin can
  make Now say anything. That is already true of a tile, which renders arbitrary markup in its
  own tab; the difference is placement, not privilege. Registration stays explicit via
  `sd plugin add`, and a row could not navigate the user off the dashboard: `href` was confined to
  an in-page anchor. *(R11-D19 later removed `href` from the row contract outright: the anchor had
  nothing it could legitimately point at, and the backbone resolves a row's destination from
  `source` instead. The property this sentence protects is unchanged.)*
- **"Now screen = externally derived facts only" still holds**, on the reading that has always
  been load-bearing: *derived at run time rather than stored*, not *fetched from a remote
  service*. Every plugin row qualifies — `launchctl list`, `machine-setup.sh candidates`, and the
  vault's own files are read fresh on each collect, and none of them is a ledger. Said explicitly
  because the other reading would forbid the cron and vault rows the system dashboard has carried
  in that view all along.
- **Standing rule 1 does not apply.** This adds no gate, ledger, hook or rule; it is one field on
  a contract that does not exist yet, and its deletion criterion is inherited from the tabs it
  serves — if Toolbox, Ports and Vault never become plugin tabs, the field has no producer and
  goes with them.

**Two things the same investigation settled without a decision.** The **rtk savings ledger** is
not a homeless fact: it is a card rendered inside `renderToolbox()`, so it rides Toolbox to the
plugin side and needs no destination of its own — the parity checklist's first draft mis-filed it
as undecided by treating "collector with no tab of its own" as "fact with no home". **Ports** does
get its own plugin tab rather than folding into Toolbox: same owner (`machine-setup.sh` lives in
`~/repos/system`, exactly like the launchctl scan), but it has its own tab and its own alert
identity today, and folding would save one tab and lose that.

**R11-D11 (user, 2026-08-31) — the caveman review lane is demoted, not forked away.**

The plan's step-3e row said "caveman fork drops review lane". P5 could not execute it and said so
rather than reporting the row done: there is no fork, the marketplace entry points straight at
upstream `JuliusBrussee/caveman`, and dropping `caveman:cavecrew-reviewer` would mean forking a
third-party plugin and maintaining that fork forever to delete one 1.5 KB file. The other two
agents in the same plugin — `cavecrew-builder` (bounded 1–2 file edits) and `cavecrew-investigator`
(read-only locator) — are useful and conflict with nothing.

**The decision: keep the plugin installed, and demote the reviewer to a scratch tool.**
`sd-review` is the only lane that produces a *recorded* verdict. `cavecrew-reviewer` may be run for
a quick second look, and its output goes nowhere: it never writes `## Review`, never dispositions a
finding, never gates a merge, and is never named by a pack lane.

**Why this is doctrine and deliberately not machinery.** Standing rule 1 forbids a new gate without
a linked incident, and there is no incident here — no caveman finding has ever entered a `## Review`
section, because nothing automated could put it there. Writing an enforcement check would be
building the gate the rule exists to prevent, to guard against a human choosing to paste. The rule
is one sentence, and the thing that makes it hold is that no code path exists to violate it.

**The falsifiable form, since a sentence with no check is how prose gates start.** No `bin/` code
invokes it: `git grep -l cavecrew -- bin/` prints nothing and exits 1 today, and that is the
invariant. The one tracked file naming `cavecrew` at all is this rollout's own `implement.md`,
describing the situation. If a `bin/` hit ever appears, the demotion has been reversed by accident
and the lane needs a real decision rather than this one.

**Why the kimi/codex treatment does not transfer.** Step 3b vendored those agents *into* the pack
and then uninstalled their plugins, because pack lanes call them — `sd-review --challenge` names
kimi-challenge, and the vendored copy is what makes the lane survive the uninstall. No pack lane
calls a caveman agent, so vendoring buys nothing and forking costs a fork. The asymmetry is not
inconsistency: it tracks whether the backbone depends on the surface.

**Deletion criterion.** Not applicable in the usual direction — nothing is being added. The
reverse trigger: if a caveman finding is ever wanted in a recorded verdict, that is `sd-review`
growing a provider row, which is a backend-table change with its own record, not a quiet promotion
of the plugin agent.

**R11-D10 (user, 2026-08-31) — D14 resolves to (c): the phone keeps its writes, and the
GET-only assertion is temporary by design.**

Three D14s exist across the rounds and only one was open. `r7 D14` (no sd-* command may depend on
claude-mem) and `R8 D14` (OmniRoute removed, R11-D2) were already decided; this is `r2 D14`, phone
access, and it is the one thing that blocked step 6b.

**Correction (2026-08-31, found while running step 4b-i's `:8767 unchanged` check).** The
paragraph below originally read "Both dashboards bind `127.0.0.1`. The binding is not the difference
between them." That is wrong, and it was wrong in the direction that would have made 6b build the
wrong thing. `lsof -i :8767` shows the system dashboard listening on `127.0.0.1` **and** on this
node's tailnet IPv6 address: `dashboard.py:1708` binds one server per address over
`["127.0.0.1"] + TAILNET_ADDRS`, deliberately never `0.0.0.0` ("binding 0.0.0.0 instead would
publish the dashboard on every network this machine joins"), and the tailnet half is gated by
`DASHBOARD_TAILNET_BIND`, which is set in `~/Library/LaunchAgents/com.sven.project-dashboard.plist`.
So the reach is **two paths, not one**: a direct tailnet bind, and a `tailscale serve` proxy at
`https://tg-sol.tail6dbb92.ts.net:8443` forwarding to the loopback socket. 6b has to carry both or
knowingly drop one; a replacement that binds loopback and assumes a proxy in front would lose the
IP-URL path, which exists precisely for a phone whose resolver ignores MagicDNS. The rest of this
record — the decision, the three guards, and the cost to the GET-only assertion — is unaffected.

A second correction in the same reading: the closing paragraph's "`tailscale funnel` remains out of
the question" is a rule about **this** dashboard, not a description of this machine. `tailscale
funnel status` reports Funnel **on** for `https://tg-sol.tail6dbb92.ts.net`, proxying to
`127.0.0.1:8766` — that is `local-task-actions`, a different system-owned service whose exposure
and authentication were not examined here and are not this plan's to change. Port 8767 is not
funneled and must not become so. The sentence is kept because the rule is right; it is qualified
because the next person to run that command will see "Funnel on" and needs to know which service it
names.

**What was actually measured, because the obvious framing was wrong.** The system dashboard reaches
the phone over the tailnet — never the public internet — by the two paths named in the correction
above, and it guards the reach with three things rather than one: a Host-header allowlist
covering the loopback names plus this node's own MagicDNS names, a per-process token required on
every mutating request (`X-Dashboard-Token`, checked immediately after the Host check), and the
deliberate absence of CORS headers, so a page on another origin cannot obtain the preflight it
would need to send that header at all. Those live in the *system* repo, not this one — the file
under replacement is `~/repos/system/local-project-dashboard/dashboard.py`, where `do_POST` opens
at line 1658 with `host_ok()` (defined at 1532) and the token comparison at 1661. The path is
spelled in full because a bare `dashboard.py:1661` reads as an in-repo citation and there is no
such file here; `dashboard/server.py` is this repo's, and it is GET-only until 6b. Three write endpoints ride on that:
`POST /api/update`, `/api/ack`, `/api/refresh`.
*(Later, 6b-7: the pack dashboard has a POST now, so "GET-only until 6b" is spent rather than
wrong. The line numbers above have drifted with the file they cite -- re-read 2026-08-31,
`do_POST` opens at `:1785`, `host_ok` at `:1657`, the token comparison at `:1788` -- and the
one this repository now cites in `dashboard/actions.py` is `:1714`, the `GET /api/state?refresh=1`
rebuild that has no token in front of it and is the shape 6b-7 deliberately did not inherit.)*
*(Later, 6b-9: that file no longer exists -- platypeeps/system#190 deleted the
server half and kept the collectors. The line numbers above are citations into
its history, not into a working tree, and are left as written because a survey
keeps its date. What replaced each of the three endpoints is recorded in
`implement.md`'s 6b-7 and 6b-9 entries.)*

**The decision.** At 6b the replacement takes `:8767` *with* the tailnet reach and *with* those
writes, under the same three guards. Options (a) loopback-only and (b) tailnet read-only were both
available and both were regressions of a working daily surface — the iOS PWA is in live use, and
removing ack and queue-set from it would mean picking up a laptop to do what a thumb does now.
A framework that makes an existing workflow worse in order to keep its own invariant tidy has the
priority backwards.

**The cost, stated rather than discovered later.** P3 shipped `dashboard/server.py` with `do_GET`
and nothing else, and `tests/test_sd_dashboard.py` asserts the *absence* of `do_POST`, `do_PUT` and
`do_DELETE`. That assertion is now known to be temporary, and it stays exactly as it is until 6b —
it is correct today and it is what stops a tab quietly growing a write endpoint in the meantime.
At 6b it is not deleted but **replaced by a stronger one**: that every mutating handler refuses a
request failing the Host allowlist, refuses one without the token, and that no CORS header is ever
emitted. "No writes" is easy to assert and easy to lose; "writes exist and are guarded three ways"
is the assertion that has to survive.

Two things this does **not** license. The server still never commits, pushes, or runs an agent: the
r2 rule that every UI mutation maps 1:1 to a `bin/` command through RUN_ALLOWLIST is untouched, and
status flips remain intents applied by the next `sd-plan`/`sd-ship` sweep rather than a working-tree
write from a page load. And `tailscale funnel` remains out of the question — the reach is the
tailnet, not the internet, which is the line the system dashboard's own module docstring draws and
the reason it draws it.

**Deletion criterion (standing rule 1 applied to a carried-over mechanism rather than a new one).**
The writes exist because the phone uses them. If 60 days after the 6b swap the index shows fewer
than 10 mutating requests from a tailnet Host, the endpoints and their guards are deleted and the
dashboard returns to GET-only — which is where P3 already left it, so the reversal costs one commit
rather than a rewrite.

**R11-D4 (user, 2026-08-29) — the macOS CI leg is dropped for the rollout, and restored at step 7.**
*Superseded in part: the step-7 restore is postponed to a manual trigger at the end of the
rollout — see the amendment at the end of this record. The drop itself stands unchanged, and
the "step 7" wording below is the original decision, kept as written.*

Corrected before merge, because the first version of this record was wrong. The claim was that
`unittest (macos-latest, 3.13)` at 12m18s is the long pole in every CI run. It is not. Measured on
the run for #604: `Shell coverage` takes 13m40s and the run's wall clock was 13m45s, so the run is
bounded by shell coverage and dropping macOS buys **approximately zero latency**. The per-job
numbers were read without checking which job actually bounded the run.

What the drop does buy is cost: GitHub bills macOS runners at ten times the Linux rate, and the
leg is 12m18s on every pull request in a rollout with roughly fifteen left to land. That is a real
saving, and it is the honest reason to do it -- but it is not the reason originally given, and the
decision to drop the leg was taken on the wrong one.

The genuine latency lever, now that it is measured, is `Shell coverage` at 13m40s. It is not
touched here: it is the kcov lane that publishes the shell-coverage baseline, and trading it away
would cost real coverage rather than duplicate runner time. Named so the next person does not
repeat the same mistake in the other direction.

Two things change together, and the order is load-bearing. Branch protection lists the six
contexts as **required**, so removing the job first would leave a required context that can never
report again and every subsequent pull request would block forever -- including the one removing
it, since a pull request's CI runs the workflow from its own branch. So protection is relaxed to
five contexts **before** the workflow change merges, never after.

This is a decision record rather than a chore precisely because R11-D3 made required contexts
part of the merge-authority claim: "the required contexts match the jobs CI runs" is one of the
enforcement dimensions `sd-status` reports, and changing the set changes what the doctrine
asserts. `sd-status` needs no edit -- it reads the live protection object rather than a stored
list, which is the design behaving as intended.

What is lost, named rather than waved away: with the leg gone, **no CI job runs on macOS at all**,
so macOS-only Python behaviour, filesystem case-insensitivity, and platform-specific path handling
are unverified in CI until it returns. The only remaining macOS coverage is the maintainer's own
`make check` -- which is how several defects in this rollout were caught locally rather than in
CI, but it is one machine, not a gate.

A second correction to this record, found in review: the first draft claimed the bash 3.2 syntax
gate in `lint` still covered macOS. It does not. **No CI job invokes `check-bash32-syntax.sh`** --
the `lint` job runs ruff, mypy, `node --check` and the opencode check, on `ubuntu-latest`, and the
gate ran only in a local `make lint`. Worse, the script's own skip warning told Linux contributors
that "the macOS CI leg still enforces them", which was false before this change too: the macOS leg
ran `unittest`, never this script.

**R11-D5 (user, 2026-08-29) -- the bash 3.2 gate now runs in CI.** Finding the gap above was the
reason to close it rather than document it. A `bash32` job builds bash 3.2.57 from source, since no
Linux distribution packages it, and runs `check-bash32-syntax.sh` with `STRICT=1` so the
no-interpreter path fails the job instead of skipping. Three details are load-bearing and were each
established by running them, not assumed:

- **The build needs `-j1`.** bash 3.2's Makefile races under parallel make: a `-j$(nproc)` build
  failed once and succeeded twice on the same input. Nondeterminism is the worst property a gate can
  have, so the build is serial and cached per version.
- **bash 3.2 predates aarch64** and its `config.sub` cannot recognise the host, so it does not build
  there. The x86_64 GitHub runners are fine; this is why the job has no matrix.
- **The job verifies the binary reports 3.2 before running the gate.** Without that, a wrong
  interpreter would turn the whole job into a green no-op -- the exact failure mode the gate exists
  to prevent.

Verified in an `ubuntu:24.04` container against the real tracked set, in both directions: clean tree
gives `14 tracked shell scripts accepted` and exit 0; a planted apostrophe inside a `$( ... )`
substitution -- the construct named at the top of the script -- is **accepted by bash 5** and
rejected by bash 3.2, failing the gate with exit 1. A gate only proven in the passing direction is
not proven.

Scope, stated so it is not overread: this covers bash 3.2 *syntax*, one real slice of macOS
compatibility. macOS-only Python behaviour, filesystem case-insensitivity, and platform path
handling remain unverified in CI until the leg returns at step 7. The stale claim is fixed in the
Makefile, README, CONTRIBUTING, and the quality-guidelines spec alongside the script itself.

Restore criterion (standing rule 1 applied to a removal rather than an addition): the leg and its
required context come back at **step 7**, which already carries "verify protection" on its
checklist. If step 7 lands without the leg restored, the rollout has quietly kept a temporary
measure, and CONTRIBUTING's "restored at step 7" sentence becomes the falsifiable record that it
did not.

**Amendment (user, 2026-08-31) -- the restore is postponed past step 7 and becomes a manual
trigger.** The user will restore the leg by hand when the rollout is done, rather than at step 7.
The reason to do it is straightforward: step 7 is not the end of the work -- steps 8 through 11
still land pull requests, so restoring a ten-times-cost runner leg at step 7 pays for it on every
one of them, which is the same argument that dropped the leg in the first place. Deferring to the
actual end of the rollout is the consistent position, not a new one.

What this costs, and it is worth naming because the paragraph above is what pays: **the deadline
was the mechanism.** Standing rule 1 asks a removal to carry a criterion that fails loudly if
ignored, and "step 7" was falsifiable precisely because step 7 is a dated event someone has to
close out. "When we are done" is not: nothing trips if it never happens, and the rollout can end
with the temporary measure quietly permanent. That is the user's call and it is recorded as their
call; what remains is that the absence stays visible rather than silent. So the CONTRIBUTING and
README paragraphs keep saying, in the present tense and with no date attached, that **no CI job
runs on macOS at all** and that macOS-only Python behaviour, filesystem case-insensitivity, and
platform path handling are unverified in CI. Those sentences are now the whole of the record. They
do not expire, which is the point: a reader arriving at any later date sees a live gap rather than
a promise whose due date has passed.

Step 7's checklist loses the restore line. It keeps "verify protection", which is a separate
obligation and unaffected. The ordering constraint is not cancelled, only deferred with the work:
whenever the leg does come back, branch protection gains the sixth required context **after** the
workflow change merges and the job has reported once, never before -- the mirror of the relax-first
ordering that removing it required, and for the same reason. A required context that has never
reported blocks every pull request including the one that would fix it.

**R11-D6 (user, 2026-08-30) -- the `Shell coverage` job is deleted at the step-3 sub-PR 3e,
because what it measures ceases to exist.**

The question was whether the kcov lane's need goes away and how soon. Both halves have sharp
answers: it goes to zero rather than to "less", and it happens in the pull request immediately
after 3d.

**Which 3e -- and the collision resolved (R11-D7, user, 2026-08-30).** `implement.md` spent the
letters `3a`-`3e` twice: once on the step-3 sub-PRs and once on the platform sweep in the master
table. The label alone was ambiguous, so this record means the **step-3 sub-PR**: new machine-scope
`install.py` + `installed.json` + parity tests, which deletes `templates/scripts/**`,
`installer/**`, and `manifest.json`.

The collision is resolved by renaming the platform sweep to `P1`-`P5`, not the sub-PRs. The
asymmetry decides it rather than taste: five merged pull requests already cite the sub-PR letters in
their titles (#601 and #602 as `3a`, #603 `3b`, #604 `3c-review`, #607 `3d`), while the platform
sweep's rows are cited in no landed pull request and every one of them is unstarted. Git history
cannot be rewritten to match a renamed step, so the side with zero landed references is the side
that moves. `P` is chosen because it cannot collide with any step number.

**The lane measures exactly one directory.** Its kcov include filter is the string
`sd-ai-command-pack-`, which matches the seven shell files under `templates/scripts/` and nothing
else. 3e deletes that directory. The replacement world in `bin/` is eleven tracked files, every one
of them Python, none matching the prefix. After 3e there is no shipped shell in the repository to
measure. This is not a coverage reduction to be weighed against its cost; the subject matter is
gone.

The surviving `.github/scripts/*.sh` files are **not** a reason to keep the lane: the
prefix never matched them, so they are unmeasured today, and deleting the job loses nothing that is
currently measured. (Written as "the seven" before 3e ran. Three survive, not seven -- the other
four were harnesses for payload this step deletes, so they went with their subjects. Corrected
rather than left, because the count is the kind of detail a later reader would take as measured.) Repointing kcov at them was considered and rejected -- it would measure CI
harness rather than shipped product, which is the kind of gate that exists to keep a number alive
rather than to catch a defect.

Left in place, the job does not merely become pointless, it becomes a blocker.
`report-shell-coverage.sh` fails hard on a zero measurement (`error: no kcov run directories`,
exit 1) deliberately, to catch silent plumbing breakage. With `templates/scripts/` gone that guard
fires on every run, and `Shell coverage` is a required context under `enforce_admins: true`.

**Ordering is load-bearing, and it is the R11-D4 trap again.** A pull request's CI runs the
workflow from its own branch, so a 3e deleting the payload and the job together would produce no
`Shell coverage` context, leave a required check permanently unreported, and block itself and every
pull request after it, with no admin bypass. Protection therefore drops to five required contexts
**before** the 3e workflow change merges, never after. Both directions of this trap have now been
observed rather than theorised: dropping the macOS leg on 2026-08-29 required relaxing protection
first, and adding `bash 3.2 syntax` on 2026-08-30 immediately flipped an open pull request from
CLEAN to BLOCKED for want of a context its branch could not yet produce.

**This settles a question R11-D4 deliberately left open.** That record named `Shell coverage` at
13m40s as the run's true long pole -- the genuine latency lever, where the macOS leg was only a cost
lever -- and declined to touch it because "trading it away would cost real coverage rather than
duplicate runner time." At 3e the objection expires: the coverage traded away is coverage of
nothing. Wall clock falls from roughly 13m45s to whatever `unittest (ubuntu-latest, 3.13)` costs.
That is a consequence, not the justification, and the distinction is the one R11-D4 got wrong the
first time.

**Scope of the removal, enumerated rather than estimated.** The first draft of this record listed
two files and was wrong by an order of magnitude; `git grep` finds the lane referenced in twenty
tracked files. The executable machinery is `kcov-bash-shim.sh` (73 lines),
`report-shell-coverage.sh` (61) and `summarize_shell_coverage.py` (103), with
`tests/test_summarize_shell_coverage.py` (141) and the spec
`docs/spec/tooling/runtime-coverage-lanes.md` (97) -- about 475 lines before counting the
references in `tests.yml`, the `Makefile`, `README.md`, `CONTRIBUTING.md`, two further specs, and
five test modules. The four `SD_AI_COMMAND_PACK_KCOV_*` variables and `SD_AI_COMMAND_PACK_TEST_BASH`
go with it. Those variables are documented, which `CONTRIBUTING.md` makes stable public surface, but
0.72.0 is the terminal release and post-0.72.0 payload edits are unversioned, so no bump is owed.
The 3e pull request enumerates this set from `git grep` at the time it is written rather than from
this paragraph, which will have aged.

Restore criterion (standing rule 1 applied to a removal). The lane returns before shipped shell
does, enforced as an invariant rather than promised in prose: 3e lands a test asserting that no
tracked shell file exists outside `.github/scripts/`. The test must enumerate shell the way
`check-bash32-syntax.sh` already does -- every tracked `*.sh` **plus** any tracked file whose
shebang names a shell -- because an extensionless script is exactly what a suffix-only check would
miss. Re-introducing shipped shell then fails CI until this decision is revisited and the lane
restored. If that test is ever deleted rather than satisfied, this record is the falsifiable
evidence that the removal was quietly widened.

**R11-D17 (user, 2026-08-31) — a plugin declares what its table can do and the backbone does
it; the markup it sends is filtered on the way out of the loader; and `dashboard/` is re-derived
at 4,000.** *(The number is superseded by R11-D24, which re-derived it at 4,300 and split a
code-only ceiling out of it. The two plugin-contract halves of this record stand unchanged.)*

6b-3 is the backbone rendering plugin tabs. R11-D16 fixed what a tile returns and left two
questions it could not answer without a consumer, and building the consumer answered both.

**One. Interaction. The tile's tables are searchable and sortable in the view they replace, and
the tile cannot ship the script that does it.** The system dashboard's own JS gives every one of
these tabs a filter box and click-to-sort headers, so a port that dropped them would be a
regression the parity checklist would catch at the swap. Three ways to keep them, and the user
chose the third: let the plugin ship script (the boundary this pack spent 6b-2 establishing, gone
in one line); accept the regression; or **have the plugin declare the behaviour and the backbone
provide it**.

The declaration is attributes, because attributes are data:

```html
<table data-sd-sort data-sd-search="filter jobs">
  <thead><tr><th data-sort="text">job</th><th data-sort="num">age</th></tr></thead>
```

`data-sd-search` asks for a filter box above the table, its value becoming the placeholder;
`data-sd-sort` asks for click-to-sort headers; a `<th data-sort="num">` says that column compares
as a number and `data-sort="none"`, or its absence, leaves a column unsortable. The backbone owns
the implementation, so every plugin's table sorts the same way and a fix reaches all of them at
once. The cost is honest and small: a behaviour no attribute names cannot be had at all, and the
answer to "our table needs to do something else" is a new attribute in this record, not a script
tag.

**Two. `innerHTML` not running `<script>` settles nothing, and that is why there is a filter.**
The markup a tile returns is injected into its panel. Injection does not execute a `<script>`
element, which is the fact that makes people stop looking — and it is not the attack. `onclick`
runs as written, `<img src=x onerror=…>` needs no click, and an `<iframe>` needs neither. So the
payload passes an **allow-list** on the way out of the loader, server-side rather than in the
browser: `/api/plugins` is a surface of this server, and a sanitiser living in `app.js` would
leave the endpoint itself serving whatever a tile printed.

An allow-list rather than a deny-list, because a list of dangerous tags is a list somebody has to
keep current against browsers. Three outcomes: structural markup is **kept**; an unknown tag is
**unwrapped**, losing the box and keeping the text; and a tag whose content is code, a request or
a control — `script`, `iframe`, `form`, `svg` — is **erased with its subtree**. `<img>` needs
neither rule: it is not allow-listed, and a void element has no subtree to erase. Attributes
are `class`, `title`, `lang`, `dir`, a few per-tag structural ones, and `data-*`, which is what
makes the interaction contract above possible without script. `href` must be `https:`, `http:` or
`mailto:` — a relative one would resolve against this server's own routes. `id` is not allowed at
all: a tile emitting `id="rows"` would claim an element the backbone addresses by name.

Every drop is reported, and the report is a rank-0 row. Markup rewritten in silence looks to its
author exactly like markup that rendered, and this is the same rule as the rest of the loader: the
tab is kept, the loss is named.

**Rows are still not markup.** R11-D16's split is unchanged and this does not soften it: `rows`
are typed fields rendered as text into the backbone's own view, and no filter makes markup
welcome there.

**Three. The dashboard cap is re-derived at 4,000, from files that exist.** R11-D16's trigger
named this landing — *"the landing that carries the backbone renders re-derives `dashboard/` from
files that exist, once, and may set the ceiling in its own record"* — and this is that record. The
re-derivation, all of it from measurement or from an enumeration already made:

| part | lines | source |
|---|---|---|
| `dashboard/` as it stands with 6b-3 | 2,488 | measured, `git ls-files -- dashboard` |
| backbone tabs still to port | 763 | R11-D13's enumeration: 79 collector lines plus 684 of JS |
| Now: merging plugin rows with the backbone's, ranked | ~120 | estimate |
| the token-gated write path R11-D10 commits to | ~200 | estimate |
| **derived total** | **~3,571** | |

Set at **4,000**, which is the derived total plus room for this repository's comment convention
rather than for more scope — roughly half of every file here is prose, which is house style and
not an accident, and a cap derived from code alone would be busted by the next docstring. Like
`bin/`'s 14,000 it may move **downward** and not up *(spent: R11-D24 raised it once, for the
reason this very sentence set up — see the note below the paragraph)*, and the two estimates in
the table are the part to check: if Now and the write path land materially over them, that is a finding for their
own records, not a second re-derivation.
*(Both did, and both are recorded where this says they should be. Now cost **212** against ~120
(6b-5b); the write path cost **343** against ~200 (6b-7). The table is left as derived — the cap
is not re-derived a second time — but a reader taking either estimate as settled is reading the
part this paragraph flagged as the part to check. After 6b-7, `dashboard/` is **4,000 of 4,000**
exactly, with nothing left for the tailnet bind R11-D10's correction still requires -- which is
what R11-D24 was written to settle.)*

The old number is not defended. 2,500 was set against a 457-line lift that R11-D13 measured at
763, and the estimate it rested on was wrong before any of this was built. What the cap is for is
unchanged: the retired stack reached 95,000 lines one defensible commit at a time.

**R11-D18 (2026-08-31) — a failing tile gets to say why, and the loader was throwing that away.**

Found by writing the first real tile. Five tabs refused, and every row read `exited 2` and nothing
else: not which argument was wrong, not that the interpreter was missing, not the traceback the
tile had already printed. `bounded_run` opened the process with `stderr=subprocess.DEVNULL`.

That is the module's own rule broken by the module. R11-D16 states that every way a tab can fail
becomes a row naming the tab and the reason, *"silence is not an available outcome"* — and the
loader was discarding the plugin's account of its own failure while dutifully reporting that
something had gone wrong. A row that says a tab failed and cannot say why sends its reader to the
one place the loader has already been: the tile's output.

**Read, not merely piped.** The obvious fix — `stderr=subprocess.PIPE`, read it at the end — is
wrong, and measurably so: a pipe nobody drains fills at 64KB and the writer blocks. Measured on
this machine, a child writing 400KB to an unread stderr is still blocked after three seconds. So a
tile with a long traceback would never reach its own exit, the five-second deadline would fire,
and the loader would report a timeout for a tile that was ready to explain itself — a lost message
replaced by a wrong diagnosis. Stderr is therefore read alongside stdout in the same `select` loop.

**Bounded, because stderr is plugin output too.** The last 512 bytes ride back in the refusal.
The tail rather than the head, since a traceback puts the error on its last line and the first
stack frame is not what anyone needs. Unbounded, a plugin would decide how long a row is.

Three properties, each tested: the reason carries what the tile said; a 20KB stderr still produces
a bounded row that keeps the *end*; and a tile that floods stderr and then prints good JSON is
served rather than killed — the test that fails against the naive fix and passes against this one.

**And one message stopped being true when the tail was added.** The stall reasons read "no output
within 5s" and "stopped writing within 5s"; with a stderr tail appended, the first became
"no output within 5s: Traceback ..." — a sentence that contradicts itself, in exactly the case it
is read in, since a tile that dies on import talks only on stderr. Both now name stdout. A guard
correct in isolation and wrong once something else touches its output: the same shape as the two
composed guards found in #652, and worth naming twice. Found in review.

**The same deadlock, past the break.** Round 3 found the half the fix had
missed. Stdout ending is not stderr ending: a tile that prints its JSON, closes
stdout, and then writes past the pipe capacity on stderr blocks in that write
until someone reads — and the loop that had been reading has already broken on
stdout's EOF. The plain `proc.wait()` after it therefore hangs on exactly the
backpressure this change removed, and reports `did not exit within 5s` for a
tile that said everything it was asked for. The wait now drains: `select` on
stderr with a 50ms cap while it is open, a plain wait for the rest of the budget
once it closes, so a tile that exits while a grandchild holds stderr is still
noticed.

The test for it took three tries, and the two failures are the finding.
`sys.stdout.close()` does **not** close descriptor 1 — CPython builds the
standard streams with `closefd=False`, so the reader never sees EOF, the loop
never breaks, and the first version of the test passed against the defect it was
written for. `os.close(1)` reproduces it. And a tile that floods stderr in the
same breath as closing stdout also passes, because `select` reports stderr ready
and the loop drains it before it ever notices the EOF; a 0.3s pause is what
makes the ordering deterministic. With both: 5.08s and `did not exit within 5s`
against the plain wait, 0.41s and served against the drain.

**A bound that stayed after its reason did not.** Round 2 read `drain()` as a
hang: called on the way to a refusal, it loops on a zero-timeout `select`, and a
tile writing stderr in a loop would keep the pipe readable forever, so the drain
would spin and never reach the kill. Shaped right, and it does not happen.
Measured with three writers — `yes`, `cat /dev/zero`, and three concurrent
`yes` — the pipe ran empty in **three reads every time**, because a zero-timeout
`select` sees the gap the instant the reader wins and no writer refills within
that scheduling quantum. A test written for the spin passed against the
unbounded code, which is the only useful thing it proved.

`DRAIN_BYTES = 65536` stays, on the narrower claim it can carry: one refusal
reads at most what one pipe buffer holds — everything a tile can have written
with nobody reading — so its cost is fixed rather than resting on an argument
about scheduling. The test was deleted rather than kept green, because a test
that passes with and against the fix is worse than none: it reports that
something was verified.

The flood test lost its clock in the same round. It asserted `load()` finished inside
`TILE_SECONDS`, which measures interpreter startup and registry reads against a budget meant for
one subprocess. It was also redundant: a tile blocked on a full stderr pipe never reaches its own
exit, so the deadlock shows up as a refused tab, and `ok` is the decisive assertion. Found in
review.

**R11-D19 (2026-08-31) — a plugin row's destination is resolved by the backbone, and `href`
leaves the row contract.**

Found while scoping 6b-5, by asking what a row's anchor actually points at. R11-D12 gave a row an
optional `href`, and R11-D16 confined it to an in-page anchor so that "a row cannot navigate the
operator anywhere". Both halves are implemented and neither is wrong. What neither record checked
is whether the anchor has anything to land on.

**It does not, in either direction.** A plugin cannot name a backbone id: `panelId`
(`dashboard/app.js:450`) composes the DOM id from the plugin's own prefix and tab name, lowercased
with non-alphanumerics collapsed, and the panel is `panel-plugin-<that>`. So the system plugin's
Toolbox tab is `panel-plugin-sys-toolbox`, and none of that composition is published anywhere a
plugin author reads. A plugin cannot name an id inside its own tile either: `id` is absent from
`GLOBAL_ATTRS` (`dashboard/markup.py:63`), so the sanitizer strips every anchor target a tile
tries to create — deliberately, and that is not being reversed here.

**The contract's own example is the proof.** design.md gives `"href": "#toolbox"`. Against the
real id that is a dead link, and `validate_rows` accepts it, because `#toolbox` is a well-formed
anchor and well-formed is all `ANCHOR` can check. The one line a plugin author copies produces
silent breakage that passes validation — the same shape as a rule that is enforced on spelling
rather than on what reached the operator.

**And nothing reads it.** `showAlerts`, then at `dashboard/app.js:265`, renders `source`, `what`
and `detail` as text and never touches `row.href`. The key is validated, carried across the
loader, and dropped. (*`showAlerts` was deleted at `56f16c7b`, 6b-5b. The line number is dropped
rather than corrected because there is nothing to correct it to -- a pointer that cannot resolve
is not a citation -- and the observation is kept as the dated one it was. The load-bearing claim,
that nothing reads `row.href`, was **not** re-verified against the renderer that replaced it.*)
That is not a gap to fill at 6b-5b; it is the absence of anything to fill it with.

**So the backbone resolves the destination instead.** The loader already stamps `source` on every
row it accepts (`dashboard/plugins.py`, in `validate_rows`), and the tab that emitted a row is the
only destination the row can legitimately have — a plugin alert exists to send its reader to the
plugin's own tab. Now therefore links each row to its origin panel, looked up from `source` in the
map the renderer fills as it assigns ids — never recomputed from `source`, for the reason the next
paragraph gives. Nothing for a plugin author to guess, nothing to get wrong, and the R11-D16
property is kept rather than restated: the destination is in-page because the backbone chose it,
not because a regex hoped so.

**The mapping is unambiguous where it resolves, and it does not always resolve.** Both halves were
checked rather than argued, because the whole ruling rests on them, and the second half is the one
two review passes reasoned past.

*Unique at the source, lossy at the id — and the difference is a design constraint, not a
footnote.* `source` is unique per served tab: `bin/sd` refuses a prefix another plugin has
registered (*"already registered by …"*), and `read_plugin` refuses a tab name a manifest declares
twice, marking it `ok: False` so it never reaches the renderer. The panel id derived from it is not
unique, because `panelId` normalises with `[^a-z0-9]+ → -`, which is many-to-one: `a-b` and `a--b`
both satisfy `TAB_NAME`, `read_plugin` refuses only exact-string duplicates, and both land on
`sys-a-b` — so the `-2` suffix is reachable after all. **Now must therefore read the panel id from
a map the renderer builds as it assigns them, keyed on `prefix/name`, and never recompute the
normalisation.** Recomputing sends a row to a sibling tab's panel, which is worse than the row not
linking at all.

This claim was wrong twice before it was right, and both failures are kept because the shape
repeats. The first draft called the id unstable, citing a collision suffix; checking found the
registry and manifest reader refuse the duplicates that would cause one. The correction then
overreached into *"a resolution that silently picks the wrong panel is not a case that exists"* —
true of `source`, false of the id, because it reasoned about the inputs to a normalisation without
asking whether the normalisation was injective. Review round 2 supplied the counterexample. A
uniqueness argument that stops at the key and never looks at the function applied to it is the
error, and it survived one self-review and one reviewer lane.

*But not total, and the exceptions are precisely the rank-0 rows.* `load()` serves only tabs with
`ok` true, while `alert_rows` emits a row for every tab and plugin that failed. Three sources
therefore name no rendered panel: `dashboard`, for a registry that did not load; the bare prefix,
for a plugin that is dark as a whole; and `prefix/name` for a tab that was refused, whose panel was
filtered out at exactly the moment its alert was created. Found by running the loader against
`~/repos/system` rather than by reading it — one cold invocation timed out on `sys/toolbox` and
produced a row sourced to a tab that was not in the served list, which is the shape in the wild.

**So Now renders a row unlinked when its source resolves to no panel**, and that is a property of
the design rather than a hole in it. A failing plugin is the case R11-D12 exists to preserve, and
sending its reader to a tab that is not on screen would be the same disappearance one layer along.
The old key could not have done better: an `href` written by a tile that then failed to render is a
dead anchor that still looks clickable, and nothing in `ANCHOR` could have told the difference.

`href` is removed from the row contract and its validation branch deleted. Its two refusal tests
— an off-page href, a `javascript:` one — are replaced by a single test that a plugin still
sending the key is neither refused nor served it: dropping is the only outcome that punishes
nobody for a key this contract used to document while keeping an attacker-chosen string out of the
rendered payload. This subtracts a key that never worked; it does not subtract a capability.

**Two rejected alternatives, and what would bring each back.**

*Allow-list `id` in tile markup and let a row deep-link inside its own panel.* This is the only
option that adds reach, and it is refused for now on cost rather than on principle: an `id` a tile
controls can be `panel-repos` or `tab-issues`, so the filter would have to namespace every id on
the way out and rewrite the matching fragments in the same pass — a rewriting sanitiser rather
than a filtering one, which is a materially larger thing to get right. No tile has asked for it.
If one does, this record is what to revisit, and the namespacing is the price.

*Publish `panelId`'s algorithm so plugins can compute the id.* Refused because it buys nothing and
costs the freedom to rename. A plugin computing the id would be reproducing, by hand and in every
plugin, the one mapping the backbone already holds — and the moment it is published, `panel-plugin-`
is a contract and the backbone cannot restructure its own DOM without breaking every plugin that
copied the recipe. The first draft of this record refused it on instability instead, citing
`panelId`'s `-2` collision suffix, and reasoned that the registry and the manifest reader make it
unreachable. Both the reason and its correction are kept rather than quietly swapped: the suffix
*is* reachable, by the lossy-normalisation counterexample above, which is a second argument against
publishing the recipe rather than a rescue of the first. A plugin computing the id would have to
reproduce the collision handling too, and get it right against tabs it cannot see.

**The tile-html rule is untouched.** `SAFE_HREF` (`dashboard/markup.py:78`) stays absolute and
external only. The asymmetry is the trust boundary, not an inconsistency: a link in a tile is
inside a tab the operator chose to open, and a row appears in the most prominent view unbidden.
This record was written after first mistaking those two rules for a contradiction, which is the
reason the distinction is now stated here rather than left to be re-derived.

**R11-D20 (2026-08-31) — `kind` is a category and never a severity; an alert id identifies one
alert.**

Found by specifying Now against the view it is replacing, before writing it. Two defects, both in
contracts that have already shipped, and both invisible until a plugin row is asked to render.

**One. The two `kind`s are different fields wearing one name.** `attentionItems()` uses `kind` as a
closed severity — `bad`, `warn`, `flat` — and `renderAttention` styles from it with a ternary whose
final branch is a catch-all: `bad` → the "broken" pill, `warn` → "look", *everything else* →
"queued". The pack's `kind` is a free-form category: `plugin-dark`, `plugin-refused`,
`plugin-registry` from the loader, `cron` and `port` from the system tile. Neither is `bad` or
`warn`, so **a rank-0 row saying a plugin has gone dark would sort to the top of Now and be painted
as the lowest severity there is.**

Checked rather than assumed, and the check corrected the first reading. The nav badge counts
`kind !== 'flat'`, which is a test against the literal string — so `plugin-dark` *is* counted. The
failure is therefore not that the row disappears from the count; it is that the count and the row
disagree in the operator's face: the badge says something needs attention, and the row it points at
is styled like a queue item. A first pass had this as a disappearance, which would have been the
easier bug to accept, because it matches the shape R11-D12 already taught us to look for.

**The ruling: Now derives severity from `rank` alone, and never reads `kind`.** `kind` stays what
the pack made it — the category of thing that happened, useful for grouping and for a plugin to
name its own domain — and it never reaches a stylesheet. The system's severity column does not
port; it is redundant with an ordering the pack already has, and keeping both is what let one name
mean two things. The bands belong with Now's implementation at 6b-5b rather than here, because
choosing them is a rendering decision and this record's job is to stop the conflation.

**Two. An id is an ack key, and one tab's failures were sharing one.** An operator dismisses a row
by its id, and the ack suppresses every row carrying that id. `alert_rows` gave every complaint
from a tab the same id — the tab's own `prefix/name` — so a tab refusing three rows produced three
losses under one key, and clearing the first cleared all three without saying so. Measured before
the fix: three distinct complaints, one distinct id. That is the disappearance R11-D18 chased out
of the loader, reintroduced one layer up in the thing that reports it.

Fixed with `alert_id`, which composes an id from the source and a stable digest of the complaint's
own text. Stable rather than positional: a complaint's ordinal moves when a neighbour clears, which
would silently transfer an ack from the row it was granted to onto a different one. The digest does
not move, and the text is what the operator read when they dismissed it.

**Two smaller ones settled in the same pass, because they are the same field.** Plugin-minted ids
were passed through verbatim, so a plugin could mint `pr:owner/repo#5` and dismiss the backbone's
row of that name; ids are now namespaced by `source` at validation, not at render time, because an
id that is only unique once somebody remembers to prefix it is not unique. And nothing bounded an
id's length while the ack store refuses anything over 300 characters — so a long refusal produced a
row that could never be cleared. `ID_MAX` bounds it, keeping the readable head and appending a
digest so two long ids stay distinct.

**What is not claimed.** The dark row and the refused rows cannot collide with each other: a tab
that failed emits its dark row and returns, so the two are mutually exclusive per tab. An earlier
account of this finding said otherwise, and it was wrong.

**R11-D21 (user, 2026-08-31) — Queues is a plugin tab, and the plugin contract grows a declared
action.**

The parity checklist put the five `db-*` queue tabs in the backbone. Specifying them found that
they are not what the row implied: `DBS` maps each key to a folder of Obsidian markdown in the
vault, every row is a note, and the status and rating dropdowns POST to `/api/update`, which
rewrites the note's YAML frontmatter in place. Queues is a vault view with a write path — and every
other vault-reading tab in the fold, Vault and Briefs, was already assigned plugin-side and
system-owned. The checklist had one vault tab going one way and three going the other, on no stated
distinction.

**The distinction does not exist, so Queues moves.** A blog-idea queue is not a framework-native
fact; it is personal vault content that a set of vault routines also write. The rule design.md
already states — the shell and the framework-native facts fold into the backbone, system views stay
system-owned behind a registered manifest — puts Queues with Vault and Briefs, and the checklist
row is the thing that was wrong.

**But read-only is not a port of this tab, and that is what forced the second half.** The queues
exist to be decided in. Ported without their dropdowns, they become a list of things awaiting a
decision the dashboard can no longer take, while Now still emits five rank-4 rows pointing at them
— an alert whose destination cannot act on it. So the plugin contract gains a declared action: a
manifest may name actions alongside its tile, the backbone renders the control and routes the
result back through `RUN_ALLOWLIST` to the named command, and the command stays in `~/repos/system`
with the vault. This is not new doctrine. design.md already says *"code + pinned actions live in
`~/repos/system`"*, and the swap gate already requires that every UI mutation map 1:1 to a `bin/`
command through `RUN_ALLOWLIST`. What was missing was the mechanism, not the intent.

**Standing rule 1 applies, and both halves are supplied rather than waived.** New `RUN_ALLOWLIST`
ids need a linked incident and a deletion criterion.

*Incident:* the five queue tabs are the only surface in the fold whose entire purpose is a decision
made on the dashboard. Ported read-only, the tab becomes a list, and the rank-4 *"N awaiting your
decision"* rows become alerts that route the operator somewhere they cannot act — the same
dead-destination failure R11-D19 removed from the row contract, reintroduced as a whole tab.

*Deletion criterion:* the action ids and the manifest key go when the queues stop carrying
decisions — when every `decide` status is empty because the vault routines own the intake end to
end, as `skill` already trends toward since `skill-proposal-accept` was retired. If no queue asks a
question, nothing needs an answer, and the mechanism should not outlive the reason for it.

**Standing rule 2 is not touched, and the check is worth recording because the name invites the
error.** The frozen 8-key vocabulary is `kinds.*`, the store schema. A `dashboard.actions` key is a
manifest key, and the manifest's top level is not the thing that rule freezes.

**Consequence for the sequence, and it is the second time 6b has been reordered by a dependency
found while specifying rather than while building.** Queues no longer rides with the backbone tabs.
It lands after `RUN_ALLOWLIST` and the action mechanism, which is to say after the write path — so
the parity checklist's Queues row moves from *backbone* to *plugin tab*, and 6b-5a is Work alone.

**R11-D22 (2026-08-31) — Suggestions leaves the backbone tab list until something fills it.**

Found by building the other two tabs it was grouped with. `Suggestions · Skills · Sessions` was
one row of the parity checklist — three new surfaces with no system counterpart — and two of the
three had data waiting for them the moment they were asked. Skills reads two directories: 76 ship
here, 138 are installed, 62 of those came from somewhere else. Sessions reads `.git/worktrees`
and the process table: eight registrations across the fleet, all eight pointing at scratchpad
paths that no longer exist.

**The third has no producer.** Suggestions renders what `sd-suggest` files — *"file framework
improvements to the configured tracker; local draft deleted on successful filing"* — and
`sd-suggest` is one of the six commands in `bin/` that do not exist. There is no draft directory,
no schema for one, and nothing anywhere on this machine that a Suggestions collector could read.
A tab whose only content is *"the command that fills this has not been written"* is worse than no
tab: it occupies a place in the nav, it has to be maintained, and it teaches the operator that a
tab can mean nothing.

**So the tab is not built, and the parity checklist stops claiming it will be.** The row splits:
Skills and Sessions are marked built at 6b-5d; Suggestions moves to a row of its own whose
destination reads *backbone, blocked on `sd-suggest`*. The swap gate at 6b-8 is unblocked by this
rather than weakened — it requires every tab marked *backbone* to serve, and Suggestions is no
longer one.

**The deletion criterion is the producer.** When `sd-suggest` is built, whatever it writes is what
Suggestions renders, and that landing carries the tab. If `sd-suggest` is never built, the tab is
not a gap in this rollout; it goes with the command, and this record is what says so rather than
a checklist item that stays unticked forever.

*Rejected: build it against a schema chosen now.* That is a producer designed by its consumer,
with no user of either to check it against — the same shape as the `dashboard.d/*.py` spelling
this document carried for weeks describing a loader that never existed. One unbuilt thing is
cheaper to carry than two things that disagree.

**R11-D23 (2026-09-01) — the declared-action manifest key, decided by building it.**

R11-D21 committed to the mechanism and deliberately left its shape open: *a manifest may name
actions alongside its tile*. 6b-7 had to pick one to have a write path at all, so this records
what was picked, why, and what a reader may rely on — a plugin contract is an external interface,
and an interface whose only specification is the code that reads it is one nobody can write
against.

```json
"dashboard": {
  "tile": "./local-project-dashboard/dashboard.sh tile",
  "tabs": ["toolbox", "briefs"],
  "actions": [{"id": "queue-set", "label": "sort the queue", "run": "sd-sys queue --sort"}]
}
```

**`id` is `^[a-z][a-z0-9-]{0,31}$` — the same shape as a tab name, and for the same two reasons.**
It becomes part of a routed identifier, and it is passed nowhere it could be mistaken for a flag.
The dashboard namespaces it with the plugin's prefix, exactly as it namespaces rows and tabs, so
the id the page sends is `sys/queue-set` and a plugin declaring `index` gets `sys/index` rather
than the backbone's. That is the whole defence against a plugin claiming a backbone command or
shadowing a sibling's, and it is tested by trying both.

**`label` is required rather than defaulted to the id.** It is the text on the button, and
`queue-set` is not a sentence anyone wants to press. Defaulting would produce a working control
that reads like a variable name, which is the failure that never gets reported.

**`run` is a command string, `shlex.split` at load, run with the plugin's root as its working
directory.** The same treatment the tile already gets, because it is the same trust boundary and
not a wider one: a plugin that can name a tile command can already run code on this machine. The
argv never reaches the browser — `/api/actions` serves ids and labels only — so a page that has
never seen a command cannot be talked into echoing a different one back.

**No arguments from the page, and that is the decision, not an omission.** An action is a
*command*, not a *form*: the id resolves to a fixed argv and nothing a caller sends is
interpolated into it. Queues needs `{key, stem, field, value}` to set one note's status, and this
key cannot express that — which is the point at which 6b-6 must either declare one action per
outcome, or R11-D21's mechanism needs a second decision record for parameters with its own
validation story. Recorded here as the known edge rather than discovered there. *(Answered at
6b-6 by R11-D25: neither — the tab reads, the writing stays in Obsidian, and each queue declares
one fixed command that opens it.)*

**Validated at registration, in `bin/sd`, not at load.** A malformed block refuses
`sd plugin add` and is reported by `sd plugin list`, the same as a malformed `dashboard.tabs`. An
action that quietly stopped being offered is a button that used to work, and the registry is the
cheapest place to catch it.

*Rejected: a `dashboard.actions` object keyed by id.* It reads more naturally and it loses the
declaration order, which is the order the buttons render in. *Rejected: reusing `kinds.*`.*
Different namespace — standing rule 2 freezes the store's eight-key vocabulary, and this is a
manifest key (R11-D21 already says so).

**Standing rule 1.** *Incident:* 6b-7 shipped a write path whose only action is the backbone's
own `index`, so the mechanism R11-D21 committed to had no shape and 6b-6 would have invented one
in a pull request. *Deletion criterion:* the key goes with the actions it declares — R11-D21 ties
those to the `decide` statuses emptying, and nothing here outlives them.

**R11-D24 (user, 2026-09-01) — the dashboard cap is re-derived at 4,300 and split in two: a
total, and a code-only ceiling prose cannot pay for.**

R11-D17 set 4,000 and said, like R11-D15 before it, that the number may only move **downward**.
This raises it. That clause is the reason any of these numbers mean anything, so what is
overturned, and what is not, is written out below rather than implied by a new constant.

**What happened.** 6b-7 landed at **4,000 of 4,000, exactly**, and the last hour of it was spent deleting
rationale to fit a write path: a docstring here, a comment there, three separate passes, each one
trimming an explanation that was written because somebody needed it. The change was not
oversized. `sd-dashboard install` had already been pushed into `bin/` exactly as the 6b-5d entry
required. What ran out was the allowance R11-D17 made *for prose* — its own words: "4,000 is that
plus room for this repository's comment convention... roughly half of every file here is prose,
which is house style and not an accident, and a cap derived from code alone would be busted by
the next docstring."

**Measured, because the estimate is the thing under review.** `dashboard/` is 4,000 lines, of
which **2,141 carry code and 1,859 are comments, docstrings and blanks — 46%** (counted by the
same function the cap test uses, so the number in this record and the number CI enforces cannot
drift apart). R11-D17's guess
of "roughly half" was right; its allowance for that half was not. One ceiling over both halves
means a branch and a paragraph bid for the same line, and the paragraph loses every time, because
the branch is what the change is for. That is the failure this record fixes, and it is not the
failure caps exist to prevent.

**Second reason, and it cuts the other way.** The 4,000 was derived from a scope that has since
moved. R11-D17 counted 2,488 measured plus R11-D13's 763-line backbone lift, and that lift
included `research` and `queues` — both of which left `dashboard/` altogether when 6b-4 and
R11-D21 made them plugin tabs. So the ceiling covers less work than it was drawn for, while the
two estimates inside it (Now ~120, the write path ~200) came in at **212 and 337**. Neither
correction was applied to the number. Re-deriving is overdue in both directions.

**The derivation, from files that exist.**

| | lines | |
|---|---|---|
| measured today, `dashboard/` at 6b-7 | 4,000 | counted |
| 6b-8: the second address bind R11-D10's correction requires | ~25 | estimate |
| the ack store, route, Now filter and control — R11-D20 says an id **is** an ack key, and nothing stores one | ~100 | estimate |
| swap-time carry: whatever `index --dump` diffed against `/api/state` turns up | ~50 | estimate |
| **derived** | **~4,175** | |
| the overrun this project has measured twice (Now +77%, the write path +69%) applied to the estimates | ~4,300 | |

**Set at 4,300 total and 2,300 code.** The second number is 2,141 measured plus the ~54% of the
remaining ~300 that is code rather than prose. The two bind at almost the same point on purpose:
new work in house style exhausts both together, and work that is *only* code hits the code cap
first, which is the whole intent.

**What is overturned, precisely.** R11-D17's downward-only clause, for the dashboard total, once.
Not for `bin/`: R11-D15's 14,000 keeps it untouched and is nowhere near binding — `bin/` is 7,925.
And **the code cap inherits the clause instead**: 2,300 may move downward and not up. A total that
can be re-derived with an itemisation and a code ceiling that cannot is a stronger pair than one
number nobody may touch, because the number nobody may touch is the one that gets busted by a
docstring and then argued about in a pull request.

**Standing rule 1.** *Incident:* 6b-7 spent its last hour deleting reasoning to fit a branch, under
a ceiling explicitly widened to hold that reasoning; the cap was working against the convention it
was drawn for. *Deletion criterion:* both dashboard caps go when `dashboard.py` is deleted at 6b-8
and the replacement is the only dashboard — at that point the pack is not racing a 1,728-line
incumbent and the ceiling has no argument left to settle. Until then they are CI tests, and
neither is raised in the pull request that crosses it.

*Rejected: raise the total and leave it undivided.* That is the fifth cap raise in this rollout
(`bin/` 6,000 → 6,500 → 8,000 → 14,000, `dashboard/` 2,500 → 4,000) and the first with no
structural change to show for it. A ceiling that moves whenever it binds is a logging statement.
*Rejected: give `app.js` its own cap.* It is 741 lines of the 4,000 and 29% prose against Python's
50%, so a separate ceiling would be a real measurement — and it would also be the answer that
happens to free the most room, arrived at while looking for room. A code cap is checkable against
the failure that prompted it; a file-shaped cap is checkable against nothing.
*Rejected: reduce instead.* Roughly half of `dashboard/` is prose and most of it is a decision
somebody will need. Freeing 300 lines that way means deleting 300 lines of why.

**R11-D25 (user, 2026-09-01) — the Queues tab is read-only, and setting a status stays in
Obsidian.** R11-D23 recorded the edge and left it open: an action is a command and not a form, so
it takes no arguments, and Queues needs `{key, stem, field, value}` to set one note's status. The
two ways out were one action per outcome, which cannot name the *note* and so does not exist as
an option once looked at, or parameters — a second decision record, a validation story per
parameter, and caller text reaching an argv, which is the one property 6b-7 was built not to have.

**Neither. The tab reads, and the writing stays where it already happens.** Obsidian is where
these notes are written, and `update_note`'s guard — a status a routine owns is not offered to a
human — lives beside the vault rather than in a dashboard. Each queue instead declares one action
that opens it (`sys/queue-blog` and four siblings), which is a fixed command with the queue named
in the manifest, so R11-D21's mechanism gets its first real plugin use without gaining a new
shape. The pack's dashboard writes through `RUN_ALLOWLIST` and nothing else, unchanged.

**The parity cost, stated rather than buried.** The system dashboard sets a status from its Queues
table and the replacement does not; that is a carry-down, not a carry, and the swap gate should
read it as one. What it buys: the write path keeps "nothing a caller sends is interpolated",
6b-8's remaining headroom is not spent on a parameter validator, and the decision UI stays in the
editor where the note is read. If parameterised actions are wanted later they arrive on their own
evidence — a second surface asking for them — rather than as a side effect of the first plugin
tab that needed a form.

*Rejected: parameters now.* ~100 lines of code against the 159 R11-D24 left, spent widening the
newest security boundary in the repository for one tab, before any second caller exists to say
what the shape should be. *Rejected: an action per outcome.* `sys/queue-accept` acts on no note.

**Standing rule 1.** *Incident:* R11-D23 recorded this edge in the pull request that created it
and left the answer to the tab that would hit it, which is the right order and only works if the
answer is then written down. *Deletion criterion:* this record dies with the Queues tab, and the
tab dies when the `decide` statuses stop filling.

**R11-D26 (user, 2026-09-01) — where a kind is *kept* is a `store` block beside `dashboard`, not
a ninth `kinds.*` key.** Step 8-iii needed `sd store` to turn `sdw.blog-idea` into
`System/Databases/Blog Ideas`, and R11-D14's eight keys carry no location: `fields`,
`initial-status`, `protected-fields`, `transitions`, `human-only`, `unique-fields`, `floor`,
`sections` all describe what a kind *is*, and not one of them changes when the same kind is kept
somewhere else. The gap was real and had to be closed somewhere.

**The block is a sibling of `dashboard`.** `"store": {"driver", "root", "bases"}`, with `bases`
mapping each declared kind to a path relative to the root. Standing rule 2's count of eight is
untouched, because nothing was added to the vocabulary it fixes — the same move `config` made at
8-ii, and for the same reason. Step 11 reorganises the vault by rewriting `bases` and nothing
else.

**The root is an environment variable reference and never a literal path.** `ROOT_PATTERN` is
`^\$[A-Z][A-Z0-9_]*$`, so `/Users/someone/Documents/Vault` refuses at registration. *Incident:*
`pack.py:146` is a hardcoded absolute vault path with a username in it, read by four bindings and
forty call sites, portable to exactly one machine — and a manifest is the file most likely to be
copied to a second one. The knob is `OBSIDIAN_VAULT`, which the 2026-09-01 vault-root entry
already settled at five callers to one. There is **no default**: an unset variable is a sentence
naming the knob, where a default would be a silent read of somebody else's vault layout and a
fourth spelling of the same path.

**Coverage is checked in both directions, and the bases are not checked for existence.** A base
naming an undeclared kind is a directory nothing reads; a kind with no base is a store verb that
refuses at use time for a reason registration could have given. Existence is the deliberate
exception to `vendor.*.path` and `sections.template`, which are checked: those live inside the
checkout, which is present by definition on the machine registering it, and a vault is not — it
may be unmounted, on another volume, or behind a macOS TCC grant this process does not hold.
Refusing registration for that would fail a correct manifest.

*Rejected: a ninth key `base` inside each kind.* It reads better and keeps one kind's facts
together, and it is a vocabulary change wearing the clothes of a convenience — which is the exact
substitution standing rule 2 exists to catch. *Rejected: convention, deriving `Blog Ideas` from
`blog-idea`.* Nothing to declare and nothing to drift, and it hardcodes today's vault layout into
the backbone: step 11's move would become a code change instead of a manifest change.

**One key of the eight changed meaning, and it is a widening rather than a change.** `fields` now
keeps its **declared order** through registration instead of being sorted. It is the column order
`sd store list` prints — `pack.py` printed status, score, rating in that order and not
alphabetically — and no other key carries that information. `name_list` already refuses
duplicates, so the order costs nothing and sorting discarded it.

**R11-D28 (2026-09-02) — `sd store list --full` adds the body, and adds nothing to the fields.** Step 9
retargets five vault `SKILL.md` files at `sd`, and three of their four real invocations are
`pack.py topics list --status active --full`, whose output the research routines read `## Covers`,
`## Feeds` and `## Ground truth` out of. `sd store list --json` already returned every *declared*
field, so the gap was never the fields — it was that a listing carried no body at all, and the
retarget would have become one listing plus one `get` per note: ten calls for nine active topics,
handed to an unattended run.

Under `--json` each row gains a `body` key; as plain text each note prints whole, frontmatter
included, the way `store get` prints one and the way `pack.py topics list --full` did — that shape
*is* the parity being bought, so plain text was never going to be body-only.

What `--full` deliberately does **not** do is widen the fields to every key a note carries, which is
what `store get --json` does and says why. `get` names one note, so a field the manifest has not caught
up with is the answer to the question asked. A listing is a table, and a row that grows a column
per note stops being one. The trailing blank line between notes is `pack.py`'s and is kept: a note
whose body ends without one runs straight into the next `===` header. Parity is measured rather
than asserted — with the `===` headers stripped, `sd store list sdw.topic --status active --full`
and `pack.py topics list --status active --full` are byte-identical across all nine active topics.

This widens the surface without touching `interface = 1`, whose only promises are the exit codes
and `store get --json`'s shape.

**Standing rule 1.** *Incident:* 8-iii could not name a directory for a kind and would otherwise
have grown the vocabulary in a pull request. *Deletion criterion:* the block dies with the last
plugin that keeps anything outside its own checkout; a plugin whose kinds live in its repository
declares no `store` and every store verb refuses by name.

**R11-D27 (2026-09-01) — `sd store add|set` edits frontmatter by the line, never by parsing
a note and writing it back.** Step 8-iv is where `protected-fields`, `transitions`, `human-only`,
`floor`, `unique-fields` and `sections` stop being declarations and start refusing. The
enforcement is the easy half. The half that decides whether the step is safe to ship is how a
note gets back to disk.

**The reader this repository already has is lossy, and that is deliberate.** `frontmatter()`
(`bin/sd:1249`) is the twin of `sd-writing-pack/scripts/pack.py:244-258` -- the vault-side tool
step 10 deletes, in the sibling repository of that name, not in this one -- down to what it cannot
see: a value spanning
lines comes back as the empty string, because the continuation line does not match the key
pattern and is skipped. 8-iii wrote that down as a limitation and not a bug, correctly, because
the corpus was written by that reader's twin and a stricter parser would disagree with it. What
8-iii did not have to ask is what happens when the same reader is put in front of a *write*.

**Read-modify-write through it destroys every note it touches, in two independent ways.**
Measured against the four bases that hold notes today by running the repository's own
`frontmatter()` over the corpus and rebuilding each block from what came back, not reasoned
about.

*List values vanish.* **244 of 244 notes** carry at least one key whose value is a YAML list —
`tags` (895 items), `contexts` (244), `aliases` (17) and `category` (10), **1,166 list items in
all**. Each key reads back as `""` and its items are not in the dictionary at all, so the rebuild
emits a bare `tags:` and drops what was under it.

*Quoted scalars lose their quotes.* The reader ends `.strip('"')` (`bin/sd:1277`), which is
correct for reading and destructive for writing: **146 of the 244** carry a quoted value whose
text contains a `:` or opens a `[[wikilink]]`, and re-emitting those bare is not lossy YAML but
*malformed* YAML — `source-brief: [[2026-08-15 - Daily Intel Brief]]` and a `description:` with a
sentence colon in it both stop parsing.

One real note makes the size of it concrete: changing `status` alone takes its frontmatter from
twelve lines to eight, taking `contexts`, `tags` and three tag items with it. There is no partial
version of this failure and no kind it spares — it is total, and it is invisible until somebody
opens a note in Obsidian and finds its tags gone.

**So the write is a line edit, and the incumbent already proves it works.**
`sd-writing-pack/scripts/pack.py:375` is
`re.sub(r"(?m)^status: .*$", "status: published", text, count=1)` — it never builds a dictionary,
so it never had this problem. The generic replacement is the thing that could regress it, because
a parsed round trip is what a reviewer would call the cleaner implementation. `set` locates the
one line whose key matches, replaces the text after the colon, and writes the file otherwise
byte-for-byte unchanged. It does not touch the body. It does not reflow, requote, or reorder
anything it did not edit.

**Three cases the line edit has to answer, and one it must refuse.** A key the note does not
carry is appended immediately before the closing `---`, which is the only position the backbone
can choose without knowing what the keys mean; `pack.py` inserted after a named anchor per field,
and that knowledge is exactly what the backbone is forbidden to hold. A key carried **twice** is
refused rather than edited: frontmatter with a duplicate key is malformed, and `count=1` picking
the first of two is a silent choice wearing the clothes of a fix. A note with no frontmatter block
at all is refused by the same reasoning — `add` creates notes, `set` edits them, and inventing a
block is `add`'s job.

**`add` renders through `sections.template` and is the safe verb**, because a new note has nothing
to preserve. `initial-status` supplies `status` and `unique-fields` is checked against the base
before the file is created.

**`sections.order` is where 8-iv finds a key that is recorded and never checked.** `validate_sections`
confirms the order is a non-empty list of unique non-empty headings and that `template` is a regular
file inside the plugin checkout, and stops there — nothing opens the template, so a template that
renders none of the declared headings registers clean. The order is currently data that no code
consults. 8-iv makes `add` assert that the note it just rendered carries the declared H2s in the
declared sequence, which is the first thing in the rollout that gives the key a consequence. That
assertion belongs on the write and not on registration, for the reason R11-D26 gave for not checking
base existence: registration must not fail a correct manifest, and a template is only proven by
rendering it.

**`human-only` has no bypass, and specifically no `--force`.** An action the manifest reserves for
a person is refused, full stop. A flag that lifts the refusal makes the key decorative and reads in
every review as though it protects something — the vacuous-check shape this rollout has now found
in a gate, a filter, and its own registration code. The escape hatch is not a flag: the human edits
the note in the vault, and 8-iii's freshness test is the standing proof that a direct write is
visible to the next query with no sync step. *Rejected: `--force` with a receipt.* A receipt records
that the line was crossed; it does not stop the tool from crossing it unattended, which is the only
thing `human-only` is for.

**A gap 8-i left, found by asking where `initial-status` gets written.** `validate_kind` requires
`initial-status` of every kind and accepts `transitions` and `human-only` from any kind, but never
checks that the kind declares a `status` **field** for any of them to act on. A kind can therefore
declare a status graph that governs nothing, and 8-iv would have no place to put the initial status
it is required to write. `status_filter` (`bin/sd:1412`) already refuses `--status` on a kind with
no `status` field for exactly this reason, on the read side. 8-iv closes it on the declaration side:
`initial-status`, `transitions` and `human-only` each require `status` in `fields`, refused at
registration with the key named (*`initial-status` is wrong here — corrected below*). This is a
tightening of 8-i's validator, landed in 8-iv because that is when it became falsifiable.

**Acceptance criterion, inverted from 8-iii's on purpose.** 8-iii wrote with `write_text` and read
through `sd`, so that an in-memory store could not pass it. 8-iv writes through `sd store add` and
reads the bytes back with `read_text`, asserting the note on disk. The load-bearing case is a
`set` against a note carrying a list value: the assertion is that the edited key changed **and the
list survived byte-identical**, which is the failure this decision exists to prevent and the one no
write-then-read-through-`sd` test can see.

**Refusals name the key that refused.** 8-i's symlink-loop lesson was that asserting one particular
sentence pins a wording that legitimately varies; the tests assert that a refusal names
`protected-fields`, or `floor`, or the offending field, and not that it phrases the complaint a
given way.

*Rejected: a real YAML parser for the write path.* `frontmatter()`'s own docstring already cites D-C1
for this, and the citation is to its rationale rather than its scope: D-C1 fixed the format of
**pack-owned** files and a vault note is not one, but the reason it gives — PyYAML is not in the
standard library, and `/usr/bin/python3` is 3.9.6 — does not care who owns the file. The dependency
would also be taken on to solve a problem the line edit does not have — a round trip through
any parser, strict or lossy, reformats what it did not change. *Rejected: enforcing `floor` at read
time.* A floor that filters what `list` shows leaves the under-floor note on disk and calls the
store clean.

**Correction, 2026-09-01, found by building it.** The paragraph above says `initial-status`,
`transitions` and `human-only` "each require `status` in `fields`". Two of the three do. The third is
wrong: `initial-status` is required of **every** kind by `KIND_REQUIRED`, so requiring a `status`
field for it would make a statusless kind unregisterable — which would in turn make
`status_filter`'s refusal unreachable code and
`test_status_on_a_kind_without_one_refuses_instead_of_matching_nothing` unconstructable, a shipped
test whose whole subject is a kind with no `status` field. The tightening lands on `transitions` and
`human-only` only, which genuinely govern nothing without a field to act on. Corrected here rather
than edited above, per this rollout's habit; `test_a_statusless_kind_is_still_registerable` pins the
third case so the overreach cannot come back.

**Standing rule 1.** *Incident:* `pack.py` preserved list-valued frontmatter by construction rather
than by decision, so nothing recorded that it mattered; the backbone that replaces it reads those
values through a parser that cannot see them. *Deletion criterion:* this record dies when no
declared kind is kept in a Markdown-with-frontmatter store — when the last `store.driver` is
something with a schema, the line-edit discipline has nothing left to protect.

**ID glossary (referenced above, defined in round artifacts):** R5-D4 = sdw meter retirement
(r5/06) · D-R4-8 = serving-root discipline (r4/05) · V4 = key-enumeration verification (r8b/03) ·
B5a = adoption-purity check (r4/05) · T1-g = guest-mode variant of the T1 handoff (r7/05).
