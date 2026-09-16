"""Reserved synthetic acceptance; not a historical production request."""
from pathlib import Path

from test_v09181_claim_and_type_evidence import source_assertions
from test_v09174_fact_reference_composition import isolated
from test_v09175_post_processing_evidence import trace_delivery, assert_complete
from app.services.canonical_semantic_state_service import build_canonical_semantic_build


def test_reserved_relations_and_limitation_keep_local_ownership():
    raw = (Path(__file__).parent / "fixtures/v09181_holdout_input.txt").read_text(encoding="utf-8")
    build = build_canonical_semantic_build(raw)
    assert [d.canonical_experience_type for d in build.experience_type_decisions] == ["项目经历", "科研经历"]
    assert len(build.identities) == 2
    plan, = [c for c in build.ledger.withheld_claims if "自动盘点" in c.text]
    assert plan.source_experience_id == "EXP-001"
    assert plan.temporal_status == "planned"
    assert not any("自动盘点" in f.fact_text for f in build.ledger.facts)
    assert any("17条" in f.fact_text and f.experience_id == "EXP-001" for f in build.ledger.facts)
    assert any("12条" in f.fact_text and f.experience_id == "EXP-002" for f in build.ledger.facts)
    assert any("没有负责论文发表" in c.text and c.source_experience_id == "EXP-002" for c in build.ledger.excluded_claims)
    source_assertions(raw, build)


def test_reserved_sample_reaches_saved_revision(monkeypatch, tmp_path, isolated):
    raw = (Path(__file__).parent / "fixtures/v09181_holdout_input.txt").read_text(encoding="utf-8")
    build, captured, snapshots = trace_delivery(raw, "detail", monkeypatch, tmp_path)
    for name, stage, projects in snapshots:
        assert_complete(projects, build)
    assert_complete(captured["saved"]["resume_sections"]["projects"], build)
