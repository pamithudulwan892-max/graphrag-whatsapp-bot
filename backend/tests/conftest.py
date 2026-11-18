import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Tests run offline and fast: no LLM, hash embeddings, no cross-encoder download.
TEST_ENV = {
    "LLM_OFFLINE": "true",
    "EMBEDDING_MODEL": "hash",
    "USE_RERANKER": "false",
    "ADMIN_API_KEY": "test-admin",
    "TWILIO_AUTH_TOKEN": "twilio-test-token",
    "META_APP_SECRET": "meta-test-secret",
    "META_VERIFY_TOKEN": "meta-verify",
    "WHATSAPP_DRY_RUN": "true",
    "SEED_SAMPLE_DOCS": "false",
    "PUBLIC_BASE_URL": "",
    "RATE_LIMIT_PER_MINUTE": "100",
    "MIN_RELEVANCE": "0.0",
}


@pytest.fixture
def settings(tmp_path, monkeypatch):
    for k, v in TEST_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    from app.config import get_settings

    get_settings.cache_clear()
    s = get_settings()
    yield s
    get_settings.cache_clear()
