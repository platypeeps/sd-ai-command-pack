from __future__ import annotations

import unittest

try:
    from test_full_check import FullCheckTests
    from test_generated_parity import GeneratedParityTests
    from test_housekeeping import HousekeepingTests
    from test_install_audit import InstallAuditTests
    from test_install_core import InstallCoreTests
    from test_pack_drift import PackDriftTests
    from test_record_session import RecordSessionTests
    from test_remove import RemoveTests
    from test_review_learnings import ReviewLearningsTests
    from test_review_local import ReviewLocalTests
    from test_review_preflight import ReviewPreflightTests
    from test_review_scope import ReviewScopeTests
    from test_update_spec_kb import UpdateSpecKbTests
except ModuleNotFoundError:
    from .test_full_check import FullCheckTests
    from .test_generated_parity import GeneratedParityTests
    from .test_housekeeping import HousekeepingTests
    from .test_install_audit import InstallAuditTests
    from .test_install_core import InstallCoreTests
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
