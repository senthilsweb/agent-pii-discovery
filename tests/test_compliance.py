"""Compliance matrix lookup: exact mappings, severity, UNKNOWN emptiness."""

from pipeline.compliance import map_compliance_impact


def test_health_record_id_hits_hipaa_not_ccpa():
    impact = map_compliance_impact(["HEALTH_RECORD_ID"])
    assert "HIPAA" in impact.impacted_jurisdictions
    assert "CCPA_CPRA" not in impact.impacted_jurisdictions


def test_ssn_severity_high_everywhere_it_triggers():
    impact = map_compliance_impact(["GOVERNMENT_ID_SSN"])
    assert {"CCPA_CPRA", "PIPEDA", "GDPR"} <= set(impact.impacted_jurisdictions)
    assert all(h.severity == "high" for h in impact.hits)


def test_unknown_maps_to_no_regimes():
    impact = map_compliance_impact(["UNKNOWN"])
    assert impact.impacted_jurisdictions == []
    assert impact.hits == []


def test_moderate_severity_for_non_high_types():
    impact = map_compliance_impact(["EMAIL_ADDRESS"])
    assert impact.hits and all(h.severity == "moderate" for h in impact.hits)


def test_triggered_by_lists_the_types():
    impact = map_compliance_impact(["EMAIL_ADDRESS", "HEALTH_CONDITION"])
    gdpr = next(h for h in impact.hits if h.jurisdiction == "GDPR")
    assert gdpr.triggered_by == ["EMAIL_ADDRESS", "HEALTH_CONDITION"]
    assert gdpr.severity == "high"  # HEALTH_CONDITION escalates


def test_matrix_version_carried():
    assert map_compliance_impact(["EMAIL_ADDRESS"]).regime_matrix_version == "1"
