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

Details shows each root's images, audio and video, listed from disk: the
media is untracked, so git is never asked. Each file is served at
`/studio/files/<repo>/<path in the repository>` under `designs.resolve`'s
rules (every segment a name, the file inside the repository) and only
inside a root a project names; each answer carries a sandbox policy.
`.mp4`, `.mp3` and `.wav` answer `Range: bytes=` with 206 and
`Content-Range`, so a player seeks; a range past the end is 416, and a
header that does not parse gets the whole file.

The page writes nothing. The stage strip, pin and hide are slice 3
(sd:6921); the `studio.*` actions are slice 4 (sd:6922).
