"""Studio (sd:6920, sd:6921; slices 2 and 3 of sd:6919): the creative projects under REPO_ROOT, each a folder with a
project.json, and each root's files. The files open at /studio/files/<repo>/<path>, which `server._studio_file` answers
(with a Range for media). Pin and Hide post /api/studio/view, Documents' view state; a stage move posts
/api/items/<n>/stage, which `server.action_route` sends to `studio.move_stage`. The actions are slice 4 (sd:6922)."""

from __future__ import annotations

from . import Api, Page


def _read(read):
    from ... import studio

    return studio.document(read.connection, now=read.now)


def _view(payload, principal):
    from ... import studio

    return studio.view_request(payload)


PAGE = Page(
    section="Studio",
    routes=("/studio",),
    html="studio.html",
    item="sd:6920",
    api=(Api("/api/studio", _read), Api("/api/studio/view", write=_view)),
    count="/api/studio",
)
