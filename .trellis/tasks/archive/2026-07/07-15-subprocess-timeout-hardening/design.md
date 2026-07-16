# Design

Use two timeout tiers across pack-owned subprocess calls:

- 60 seconds for local git and filesystem-adjacent probes.
- 120 seconds for networked GitHub CLI calls and Trellis wrapper calls.

Python scripts use `sd_ai_command_pack_lib.run_command()` where they already
need command output or checked errors. Installer modules keep local wrappers so
they do not import consumer-shipped script modules. Shell scripts route through
`run_command_with_timeout` in `sd-ai-command-pack-shell-lib.sh` where available.

Timeout errors should identify the command, elapsed limit, and operation being
attempted. Optional probes may warn or return no result; required operations
must fail closed.
