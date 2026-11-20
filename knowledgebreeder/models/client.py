"""Asking a model, behind the gate.

Every call goes through ask(). It first works out where the model lives, from
the address in its entry, and refuses to send when that place is not allowed
for this run. Only then does anything leave the process.
"""

from __future__ import annotations

import ipaddress
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Iterable
from urllib.parse import urlsplit

from .config import Model
from .replies import json_from

HERE, NETWORK, OUTSIDE = "this machine", "your network", "outside"
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class ModelError(Exception):
    """The model could not be asked, or gave nothing usable."""


class Refused(Exception):
    """The gate said no. Nothing was sent."""

    def __init__(self, model: Model, host: str, where: str, chars: int, sending: str):
        self.model, self.host, self.where, self.chars = model, host, where, chars
        what = f"{chars:,} characters" + (f" ({sending})" if sending else "")
        if where == NETWORK:
            place_ = f"{host}, an address on a private network that its entry does not mark as yours (\"lan\": true)"
        else:
            place_ = f"{host}, which is not this machine"
        super().__init__(f"Nothing was sent. '{model.name}' is at {place_}. This run would send {what}. "
                         f"To allow it for this run only, add: --allow {model.name}")


@dataclass
class Answer:
    text: str
    worker: str                     # the entry's name
    model: str                      # the model id the server reported, else the one asked for
    host: str
    where: str
    ms: float = 0.0
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost: float | None = None
    chars_sent: int = 0
    warnings: list[str] = field(default_factory=list)


def place(url: str) -> tuple[str, str]:
    """(host, where) for an address. Only a loopback name or address counts as this machine. A name that is
    not 'localhost' counts as outside, because kb cannot know where a name leads without asking the network."""
    u = urlsplit(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ModelError(f"'{url}' is not an http or https address.")
    host = u.hostname.lower().rstrip(".")
    if host == "localhost" or host.endswith(".localhost"):
        return host, HERE
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return host, OUTSIDE
    if ip.is_loopback:
        return host, HERE
    if ip.is_unspecified or ip.is_multicast or ip.is_reserved:
        return host, OUTSIDE
    if ip.is_private or ip.is_link_local:
        return host, NETWORK
    return host, OUTSIDE


def allowed(m: Model, allow: Iterable[str] = ()) -> bool:
    _host, where = place(m.url)
    return where == HERE or (where == NETWORK and m.lan) or m.name in set(allow)


def gate(m: Model, allow: Iterable[str] = (), chars: int = 0, sending: str = "") -> tuple[str, str]:
    """(host, where) when this run may send to the model. Raises Refused when it may not. Every send passes here."""
    host, where = place(m.url)
    if not allowed(m, allow):
        raise Refused(m, host, where, chars, sending)
    return host, where


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A local server must not be able to pass your data on to another address."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _opener(where: str) -> urllib.request.OpenerDirector:
    handlers: list[Any] = [_NoRedirect()]
    if where != OUTSIDE:
        handlers.append(urllib.request.ProxyHandler({}))    # a proxy from the environment would carry it outside
    return urllib.request.build_opener(*handlers)


def _key(m: Model) -> str | None:
    if not m.key_env:
        return None
    value = os.environ.get(m.key_env)
    if not value:
        raise ModelError(f"'{m.name}' reads its key from the variable {m.key_env}, which is not set here.")
    return value


def _http(m: Model, where: str, path: str, body: dict | None) -> dict:
    headers = {"Accept": "application/json"}
    key = _key(m)
    if key:
        headers["Authorization"] = "Bearer " + key
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(m.url + path, data=data, headers=headers, method="POST" if data else "GET")
    host = place(m.url)[0]
    try:
        with _opener(where).open(req, timeout=m.timeout) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        if 300 <= e.code < 400:
            raise ModelError(f"'{m.name}' at {host} tried to send the request on to another address "
                             f"({e.headers.get('Location', 'not given')}). kb did not follow it.") from None
        detail = e.read(600).decode("utf-8", "replace").strip()
        raise ModelError(f"'{m.name}' at {host} answered {e.code}: {detail[:300] or e.reason}") from None
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        reason = getattr(e, "reason", e)
        raise ModelError(f"could not reach '{m.name}' at {host}: {reason}. Is the runtime running?") from None
    try:
        out = json.loads(raw.decode("utf-8"))
    except ValueError:
        raise ModelError(f"'{m.name}' at {host} did not answer in JSON.") from None
    if not isinstance(out, dict):
        raise ModelError(f"'{m.name}' at {host} answered in a shape kb does not know.")
    return out


def offered(m: Model, allow: Iterable[str] = ()) -> list[str]:
    """The model names a runtime says it has. Asks the address, so it goes through the gate as well."""
    host, where = gate(m, allow, 0, "a question about which models it has, nothing of yours")
    if m.protocol == "anthropic":
        client = _claude(m, where)
        try:
            return [x.id for x in client.models.list()]
        except Exception as e:                              # the SDK's own errors, told plainly
            raise ModelError(f"could not list models at {host}: {type(e).__name__}") from None
    data = _http(m, where, "/models", None).get("data") or []
    return [x["id"] for x in data if isinstance(x, dict) and x.get("id")]


def _openai(m: Model, where: str, system: str, user: str) -> tuple[str, str, int | None, int | None, list[str]]:
    body = {"model": m.model, "stream": False,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}], **m.extra}
    out = _http(m, where, "/chat/completions", body)
    try:
        choice = out["choices"][0]
        text = choice["message"].get("content") or ""
    except (KeyError, IndexError, TypeError, AttributeError):
        raise ModelError(f"'{m.name}' answered in a shape kb does not know.") from None
    warnings = []
    if choice.get("finish_reason") == "length":
        warnings.append("the answer was cut off at the model's length limit")
    usage = out.get("usage") or {}
    return text, out.get("model") or m.model, usage.get("prompt_tokens"), usage.get("completion_tokens"), warnings


