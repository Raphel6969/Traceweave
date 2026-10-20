"""Acceptance coverage for the complete local API workflow."""

from pathlib import Path

from fastapi.testclient import TestClient

from api.app import create_app


DATASETS = Path(__file__).parents[1] / "datasets"
EVIDENCE = ("case1_auth.jsonl", "case1_application.audit", "case1_network.csv")


def upload_case(client: TestClient) -> tuple[str, dict]:
    files = [("files", (name, (DATASETS / name).read_bytes(), "text/plain")) for name in EVIDENCE]
    response = client.post("/cases", files=files)
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["file_count"] == len(EVIDENCE)
    return payload["id"], payload


def test_all_case_routes_and_report_contract(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))
    health = client.get("/health")
    assert health.json()["status"] == "ok"
    assert health.headers["x-traceweave-version"]
    case_id, created = upload_case(client)

    assert client.get("/diagnostics").status_code == 200
    assert client.get("/telemetry").status_code == 200
    assert client.get("/demo-cases").status_code == 200
    assert client.get("/simulator/catalog").status_code == 200

    listed = client.get("/cases")
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["id"] == case_id

    detail = client.get(f"/cases/{case_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["id"] == case_id
    assert len(body["files"]) == created["file_count"]
    assert body["progress"]["processed"] == body["progress"]["total"] == created["record_count"]
    assert body["chain_valid"] is True

    timeline = client.get(f"/cases/{case_id}/timeline").json()
    graph = client.get(f"/cases/{case_id}/graph").json()
    claims = client.get(f"/cases/{case_id}/claims").json()
    gaps = client.get(f"/cases/{case_id}/gaps").json()
    contradictions = client.get(f"/cases/{case_id}/contradictions").json()
    assert len(timeline) == created["record_count"]
    assert graph["nodes"] == sorted(graph["nodes"])
    assert all(set(link) >= {"source", "target", "relation", "evidence_id", "provenance"} for link in graph["links"])
    assert all(link["provenance"] for link in graph["links"])
    assert isinstance(gaps, list)
    assert isinstance(contradictions, list)

    assert claims
    claim_id = claims[0]["claim_id"]
    for url in (f"/claims/{claim_id}/provenance", f"/cases/{case_id}/claims/{claim_id}/provenance"):
        provenance = client.get(url)
        assert provenance.status_code == 200
        assert provenance.json()["provenance"]
        assert all(item["raw_sha256"] and item["chain_hash"] for item in provenance.json()["provenance"])

    integrity = client.get(f"/cases/{case_id}/integrity")
    assert integrity.json() == {
        "case_id": case_id,
        "verified": True,
        "valid": True,
        "first_broken_index": None,
        "recomputed": True,
    }
    manifest = client.get(f"/cases/{case_id}/manifest")
    assert manifest.status_code == 200
    assert manifest.json()["record_count"] == created["record_count"]
    for export_format, content_type in (("jsonl", "application/x-ndjson"), ("json", "application/json")):
        exported = client.get(f"/cases/{case_id}/events/export?format={export_format}")
        assert exported.status_code == 200
        assert exported.headers["content-type"].startswith(content_type)
        assert exported.headers["content-disposition"].startswith("attachment;")
    assert client.get(f"/cases/{case_id}/events/export?format=xml").status_code == 400
    for suffix in ("progress", "progress/stream"):
        stream = client.get(f"/cases/{case_id}/{suffix}")
        assert stream.status_code == 200
        assert stream.headers["content-type"].startswith("text/event-stream")
        assert stream.text.startswith("data: {")
    status = client.get(f"/cases/{case_id}/progress/status")
    assert status.json()["status"] == "complete"

    report_json = client.get(f"/cases/{case_id}/report?format=json")
    report_html = client.get(f"/cases/{case_id}/report?format=html")
    assert report_json.status_code == 200
    assert report_json.json()["graph"] == graph
    assert report_html.status_code == 200
    assert "<!doctype html>" in report_html.text
    assert "TraceWeave" in report_html.text
    assert client.get(f"/cases/{case_id}/report?format=xml").status_code == 400


def test_simulator_demo_selection_and_bulk_upload(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))
    simulated = client.post("/simulator/files")
    assert simulated.status_code == 200
    files = simulated.json()["files"]
    assert {item["name"] for item in files} == set(EVIDENCE)
    response = client.post(
        "/cases",
        files=[("files", (item["name"], item["content"].encode(), "text/plain")) for item in files],
    )
    assert response.status_code == 201
    case_id = response.json()["id"]
    assert client.get("/cases").json()[0]["id"] == case_id
    assert client.get(f"/cases/{case_id}").json()["status"] == "complete"


