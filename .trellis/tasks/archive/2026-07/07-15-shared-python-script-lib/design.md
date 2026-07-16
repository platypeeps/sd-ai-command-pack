# Design

Add a small stdlib-only Python module at `scripts/sd_ai_command_pack_lib.py`
and ship the same file through `templates/scripts/`. Pack-owned Python helpers
can import it from their script directory after installation, so consumers do
not need packaging metadata or `PYTHONPATH` setup.

The first shared surface is intentionally narrow: command display helpers,
bounded subprocess wrappers, git/gh runners, and repository-root resolution.
This keeps the helper useful for repeated error-prone code without turning it
into a broad framework. The installer continues to own installer-specific file
operations and manifest handling.

Templates remain the distributed source of truth. The helper is listed in
`manifest.json`, scanner tables, installed-target receipts, and coverage floors
so future installs include it and future drift is visible.
