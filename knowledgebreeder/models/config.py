"""The models file: one private JSON file that lists what kb may ask."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_PATH = "work/models.json"
CAP = 1.0                           # dollars a day the page may spend on paid models, until you say another
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
    cap: float = CAP                # "daily_cap" in the file: what the page may spend a day, in dollars

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
    return Book(models, default, str(p), _cap(data.get("daily_cap", CAP), str(p)))


def _cap(raw: Any, path: str) -> float:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not 0 <= raw <= 1000:
        raise KeyError(f"{path}: \"daily_cap\" must be a number of dollars from 0 to 1000.")
    return float(raw)


def set_cap(path: str | Path, dollars: float) -> float:
    """Write what the page may spend a day on paid models into the models file, keeping everything else."""
    p = Path(path)
    if not p.exists():
        raise KeyError(f"no models file at {p}. Make one with: kb models init")
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise KeyError(f"{p} must hold an object with a \"models\" object inside.")
    data["daily_cap"] = _cap(round(float(dollars), 2), str(p))
    tmp = p.with_name(p.name + ".part")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, p)
    return data["daily_cap"]


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


# Ready entries for the providers kb knows, checked against each provider's own pages on 2026-11-21. Prices move,
# and a provider may rename its models: kb models check NAME --allow NAME lists what the key can really use.
PRESETS: dict[str, dict[str, Any]] = {
    "openai": {"entry": {"protocol": "openai", "url": "https://api.openai.com/v1", "model": "gpt-6.2-sol",
                         "key_env": "OPENAI_API_KEY", "budget": 60_000, "price_in": 2.0, "price_out": 10.0},
               "key_page": "https://platform.openai.com/api-keys",
               "data": "OpenAI says API data is not used for training by default, and is kept up to 30 days."},
    "gemini": {"entry": {"protocol": "openai", "url": "https://generativelanguage.googleapis.com/v1beta/openai",
                         "model": "gemini-4-argon", "key_env": "GEMINI_API_KEY", "budget": 60_000},
               "key_page": "https://aistudio.google.com/apikey",
               "data": "Turn billing on for this key. On the free tier Google uses what you send to improve its "
                       "products; on the paid tier it does not. kb could not confirm this model's price, so the run "
                       "log shows no cost for it until you add price_in and price_out to the entry."},
    "kimi": {"entry": {"protocol": "openai", "url": "https://api.moonshot.ai/v1", "model": "kimi-k3.1-pro",
                       "key_env": "MOONSHOT_API_KEY", "budget": 60_000},
             "key_page": "https://platform.kimi.ai/console/api-keys",
             "data": "Moonshot says API data is not used to train its models. It does not say where the data is "
                     "kept. Its docs do not list model names, so check that kimi-k3.1-pro is among them."},
    "deepseek": {"entry": {"protocol": "openai", "url": "https://api.deepseek.com", "model": "deepseek-flash",
                           "key_env": "DEEPSEEK_API_KEY", "budget": 60_000, "price_in": 0.30, "price_out": 1.20},
                 "key_page": "https://platform.deepseek.com/api_keys",
                 "data": "DeepSeek's privacy policy says it stores data in China and may use it to train its models; "
                         "its API terms do not promise otherwise. Think before sending it cards about client work."},
    "claude": {"entry": {"protocol": "anthropic", "url": CLAUDE_API, "model": "claude-sonnet-5-5",
                         "key_env": "ANTHROPIC_API_KEY", "budget": 60_000, "price_in": 2.0, "price_out": 10.0},
               "key_page": "https://platform.claude.com/settings/keys",
               "data": "Anthropic does not train on API data by default. API use is billed apart from a claude.ai "
                       "plan. It needs the Anthropic SDK: pip install -e \".[key]\"."},
}


def add_preset(path: str | Path, name: str, as_name: str | None = None, model: str | None = None,
               force: bool = False) -> tuple[Model, dict[str, Any]]:
    """Write one provider's entry into the models file, keeping every other entry as it is."""
    if name not in PRESETS:
        raise KeyError(f"kb has no ready entry for '{name}'. It knows: {', '.join(PRESETS)}.")
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"default": None, "models": {}}
    if not isinstance(data, dict) or not isinstance(data.get("models"), dict):
        raise KeyError(f"{p} must hold an object with a \"models\" object inside.")
    as_name = as_name or name
    if as_name in data["models"] and not force:
        raise KeyError(f"{p} already has an entry called '{as_name}'. Add --force to write it again.")
    entry = dict(PRESETS[name]["entry"], **({"model": model} if model else {}))
    data["models"][as_name] = entry
    data["default"] = data.get("default") or next(iter(data["models"]))
    m = _entry(as_name, entry, str(p))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return m, PRESETS[name]
