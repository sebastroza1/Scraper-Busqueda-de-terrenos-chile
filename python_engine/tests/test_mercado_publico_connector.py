import httpx
import pytest

from landfinder.connectors.base import SourceUnavailableError
from landfinder.connectors.public_procurement.mercado_publico import (
    PublicProcurementLandClassification,
    _matches_keywords,
    _raise_safe_http_error,
    classify_public_procurement_land_tender,
    explain_public_procurement_land_tender,
)
from landfinder.connectors.transforms import mercado_publico_tender_to_raw


def test_classifies_land_acquisition() -> None:
    item = {
        "Nombre": "Adquisicion de terreno para proyecto habitacional",
        "Descripcion": "Compra de inmueble urbano para SERVIU",
    }

    assert (
        classify_public_procurement_land_tender(item)
        == PublicProcurementLandClassification.LAND_DEMAND
    )


def test_explainable_classifier_returns_terms_rules_and_manual_review_hint() -> None:
    item = {
        "Nombre": "Compra terreno para vivienda social",
        "Descripcion": "Adquisicion de inmueble urbano por SERVIU",
    }

    decision = explain_public_procurement_land_tender(item)

    assert (
        decision.classification.value
        == PublicProcurementLandClassification.LAND_DEMAND.value
    )
    assert decision.confidence >= 0.8
    assert {"compra", "terreno"}.issubset(set(decision.positive_terms))
    assert "PUBLIC_BUYER_LAND_DEMAND" in decision.rules_triggered
    assert decision.requires_manual_review is False


def test_classifies_acquisition_title_over_sale_product_category() -> None:
    item = {
        "Nombre": "ADQUISICION DE TERRENO PARA PROYECTO EDUCACIONAL",
        "Items": {
            "Listado": [
                {
                    "Categoria": "Servicios inmobiliarios / Venta de propiedades",
                    "NombreProducto": "Venta de terrenos comerciales o industriales",
                }
            ]
        },
    }

    assert (
        classify_public_procurement_land_tender(item)
        == PublicProcurementLandClassification.LAND_DEMAND
    )


def test_classifies_mojibake_acquisition_title() -> None:
    item = {
        "Nombre": "ADQUISICI\uFFFdN DE TERRENO PARA PROYECTO EDUCACIONAL",
    }

    assert (
        classify_public_procurement_land_tender(item)
        == PublicProcurementLandClassification.LAND_DEMAND
    )


def test_classifies_land_sale() -> None:
    item = {"Nombre": "Enajenacion inmueble municipal", "Descripcion": "Venta de terreno"}

    assert (
        classify_public_procurement_land_tender(item)
        == PublicProcurementLandClassification.LAND_SALE_PROCESS
    )


def test_classifies_municipal_land_sale_with_legal_acquisition_text_as_sale() -> None:
    item = {
        "Nombre": "VENTA DE TERRENOS DE PROPIEDAD MUNICIPAL LA SERENA",
        "Descripcion": (
            "Seleccionar compradores para contrato de compraventa de inmuebles "
            "de propiedad municipal. Las municipalidades podran adquirir y "
            "enajenar bienes muebles e inmuebles."
        ),
        "Items": {
            "Listado": [
                {
                    "NombreProducto": "Venta de terrenos comerciales o industriales",
                    "Descripcion": "Venta Terreno N1: Lote 5 de la Manzana 5",
                }
            ]
        },
    }

    assert (
        classify_public_procurement_land_tender(item)
        == PublicProcurementLandClassification.LAND_SALE_PROCESS
    )


def test_classifies_civil_works_with_weak_lote_term_as_false_positive() -> None:
    item = {
        "Nombre": "Construccion Plaza de Conmemoracion Pueblo Chilote",
        "Descripcion": "Ejecucion Proyecto Plaza de Conmemoracion",
        "Items": {
            "Listado": [
                {
                    "Categoria": "Servicios de construccion y mantenimiento",
                    "NombreProducto": "Construccion de obras civiles",
                    "Descripcion": "Construccion plaza en lote municipal",
                }
            ]
        },
    }

    assert (
        classify_public_procurement_land_tender(item)
        == PublicProcurementLandClassification.WORKS_ON_EXISTING_PROPERTY
    )


