"""
Start coverage in installer subprocesses when the test runner requests it.

Python imports this special ``sitecustomize`` module automatically when this
directory is on ``sys.path``. The test harness adds it to ``PYTHONPATH`` for
subprocesses so coverage can collect data from installed scripts.
"""
import sys

try:
    import coverage

    coverage.process_startup()
except (ImportError, AttributeError):
    print(
        "sitecustomize: coverage.py not found or is too old, subprocess coverage will not be collected.",
        file=sys.stderr,
    )
