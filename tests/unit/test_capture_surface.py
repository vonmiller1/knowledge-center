"""The capture surfaces (API, CLI, agent tool) all run the same engine and route under R8."""

from __future__ import annotations

from fastapi.testclient import TestClient

from meeting_capture.agent.tools import capture_meeting
from meeting_capture.cli.main import main as cli_main

from tests.conftest import local_settings

_SG = "fixture://meetings/sg-1"


def test_capture_endpoint_returns_the_register_and_grounded_minutes(
    api_client: TestClient,
) -> None:
    resp = api_client.post(
        "/v1/capture",
        json={"audio_uri": _SG, "market": "SG", "as_of": "2026-08-03"},
        headers={"x-dev-persona": "auditor"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["minutes_grounded"] is True
    assert body["requires_human_review"] is True
    accepted = [e for e in body["entries"] if e["outcome"] == "accepted"]
    assert len(accepted) == 4
    # Consequential entries carry a routing reference (rule R8), and no raw NRIC leaks.
    consequential = [e for e in body["entries"] if e["requires_human_review"]]
    assert consequential and all(e["review_ref"] for e in consequential)
    assert "S1234567D" not in resp.text


def test_capture_endpoint_rejects_a_bad_as_of() -> None:
    from meeting_capture.api.app import app

    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        resp = client.post(
            "/v1/capture",
            json={"audio_uri": _SG, "market": "SG", "as_of": "not-a-date"},
            headers={"x-dev-persona": "auditor"},
        )
    assert resp.status_code == 422


def test_capture_endpoint_rejects_an_unknown_market(api_client: TestClient) -> None:
    resp = api_client.post(
        "/v1/capture",
        json={"audio_uri": _SG, "market": "ZZ", "as_of": "2026-08-03"},
        headers={"x-dev-persona": "auditor"},
    )
    assert resp.status_code == 422


def test_the_agent_tool_masks_pii_and_routes() -> None:
    result = capture_meeting(_SG, "SG", "2026-08-03", settings=local_settings())
    assert "S1234567D" not in str(result)
    assert result["review_refs"], "consequential entries must be routed under R8"


def test_the_cli_capture_command_runs(capsys: object) -> None:
    code = cli_main(["capture", _SG, "--market", "SG", "--as-of", "2026-08-03"])
    assert code == 0