def test_demo_catalog_only_contains_loadable_fixtures_and_timeline_has_provenance(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))
    demos = client.get("/demo-cases").json()
    assert demos
    assert all(item["files"] for item in demos)
    for demo in demos:
        loaded = client.post(f"/demo-cases/{demo['id']}/load")
        assert loaded.status_code == 201, (demo, loaded.text)
        timeline = client.get(f"/cases/{loaded.json()['id']}/timeline").json()
        assert timeline
        assert all(item.get("source") and item.get("raw_line") is not None for item in timeline)


def test_graph_contract_accepts_string_nodes(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))
    case_id, _ = upload_case(client)
    graph = client.get(f"/cases/{case_id}/graph").json()
    assert all(isinstance(node, str) for node in graph["nodes"])


def test_api_key_auth_covers_protected_routes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TRACEWEAVE_API_KEY", "secret-test-key")
    client = TestClient(create_app(tmp_path))
    assert client.get("/health").status_code == 200
    assert client.get("/cases").status_code == 401
    assert client.post("/simulator/files").status_code == 401
    assert client.get("/cases", headers={"X-API-Key": "secret-test-key"}).status_code == 200
    assert client.get("/cases", params={"api_key": "secret-test-key"}).status_code == 200


def test_report_bytes_are_deterministic_and_delete_cascades(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))
    first_id, _ = upload_case(client)
    first_json = client.get(f"/cases/{first_id}/report?format=json").content
    first_html = client.get(f"/cases/{first_id}/report?format=html").content
    second_id, _ = upload_case(client)
    assert first_id == second_id
    assert client.get(f"/cases/{second_id}/report?format=json").content == first_json
    assert client.get(f"/cases/{second_id}/report?format=html").content == first_html

    assert client.delete(f"/cases/{first_id}").status_code == 204
    assert client.get(f"/cases/{first_id}").status_code == 404
    assert client.get(f"/cases/{first_id}/integrity").status_code == 404
    assert client.get("/cases").json() == []


def test_frontend_has_no_fabricated_case_payload(tmp_path: Path) -> None:
    # The UI may provide an empty state, but case data must come from API responses.
    source = (Path(__file__).parents[1] / "web" / "app" / "page.tsx").read_text(encoding="utf-8")
    assert "No case selected" in source
    assert "TraceWeave case" not in source
    assert "/demo-cases/" in source
    assert 'view === "findings"' in source
    assert 'view === "upload"' in source
    assert "Paste raw evidence" in source
    assert "occurred_at" in source


def test_generated_demo_runtime_assets_and_local_url_are_packaged() -> None:
    dockerfile = (Path(__file__).parents[1] / "Dockerfile.api").read_text(encoding="utf-8")
    start_sh = (Path(__file__).parents[1] / "start.sh").read_text(encoding="utf-8")
    env_example = (Path(__file__).parents[1] / ".env.example").read_text(encoding="utf-8")
    assert "COPY datasets ./datasets" in dockerfile
    assert "NEXT_PUBLIC_API_URL=http://127.0.0.1:8000" in env_example
    assert "NEXT_PUBLIC_API_URL=http://127.0.0.1:8000" in start_sh
