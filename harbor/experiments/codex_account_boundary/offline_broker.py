"""OFFLINE ONLY: fixed local upstream; never accepts real credentials or URLs.

Tests native ChatGPT-mode transport without giving the candidate the synthetic
upstream credential. This is a feasibility fixture, not a live auth service.
"""
import hashlib
import hmac
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time

STATE = json.loads(Path('/tmp/probe-state.json').read_text())
assert STATE['upstream_secret'].startswith('SYNTHETIC-ACCOUNT-')
EXPIRES = time.monotonic() + 300
AUDIT = []
LOCK = threading.Lock()
REQUESTS = []
NATIVE_COMMANDS = json.loads(Path('/tmp/commands.json').read_text())


def record(**item):
    with LOCK:
        AUDIT.append(item)
        Path('/tmp/audit.json').write_text(json.dumps(AUDIT, indent=2))


class Quiet(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reject(self, code):
        self.send_response(code)
        self.send_header('Content-Length', '0')
        self.end_headers()


class Upstream(Quiet):
    def do_POST(self):
        # The synthetic account credential exists in this trusted container only.
        assert self.headers.get('Authorization') == 'Bearer ' + STATE['upstream_secret']
        assert self.headers.get('ChatGPT-Account-ID') == 'synthetic-upstream-account'
        data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        assert data['model'] == 'gpt-6.1-sol'
        REQUESTS.append(data)
        index = len(REQUESTS) - 1
        outputs = {item['call_id']: item['output'] for request in REQUESTS
                   for item in request.get('input', [])
                   if item.get('type') in ('custom_tool_call_output', 'function_call_output')}
        Path('/tmp/tool-outputs.json').write_text(json.dumps(outputs, indent=2))
        record(upstream_request=index, account_header_valid=True,
               candidate_nonce_not_forwarded=self.headers.get('Authorization') != 'Bearer ' + STATE['nonce'])
        if index < len(NATIVE_COMMANDS):
            item = dict(id='ctc_' + str(index), type='custom_tool_call', status='completed',
                        call_id='call_' + str(index), name='exec', input=NATIVE_COMMANDS[index])
        else:
            item = dict(id='msg_done', type='message', role='assistant', status='completed',
                        content=[dict(type='output_text', text='Offline isolation fixture complete.', annotations=[])])
        rid = 'response_' + str(index)
        events = [dict(type='response.created', response=dict(id=rid, object='response', model='gpt-6.1-sol', status='in_progress', output=[])),
                  dict(type='response.output_item.done', output_index=0, item=item),
                  dict(type='response.completed', response=dict(id=rid, object='response', model='gpt-6.1-sol', status='completed', output=[item], usage=dict(input_tokens=0, output_tokens=0, total_tokens=0)))]
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Connection', 'close')
        self.end_headers()
        for seq, event in enumerate(events):
            event['sequence_number'] = seq
            self.wfile.write(('event: ' + event['type'] + '\ndata: ' + json.dumps(event) + '\n\n').encode())
            self.wfile.flush()


class Broker(Quiet):
    def do_GET(self):
        # No credential retrieval, refresh, arbitrary URL or filesystem API.
        record(rejected_method='GET', path=self.path)
        self.reject(404)

    def do_POST(self):
        if time.monotonic() >= EXPIRES or Path('/tmp/revoked').exists():
            self.reject(401)
            return
        if not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + STATE['nonce']):
            self.reject(401)
            return
        if self.path != '/backend-api/codex/responses':
            record(rejected_method='POST', path=self.path)
            self.reject(404)
            return
        if self.headers.get('Transfer-Encoding') or self.headers.get('Content-Encoding'):
            self.reject(400)
            return
        size = int(self.headers.get('Content-Length', '0'))
        if not 0 < size <= 2 * 1024 * 1024:
            self.reject(413)
            return
        body = self.rfile.read(size)
        try:
            request = json.loads(body)
        except ValueError:
            self.reject(400)
            return
        if request.get('model') != 'gpt-6.1-sol' or len(REQUESTS) > len(NATIVE_COMMANDS):
            self.reject(403)
            return
        record(candidate_request=len(REQUESTS), route=self.path,
               native_chatgpt_transport=True, body_sha256=hashlib.sha256(body).hexdigest())
        # Fixed local upstream and explicit header replacement. No user-provided
        # destinations, forwarded credentials, redirects, or account endpoints.
        conn = http.client.HTTPConnection('127.0.0.1', 8766, timeout=60)
        try:
            conn.request('POST', '/backend-api/codex/responses', body=body, headers={
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + STATE['upstream_secret'],
                'ChatGPT-Account-ID': 'synthetic-upstream-account'})
            response = conn.getresponse()
            self.send_response(response.status)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Connection', 'close')
            self.end_headers()
            while True:
                data = response.read(4096)
                if not data:
                    break
                self.wfile.write(data)
                self.wfile.flush()
        finally:
            conn.close()


if __name__ == '__main__':
    upstream = ThreadingHTTPServer(('127.0.0.1', 8766), Upstream)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    ThreadingHTTPServer(('0.0.0.0', 8765), Broker).serve_forever()
