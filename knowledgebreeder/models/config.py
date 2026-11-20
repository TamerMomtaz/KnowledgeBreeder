"""The models file: one private JSON file that lists what kb may ask."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_PATH = "work/models.json"
PROTOCOLS = ("openai", "anthropic")
CLAUDE_API = "https://api.anthropic.com"
LOCAL_URL = "http://localhost:11434/v1"
# Characters of evidence one prompt may hold. A local runtime can cut a long prompt to fit its context window
# without saying so, so the default for a local model is small. Raise it in the entry when the window allows.
BUDGET = {"openai": 8_000, "anthropic": 200_000}
_SECRET_FIELDS = ("key", "api_key", "apikey", "token", "secret", "password", "authorization")
_FIELDS = {"protocol", "url", "model", "key_env", "lan", "budget", "timeout", "max_tokens", "price_in", "price_out",
           "extra", "effort", "fallbacks", "note"}


@dataclass(frozen=True)
class Model:
    name: str                       # what you call it: --model NAME, --allow NAME
    protocol: str                   # "openai" (any local runtime) or "anthropic" (the Claude API)
    url: str
    model: str                      # the model's own id at that address
    key_env: str | None = None      # the NAME of the variable that holds the key. Never the key.
    lan: bool = False               # this address is on your own network and may be used without asking
    budget: int = 8_000
    timeout: float = 600.0
    max_tokens: int = 16_000
    price_in: float | None = None   # per million tokens, if you want cost in the run log
    price_out: float | None = None
    extra: dict = field(default_factory=dict)   # openai protocol only: sent in the request as it is
    effort: str | None = None       # anthropic protocol only
    fallbacks: Any = None           # anthropic protocol only: what answers if the model declines

    @property
    def version(self) -> str:
        return self.model


@dataclass
class Book:
    models: dict[str, Model]
    default: str | None
    path: str

    def get(self, name: str | None = None) -> Model:
        name = name or self.default
        if not name:
            raise KeyError(f"{self.path} names no default model. Say which with --model NAME.")
        if name not in self.models:
            raise KeyError(f"no model called '{name}' in {self.path}. It holds: {', '.join(self.models) or 'none'}.")
        return self.models[name]

    def pick(self, names: str | None) -> list[Model]:
        """'a,b,c' -> those models, in that order, each once."""
        wanted = [n.strip() for n in (names or "").split(",") if n.strip()] or [None]
        out: list[Model] = []
        for n in wanted:
            m = self.get(n)
            if m not in out:
                out.append(m)
        return out


def _entry(name: str, raw: Any, path: str) -> Model:
    if not isinstance(raw, dict):
        raise KeyError(f"{path}: '{name}' must be an object.")
    held = [k for k in raw if k.lower() in _SECRET_FIELDS]
    if held:
        raise KeyError(f"{path}: '{name}' holds a field called '{held[0]}'. A key does not go in this file. "
                       f"Keep it in your environment and give the variable's name in \"key_env\".")
    odd = sorted(set(raw) - _FIELDS)
    if odd:
        raise KeyError(f"{path}: '{name}' has a field kb does not know: {', '.join(odd)}.")
    protocol = raw.get("protocol", "openai")
    if protocol not in PROTOCOLS:
        raise KeyError(f"{path}: '{name}' has protocol '{protocol}'. Use one of: {', '.join(PROTOCOLS)}.")
    if not raw.get("model") or not isinstance(raw["model"], str):
        raise KeyError(f"{path}: '{name}' names no model. See what your runtime offers with: kb models check")
    url = raw.get("url") or (CLAUDE_API if protocol == "anthropic" else LOCAL_URL)
    return Model(name=name, protocol=protocol, url=str(url).rstrip("/"), model=raw["model"],
                 key_env=raw.get("key_env") or None, lan=bool(raw.get("lan", False)),
                 budget=int(raw.get("budget", BUDGET[protocol])), timeout=float(raw.get("timeout", 600)),
                 max_tokens=int(raw.get("max_tokens", 16_000)), price_in=raw.get("price_in"),
                 price_out=raw.get("price_out"), extra=dict(raw.get("extra") or {}), effort=raw.get("effort"),
                 fallbacks=raw.get("fallbacks"))


def load(path: str | Path | None = None) -> Book:
    p = Path(path or os.environ.get("KB_MODELS") or DEFAULT_PATH)
    if not p.exists():
        raise KeyError(f"no models file at {p}. Make one with: kb models init")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as e:
        raise KeyError(f"{p} is not valid JSON: {e}") from None
    if not isinstance(data, dict) or not isinstance(data.get("models"), dict):
        raise KeyError(f"{p} must hold an object with a \"models\" object inside.")
    models = {name: _entry(name, raw, str(p)) for name, raw in data["models"].items()}
    default = data.get("default") or next(iter(models), None)
    if default and default not in models:
        raise KeyError(f"{p}: the default '{default}' is not one of its models.")
    return Book(models, default, str(p))


def example(local_models: list[str] | None = None, url: str = LOCAL_URL) -> dict:
    """A starting file. With the names a local runtime offers, one entry each. Without, one to fill in."""
    names = local_models or []
    models: dict[str, dict] = {}
    for i, n in enumerate(names[:6]):
        models["local" if i == 0 else f"local-{i + 1}"] = {"protocol": "openai", "url": url, "model": n}
    if not names:
        models["local"] = {"protocol": "openai", "url": url, "model": "PUT-A-NAME-FROM-kb-models-check-HERE"}
    models["key"] = {"protocol": "anthropic", "model": "claude-opus-5-5", "key_env": "ANTHROPIC_API_KEY",
                     "fallbacks": "default", "price_in": 4.0, "price_out": 20.0,
                     "note": "Used only when you add --allow key to a run. The key stays in your environment."}
    return {"default": "local", "models": models}
