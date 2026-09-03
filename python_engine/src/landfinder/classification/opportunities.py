from __future__ import annotations

import re
import unicodedata
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from landfinder.models.enums import LandClassification


class ClassificationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    classification: LandClassification
    confidence: float = Field(ge=0, le=1)
    score: int
    positive_terms: list[str] = Field(default_factory=list)
    negative_terms: list[str] = Field(default_factory=list)
    rules_triggered: list[str] = Field(default_factory=list)
    explanation: str
    requires_manual_review: bool


class LandOpportunityClassifier:
    """Deterministic classifier for public land opportunity triage."""

    action_terms = [
        "adquisicion",
        "adquisici",
        "adquirir",
        "compra",
        "comprar",
        "enajenacion",
        "venta",
        "vender",
        "remate",
        "subasta",
        "expropiacion",
        "expropiar",
    ]
    acquisition_terms = [
        "adquisicion",
        "adquisici",
        "adquirir",
        "compra",
        "comprar",
        "expropiacion",
        "expropiar",
    ]
    sale_terms = ["enajenacion", "venta", "vender", "remate", "subasta"]
    real_estate_terms = [
        "terreno",
        "terrenos",
        "predio",
        "predios",
        "sitio",
        "sitios",
        "eriazo",
        "eriazos",
        "peladero",
        "peladeros",
        "pano",
        "panos",
        "lote",
        "lotes",
        "macrolote",
        "macrolotes",
        "suelo",
        "suelos",
        "inmueble",
        "inmuebles",
        "propiedad",
        "propiedades",
        "bien raiz",
        "bienes raices",
    ]
    action_real_estate_terms = [
        "terreno",
        "terrenos",
        "predio",
        "predios",
        "inmueble",
        "inmuebles",
        "propiedad",
        "propiedades",
        "bien raiz",
        "bienes raices",
    ]
    strong_acquisition_phrases = [
        "adquisicion de terreno",
        "adquisicion terreno",
        "compra de terreno",
        "compra terreno",
        "adquirir terreno",
        "adquisicion de predio",
        "adquisicion predio",
        "compra de predio",
        "compra predio",
        "adquisicion de inmueble",
        "adquisicion inmueble",
        "compra de inmueble",
        "compra inmueble",
        "terreno para proyecto habitacional",
        "suelo para vivienda",
        "suelo para proyecto habitacional",
    ]
    strong_sale_phrases = [
        "venta de terreno",
        "venta terreno",
        "venta de terrenos",
        "enajenacion de terreno",
        "enajenacion terreno",
        "venta de predio",
        "venta predio",
        "enajenacion de predio",
        "venta de inmueble",
        "venta inmueble",
        "remate de terreno",
        "subasta de terreno",
    ]
    strong_real_estate_phrases = [
        "sitio eriazo",
        "sitios eriazos",
        "sitio vacio",
        "sitio sin construir",
        "terreno eriazo",
        "terreno baldio",
        "terreno urbano",
        "terreno habitacional",
        "predio urbano",
        "lote urbano",
        "macrolote urbano",
        "pano de terreno",
        "gran pano",
        "pano urbano",
        "suelo urbano",
        "suelo habitacional",
        "suelo disponible",
        "proyecto habitacional",
        "vivienda social",
    ]
    housing_terms = [
        "vivienda social",
        "proyecto habitacional",
        "suelo habitacional",
        "suelo urbano",
    ]
    organization_terms = ["serviu"]
    negative_service_terms = [
        "sitio web",
        "sitios web",
        "pagina web",
        "portal web",
        "plataforma web",
        "articulos electricos",
        "articulo electrico",
        "materiales electricos",
        "insumos electricos",
        "mantencion",
        "mantenimiento",
        "limpieza",
        "habilitacion",
        "consultoria",
        "estudio",
        "topografia",
        "levantamiento",
        "nivelacion terreno",
        "preparacion terreno",
        "reparacion terreno",
        "habilitacion de terreno",
        "habilitacion de terrenos",
        "limpieza de terreno",
        "limpieza de terrenos",
        "limpieza de terreno",
        "desmalezado",
        "mantencion de terreno",
        "mantenimiento de terreno",
        "movimiento de tierra",
        "cubre suelo",
        "cubre suelos",
        "piso",
        "pisos",
        "ceramica",
        "ceramicas",
        "materiales",
        "maquinaria",
        "insumos",
        "fertilizantes",
        "tierra vegetal",
        "aridos",
        "canal de riego",
        "sistema de riego",
        "cesped",
        "rehabilitacion de espacio publico",
        "recuperacion de espacio",
        "suelo cemento",
        "estudio de suelo",
        "estudio mecanica de suelo",
        "estudio mecanica de suelos",
        "mecanica de suelo",
        "mecanica de suelos",
        "analisis de suelo",
        "penetrometro",
        "equipo penetrometro",
        "topografia",
        "levantamiento topografico",
        "arriendo maquinaria",
        "lote de materiales",
        "lote de medicamentos",
        "lote de insumos",
        "lote de alimentos",
        "visita a terreno",
        "visita terreno",
        "en terreno",
        "trabajo en terreno",
        "trabajos en terreno",
        "actividades domiciliarias y terreno",
        "todo terreno",
        "todoterreno",
        "construccion de obras civiles",
        "construccion plaza",
        "servicio de mantenimiento",
        "mantencion de inmuebles",
        "servicio de aseo",
        "mejoramiento de infraestructura",
        "polizas de seguros",
        "seguros",
        "cobertura de seguros",
        "seguro de incendio",
        "servicio de guardia",
        "tasacion",
        "tasacion de bienes inmuebles",
        "taludes",
        "restauracion forestal",
        "servicios de asistencia forestal",
        "administracion de cultivos forestales",
    ]
    context_terms = [
        "venta de terrenos comerciales o industriales",
        "venta de propiedades o edificios",
        "contrato de compraventa",
        "bases administrativas",
        "bases tecnicas",
    ]

    def classify(self, item: dict[str, Any]) -> ClassificationDecision:
        title = _normalize_text(
            " ".join(str(item.get(key) or "") for key in ("Nombre", "name", "Titulo", "title"))
        )
        item_text = _normalize_text(_items_text(item))
        description = _normalize_text(
            " ".join(str(item.get(key) or "") for key in ("Descripcion", "description"))
        )
        full_text = " ".join(part for part in (title, description, item_text) if part)
        primary_text = " ".join(part for part in (title, item_text) if part)

        positive_terms = _matched_terms(
            full_text,
            [
                *self.action_terms,
                *self.real_estate_terms,
                *self.strong_acquisition_phrases,
                *self.strong_sale_phrases,
                *self.strong_real_estate_phrases,
                *self.housing_terms,
                *self.organization_terms,
                *self.context_terms,
            ],
        )
        negative_terms = _matched_terms(full_text, self.negative_service_terms)
        rules: list[str] = []
        score = 0

        title_has_acquisition = _contains_any(title, self.acquisition_terms)
        title_has_sale = _contains_any(title, self.sale_terms)
        title_has_action_real_estate = _contains_any(title, self.action_real_estate_terms)
        title_has_strong_acquisition = _contains_any(title, self.strong_acquisition_phrases)
        title_has_strong_sale = _contains_any(title, self.strong_sale_phrases)
        title_has_strong_real_estate = _contains_any(title, self.strong_real_estate_phrases)
        primary_has_acquisition = _contains_any(primary_text, self.acquisition_terms)
        primary_has_sale = _contains_any(primary_text, self.sale_terms)
        primary_has_action_real_estate = _contains_any(primary_text, self.action_real_estate_terms)
        primary_has_strong_acquisition = _contains_any(
            primary_text,
            self.strong_acquisition_phrases,
        )
        primary_has_strong_sale = _contains_any(primary_text, self.strong_sale_phrases)
        primary_has_strong_real_estate = _contains_any(
            primary_text,
            self.strong_real_estate_phrases,
        )
        has_real_estate = _contains_any(full_text, self.real_estate_terms)
        has_strong_real_estate = _contains_any(full_text, self.strong_real_estate_phrases)
        has_housing = _contains_any(full_text, self.housing_terms)
        has_org = _contains_any(full_text, self.organization_terms)
        has_context = _contains_any(full_text, self.context_terms)
        has_negative = bool(negative_terms)
        title_has_negative = _contains_any(title, self.negative_service_terms)
        primary_has_negative = _contains_any(primary_text, self.negative_service_terms)

        strong_classification: LandClassification | None = None
        if (
            (
                title_has_strong_acquisition
                or (title_has_acquisition and title_has_action_real_estate)
            )
            and not title_has_negative
        ):
            score += 90
            rules.append("TITLE_LAND_ACQUISITION")
            strong_classification = LandClassification.LAND_ACQUISITION
        elif (
            (title_has_strong_sale or (title_has_sale and title_has_action_real_estate))
            and not title_has_negative
        ):
            score += 90
            rules.append("TITLE_LAND_SALE")
            strong_classification = LandClassification.LAND_SALE
        elif (
            (
                primary_has_strong_acquisition
                or (primary_has_acquisition and primary_has_action_real_estate)
            )
            and not primary_has_negative
        ):
            score += 75
            rules.append("PRIMARY_LAND_ACQUISITION")
            strong_classification = LandClassification.LAND_ACQUISITION
        elif (
            (primary_has_strong_sale or (primary_has_sale and primary_has_action_real_estate))
            and not primary_has_negative
        ):
            score += 75
            rules.append("PRIMARY_LAND_SALE")
            strong_classification = LandClassification.LAND_SALE

        if has_real_estate:
            score += 20
            rules.append("REAL_ESTATE_TERMS")
        if title_has_strong_real_estate or primary_has_strong_real_estate or has_strong_real_estate:
            score += 25
            rules.append("STRONG_REAL_ESTATE_PHRASE")
        if has_housing:
            score += 15
            rules.append("HOUSING_CONTEXT")
        if has_org:
            score += 10
            rules.append("PUBLIC_HOUSING_ORGANIZATION")
        if has_context:
            score += 8
            rules.append("PROCUREMENT_REAL_ESTATE_CONTEXT")
        if has_negative:
            penalty = 20 if strong_classification else 70
            score -= penalty
            rules.append("NEGATIVE_SERVICE_CONTEXT")

        if strong_classification is not None:
            classification = strong_classification
        elif has_negative and score < 0:
            classification = LandClassification.FALSE_POSITIVE
        elif has_real_estate and (has_housing or has_org or has_context):
            classification = LandClassification.REAL_ESTATE
        elif has_real_estate:
            classification = LandClassification.POSSIBLE_LAND
        else:
            classification = LandClassification.UNKNOWN

        confidence = _confidence(classification, score, positive_terms, negative_terms)
        requires_manual_review = classification in {
            LandClassification.REAL_ESTATE,
            LandClassification.POSSIBLE_LAND,
            LandClassification.UNKNOWN,
        } or confidence < 0.8

        return ClassificationDecision(
            classification=classification,
            confidence=confidence,
            score=score,
            positive_terms=positive_terms,
            negative_terms=negative_terms,
            rules_triggered=rules,
            explanation=_explanation(classification, score, positive_terms, negative_terms, rules),
            requires_manual_review=requires_manual_review,
        )


