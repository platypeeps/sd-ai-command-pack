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
  skills/sd-*/SKILL.md  12 commands + templates (prd, design, implement, decision, work-README)
  skills/sd-*/SKILL.md  + 64 merged skills, renamed se-* → sd-* at fold (67 on disk − 3 retired:
                        se-help, se-brand-voice, se-humanizer — retired under old names)
  agents/               sd-rust-write/fill/reviewer, sd-claim-verifier, sd-source-reader +
                        vendored kimi-review/-challenge/-ask/-swarm/-swarm-write, codex-rescue,
                        example-reviewer — all with declared tools:
  bin/                  sd_lib.py (detection, derive_status), sd_route.py, sd-check, sd-docs-lint,
                        sd-pr-state, sd-review(+-local), sd-status, sd-spec, sd-map, sd-handoff,
                        sd-trackers, sd-handoff-restore (hook), sd CLI (plugin|store|issue|config groups),
                        migrate-* (temp)
  dashboard/            stdlib HTTP server + one JS file + sd-dashboard CLI (≤2,500 LOC cap)
  actions/              docs-lint + review-route composite actions (SHA/tag-pinned, opt-in only)
  docs/work|spec|decisions   dogfood
  tests/                ~3k lines: install, docs-lint, route fixtures, store invariants,
                        renderer parity across 3 platforms (+Antigravity once P1 passes), verb-inventory, LOC caps
```

**LOC discipline (one decision record, restated after the feasibility audit):** bin/ ceiling
**8,000** (accepted by user 2026-08-29). Itemized: core (sd_lib, sd_route, sd-check, docs-lint, pr-state, status, spec,
trackers incl. ~90 lifted Jira LOC) ~1,800 · review lane **1,400 sub-cap** · r2 dashboard
glue/index +900 · r4 sd-map +400 · r5 plugin/store **1,400 sub-cap** · r7 Lane B handoff +120 ·
R10-D3 packet writer + restore hook + identity checks +250 · R10-D1 worktree/codex-exec/budget/
draft-PR lane +450 · R10-D2 draft-convert +40 · 45-day sweep +40 · google.accounts resolution
+50 · env reads +20 = **~6,870**, leaving ~1,100 headroom. The earlier 6,000 and 6,500 figures
were both busted on paper; setting 8,000 now is the honest number, still <1/11 of today's 95k.
Temporary `migrate-*` is **outside** the cap (deleted at steps 7/11), tracked by its own 1,500
ceiling until then. dashboard/ ≤ **2,500** (credible: 457 lifted + one JS file). Caps are CI tests; a cap is never raised in the PR
that busts it. Still <1/10 of today's 54k scripts + 30k router + 11k installer.

### Commands (12 — grown from 8, each growth carried by a decision record)

| Command | Purpose |
|---|---|
| `sd-plan <slug>` | Interview → `<work>/<date>-<slug>/prd.md` (+design/implement when warranted); ends with `sd-review --scope planning` (codex second-model lane, r8) writing `## Review`; `planning → ready` only with no open BLOCKING line; creates branch, records `branch:`; first commit sweeps merged items — and items idle in `planning` >45 days with no `branch:` (R10-D1) — to `archive/YYYY-MM/`. Flags: `--decision`, `--work-dir`, `--worktree`, `--from gh:o/r#N\|jira:KEY`, `--from-suggestion`, `--from-proposal` |
| `sd-check` | Typed deterministic runner over repo-native entrypoints (`check:` in local block, else autodetect Makefile/Taskfile/package.json/Cargo/pyproject) |
| `sd-review` | sd-check → route() → local providers on exact diff; findings dispositioned locally, never posted; `--scope worktree\|branch\|pr\|planning`, `--challenge` (kimi-challenge or codex adversarial prompt), `--explain`, `--dry-run`, `setup-github` subcommand (opt-in CI routing, r3) |
| `sd-ship` | Verify acceptance → sd-spec → docs-lint → commit (enumerated paths only, never `add -A`) → push → PR with `Work:` line → request Copilot once per head → settle loop → `gh pr merge --squash -t "<title> (#N)" -b "<body>"` (wip-eraser, r7). **No write after settled-green.** `--pr N`, `--backlog` (ported work-backlog loop, r6 D12), `--agent claude\|codex` + `--jobs N` + `--cap N` + `--dry-run` (autonomous lane, R10-D1), `--tier`, `--no-github` |
| `sd-spec` | Update `docs/spec/**` on the PR branch; `--retro` appends review-learnings |
| `sd-status` | Read-only: derived status, open PRs, detected setup + protection gaps — enforcement state first (`enforce_admins`, required contexts vs the jobs CI runs, PR-review requirement), then squash-message + rebase-merge flags (r7), resumable-handoff section (pending local packet for this directory + Lane B branches derived from origin), backend availability, legacy residue with exact removal commands, pack banner |
| `sd-deps` | Batch-triage dependabot/renovate PRs |
| `sd-help` | Runtime catalog of installed sd-* skills + registered plugins |
| `sd-suggest` | File framework improvements to the configured tracker (gh dedup via list API; local draft deleted on successful filing) — r2 N7 |
| `sd-skill-adopt <path\|url\|->` | One-command skill intake: safety pre-screen → lint → canonical transform → provenance → write per `--scope pack\|user`; `--from-repo --list` for external-repo survey (report-only) — r2 N8 |
| `sd-map` | Supporting artifacts (repomix/index/kb) into `~/.local/share/sd-ai-command-pack/<repo-id>/artifacts/` — out-of-tree by construction, flock'd, never a gate, never scheduled — r4 |
| `sd-handoff [--push] [--park] [--show]` | **Default (R10-D3, Lane A):** write the local session packet for this directory, no git touched; then `/clear` restores it. `--show` prints the pending packet (the load path for Codex/OpenCode sessions, which have no SessionStart hook). `--push` (Lane B): additionally append `handoff:` to `## Log`, commit+push WIP to carrier branch, print restart one-liner; `--park` applies to Lane B only. Guards: settled-green refusal, branch-scoped stash check, open-PR draft+no-re-review (R10-D2). 60-day deletion criteria on both lanes |

