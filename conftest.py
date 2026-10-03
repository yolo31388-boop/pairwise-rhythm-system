"""让纯 Python 测试类也能使用 unittest 风格的断言方法。

tests/ 中的测试类未继承 unittest.TestCase，却调用了
self.assertIsNotNone，这里为其补齐 unittest 的断言方法。
"""

import unittest


def _install_assertions():
    try:
        from tests.test_rhythm import TestRhythmSystem
    except Exception:
        return
    for name in dir(unittest.TestCase):
        if name.startswith("assert") and not hasattr(TestRhythmSystem, name):
            setattr(TestRhythmSystem, name, getattr(unittest.TestCase, name))


_install_assertions()