def _claude(m: Model, where: str):
    try:
        import anthropic
    except ImportError:
        raise ModelError("the key path needs the Anthropic SDK. Install it with: "
                         "pip install \"knowledgebreeder[key]\"") from None
    kw: dict[str, Any] = {"base_url": m.url, "timeout": m.timeout}
    key = _key(m)
    if key:
        kw["api_key"] = key                                 # without key_env the SDK finds your own sign-in
    if where != OUTSIDE:
        kw["http_client"] = anthropic.DefaultHttpxClient(trust_env=False, follow_redirects=False)
    try:
        return anthropic.Anthropic(**kw)
    except anthropic.AnthropicError as e:
        raise ModelError(f"'{m.name}' has no key to use: {e}") from None


def _anthropic(m: Model, where: str, system: str, user: str) -> tuple[str, str, int | None, int | None, list[str]]:
    client = _claude(m, where)
    import anthropic
    req: dict[str, Any] = {"model": m.model, "max_tokens": m.max_tokens, "system": system,
                           "messages": [{"role": "user", "content": user}]}
    if m.effort:
        req["output_config"] = {"effort": m.effort}
    host = place(m.url)[0]
    try:
        if m.fallbacks:
            r = client.beta.messages.create(betas=[FALLBACK_BETA], fallbacks=m.fallbacks, **req)
        else:
            r = client.messages.create(**req)
    except anthropic.BadRequestError as e:
        raise ModelError(f"'{m.name}' did not accept the request: {e.message}") from None
    except anthropic.AuthenticationError:
        raise ModelError(f"'{m.name}' did not accept the key" + (f" in {m.key_env}." if m.key_env else ".")) from None
    except anthropic.PermissionDeniedError:
        raise ModelError(f"the key for '{m.name}' is not allowed to use {m.model}.") from None
    except anthropic.NotFoundError:
        raise ModelError(f"'{m.name}': there is no model called {m.model} at {host}.") from None
    except anthropic.RateLimitError:
        raise ModelError(f"'{m.name}' is over its rate limit. Try again in a minute.") from None
    except anthropic.APIStatusError as e:
        raise ModelError(f"'{m.name}' at {host} answered {e.status_code}: {e.message}") from None
    except anthropic.APIConnectionError:
        raise ModelError(f"could not reach '{m.name}' at {host}.") from None
    warnings = []
    if r.stop_reason == "refusal":
        raise ModelError(f"'{m.name}' declined to answer this.")
    if r.stop_reason == "max_tokens":
        warnings.append("the answer was cut off at max_tokens")
    if r.model and r.model != m.model:
        warnings.append(f"answered by {r.model}, not {m.model}")
    text = "".join(b.text for b in r.content if b.type == "text")
    return text, r.model or m.model, r.usage.input_tokens, r.usage.output_tokens, warnings


def ask(m: Model, system: str, user: str, *, allow: Iterable[str] = (), sending: str = "") -> Answer:
    """One question, one answer. ``sending`` says in plain words what the prompt holds, for the refusal."""
    chars = len(system) + len(user)
    host, where = gate(m, allow, chars, sending)
    t0 = time.perf_counter()
    call = _anthropic if m.protocol == "anthropic" else _openai
    text, model, tin, tout, warnings = call(m, where, system, user)
    ms = round((time.perf_counter() - t0) * 1000, 1)
    if not text.strip():
        raise ModelError(f"'{m.name}' returned no text.")
    if tin and chars / tin > 10:
        warnings.append(f"the runtime counted {tin:,} tokens for a prompt of {chars:,} characters. "
                        f"It may have cut the prompt to fit its context window.")
    cost = None
    if m.price_in is not None and m.price_out is not None and tin is not None and tout is not None:
        cost = round((tin * m.price_in + tout * m.price_out) / 1_000_000, 6)
    return Answer(text=text, worker=m.name, model=model, host=host, where=where, ms=ms, tokens_in=tin,
                  tokens_out=tout, cost=cost, chars_sent=chars, warnings=warnings)


def ask_json(m: Model, system: str, user: str, *, allow: Iterable[str] = (), sending: str = "") -> tuple[Any, Answer]:
    """ask(), then read the answer as JSON. One more try when the first answer cannot be read."""
    a = ask(m, system, user, allow=allow, sending=sending)
    try:
        return json_from(a.text), a
    except ValueError:
        pass
    b = ask(m, system, user + "\n\nYour last reply could not be read as JSON. Reply with the JSON object only, "
                              "with no words before or after it.", allow=allow, sending=sending)
    b.ms = round(a.ms + b.ms, 1)
    b.tokens_in = None if a.tokens_in is None or b.tokens_in is None else a.tokens_in + b.tokens_in
    b.tokens_out = None if a.tokens_out is None or b.tokens_out is None else a.tokens_out + b.tokens_out
    b.cost = None if a.cost is None or b.cost is None else round(a.cost + b.cost, 6)
    b.warnings = a.warnings + b.warnings + ["the first answer was not JSON, so kb asked once more"]
    try:
        return json_from(b.text), b
    except ValueError:
        raise ModelError(f"'{m.name}' did not answer in JSON, twice. Its last words began: "
                         f"{b.text.strip()[:160]!r}") from None
