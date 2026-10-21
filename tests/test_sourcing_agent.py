import json
from pathlib import Path

import pytest

from app.sourcing_agent import ProductAgent, validate_quotes, validate_arguments, render_html
from app.sourcing_pipeline import atomic_json


def test_fabricated_material_quote_cannot_enter_verified_evidence():
    domestic = {'title': '오일 분무기 470ml'}
    overseas = {'title': '470ml glass oil sprayer'}
    with pytest.raises(ValueError, match='exact substring'):
        validate_quotes([{'side': 'domestic', 'quote': '유리'}, {'side': 'overseas', 'quote': 'glass'}], domestic, overseas)
    assert validate_quotes([{'side': 'domestic', 'quote': '470ml'}, {'side': 'overseas', 'quote': 'glass'}], domestic, overseas)


def test_finish_does_not_turn_partial_collection_into_complete(tmp_path):
    agent = ProductAgent({'id': 'oil'}, {}, tmp_path, ['opencli'])
    (agent.out/'pipeline').mkdir()
    atomic_json(agent.out/'pipeline/report.json', {'jobs': [{'site': 'naver', 'search_type': 'keyword', 'state': 'collected', 'products': []}]})
    result = agent.dispatch('finish', {'reason': 'Model claims success'})
    assert result['status'] == 'needs_review'
    assert result['all_search_paths_complete'] is False


def test_pending_tool_replayed_before_another_model_request(tmp_path, monkeypatch):
    agent = ProductAgent({'id': 'oil'}, {}, tmp_path, ['opencli'])
    call = {'id': 'pending-1', 'type': 'function', 'function': {'name': 'finish', 'arguments': '{"reason":"resume"}'}}
    agent.state['messages'].append({'role': 'assistant', 'tool_calls': [call], 'content': None})
    agent.state['pending_calls'] = [call]
    agent.save()
    resumed = ProductAgent({'id': 'oil'}, {}, tmp_path, ['opencli'])
    def finish(name, args):
        assert name == 'finish' and args == {'reason': 'resume'}
        resumed.state['status'] = 'needs_review'
        return {'status': 'needs_review'}
    monkeypatch.setattr(resumed, 'dispatch', finish)
    def unexpected(*args, **kwargs):
        raise AssertionError('Model must not be called before pending tool replay')
    monkeypatch.setattr('httpx.Client.post', unexpected)
    resumed.run({})
    assert resumed.state['pending_calls'] == []
    assert resumed.state['messages'][-1]['role'] == 'tool'


def test_html_escapes_untrusted_product_claims(tmp_path):
    target = tmp_path/'index.html'
    render_html([{'agent_product_id': '<script>bad()</script>', 'jobs': []}], target)
    assert '<script>bad()</script>' not in target.read_text()
    assert '&lt;script&gt;bad()&lt;/script&gt;' in target.read_text()


def test_unexpected_model_arguments_cannot_override_uploaded_images():
    schema = {'type': 'object', 'properties': {'query_ko': {'type': 'string'}}, 'required': ['query_ko']}
    with pytest.raises(ValueError, match='Unexpected'):
        validate_arguments({'query_ko': 'oil', 'images': ['/private/photo.jpg']}, schema)


def test_tool_boolean_does_not_accept_truthy_string():
    with pytest.raises(ValueError, match='boolean'):
        validate_arguments('false', {'type': 'boolean'})
