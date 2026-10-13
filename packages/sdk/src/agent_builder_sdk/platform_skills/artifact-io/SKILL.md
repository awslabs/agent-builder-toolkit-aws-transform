---
name: artifact-io
description: Use whenever a file or result must outlive the conversation - persisting outputs, delivering a file to the user, or reading a user-uploaded file back. Covers the upload ritual, the delivery decision (internal vs customer-visible), attaching output to a plan step, downloads, and verifying an upload actually landed.
---

# Artifact I/O

The artifact store is the job's file system of record. Anything worth keeping — reports, schemas,
generated code, results, approval summaries — is an artifact. Files in `/tmp` die with the
container, and content pasted into chat is not a deliverable.

## Decide visibility BEFORE you upload

The visibility you pass selects which bucket the presigned URL points at, so this is a decision
you make at the upload-URL call, not afterward:

| Situation | How to upload |
|---|---|
| Intermediate result you may re-read later in the job | `categoryType="AGENT_OUTPUT"`, leave visibility at its `INTERNAL` default |
| **Something the user is meant to receive** | `categoryType="CUSTOMER_OUTPUT"` **and** `visibility="EXTERNAL"` — one upload, no copy step |
| Request payload backing a HITL task | `categoryType="HITL_FROM_AGENT"` |
| Internal step output to re-query by step later | `categoryType="PLAN_STEP_OUTPUT"` — stays `INTERNAL`, routes to the internal (not customer-visible) path |

`categoryType` and visibility are independent: visibility picks the bucket (customer-reachable or
not), `categoryType` picks the path. **To attach any artifact to a plan step, pass `plan_step_id`**
— that's the attachment mechanism, and it works with any category. So a step deliverable the user
should receive is the `CUSTOMER_OUTPUT` + `visibility="EXTERNAL"` row **plus** `plan_step_id`, not
`PLAN_STEP_OUTPUT`.

`copy_artifact` is the **repair path**, not the delivery path: use it only for something you
already uploaded as `INTERNAL` and have since decided to surface. Never plan an internal upload
followed by a copy when you already know the file is for the user.

## Upload: four calls, none optional

```
1. digest = python3 -c "import hashlib,base64,sys; \
     print(base64.b64encode(hashlib.sha256(open(sys.argv[1],'rb').read()).digest()).decode())" <file>
2. resp   = create_artifact_upload_url(
                content_digest=digest,
                artifact_reference={"artifactType": {
                    "categoryType": "CUSTOMER_OUTPUT",   # see table above
                    "fileType": "JSON",                  # JSON | TXT | ZIP | HTML | CSV | PDF | ...
                    "schemaType": "NONE"}},
                visibility="EXTERNAL",                   # for anything the user receives
                plan_step_id=<step id>,
                label="Schema inspection report",
                file_metadata={"path": "schema-report.json",
                               "description": "Source schema and drift summary"})
3. PUT    = upload_artifact(s3_presigned_url=resp["s3preSignedUrl"],
                request_headers=resp["requestHeaders"],
                artifact_id=resp["artifactId"], file_path=<local path>)
4. DONE   = complete_artifact_upload(artifact_id=resp["artifactId"])
```

**The digest is base64 of the raw 32 sha256 bytes** — 44 chars, ends in `=`. Use the command
above; never `sha256sum` or `hexdigest()`. A hex digest is not caught locally: it passes
validation and then fails at upload. If that happens, recompute the base64 digest and request a
new URL rather than retrying the same value.

**Compute the digest last, and freeze the file.** The digest is handed back inside
`requestHeaders` and forwarded on the PUT, so the URL accepts only those exact bytes. If you edit
or re-serialize the file after getting the URL, discard the URL and request a new one.

**Check `PUT["success"]` after step 3.** A missing file, an expired URL, a checksum mismatch, and
a 403 all come back as ordinary data (`{"success": false, "status_code": ..., "error": ...}`) —
nothing raises. Call `complete_artifact_upload` only when `PUT["success"]` is true. When the PUT
fails against a customer-configured (non-AWS Transform) bucket, the error may also carry `is_user_error:
true` and a `customer_facing_message` — relay that message to the user instead of the raw `error`.

**Name anything a human opens** via `file_metadata` — and if you pass `file_metadata` at all you
must include `"path"`, or the call fails locally.

**Verify it landed** before citing the id to the user: `complete_artifact_upload` returns the full
artifact, so compare its `sizeInBytes` with the local size from step 3. If unsure whether you ever
completed one, `get_artifact_metadata(artifact_id)` and read `isS3ObjectPresent` — an
uncompleted upload is the classic silent failure and this is the only way to see it.

## Attaching output to the plan: two separate indexes

Neither implies the other, so do both for every step deliverable:

```
create_artifact_upload_url(..., plan_step_id=<step id>)     # artifact carries the step
create_worklog(plan_step_id=<step id>, artifact_id=<id>)    # step timeline carries the file
```

The worklog is what makes it visible: an artifact with `plan_step_id` but no worklog is queryable
and invisible in the step narrative, and the worklog's `artifact_id` is what grows a **Download
link** in the activity feed the user reads.

## Download

```
resp = create_artifact_download_url(artifact_id=...)   # visibility="EXTERNAL" to read a public copy
download_artifact(s3_presigned_url=..., request_headers=..., artifact_id=...,
                  output_dir=<fresh dir>, file_name=<name from fileMetadata>)
```

**Always pass `file_name`** — omit it and the file is written as literally `downloaded_file`,
losing the extension your parser needs and overwriting the previous one.

A HITL file *field* — a `fileUploadV2` field inside an autoform, or a standalone `FileUploadV2`
task — arrives as artifact references: get the id from the HITL response, `get_artifact_metadata`
to confirm presence and learn the real filename, then download; do not expect inline bytes. The
one exception is a standalone `FileUploadComponent` task, whose `retrieve_hitl_output_as_string`
returns base64-decoded content inline instead of a reference (see `hitl-loop`).

## Default-sink rule

At the end of every step that produced content, ask whether it landed in the artifact store.
Upload as soon as results are final — don't wait to be asked, and don't treat chat as delivery.

## Symptoms and causes

| Symptom | Cause | Fix |
|---|---|---|
| "Invalid SHA-256 checksum format" | digest is not base64 (e.g. raw `sha256sum` output) | regenerate with the base64 command above |
| Upload fails although the digest passed local checks | hex digest | recompute the base64 digest, request a new URL |
| Artifact "uploaded" but downloads fail / never appears | `complete_artifact_upload` skipped, or `success:false` ignored | check `success`, then complete; verify `isS3ObjectPresent` |
| PUT returns 403 / expired | presigned URL lapsed | re-request the URL for the SAME id — see `references/upload-recovery.md` |
| User can't see a file you delivered | uploaded `INTERNAL` | upload as `CUSTOMER_OUTPUT` + `visibility="EXTERNAL"`; `copy_artifact` to repair |
| Downloaded file has no extension | `file_name` omitted | always pass it, from `fileMetadata` |
| 404 on an artifact id you cited | id fabricated or from a failed upload | cite only verified ids |
| Deliverables lost after container restart | outputs kept in `/tmp` | upload as artifacts as soon as produced |

## References

- `references/upload-recovery.md` — expired URLs, download failures, and `copy_artifact`'s async
  behavior.
- `references/finding-artifacts.md` — `list_artifacts` filter shapes (the tool description's field
  names differ from the wire model).
