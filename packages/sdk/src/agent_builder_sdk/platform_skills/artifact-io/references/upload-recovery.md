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

## "The user can't download it but my own download works"

Check `get_artifact_metadata`'s **`scanStatus` before touching visibility or re-uploading.** The
malware-scan gate is applied on the user-facing path but not on the agent's, so an artifact can be
readable by you and blocked for them:

| `scanStatus` | Meaning | Action |
|---|---|---|
| `CLEAN` | scan passed | the problem really is visibility — see `copy_artifact` below |
| `PENDING` | still scanning | wait and re-check; don't re-upload |
| `QUARANTINED` | permanently blocked | re-uploading the same bytes will be blocked again — regenerate the file or explain to the user |
| `FAILED` | unservable | report it; do not retry |

## `copy_artifact` is async and returns no new id

It returns only `{"copyStatus": ...}` — `IN_PROGRESS` or `COMPLETED` — and the public copy keeps
the **same artifact id**.

1. On `IN_PROGRESS`, do not yet tell the user the file is available.
2. Confirm with `get_artifact_metadata(artifact_id)` and check `isS3ObjectPresent.publicBucket`
   is true before announcing.
3. To read the copy back yourself, call `create_artifact_download_url` with the same id **and
   `visibility="EXTERNAL"`** — the default is `INTERNAL`, which reads the artifact-store copy and
   keeps succeeding even when the public copy is missing.

## Download failures: which call failed matters

**`create_artifact_download_url` raises.** Branch on the exception type, never the HTTP status:

- `ArtifactScanInProgressException` — transient. Wait its `retryAfterSeconds`, retry the same call.
- `ArtifactScanFailedException` — terminal despite also being a 409. Stop; report unavailable.
- `ArtifactQuarantinedException` — permanent (403). Never retry; tell the user the file was blocked.

**`download_artifact` returns** `{"success": false, "status_code": ...}` for transfer failures. A
403 there usually means the presigned URL expired — re-call `create_artifact_download_url` for a
fresh URL rather than retrying the old one.
