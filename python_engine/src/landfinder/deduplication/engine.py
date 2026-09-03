from __future__ import annotations

from difflib import SequenceMatcher
from math import asin, cos, radians, sin, sqrt
from uuid import uuid4

from landfinder.models.records import CanonicalPropertyMatch, NormalizedPropertyRecord
from landfinder.normalization.parsers import normalize_key


class DeduplicationEngine:
    duplicate_threshold = 0.78
    possible_threshold = 0.58

    def cluster(self, records: list[NormalizedPropertyRecord]) -> list[CanonicalPropertyMatch]:
        matches: list[CanonicalPropertyMatch] = []
        assigned: dict[str, str] = {}

        for index, record in enumerate(records):
            best_score = 0.0
            best_id: str | None = None
            best_reasons: list[str] = []
            for previous in records[:index]:
                score, reasons = self.score(record, previous)
                if score > best_score and previous.internal_id in assigned:
                    best_score = score
                    best_id = assigned[previous.internal_id]
                    best_reasons = reasons

            canonical_id = (
                best_id if best_score >= self.possible_threshold and best_id else str(uuid4())
            )
            assigned[record.internal_id] = canonical_id
            matches.append(
                CanonicalPropertyMatch(
                    canonical_id=canonical_id,
                    internal_id=record.internal_id,
                    match_score=best_score if best_id else 1.0,
                    match_reason=best_reasons if best_id else ["PRIMARY_RECORD"],
                    possible_duplicate=bool(best_id and best_score < self.duplicate_threshold),
                )
            )
        return matches

    def score(
        self,
        left: NormalizedPropertyRecord,
        right: NormalizedPropertyRecord,
    ) -> tuple[float, list[str]]:
        score = 0.0
        reasons: list[str] = []

        if left.canonical_url and right.canonical_url and left.canonical_url == right.canonical_url:
            score += 0.45
            reasons.append("canonical_url")
        if (
            left.source_id == right.source_id
            and left.external_id
            and right.external_id
            and left.external_id == right.external_id
        ):
            score += 0.9
            reasons.append("same_source_external_id")

        if (
            left.commune
            and right.commune
            and normalize_key(left.commune) == normalize_key(right.commune)
        ):
            score += 0.12
            reasons.append("commune")

        if left.latitude and left.longitude and right.latitude and right.longitude:
            distance = _haversine_m(left.latitude, left.longitude, right.latitude, right.longitude)
            if distance <= 80:
                score += 0.22
                reasons.append("coordinates_80m")
            elif distance <= 250:
                score += 0.1
                reasons.append("coordinates_250m")

        if left.gross_area_m2 and right.gross_area_m2:
            larger = max(left.gross_area_m2, right.gross_area_m2)
            smaller = min(left.gross_area_m2, right.gross_area_m2)
            if larger > 0 and float(smaller / larger) >= 0.95:
                score += 0.1
                reasons.append("area_close")

        if left.price_uf and right.price_uf:
            larger = max(left.price_uf, right.price_uf)
            smaller = min(left.price_uf, right.price_uf)
            if larger > 0 and float(smaller / larger) >= 0.95:
                score += 0.08
                reasons.append("price_close")

        title_similarity = _similarity(left.title, right.title)
        if title_similarity >= 0.85:
            score += 0.16
            reasons.append("title_high_similarity")
        elif title_similarity >= 0.65:
            score += 0.08
            reasons.append("title_medium_similarity")

        if left.image_phash and right.image_phash and left.image_phash == right.image_phash:
            score += 0.18
            reasons.append("image_phash")

        return min(score, 1.0), reasons


def _similarity(left: str | None, right: str | None) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, normalize_key(left), normalize_key(right)).ratio()


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * radius * asin(sqrt(a))
