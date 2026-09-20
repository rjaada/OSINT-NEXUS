"""Recovery behavior for Neo4j becoming available after backend startup."""
import unittest
from unittest.mock import patch

import graph_store


class _Session:
    def __init__(self, fail=False):
        self.fail = fail

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def run(self, _query, *_args, **_kwargs):
        if self.fail:
            raise ConnectionError("bolt not ready")
        return self

    def single(self):
        return {"ok": 1}


class _Driver:
    def __init__(self, fail=False):
        self.fail = fail
        self.closed = False

    def session(self):
        return _Session(self.fail)

    def close(self):
        self.closed = True


class _GraphDatabase:
    calls = 0

    @classmethod
    def driver(cls, _uri, auth=None):
        del auth
        cls.calls += 1
        return _Driver(fail=cls.calls == 1)


class GraphStoreRecoveryTests(unittest.TestCase):
    def test_reconnect_recovers_after_initial_bolt_failure(self):
        _GraphDatabase.calls = 0
        with patch.object(graph_store, "GraphDatabase", _GraphDatabase):
            store = graph_store.GraphStore("bolt://neo4j:7687", "neo4j", "secret")
            self.assertFalse(store.status()["connected"])
            self.assertTrue(store.reconnect())
            self.assertTrue(store.status()["connected"])
            self.assertIsNone(store.status()["error"])


if __name__ == "__main__":
    unittest.main()
