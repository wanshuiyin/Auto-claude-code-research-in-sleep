#!/usr/bin/env python3
"""Regression tests for the ARIS toy project experiment."""

import os
import sys
import unittest


sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "scripts"),
)

import run_toy_experiment


class TestToyExperiment(unittest.TestCase):
    def test_label_depends_on_endpoints(self):
        self.assertEqual(run_toy_experiment.label((1, 0, 0, 1)), 1)
        self.assertEqual(run_toy_experiment.label((1, 0, 0, 0)), 0)

    def test_count_only_accuracy_matches_known_length_4_result(self):
        self.assertAlmostEqual(run_toy_experiment.optimal_count_only_accuracy(4), 0.625)

    def test_boundary_aware_is_exact(self):
        self.assertAlmostEqual(run_toy_experiment.boundary_aware_accuracy(16), 1.0)

    def test_longer_sequences_hurt_count_only_summary(self):
        short = run_toy_experiment.optimal_count_only_accuracy(4)
        long = run_toy_experiment.optimal_count_only_accuracy(16)
        self.assertGreater(short, long)


if __name__ == "__main__":
    unittest.main()
