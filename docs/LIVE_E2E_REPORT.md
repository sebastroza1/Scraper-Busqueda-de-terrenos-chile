# Live E2E Report

Fecha UTC: 2026-09-02T04:25:29.971858+00:00

## API Local

Esta validacion fue ejecutada contra la app FastAPI local con TestClient.
No se incluyen secretos, tokens, tickets ni claves API.

## Credenciales

| Fuente | Estado |
|---|---|
| Mercado Publico | `CONNECTED` |
| CMF | `CONNECTED` |
| MercadoLibre | `NOT_CONFIGURED` |

## SearchJobs Reales Por API

| SearchJob | Fuente | Estado | Fuente recibidos | Clasificados | Aceptados | Posibles | Rechazados | Persistidos |
|---|---|---|---:|---:|---:|---:|---:|---:|
| `ba7111fd-b477-41d8-ba3a-7f5db0d20058` | mercado_publico | `COMPLETED_WITH_WARNINGS` | 29 | 29 | 3 | 4 | 22 | 3 |

## Clasificador Y Registros Fuente

```json
[
  {
    "search_id": "ba7111fd-b477-41d8-ba3a-7f5db0d20058",
    "requested": {
      "search_sources": [
        "mercado_publico"
      ],
      "enrichment_sources": [
        "cmf_uf",
        "minvu"
      ],
      "keywords": [
        "terreno",
        "terrenos",
        "predio",
        "predios",
        "sitio",
        "sitios",
        "sitio eriazo",
        "sitios eriazos",
        "sitio vacio",
        "sitio sin construir",
        "eriazo",
        "eriazos",
        "terreno eriazo",
        "terreno baldio",
        "peladero",
        "peladeros",
        "pano",
        "panos",
        "gran pano",
        "pano urbano",
        "macrolote",
        "macrolotes",
        "lote",
        "lotes",
        "lote urbano",
        "loteo",
        "suelo",
        "suelo urbano",
        "suelo habitacional",
        "suelo disponible",
        "terreno urbano",
        "terreno habitacional",
        "predio urbano",
        "inmueble",
        "inmuebles",
        "propiedad",
        "propiedades",
        "venta de terreno",
        "venta terreno",
        "venta de terrenos",
        "adquisicion de terreno",
        "adquisicion terreno",
        "compra de terreno",
        "compra terreno",
        "enajenacion de terreno",
        "enajenacion terreno",
        "licitacion de terreno",
        "licitacion terreno",
        "terreno fiscal",
        "terreno municipal",
        "terreno serviu",
        "terreno para vivienda",
        "terreno para viviendas",
        "terreno proyecto habitacional",
        "terreno vivienda social",
        "suelo para vivienda",
        "suelo para proyecto habitacional",
        "adquisicion de inmueble",
        "venta de inmueble",
        "compra de inmueble",
        "serviu",
        "proyecto habitacional",
        "vivienda social"
      ],
      "keyword_mode": "ANY",
      "extra_filters": {
        "mercado_publico_max_detail_records": 50
      }
    },
    "status": "COMPLETED_WITH_WARNINGS",
    "source_run_status": [
      {
        "source_id": "cmf_uf",
        "source_type": "EnrichmentSource",
        "enabled": 1,
        "configured": 1,
        "attempted": 1,
        "status": "SUCCESS",
        "records_received": 1,
        "records_accepted": 1,
        "records_rejected": 0
      },
      {
        "source_id": "minvu",
        "source_type": "EnrichmentSource",
        "enabled": 1,
        "configured": 1,
        "attempted": 0,
        "status": "SUCCESS_WITH_WARNINGS",
        "records_received": 3,
        "records_accepted": 0,
        "records_rejected": 3
      },
      {
        "source_id": "mercado_publico",
        "source_type": "SearchSource",
        "enabled": 1,
        "configured": 1,
        "attempted": 1,
        "status": "SUCCESS_WITH_WARNINGS",
        "records_received": 29,
        "records_accepted": 3,
        "records_rejected": 26
      },
      {
        "source_id": "mercadolibre_real_estate",
        "source_type": "SearchSource",
        "enabled": 0,
        "configured": 0,
        "attempted": 0,
        "status": "SKIPPED_DISABLED",
        "records_received": 0,
        "records_accepted": 0,
        "records_rejected": 0
      }
    ],
    "found_count": 29,
    "processed_count": 3,
    "discarded_count": 26,
    "source_records_received": 29,
    "source_records_classified": 29,
    "accepted_candidates": 3,
    "normalized_candidates": 3,
    "persisted_properties": 3,
    "possible_candidates": 4,
    "rejected_records": 22,
    "classifier_distribution": {
      "total_analyzed": 29,
      "distribution": {
        "FALSE_POSITIVE": 22,
        "LAND_ACQUISITION": 2,
        "LAND_SALE": 1,
        "POSSIBLE_LAND": 4
      },
      "accepted": 3,
      "possible": 4,
      "rejected": 22,
      "manual_reviewed": 0
    },
    "source_records": {
      "all": {
        "total": 29,
        "sample": [
          {
            "source_record_id": "sr_f2e743e1a308aaa0427de12b",
            "job_id": "ba7111fd-b477-41d8-ba3a-7f5db0d20058",
            "source": "mercado_publico",
            "external_id": "5358-9-LR26",
            "title": "ADQUISICI\u00d3N DE TERRENO PARA PROYECTO EDUCACIONAL U",
            "organization": "UNIVERSIDAD DE TARAPACA",
            "organization_region": "Regi\u00f3n de Tarapac\u00e1  ",
            "organization_commune": "Iquique",
            "organization_address": "Salvador Allende N.\u00ba 3378",
            "property_region": null,
            "property_commune": null,
            "property_address": null,
            "amount_raw": "CLP 5000000000.0",
            "amount": 5000000000,
            "amount_type": "ESTIMATED_AMOUNT",
            "surface_raw": null,
            "surface_m2": null,
            "detail_fetched": 1,
            "detail_attempts": 1,
            "detail_http_status": 200,
            "fields_extracted": [
              "title",
              "description",
              "amount"
            ],
            "fields_missing": [
              "surface",
              "property_region",
              "property_commune",
              "property_address",
              "url"
            ],
            "extraction_reasons": {
              "surface": "No public field/text with compatible unit was found.",
              "property_region": "Buyer region is not treated as property location.",
              "property_commune": "Buyer commune is not treated as property location.",
              "property_address": "Buyer address is not treated as property address.",
              "url": "Public API did not expose a web ficha URL."
            },
            "data_completeness_score": 45,
            "classification": "LAND_ACQUISITION",
            "confidence": 0.96,
            "score": 118,
            "positive_terms": [
              "adquisicion",
              "compra",
              "venta",
              "terreno",
              "terrenos",
              "propiedades",
              "adquisicion de terreno",
              "venta de terrenos",
              "venta de terrenos comerciales o industriales",
              "venta de propiedades o edificios"
            ],
            "negative_terms": [],
            "rules_triggered": [
              "TITLE_LAND_ACQUISITION",
              "REAL_ESTATE_TERMS",
              "PROCUREMENT_REAL_ESTATE_CONTEXT"
            ],
            "manual_classification": "UNREVIEWED",
            "property_id": "9c4f4933-e707-4834-8242-60dea8d1aea5",
            "source_url": "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json?codigo=5358-9-LR26"
          },
          {
            "source_record_id": "sr_0a4328d395136ce025b7e520",
            "job_id": "ba7111fd-b477-41d8-ba3a-7f5db0d20058",
            "source": "mercado_publico",
            "external_id": "4328-31-B226",
            "title": "ADQUISICI\u00d3N DE TERRENO SAN GREGORIO \u00d1IQU\u00c9N",
            "organization": "Ilustre Municipalidad de \u00d1iquen",
            "organization_region": "Regi\u00f3n del \u00d1uble",
            "organization_commune": "\u00d1iqu\u00e9n",
            "organization_address": "Estado 188",
            "property_region": null,
            "property_commune": null,
            "property_address": null,
            "amount_raw": null,
            "amount": null,
            "amount_type": "UNKNOWN",
            "surface_raw": null,
            "surface_m2": null,
            "detail_fetched": 1,
            "detail_attempts": 1,
            "detail_http_status": 200,
            "fields_extracted": [
              "title",
              "description"
            ],
            "fields_missing": [
              "amount",
              "surface",
              "property_region",
              "property_commune",
              "property_address",
              "url"
            ],
            "extraction_reasons": {
              "surface": "No public field/text with compatible unit was found.",
              "property_region": "Buyer region is not treated as property location.",
              "property_commune": "Buyer commune is not treated as property location.",
              "property_address": "Buyer address is not treated as property address.",
              "url": "Public API did not expose a web ficha URL."
            },
            "data_completeness_score": 30,
            "classification": "LAND_ACQUISITION",
            "confidence": 0.82,
            "score": 90,
            "positive_terms": [
              "adquisicion",
              "adquirir",
              "terreno",
              "terrenos",
              "suelo",
              "adquisicion de terreno"
            ],
            "negative_terms": [
              "tasacion"
            ],
            "rules_triggered": [
              "TITLE_LAND_ACQUISITION",
              "REAL_ESTATE_TERMS",
              "NEGATIVE_SERVICE_CONTEXT"
            ],
            "manual_classification": "UNREVIEWED",
            "property_id": "c7033171-fc4e-49a5-a6f4-f252cef0e178",
            "source_url": "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json?codigo=4328-31-B226"
          },
          {
            "source_record_id": "sr_3c733a4cb9eb9acb0f73bb87",
            "job_id": "ba7111fd-b477-41d8-ba3a-7f5db0d20058",
            "source": "mercado_publico",
            "external_id": "4295-54-LR26",
            "title": "VENTA DE TERRENOS DE PROPIEDAD MUNICIPAL LA SERENA",
            "organization": "ILUSTRE MUNICIPALIDAD DE LA SERENA",
            "organization_region": "Regi\u00f3n de Coquimbo ",
            "organization_commune": "La Serena",
            "organization_address": "LOS CARRERA 301 - 2\u00ba PISO",
            "property_region": null,
            "property_commune": null,
            "property_address": null,
            "amount_raw": null,
            "amount": null,
            "amount_type": "UNKNOWN",
            "surface_raw": null,
            "surface_m2": null,
            "detail_fetched": 1,
            "detail_attempts": 1,
            "detail_http_status": 200,
            "fields_extracted": [
              "title",
              "description"
            ],
            "fields_missing": [
              "amount",
              "surface",
              "property_region",
              "property_commune",
              "property_address",
              "url"
            ],
            "extraction_reasons": {
              "surface": "No public field/text with compatible unit was found.",
              "property_region": "Buyer region is not treated as property location.",
              "property_commune": "Buyer commune is not treated as property location.",
              "property_address": "Buyer address is not treated as property address.",
              "url": "Public API did not expose a web ficha URL."
            },
            "data_completeness_score": 30,
            "classification": "LAND_SALE",
            "confidence": 0.96,
            "score": 118,
            "positive_terms": [
              "adquirir",
              "venta",
              "terreno",
              "terrenos",
              "lote",
              "inmuebles",
              "propiedad",
              "propiedades",
              "venta terreno",
              "venta de terrenos",
              "venta de terrenos comerciales o industriales",
              "venta de propiedades o edificios",
              "contrato de compraventa"
            ],
            "negative_terms": [],
            "rules_triggered": [
              "TITLE_LAND_SALE",
              "REAL_ESTATE_TERMS",
              "PROCUREMENT_REAL_ESTATE_CONTEXT"
            ],
            "manual_classification": "UNREVIEWED",
            "property_id": "7e9f5626-7f50-4923-bc4a-b4e08234eed2",
            "source_url": "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json?codigo=4295-54-LR26"
          },
          {
            "source_record_id": "sr_9905202b894f03f6a72aa0a9",
            "job_id": "ba7111fd-b477-41d8-ba3a-7f5db0d20058",
            "source": "mercado_publico",
            "external_id": "867990-62-LE26",
            "title": "CDP 91352 - CC 102 \u2014 TASACI\u00d3N DE BIENES INMUEBLES",
            "organization": null,
            "organization_region": null,
            "organization_commune": null,
            "organization_address": null,
            "property_region": null,
            "property_commune": null,
            "property_address": null,
            "amount_raw": null,
            "amount": null,
            "amount_type": "UNKNOWN",
            "surface_raw": null,
            "surface_m2": null,
            "detail_fetched": 0,
            "detail_attempts": 0,
            "detail_http_status": null,
            "fields_extracted": [
              "title"
            ],
            "fields_missing": [
              "description",
              "amount",
              "surface",
              "property_region",
              "property_commune",
              "property_address",
              "url"
            ],
            "extraction_reasons": {
              "surface": "No public field/text with compatible unit was found.",
              "property_region": "Buyer region is not treated as property location.",
              "property_commune": "Buyer commune is not treated as property location.",
              "property_address": "Buyer address is not treated as property address.",
              "url": "Public API did not expose a web ficha URL."
            },
            "data_completeness_score": 15,
            "classification": "FALSE_POSITIVE",
            "confidence": 0.62,
            "score": -50,
            "positive_terms": [
              "inmuebles"
            ],
            "negative_terms": [
              "tasacion",
              "tasacion de bienes inmuebles"
            ],
            "rules_triggered": [
              "REAL_ESTATE_TERMS",
              "NEGATIVE_SERVICE_CONTEXT"
            ],
            "manual_classification": "UNREVIEWED",
            "property_id": null,
            "source_url": "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json?codigo=867990-62-LE26"
          },
          {
            "source_record_id": "sr_688df65956bfed140fd4acd9",
            "job_id": "ba7111fd-b477-41d8-ba3a-7f5db0d20058",
            "source": "mercado_publico",
            "external_id": "867990-59-L126",
            "title": "cc 102 - sol 91975 servicio de mantenimiento del sistema de calefacci\u00f3n central con visita a terreno",
            "organization": null,
            "organization_region": null,
            "organization_commune": null,
            "organization_address": null,
            "property_region": null,
            "property_commune": null,
            "property_address": null,
            "amount_raw": null,
            "amount": null,
            "amount_type": "UNKNOWN",
            "surface_raw": null,
            "surface_m2": null,
            "detail_fetched": 0,
            "detail_attempts": 0,
            "detail_http_status": null,
            "fields_extracted": [
              "title"
            ],
            "fields_missing": [
              "description",
              "amount",
              "surface",
              "property_region",
              "property_commune",
              "property_address",
              "url"
            ],
            "extraction_reasons": {
              "surface": "No public field/text with compatible unit was found.",
              "property_region": "Buyer region is not treated as property location.",
              "property_commune": "Buyer commune is not treated as property location.",
              "property_address": "Buyer address is not treated as property address.",
              "url": "Public API did not expose a web ficha URL."
            },
            "data_completeness_score": 15,
            "classification": "FALSE_POSITIVE",
            "confidence": 0.62,
            "score": -50,
            "positive_terms": [
              "terreno"
            ],
            "negative_terms": [
              "mantenimiento",
              "visita a terreno",
              "servicio de mantenimiento"
            ],
            "rules_triggered": [
              "REAL_ESTATE_TERMS",
              "NEGATIVE_SERVICE_CONTEXT"
            ],
            "manual_classification": "UNREVIEWED",
            "property_id": null,
            "source_url": "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json?codigo=867990-59-L126"
          },
          {
            "source_record_id": "sr_119ffa7bc7ff1ccf9490df5b",
            "job_id": "ba7111fd-b477-41d8-ba3a-7f5db0d20058",
            "source": "mercado_publico",
            "external_id": "858-64-LE26",
            "title": "Mantenci\u00f3n sitio web oficial IND por 24 meses",
            "organization": null,
            "organization_region": null,
            "organization_commune": null,
            "organization_address": null,
            "property_region": null,
            "property_commune": null,
            "property_address": null,
            "amount_raw": null,
            "amount": null,
            "amount_type": "UNKNOWN",
            "surface_raw": null,
            "surface_m2": null,
            "detail_fetched": 0,
            "detail_attempts": 0,
            "detail_http_status": null,
            "fields_extracted": [
              "title"
            ],
            "fields_missing": [
              "description",
              "amount",
              "surface",
              "property_region",
              "property_commune",
              "property_address",
              "url"
            ],
            "extraction_reasons": {
              "surface": "No public field/text with compatible unit was found.",
              "property_region": "Buyer region is not treated as property location.",
              "property_commune": "Buyer commune is not treated as property location.",
              "property_address": "Buyer address is not treated as property address.",
              "url": "Public API did not expose a web ficha URL."
            },
            "data_completeness_score": 15,
            "classification": "FALSE_POSITIVE",
            "confidence": 0.62,
            "score": -50,
            "positive_terms": [
              "sitio"
            ],
            "negative_terms": [
              "sitio web",
              "mantencion"
            ],
            "rules_triggered": [
              "REAL_ESTATE_TERMS",
              "NEGATIVE_SERVICE_CONTEXT"
            ],
            "manual_classification": "UNREVIEWED",
            "property_id": null,
            "source_url": "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json?codigo=858-64-LE26"
          },
          {
            "source_record_id": "sr_beafd17d784aca5ace36f804",
            "job_id": "ba7111fd-b477-41d8-ba3a-7f5db0d20058",
            "source": "mercado_publico",
            "external_id": "653-15-O126",
            "title": "Habilitaci\u00f3n de Terrenos Etapa V Lote D y E, Las Americas, Talca",
            "organization": null,
            "organization_region": null,
            "organization_commune": null,
            "organization_address": null,
            "property_region": null,
            "property_commune": null,
            "property_address": null,
            "amount_raw": null,
            "amount": null,
            "amount_type": "UNKNOWN",
            "surface_raw": null,
            "surface_m2": null,
            "detail_fetched": 0,
            "detail_attempts": 0,
            "detail_http_status": null,
            "fields_extracted": [
              "title"
            ],
            "fields_missing": [
              "description",
              "amount",
              "surface",
              "property_region",
              "property_commune",
              "property_address",
              "url"
            ],
            "extraction_reasons": {
              "surface": "No public field/text with compatible unit was found.",
              "property_region": "Buyer region is not treated as property location.",
              "property_commune": "Buyer commune is not treated as property location.",
              "property_address": "Buyer address is not treated as property address.",
              "url": "Public API did not expose a web ficha URL."
            },
            "data_completeness_score": 15,
            "classification": "FALSE_POSITIVE",
            "confidence": 0.62,
            "score": -50,
            "positive_terms": [
              "terrenos",
              "lote"
            ],
            "negative_terms": [
              "habilitacion",
              "habilitacion de terrenos"
            ],
            "rules_triggered": [
              "REAL_ESTATE_TERMS",
              "NEGATIVE_SERVICE_CONTEXT"
            ],
            "manual_classification": "UNREVIEWED",
            "property_id": null,
            "source_url": "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json?codigo=653-15-O126"
          },
          {
            "source_record_id": "sr_6b2ddc9099641b8a00020412",
            "job_id": "ba7111fd-b477-41d8-ba3a-7f5db0d20058",
            "source": "mercado_publico",
            "external_id": "638-19-LE26",
            "title": "CONSULTORIA SERVICIOS EXTERNOS FISCALIZACI\u00d3N T\u00c9CNICA DE OBRAS PROYECTOS PROGRAMA FSEV REGULADO POR DS49 DE 2011 Y SUS MODIFICACIONES EN SERVIU REGI\u00d3N DE MAGALLANES Y DE LA ANT\u00c1RTICA CHILENA",
            "organization": null,
            "organization_region": null,
            "organization_commune": null,
            "organization_address": null,
            "property_region": null,
            "property_commune": null,
            "property_address": null,
            "amount_raw": null,
            "amount": null,
            "amount_type": "UNKNOWN",
            "surface_raw": null,
            "surface_m2": null,
            "detail_fetched": 0,
            "detail_attempts": 0,
            "detail_http_status": null,
            "fields_extracted": [
              "title"
            ],
            "fields_missing": [
              "description",
              "amount",
              "surface",
              "property_region",
              "property_commune",
              "property_address",
              "url"
            ],
            "extraction_reasons": {
              "surface": "No public field/text with compatible unit was found.",
              "property_region": "Buyer region is not treated as property location.",
              "property_commune": "Buyer commune is not treated as property location.",
              "property_address": "Buyer address is not treated as property address.",
              "url": "Public API did not expose a web ficha URL."
            },
            "data_completeness_score": 15,
            "classification": "FALSE_POSITIVE",
            "confidence": 0.62,
            "score": -60,
            "positive_terms": [
              "serviu"
            ],
            "negative_terms": [
              "consultoria"
            ],
            "rules_triggered": [
              "PUBLIC_HOUSING_ORGANIZATION",
              "NEGATIVE_SERVICE_CONTEXT"
            ],
            "manual_classification": "UNREVIEWED",
            "property_id": null,
            "source_url": "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json?codigo=638-19-LE26"
          },
          {
            "source_record_id": "sr_45f7730eb626ceae3298d1c5",
            "job_id": "ba7111fd-b477-41d8-ba3a-7f5db0d20058",
            "source": "mercado_publico",
            "external_id": "548874-71-B226",
            "title": "SEGURO DE INCENDIO DE BIENES MUEBLES E INMUEBLES",
            "organization": null,
            "organization_region": null,
            "organization_commune": null,
            "organization_address": null,
            "property_region": null,
            "property_commune": null,
            "property_address": null,
            "amount_raw": null,
            "amount": null,
            "amount_type": "UNKNOWN",
            "surface_raw": null,
            "surface_m2": null,
            "detail_fetched": 0,
            "detail_attempts": 0,
            "detail_http_status": null,
            "fields_extracted": [
              "title"
            ],
            "fields_missing": [
              "description",
              "amount",
              "surface",
              "property_region",
              "property_commune",
              "property_address",
              "url"
            ],
            "extraction_reasons": {
              "surface": "No public field/text with compatible unit was found.",
              "property_region": "Buyer region is not treated as property location.",
              "property_commune": "Buyer commune is not treated as property location.",
              "property_address": "Buyer address is not treated as property address.",
              "url": "Public API did not expose a web ficha URL."
            },
            "data_completeness_score": 15,
            "classification": "FALSE_POSITIVE",
            "confidence": 0.62,
            "score": -50,
            "positive_terms": [
              "inmuebles"
            ],
            "negative_terms": [
              "seguro de incendio"
            ],
            "rules_triggered": [
              "REAL_ESTATE_TERMS",
              "NEGATIVE_SERVICE_CONTEXT"
            ],
            "manual_classification": "UNREVIEWED",
            "property_id": null,
            "source_url": "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json?codigo=548874-71-B226"
          },
          {
            "source_record_id": "sr_8c6e589bd937bb82d756d6d0",
            "job_id": "ba7111fd-b477-41d8-ba3a-7f5db0d20058",
            "source": "mercado_publico",
            "external_id": "548874-70-LR26",
            "title": "SERV MULTIBAM SUCURSALES Y GOBIERNOS EN TERRENO",
            "organization": null,
            "organization_region": null,
            "organization_commune": null,
            "organization_address": null,
            "property_region": null,
            "property_commune": null,
            "property_address": null,
            "amount_raw": null,
            "amount": null,
            "amount_type": "UNKNOWN",
            "surface_raw": null,
            "surface_m2": null,
            "detail_fetched": 0,
            "detail_attempts": 0,
            "detail_http_status": null,
            "fields_extracted": [
              "title"
            ],
            "fields_missing": [
              "description",
              "amount",
              "surface",
              "property_region",
              "property_commune",
              "property_address",
              "url"
            ],
            "extraction_reasons": {
              "surface": "No public field/text with compatible unit was found.",
              "property_region": "Buyer region is not treated as property location.",
              "property_commune": "Buyer commune is not treated as property location.",
              "property_address": "Buyer address is not treated as property address.",
              "url": "Public API did not expose a web ficha URL."
            },
            "data_completeness_score": 15,
            "classification": "FALSE_POSITIVE",
            "confidence": 0.62,
            "score": -50,
            "positive_terms": [
              "terreno"
            ],
            "negative_terms": [
              "en terreno"
            ],
            "rules_triggered": [
              "REAL_ESTATE_TERMS",
              "NEGATIVE_SERVICE_CONTEXT"
            ],
            "manual_classification": "UNREVIEWED",
            "property_id": null,
            "source_url": "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json?codigo=548874-70-LR26"
          }
        ]
      },
      "accepted": {
        "total": 3,
        "sample": [
          {
            "source_record_id": "sr_f2e743e1a308aaa0427de12b",
            "job_id": "ba7111fd-b477-41d8-ba3a-7f5db0d20058",
            "source": "mercado_publico",
            "external_id": "5358-9-LR26",
            "title": "ADQUISICI\u00d3N DE TERRENO PARA PROYECTO EDUCACIONAL U",
            "organization": "UNIVERSIDAD DE TARAPACA",
            "organization_region": "Regi\u00f3n de Tarapac\u00e1  ",
            "organization_commune": "Iquique",
            "organization_address": "Salvador Allende N.\u00ba 3378",
            "property_region": null,
            "property_commune": null,
            "property_address": null,
            "amount_raw": "CLP 5000000000.0",
            "amount": 5000000000,
            "amount_type": "ESTIMATED_AMOUNT",
            "surface_raw": null,
            "surface_m2": null,
            "detail_fetched": 1,
            "detail_attempts": 1,
            "detail_http_status": 200,
            "fields_extracted": [
              "title",
              "description",
              "amount"
            ],
            "fields_missing": [
              "surface",
              "property_region",
              "property_commune",
              "property_address",
              "url"
            ],
            "extraction_reasons": {
              "surface": "No public field/text with compatible unit was found.",
              "property_region": "Buyer region is not treated as property location.",
              "property_commune": "Buyer commune is not treated as property location.",
              "property_address": "Buyer address is not treated as property address.",
              "url": "Public API did not expose a web ficha URL."
            },
            "data_completeness_score": 45,
            "classification": "LAND_ACQUISITION",
            "confidence": 0.96,
            "score": 118,
            "positive_terms": [
              "adquisicion",
              "compra",
              "venta",
              "terreno",
              "terrenos",
              "propiedades",
              "adquisicion de terreno",
              "venta de terrenos",
              "venta de terrenos comerciales o industriales",
              "venta de propiedades o edificios"
            ],
            "negative_terms": [],
            "rules_triggered": [
              "TITLE_LAND_ACQUISITION",
              "REAL_ESTATE_TERMS",
              "PROCUREMENT_REAL_ESTATE_CONTEXT"
            ],
            "manual_classification": "UNREVIEWED",
            "property_id": "9c4f4933-e707-4834-8242-60dea8d1aea5",
            "source_url": "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json?codigo=5358-9-LR26"
          },
          {
            "source_record_id": "sr_0a4328d395136ce025b7e520",
            "job_id": "ba7111fd-b477-41d8-ba3a-7f5db0d20058",
            "source": "mercado_publico",
            "external_id": "4328-31-B226",
            "title": "ADQUISICI\u00d3N DE TERRENO SAN GREGORIO \u00d1IQU\u00c9N",
            "organization": "Ilustre Municipalidad de \u00d1iquen",
            "organization_region": "Regi\u00f3n del \u00d1uble",
            "organization_commune": "\u00d1iqu\u00e9n",
            "organization_address": "Estado 188",
            "property_region": null,
            "property_commune": null,
            "property_address": null,
            "amount_raw": null,
            "amount": null,
            "amount_type": "UNKNOWN",
            "surface_raw": null,
            "surface_m2": null,
            "detail_fetched": 1,
            "detail_attempts": 1,
            "detail_http_status": 200,
            "fields_extracted": [
              "title",
              "description"
            ],
            "fields_missing": [
              "amount",
              "surface",
              "property_region",
              "property_commune",
              "property_address",
              "url"
            ],
            "extraction_reasons": {
              "surface": "No public field/text with compatible unit was found.",
              "property_region": "Buyer region is not treated as property location.",
              "property_commune": "Buyer commune is not treated as property location.",
              "property_address": "Buyer address is not treated as property address.",
              "url": "Public API did not expose a web ficha URL."
            },
            "data_completeness_score": 30,
            "classification": "LAND_ACQUISITION",
            "confidence": 0.82,
            "score": 90,
            "positive_terms": [
              "adquisicion",
              "adquirir",
              "terreno",
              "terrenos",
              "suelo",
              "adquisicion de terreno"
            ],
            "negative_terms": [
              "tasacion"
            ],
            "rules_triggered": [
              "TITLE_LAND_ACQUISITION",
              "REAL_ESTATE_TERMS",
              "NEGATIVE_SERVICE_CONTEXT"
            ],
            "manual_classification": "UNREVIEWED",
            "property_id": "c7033171-fc4e-49a5-a6f4-f252cef0e178",
            "source_url": "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json?codigo=4328-31-B226"
          },
          {
            "source_record_id": "sr_3c733a4cb9eb9acb0f73bb87",
            "job_id": "ba7111fd-b477-41d8-ba3a-7f5db0d20058",
            "source": "mercado_publico",
            "external_id": "4295-54-LR26",
            "title": "VENTA DE TERRENOS DE PROPIEDAD MUNICIPAL LA SERENA",
            "organization": "ILUSTRE MUNICIPALIDAD DE LA SERENA",
            "organization_region": "Regi\u00f3n de Coquimbo ",
            "organization_commune": "La Serena",
            "organization_address": "LOS CARRERA 301 - 2\u00ba PISO",
            "property_region": null,
            "property_commune": null,
            "property_address": null,
            "amount_raw": null,
            "amount": null,
            "amount_type": "UNKNOWN",
            "surface_raw": null,
            "surface_m2": null,
            "detail_fetched": 1,
            "detail_attempts": 1,
            "detail_http_status": 200,
            "fields_extracted": [
              "title",
              "description"
            ],
            "fields_missing": [
              "amount",
              "surface",
              "property_region",
              "property_commune",
              "property_address",
              "url"
            ],
            "extraction_reasons": {
              "surface": "No public field/text with compatible unit was found.",
              "property_region": "Buyer region is not treated as property location.",
              "property_commune": "Buyer commune is not treated as property location.",
              "property_address": "Buyer address is not treated as property address.",
              "url": "Public API did not expose a web ficha URL."
            },
            "data_completeness_score": 30,
            "classification": "LAND_SALE",
            "confidence": 0.96,
            "score": 118,
            "positive_terms": [
              "adquirir",
              "venta",
              "terreno",
              "terrenos",
              "lote",
              "inmuebles",
              "propiedad",
              "propiedades",
              "venta terreno",
              "venta de terrenos",
              "venta de terrenos comerciales o industriales",
              "venta de propiedades o edificios",
              "contrato de compraventa"
            ],
            "negative_terms": [],
            "rules_triggered": [
              "TITLE_LAND_SALE",
              "REAL_ESTATE_TERMS",
              "PROCUREMENT_REAL_ESTATE_CONTEXT"
            ],
            "manual_classification": "UNREVIEWED",
            "property_id": "7e9f5626-7f50-4923-bc4a-b4e08234eed2",
            "source_url": "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json?codigo=4295-54-LR26"
          }
        ]
      },
      "possible": {
        "total": 4,
        "sample": [
          {
            "source_record_id": "sr_5ec1e39a75fe0c0106199af0",
            "job_id": "ba7111fd-b477-41d8-ba3a-7f5db0d20058",
            "source": "mercado_publico",
            "external_id": "539119-80-LP26",
            "title": "CONTRATACI\u00d3N DE SERVICIOS DE EMERGENCIAS SANITARIAS REPARACI\u00d3N YO REPOSICI\u00d3N DE REDES DE ALCANTARILLADO AGUA POTABLE Y REDES DE GAS EN INMUEBLES UBICADOS EN LA REGI\u00d3N METROPOLITANA DEPENDIENTE DE LA DIRECCI\u00d3N DE BIENESTAR DE CARABINEROS",
            "organization": null,
            "organization_region": null,
            "organization_commune": null,
            "organization_address": null,
            "property_region": null,
            "property_commune": null,
            "property_address": null,
            "amount_raw": null,
            "amount": null,
            "amount_type": "UNKNOWN",
            "surface_raw": null,
            "surface_m2": null,
            "detail_fetched": 0,
            "detail_attempts": 0,
            "detail_http_status": null,
            "fields_extracted": [
              "title"
            ],
            "fields_missing": [
              "description",
              "amount",
              "surface",
              "property_region",
              "property_commune",
              "property_address",
              "url"
            ],
            "extraction_reasons": {
              "surface": "No public field/text with compatible unit was found.",
              "property_region": "Buyer region is not treated as property location.",
              "property_commune": "Buyer commune is not treated as property location.",
              "property_address": "Buyer address is not treated as property address.",
              "url": "Public API did not expose a web ficha URL."
            },
            "data_completeness_score": 15,
            "classification": "POSSIBLE_LAND",
            "confidence": 0.49,
            "score": 20,
            "positive_terms": [
              "inmuebles"
            ],
            "negative_terms": [],
            "rules_triggered": [
              "REAL_ESTATE_TERMS"
            ],
            "manual_classification": "UNREVIEWED",
            "property_id": null,
            "source_url": "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json?codigo=539119-80-LP26"
          },
          {
            "source_record_id": "sr_93768587eb06340d825675e0",
            "job_id": "ba7111fd-b477-41d8-ba3a-7f5db0d20058",
            "source": "mercado_publico",
            "external_id": "4887-25-LE26",
            "title": "Implementaci\u00f3n y Recuperaci\u00f3n de sitios de Memoria",
            "organization": null,
            "organization_region": null,
            "organization_commune": null,
            "organization_address": null,
            "property_region": null,
            "property_commune": null,
            "property_address": null,
            "amount_raw": null,
            "amount": null,
            "amount_type": "UNKNOWN",
            "surface_raw": null,
            "surface_m2": null,
            "detail_fetched": 0,
            "detail_attempts": 0,
            "detail_http_status": null,
            "fields_extracted": [
              "title"
            ],
            "fields_missing": [
              "description",
              "amount",
              "surface",
              "property_region",
              "property_commune",
              "property_address",
              "url"
            ],
            "extraction_reasons": {
              "surface": "No public field/text with compatible unit was found.",
              "property_region": "Buyer region is not treated as property location.",
              "property_commune": "Buyer commune is not treated as property location.",
              "property_address": "Buyer address is not treated as property address.",
              "url": "Public API did not expose a web ficha URL."
            },
            "data_completeness_score": 15,
            "classification": "POSSIBLE_LAND",
            "confidence": 0.49,
            "score": 20,
            "positive_terms": [
              "sitios"
            ],
            "negative_terms": [],
            "rules_triggered": [
              "REAL_ESTATE_TERMS"
            ],
            "manual_classification": "UNREVIEWED",
            "property_id": null,
            "source_url": "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json?codigo=4887-25-LE26"
          },
          {
            "source_record_id": "sr_9fa93735fce4bb4ebd647243",
            "job_id": "ba7111fd-b477-41d8-ba3a-7f5db0d20058",
            "source": "mercado_publico",
            "external_id": "3489-30-LR26",
            "title": "CONST. VIVIENDA NUEVA EN SITIO PROPIO D.S10",
            "organization": null,
            "organization_region": null,
            "organization_commune": null,
            "organization_address": null,
            "property_region": null,
            "property_commune": null,
            "property_address": null,
            "amount_raw": null,
            "amount": null,
            "amount_type": "UNKNOWN",
            "surface_raw": null,
            "surface_m2": null,
            "detail_fetched": 0,
            "detail_attempts": 0,
            "detail_http_status": null,
            "fields_extracted": [
              "title"
            ],
            "fields_missing": [
              "description",
              "amount",
              "surface",
              "property_region",
              "property_commune",
              "property_address",
              "url"
            ],
            "extraction_reasons": {
              "surface": "No public field/text with compatible unit was found.",
              "property_region": "Buyer region is not treated as property location.",
              "property_commune": "Buyer commune is not treated as property location.",
              "property_address": "Buyer address is not treated as property address.",
              "url": "Public API did not expose a web ficha URL."
            },
            "data_completeness_score": 15,
            "classification": "POSSIBLE_LAND",
            "confidence": 0.49,
            "score": 20,
            "positive_terms": [
              "sitio"
            ],
            "negative_terms": [],
            "rules_triggered": [
              "REAL_ESTATE_TERMS"
            ],
            "manual_classification": "UNREVIEWED",
            "property_id": null,
            "source_url": "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json?codigo=3489-30-LR26"
          },
          {
            "source_record_id": "sr_f85f8a678cb8da33cc0b1ff4",
            "job_id": "ba7111fd-b477-41d8-ba3a-7f5db0d20058",
            "source": "mercado_publico",
            "external_id": "2359-13-LP26",
            "title": "ARRIENDO DE INMUEBLES 2026-2028",
            "organization": null,
            "organization_region": null,
            "organization_commune": null,
            "organization_address": null,
            "property_region": null,
            "property_commune": null,
            "property_address": null,
            "amount_raw": null,
            "amount": null,
            "amount_type": "UNKNOWN",
            "surface_raw": null,
            "surface_m2": null,
            "detail_fetched": 0,
            "detail_attempts": 0,
            "detail_http_status": null,
            "fields_extracted": [
              "title"
            ],
            "fields_missing": [
              "description",
              "amount",
              "surface",
              "property_region",
              "property_commune",
              "property_address",
              "url"
            ],
            "extraction_reasons": {
              "surface": "No public field/text with compatible unit was found.",
              "property_region": "Buyer region is not treated as property location.",
              "property_commune": "Buyer commune is not treated as property location.",
              "property_address": "Buyer address is not treated as property address.",
              "url": "Public API did not expose a web ficha URL."
            },
            "data_completeness_score": 15,
            "classification": "POSSIBLE_LAND",
            "confidence": 0.49,
            "score": 20,
            "positive_terms": [
              "inmuebles"
            ],
            "negative_terms": [],
            "rules_triggered": [
              "REAL_ESTATE_TERMS"
            ],
            "manual_classification": "UNREVIEWED",
            "property_id": null,
            "source_url": "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json?codigo=2359-13-LP26"
          }
        ]
      },
      "rejected": {
        "total": 22,
        "sample": [
          {
            "source_record_id": "sr_9905202b894f03f6a72aa0a9",
            "job_id": "ba7111fd-b477-41d8-ba3a-7f5db0d20058",
            "source": "mercado_publico",
            "external_id": "867990-62-LE26",
            "title": "CDP 91352 - CC 102 \u2014 TASACI\u00d3N DE BIENES INMUEBLES",
            "organization": null,
            "organization_region": null,
            "organization_commune": null,
            "organization_address": null,
            "property_region": null,
            "property_commune": null,
            "property_address": null,
            "amount_raw": null,
            "amount": null,
            "amount_type": "UNKNOWN",
            "surface_raw": null,
            "surface_m2": null,
            "detail_fetched": 0,
            "detail_attempts": 0,
            "detail_http_status": null,
            "fields_extracted": [
              "title"
            ],
            "fields_missing": [
              "description",
              "amount",
              "surface",
              "property_region",
              "property_commune",
              "property_address",
              "url"
            ],
            "extraction_reasons": {
              "surface": "No public field/text with compatible unit was found.",
              "property_region": "Buyer region is not treated as property location.",
              "property_commune": "Buyer commune is not treated as property location.",
              "property_address": "Buyer address is not treated as property address.",
              "url": "Public API did not expose a web ficha URL."
            },
            "data_completeness_score": 15,
            "classification": "FALSE_POSITIVE",
            "confidence": 0.62,
            "score": -50,
            "positive_terms": [
              "inmuebles"
            ],
            "negative_terms": [
              "tasacion",
              "tasacion de bienes inmuebles"
            ],
            "rules_triggered": [
              "REAL_ESTATE_TERMS",
              "NEGATIVE_SERVICE_CONTEXT"
            ],
            "manual_classification": "UNREVIEWED",
            "property_id": null,
            "source_url": "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json?codigo=867990-62-LE26"
          },
          {
            "source_record_id": "sr_688df65956bfed140fd4acd9",
            "job_id": "ba7111fd-b477-41d8-ba3a-7f5db0d20058",
            "source": "mercado_publico",
            "external_id": "867990-59-L126",
            "title": "cc 102 - sol 91975 servicio de mantenimiento del sistema de calefacci\u00f3n central con visita a terreno",
            "organization": null,
            "organization_region": null,
            "organization_commune": null,
            "organization_address": null,
            "property_region": null,
            "property_commune": null,
            "property_address": null,
            "amount_raw": null,
            "amount": null,
            "amount_type": "UNKNOWN",
            "surface_raw": null,
            "surface_m2": null,
            "detail_fetched": 0,
            "detail_attempts": 0,
            "detail_http_status": null,
            "fields_extracted": [
              "title"
            ],
            "fields_missing": [
              "description",
              "amount",
              "surface",
              "property_region",
              "property_commune",
              "property_address",
              "url"
            ],
            "extraction_reasons": {
              "surface": "No public field/text with compatible unit was found.",
              "property_region": "Buyer region is not treated as property location.",
              "property_commune": "Buyer commune is not treated as property location.",
              "property_address": "Buyer address is not treated as property address.",
              "url": "Public API did not expose a web ficha URL."
            },
            "data_completeness_score": 15,
            "classification": "FALSE_POSITIVE",
            "confidence": 0.62,
            "score": -50,
            "positive_terms": [
              "terreno"
            ],
            "negative_terms": [
              "mantenimiento",
              "visita a terreno",
              "servicio de mantenimiento"
            ],
            "rules_triggered": [
              "REAL_ESTATE_TERMS",
              "NEGATIVE_SERVICE_CONTEXT"
            ],
            "manual_classification": "UNREVIEWED",
            "property_id": null,
            "source_url": "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json?codigo=867990-59-L126"
          },
          {
            "source_record_id": "sr_119ffa7bc7ff1ccf9490df5b",
            "job_id": "ba7111fd-b477-41d8-ba3a-7f5db0d20058",
            "source": "mercado_publico",
            "external_id": "858-64-LE26",
            "title": "Mantenci\u00f3n sitio web oficial IND por 24 meses",
            "organization": null,
            "organization_region": null,
            "organization_commune": null,
            "organization_address": null,
            "property_region": null,
            "property_commune": null,
            "property_address": null,
            "amount_raw": null,
            "amount": null,
            "amount_type": "UNKNOWN",
            "surface_raw": null,
            "surface_m2": null,
            "detail_fetched": 0,
            "detail_attempts": 0,
            "detail_http_status": null,
            "fields_extracted": [
              "title"
            ],
            "fields_missing": [
              "description",
              "amount",
              "surface",
              "property_region",
              "property_commune",
              "property_address",
              "url"
            ],
            "extraction_reasons": {
              "surface": "No public field/text with compatible unit was found.",
              "property_region": "Buyer region is not treated as property location.",
              "property_commune": "Buyer commune is not treated as property location.",
              "property_address": "Buyer address is not treated as property address.",
              "url": "Public API did not expose a web ficha URL."
            },
            "data_completeness_score": 15,
            "classification": "FALSE_POSITIVE",
            "confidence": 0.62,
            "score": -50,
            "positive_terms": [
              "sitio"
            ],
            "negative_terms": [
              "sitio web",
              "mantencion"
            ],
            "rules_triggered": [
              "REAL_ESTATE_TERMS",
              "NEGATIVE_SERVICE_CONTEXT"
            ],
            "manual_classification": "UNREVIEWED",
            "property_id": null,
            "source_url": "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json?codigo=858-64-LE26"
          },
          {
            "source_record_id": "sr_beafd17d784aca5ace36f804",
            "job_id": "ba7111fd-b477-41d8-ba3a-7f5db0d20058",
            "source": "mercado_publico",
            "external_id": "653-15-O126",
            "title": "Habilitaci\u00f3n de Terrenos Etapa V Lote D y E, Las Americas, Talca",
            "organization": null,
            "organization_region": null,
            "organization_commune": null,
            "organization_address": null,
            "property_region": null,
            "property_commune": null,
            "property_address": null,
            "amount_raw": null,
            "amount": null,
            "amount_type": "UNKNOWN",
            "surface_raw": null,
            "surface_m2": null,
            "detail_fetched": 0,
            "detail_attempts": 0,
            "detail_http_status": null,
            "fields_extracted": [
              "title"
            ],
            "fields_missing": [
              "description",
              "amount",
              "surface",
              "property_region",
              "property_commune",
              "property_address",
              "url"
            ],
            "extraction_reasons": {
              "surface": "No public field/text with compatible unit was found.",
              "property_region": "Buyer region is not treated as property location.",
              "property_commune": "Buyer commune is not treated as property location.",
              "property_address": "Buyer address is not treated as property address.",
              "url": "Public API did not expose a web ficha URL."
            },
            "data_completeness_score": 15,
            "classification": "FALSE_POSITIVE",
            "confidence": 0.62,
            "score": -50,
            "positive_terms": [
              "terrenos",
              "lote"
            ],
            "negative_terms": [
              "habilitacion",
              "habilitacion de terrenos"
            ],
            "rules_triggered": [
              "REAL_ESTATE_TERMS",
              "NEGATIVE_SERVICE_CONTEXT"
            ],
            "manual_classification": "UNREVIEWED",
            "property_id": null,
            "source_url": "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json?codigo=653-15-O126"
          },
          {
            "source_record_id": "sr_6b2ddc9099641b8a00020412",
            "job_id": "ba7111fd-b477-41d8-ba3a-7f5db0d20058",
            "source": "mercado_publico",
            "external_id": "638-19-LE26",
            "title": "CONSULTORIA SERVICIOS EXTERNOS FISCALIZACI\u00d3N T\u00c9CNICA DE OBRAS PROYECTOS PROGRAMA FSEV REGULADO POR DS49 DE 2011 Y SUS MODIFICACIONES EN SERVIU REGI\u00d3N DE MAGALLANES Y DE LA ANT\u00c1RTICA CHILENA",
            "organization": null,
            "organization_region": null,
            "organization_commune": null,
            "organization_address": null,
            "property_region": null,
            "property_commune": null,
            "property_address": null,
            "amount_raw": null,
            "amount": null,
            "amount_type": "UNKNOWN",
            "surface_raw": null,
            "surface_m2": null,
            "detail_fetched": 0,
            "detail_attempts": 0,
            "detail_http_status": null,
            "fields_extracted": [
              "title"
            ],
            "fields_missing": [
              "description",
              "amount",
              "surface",
              "property_region",
              "property_commune",
              "property_address",
              "url"
            ],
            "extraction_reasons": {
              "surface": "No public field/text with compatible unit was found.",
              "property_region": "Buyer region is not treated as property location.",
              "property_commune": "Buyer commune is not treated as property location.",
              "property_address": "Buyer address is not treated as property address.",
              "url": "Public API did not expose a web ficha URL."
            },
            "data_completeness_score": 15,
            "classification": "FALSE_POSITIVE",
            "confidence": 0.62,
            "score": -60,
            "positive_terms": [
              "serviu"
            ],
            "negative_terms": [
              "consultoria"
            ],
            "rules_triggered": [
              "PUBLIC_HOUSING_ORGANIZATION",
              "NEGATIVE_SERVICE_CONTEXT"
            ],
            "manual_classification": "UNREVIEWED",
            "property_id": null,
            "source_url": "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json?codigo=638-19-LE26"
          },
          {
            "source_record_id": "sr_45f7730eb626ceae3298d1c5",
            "job_id": "ba7111fd-b477-41d8-ba3a-7f5db0d20058",
            "source": "mercado_publico",
            "external_id": "548874-71-B226",
            "title": "SEGURO DE INCENDIO DE BIENES MUEBLES E INMUEBLES",
            "organization": null,
            "organization_region": null,
            "organization_commune": null,
            "organization_address": null,
            "property_region": null,
            "property_commune": null,
            "property_address": null,
            "amount_raw": null,
            "amount": null,
            "amount_type": "UNKNOWN",
            "surface_raw": null,
            "surface_m2": null,
            "detail_fetched": 0,
            "detail_attempts": 0,
            "detail_http_status": null,
            "fields_extracted": [
              "title"
            ],
            "fields_missing": [
              "description",
              "amount",
              "surface",
              "property_region",
              "property_commune",
              "property_address",
              "url"
            ],
            "extraction_reasons": {
              "surface": "No public field/text with compatible unit was found.",
              "property_region": "Buyer region is not treated as property location.",
              "property_commune": "Buyer commune is not treated as property location.",
              "property_address": "Buyer address is not treated as property address.",
              "url": "Public API did not expose a web ficha URL."
            },
            "data_completeness_score": 15,
            "classification": "FALSE_POSITIVE",
            "confidence": 0.62,
            "score": -50,
            "positive_terms": [
              "inmuebles"
            ],
            "negative_terms": [
              "seguro de incendio"
            ],
            "rules_triggered": [
              "REAL_ESTATE_TERMS",
              "NEGATIVE_SERVICE_CONTEXT"
            ],
            "manual_classification": "UNREVIEWED",
            "property_id": null,
            "source_url": "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json?codigo=548874-71-B226"
          },
          {
            "source_record_id": "sr_8c6e589bd937bb82d756d6d0",
            "job_id": "ba7111fd-b477-41d8-ba3a-7f5db0d20058",
            "source": "mercado_publico",
            "external_id": "548874-70-LR26",
            "title": "SERV MULTIBAM SUCURSALES Y GOBIERNOS EN TERRENO",
            "organization": null,
            "organization_region": null,
            "organization_commune": null,
            "organization_address": null,
            "property_region": null,
            "property_commune": null,
            "property_address": null,
            "amount_raw": null,
            "amount": null,
            "amount_type": "UNKNOWN",
            "surface_raw": null,
            "surface_m2": null,
            "detail_fetched": 0,
            "detail_attempts": 0,
            "detail_http_status": null,
            "fields_extracted": [
              "title"
            ],
            "fields_missing": [
              "description",
              "amount",
              "surface",
              "property_region",
              "property_commune",
              "property_address",
              "url"
            ],
            "extraction_reasons": {
              "surface": "No public field/text with compatible unit was found.",
              "property_region": "Buyer region is not treated as property location.",
              "property_commune": "Buyer commune is not treated as property location.",
              "property_address": "Buyer address is not treated as property address.",
              "url": "Public API did not expose a web ficha URL."
            },
            "data_completeness_score": 15,
            "classification": "FALSE_POSITIVE",
            "confidence": 0.62,
            "score": -50,
            "positive_terms": [
              "terreno"
            ],
            "negative_terms": [
              "en terreno"
            ],
            "rules_triggered": [
              "REAL_ESTATE_TERMS",
              "NEGATIVE_SERVICE_CONTEXT"
            ],
            "manual_classification": "UNREVIEWED",
            "property_id": null,
            "source_url": "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json?codigo=548874-70-LR26"
          },
          {
            "source_record_id": "sr_8446e2ce5d723ac5a39e764e",
            "job_id": "ba7111fd-b477-41d8-ba3a-7f5db0d20058",
            "source": "mercado_publico",
            "external_id": "4179-45-LP26",
            "title": "\u201cCONTRATACI\u00d3N DE COBERTURA DE SEGUROS GENERALES BIENES INMUEBLES Y CONTENIDO DE LA MUNICIPALIDAD DE LAUTARO\u201d.",
            "organization": null,
            "organization_region": null,
            "organization_commune": null,
            "organization_address": null,
            "property_region": null,
            "property_commune": null,
            "property_address": null,
            "amount_raw": null,
            "amount": null,
            "amount_type": "UNKNOWN",
            "surface_raw": null,
            "surface_m2": null,
            "detail_fetched": 0,
            "detail_attempts": 0,
            "detail_http_status": null,
            "fields_extracted": [
              "title"
            ],
            "fields_missing": [
              "description",
              "amount",
              "surface",
              "property_region",
              "property_commune",
              "property_address",
              "url"
            ],
            "extraction_reasons": {
              "surface": "No public field/text with compatible unit was found.",
              "property_region": "Buyer region is not treated as property location.",
              "property_commune": "Buyer commune is not treated as property location.",
              "property_address": "Buyer address is not treated as property address.",
              "url": "Public API did not expose a web ficha URL."
            },
            "data_completeness_score": 15,
            "classification": "FALSE_POSITIVE",
            "confidence": 0.62,
            "score": -50,
            "positive_terms": [
              "inmuebles"
            ],
            "negative_terms": [
              "seguros",
              "cobertura de seguros"
            ],
            "rules_triggered": [
              "REAL_ESTATE_TERMS",
              "NEGATIVE_SERVICE_CONTEXT"
            ],
            "manual_classification": "UNREVIEWED",
            "property_id": null,
            "source_url": "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json?codigo=4179-45-LP26"
          },
          {
            "source_record_id": "sr_6865e4d75ac58202476c41b3",
            "job_id": "ba7111fd-b477-41d8-ba3a-7f5db0d20058",
            "source": "mercado_publico",
            "external_id": "4123-6-LE26",
            "title": "SEGUROS BIENES MUEBLES INMUEBLE VEH\u00cdCULOS DEPTO",
            "organization": null,
            "organization_region": null,
            "organization_commune": null,
            "organization_address": null,
            "property_region": null,
            "property_commune": null,
            "property_address": null,
            "amount_raw": null,
            "amount": null,
            "amount_type": "UNKNOWN",
            "surface_raw": null,
            "surface_m2": null,
            "detail_fetched": 0,
            "detail_attempts": 0,
            "detail_http_status": null,
            "fields_extracted": [
              "title"
            ],
            "fields_missing": [
              "description",
              "amount",
              "surface",
              "property_region",
              "property_commune",
              "property_address",
              "url"
            ],
            "extraction_reasons": {
              "surface": "No public field/text with compatible unit was found.",
              "property_region": "Buyer region is not treated as property location.",
              "property_commune": "Buyer commune is not treated as property location.",
              "property_address": "Buyer address is not treated as property address.",
              "url": "Public API did not expose a web ficha URL."
            },
            "data_completeness_score": 15,
            "classification": "FALSE_POSITIVE",
            "confidence": 0.62,
            "score": -50,
            "positive_terms": [
              "inmueble"
            ],
            "negative_terms": [
              "seguros"
            ],
            "rules_triggered": [
              "REAL_ESTATE_TERMS",
              "NEGATIVE_SERVICE_CONTEXT"
            ],
            "manual_classification": "UNREVIEWED",
            "property_id": null,
            "source_url": "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json?codigo=4123-6-LE26"
          },
          {
            "source_record_id": "sr_a503ecc9c484b3e5b5e7594e",
            "job_id": "ba7111fd-b477-41d8-ba3a-7f5db0d20058",
            "source": "mercado_publico",
            "external_id": "3950-40-LE26",
            "title": "MEJORAMIENTO INTERNO EXTERNO Y LIMPIEZA DE TERRENO EN POSTA DE SALUD RURAL EN LOCALIDAD DE PUERTO AGUIRRE",
            "organization": null,
            "organization_region": null,
            "organization_commune": null,
            "organization_address": null,
            "property_region": null,
            "property_commune": null,
            "property_address": null,
            "amount_raw": null,
            "amount": null,
            "amount_type": "UNKNOWN",
            "surface_raw": null,
            "surface_m2": null,
            "detail_fetched": 0,
            "detail_attempts": 0,
            "detail_http_status": null,
            "fields_extracted": [
              "title"
            ],
            "fields_missing": [
              "description",
              "amount",
              "surface",
              "property_region",
              "property_commune",
              "property_address",
              "url"
            ],
            "extraction_reasons": {
              "surface": "No public field/text with compatible unit was found.",
              "property_region": "Buyer region is not treated as property location.",
              "property_commune": "Buyer commune is not treated as property location.",
              "property_address": "Buyer address is not treated as property address.",
              "url": "Public API did not expose a web ficha URL."
            },
            "data_completeness_score": 15,
            "classification": "FALSE_POSITIVE",
            "confidence": 0.62,
            "score": -50,
            "positive_terms": [
              "terreno"
            ],
            "negative_terms": [
              "limpieza",
              "limpieza de terreno",
              "limpieza de terreno"
            ],
            "rules_triggered": [
              "REAL_ESTATE_TERMS",
              "NEGATIVE_SERVICE_CONTEXT"
            ],
            "manual_classification": "UNREVIEWED",
            "property_id": null,
            "source_url": "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json?codigo=3950-40-LE26"
          }
        ]
      }
    },
    "events": [
      {
        "type": "started",
        "stage": "DISCOVERY",
        "source": null,
        "property_id": null,
        "message": "Starting discovery"
      },
      {
        "type": "progress",
        "stage": "DISCOVERY",
        "source": "mercado_publico",
        "property_id": null,
        "message": "mercado_publico: 3 candidate(s) from 29 source record(s)"
      },
      {
        "type": "completed",
        "stage": "DISCOVERY",
        "source": null,
        "property_id": null,
        "message": "Discovery completed"
      },
      {
        "type": "started",
        "stage": "DETAIL_EXTRACTION",
        "source": null,
        "property_id": null,
        "message": "Detail extraction"
      },
      {
        "type": "completed",
        "stage": "DETAIL_EXTRACTION",
        "source": null,
        "property_id": null,
        "message": "No detail endpoint required for MVP raw records"
      },
      {
        "type": "started",
        "stage": "NORMALIZATION",
        "source": null,
        "property_id": null,
        "message": "Normalizing records"
      },
      {
        "type": "progress",
        "stage": "NORMALIZATION",
        "source": null,
        "property_id": null,
        "message": "Normalized"
      },
      {
        "type": "progress",
        "stage": "NORMALIZATION",
        "source": null,
        "property_id": null,
        "message": "Normalized"
      },
      {
        "type": "progress",
        "stage": "NORMALIZATION",
        "source": null,
        "property_id": null,
        "message": "Normalized"
      },
      {
        "type": "completed",
        "stage": "NORMALIZATION",
        "source": null,
        "property_id": null,
        "message": "Normalization completed"
      },
      {
        "type": "started",
        "stage": "UF_ENRICHMENT",
        "source": null,
        "property_id": null,
        "message": "Enriching UF values"
      },
      {
        "type": "progress",
        "stage": "UF_ENRICHMENT",
        "source": null,
        "property_id": null,
        "message": "UF enrichment"
      },
      {
        "type": "progress",
        "stage": "UF_ENRICHMENT",
        "source": null,
        "property_id": null,
        "message": "UF enrichment"
      },
      {
        "type": "progress",
        "stage": "UF_ENRICHMENT",
        "source": null,
        "property_id": null,
        "message": "UF enrichment"
      },
      {
        "type": "completed",
        "stage": "UF_ENRICHMENT",
        "source": null,
        "property_id": null,
        "message": "UF enrichment completed"
      },
      {
        "type": "started",
        "stage": "IMAGE_PROCESSING",
        "source": null,
        "property_id": null,
        "message": "Processing images"
      },
      {
        "type": "progress",
        "stage": "IMAGE_PROCESSING",
        "source": null,
        "property_id": null,
        "message": "Image processing"
      },
      {
        "type": "progress",
        "stage": "IMAGE_PROCESSING",
        "source": null,
        "property_id": null,
        "message": "Image processing"
      },
      {
        "type": "progress",
        "stage": "IMAGE_PROCESSING",
        "source": null,
        "property_id": null,
        "message": "Image processing"
      },
      {
        "type": "completed",
        "stage": "IMAGE_PROCESSING",
        "source": null,
        "property_id": null,
        "message": "Image processing completed"
      },
      {
        "type": "started",
        "stage": "DEDUPLICATION",
        "source": null,
        "property_id": null,
        "message": "Deduplicating"
      },
      {
        "type": "completed",
        "stage": "DEDUPLICATION",
        "source": null,
        "property_id": null,
        "message": "Deduplication completed"
      },
      {
        "type": "started",
        "stage": "PERSISTENCE",
        "source": null,
        "property_id": null,
        "message": "Persisting records"
      },
      {
        "type": "completed",
        "stage": "PERSISTENCE",
        "source": null,
        "property_id": null,
        "message": "Persistence completed"
      },
      {
        "type": "started",
        "stage": "GIS_ENRICHMENT",
        "source": null,
        "property_id": null,
        "message": "MINVU enrichment"
      },
      {
        "type": "progress",
        "stage": "GIS_ENRICHMENT",
        "source": null,
        "property_id": "7e9f5626-7f50-4923-bc4a-b4e08234eed2",
        "message": "MINVU skipped property without coordinates"
      },
      {
        "type": "progress",
        "stage": "GIS_ENRICHMENT",
        "source": null,
        "property_id": "9c4f4933-e707-4834-8242-60dea8d1aea5",
        "message": "MINVU skipped property without coordinates"
      },
      {
        "type": "progress",
        "stage": "GIS_ENRICHMENT",
        "source": null,
        "property_id": "c7033171-fc4e-49a5-a6f4-f252cef0e178",
        "message": "MINVU skipped property without coordinates"
      },
      {
        "type": "completed",
        "stage": "GIS_ENRICHMENT",
        "source": null,
        "property_id": null,
        "message": "MINVU enrichment completed"
      },
      {
        "type": "completed",
        "stage": "EXPORT_READY",
        "source": null,
        "property_id": null,
        "message": "Search job completed"
      }
    ]
  }
]
```

