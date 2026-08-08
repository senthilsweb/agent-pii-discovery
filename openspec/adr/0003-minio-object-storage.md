# ADR 0003 — Self-hosted MinIO as the S3 backend; shared bucket, owned prefixes

Date: 2026-08-08 · Status: accepted

## Decision

Object storage runs against the owner's existing self-hosted **MinIO**
instance rather than AWS S3, reusing the shared `ai-agents` bucket and the
credentials already provisioned for `agents/linkedin-cover-generator/.env`
in the monorepo — no new bucket, no new IAM identity. This project owns the
`uploads/`, `results/`, and `exports/` top-level prefixes inside that bucket
(the hive partitions from PRD §9.1); every other agent's own prefix
(`runs/<runId>/`, etc.) is untouched.

`OBJECT_STORE_ENDPOINT=https://minio-console.nathansweb.com` is the real S3
API endpoint despite the "console" name in the hostname — verified directly
(see Consequences).

## Why

- `pipeline/storage/s3.py` was built S3-compatible-first (boto3, no
  AWS-specific SDK calls), so pointing it at a self-hosted MinIO instead of
  AWS S3 needed no code change beyond the addressing-style fix below —
  exactly the portability the module was designed for.
- The owner already runs and pays for this MinIO instance; a second bucket
  or a second AWS account would be pure duplication for a project whose S3
  usage is uploads + result mirrors, nothing exotic.
- Reusing the existing credentials (rather than minting a new MinIO IAM user
  scoped to a fresh bucket) matches how this project has consistently
  reused proven monorepo infrastructure (Arize space, `ant` OAuth profile)
  instead of standing up parallel copies.

## Consequences

- **Bug found and fixed in the same session**: `pipeline/storage/s3.py`'s
  `_client()` built a boto3 client with no addressing-style configuration.
  Virtual-hosted-style (boto3's default) doesn't work against MinIO — every
  write failed with `S3 API Requests must be made to API port`. Fixed by
  honoring `OBJECT_STORE_FORCE_PATH_STYLE` via
  `Config(s3={"addressing_style": "path"})`. Two regression tests guard it
  (`tests/test_storage.py`).
- **Endpoint correction**: the owner's initial pointer (`minio.nathansweb.com`)
  turned out to be a vhost that serves only the MinIO console, not the S3
  API — confirmed empirically (that hostname returns the same "must be made
  to API port" error even with correct path-style config). The hostname
  that actually accepts S3 API calls, and that `linkedin-cover-generator`
  already uses successfully in production, is
  `minio-console.nathansweb.com` — the "console" in the name is misleading
  but it is the working API endpoint. Verified with a real
  put/list/delete round trip against the `ai-agents` bucket, 2026-08-08.
- **Bucket sharing is safe by construction**: `list_objects_v2` against
  `ai-agents` before this project wrote anything showed exactly one
  existing top-level prefix, `runs/`, from other agents. This project's
  three prefixes don't collide with it or with each other.
- Credentials live host-side in `.env` (gitignored) — see the
  Managed Agents Vault note below; they were never a candidate for a vault
  credential in the first place, for the same reason the Arize credentials
  aren't (ADR 0002): the S3 client only ever runs in the host process
  (`pipeline/storage/s3.py`, called from `pipeline/scan.py`'s `_finish()`),
  never inside a Managed Agents session sandbox. No sandbox in this
  codepath means no vault-injection point exists to use.
- Production hardening (bucket lifecycle policy on `uploads/`, a
  dedicated non-root MinIO credential scoped to this project's prefixes
  instead of the shared root-equivalent key) is deferred — tracked in the
  openspec task register, not blocking Phase 1's storage contract.
