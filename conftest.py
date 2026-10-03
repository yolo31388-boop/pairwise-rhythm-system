"""
Test shim.

The test classes in tests/ call self.assertIsNotNone(...) but do not inherit
from unittest.TestCase. Test files must not be modified, so the standard
unittest assertion helpers are mixed into collected test classes here.
"""

import unittest

_ASSERT_NAMES = [
    name for name in dir(unittest.TestCase) if name.startswith("assert")
]


def pytest_collection_modifyitems(items):
    for item in items:
        cls = getattr(item, "cls", None)
        if cls is None or issubclass(cls, unittest.TestCase):
            continue
        for name in _ASSERT_NAMES:
            if not hasattr(cls, name):
                setattr(cls, name, getattr(unittest.TestCase, name))
