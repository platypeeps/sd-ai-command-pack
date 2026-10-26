"""A fake of the system checkout's `satellite_refresh.py` for the dashboard's tests (sd:6044).

`request` writes the Refresh satellites row; `document` reads it back with no satellites: what each satellite answers
is the system checkout's to test.
"""

import json
import secrets

REQUEST = "refresh.request"


def request(connection):
    from sd_db import writes

    value = {"id": secrets.token_hex(8), "at": writes.now()}
    writes.set_setting(connection, REQUEST, json.dumps(value))
    return value


def document(connection):
    from sd_db import writes

    held = writes.read_settings(connection, [REQUEST]).get(REQUEST)
    return {"request": None if held is None else json.loads(held), "satellites": []}
