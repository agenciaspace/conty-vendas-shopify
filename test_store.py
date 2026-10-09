import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from core import Store, Problem

class StoreTests(unittest.TestCase):
    def test_persistence_and_rollback(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = tmp + '/data.db'
            store = Store(path)
            store.transact(lambda s: s.update(value=1))
            def bad(state):
                state['value'] = 2
                raise Problem('rejected')
            with self.assertRaises(Problem): store.transact(bad)
            store.close(); store = Store(path)
            self.assertEqual(store.transact(lambda s: s['value']), 1)
            store.close()
    def test_concurrent_connections_do_not_lose_updates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = tmp + '/data.db'
            store = Store(path); store.close()
            def increment(_):
                local = Store(path)
                try:
                    for _ in range(10): local.transact(lambda s: s.update(count=s.get('count', 0) + 1))
                finally: local.close()
            with ThreadPoolExecutor(max_workers=4) as pool: list(pool.map(increment, range(4)))
            store = Store(path)
            self.assertEqual(store.transact(lambda s: s['count']), 40)
            store.close()
