# Studio

Studio is at `/studio` (sd:6920, slice 2 of sd:6919; shape in
`docs/work/2026-10-31-studio/design.md`): the creative projects, one row per
`project.json` in a registered repository under `REPO_ROOT`, found a few
folders deep. `GET /api/studio` (`studio.document`) lists each project's
kind (`shirt`, `song`, `episode`), title, brief, item (`sd:<n>`) and its
artifact roots, a map from a role (`reference`, `candidates`, `selected`,
`print`, `stickers`, `previews`, `media`) to a folder inside the project.
A file that parses with no `kind` is another tool's and is not listed.
A file that does not parse lists with its error; an unknown kind or role,
or a root that leaves the project folder, lists as a problem and the root
is left out. A machine with no `project.json` shows an empty list.

A repository's key is its folder name. Two registered repositories of one
name each take their path under `REPO_ROOT` with `-` for `/`
(`alpha-tools`, `beta-tools`), so both are read (sd:7392); a key two still
share is served for neither and listed as a problem. When the scan names
a problem and finds no project, the banner says how many repositories it
read.

Details shows each root's images, audio and video, listed from disk: the
media is untracked, so git is never asked. Each file is served at
`/studio/files/<repo>/<path in the repository>` under `designs.resolve`'s
rules (every segment a name, the file inside the repository) and only
inside a root a project names; each answer carries a sandbox policy.
`.mp4`, `.mp3` and `.wav` answer `Range: bytes=` with 206 and
`Content-Range`, so a player seeks; a range past the end is 416, and a
header that does not parse gets the whole file.

Details draws the kind's stage strip (sd:6921): shirt is brief,
candidates, selected, print_export, approved, ordered; song is lyrics,
suno, selections, film, delivered; episode is idea, outlined, scripted,
in_production, published. The stage is the `stage` of the item the
`project.json` names. Next stage posts `/api/items/<n>/stage` with the
revision the page read, the route Writing and Watches post: the server
sends an item that is no writing piece and that one project names to
`studio.move_stage`. It moves one stage forward and writes a comment
note in the same transaction. A stale revision answers 409, any other
stage 400, and neither writes. An item at a stage off its strip is
refused and listed as a problem; the shell moves it.

Each gallery file has Pin and Hide, Documents' view state keyed
`studio/<repo>/<path>` and written by `POST /api/studio/view`
(`{"file", "pinned" | "hidden"}`). A pinned file leads its root; a
hidden one folds under the root's Hidden. A file the gallery does not
serve is refused. The `studio.*` actions are slice 4 (sd:6922).
