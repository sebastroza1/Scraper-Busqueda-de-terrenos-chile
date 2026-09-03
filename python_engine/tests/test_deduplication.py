from decimal import Decimal

from landfinder.deduplication.engine import DeduplicationEngine
from landfinder.models.enums import SourceType
from landfinder.models.records import NormalizedPropertyRecord


def test_deduplication_groups_close_records() -> None:
    records = [
        NormalizedPropertyRecord(
            source_id="a",
            source_type=SourceType.MARKETPLACE,
            title="Gran terreno urbano Puente Alto",
            commune="Puente Alto",
            latitude=-33.6,
            longitude=-70.57,
            gross_area_m2=Decimal("10000"),
            price_uf=Decimal("18000"),
        ),
        NormalizedPropertyRecord(
            source_id="b",
            source_type=SourceType.BROKER,
            title="Terreno urbano en Puente Alto",
            commune="Puente Alto",
            latitude=-33.6002,
            longitude=-70.5701,
            gross_area_m2=Decimal("10020"),
            price_uf=Decimal("18100"),
        ),
    ]

    matches = DeduplicationEngine().cluster(records)
    assert matches[0].canonical_id == matches[1].canonical_id
    assert matches[1].match_score >= 0.58
