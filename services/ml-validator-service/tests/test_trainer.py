from __future__ import annotations

import unittest

import numpy as np

try:
    from src.trainer import _choose_threshold, _compute_feature_stats
except ModuleNotFoundError:  # pragma: no cover - optional dependency in local env
    _choose_threshold = None
    _compute_feature_stats = None


@unittest.skipIf(_choose_threshold is None, "trainer dependencies are not installed in current environment")
class TestTrainer(unittest.TestCase):
    def test_choose_threshold_in_range(self) -> None:
        y_true = np.array([0, 0, 1, 1, 1, 0], dtype=int)
        y_score = np.array([0.1, 0.2, 0.7, 0.8, 0.65, 0.4], dtype=float)
        t = _choose_threshold(y_true, y_score)
        self.assertGreaterEqual(t, 0.30)
        self.assertLessEqual(t, 0.80)

    def test_compute_feature_stats_contains_bins(self) -> None:
        import pandas as pd

        frame = pd.DataFrame(
            {
                "f1": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
                "f2": [1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9],
            }
        )
        stats = _compute_feature_stats(frame, ["f1", "f2"])
        self.assertIn("f1", stats)
        self.assertIn("bins", stats["f1"])
        self.assertGreaterEqual(len(stats["f1"]["bins"]), 3)


if __name__ == "__main__":
    unittest.main()
