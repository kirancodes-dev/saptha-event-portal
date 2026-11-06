"""
tests/test_signed_urls.py — UPG-99: a private file's signed download link works
with key-less credentials (Cloud Run): it is signed through IAM signBlob with
the service account's email and an access token, while credentials that hold a
private key still sign locally.
"""
import pytest

import utils_storage


class _Blob:
    calls = []

    def generate_signed_url(self, **kwargs):
        _Blob.calls.append(kwargs)
        return 'https://storage.googleapis.com/signed'


class _Client:
    def bucket(self, name):
        assert name == 'test-bucket'
        return type('B', (), {'blob': lambda self, key: _Blob()})()


class _Keyless:          # like google.auth.compute_engine.Credentials: no signer
    service_account_email = 'runtime@project.iam.gserviceaccount.com'
    token = None

    def refresh(self, request):
        self.token = 'ya29.access-token'


class _WithKey:          # like a service-account key file: can sign locally
    signer = object()
    service_account_email = 'key@project.iam.gserviceaccount.com'

    def sign_bytes(self, data):
        return b'sig'


@pytest.fixture
def gcs(monkeypatch):
    import google.auth
    from google.cloud import storage
    monkeypatch.setenv('STORAGE_TYPE', 'gcs')
    monkeypatch.setenv('GCS_BUCKET_NAME', 'test-bucket')
    monkeypatch.setattr(storage, 'Client', _Client)
    _Blob.calls = []
    return lambda creds: monkeypatch.setattr(google.auth, 'default', lambda *a, **k: (creds, 'project'))


def test_keyless_credentials_sign_through_iam(gcs):
    gcs(_Keyless())
    assert utils_storage.signed_url('exports/report.xlsx', 600) == 'https://storage.googleapis.com/signed'
    [kwargs] = _Blob.calls
    assert kwargs['service_account_email'] == 'runtime@project.iam.gserviceaccount.com'
    assert kwargs['access_token'] == 'ya29.access-token' and kwargs['version'] == 'v4'
    assert kwargs['expiration'].total_seconds() == 600


def test_credentials_with_a_key_still_sign_locally(gcs):
    gcs(_WithKey())
    utils_storage.signed_url('exports/report.xlsx')
    [kwargs] = _Blob.calls
    assert 'access_token' not in kwargs and 'service_account_email' not in kwargs
