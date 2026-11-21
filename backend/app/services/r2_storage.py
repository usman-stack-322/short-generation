from pathlib import Path
from typing import Optional

from ..config import Settings, get_settings

try:
    import boto3
    from boto3.s3.transfer import TransferConfig
    from botocore.config import Config as BotoConfig
    from botocore.exceptions import ClientError
except ImportError:  # Allows running pure logic tests before pip install
    boto3 = None
    TransferConfig = None
    BotoConfig = None
    ClientError = Exception


class R2StorageService:
    """Cloudflare R2 (S3-compatible) storage client with multipart upload & presigned URLs."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self._client = None

    @property
    def client(self):
        if self._client is None:
            if boto3 is None:
                raise RuntimeError("boto3 is not installed. Run: pip install -r backend/requirements.txt")
            if self.settings.is_local_storage:
                raise RuntimeError(
                    "STORAGE_MODE is set to 'local'. Switch STORAGE_MODE=r2 with valid Cloudflare R2 credentials for R2 uploads."
                )
            if not self.settings.r2_configured:
                raise RuntimeError("Cloudflare R2 credentials are missing in .env")
            self._client = boto3.client(
                service_name="s3",
                endpoint_url=self.settings.r2_endpoint_url,
                aws_access_key_id=self.settings.r2_access_key_id,
                aws_secret_access_key=self.settings.r2_secret_access_key,
                region_name="auto",
                config=BotoConfig(signature_version="s3v4", retries={"max_attempts": 5, "mode": "standard"}),
            )
        return self._client

    def generate_presigned_upload_url(self, r2_key: str, content_type: str = "video/mp4", expires_in: int = 3600) -> str:
        return self.client.generate_presigned_url(
            ClientMethod="put_object",
            Params={
                "Bucket": self.settings.r2_bucket_name,
                "Key": r2_key,
                "ContentType": content_type,
            },
            ExpiresIn=expires_in,
        )

    def generate_presigned_download_url(self, r2_key: str, expires_in: int = 3600) -> str:
        return self.client.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": self.settings.r2_bucket_name, "Key": r2_key},
            ExpiresIn=expires_in,
        )

    def object_exists(self, r2_key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.settings.r2_bucket_name, Key=r2_key)
            return True
        except ClientError:
            return False

    def upload_file_multipart(self, local_path: Path, r2_key: str, content_type: str = "video/mp4") -> None:
        """Uploads large video files reliably using 16 MB multipart chunks."""
        config = TransferConfig(
            multipart_threshold=16 * 1024 * 1024,
            multipart_chunksize=16 * 1024 * 1024,
            max_concurrency=4,
            use_threads=True,
        )
        self.client.upload_file(
            Filename=str(local_path),
            Bucket=self.settings.r2_bucket_name,
            Key=r2_key,
            ExtraArgs={"ContentType": content_type},
            Config=config,
        )
