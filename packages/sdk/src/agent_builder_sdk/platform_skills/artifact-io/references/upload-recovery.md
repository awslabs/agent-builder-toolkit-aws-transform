# Artifact Upload & Download Recovery

Read this when an upload or download fails, or when the user cannot get a file you delivered.

## The PUT failed or the URL expired

`upload_artifact` returned `{"success": false, ...}` — often a 403 with an expiry or AccessDenied
message. **Do not start over with a new artifact.**

Re-request a URL for the artifact you already have, by passing the id form of the reference:

```
create_artifact_upload_url(
    content_digest=digest,
    artifact_reference={"artifactId": "<the id you already have>"},   # NOT artifactType
    ...)
```

`artifact_reference` is a union of exactly one of `artifactType` (mint a new artifact) or
`artifactId` (target the existing one). Then re-PUT with the fresh url/headers and complete.

Mint a brand-new artifact only if you have not cited the old id anywhere yet.

If the re-request returns `FileAlreadyExistsException` or `ConflictException`, stop retrying — the
object is already stored. Call `get_artifact_metadata`, confirm `isS3ObjectPresent`, and just
complete.

## `copy_artifact` is async and returns no new id

It returns only `{"copyStatus": ...}` — `IN_PROGRESS` or `COMPLETED` — and the public copy keeps
the **same artifact id**.

1. On `IN_PROGRESS`, do not yet tell the user the file is available.
2. Confirm with `get_artifact_metadata(artifact_id)` and check `isS3ObjectPresent.publicBucket`
   is true before announcing.
3. To read the copy back yourself, call `create_artifact_download_url` with the same id **and
   `visibility="EXTERNAL"`** — the default is `INTERNAL`, which reads the artifact-store copy and
   keeps succeeding even when the public copy is missing.

## Download failures

**`download_artifact` returns** `{"success": false, "status_code": ...}` for transfer failures. A
403 there usually means the presigned URL expired — re-call `create_artifact_download_url` for a
fresh URL rather than retrying the old one.
