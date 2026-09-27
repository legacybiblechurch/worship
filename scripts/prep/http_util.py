"""
Tiny HTTP helper.

Uses `requests` if available, else stdlib urllib, else shells out to `curl`.
The curl fallback exists because this repo's dev Mac ships an ancient LibreSSL that
Cloudflare-fronted APIs (Groq) reject from urllib. GitHub Actions has none of that
problem; there `requests` (or urllib) is used.
"""

from __future__ import annotations

import json
import subprocess
import urllib.request

try:  # noqa: SIM105
    import requests  # type: ignore
except Exception:  # pragma: no cover
    requests = None


class HTTPError(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:500]}")
        self.status = status
        self.body = body


def _via_requests(method, url, headers, data, timeout):
    r = requests.request(method, url, headers=headers, data=data, timeout=timeout)
    if r.status_code >= 400:
        raise HTTPError(r.status_code, r.text)
    return r.json()


def _via_urllib(method, url, headers, data, timeout):
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:  # type: ignore[attr-defined]
        raise HTTPError(e.code, e.read().decode("utf-8", "replace"))


def _via_curl(method, url, headers, data, timeout):
    cmd = ["curl", "-sS", "-X", method, "--max-time", str(timeout),
           "-w", "\n%{http_code}", url]
    for k, v in headers.items():
        cmd += ["-H", f"{k}: {v}"]
    if data is not None:
        cmd += ["--data-binary", data if isinstance(data, str) else data.decode()]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 15).stdout
    body, _, status = out.rpartition("\n")
    code = int(status.strip() or 0)
    if code >= 400 or code == 0:
        raise HTTPError(code, body)
    return json.loads(body)


def request_json(method: str, url: str, *, headers: dict | None = None,
                 json_body: dict | None = None, timeout: int = 120) -> dict:
    headers = dict(headers or {})
    data = None
    if json_body is not None:
        data = json.dumps(json_body).encode()
        headers.setdefault("content-type", "application/json")

    if requests is not None:
        try:
            return _via_requests(method, url, headers, data, timeout)
        except HTTPError:
            raise
        except Exception:
            pass
    try:
        return _via_urllib(method, url, headers, data, timeout)
    except HTTPError:
        raise
    except Exception:
        return _via_curl(method, url, headers, data, timeout)


def get_json(url: str, **kw) -> dict:
    return request_json("GET", url, **kw)


def post_json(url: str, **kw) -> dict:
    return request_json("POST", url, **kw)
