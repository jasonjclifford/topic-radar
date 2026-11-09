import threading
import time
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import pytest_asyncio

from topic_radar.context import RunContext
from topic_radar.settings import Settings
from topic_radar.watch import Watch

SITES = Path(__file__).parent / "sites"
NOW = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
_TYPES = {".xml": "application/xml", ".atom": "application/atom+xml", ".rss": "application/rss+xml",
          ".html": "text/html; charset=utf-8", ".txt": "text/plain"}


@dataclass
class Site:
    base: str
    requests: list = field(default_factory=list)  # (method, path) in arrival order

    def url(self, path: str) -> str:
        return self.base + path


class _Handler(BaseHTTPRequestHandler):
    """Serves tests/sites/ (with {BASE} replaced by the server's address), plus:

    /status/<code>                 that status
    /slow                          answers after 1 second
    /redirect?to=<url>&code=<n>    a redirect (302 by default)
    /head-fails?to=<url>           HEAD gets 405; GET redirects to <url>
    /bytes/<n>?type=<mime>&length=0|1&declare=<m>   n bytes of body; length=0 sends no Content-Length;
                                   declare=m states Content-Length m whatever n is
    """

    def log_message(self, *args):
        pass

    def do_GET(self):
        self._serve(True)

    def do_HEAD(self):
        self._serve(False)

    def _send(self, code, ctype="text/plain", body=b"", headers=None, send_body=True):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if send_body:
            self.wfile.write(body)

    def _serve(self, send_body):
        site = self.server.site
        parsed = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        path = parsed.path
        site.requests.append((self.command, self.path))
        try:
            if path.startswith("/status/"):
                self._send(int(path.rsplit("/", 1)[1]), body=b"nope", send_body=send_body)
            elif path == "/slow":
                time.sleep(1.0)
                self._send(200, body=b"late", send_body=send_body)
            elif path == "/redirect":
                self._send(int(q.get("code", 302)), headers={"Location": q["to"]}, send_body=send_body)
            elif path == "/head-fails":
                if self.command == "HEAD":
                    self._send(405, send_body=False)
                else:
                    self._send(301, headers={"Location": q["to"]})
            elif path.startswith("/bytes/"):
                n = int(path.rsplit("/", 1)[1])
                self.send_response(200)
                self.send_header("Content-Type", q.get("type", "text/plain"))
                if q.get("length", "1") == "1":
                    self.send_header("Content-Length", q.get("declare", str(n)))
                self.end_headers()
                if send_body:
                    left = n
                    while left:
                        chunk = min(left, 65536)
                        self.wfile.write(b"a" * chunk)
                        left -= chunk
            else:
                file = (SITES / path.lstrip("/")).resolve()
                if SITES.resolve() not in file.parents or not file.is_file():
                    self._send(404, body=b"missing", send_body=send_body)
                else:
                    body = file.read_text(encoding="utf-8").replace("{BASE}", site.base).encode()
                    self._send(200, _TYPES.get(file.suffix, "text/plain"), body, send_body=send_body)
        except OSError:
            pass  # the client hung up, which is what a refusal looks like from here


@pytest.fixture
def site():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.daemon_threads = True
    s = Site(base=f"http://127.0.0.1:{server.server_address[1]}")
    server.site = s
    threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True).start()
    yield s
    server.shutdown()
    server.server_close()


@pytest_asyncio.fixture
async def make_ctx(tmp_path):
    clients = []

    def build(seeds=(), allow_loopback=True, lookback=timedelta(days=7), **settings):
        client = httpx.AsyncClient()
        clients.append(client)
        values = dict(request_delay_seconds=0, timeout_seconds=2)
        values.update(settings)
        return RunContext(
            settings=replace(Settings(), **values),
            watch=Watch(name="Test", slug="test", interests="anything", seeds=list(seeds),
                        first_run_lookback=lookback),
            folder=tmp_path, clock=lambda: NOW, http=client, model=None,
            run_folder=tmp_path / "run", allow_loopback=allow_loopback,
        )

    yield build
    for c in clients:
        await c.aclose()
