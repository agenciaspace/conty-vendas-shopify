import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        cls.base = 'http://127.0.0.1:' + str(port)
        cls.log = open(cls.tmp.name + '/server.log', 'w+')
        env = dict(os.environ, PORT=str(port), HOST='127.0.0.1', DATABASE_PATH=cls.tmp.name + '/state.db', API_TOKEN='http-test-token')
        env.pop('AGGREGATOR_URL', None); env.pop('AGGREGATOR_TOKEN', None)
        cls.proc = subprocess.Popen(['python3', 'app.py'], cwd=Path(__file__).resolve().parent, env=env, stdout=cls.log, stderr=cls.log)
        for _ in range(100):
            try:
                with urlopen(cls.base + '/health', timeout=.5) as response:
                    if response.status == 200: return
            except (URLError, TimeoutError): time.sleep(.05)
        cls.proc.terminate(); cls.proc.wait(timeout=5)
        cls.log.seek(0); error = cls.log.read(); cls.log.close(); cls.tmp.cleanup()
        raise AssertionError('server failed to start: ' + error)
    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate(); cls.proc.wait(timeout=5); cls.log.close(); cls.tmp.cleanup()
    def request(self, path, data=None, expected=200, auth=True, raw=None):
        headers = {'Content-Type': 'application/json'}
        if auth: headers['Authorization'] = 'Bearer http-test-token'
        payload = raw if raw is not None else (json.dumps(data).encode() if data is not None else None)
        request = Request(self.base + path, data=payload, headers=headers)
        try: response = urlopen(request, timeout=8)
        except HTTPError as exc: response = exc
        with response:
            body = json.loads(response.read())
            self.assertEqual(response.status, expected, body)
            return body
    def test_health(self): self.assertEqual(self.request('/health', auth=False), {'ok': True})
    def test_unauthenticated_request(self): self.request('/missing', expected=401, auth=False)
    def test_bad_json_and_object_contract(self):
        self.request('/missing', raw=b'{', expected=400)
        self.request('/missing', data=[], expected=400)
        self.request('/missing', raw=b'{"value": NaN}', expected=400)
    def test_missing_route(self): self.request('/missing', expected=404)
    def test_http_workflow(self):
        self.request('/creators', {'shop': 'demo', 'id': 'alice', 'coupon': 'ALICE'})
        refund = {'shop': 'demo', 'id': 'r1', 'order_id': 'o1', 'amount_cents': 3000}
        self.assertEqual(self.request('/refunds', refund)['state'], 'pending')
        order = {'shop': 'demo', 'id': 'o1', 'total_cents': 10000, 'coupon': 'ALICE', 'status': 'paid'}
        self.assertEqual(self.request('/orders', order)['attributed_cents'], 7000)
        self.request('/orders', order); self.request('/refunds', refund)
        self.assertEqual(self.request('/orders/demo/o1')['net_cents'], 7000)

if __name__ == '__main__': unittest.main()
