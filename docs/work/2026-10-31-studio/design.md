---
title: A Studio page for creative projects and their artifacts
created: 2026-10-31
item: sd:6919
branch: build/sd-346
---

# Design — studio

The item's row holds status, progress and decisions; this page holds the shape.

## Problem

Creative projects (shirts, songs, episodes) live in a fleet repository as folders of prompts, PNGs, audio and video.
Nothing on the dashboard lists them, shows their artifacts, or says what stage each one is at.
The operator works them from the shell: finds the folder, opens the images, runs the checks by hand.

## Approach

One page, `/studio`: the project list on the left, the selected project's detail on the right (the Today row-detail
ruling). It reuses what exists and adds no store.

| Concern | Reuses | Shape |
| --- | --- | --- |
| Which projects | the Documents scan of `REPO_ROOT` | every `project.json` under a registered repository under `REPO_ROOT`; the page names no repository in its source |
| Project facts | a tracked `project.json` per project folder | `kind` (`shirt`, `song`, `episode`), `title`, `brief`, and artifact roots by role: `reference`, `candidates`, `selected`, `print`, `stickers`, `previews`, `media` |
| Stage | one sd item per project, as Writing pieces | the item's `stage` and its notes; `project.json` names the item as `item: sd:<id>` |
| Gallery | `designs.resolve` and the mockup policy | each root's files, listed from disk (PNGs are untracked: never read git for media), served by the same segment and stay-inside rules, under a sandbox policy |
| Audio and video | the gallery route | `Range: bytes=` answered with 206 and `Content-Range` for `.mp4`, `.mp3` and `.wav`, so a player can seek |
| Pin and hide | Documents' view state | keyed `<project>/<file>`, so a rejected candidate hides without a delete |
| Checks and pipelines | `/api/actions/run` | new `ACTIONS` rows with fixed argv, bounded and logged as every Run is |
| Creative work | `fix_session` | a claude session in herdr, given the brief as fixed text |

Stage strips, one per kind, in order:

| Kind | Stages |
| --- | --- |
| shirt | brief, candidates, selected, print export, approved, ordered |
| song | lyrics, suno, selections, film, delivered |
| episode | idea, outlined, scripted, in_production, published |

Actions, each a fixed argv run in the project's repository:

| Action | Step |
| --- | --- |
| `studio.check` | `make check` |
| `studio.episode` | `tools/episode.py check` (in the project repo) or `pack`, with the episode the project names |
| `studio.song` | `songs/tools/song_pipeline.py` `import`, `assemble`, `runway`, `validate` or `suno-export` |
| `studio.session` | claude in herdr with the brief (`fix_session` pattern) |

Rejected: a Studio table in the database. The folder already holds the facts and the item holds the stage; a third
copy would drift from both.

Rejected: listing artifacts from git. The PNGs and media are untracked by design, so git sees none of them.

## Non-goals

- No order, upload or purchase action: the page never spends money or publishes.
- No editing of `project.json` from the page; the session or the shell edits it.
- No thumbnails or transcoding: the browser scales what it is served.
- No `project.json` files in this repository: fun-ai-stuff gets them in its own item, after this design.

## Failure table

Slices 3 and 4 move state: a stage on the item, a run of an action.

| Step | State moved | Failure | Recovery | Test |
| --- | --- | --- | --- | --- |
| Read projects | nothing | a `project.json` that does not parse, or names a root outside its folder | the project lists with its error; that root is dropped | a bad file and an escaping root each list as an error |
| Serve a file | nothing | a path that leaves the root, a dotfile, an unknown type | 404, as `designs.resolve` | the `designs` resolve cases, run against a studio root |
| Serve a range | nothing | a range past the end, a malformed or multi-range header | 416 for past the end; the whole file (200) for one it cannot parse | each header shape answers its status and bytes |
| Move a stage | the item's `stage` and a note | a stale revision; a stage not next on the kind's strip | 409 or 400; nothing written | a stale click and a skipped stage are each refused |
| Run an action | a journal entry; the tool's own writes | the step passes its bound | 504 `outcome: unknown`, as every Run; the journal names it | a slow fake action answers 504 |
| Start a session | a herdr workspace and a note | herdr down; the note fails after the launch | 503 with herdr's words; 503 naming the pane | the `fix_session` cases, with the studio prompt |

## Slices

1. This design. Leaves nothing new running.
2. Range serving and the read-only gallery: `/studio` lists projects and shows each root's files; media seeks.
   Works on every machine with a fleet checkout; one with no `project.json` shows an empty list.
3. Stage strip and sd items: the strip per kind, a stage move through the item, pin and hide.
4. Actions: the `studio.*` rows in `ACTIONS` and the session start.

fun-ai-stuff writes a `project.json` per project in its own item, after slice 1, so slice 2 has data to show.

## Acceptance criteria

- [ ] A `project.json` under `REPO_ROOT` lists on `/studio`; one that does not parse lists with its error.
- [ ] Every gallery file the page links answers 200; a path outside its root answers 404.
- [ ] `Range: bytes=0-99` on an `.mp4` answers 206 with 100 bytes and `Content-Range: bytes 0-99/<size>`.
- [ ] A stage move with a stale revision answers 409 and writes no note.
- [ ] No action's argv holds a value the page sent other than a project the server found and a verb from its list.
- [ ] No route places an order, uploads a file or makes a purchase.

## Risks

- Media files are large. Range keeps a seek cheap, but a full `.wav` read still streams the whole file; accepted.
- A `project.json` is the operator's own text; the page draws it as text and runs nothing it names but a verb from
  the fixed list.
- The gallery serves untracked files from a checkout. The `designs.resolve` rules and the sandbox policy keep it to
  the roots `project.json` names; a root that symlinks out is a 404.
- The stage strips are fixed per kind. A fourth kind needs a code change; accepted until one exists.
