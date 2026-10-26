"""sd:6158. A test's wall-clock budget grows with the load per core, within bounds."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from sd_db.testing import patience
from sd_db.testing.patience import MOST, factor


def loaded(load: float, cores: int | None = 16):
    return patch("os.getloadavg", return_value=(load, 0.0, 0.0)), patch("os.cpu_count", return_value=cores)


class Patience(unittest.TestCase):
    def at(self, load: float, cores: int | None = 16) -> float:
        first, second = loaded(load, cores)
        with first, second:
            return factor()

    def test_a_quiet_machine_keeps_the_budget(self):
        self.assertEqual(self.at(0.0), 1.0)
        self.assertEqual(self.at(15.9), 1.0)

    def test_the_budget_grows_with_the_load_per_core(self):
        self.assertEqual(self.at(80.0), 5.0)
        first, second = loaded(48.0)
        with first, second:
            self.assertEqual(patience(5), 15.0)

    def test_the_growth_stops_at_the_cap(self):
        self.assertEqual(self.at(1e9), MOST)
        self.assertEqual(self.at(float("inf")), MOST)

    def test_an_unknown_core_count_counts_one_core(self):
        self.assertEqual(self.at(3.0, None), 3.0)

    def test_a_load_that_cannot_be_read_errs_long(self):
        with patch("os.getloadavg", side_effect=OSError("no load")):
            self.assertEqual(factor(), MOST)


if __name__ == "__main__":
    unittest.main()
