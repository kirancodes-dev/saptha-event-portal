"""
tests/test_health.py — Health check endpoint tests
"""

import json
from unittest.mock import patch


def test_health_returns_200(client, mock_db):
    resp = client.get('/health')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data['status'] == 'healthy'
    assert 'timestamp' in data
    assert 'version' in data


def test_ready_returns_200(client, mock_db):
    resp = client.get('/health/ready')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data['ready'] is True


def test_health_503_on_db_failure(client, mock_db):
    with patch.object(mock_db, 'collection', side_effect=Exception('db down')):
        resp = client.get('/health')
        assert resp.status_code == 503
        data = json.loads(resp.data)
        assert data['status'] == 'unhealthy'
