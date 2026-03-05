from __future__ import annotations

import unittest

try:
    from src.drift import _psi
except ModuleNotFoundError:  # pragma: no cover - optional dependency in local env
    _psi = None


@unittest.skipIf(_psi is None, "drift dependencies are not installed in current environment")
class TestDrift(unittest.TestCase):
    def test_psi_near_zero_when_distribution_same(self) -> None:
        expected = [0.2, 0.3, 0.5]
        current = [0.2, 0.3, 0.5]
        self.assertAlmostEqual(_psi(expected, current), 0.0, places=8)

    def test_psi_positive_when_distribution_shifted(self) -> None:
        expected = [0.2, 0.3, 0.5]
        current = [0.5, 0.3, 0.2]
        self.assertGreater(_psi(expected, current), 0.0)


if __name__ == "__main__":
    unittest.main()
