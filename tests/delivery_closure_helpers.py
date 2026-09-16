"""Observe real rejected delivery; never substitute a Gate decision or payload."""
from unittest.mock import patch
import pytest


def rejected_delivery_payload(service, db, request, *, critical_code=None, **kwargs):
    from app import models
    observed = []
    gate = service.validate_resume_delivery_quality
    def observe(payload, *args, **options):
        result = gate(payload, *args, **options)
        observed.append((payload.model_copy(deep=True), result))
        return result
    with patch.object(service, 'validate_resume_delivery_quality', observe):
        with pytest.raises(service.GenerationServiceError) as caught:
            service.create_generation(db, request, **kwargs)
    assert caught.value.code == 'DELIVERY_QUALITY_FAILED'
    payload, evaluation = observed[-1]
    assert not evaluation.stats.gate_passed
    if critical_code:
        assert any(i.issue_code == critical_code and i.severity == 'critical' for i in evaluation.issues)
    for model in (models.GenerationResult, models.ResumeVersion, models.GeneratedFile):
        assert db.query(model).count() == 0
    assert db.query(models.ExperienceInput).count() == 1
    return payload
