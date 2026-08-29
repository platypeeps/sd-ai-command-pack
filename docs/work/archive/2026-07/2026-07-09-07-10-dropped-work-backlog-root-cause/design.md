# Dropped Claude Work-Backlog Install Root Cause Design

Historical session output confirms that the failure was caused by automatic
platform detection, not by a write or gitignore failure. Both affected repos
had the `.claude/` anchor and existing SD commands, but no active Trellis Claude
marker. The installer therefore skipped the whole Claude platform, retained
the old receipt entries, and had no old entry to retain for the newly added
work-backlog command.

The desired safety property is generic: a selected manifest target must either
be installed and recorded, or the installer/audit must report why it was not.
No consumer-specific branch should exist in production installer code.

The regression fixture should model a two-version refresh: first install a
manifest without the new Claude command, then remove the active Claude marker
and refresh with the current manifest. Preserve the installer's existing
auto-detection semantics and prove that current manifest completeness rejects
the resulting partial state because older retained Claude receipt entries
infer that platform. Also prove that the explicit expected-platform audit
fails without depending on that inference. Fleet tooling must continue to pass
the same explicit platform set to both installation and audit.