## Registro Seleccionado

```json
{
  "source_record_id": "sr_f2e743e1a308aaa0427de12b",
  "job_id": "ba7111fd-b477-41d8-ba3a-7f5db0d20058",
  "source": "mercado_publico",
  "external_id": "5358-9-LR26",
  "title": "ADQUISICI\u00d3N DE TERRENO PARA PROYECTO EDUCACIONAL U",
  "organization": "UNIVERSIDAD DE TARAPACA",
  "organization_region": "Regi\u00f3n de Tarapac\u00e1  ",
  "organization_commune": "Iquique",
  "organization_address": "Salvador Allende N.\u00ba 3378",
  "property_region": null,
  "property_commune": null,
  "property_address": null,
  "amount_raw": "CLP 5000000000.0",
  "amount": 5000000000,
  "amount_type": "ESTIMATED_AMOUNT",
  "surface_raw": null,
  "surface_m2": null,
  "detail_fetched": 1,
  "detail_attempts": 1,
  "detail_http_status": 200,
  "fields_extracted": [
    "title",
    "description",
    "amount"
  ],
  "fields_missing": [
    "surface",
    "property_region",
    "property_commune",
    "property_address",
    "url"
  ],
  "extraction_reasons": {
    "surface": "No public field/text with compatible unit was found.",
    "property_region": "Buyer region is not treated as property location.",
    "property_commune": "Buyer commune is not treated as property location.",
    "property_address": "Buyer address is not treated as property address.",
    "url": "Public API did not expose a web ficha URL."
  },
  "data_completeness_score": 45,
  "classification": "LAND_ACQUISITION",
  "confidence": 0.96,
  "score": 118,
  "positive_terms": [
    "adquisicion",
    "compra",
    "venta",
    "terreno",
    "terrenos",
    "propiedades",
    "adquisicion de terreno",
    "venta de terrenos",
    "venta de terrenos comerciales o industriales",
    "venta de propiedades o edificios"
  ],
  "negative_terms": [],
  "rules_triggered": [
    "TITLE_LAND_ACQUISITION",
    "REAL_ESTATE_TERMS",
    "PROCUREMENT_REAL_ESTATE_CONTEXT"
  ],
  "manual_classification": "UNREVIEWED",
  "property_id": "9c4f4933-e707-4834-8242-60dea8d1aea5",
  "source_url": "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json?codigo=5358-9-LR26"
}
```

