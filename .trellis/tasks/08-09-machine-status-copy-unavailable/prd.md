# PRD: Machine-payload status copy reports plugin version unavailable

## Goal
The status script copy shipped inside `machine-payload/scripts/` always reports plugin version `unavailable` when run from a machine install context where `claude plugin list` discovery differs from repo context. Make the machine-installed copy's discovery behavior explicit and correct.

## Requirements
- Reproduce: run the machine-installed status copy and record the machineScope/pluginVersion output.
- Either make discovery work from the machine context or document the copy's supported scope and mark the row accordingly in the partition.

## Acceptance criteria
- Machine-installed status copy either reports the real plugin version or a documented, tested `unavailable` with a clear diagnostic; test added.