def test_classifies_forest_service_lote_toponym_as_false_positive() -> None:
    item = {
        "Nombre": "Restauracion forestal en Lote 2 Ojo Bueno",
        "Descripcion": (
            "Participar en la licitacion publica para el servicio de "
            "restauracion forestal mediante el portal de compras del Estado."
        ),
        "Items": {
            "Listado": [
                {
                    "Categoria": "Administracion de cultivos forestales",
                    "NombreProducto": "Servicios de asistencia forestal",
                }
            ]
        },
    }

    assert (
        classify_public_procurement_land_tender(item)
        == PublicProcurementLandClassification.LAND_RELATED_SERVICE
    )


def test_classifies_false_positive_soil_study() -> None:
    item = {
        "Nombre": "Estudio de mecanica de suelo",
        "Descripcion": "Informe para obras civiles",
    }

    assert (
        classify_public_procurement_land_tender(item)
        == PublicProcurementLandClassification.VALUATION_OR_STUDY
    )


def test_classifies_cubre_suelos_as_false_positive() -> None:
    item = {
        "Nombre": "Adquisicion de cubre suelos y sistema de riego",
        "Descripcion": (
            "Recuperacion de espacio publico con reparacion de cesped en "
            "terreno de administracion municipal."
        ),
        "Items": {
            "Listado": [
                {
                    "NombreProducto": "Canal de riego",
                    "Descripcion": "Cubre suelo Tiki Tiki",
                }
            ]
        },
    }

    assert (
        classify_public_procurement_land_tender(item)
        == PublicProcurementLandClassification.GOODS_FOR_PROPERTY
    )


def test_classifies_maintenance_articles_for_buildings_as_false_positive() -> None:
    item = {
        "Nombre": "Adquisicion de articulos electricos para mantencion de inmuebles",
        "Descripcion": "Materiales para servicio de mantenimiento.",
    }

    assert (
        classify_public_procurement_land_tender(item)
        == PublicProcurementLandClassification.GOODS_FOR_PROPERTY
    )


def test_classifies_site_web_as_false_positive() -> None:
    item = {
        "Nombre": "Adquisicion de sitio web institucional",
        "Descripcion": "Servicio de plataforma web municipal.",
    }

    assert (
        classify_public_procurement_land_tender(item)
        == PublicProcurementLandClassification.FALSE_POSITIVE
    )


def test_classifies_sitio_eriazo_with_area_as_possible_land() -> None:
    item = {"Nombre": "Sitio eriazo 10.000 m2 disponible"}

    assert (
        classify_public_procurement_land_tender(item)
        == PublicProcurementLandClassification.UNKNOWN
    )


def test_classifies_peladero_en_venta_as_possible_not_confirmed_sale() -> None:
    item = {"Nombre": "Peladero urbano en venta"}

    assert (
        classify_public_procurement_land_tender(item)
        == PublicProcurementLandClassification.UNKNOWN
    )


def test_classifies_real_sale_phrase() -> None:
    item = {"Nombre": "Venta de terreno urbano"}

    assert (
        classify_public_procurement_land_tender(item)
        == PublicProcurementLandClassification.LAND_SALE_PROCESS
    )


def test_mercado_publico_transform_keeps_buyer_location_separate() -> None:
    item = {
        "CodigoExterno": "1234-1-LQ26",
        "Nombre": "Compra terreno",
        "Estado": "Publicada",
        "MontoEstimado": 1000000,
        "Comprador": {
            "NombreOrganismo": "SERVIU Metropolitano",
            "NombreUnidad": "Unidad de vivienda",
            "ComunaUnidad": "Maipu",
            "RegionUnidad": "Region Metropolitana de Santiago",
            "DireccionUnidad": "Av. Ejemplo 123",
        },
        "Fechas": {"FechaPublicacion": "30-08-2026", "FechaCierre": "12-09-2026"},
        "landfinder": {
            "procurement_classification": "LAND_DEMAND",
            "original_text": "Compra terreno SERVIU",
        },
    }

    raw = mercado_publico_tender_to_raw(item)

    assert raw.external_id == "1234-1-LQ26"
    assert raw.commune_raw is None
    assert raw.region_raw is None
    assert raw.address_raw is None
    assert raw.price_raw == "CLP 1000000"
    assert raw.raw_payload["landfinder"]["organization_commune"] == "Maipu"
    assert (
        raw.raw_payload["landfinder"]["organization_region"]
        == "Region Metropolitana de Santiago"
    )
    assert raw.raw_payload["landfinder"]["organization_address"] == "Av. Ejemplo 123"
    assert raw.raw_payload["landfinder"]["property_commune"] is None
    assert raw.raw_payload["landfinder"]["property_address"] is None
    assert raw.raw_payload["landfinder"]["procurement_classification"] == "LAND_DEMAND"