def _normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.replace("\ufffd", " ").lower())
    without_accents = "".join(
        char for char in decomposed if unicodedata.category(char) != "Mn"
    )
    return " ".join(without_accents.split())


def _items_text(item: dict[str, Any]) -> str:
    items = item.get("Items")
    if not isinstance(items, dict):
        return ""
    listing = items.get("Listado")
    if not isinstance(listing, list):
        return ""
    parts: list[str] = []
    for entry in listing[:20]:
        if not isinstance(entry, dict):
            continue
        for key in ("NombreProducto", "Descripcion", "Producto", "Categoria"):
            value = entry.get(key)
            if value:
                parts.append(str(value))
    return " ".join(parts)


def _matched_terms(text: str, terms: list[str]) -> list[str]:
    return [term for term in terms if _contains_term(text, term)]


def _contains_any(text: str, terms: list[str]) -> bool:
    return any(_contains_term(text, term) for term in terms)


def _contains_term(text: str, term: str) -> bool:
    escaped = re.escape(term).replace(r"\ ", r"\s+")
    return re.search(rf"(?<!\w){escaped}(?!\w)", text) is not None


def _confidence(
    classification: LandClassification,
    score: int,
    positive_terms: list[str],
    negative_terms: list[str],
) -> float:
    if classification in {LandClassification.LAND_ACQUISITION, LandClassification.LAND_SALE}:
        base = 0.72 + min(max(score, 0), 120) / 500
    elif classification == LandClassification.REAL_ESTATE:
        base = 0.58 + min(max(score, 0), 80) / 600
    elif classification == LandClassification.POSSIBLE_LAND:
        base = 0.46 + min(max(score, 0), 60) / 700
    elif classification == LandClassification.FALSE_POSITIVE:
        base = 0.7 if negative_terms and not positive_terms else 0.62
    else:
        base = 0.35
    if negative_terms and classification != LandClassification.FALSE_POSITIVE:
        base -= 0.08
    return round(max(0.05, min(0.98, base)), 2)


def _explanation(
    classification: LandClassification,
    score: int,
    positive_terms: list[str],
    negative_terms: list[str],
    rules: list[str],
) -> str:
    parts = [
        f"classification={classification.value}",
        f"score={score}",
    ]
    if positive_terms:
        parts.append("positive=" + ", ".join(positive_terms))
    if negative_terms:
        parts.append("negative=" + ", ".join(negative_terms))
    if rules:
        parts.append("rules=" + ", ".join(rules))
    return " | ".join(parts)
