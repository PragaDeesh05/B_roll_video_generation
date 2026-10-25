"""
MinIO S3-Compatible Storage Service with Local Filesystem Fallback (Phase 11 & Section 17).
Handles media, final video results, and artifact uploads/downloads/caching with MinIO and Docker.
"""
from __future__ import annotations

import json
import logging
import mimetypes
import shutil
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings

logger = logging.getLogger(__name__)


class StorageService:
    """Manages file storage in MinIO S3 or local directory fallback."""

    def __init__(
        self,
        endpoint: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        bucket: Optional[str] = None,
        secure: Optional[bool] = None,
        use_minio: Optional[bool] = None,
    ):
        self.use_minio = use_minio if use_minio is not None else settings.use_minio
        self.endpoint = endpoint or settings.minio_endpoint
        self.access_key = access_key or settings.minio_access_key
        self.secret_key = secret_key or settings.minio_secret_key
        self.bucket = bucket or settings.minio_bucket
        self.secure = secure if secure is not None else settings.minio_secure

        self.minio_client = None
        self.boto3_client = None

        if self.use_minio:
            self._connect_minio()

    def _connect_minio(self) -> None:
        """Connect to MinIO using the official Minio Python SDK or boto3."""
        # 1. Try official Minio SDK
        try:
            from minio import Minio
            self.minio_client = Minio(
                endpoint=self.endpoint,
                access_key=self.access_key,
                secret_key=self.secret_key,
                secure=self.secure,
            )
            if not self.minio_client.bucket_exists(self.bucket):
                self.minio_client.make_bucket(self.bucket)
                logger.info(f"Created MinIO bucket '{self.bucket}' at {self.endpoint}")
                # Set public read policy on bucket for easy downloading
                self._set_bucket_download_policy()
            else:
                logger.info(f"Connected to MinIO bucket '{self.bucket}' at {self.endpoint}")
            return
        except Exception as e:
            logger.warning(f"Official MinIO SDK connection failed ({e}); trying boto3 fallback...")

        # 2. Try boto3 fallback
        try:
            import boto3
            self.boto3_client = boto3.client(
                "s3",
                endpoint_url=f"{'https' if self.secure else 'http'}://{self.endpoint}",
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
            )
            try:
                self.boto3_client.head_bucket(Bucket=self.bucket)
            except Exception:
                self.boto3_client.create_bucket(Bucket=self.bucket)
            logger.info(f"Connected to MinIO via boto3 at {self.endpoint}")
        except Exception as e:
            logger.warning(f"MinIO connection failed: {e}; falling back to local storage")
            self.use_minio = False

    def _set_bucket_download_policy(self) -> None:
        """Configure read-only policy for bucket so artifacts can be downloaded directly."""
        if not self.minio_client:
            return
        try:
            policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Sid": "PublicRead",
                        "Effect": "Allow",
                        "Principal": "*",
                        "Action": ["s3:GetObject"],
                        "Resource": [f"arn:aws:s3:::{self.bucket}/*"],
                    }
                ],
            }
            self.minio_client.set_bucket_policy(self.bucket, json.dumps(policy))
        except Exception as e:
            logger.debug(f"Could not set public bucket policy: {e}")

    # ── Upload & Presigned URLs ───────────────────────────────────────────────

    def upload_file(
        self,
        local_path: Path,
        object_key: str,
        content_type: Optional[str] = None,
    ) -> str:
        """Upload a file to MinIO storage and return its S3 URI."""
        if not local_path.exists():
            raise FileNotFoundError(f"File to upload does not exist: {local_path}")

        if not content_type:
            content_type, _ = mimetypes.guess_type(str(local_path))
            if not content_type:
                content_type = "application/octet-stream"

        if self.use_minio:
            if self.minio_client:
                try:
                    self.minio_client.fput_object(
                        bucket_name=self.bucket,
                        object_name=object_key,
                        file_path=str(local_path),
                        content_type=content_type,
                    )
                    return f"s3://{self.bucket}/{object_key}"
                except Exception as e:
                    logger.warning(f"Minio SDK upload failed: {e}; trying boto3...")

            if self.boto3_client:
                try:
                    self.boto3_client.upload_file(
                        str(local_path),
                        self.bucket,
                        object_key,
                        ExtraArgs={"ContentType": content_type},
                    )
                    return f"s3://{self.bucket}/{object_key}"
                except Exception as e:
                    logger.warning(f"boto3 upload failed: {e}; falling back to local storage")

        # Local storage fallback
        dest_path = settings.output_dir / object_key
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        if dest_path.resolve() != local_path.resolve():
            shutil.copy2(local_path, dest_path)
        return str(dest_path)

    def get_presigned_url(self, object_key: str, expires_hours: int = 24) -> Optional[str]:
        """Generate a presigned GET URL for an object stored in MinIO."""
        if not self.use_minio:
            return None

        if self.minio_client:
            try:
                return self.minio_client.presigned_get_object(
                    self.bucket,
                    object_key,
                    expires=timedelta(hours=expires_hours),
                )
            except Exception as e:
                logger.warning(f"Failed to generate presigned URL via MinIO SDK: {e}")

        if self.boto3_client:
            try:
                return self.boto3_client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self.bucket, "Key": object_key},
                    ExpiresIn=expires_hours * 3600,
                )
            except Exception as e:
                logger.warning(f"Failed to generate presigned URL via boto3: {e}")

        return None

    def upload_job_artifacts(self, job_id: str, job_dir: Path) -> Dict[str, Any]:
        """
        Upload all final videos, reports, evaluation sheets, and media for a job
        into MinIO object storage under 'jobs/{job_id}/...'.
        Returns a dictionary of artifact keys, S3 URIs, and presigned access URLs.
        """
        uploaded = {}
        presigned = {}

        if not job_dir.exists():
            return {"uploaded": uploaded, "presigned": presigned}

        # 1. Upload root files (mp4 videos, csv, json, srt)
        for f in job_dir.glob("*"):
            if f.is_file():
                obj_key = f"jobs/{job_id}/{f.name}"
                s3_uri = self.upload_file(f, obj_key)
                uploaded[f.name] = s3_uri
                presigned_url = self.get_presigned_url(obj_key)
                if presigned_url:
                    presigned[f.name] = presigned_url

        # 2. Upload candidate & generated image frames
        for subdir_name in ["candidate_frames", "generated_images"]:
            subdir = job_dir / subdir_name
            if subdir.exists() and subdir.is_dir():
                for img_file in subdir.rglob("*"):
                    if img_file.is_file() and img_file.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                        rel_path = img_file.relative_to(job_dir).as_posix()
                        obj_key = f"jobs/{job_id}/{rel_path}"
                        s3_uri = self.upload_file(img_file, obj_key)
                        uploaded[rel_path] = s3_uri

        logger.info(f"Successfully uploaded {len(uploaded)} artifacts to MinIO bucket '{self.bucket}' for job '{job_id}'")
        return {
            "bucket": self.bucket,
            "job_id": job_id,
            "artifacts_count": len(uploaded),
            "uploaded": uploaded,
            "presigned_urls": presigned,
        }

    # ── Image Caching ─────────────────────────────────────────────────────────

    def cache_image(self, local_path: Path, cache_key: str) -> str:
        """Cache an image in MinIO object storage under 'cache/images/{cache_key}'."""
        ext = local_path.suffix.lower() or ".jpg"
        obj_key = f"cache/images/{cache_key}{ext}"
        return self.upload_file(local_path, obj_key)

    def get_cached_image(self, cache_key: str, dest_dir: Path) -> Optional[Path]:
        """
        Check if an image is already cached in MinIO; if found, download to dest_dir.
        """
        for ext in [".jpg", ".jpeg", ".png", ".webp"]:
            obj_key = f"cache/images/{cache_key}{ext}"
            dest_file = dest_dir / f"{cache_key}{ext}"
            try:
                if self.use_minio and self.minio_client:
                    # Check if object exists
                    self.minio_client.stat_object(self.bucket, obj_key)
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    self.minio_client.fget_object(self.bucket, obj_key, str(dest_file))
                    return dest_file

                if self.use_minio and self.boto3_client:
                    self.boto3_client.head_object(Bucket=self.bucket, Key=obj_key)
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    self.boto3_client.download_file(self.bucket, obj_key, str(dest_file))
                    return dest_file
            except Exception:
                continue

        return None

    def get_file_bytes(self, object_key: str) -> bytes:
        """Read file bytes from MinIO or local fallback."""
        if self.use_minio and self.minio_client:
            try:
                response = self.minio_client.get_object(self.bucket, object_key)
                return response.read()
            finally:
                if 'response' in locals():
                    response.close()
                    response.release_conn()

        if self.use_minio and self.boto3_client:
            obj = self.boto3_client.get_object(Bucket=self.bucket, Key=object_key)
            return obj["Body"].read()

        dest_path = settings.output_dir / object_key
        if not dest_path.exists():
            raise FileNotFoundError(f"Storage object not found: {dest_path}")
        return dest_path.read_bytes()
