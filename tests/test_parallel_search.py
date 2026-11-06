"""Synthetic MCP responses; live runtime evidence is collected separately."""
import importlib.util
import io
import json
import threading
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def module(monkeypatch):
    for key in ('PARALLEL_API_KEY', 'ARIS_SEARCH_DISABLED', 'ARIS_SEARCH_OFFLINE'):
        monkeypatch.delenv(key, raising=False)
    spec = importlib.util.spec_from_file_location('parallel_search', ROOT / 'tools/parallel_search.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Response(io.BytesIO):
    def __init__(self, body, content_type='application/json'):
        super().__init__(body)
        self.headers = {'Content-Type': content_type}


@pytest.mark.parametrize("separator", ["\r\n", "\r", "\n"])
def test_sse_crlf_unicode_notifications_and_chunks(module, separator):
    # Unicode line/paragraph separators and NEL are JSON characters, not SSE lines.
    body = ': ping\r\nevent: message\r\ndata: {"jsonrpc":"2.0","method":"notice"}\r\n\r\n'
    body += 'data: ' + json.dumps({'id': 7, 'result': {'text': 'α\u2028β\u2029γ\u0085'}}, ensure_ascii=False) + '\r\n\r\n'

    class Chunked(Response):
        def read1(self, size):
            return self.read(1)  # Splits CRLF and multibyte UTF-8 characters.

    response = Chunked(body.replace("\r\n", separator).encode(), 'text/event-stream; charset=utf-8')
    assert module._decode_response(response, 7)['text'] == 'α\u2028β\u2029γ\u0085'


@pytest.mark.parametrize('body,match', [
    ({'id': 1, 'error': {'code': -32602, 'message': 'secret'}}, 'code -32602'),
    ({'id': 2, 'result': {}}, 'response ID'),
    ({'id': 1, 'result': []}, 'Invalid MCP result'),
])
def test_protocol_errors(module, body, match):
    with pytest.raises(RuntimeError, match=match):
        module._decode_response(Response(json.dumps(body).encode()), 1)


def test_truncated_sse(module):
    with pytest.raises(RuntimeError, match='stream ended'):
        module._decode_response(Response(b'data: {}\n', 'text/event-stream'), 1)


@pytest.mark.parametrize('kwargs', [{'offline': True}, {'disabled': True}])
def test_flags_block_before_client(module, monkeypatch, kwargs):
    monkeypatch.setattr(module, '_Client', lambda: pytest.fail('network client created'))
    with pytest.raises(RuntimeError, match='disabled/offline'):
        module.search('query', **kwargs)


@pytest.mark.parametrize('name', ['ARIS_SEARCH_OFFLINE', 'ARIS_SEARCH_DISABLED'])
def test_environment_blocks_before_client(module, monkeypatch, name):
    monkeypatch.setenv(name, 'TRUE')
    monkeypatch.setattr(module, '_Client', lambda: pytest.fail('network client created'))
    with pytest.raises(RuntimeError, match='disabled/offline'):
        module.search('query')


@pytest.mark.parametrize('query,limit,chars', [(' ', 5, 10), ('q', 0, 10), ('q', 101, 10), ('q', 1, 0), ('q', 1, 100001)])
def test_invalid_arguments_no_network(module, monkeypatch, query, limit, chars):
    monkeypatch.setattr(module, '_Client', lambda: pytest.fail('network client created'))
    with pytest.raises(ValueError):
        module.search(query, limit, chars)


@pytest.mark.parametrize('key', ['', '  ', 'bad\nkey', 'bad\x7fkey'])
def test_explicit_invalid_key_never_anonymous(module, monkeypatch, key):
    monkeypatch.setenv('PARALLEL_API_KEY', key)
    with pytest.raises(ValueError, match='PARALLEL_API_KEY'):
        module._Client()


def test_auth_http_failure_not_retried(module, monkeypatch, capsys):
    monkeypatch.setenv('PARALLEL_API_KEY', 'explicit-key')
    requests = []

    class Opener:
        def open(self, req, **kwargs):
            requests.append(req)
            raise urllib.error.HTTPError(req.full_url, 401, 'unauthorized', {}, None)

    monkeypatch.setattr(module.urllib.request, 'build_opener', lambda *a: Opener())
    assert module.main(['search', 'query']) == 1
    assert len(requests) == 1
    assert requests[0].get_header('Authorization') == 'Bearer explicit-key'
    assert 'explicit-key' not in capsys.readouterr().err


@pytest.mark.parametrize('text_only', [False, True])
def test_search_lifecycle_limits_and_json(module, monkeypatch, capsys, text_only):
    calls = []
    payload = {'results': [{'url': 'https://example.org', 'title': 'Example',
                           'excerpts': ['abc', 'defg', 'ignored']}] * 3, 'warnings': [{'message': 'warning'}]}

    class Client:
        headers = {}
        def request(self, method, params=None, **kwargs):
            calls.append((method, params, kwargs))
            if method == 'initialize': return {'protocolVersion': module.PROTOCOL}
            if method == 'tools/list': return {'tools': [{'name': 'web_search'}]}
            if method == 'tools/call':
                if text_only: return {'content': [{'type': 'text', 'text': json.dumps(payload)}]}
                return {'structuredContent': payload}
        def close(self): calls.append(('close', None, {}))

    monkeypatch.setattr(module, '_Client', Client)
    assert module.main(['search', 'test search query', '--max', '2', '--max-chars', '5']) == 0
    output = json.loads(capsys.readouterr().out)
    assert output['returned'] == 2
    assert output['data'][0]['excerpts'] == ['abc', 'de']
    assert output['warnings'] == payload['warnings']
    assert [c[0] for c in calls] == ['initialize', 'notifications/initialized', 'tools/list', 'tools/call', 'close']
    assert calls[1][2] == {'notification': True}
    assert calls[3][1] == {'name': 'web_search', 'arguments': {'objective': 'test search query', 'search_queries': ['test search query']}}


@pytest.mark.parametrize('tool_result', [{'isError': True}, {'structuredContent': {'wrong': []}},
                                       {'structuredContent': {'results': [{'url': None}]}}])
def test_tool_failures_cleanup(module, monkeypatch, tool_result):
    closed = []
    class Client:
        headers = {}
        def request(self, method, *args, **kwargs):
            if method == 'initialize': return {'protocolVersion': module.PROTOCOL}
            if method == 'tools/list': return {'tools': [{'name': 'web_search'}]}
            return tool_result
        def close(self): closed.append(True)
    monkeypatch.setattr(module, '_Client', Client)
    with pytest.raises(RuntimeError): module.search('query')
    assert closed == [True]


def test_parser_rejects_exa_commands_and_flags(module):
    for argv in [['find-similar', 'https://example.org'], ['search', 'query', '--category', 'news']]:
        with pytest.raises(SystemExit): module._build_parser().parse_args(argv)


def test_real_http_headers_and_redirect_rejection(module, monkeypatch):
    # Local HTTP server with synthetic responses exercises final urllib headers.
    observed = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            observed.append((self.command, dict(self.headers), body))
            if self.path == '/redirect':
                self.send_response(307); self.send_header('Location', '/other'); self.end_headers(); return
            method = body['method']
            if method == 'initialize': result = {'protocolVersion': module.PROTOCOL}
            elif method == 'tools/list': result = {'tools': [{'name': 'web_search'}]}
            else: result = {'structuredContent': {'results': []}}
            data = json.dumps({'id': body.get('id'), 'result': result}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Mcp-Session-Id', 'synthetic-session')
            self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
        def do_DELETE(self):
            observed.append((self.command, dict(self.headers), None))
            self.send_response(204); self.end_headers()
    server = HTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    monkeypatch.setenv('no_proxy', '127.0.0.1')
    endpoint = f'http://127.0.0.1:{server.server_port}'
    try:
        monkeypatch.setattr(module, 'ENDPOINT', endpoint + '/mcp')
        monkeypatch.setenv('PARALLEL_API_KEY', 'synthetic-key')
        assert module.search('test search query')['returned'] == 0
        assert [r[0] for r in observed] == ['POST'] * 4 + ['DELETE']
        assert all(r[1]['User-Agent'] == module.USER_AGENT for r in observed)
        assert all(r[1]['Authorization'] == 'Bearer synthetic-key' for r in observed)
        assert all(r[1].get('Mcp-Session-Id') == 'synthetic-session' for r in observed[1:])
        monkeypatch.setattr(module, 'ENDPOINT', endpoint + '/redirect')
        with pytest.raises(RuntimeError, match='HTTP 307'): module.search('query')
        assert len(observed) == 6  # No redirected request, credential leak or retry.
    finally:
        server.shutdown(); server.server_close(); thread.join()


@pytest.mark.parametrize('status', [403, 429, 500])
def test_http_errors_do_not_switch_or_retry(module, monkeypatch, status):
    calls = []
    class Opener:
        def open(self, req, **kwargs):
            calls.append(req)
            raise urllib.error.HTTPError(req.full_url, status, 'synthetic failure', {}, None)
    monkeypatch.setattr(module.urllib.request, 'build_opener', lambda *a: Opener())
    with pytest.raises(RuntimeError, match=f'HTTP {status}'):
        module.search('query')
    assert len(calls) == 1
    assert calls[0].get_header('Authorization') is None


def test_discovery_pagination_and_missing_tool(module, monkeypatch):
    pages = []
    closed = []
    class Client:
        headers = {}
        def request(self, method, params=None, **kwargs):
            if method == 'initialize': return {'protocolVersion': module.PROTOCOL}
            if method == 'tools/list':
                pages.append(params)
                return {'tools': [], 'nextCursor': 'repeated'}
        def close(self): closed.append(True)
    monkeypatch.setattr(module, '_Client', Client)
    with pytest.raises(RuntimeError, match='does not expose web_search'):
        module.search('query')
    assert pages == [{}, {'cursor': 'repeated'}]
    assert closed == [True]


def test_cleanup_http_warning_retained(module, monkeypatch, capsys):
    client = module._Client()
    client.headers['Mcp-Session-Id'] = 'synthetic'
    class Opener:
        def open(self, req, **kwargs):
            assert req.method == 'DELETE'
            assert req.get_header('User-agent') == module.USER_AGENT
            raise urllib.error.HTTPError(req.full_url, 500, 'synthetic', {}, None)
    client.opener = Opener()
    client.close()
    assert 'cleanup HTTP 500' in capsys.readouterr().err
