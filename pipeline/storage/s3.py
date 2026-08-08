"""S3 storage: hive-partitioned keys + a never-throw, env-gated uploader.

Adapted from the monorepo's upload_run_to_object_store.ts, with the flat
runs/ prefix replaced by `user_login=<login>/dt=<date>/<sha256>/` partitions
so DuckDB/Athena partition-prune natively. Without OBJECT_STORE_BUCKET the
uploader is a no-op (dev mode); per-file failures are collected, never
raised — storage trouble must not kill a scan.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path


def upload_key(user_login: str, dt: date, checksum: str, file_name: str) -> str:
    """uploads/user_login=<login>/dt=<YYYY-MM-DD>/<sha256>/<original-filename>"""
    return f"uploads/user_login={user_login}/dt={dt.isoformat()}/{checksum}/{file_name}"


def result_key(user_login: str, dt: date, checksum: str) -> str:
    """results/user_login=<login>/dt=<YYYY-MM-DD>/<sha256>/result.json"""
    return f"results/user_login={user_login}/dt={dt.isoformat()}/{checksum}/result.json"


@dataclass
class UploadOutcome:
    """What happened; `skipped` means no bucket configured (dev no-op)."""
    skipped: bool
    bucket: str | None = None
    uploaded: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)  # (key, error)


def _client():
    import boto3  # lazy: optional [s3] dependency
    from botocore.config import Config

    kwargs: dict = {"region_name": os.environ.get("OBJECT_STORE_REGION", "us-east-1")}
    if os.environ.get("OBJECT_STORE_ENDPOINT"):
        kwargs["endpoint_url"] = os.environ["OBJECT_STORE_ENDPOINT"]
    if os.environ.get("OBJECT_STORE_ACCESS_KEY_ID"):
        kwargs["aws_access_key_id"] = os.environ["OBJECT_STORE_ACCESS_KEY_ID"]
        kwargs["aws_secret_access_key"] = os.environ.get("OBJECT_STORE_SECRET_ACCESS_KEY", "")
    # MinIO (and most self-hosted S3-compatible stores) can't do
    # virtual-hosted-style bucket DNS resolution — path-style is required.
    if os.environ.get("OBJECT_STORE_FORCE_PATH_STYLE", "").lower() in ("1", "true", "yes"):
        kwargs["config"] = Config(s3={"addressing_style": "path"})
    return boto3.client("s3", **kwargs)


def put_file(local_path: str | Path, key: str) -> UploadOutcome:
    """Upload one file; env-gated no-op without a bucket; never raises."""
    bucket = os.environ.get("OBJECT_STORE_BUCKET", "").strip()
    if not bucket:
        return UploadOutcome(skipped=True)
    outcome = UploadOutcome(skipped=False, bucket=bucket)
    try:
        _client().upload_file(str(local_path), bucket, key)
        outcome.uploaded.append(key)
    except Exception as exc:  # noqa: BLE001 — collected, reported, never fatal
        outcome.failed.append((key, str(exc)))
    return outcome


def put_bytes(data: bytes, key: str) -> UploadOutcome:
    """Upload a byte payload (result.json mirror); same no-op/never-throw rules."""
    bucket = os.environ.get("OBJECT_STORE_BUCKET", "").strip()
    if not bucket:
        return UploadOutcome(skipped=True)
    outcome = UploadOutcome(skipped=False, bucket=bucket)
    try:
        _client().put_object(Bucket=bucket, Key=key, Body=data,
                             ContentType="application/json")
        outcome.uploaded.append(key)
    except Exception as exc:  # noqa: BLE001
        outcome.failed.append((key, str(exc)))
    return outcome
