"""Start coverage in installer subprocesses when the test runner requests it."""

from __future__ import annotations

try:
    import coverage
except ImportError:
    coverage = None

if coverage is not None:
    coverage.process_startup()
