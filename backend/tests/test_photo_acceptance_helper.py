"""Offline checks for diagnostic/acceptance reporting. No internet fixture is accepted as live."""
import importlib.util
from pathlib import Path
import pytest
path=Path(__file__).resolve().parents[1]/'tools'/'photo_acceptance.py'
spec=importlib.util.spec_from_file_location('photo_acceptance',path)
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)


def test_only_real_provider_assets_qualify():
    base={'preview_url':'/generated/images/job/test.jpg','url':'https://commons.wikimedia.org/wiki/File:Photo','attribution':'Photo by creator - CC BY 4.0'}
    rows=[{**base,'source':'Local text card'},{**base,'source':'Fixture'},{**base,'source':'commons'},{**base,'source':'pexels'}]
    assert [a['source'] for a in helper.successful_assets(rows)]==['commons','pexels']
    assert not helper.successful_assets([{'source':'commons'}])


def test_diagnostic_errors_redact_secrets():
    value=helper.safe_error(RuntimeError('request failed fake-sensitive-value'),['fake-sensitive-value'])
    assert 'fake-sensitive-value' not in str(value) and '[REDACTED]' in value['message']


def test_acceptance_paths_cannot_escape_generated():
    with pytest.raises(ValueError):helper.inside_generated(helper.ROOT/'backend'/'.env')
    assert helper.inside_generated(helper.ROOT/'generated'/'photo-network-test'/'x.jpg').name=='x.jpg'


def test_dns_failure_recorded_without_false_success(monkeypatch):
    def fail(*a,**k):raise helper.socket.gaierror(11001,'getaddrinfo failed')
    monkeypatch.setattr(helper.socket,'getaddrinfo',fail)
    result=helper.check_dns('commons.wikimedia.org')
    assert result['ok'] is False and result['errno']==11001
