# Dropped Claude Work-Backlog Install Root Cause Design

The investigation should stay inside installer tests unless live consumer state
is needed for evidence. Build the smallest fixture that models the historical
failure: Claude selected, `.claude/` treated as local or gitignored state, and
the work-backlog command absent from all three install records.

The desired safety property is generic: a selected manifest target must either
be installed and recorded, or the installer/audit must report why it was not.
No consumer-specific branch should exist in production installer code.

If the exact omission cannot be reproduced, the task should still produce a
durable negative result explaining which hypotheses were tested and why the
0.8.5 expected-target audit covers the historical symptom.
