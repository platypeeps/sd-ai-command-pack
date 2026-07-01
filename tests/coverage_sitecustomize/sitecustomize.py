"""
Start coverage in installer subprocesses when the test runner requests it.

Python imports this special ``sitecustomize`` module automatically when this
directory is on ``sys.path``. The test harness adds it to ``PYTHONPATH`` for
subprocesses so coverage can collect data from installed scripts.
"""
import sys

COVERAGE_UNAVAILABLE_MESSAGE = (
    "sitecustomize: coverage.py not found or is too old, subprocess coverage will not be collected."
)

try:
    import coverage
except ImportError:
    print(
        COVERAGE_UNAVAILABLE_MESSAGE,
        file=sys.stderr,
    )
else:
    process_startup = getattr(coverage, "process_startup", None)
    if callable(process_startup):
        process_startup()
    else:
        print(
            COVERAGE_UNAVAILABLE_MESSAGE,
            file=sys.stderr,
        )
