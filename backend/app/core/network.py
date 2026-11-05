"""Bounded public HTTPS fetches with redirect and SSRF validation."""
import ipaddress
import socket
from urllib.parse import urlparse
import httpx
from app.core.config import settings


def reference_urls(values):
    for value in values:
        parsed=urlparse(value)
        if len(value)>2000 or parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in {None,443}:
            raise ValueError('Historical references must be public HTTPS URLs without credentials')
    return list(dict.fromkeys(values))


def validate_url(url, hosts=None):
    parsed = urlparse(url)
    host = parsed.hostname or ''
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in {None, 443}:
        raise ValueError('Only public HTTPS sources are allowed')
    if hosts and not any(host == h or host.endswith('.'+h) for h in hosts):
        raise ValueError('Source host is not permitted')
    addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
        raise ValueError('Private/local source addresses are blocked')
    return url


def public_get(url, params=None, hosts=None, max_bytes=4*1024*1024, timeout=25,user_agent=None):
    with httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False,
                      headers={'User-Agent': user_agent or settings.network_user_agent}) as client:
        for _ in range(4):
            validate_url(url, hosts)
            with client.stream('GET', url, params=params) as response:
                if response.is_redirect:
                    url = str(response.url.join(response.headers['location']))
                    params = None
                    continue
                if response.is_error:
                    # Streamed HTTP errors must retain a bounded provider body.
                    # Calling raise_for_status before reading loses robot-policy
                    # messages and their support reference identifiers.
                    error_body=bytearray()
                    for chunk in response.iter_bytes(chunk_size=1024):
                        error_body.extend(chunk[:8192-len(error_body)])
                        if len(error_body)>=8192:break
                    httpx.Response(response.status_code,headers=response.headers,
                        content=bytes(error_body),request=response.request).raise_for_status()
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > max_bytes:
                        raise ValueError('Source response exceeds size limit')
                return bytes(body), dict(response.headers)
    raise ValueError('Too many source redirects')
