from landfinder.classification.preliminary import (
    CriterionResult,
    PreliminaryLandStatus,
    evaluate_preliminary_territorial_status,
)


def test_no_intersection_does_not_become_compliance_without_coverage_evidence() -> None:
    assessment = evaluate_preliminary_territorial_status(
        property_record={
            "internal_id": "p1",
            "latitude": -33.4,
            "longitude": -70.6,
            "location_precision": "PARCEL_POLYGON",
            "geocoding_confidence": 0.9,
            "gross_area_m2": 7100,
        },
        urban_limit={"status": "NO", "confidence": 0.7},
        risk={"status": "NO_INTERSECTION_DETECTED", "confidence": 0.75, "risk_types": []},
        prc={"status": "UNKNOWN"},
    )

    by_key = {criterion["criterion_key"]: criterion for criterion in assessment.criteria}
    assert by_key["urban_limit"]["result"] == CriterionResult.NOT_VERIFIED
    assert by_key["risk"]["result"] == CriterionResult.NOT_VERIFIED
    assert assessment.status == PreliminaryLandStatus.NEEDS_REVIEW
