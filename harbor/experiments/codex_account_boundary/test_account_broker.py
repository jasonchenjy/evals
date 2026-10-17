"""Boundary tests use fake credentials, no external network and no real auth file."""
import http.client
import json
import threading
import unittest
from unittest.mock import patch
from account_broker import State, handler, MAX_RESPONSE
from http.server import ThreadingHTTPServer


class Boundary(unittest.TestCase):
    def setUp(self):
        self.state = State(dict(nonce='ephemeral', access_token='FAKE_ACCOUNT_ACCESS_123456789', account_id='FAKE_ACCOUNT_ID_123456'))
        self.state.catalog_verified = True
        self.calls = []
        self.returned = (200, 'text/event-stream', b'data: safe\n\n')
        def transport(*args):
            self.calls.append(args[:3])
            return self.returned
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), handler(self.state, transport))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, path='/backend-api/codex/responses', method='POST', body=None, **headers):
        if body is None:
            body = json.dumps({'model': 'gpt-6.1-sol'}) if method == 'POST' else ''
        conn = http.client.HTTPConnection(*self.server.server_address, timeout=3)
        conn.request(method, path, body, headers={'Authorization': 'Bearer ephemeral', **headers})
        response = conn.getresponse()
        result = response.status, response.read()
        conn.close()
        return result

    def test_valid_account_transport(self):
        self.assertEqual(self.request()[0], 200)
        self.assertEqual(len(self.calls), 1)

    def test_wrong_nonce_expiry_revocation(self):
        self.assertEqual(self.request(Authorization='Bearer wrong')[0], 401)
        self.state.deadline = 0
        self.assertEqual(self.request()[0], 401)
        self.state.deadline = float('inf'); self.state.revoked = True
        self.assertEqual(self.request()[0], 401)
        self.assertFalse(self.calls)

    def test_routes(self):
        for path in ['/auth.json', '/api/codex/accounts/check', 'https://example.com/', '/backend-api/codex/responses?url=x', '/backend-api/codex/../auth.json']:
            self.assertEqual(self.request(path)[0], 404)
        self.assertFalse(self.calls)

    def test_bad_bodies(self):
        for body, expected in [('[]', 403), ('bad', 400), ('{"model":"other"}', 403), ('{"model":"gpt-6.1-sol","store":true}', 403), ('{"model":"gpt-6.1-sol","max_output_tokens":9000}', 403)]:
            self.assertEqual(self.request(body=body)[0], expected)
        for headers, expected in [({'Content-Encoding':'gzip'},400), ({'Transfer-Encoding':'chunked'},400), ({'Content-Length':'-1'},400), ({'Content-Length':'3145728'},413)]:
            self.assertEqual(self.request(**headers)[0], expected)
        self.assertFalse(self.calls)

    def test_quota_atomic_and_busy(self):
        self.state.quota = 1
        self.state.busy.acquire()
        self.assertEqual(self.request()[0], 429)
        self.state.busy.release()
        self.assertEqual(self.request()[0], 200)
        self.assertEqual(self.request()[0], 429)
        self.assertEqual(len(self.calls), 1)

    def test_catalog_once(self):
        self.returned = (200, 'application/json', b'{"models":[{"slug":"gpt-6.1-sol"}]}')
        path = '/backend-api/codex/models?client_version=0.162.1'
        self.assertEqual(self.request(path, 'GET')[0], 200)
        self.assertEqual(self.request(path, 'GET')[0], 200)
        self.assertEqual(len(self.calls), 1)

    def test_upstream_errors_redirects_secrets_size(self):
        for returned in [(302,'text/event-stream',b'redirect'), (401,'text/event-stream',b'error secret'), (200,'text/event-stream',self.state.secrets['access_token'].encode()), (200,'text/event-stream',b'x'*(MAX_RESPONSE+1)), (200,'text/html',b'html')]:
            self.returned = returned
            self.assertEqual(self.request(), (502, b''))

    def test_account_metadata_redacted_without_releasing_credentials(self):
        self.returned = (200, 'text/event-stream', ('data: '+self.state.secrets['account_id']).encode())
        self.assertEqual(self.request(), (200, b'data: synthetic-candidate'))

    def test_noncanonical_sse_content_type_requires_valid_completion(self):
        body=b'data: {"type":"response.completed","response":{"model":"gpt-6.1-sol"}}\n\n'
        for media_type in ['', 'application/octet-stream']:
            self.returned=(200,media_type,body)
            self.assertEqual(self.request(),(200,body))

    def test_duplicate_authorization(self):
        conn = http.client.HTTPConnection(*self.server.server_address)
        conn.putrequest('POST', '/backend-api/codex/responses')
        conn.putheader('Authorization','Bearer ephemeral')
        conn.putheader('Authorization','Bearer other')
        conn.putheader('Content-Length','0'); conn.endheaders()
        self.assertEqual(conn.getresponse().status, 400)
        conn.close()
        self.assertFalse(self.calls)

    def test_upstream_header_allowlist_tls_and_no_redirect(self):
        from account_broker import upstream
        with patch('account_broker.http.client.HTTPSConnection') as factory:
            conn = factory.return_value
            response = conn.getresponse.return_value
            response.status = 302; response.getheader.return_value = 'text/html'; response.read.return_value = b''
            self.assertEqual(upstream('POST','/backend-api/codex/responses',b'{}',self.state)[0],302)
            args, kwargs = factory.call_args
            self.assertEqual(args, ('chatgpt.com',443))
            self.assertTrue(kwargs['context'].check_hostname)
            self.assertEqual(conn.request.call_count,1)
            headers = conn.request.call_args.kwargs['headers']
            self.assertEqual(headers['Authorization'], 'Bearer '+self.state.secrets['access_token'])
            self.assertNotIn('ephemeral', str(headers))


if __name__ == '__main__':
    unittest.main()
