import unittest
import dataclasses
from api._config_manager import ConfigManagerImpl  # noqa


class TestConfigManagerImpl(unittest.TestCase):
    def test_simple(self):
        @dataclasses.dataclass
        class SomeCfg:
            a: int
            b: str
            c: bool

        data = {'a': 42, 'b': 'foobar', 'c': True}
        res = ConfigManagerImpl.construct_instance(SomeCfg, data)
        self.assertIsInstance(res, SomeCfg)
        self.assertEqual(res.a, 42)
        self.assertEqual(res.b, 'foobar')
        self.assertIs(res.c, True)

    def test_missing(self):
        @dataclasses.dataclass
        class SomeCfg:
            a: int
            b: str = 'nope'
            c: bool = False
        data = {'a': 42, 'c': True}
        res = ConfigManagerImpl.construct_instance(SomeCfg, data)
        self.assertIsInstance(res, SomeCfg)
        self.assertEqual(res.a, 42)
        self.assertEqual(res.b, 'nope')
        self.assertIs(res.c, True)

    def test_simple_sequence(self):
        @dataclasses.dataclass
        class SomeCfg:
            a: list[int]
        data = {'a': [1, 2, 3]}
        res = ConfigManagerImpl.construct_instance(SomeCfg, data)
        self.assertIsInstance(res, SomeCfg)
        self.assertIsInstance(res.a, list)
        self.assertSequenceEqual(res.a, [1, 2, 3])

        @dataclasses.dataclass
        class SomeCfg:
            a: list[int]
        data = {'a': [1, 2, 3]}
        res = ConfigManagerImpl.construct_instance(SomeCfg, data)
        self.assertIsInstance(res, SomeCfg)

    def test_nested(self):
        @dataclasses.dataclass
        class InnerCfg:
            x: int
            y: int

        @dataclasses.dataclass
        class OuterCfg:
            inner: InnerCfg
        data = {'inner': {'x': 1, 'y': 2}}
        res = ConfigManagerImpl.construct_instance(OuterCfg, data)
        self.assertIsInstance(res, OuterCfg)
        self.assertIsInstance(res.inner, InnerCfg)
        self.assertEqual(res.inner.x, 1)
        self.assertEqual(res.inner.y, 2)

    def test_nested_sequence(self):
        @dataclasses.dataclass
        class InnerCfg:
            x: int
            y: int

        @dataclasses.dataclass
        class OuterCfg:
            inner: list[InnerCfg]

        data = {'inner': [{'x': 1, 'y': 2}, {'x': 1, 'y': 2}]}
        res = ConfigManagerImpl.construct_instance(OuterCfg, data)
        self.assertIsInstance(res, OuterCfg)
        self.assertIsInstance(res.inner, list)
        for inner in res.inner:
            self.assertIsInstance(inner, InnerCfg)
            self.assertEqual(inner.x, 1)
            self.assertEqual(inner.y, 2)


if __name__ == '__main__':
    unittest.main()
