# Housekeeping

Run SD end-of-stream housekeeping for the current repository.

1. Read `.agents/skills/sd-housekeeping/SKILL.md`.
2. Follow that skill exactly. It defines when finish-work must run, when the
   housekeeping script may merge or clean up a PR, and which safety checks stop
   the command. When the skill calls for the script, run
   `bash scripts/sd-ai-command-pack-housekeeping.sh`.
3. Report the condensed expected clean state plus any anomalies. Do not stage,
   commit, or push unrelated work.
