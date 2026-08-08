"""Content addressing and cache-key derivation.

Identity is content-based (never filename-based), and the cache key includes
`pipeline_version` — a hash of everything whose change must invalidate cached
results (engine, model, detection prompt, taxonomy version). Changing any of
them IS the invalidation; there is no TTL.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_bytes(data: bytes) -> str:
    """Checksum of the raw bytes — the document's identity."""
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path) -> str:
    """Stream a file into its content checksum."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def compute_pipeline_version(
    engine: str,
    models: list[str],
    detection_prompt: str,
    taxonomy_version: str,
) -> str:
    """Hash the scan configuration into the cache-key component.

    Model order must not matter (the same comparison set is the same
    pipeline), so models are sorted before hashing.
    """
    material = "\x1f".join([engine, ",".join(sorted(models)), detection_prompt, taxonomy_version])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
