import tempfile
import unittest
from core import Store, Problem, instant
from domain import dispatch

class SalesTests(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.now = instant('2026-10-09T15:00:00Z')
        self.call('/creators', id='alice', coupon='ALICE')
        self.call('/creators', id='bob', coupon='BOB')
    def tearDown(self): self.store.close()
    def call(self, path, **data):
        return self.store.transact(lambda s: dispatch(s, 'POST', path, {'shop': 'shop1', **data}, self.now))
    def order(self, **overrides): return self.call('/orders', **dict(dict(id='o1', total_cents=10000, coupon='alice', utm_creator='bob', status='paid'), **overrides))
    def refund(self, **overrides): return self.call('/refunds', **dict(dict(id='r1', order_id='o1', amount_cents=3000), **overrides))
    def get(self): return self.store.transact(lambda s: dispatch(s, 'GET', '/orders/shop1/o1', {}, self.now))
    def test_coupon_beats_utm_and_order_duplicate_does_not_credit_twice(self):
        self.order(); result = self.order()
        self.assertEqual(result['attribution']['creator_id'], 'alice')
        self.assertEqual(result['attributed_cents'], 10000)
        self.assertEqual(len(result['ledger']), 1)
    def test_partial_then_repeated_then_full_refund(self):
        self.order(); self.refund(); self.refund()
        self.assertEqual(self.get()['net_cents'], 7000)
        self.refund(id='r2', amount_cents=7000)
        result = self.get()
        self.assertEqual(result['attributed_cents'], 0)
        self.assertEqual(len(result['ledger']), 3)
        self.assertEqual(result['status'], 'refunded')
    def test_refund_before_order_and_duplicate_after_order(self):
        self.assertEqual(self.refund()['state'], 'pending')
        result = self.order()
        self.assertEqual(result['net_cents'], 7000)
        self.assertEqual(self.refund()['applied_cents'], 3000)
        self.assertEqual(self.get()['net_cents'], 7000)
    def test_refunds_capped_without_discarding_excess(self):
        self.refund(amount_cents=9000)
        self.refund(id='r2', amount_cents=9000)
        result = self.order()
        self.assertEqual(result['refunded_cents'], 10000)
        self.assertEqual(result['refunds'][1]['excess_cents'], 8000)
        self.assertEqual(sum(e['cents'] for e in result['ledger']), 0)
    def test_unknown_coupon_falls_back_to_known_utm(self):
        self.assertEqual(self.order(coupon='UNKNOWN')['attribution']['creator_id'], 'bob')
    def test_unknown_origins_remain_unattributed(self):
        self.assertIsNone(self.order(coupon='', utm_creator='unknown')['attribution']['creator_id'])
    def test_conflicting_replay_and_negative_money_rejected(self):
        self.order(); self.refund()
        for fn in [lambda: self.order(total_cents=20000), lambda: self.refund(amount_cents=200), lambda: self.refund(id='r2', amount_cents=-1)]:
            with self.assertRaises(Problem): fn()
        self.assertEqual(self.get()['net_cents'], 7000)
    def test_tenant_identity_isolation(self):
        self.order(); self.refund(shop='other')
        self.assertEqual(self.get()['net_cents'], 10000)
    def test_pending_refund_survives_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.store.close(); self.store = Store(tmp + '/state.db')
            self.refund(); self.store.close(); self.store = Store(tmp + '/state.db')
            self.assertEqual(self.order()['net_cents'], 7000)

if __name__ == '__main__': unittest.main()