CLIs (not skills): `install.py`, `sd-dashboard serve|install|index [--dump]|item set-status|export
--obsidian`, `sd plugin|store|issue|config` verb groups (r5), temporary `migrate-trellis`/`migrate-vault`.
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
check is keyed on kind. Vendored agents (kimi-*, codex-rescue, example-reviewer) keep their
upstream names — the one-prefix rule covers merged se-* surfaces, not vendored ones.

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

Stdlib ThreadingHTTPServer + one vanilla JS file; ~457 LOC lifted verbatim from dashboard.py. Tabs:
Now · Work · PRs · Issues · Repos · Queues · Suggestions · Skills · Sessions · plugin tabs
(`dashboard.d/*.py` contract incl. `mounts`). Now screen = externally derived facts only. Every UI
mutation maps 1:1 to a bin/ command (RUN_ALLOWLIST); server never commits/pushes/runs agents.
Sessions tab = `git worktree list` + running sd-* processes (replaces Trellis `.runtime/sessions`
— the Trellis-hooks answer: **no hook carries over**). Lands on **:8768 beside** the system
dashboard; per-tab parity checklist gates the swap to :8767 at step 6b. Deferred behind standing
rule 1: FTS/Search, log streaming, session launcher. D14 decides phone access (today's tailnet
iOS PWA writes are live — loopback-only is a knowing regression; option (c) keeps ack/queue-set
POSTs under token).

### Review routing + pluggable backends (r3; revises D4)

D4 stands for the *mandatory* footprint: Action, receipt protocol, consumer installer, labels,
variables retired. The routing model survives as one config table + pure
`route(paths, lines, draft, policy) → Plan`: categories (required-first, docs-skip as allow-list
minus a non-removable `never_skip` deny-list), 800-line threshold, sensitive globs, draft policy,
tier chains. Backends on the existing Provider seam:

| Backend | Kind | Cost | Default role |
|---|---|---|---|
| codex | local CLI (hardened invocation verbatim from review-local.py:1983-2018) | $0 (ChatGPT sub; **rate-limited outcome distinct from unavailable**, r8). **Subscription only, never API billing (R10-D4, user 2026-08-29):** verified precedence in codex-rs `load_auth()` is `CODEX_API_KEY` env → ephemeral → `CODEX_ACCESS_TOKEN` env → `auth.json`; `OPENAI_API_KEY` is *not* read by the CLI. This machine: `auth_mode: chatgpt`, no key in auth.json, `codex login status` = "Logged in using ChatGPT". Preflight before every codex call (review, planning, `--agent codex`): scrub `CODEX_API_KEY`/`CODEX_ACCESS_TOKEN` from the subprocess env (`build_tool_environment` inherits `os.environ` today), assert auth.json `auth_mode == chatgpt`, refuse otherwise — a run can never silently fall over to metered billing | heads every chain; default planning-review provider |
| prism | openai-compatible | ~low | standard fallback |
| gito | openai-compatible | per-file | deep fallback |
| kimi | argv row (+ vendored agents for swarm/challenge) | low | `--challenge`, fan-out |
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
`sd plugin add` — no disk scanning, no repo writes. Repo-scoped skills ARE the contract (no
`sd plugin sync` copy machinery). **sd-writing-pack is the first plugin**: pack.py 2,532 → ~1,250
LOC (store verbs/gh/config/help/adversarial deleted → backbone; pieces/build-html/companion ledger
stay). Vault-side routines (intel-brief, intel-weekly, tips-weekly, tips-accept,
aaif-brief-compile, market-watch) retargeted **before** any deletion (step 9). pp-* is the named
second consumer that validates the interface before any freeze.

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
  `sd-review-test` are retired at step 4; `testme` has no default branch. `platypeeps/
  google_workspace_mcp` is the one open call — active PR flow (41 merges/60d), no protection —
  left to the user rather than changed unilaterally.
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
framework dashboard** via `dashboard.d/*.py` plugin tabs (TaskNotes/Vault, Toolbox, Briefs, Jira
personal, Research via mounts) — code + pinned actions live in `~/repos/system`. Only the
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
- **R9b-D3** step 3a: delete 19 gemini TOMLs, re-render 0 (`test ! -e ~/.gemini/commands/sd`);
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
12 commands, old se-* renders deleted; retired skills keep historical se- names in records only.

**Proposed defaults — all accepted by user 2026-08-29 (R11-D0), now decided as written; exceptions noted inline:**
- D3 import 386 archived tasks under `docs/work/archive/` · D5 protection: report + opt-in
  `--set-protection` · D7 mezmo_benchmark deferred (freeze shim) · D8 planning checklist = 10
  dimensions via codex lane · D9 journals: give up cross-references
- R2: D12 queue dispositions (Skill Proposals → files, rest keep) · D13 suggestion tracker =
  GitHub issues on pack repo · **D14 phone access (a/b/c — (c) keeps today's PWA writes)** ·
  D17 intents vs immediate commit · D19 Sessions tab + claude-mem · D22 superseded by R9b-D4
  (Antigravity supported)
- R3: D10/D-C1 **decided: JSON** for all pack-owned config/manifests (see storage table) · D13
  system collectors → index · D16 **revised (user, 2026-08-29): pack first, then the other `mode: full` repos in the same initial trial** — pack PR proves the route action green once, then one `setup-github` PR per remaining full-mode platypeeps repo lands in the same step-3-c wave; no prolonged single-repo trial · D20 fork/dependabot red-check
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

**R11-D4 (user, 2026-08-29) — the macOS CI leg is dropped for the rollout, and restored at step 7.**

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

What is lost, named rather than waved away: macOS-only Python behaviour, filesystem
case-insensitivity, and platform-specific path handling are unverified in CI until the leg
returns. What still covers macOS meanwhile: the bash 3.2 syntax gate in `lint` runs against
`/bin/bash`, the interpreter macOS ships, and the maintainer's `make check` runs on macOS before
every push -- which is how several defects in this rollout were already caught locally rather
than in CI.

Restore criterion (standing rule 1 applied to a removal rather than an addition): the leg and its
required context come back at **step 7**, which already carries "verify protection" on its
checklist. If step 7 lands without the leg restored, the rollout has quietly kept a temporary
measure, and CONTRIBUTING's "restored at step 7" sentence becomes the falsifiable record that it
did not.

**ID glossary (referenced above, defined in round artifacts):** R5-D4 = sdw meter retirement
(r5/06) · D-R4-8 = serving-root discipline (r4/05) · V4 = key-enumeration verification (r8b/03) ·
B5a = adoption-purity check (r4/05) · T1-g = guest-mode variant of the T1 handoff (r7/05).
