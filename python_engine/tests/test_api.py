from fastapi.testclient import TestClient

from landfinder.api.app import create_app
from landfinder.core.settings import load_settings
from landfinder.models.enums import SourceType
from landfinder.storage.repositories import Database, SourceRecordAuditRepository


def test_api_health_session_and_sources(tmp_path) -> None:
    settings = load_settings(data_dir=tmp_path, port=8766, session_token="test-token")
    client = TestClient(create_app(settings))

    assert client.get("/health").status_code == 200
    assert client.get("/session").json()["token"] == "test-token"
    assert client.get("/sources").status_code == 401

    response = client.get("/sources", headers={"Authorization": "Bearer test-token"})
    assert response.status_code == 200
    assert {item["source_id"] for item in response.json()} >= {
        "mercado_publico",
        "mercadolibre_real_estate",
    }
    assert {item["source_role"] for item in response.json()} == {"SearchSource"}

    enrichment = client.get(
        "/enrichment-sources",
        headers={"Authorization": "Bearer test-token"},
    )
    assert enrichment.status_code == 200
    assert {item["source_id"] for item in enrichment.json()} >= {"cmf_uf", "minvu"}


def test_api_exposes_source_record_classifier_audit(tmp_path) -> None:
    settings = load_settings(data_dir=tmp_path, port=8766, session_token="test-token")
    database = Database(settings.database_path)
    source_records = SourceRecordAuditRepository(database)
    source_record_id = source_records.upsert(
        "job-api",
        {
            "source": "mercado_publico",
            "source_type": SourceType.PUBLIC_PROCUREMENT.value,
            "external_id": "1234-1-LQ26",
            "title": "Compra terreno",
            "automatic_classification": "LAND_ACQUISITION",
            "automatic_confidence": 0.91,
            "automatic_score": 110,
            "positive_terms": ["compra", "terreno"],
            "rules_triggered": ["TITLE_LAND_ACQUISITION"],
            "raw_payload": {"Nombre": "Compra terreno"},
        },
    )
    client = TestClient(create_app(settings))
    headers = {"Authorization": "Bearer test-token"}

    listing = client.get("/searches/job-api/source-records", headers=headers)
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["positive_terms"] == ["compra", "terreno"]

    diagnostics = client.get("/searches/job-api/classifier-diagnostics", headers=headers)
    assert diagnostics.status_code == 200
    assert diagnostics.json()["classifier_distribution"]["accepted"] == 1

    detail = client.get(f"/source-records/{source_record_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["external_id"] == "1234-1-LQ26"

    reviewed = client.put(
        f"/source-records/{source_record_id}/manual-classification",
        headers=headers,
        json={"manual_classification": "CONFIRMED_LAND"},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["manual_classification"] == "CONFIRMED_LAND"
    assert reviewed.json()["manual_review_status"] == "REVIEWED"


def test_api_exposes_chile_catalog_and_keyword_presets(tmp_path) -> None:
    settings = load_settings(data_dir=tmp_path, port=8766, session_token="test-token")
    client = TestClient(create_app(settings))
    headers = {"Authorization": "Bearer test-token"}

    regions = client.get("/catalog/regions", headers=headers)
    assert regions.status_code == 200
    region_items = regions.json()["items"]
    assert len(region_items) == 16
    assert {item["code"] for item in region_items} >= {"CL-RM", "CL-TA", "CL-NB"}

    communes = client.get("/catalog/regions/CL-RM/communes", headers=headers)
    assert communes.status_code == 200
    assert {item["name"] for item in communes.json()["items"]} >= {
        "Maipu",
        "Pudahuel",
        "Cerrillos",
        "Santiago",
    }
    assert {item["region_code"] for item in communes.json()["items"]} == {"CL-RM"}

    all_communes = client.get("/catalog/regions/ALL/communes", headers=headers)
    assert all_communes.status_code == 200
    all_commune_items = all_communes.json()["items"]
    assert len(all_commune_items) > len(communes.json()["items"])
    assert {item["region_code"] for item in all_commune_items} >= {"CL-RM", "CL-TA"}

    presets = client.get("/catalog/search-keyword-presets", headers=headers)
    assert presets.status_code == 200
    default = next(
        item for item in presets.json()["items"] if item["id"] == "BUSQUEDA_TERRENOS_CHILE"
    )
    assert "peladero" in default["keywords"]
    assert "sitio eriazo" in default["keywords"]
    assert default["default_mode"] == "ANY"
