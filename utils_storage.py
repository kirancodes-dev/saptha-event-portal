"""
utils_storage.py — Unified storage manager for AWS S3 (or any S3-compatible
service such as Supabase Storage), Google Cloud Storage, and local disk.

- `upload_file`: a public file (e.g. a certificate the verify page links).
- `upload_private` + `signed_url`: a private object handed out through a
  short-lived signed URL (exports with personal data). UPG-17, folded into UPG-21.

Settings: STORAGE_TYPE (s3 | gcs | local), AWS_* or GCS_BUCKET_NAME, and
S3_ENDPOINT_URL for an S3-compatible service. Local disk is for development
only: in production a storage error is raised, never written to the
container's disk (which Cloud Run wipes on restart).
"""
import os
import logging

logger = logging.getLogger(__name__)

SIGNED_URL_SECONDS = 15 * 60


class StorageError(RuntimeError):
    pass


def _production():
    return os.environ.get('FLASK_ENV') == 'production'


def _storage_type():
    storage_type = os.environ.get('STORAGE_TYPE', '').lower()
    if storage_type:
        return storage_type
    if os.environ.get('AWS_STORAGE_BUCKET_NAME'):
        return 's3'
    if os.environ.get('GCS_BUCKET_NAME'):
        return 'gcs'
    return 'local'


def _s3_client():
    import boto3
    kwargs = dict(
        aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
        region_name=os.environ.get('AWS_DEFAULT_REGION', 'eu-north-1'),
    )
    endpoint = os.environ.get('S3_ENDPOINT_URL', '').strip()
    if endpoint:   # Supabase Storage, MinIO, R2, ...
        kwargs['endpoint_url'] = endpoint
    return boto3.client('s3', **kwargs)


def _s3_bucket():
    bucket_name = os.environ.get('AWS_STORAGE_BUCKET_NAME', '')
    if not bucket_name:
        raise ValueError("AWS_STORAGE_BUCKET_NAME not set")
    return bucket_name


def _s3_public_url(bucket_name, key):
    custom_domain = os.environ.get('AWS_S3_CUSTOM_DOMAIN', '')
    if custom_domain:
        return f"https://{custom_domain}/{key}"
    endpoint = os.environ.get('S3_ENDPOINT_URL', '').strip().rstrip('/')
    if endpoint:
        return f"{endpoint}/{bucket_name}/{key}"
    region = os.environ.get('AWS_DEFAULT_REGION', 'eu-north-1')
    return f"https://{bucket_name}.s3.{region}.amazonaws.com/{key}"


def _local_write(data, path):
    if _production():
        raise StorageError("Local file storage is for development only; set STORAGE_TYPE=s3 or gcs.")
    project_root = os.path.dirname(os.path.abspath(__file__))
    upload_dir = os.path.join(project_root, 'static', 'uploads')
    os.makedirs(upload_dir, exist_ok=True)
    # Replace slashes in filename to avoid nested dir creation issues locally
    filename = path.replace('/', '_')
    with open(os.path.join(upload_dir, filename), 'wb') as f:
        f.write(data)
    return filename


def _cloud_failed(provider, exc):
    """In production a cloud error is an error; in development, fall back to disk."""
    if _production():
        raise StorageError(f"{provider} upload failed: {exc}") from exc
    logger.error("%s upload failed: %s. Falling back to local storage (development only)...", provider, exc)


def upload_file(data: bytes, path: str, content_type: str) -> str:
    """
    Upload a public file to the configured storage (S3 / GCS / local in
    development). Returns its public download URL.

    :param data: File contents in bytes.
    :param path: Destination path (e.g. 'certificates/reg_123.pdf').
    :param content_type: MIME type of the file (e.g. 'application/pdf').
    """
    storage_type = _storage_type()

    # ── 1. AWS S3 / S3-compatible ────────────────────────────────────────────
    if storage_type == 's3':
        try:
            bucket_name = _s3_bucket()
            key = path.lstrip('/')   # S3 key is the path without a leading slash
            _s3_client().put_object(Bucket=bucket_name, Key=key, Body=data,
                                    ContentType=content_type, ACL='public-read')
            return _s3_public_url(bucket_name, key)
        except Exception as exc:
            _cloud_failed('AWS S3', exc)

    # ── 2. Google Cloud Storage (GCS) ────────────────────────────────────────
    elif storage_type == 'gcs':
        try:
            from google.cloud import storage
            bucket_name = os.environ.get('GCS_BUCKET_NAME', '')
            if not bucket_name:
                raise ValueError("GCS_BUCKET_NAME not configured")
            blob = storage.Client().bucket(bucket_name).blob(path)
            blob.upload_from_string(data, content_type=content_type)
            blob.make_public()
            return blob.public_url
        except Exception as exc:
            _cloud_failed('Google Cloud Storage', exc)

    # ── 3. Local disk (development only) ─────────────────────────────────────
    try:
        filename = _local_write(data, path)
    except StorageError:
        raise
    except Exception as exc:
        logger.error("Local storage fallback failed: %s", exc)
        return ''
    base_url = os.environ.get('BASE_URL', 'http://127.0.0.1:5000')
    return f"{base_url.rstrip('/')}/static/uploads/{filename}"


def upload_private(data: bytes, path: str, content_type: str) -> str:
    """Upload a private object (no public ACL). Returns its key, for signed_url."""
    key = path.lstrip('/')
    storage_type = _storage_type()
    if storage_type == 's3':
        try:
            _s3_client().put_object(Bucket=_s3_bucket(), Key=key, Body=data, ContentType=content_type)
            return key
        except Exception as exc:
            _cloud_failed('AWS S3', exc)
    elif storage_type == 'gcs':
        try:
            from google.cloud import storage
            storage.Client().bucket(os.environ['GCS_BUCKET_NAME']).blob(key).upload_from_string(
                data, content_type=content_type)
            return key
        except Exception as exc:
            _cloud_failed('Google Cloud Storage', exc)
    _local_write(data, key)
    return key


def signed_url(key: str, expires_in: int = SIGNED_URL_SECONDS) -> str:
    """A download link for a private object that stops working after expires_in seconds."""
    storage_type = _storage_type()
    if storage_type == 's3':
        return _s3_client().generate_presigned_url(
            'get_object', Params={'Bucket': _s3_bucket(), 'Key': key}, ExpiresIn=expires_in)
    if storage_type == 'gcs':
        import datetime
        from google.cloud import storage
        blob = storage.Client().bucket(os.environ['GCS_BUCKET_NAME']).blob(key)
        return blob.generate_signed_url(expiration=datetime.timedelta(seconds=expires_in), version='v4')
    if _production():
        raise StorageError("Local file storage is for development only.")
    base_url = os.environ.get('BASE_URL', 'http://127.0.0.1:5000')
    return f"{base_url.rstrip('/')}/static/uploads/{key.replace('/', '_')}"
