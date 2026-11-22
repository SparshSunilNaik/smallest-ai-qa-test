from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from fake_api import VALID_KEY, make_wav  # noqa: E402

from smallest_qa.config import Settings  # noqa: E402
from smallest_qa.fixtures import STT_REFERENCE_TEXT, Fixture  # noqa: E402


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(api_key=VALID_KEY, base_url="https://fake.invalid", evidence_dir=tmp_path / "evidence",
                    inter_request_delay_s=0.0, max_requests=28)


@pytest.fixture
def fixture_wav(tmp_path: Path) -> Fixture:
    data = make_wav(16000, 1.5)
    path = tmp_path / "stt.wav"
    path.write_bytes(data)
    return Fixture(path, STT_REFERENCE_TEXT, hashlib.sha256(data).hexdigest(), len(data), 1.5, 16000)
