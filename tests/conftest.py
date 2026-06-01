import os

# Provide a default model name so resolve_model() doesn't raise in tests that
# mock make_llm_client or complete() without setting LLM_MODEL in the environment.
os.environ.setdefault("LLM_MODEL", "test-model")
