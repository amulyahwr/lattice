import os

# Provide a default model name so resolve_model() doesn't raise in tests that
# mock make_llm_client or complete() without setting LLM_MODEL in the environment.
os.environ.setdefault("LLM_MODEL", "test-model")

import pytest


@pytest.fixture(autouse=True)
def _isolate_web_app(tmp_path, monkeypatch):
    """Patch the web app's global _cfg and _db to an isolated tmp_path instance.

    Prevents any test from accidentally reading or writing to the real ~/.lattice
    when using TestClient(app) without an explicit set_config() call.
    """
    import lattice.web.app as _web
    from lattice.config import Config
    from lattice.db import LatticeDB

    cfg = Config(lattice_dir=tmp_path, llm_provider="ollama", llm_model="test-model")
    db = LatticeDB(cfg.lattice_dir)
    monkeypatch.setattr(_web, "_cfg", cfg)
    monkeypatch.setattr(_web, "_db", db)
    yield
    # monkeypatch restores originals automatically after each test
