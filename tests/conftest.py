"""Every test gets its own empty keys file, so a run on your laptop never reads or changes your real keys, and a
key a test keeps (kb fills the environment from the file when a command starts) is gone when the test ends."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _own_keys_file(tmp_path, monkeypatch):
    monkeypatch.setenv("KB_KEYS", str(tmp_path / "kb-keys" / "keys.env"))
    before = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(before)
