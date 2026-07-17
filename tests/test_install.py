from __future__ import annotations

import unittest

_LOCAL_TEST_MODULES = {
    "test_full_check",
    "test_generated_parity",
    "test_housekeeping",
    "test_install_audit",
    "test_install_core",
    "test_install_inspection",
    "test_pack_drift",
    "test_record_session",
    "test_remove",
    "test_review_learnings",
    "test_review_local",
    "test_review_preflight",
    "test_review_scope",
    "test_update_spec_kb",
}

try:
    from test_full_check import FullCheckTests
    from test_generated_parity import GeneratedParityTests
    from test_housekeeping import HousekeepingTests
    from test_install_audit import InstallAuditTests
    from test_install_core import InstallCoreTests
    from test_install_inspection import InstallInspectionTests
    from test_pack_drift import PackDriftTests
    from test_record_session import RecordSessionTests
    from test_remove import RemoveTests
    from test_review_learnings import ReviewLearningsTests
    from test_review_local import ReviewLocalTests
    from test_review_preflight import ReviewPreflightTests
    from test_review_scope import ReviewScopeTests
    from test_update_spec_kb import UpdateSpecKbTests
except ModuleNotFoundError as exc:
    if not __package__ or exc.name not in _LOCAL_TEST_MODULES:
        raise
    from .test_full_check import FullCheckTests
    from .test_generated_parity import GeneratedParityTests
    from .test_housekeeping import HousekeepingTests
    from .test_install_audit import InstallAuditTests
    from .test_install_core import InstallCoreTests
    from .test_install_inspection import InstallInspectionTests
    from .test_pack_drift import PackDriftTests
    from .test_record_session import RecordSessionTests
    from .test_remove import RemoveTests
    from .test_review_learnings import ReviewLearningsTests
    from .test_review_local import ReviewLocalTests
    from .test_review_preflight import ReviewPreflightTests
    from .test_review_scope import ReviewScopeTests
    from .test_update_spec_kb import UpdateSpecKbTests


class InstallTests(
    InstallCoreTests,
    InstallInspectionTests,
    GeneratedParityTests,
    ReviewLocalTests,
    FullCheckTests,
    ReviewPreflightTests,
    InstallAuditTests,
    RemoveTests,
    ReviewLearningsTests,
    UpdateSpecKbTests,
    ReviewScopeTests,
    RecordSessionTests,
    HousekeepingTests,
    PackDriftTests,
):
    """Compatibility facade for historical unittest node IDs."""


def load_tests(loader: unittest.TestLoader, tests: unittest.TestSuite, pattern: str | None) -> unittest.TestSuite:
    """Keep discovery from running this compatibility facade twice."""
    return unittest.TestSuite()


if __name__ == "__main__":
    unittest.main()
