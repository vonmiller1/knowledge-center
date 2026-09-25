"""The service half of the model pills: which model ANSWERED, and whether it searched.

The console shows two pills at the top right: the model that answered the last request, and
``Search`` when that answer used an online search tool. Both come from response headers the kit
emits (``install_answer_provenance`` in ``api/app.py``) for whatever the model adapters NOTED as
they called. Before a request is answered the pill shows ``generator_model`` from ``/healthz``,
so that value must be the model the bound adapter calls, never one a configuration flag names
while the adapter calls another.

The model calls here are commitment extraction and minutes narration. Under ``local`` both are
the deterministic stand-in, which answers as the stub ``generator_model`` names. The managed
Gemini adapter is a deployment-wired placeholder that raises before calling anything, so it
notes nothing and the pill keeps naming ``managed-not-implemented``.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from hex_service_kit import provenance

from meeting_capture import config
from meeting_capture.adapters.gcp.generation import CloudGenerationAdapter
from meeting_capture.adapters.local.generation import STUB_MODEL, LocalGenerationAdapter
from meeting_capture.api import app as app_module
from meeting_capture.ports.generation import ExtractionRequest, NarrationRequest

from tests import REPO_ROOT
from tests.conftest import local_settings

ANSWERED_BY = "x-answered-by"
SEARCH_USED = "x-search-used"
_SG = "fixture://meetings/sg-1"


@pytest.fixture()
def local_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """The API under ``local`` whatever the shell exported: CI runs with no profile set."""
    monkeypatch.setenv(config._PROFILE_ENV, "local")
    app_module._container.cache_clear()
    with TestClient(app_module.app, client=("127.0.0.1", 50000)) as client:
        yield client
    app_module._container.cache_clear()


def _capture(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/v1/capture",
        json={"audio_uri": _SG, "market": "SG", "as_of": "2026-08-03"},
        headers={"x-dev-persona": "auditor"},
    )
    assert response.status_code == 200, response.text
    return dict(response.headers)


def test_the_local_model_answers_as_the_stub_the_pill_first_names(
    local_client: TestClient,
) -> None:
    headers = _capture(local_client)
    assert headers[ANSWERED_BY] == STUB_MODEL
    assert SEARCH_USED not in headers
    assert local_settings().generator_model == STUB_MODEL


def test_a_call_that_searched_says_so_and_the_next_request_starts_fresh(
    local_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = LocalGenerationAdapter.narrate

    def searching(self: LocalGenerationAdapter, request: NarrationRequest) -> str:
        provenance.note_model("fake-searching-model")
        provenance.note_search()
        return original(self, request)

    monkeypatch.setattr(LocalGenerationAdapter, "narrate", searching)
    headers = _capture(local_client)
    assert headers[ANSWERED_BY] == f"{STUB_MODEL}, fake-searching-model"
    assert headers[SEARCH_USED] == "true"
    monkeypatch.setattr(LocalGenerationAdapter, "narrate", original)
    headers = _capture(local_client)
    assert headers[ANSWERED_BY] == STUB_MODEL
    assert SEARCH_USED not in headers


def test_extraction_is_pinned_and_the_minutes_are_drafted_with_no_temperature(
    local_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, float | None] = {}
    extract, narrate = LocalGenerationAdapter.extract, LocalGenerationAdapter.narrate

    def recording_extract(self: LocalGenerationAdapter, request: ExtractionRequest) -> str:
        seen["extract"] = request.temperature
        return extract(self, request)

    def recording_narrate(self: LocalGenerationAdapter, request: NarrationRequest) -> str:
        seen["narrate"] = request.temperature
        return narrate(self, request)

    monkeypatch.setattr(LocalGenerationAdapter, "extract", recording_extract)
    monkeypatch.setattr(LocalGenerationAdapter, "narrate", recording_narrate)
    _capture(local_client)
    assert seen == {"extract": 0.0, "narrate": None}


def test_the_request_types_send_no_temperature_unless_a_call_site_pins_one() -> None:
    for request_type in (ExtractionRequest, NarrationRequest):
        assert request_type.__dataclass_fields__["temperature"].default is None


def test_the_managed_placeholder_notes_nothing_because_it_never_answers() -> None:
    """An adapter that raises before calling a model must not put a model on screen."""
    settings = dataclasses.replace(local_settings(), profile="gcp")
    request = ExtractionRequest(transcript=None)  # type: ignore[arg-type]
    with provenance.scope() as record, pytest.raises(Exception):  # noqa: B017, PT011
        CloudGenerationAdapter(settings).extract(request)
    assert record.models == []
    assert record.search_used is False
    assert settings.generator_model == "managed-not-implemented"


def test_no_flag_swaps_in_a_model_the_adapter_never_calls() -> None:
    """The latent false banner: a flag that moved the pill but not the model that answered."""
    models = SimpleNamespace(
        reasoning="the-model-the-adapter-calls",
        hard_reasoning="a-model-nobody-calls",
        use_hard_reasoning=True,
    )
    named = config._model_from_settings(SimpleNamespace(models=models), "models.reasoning")
    assert named == "the-model-the-adapter-calls"


def test_the_hard_reasoning_flag_does_not_exist() -> None:
    settings_file = (REPO_ROOT / "config" / "settings.yaml").read_text(encoding="utf-8")
    assert "use_hard_reasoning" not in settings_file
    for source in sorted((REPO_ROOT / "src").rglob("*.py")):
        assert "use_hard_reasoning" not in source.read_text(encoding="utf-8"), source
