"""Studio (sd:6920, slice 2 of sd:6919): the creative projects under REPO_ROOT, each a folder with a project.json, and
each root's files. Read-only: the files open at /studio/files/<repo>/<path>, which `server._studio_file` answers (with a
Range for media). The stage strip and the actions are slices 3 and 4 (sd:6921, sd:6922)."""

from __future__ import annotations

from . import Api, Page


def _read(read):
    from ... import studio

    return studio.document(read.connection, now=read.now)


PAGE = Page(
    section="Studio",
    routes=("/studio",),
    html="studio.html",
    item="sd:6920",
    api=(Api("/api/studio", _read),),
    count="/api/studio",
)
