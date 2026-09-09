from landfinder.connectors.auctions.bienes_nacionales import BienesNacionalesProvider
from landfinder.connectors.base import SearchSource, SourceConnector
from landfinder.connectors.public_procurement.chilecompra_ocds import ChileCompraOCDSProvider
from landfinder.connectors.public_procurement.mercado_publico import MercadoPublicoConnector
from landfinder.models.enums import SourceRole


def default_connectors() -> list[SourceConnector]:
    return default_search_sources()


def default_search_sources() -> list[SearchSource]:
    return [
        BienesNacionalesProvider(),
        ChileCompraOCDSProvider(),
        MercadoPublicoConnector(),
    ]


def default_enrichment_sources() -> list[dict[str, str]]:
    return [
        {
            "source_id": "cmf_uf",
            "source_name": "CMF - Conversion UF",
            "source_role": SourceRole.ENRICHMENT.value,
            "source_type": "monetary",
            "strategy": "official_api",
            "usage": "Conversion UF",
        },
        {
            "source_id": "minvu",
            "source_name": "IDE MINVU - Informacion territorial",
            "source_role": SourceRole.ENRICHMENT.value,
            "source_type": "geospatial",
            "strategy": "arcgis_rest",
            "usage": "Territorial",
        },
    ]
