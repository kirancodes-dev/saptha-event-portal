"""
tests/test_storage.py — Unit tests for the unified cloud and local storage manager
"""
import os
import shutil
import pytest
from unittest.mock import MagicMock, patch

from utils_storage import upload_file


@pytest.fixture(scope="function")
def clean_local_uploads():
    """Ensure local upload folder is cleaned up before and after tests."""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    upload_dir = os.path.join(project_root, 'static', 'uploads')
    
    # Pre-clean
    if os.path.exists(upload_dir):
        shutil.rmtree(upload_dir)
        
    yield upload_dir
    
    # Post-clean
    if os.path.exists(upload_dir):
        shutil.rmtree(upload_dir)


def test_local_storage_fallback(clean_local_uploads, monkeypatch):
    """Test that file is saved locally when STORAGE_TYPE=local."""
    monkeypatch.setenv("STORAGE_TYPE", "local")
    monkeypatch.setenv("BASE_URL", "http://localhost:5001")
    
    test_data = b"Hello Local Storage!"
    test_path = "test_dir/file.txt"
    content_type = "text/plain"
    
    url = upload_file(test_data, test_path, content_type)
    
    # Verify relative URL structure
    assert url == "http://localhost:5001/static/uploads/test_dir_file.txt"
    
    # Verify file is saved in correct path
    expected_filepath = os.path.join(clean_local_uploads, "test_dir_file.txt")
    assert os.path.exists(expected_filepath)
    
    with open(expected_filepath, "rb") as f:
        assert f.read() == test_data


def test_aws_s3_upload(monkeypatch):
    """Test that boto3 S3 client is called correctly when STORAGE_TYPE=s3."""
    monkeypatch.setenv("STORAGE_TYPE", "s3")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "mock_key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "mock_secret")
    monkeypatch.setenv("AWS_STORAGE_BUCKET_NAME", "my-test-s3-bucket")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-north-1")
    
    test_data = b"Hello AWS S3!"
    test_path = "certificates/12345.pdf"
    content_type = "application/pdf"
    
    # Mock boto3 client
    mock_s3_client = MagicMock()
    
    with patch("boto3.client", return_value=mock_s3_client) as mock_boto:
        url = upload_file(test_data, test_path, content_type)
        
        # Verify boto3 client is initialized with correct credentials
        mock_boto.assert_called_once_with(
            's3',
            aws_access_key_id='mock_key',
            aws_secret_access_key='mock_secret',
            region_name='eu-north-1'
        )
        
        # Verify put_object was called with correct parameters
        mock_s3_client.put_object.assert_called_once_with(
            Bucket='my-test-s3-bucket',
            Key='certificates/12345.pdf',
            Body=test_data,
            ContentType=content_type,
            ACL='public-read'
        )
        
        # Verify public URL format
        assert url == "https://my-test-s3-bucket.s3.eu-north-1.amazonaws.com/certificates/12345.pdf"


def test_aws_s3_custom_domain(monkeypatch):
    """Test S3 upload returns custom CDN domain when configured."""
    monkeypatch.setenv("STORAGE_TYPE", "s3")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "mock_key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "mock_secret")
    monkeypatch.setenv("AWS_STORAGE_BUCKET_NAME", "my-test-s3-bucket")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-north-1")
    monkeypatch.setenv("AWS_S3_CUSTOM_DOMAIN", "cdn.sapthaevents.com")
    
    test_data = b"Hello Custom S3 CDN!"
    mock_s3_client = MagicMock()
    
    with patch("boto3.client", return_value=mock_s3_client):
        url = upload_file(test_data, "exports/sheet.xlsx", "application/vnd.ms-excel")
        assert url == "https://cdn.sapthaevents.com/exports/sheet.xlsx"


def test_gcs_upload(monkeypatch):
    """Test GCS uploads are handled correctly when STORAGE_TYPE=gcs."""
    monkeypatch.setenv("STORAGE_TYPE", "gcs")
    monkeypatch.setenv("GCS_BUCKET_NAME", "my-gcs-bucket")
    
    test_data = b"Hello GCS!"
    test_path = "exports/data.csv"
    content_type = "text/csv"
    
    # Mock google storage client and nested attributes
    mock_storage_client = MagicMock()
    mock_bucket = MagicMock()
    mock_blob = MagicMock()
    
    mock_storage_client.bucket.return_value = mock_bucket
    mock_bucket.blob.return_value = mock_blob
    mock_blob.public_url = "https://storage.googleapis.com/my-gcs-bucket/exports/data.csv"
    
    with patch("google.cloud.storage.Client", return_value=mock_storage_client) as mock_gcs:
        url = upload_file(test_data, test_path, content_type)
        
        mock_gcs.assert_called_once()
        mock_storage_client.bucket.assert_called_once_with("my-gcs-bucket")
        mock_bucket.blob.assert_called_once_with(test_path)
        mock_blob.upload_from_string.assert_called_once_with(test_data, content_type=content_type)
        mock_blob.make_public.assert_called_once()
        
        assert url == "https://storage.googleapis.com/my-gcs-bucket/exports/data.csv"