def test_mercado_publico_transform_ignores_code_like_tiny_amount_and_extracts_area() -> None:
    item = {
        "CodigoExterno": "4295-54-LR26",
        "Nombre": "VENTA DE TERRENOS DE PROPIEDAD MUNICIPAL LA SERENA",
        "MontoEstimado": 2,
        "Items": {
            "Listado": [
                {
                    "NombreProducto": "Venta de terrenos comerciales o industriales",
                    "Descripcion": "Venta Terreno N1: Lote 5, superficie 12.500 m2",
                }
            ]
        },
    }

    raw = mercado_publico_tender_to_raw(item)

    assert raw.price_raw is None
    assert raw.area_raw == "12.500 m2"


def test_mercado_publico_transform_extracts_hectares_but_not_units() -> None:
    item = {
        "CodigoExterno": "9999-1-LQ26",
        "Nombre": "Venta de terreno urbano",
        "Items": {
            "Listado": [
                {
                    "NombreProducto": "Venta de terrenos comerciales o industriales",
                    "Descripcion": "Paño con superficie 1,2 ha y 1200 unidades referenciales",
                }
            ]
        },
    }

    raw = mercado_publico_tender_to_raw(item)

    assert raw.area_raw == "1,2 ha"


def test_regression_real_container_tender_is_not_land_demand() -> None:
    item = {
        "CodigoExterno": "2427-87-LE26",
        "Nombre": (
            "ADQUISICION DE CONTENEDORES CUARTEL DE ASEO LUCUMO "
            "INMUEBLE EX TEATRO PACIFICO DAT."
        ),
    }

    assert (
        classify_public_procurement_land_tender(item)
        == PublicProcurementLandClassification.GOODS_FOR_PROPERTY
    )


def test_regression_real_land_purchase_tenders_are_public_demand() -> None:
    for code, name in [
        ("4328-33-B226", "ADQUISICION TERRENO TIUQUILEMU"),
        ("2794-22-LR26", "Adquisicion de Terreno para Medio Ambiente L.A."),
        ("5358-9-LR26", "ADQUISICION DE TERRENO PARA PROYECTO EDUCACIONAL U"),
    ]:
        assert classify_public_procurement_land_tender(
            {"CodigoExterno": code, "Nombre": name}
        ) == PublicProcurementLandClassification.LAND_DEMAND


def test_regression_lawn_area_does_not_become_parcel_surface() -> None:
    item = {
        "CodigoExterno": "2450-90-LE26",
        "Nombre": "Adquisicion de cubre suelos Tiki Tiki y sistema de riego",
        "Descripcion": "Recuperacion de espacio publico con cesped en 1.200 m2.",
    }

    raw = mercado_publico_tender_to_raw(item)

    assert raw.area_raw is None
    assert raw.raw_payload["landfinder"]["surface_context"] == "LAWN_AREA"


def test_mercado_publico_keyword_matching_uses_word_boundaries_and_modes() -> None:
    item = {"Nombre": "Adquisicion de sitio web institucional"}

    assert _matches_keywords(item, ["sitio"], mode="ANY")
    assert not _matches_keywords(item, ["sit"], mode="ANY")
    assert not _matches_keywords(item, ["sitio", "terreno"], mode="ALL")


def test_mercado_publico_429_is_reported_as_source_unavailable() -> None:
    response = httpx.Response(
        429,
        request=httpx.Request(
            "GET",
            "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json",
        ),
    )

    with pytest.raises(SourceUnavailableError, match="rate limited"):
        _raise_safe_http_error(response)
