"""End-to-end HTTP tests with a stub engine.

Covers the full request path — upload, audio conversion, biasing, correction,
parsing, response shape — without needing a model. This is the contract the
other four teammates code against, so it is worth locking down.
"""

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from stt import server
from stt.engines.base import ASREngine, TranscriptResult


class StubEngine(ASREngine):
    """Records the bias it was handed so we can assert biasing is wired up."""

    bias_style = "vocabulary"
    name = "stub-engine"

    def __init__(self, text="two kopi c siew dai tapao"):
        self.text = text
        self.last_bias = None

    def transcribe(self, audio_path, bias=None):
        self.last_bias = bias
        return TranscriptResult(
            text=self.text, engine=self.name, latency_ms=7, confidence=-0.3
        )


@pytest.fixture
def client():
    stub = StubEngine()
    server._state["engine"] = stub
    server._state["catalogues"] = {}
    # Bypass lifespan so the stub is not replaced by a real engine.
    with TestClient(server.app) as c:
        server._state["engine"] = stub
        c.stub = stub
        yield c


@pytest.fixture
def wav(tmp_path):
    path = tmp_path / "order.wav"
    t = np.linspace(0, 1.5, 24000, dtype="float32")
    sf.write(str(path), np.sin(2 * np.pi * 300 * t), 16000)
    return path


def _post(client, wav, **params):
    with open(wav, "rb") as fh:
        return client.post(
            "/transcribe", files={"audio": ("order.wav", fh, "audio/wav")},
            params=params,
        )


def test_health_reports_engine(client):
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["engine"] == "stub-engine"


def test_catalogue_endpoint_lists_items(client):
    body = client.get("/catalogue", params={"name": "hawker"}).json()
    assert body["merchant"] == "Ah Seng Kopitiam"
    assert any(i["canonical"] == "KOPI_C" for i in body["items"])


def test_unknown_catalogue_is_404(client):
    assert client.get("/catalogue", params={"name": "nope"}).status_code == 404


def test_transcribe_returns_full_contract(client, wav):
    body = _post(client, wav).json()
    for key in ("text", "corrected_text", "matched_items", "confidence",
                "low_confidence", "engine", "latency_ms", "order", "readback"):
        assert key in body, f"missing contract key: {key}"

    assert body["order"]["takeaway"] is True
    assert body["order"]["lines"][0]["canonical"] == "KOPI_C"
    assert body["order"]["lines"][0]["quantity"] == 2
    assert body["readback"] == "2x Kopi-C (siew dai) — takeaway"


def test_biasing_is_passed_to_engine(client, wav):
    _post(client, wav)
    assert client.stub.last_bias.startswith("Vocabulary:")


def test_bias_can_be_disabled_for_ab_testing(client, wav):
    _post(client, wav, bias="false")
    assert client.stub.last_bias is None


def test_catalogue_swap_changes_result(client, wav):
    # Same audio, different merchant: the hawker terms must stop matching.
    client.stub.text = "one packet of jasmine rice and milo tapao"
    grocery = _post(client, wav, catalogue="grocery").json()
    assert {line["canonical"] for line in grocery["order"]["lines"]} == {
        "JASMINE_RICE", "MILO"
    }
    hawker = _post(client, wav, catalogue="hawker").json()
    assert "JASMINE_RICE" not in {
        line["canonical"] for line in hawker["order"]["lines"]
    }


def test_short_audio_returns_400(client, tmp_path):
    path = tmp_path / "tiny.wav"
    sf.write(str(path), np.zeros(800, dtype="float32"), 16000)
    response = _post(client, path)
    assert response.status_code == 400 and "at least" in response.json()["detail"]


class UnavailableEngine(StubEngine):
    """An engine whose backend is not installed on this machine."""

    name = "unavailable-engine"

    @classmethod
    def is_available(cls):
        return False


def test_health_is_degraded_when_backend_missing(client):
    server._state["engine"] = UnavailableEngine()
    body = client.get("/health").json()
    assert body["status"] == "degraded" and body["engine_ready"] is False


def test_transcribe_503s_with_actionable_message_when_backend_missing(client, wav):
    server._state["engine"] = UnavailableEngine()
    response = _post(client, wav)
    assert response.status_code == 503
    # The message must tell the reader what to install, not just "unavailable".
    assert "pip install" in response.json()["detail"]


def test_catalogue_still_served_when_engine_unavailable(client):
    # Frontend teammates must be able to build against the contract on any
    # machine, so a missing ASR backend cannot take the whole service down.
    server._state["engine"] = UnavailableEngine()
    assert client.get("/catalogue", params={"name": "hawker"}).status_code == 200
