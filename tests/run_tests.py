#!/usr/bin/env python3
"""Run offline contract tests; --strict makes documented defects fail the run."""
import os
import sys
import unittest
from pathlib import Path

if sys.version_info < (3, 10):
    sys.exit("Python 3.10 or newer is required to run the tests.")
if "--strict" in sys.argv:
    os.environ["ETHNOTRACE_STRICT"] = "1"
    sys.argv.remove("--strict")
sys.dont_write_bytecode = True
suite = unittest.defaultTestLoader.discover(str(Path(__file__).resolve().parent), pattern="test_*.py")
result = unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
