#!/usr/bin/env python3
"""Regression tests for the GMU implementation scaffold configs."""

import os
import sys
import unittest


ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)

from lib.experiment_config import get_run, validate_configs


class TestExperimentConfig(unittest.TestCase):
    def test_validation_passes(self):
        self.assertEqual(validate_configs(), [])

    def test_r001_is_clean_retrain_oracle(self):
        run = get_run("R001")
        self.assertEqual(run["kind"], "vision")
        self.assertEqual(run["method"], "retrain_oracle")
        self.assertEqual(run["target_family"], "clean")

    def test_r008_is_diagnostic_bundle(self):
        run = get_run("R008")
        self.assertEqual(run["kind"], "diagnostic")
        self.assertIn("T_noise", run["target_family"])
        self.assertIn("T_blur", run["target_family"])
        self.assertIn("T_digital", run["target_family"])


if __name__ == "__main__":
    unittest.main()
