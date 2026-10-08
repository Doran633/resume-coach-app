"""The formal bold view is a projection, never a second body writer."""
from copy import deepcopy
from dataclasses import replace
import json

import pytest
from docx import Document

from app.services import generation_service as generation
from app.services.canonical_consumer_view_service import build_canonical_consumer_views
from test_v09174_fact_reference_composition import isolated
from test_v09176_delivery_closure import deliver, provider
from test_v09193_evidence_bounded_composition import composition_sample
from test_v09162_model_output_evidence_contract import request


def test_formal_bold_is_the_same_saved_and_exported_expression(monkeypatch, tmp_path, isolated):
    case, _, body = composition_sample(combine=False)
    body['bold_version'] = '另一份独立编写的项目说明'
    gates = []
    original = generation.validate_resume_delivery_quality
    def observe(payload, **kwargs):
        gates.append((payload.bold_version, deepcopy(payload.resume_sections.projects)))
        return original(payload, **kwargs)
    monkeypatch.setattr(generation, 'validate_resume_delivery_quality', observe)
    outcome = deliver(monkeypatch, tmp_path, case, [(json.dumps(body, ensure_ascii=False), 'stop')])
    assert outcome['results'] == 1 and 'docx' in outcome, outcome
    saved = outcome['saved']
    docx_text = '\n'.join(paragraph.text for paragraph in Document(
        next(tmp_path.glob('*.docx'))).paragraphs)
    assert '另一份独立编写' not in saved['bold_version']
    for project in saved['resume_sections']['projects']:
        for text in (project['intro'], project['role'], *project['details']):
            if text:
                assert text in saved['bold_version']
                assert text in docx_text
    for bold, projects in gates:
        assert '另一份独立编写' not in bold
        assert all(text in bold for project in projects for text in (
            project['intro'], project['role'], *project['details']) if text)


@pytest.mark.parametrize('long_mode', [False, True])
def test_actual_writer_task_has_one_formal_expression_target(long_mode, monkeypatch, isolated):
    case, build, body = composition_sample(combine=False)
    before = deepcopy(build)
    sent = provider(monkeypatch, [('not json', 'stop'), (json.dumps(body), 'stop')])
    generation.build_llm_generation(request(case), replace(build.long_input_context,
        long_input_mode=long_mode), consumer_views=build_canonical_consumer_views(build))
    for wire in sent:
        actual = wire['messages'][1]['content']
        assert '正式大胆正文只写在 expression_units' in actual
        assert 'bold_version 不另写一套项目' in actual
        assert '行动、对象与工作意义' in actual
    assert build == before
