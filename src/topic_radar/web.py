import asyncio
import ipaddress
import socket
import time
import weakref
from dataclasses import dataclass
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

import httpx

MAX_BYTES = 5 * 1024 * 1024
MAX_HOPS = 5
_TRACKING = {"fbclid", "gclid", "mc_cid", "mc_eid"}
_XML_TYPES = {"text/xml", "application/xml", "application/rss+xml", "application/atom+xml",
              "application/rdf+xml", "application/xhtml+xml"}
_OK_TYPES = _XML_TYPES | {"text/html", "text/plain"}


class FetchError(Exception):
    """A fetch that did not give a page. `reason` is a plain sentence for the notes."""

    def __init__(self, reason: str, refused: bool = False):
        super().__init__(reason)
        self.reason = reason
        self.refused = refused  # True when the guard refused it, False when the fetch just failed


@dataclass
class Fetched:
    url: str  # the address after redirects
    status: int
    content_type: str  # the media type alone, lowercase
    body: bytes
    charset: str = "utf-8"

    @property
    def text(self) -> str:
        try:
            return self.body.decode(self.charset, errors="replace")
        except LookupError:  # a header charset Python has no codec for: utf8mb4, none, binary, ...
            return self.body.decode("utf-8", errors="replace")


def _is_tracking(key: str) -> bool:
    key = unquote(key).lower()
    return key.startswith("utm_") or key in _TRACKING


def normalize_address(url: str) -> str:
    parts = urlsplit(url.strip())
    pairs = [p for p in parts.query.split("&") if p and not _is_tracking(p.split("=", 1)[0])]
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "&".join(pairs), parts.fragment))


def _ok_type(media: str) -> bool:
    return media in _OK_TYPES or media.endswith("+xml")


def _refuse(reason: str) -> FetchError:
    return FetchError(f"refused: {reason}", refused=True)


async def _check_host(ctx, url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise _refuse(f"only http and https addresses are fetched (this one is {parts.scheme or 'not an address'}:)")
    host = parts.hostname
    if not host:
        raise _refuse("the address has no host")
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, parts.port or 443, type=socket.SOCK_STREAM)
    except OSError:
        raise FetchError(f"the name {host} could not be found") from None
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if ip.version == 6 and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        if ip.is_loopback and ctx.allow_loopback:
            continue
        if not ip.is_global:
            raise _refuse(f"{host} is a private or local network address")


_last_request: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


async def _pace(ctx, host: str) -> None:
    last = _last_request.setdefault(ctx.http, {})
    wait = last.get(host, 0) + ctx.settings.request_delay_seconds - time.monotonic()
    if wait > 0:
        last[host] = time.monotonic() + wait  # claim the slot before sleeping
        await asyncio.sleep(wait)
    else:
        last[host] = time.monotonic()


def is_parseable_address(url: str) -> bool:
    """True when the address splits into parts, including a port that is a number from 0 to 65535."""
    try:
        urlsplit(url).port
    except ValueError:
        return False
    return True


async def fetch(ctx, url: str, *, method: str = "GET") -> Fetched:
    """Fetch one address under the guard, following redirects by hand. Raises FetchError."""
    try:
        return await _fetch(ctx, url, method)
    except (ValueError, httpx.InvalidURL):  # a bad port or bracket in the address, or in a redirect's Location
        raise FetchError("the address is not a valid web address") from None


async def _fetch(ctx, url: str, method: str) -> Fetched:
    timeout = ctx.settings.timeout_seconds
    for _ in range(MAX_HOPS + 1):
        await _check_host(ctx, url)
        await _pace(ctx, urlsplit(url).netloc)
        try:
            async with ctx.http.stream(method, url, follow_redirects=False, timeout=timeout) as resp:
                if resp.status_code in (301, 302, 303, 307, 308) and "location" in resp.headers:
                    url = urljoin(url, resp.headers["location"])
                    continue
                if resp.status_code != 200:
                    raise FetchError(f"the server answered {resp.status_code}")
                media = resp.headers.get("content-type", "text/plain").split(";")[0].strip().lower()
                if not _ok_type(media):
                    raise _refuse(f"the content type {media} is not a page or feed")
                declared = resp.headers.get("content-length", "")
                if declared.isdigit() and int(declared) > MAX_BYTES:
                    raise _refuse("the page is larger than 5 MB")
                body = bytearray()
                if method != "HEAD":
                    async for chunk in resp.aiter_bytes():
                        body += chunk
                        if len(body) > MAX_BYTES:
                            raise _refuse("the page is larger than 5 MB")
                return Fetched(url, resp.status_code, media, bytes(body), resp.charset_encoding or "utf-8")
        except httpx.TimeoutException:
            raise FetchError(f"no answer within {timeout:g} seconds") from None
        except httpx.HTTPError:
            raise FetchError("the connection failed") from None
    raise _refuse("too many redirects")
