# Finding Artifacts

Read this when you need to locate an artifact you did not just create — a user upload, an earlier
step's output, or everything attached to a plan step.

## `list_artifacts` filter shapes

Build filters with the **wire field names** the service expects: the filter structures use
`category` (the CategoryType enum) and `artifactLabel`. Do not use `categoryType`/`label` here —
those are the *upload* path's names (`ArtifactType.categoryType` and the top-level `label` on
`create_artifact_upload_url`), not the `list_artifacts` filter's. The tool forwards your dict
unvalidated, so a wrong key fails service-side with a validation error instead of a helpful local one.

```
# everything attached to a plan step — the direct way to find a step's outputs
{"planStepFilter": {"planStepId": "<step id>", "category": "PLAN_STEP_OUTPUT"}}

# by category and label
{"categoryFilter": {"category": "HITL_FROM_USER", "artifactLabel": "..."}}

# what a particular agent instance produced
{"agentFilter": {"agentInstanceId": "...", "category": "..."}}

# across the workspace
{"workspaceFilter": {"category": "...", "artifactLabel": "..."}}
```

`planStepFilter` and `workspaceFilter` are absent from the tool description but work, for the same
pass-through reason.

## Reading back a file the user uploaded

Four steps, in order:

1. **Get the id** from the HITL response, or find it with a `categoryFilter` on the user-side
   category (`HITL_FROM_USER` or `CUSTOMER_INPUT`).
2. **`get_artifact_metadata(artifact_id)`** — confirm `isS3ObjectPresent` and read `fileMetadata`
   to learn the real filename.
3. **`create_artifact_download_url(artifact_id)`** with visibility matching where the bytes live
   (`INTERNAL` default for artifact-store copies).
4. **`download_artifact(..., output_dir=<a fresh dir per artifact>, file_name=<name from
   fileMetadata>)`** — always pass `file_name`, or the file lands as literally `downloaded_file`,
   losing the extension your parser keys on and overwriting the previous download.

## Verify before you cite

Artifact ids are platform-issued. Before referencing one in a message, worklog, or HITL payload,
be sure it came from a real response — `get_artifact_metadata` or `list_artifacts` if in doubt.
A fabricated or half-uploaded id produces a 404 on the user's side.
