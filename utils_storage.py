"""
utils_storage.py — Unified storage manager for AWS S3, Google Cloud Storage, and Local fallback.
"""
import os
import logging

logger = logging.getLogger(__name__)


def upload_file(data: bytes, path: str, content_type: str) -> str:
    """
    Upload file data to configured cloud storage (S3 / GCS / Local fallback).
    Returns the public download URL of the uploaded file.
    
    :param data: File contents in bytes.
    :param path: Destination path (e.g. 'certificates/reg_123.pdf').
    :param content_type: MIME type of the file (e.g. 'application/pdf').
    """
    storage_type = os.environ.get('STORAGE_TYPE', '').lower()

    # ── 1. AWS S3 Storage ────────────────────────────────────────────────────
    if storage_type == 's3' or (not storage_type and os.environ.get('AWS_STORAGE_BUCKET_NAME')):
        try:
            import boto3
            bucket_name = os.environ.get('AWS_STORAGE_BUCKET_NAME', '')
            if not bucket_name:
                raise ValueError("AWS_STORAGE_BUCKET_NAME not set")

            s3 = boto3.client(
                's3',
                aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
                region_name=os.environ.get('AWS_DEFAULT_REGION', 'eu-north-1')
            )

            # S3 key is the path without a leading slash
            key = path.lstrip('/')

            s3.put_object(
                Bucket=bucket_name,
                Key=key,
                Body=data,
                ContentType=content_type,
                ACL='public-read'
            )

            region = os.environ.get('AWS_DEFAULT_REGION', 'eu-north-1')
            custom_domain = os.environ.get('AWS_S3_CUSTOM_DOMAIN', '')

            if custom_domain:
                return f"https://{custom_domain}/{key}"
            return f"https://{bucket_name}.s3.{region}.amazonaws.com/{key}"

        except Exception as exc:
            logger.error("AWS S3 upload failed: %s. Falling back to local storage...", exc)

    # ── 2. Google Cloud Storage (GCS) ────────────────────────────────────────
    elif storage_type == 'gcs' or (not storage_type and os.environ.get('GCS_BUCKET_NAME')):
        try:
            from google.cloud import storage
            bucket_name = os.environ.get('GCS_BUCKET_NAME', '')
            if not bucket_name:
                raise ValueError("GCS_BUCKET_NAME not configured")

            client = storage.Client()
            blob = client.bucket(bucket_name).blob(path)
            blob.upload_from_string(data, content_type=content_type)
            blob.make_public()
            return blob.public_url

        except Exception as exc:
            logger.error("Google Cloud Storage upload failed: %s. Falling back to local storage...", exc)

    # ── 3. Local Storage Fallback ────────────────────────────────────────────
    try:
        # Determine static directory path relative to project root
        project_root = os.path.dirname(os.path.abspath(__file__))
        upload_dir = os.path.join(project_root, 'static', 'uploads')
        os.makedirs(upload_dir, exist_ok=True)

        # Replace slashes in filename to avoid nested dir creation issues locally
        filename = path.replace('/', '_')
        dest_path = os.path.join(upload_dir, filename)

        with open(dest_path, 'wb') as f:
            f.write(data)

        base_url = os.environ.get('BASE_URL', 'http://127.0.0.1:5000')
        return f"{base_url.rstrip('/')}/static/uploads/{filename}"

    except Exception as exc:
        logger.error("Local storage fallback failed: %s", exc)
        return ''
