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
