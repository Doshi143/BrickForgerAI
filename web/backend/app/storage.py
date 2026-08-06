"""Stage: job artifact storage -- local disk vs S3-compatible object storage
(Cloudflare R2), so job files survive a redeploy instead of living only on
whichever machine happened to run the pipeline.

Deliberately just this narrow interface (put/get_bytes/exists/signed_url),
not a full filesystem abstraction: the pipeline stages themselves still
write to local disk during processing (trimesh, PIL, and brickforge all
need real filesystem paths, not S3 keys) -- this module only covers
mirroring the *finished* artifacts somewhere that survives past this
process, and serving them back out.
"""
from __future__ import annotations

import os
import shutil
from abc import ABC, abstractmethod


class Storage(ABC):
    @abstractmethod
    def put(self, job_id: str, filename: str, local_path: str) -> None:
        """Persist the file already sitting at local_path under
        (job_id, filename)."""
        raise NotImplementedError

    @abstractmethod
    def get_bytes(self, job_id: str, filename: str) -> bytes | None:
        raise NotImplementedError

    @abstractmethod
    def exists(self, job_id: str, filename: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def signed_url(self, job_id: str, filename: str, expires_in: int = 300) -> str | None:
        """A short-lived direct-download URL, or None if this backend can't
        produce one -- callers should fall back to serving the file
        directly from local disk in that case (see LocalStorage)."""
        raise NotImplementedError


class LocalStorage(Storage):
    """Current behaviour: files just live under jobs/<job_id>/<filename> on
    this machine. The default whenever R2 env vars are absent, so local
    development needs zero extra setup."""

    def __init__(self, root: str):
        self.root = root

    def _path(self, job_id: str, filename: str) -> str:
        job_dir = os.path.join(self.root, job_id)
        os.makedirs(job_dir, exist_ok=True)
        return os.path.join(job_dir, filename)

    def put(self, job_id: str, filename: str, local_path: str) -> None:
        dest = self._path(job_id, filename)
        if os.path.abspath(dest) != os.path.abspath(local_path):
            shutil.copy2(local_path, dest)

    def get_bytes(self, job_id: str, filename: str) -> bytes | None:
        path = self._path(job_id, filename)
        if not os.path.isfile(path):
            return None
        with open(path, "rb") as f:
            return f.read()

    def exists(self, job_id: str, filename: str) -> bool:
        return os.path.isfile(self._path(job_id, filename))

    def signed_url(self, job_id: str, filename: str, expires_in: int = 300) -> str | None:
        # No meaningful "signed URL" for a file on this same machine --
        # callers serve it directly instead (see main.py's _serve_job_file).
        return None


class R2Storage(Storage):
    """S3-compatible object storage via Cloudflare R2. boto3 pointed at
    R2's S3-compatible endpoint (https://<account_id>.r2.cloudflarestorage.com)
    rather than a Cloudflare-specific SDK -- R2 deliberately implements the
    S3 API for exactly this reason."""

    def __init__(self, account_id: str, access_key_id: str, secret_access_key: str, bucket: str):
        import boto3

        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name="auto",
        )

    @staticmethod
    def _key(job_id: str, filename: str) -> str:
        return f"{job_id}/{filename}"

    def put(self, job_id: str, filename: str, local_path: str) -> None:
        self.client.upload_file(local_path, self.bucket, self._key(job_id, filename))

    def get_bytes(self, job_id: str, filename: str) -> bytes | None:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=self._key(job_id, filename))
        except self.client.exceptions.NoSuchKey:
            return None
        except Exception as exc:
            if "NoSuchKey" in type(exc).__name__ or "404" in str(exc):
                return None
            raise
        return response["Body"].read()

    def exists(self, job_id: str, filename: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=self._key(job_id, filename))
            return True
        except Exception:
            return False

    def signed_url(self, job_id: str, filename: str, expires_in: int = 300) -> str | None:
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": self._key(job_id, filename)},
            ExpiresIn=expires_in,
        )


def get_storage() -> Storage:
    account_id = os.environ.get("R2_ACCOUNT_ID")
    access_key_id = os.environ.get("R2_ACCESS_KEY_ID")
    secret_access_key = os.environ.get("R2_SECRET_ACCESS_KEY")
    bucket = os.environ.get("R2_BUCKET")

    if account_id and access_key_id and secret_access_key and bucket:
        return R2Storage(account_id, access_key_id, secret_access_key, bucket)

    local_root = os.path.join(os.path.dirname(__file__), "..", "jobs")
    return LocalStorage(local_root)
