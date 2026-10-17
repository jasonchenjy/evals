"""Bounded account gateway. Live upstream is fixed; secrets arrive on stdin only.

No candidate execution, file API, refresh API, redirect following or generic proxy.
Responses are buffered and scanned before release, including across chunk boundaries.
"""
import hashlib
import hmac
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import ssl
import sys
import threading
import time

MODEL = 'gpt-6.1-sol'
PREFIX = '/backend-api/codex/'
MAX_BODY = 2 * 1024 * 1024
MAX_RESPONSE = 16 * 1024 * 1024


class State:
    def __init__(self, secrets, lifetime=300, quota=12):
        self.secrets = secrets
        self.deadline = time.monotonic() + lifetime
        self.quota = quota
        self.used = 0
        self.catalog_used = False
        self.catalog_verified = False
        self.catalog_cache = None
        self.revoked = False
        self.lock = threading.Lock()
        self.busy = threading.Lock()

    def valid(self, value):
        return (not self.revoked and time.monotonic() < self.deadline and
                hmac.compare_digest(value, 'Bearer ' + self.secrets['nonce']))

    def reserve(self, catalog):
        with self.lock:
            if catalog:
                if self.catalog_used:
                    return False
                self.catalog_used = True
            else:
                if self.used >= self.quota:
                    return False
                self.used += 1  # includes failed upstream attempts; never refund/retry
            return True

    def clean(self, body):
        return all(value.encode() not in body for key, value in self.secrets.items()
                   if key != 'nonce' and isinstance(value, str) and len(value) >= 12)


def event(**fields):
    print(json.dumps(fields), flush=True)


def upstream(method, path, body, state):
    # No environment proxies, redirects, caller-controlled hosts or TLS bypass.
    connection = http.client.HTTPSConnection('chatgpt.com', 443, timeout=120,
                                            context=ssl.create_default_context())
    headers = {'Authorization': 'Bearer ' + state.secrets['access_token'],
               'ChatGPT-Account-ID': state.secrets['account_id'],
               'Content-Type': 'application/json', 'Accept': 'text/event-stream' if method == 'POST' else 'application/json',
               'User-Agent': 'codex_cli_rs/0.162.1', 'originator': 'codex_cli_rs'}
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        status = response.status
        content_type = response.getheader('Content-Type', '').split(';')[0]
        data = response.read(MAX_RESPONSE + 1)
        return status, content_type, data
    finally:
        connection.close()


def handler(state, transport=upstream):
    class Gateway(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.0'

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, *args):
            pass

        def reply(self, status, body=b'', content_type='application/json'):
            self.send_response(status)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Content-Type', content_type)
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self.handle_request(True)

        def do_POST(self):
            self.handle_request(False)

        def handle_request(self, catalog):
            try:
                self.checked_request(catalog)
            except Exception as error:
                import traceback
                event(kind='gateway_error', category='transport_or_parse', error_type=type(error).__name__, lines=[t.lineno for t in traceback.extract_tb(error.__traceback__)])
                try:
                    self.reply(502)
                except OSError:
                    pass

        def checked_request(self, catalog):
            for name in ('Authorization', 'Content-Length', 'Host', 'Content-Type'):
                if len(self.headers.get_all(name, [])) > 1:
                    self.reply(400)
                    return
            if not state.valid(self.headers.get('Authorization', '')):
                self.reply(401)
                return
            expected = PREFIX + ('models?client_version=0.162.1' if catalog else 'responses')
            if self.path != expected:
                self.reply(404)
                return
            if self.headers.get('Transfer-Encoding') or self.headers.get('Content-Encoding'):
                self.reply(400)
                return
            raw_size = self.headers.get('Content-Length', '0')
            if not raw_size.isascii() or not raw_size.isdecimal():
                self.reply(400)
                return
            size = int(raw_size)
            if (catalog and size != 0) or (not catalog and not 0 < size <= MAX_BODY):
                self.reply(413)
                return
            body = None
            if not catalog and not state.catalog_verified:
                self.reply(403)
                return
            if not catalog:
                body = self.rfile.read(size)
                if len(body) != size:
                    self.reply(400)
                    return
                try:
                    request = json.loads(body)
                except ValueError:
                    self.reply(400)
                    return
                if not isinstance(request, dict) or request.get('model') != MODEL:
                    self.reply(403)
                    return
                # Only the ordinary Responses shape; no upstream file retrieval.
                if request.get('previous_response_id') or request.get('background') or request.get('store'):
                    self.reply(403)
                    return
                if request.get('max_output_tokens', 8192) not in range(1, 8193):
                    self.reply(403)
                    return
            if catalog and state.catalog_cache is not None:
                self.reply(200, state.catalog_cache, 'application/json')
                return
            if not state.busy.acquire(blocking=False):
                self.reply(429)
                return
            try:
                if not state.reserve(catalog):
                    self.reply(429)
                    return
                event(kind='upstream_started', route='catalog' if catalog else 'responses', attempt=state.used)
                status, kind, data = transport(self.command, expected, body, state)
                event(kind='upstream', route='catalog' if catalog else 'responses', status=status,
                      attempt=state.used, response_bytes=len(data), response_sha256=hashlib.sha256(data).hexdigest())
                if not state.valid(self.headers['Authorization']):
                    self.reply(401)
                elif status != 200:  # never relay upstream errors or redirects
                    self.reply(502)
                elif len(data) > MAX_RESPONSE or not state.clean(data):
                    self.reply(502)
                elif kind != ('application/json' if catalog else 'text/event-stream'):
                    self.reply(502)
                else:
                    if catalog:
                        parsed = json.loads(data)
                        state.catalog_verified = any(m.get('slug') == MODEL for m in parsed.get('models', []))
                        event(kind='catalog_verified', selected_model_present=state.catalog_verified)
                        if not state.catalog_verified:
                            self.reply(502)
                            return
                        state.catalog_cache = data
                    self.reply(200, data, kind)
            finally:
                state.busy.release()
    return Gateway


def main():
    state = State(json.loads(sys.stdin.readline()))
    server = ThreadingHTTPServer(('0.0.0.0', 8765), handler(state))
    server.daemon_threads = True
    def expire():
        time.sleep(300)
        state.revoked = True
        server.shutdown()
    threading.Thread(target=expire, daemon=True).start()
    event(kind='ready', real_credential_in_memory_only=True, lifetime_seconds=300, response_quota=12)
    server.serve_forever()


if __name__ == '__main__':
    main()
