# Review test evidence

Read this when reviewing a regression test or its reported result.

For equality assertions, name what must differ for the assertion to fail.
A clock tick, filesystem order, or impossible difference does not establish the intended property.

Assert the required output directly.
For reproducible archives, check normalized archive timestamps and zero gzip MTIME.
Matching outputs from two builds within one second do not prove reproducibility.

For a specific defect, introduce that defect in an isolated fixture or reversible mutation.
Run the target test and quote the failing result.
Restore the implementation and confirm the passing control.
Use deterministic synchronization for process tests instead of machine-speed assumptions.

A refusal test also needs a positive success control.
An absence assertion alone can pass after a usage error, missing dependency, or early crash.
Check the successful exit code and output unique to the intended path before asserting absent refusal text.

Static checks catch identical operands, literal-only assertions, and missing assertions.
They cannot prove that a realistic defect makes a test fail.
Report mutation evidence separately from ordinary test success.