## Propiedad Persistida

```json
{
  "internal_id": "9c4f4933-e707-4834-8242-60dea8d1aea5",
  "source": "mercado_publico",
  "external_id": "5358-9-LR26",
  "url": null,
  "title": "ADQUISICI\u00d3N DE TERRENO PARA PROYECTO EDUCACIONAL U",
  "price_clp": 5000000000,
  "price_uf": 122966.5,
  "uf_rate": 40661.48,
  "uf_rate_date": "2026-06-03",
  "uf_source": "CMF",
  "uf_retrieved_at": "2026-09-01T04:34:47.297415+00:00",
  "uf_cache_hit": 1,
  "area_m2": null,
  "uf_m2": null,
  "region": null,
  "commune": null,
  "address": null,
  "latitude": null,
  "longitude": null,
  "location_precision": "UNKNOWN",
  "geometry_status": "UNKNOWN",
  "geometry_type": "UNKNOWN"
}
```

## Territorio / MINVU

```json
{
  "urban_limit": null,
  "risk_intersection": null,
  "prc": null,
  "geometry_metrics": null,
  "evidence_count": 1
}
```

Nota: cualquier evidencia `UNKNOWN` de geometria es trazabilidad de ausencia de dato, no una consulta efectiva a capas MINVU.

## Excel

```json
{
  "path": "C:\\Users\\sebas\\OneDrive\\Desktop\\Scraper-Busqueda-de-terrenos-chile\\data\\exports\\landfinder_export.xlsx",
  "status": "created",
  "openpyxl_valid": true,
  "sheets": [
    "Resumen",
    "Terrenos",
    "Fuentes_Utilizadas",
    "Fuentes",
    "Historial_Precios",
    "Metricas_GIS",
    "Fuentes_Evidencia",
    "Classifier_Audit",
    "SourceRecords",
    "Errores"
  ]
}
```

## Criterio De Termino

```json
{
  "has_real_external_record": true,
  "has_persisted_property": true,
  "has_price": true,
  "has_area": false,
  "has_coordinates": false,
  "has_minvu": false,
  "has_evidence": false,
  "has_excel": true
}
```
