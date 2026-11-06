"""
tests/test_storage_endpoints.py — UPG-21's storage part (UPG-17 folded in),
boto3 stubbed: an S3-compatible endpoint (Supabase Storage, MinIO) reaches the
client and the public URL; private uploads carry no public ACL and come back
through a signed link; in production an S3 failure raises and nothing is written
under static/uploads/.
"""
import os
import sys
import types

import pytest

import utils_storage

UPLOADS = os.path.join(os.path.dirname(utils_storage.__file__), 'static', 'uploads')


@pytest.fixture
def s3(monkeypatch):
    calls = {'client': [], 'put': [], 'presign': [], 'fail': False}

    class Client:
        def put_object(self, **kwargs):
            if calls['fail']:
                raise RuntimeError('S3 is down')
            calls['put'].append(kwargs)

        def generate_presigned_url(self, op, Params, ExpiresIn):
            calls['presign'].append((op, Params, ExpiresIn))
            return f"https://signed.example/{Params['Key']}?X-Amz-Expires={ExpiresIn}"

    fake = types.SimpleNamespace(client=lambda service, **kw: calls['client'].append((service, kw)) or Client())
    monkeypatch.setitem(sys.modules, 'boto3', fake)
    monkeypatch.setenv('STORAGE_TYPE', 's3')
    monkeypatch.setenv('AWS_STORAGE_BUCKET_NAME', 'event-files')
    monkeypatch.setenv('S3_ENDPOINT_URL', 'https://project.supabase.co/storage/v1/s3')
    monkeypatch.delenv('AWS_S3_CUSTOM_DOMAIN', raising=False)
    return calls


def test_the_s3_endpoint_reaches_the_client_and_the_public_url(s3):
    url = utils_storage.upload_file(b'pdf', 'certificates/a.pdf', 'application/pdf')
    assert s3['client'][0][1]['endpoint_url'] == 'https://project.supabase.co/storage/v1/s3'
    assert url == 'https://project.supabase.co/storage/v1/s3/event-files/certificates/a.pdf'
    assert s3['put'][0]['ACL'] == 'public-read'


def test_private_uploads_have_no_public_acl_and_come_back_signed(s3):
    key = utils_storage.upload_private(b'xlsx', 'exports/report.xlsx', 'application/octet-stream')
    assert key == 'exports/report.xlsx' and 'ACL' not in s3['put'][0]
    link = utils_storage.signed_url(key)
    assert link.startswith('https://signed.example/exports/report.xlsx')
    assert s3['presign'] == [('get_object', {'Bucket': 'event-files', 'Key': key}, utils_storage.SIGNED_URL_SECONDS)]


def test_in_production_an_s3_failure_raises_and_writes_nothing_locally(s3, monkeypatch):
    monkeypatch.setenv('FLASK_ENV', 'production')
    s3['fail'] = True
    before = set(os.listdir(UPLOADS)) if os.path.isdir(UPLOADS) else set()
    with pytest.raises(utils_storage.StorageError):
        utils_storage.upload_file(b'x', 'banners/new.png', 'image/png')
    with pytest.raises(utils_storage.StorageError):
        utils_storage.upload_private(b'x', 'exports/new.xlsx', 'application/octet-stream')
    after = set(os.listdir(UPLOADS)) if os.path.isdir(UPLOADS) else set()
    assert after == before
