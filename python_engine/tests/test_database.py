import json
from decimal import Decimal

from landfinder.models.enums import SourceType
from landfinder.models.records import NormalizedPropertyRecord
from landfinder.storage.repositories import Database, PropertyRepository


def test_property_upsert_list_get_and_history(tmp_path) -> None:
    database = Database(tmp_path / "landfinder.sqlite")
    repo = PropertyRepository(database)
    record = NormalizedPropertyRecord(
        source_id="fixture",
        source_type=SourceType.MARKETPLACE,
        external_id="abc",
        canonical_url="https://example.test/a",
        title="Terreno urbano",
        commune="Maipu",
        gross_area_m2=Decimal("10000"),
        price_amount=Decimal("2000"),
        price_currency="UF",
        price_uf=Decimal("2000"),
        price_uf_m2=Decimal("0.20"),
    )

    internal_id = repo.upsert(record)
    rows = repo.list()
    assert len(rows) == 1
    assert rows[0]["internal_id"] == internal_id
    detail = repo.get(internal_id)
    assert detail is not None
    assert detail["publication_title"] == "Terreno urbano"
    assert len(detail["price_history"]) == 1


def test_admin_validation_match_releases_previous_admin_block(tmp_path) -> None:
    database = Database(tmp_path / "landfinder.sqlite")
    repo = PropertyRepository(database)
    record = NormalizedPropertyRecord(
        source_id="fixture",
        source_type=SourceType.MARKETPLACE,
        external_id="admin-1",
        canonical_url="https://example.test/admin-1",
        title="Terreno con validacion",
        region="Atacama",
        commune="Chanaral",
        latitude=-26.37,
        longitude=-70.50,
    )

    internal_id = repo.upsert(record)
    repo.update_admin_validation(
        internal_id,
        {
            "source_region": "Atacama",
            "source_commune": "Chanaral",
            "calculated_region": "Antofagasta",
            "calculated_commune": "Calama",
            "admin_validation_status": "COMMUNE_AND_REGION_MISMATCH",
            "admin_validation_confidence": 0.9,
            "admin_validation_reason": "Mismatch.",
        },
    )
    blocked = repo.get(internal_id)
    assert blocked is not None
    assert blocked["territorial_status"] == "BLOCKED_LOCATION_CONFLICT"
    assert "ADMIN_LOCATION_CONFLICT" in json.loads(blocked["anomaly_flags_json"])

    repo.update_admin_validation(
        internal_id,
        {
            "source_region": "Atacama",
            "source_commune": "Chanaral",
            "calculated_region": "Atacama",
            "calculated_commune": "Chanaral",
            "admin_validation_status": "MATCH",
            "admin_validation_confidence": 0.95,
            "admin_validation_reason": "Match.",
        },
    )
    released = repo.get(internal_id)
    assert released is not None
    assert released["territorial_status"] == "SIN_INFORMACION_SUFICIENTE"
    assert "ADMIN_LOCATION_CONFLICT" not in json.loads(released["anomaly_flags_json"])
