"""Tests for Sources citation builder."""

import json
import os
from unittest.mock import patch

import pytest

from agent_builder_sdk.ui_chat.sources import SourceEntry, Sources

WS = "11111111-1111-1111-1111-111111111111"
JOB = "22222222-2222-2222-2222-222222222222"
ART = "33333333-3333-3333-3333-333333333333"
ART2 = "44444444-4444-4444-4444-444444444444"

ENV = {"WORKSPACE_ID": WS, "JOB_ID": JOB}


class TestSourceEntry:

    def test_to_dict_minimal(self):
        e = SourceEntry(id="f1", title="File 1", link="aws-transform://x")
        assert e.to_dict() == {"id": "f1", "title": "File 1", "link": "aws-transform://x"}

    def test_to_dict_with_description(self):
        e = SourceEntry(id="f1", title="File 1", link="aws-transform://x", description="desc")
        assert e.to_dict()["description"] == "desc"

    def test_to_dict_omits_empty_description(self):
        e = SourceEntry(id="f1", title="File 1", link="aws-transform://x")
        assert "description" not in e.to_dict()


class TestSources:

    @patch.dict(os.environ, ENV)
    def test_build_empty(self):
        assert Sources().build() == ""

    @patch.dict(os.environ, ENV)
    def test_build_single_artifact_source(self):
        s = Sources()
        s.add_artifact_source(title="servers.csv", artifact_id=ART)
        result = s.build()
        assert result.startswith("```atx-sources\n")
        assert result.endswith("\n```")
        payload = json.loads(result.split("\n")[1])
        assert len(payload) == 1
        assert payload[0]["title"] == "servers.csv"
        assert payload[0]["link"] == f"aws-transform://workspaces/{WS}/jobs/{JOB}/artifacts/{ART}"

    @patch.dict(os.environ, ENV)
    def test_id_is_auto_generated_uuid(self):
        s = Sources()
        s.add_artifact_source(title="f.csv", artifact_id=ART)
        payload = json.loads(s.build().split("\n")[1])
        # Should be a valid UUID
        import uuid

        uuid.UUID(payload[0]["id"])

    @patch.dict(os.environ, ENV)
    def test_build_multiple_sources(self):
        s = Sources()
        s.add_artifact_source(title="File 1", artifact_id=ART)
        s.add_artifact_source(title="File 2", artifact_id=ART2, description="details")
        payload = json.loads(s.build().split("\n")[1])
        assert len(payload) == 2
        assert payload[1]["description"] == "details"

    @patch.dict(os.environ, ENV)
    def test_chaining(self):
        result = (
            Sources()
            .add_artifact_source(title="A", artifact_id=ART)
            .add_artifact_source(title="B", artifact_id=ART2)
            .build()
        )
        payload = json.loads(result.split("\n")[1])
        assert len(payload) == 2

    @patch.dict(os.environ, ENV)
    def test_description_omitted_when_empty(self):
        s = Sources()
        s.add_artifact_source(title="File", artifact_id=ART)
        payload = json.loads(s.build().split("\n")[1])
        assert "description" not in payload[0]

    @patch.dict(os.environ, ENV)
    def test_invalid_artifact_id_raises(self):
        with pytest.raises(ValueError, match="artifact_id must be a valid UUID"):
            Sources().add_artifact_source(title="F", artifact_id="bad")

    def test_explicit_workspace_and_job(self):
        s = Sources(workspace_id=WS, job_id=JOB)
        s.add_artifact_source(title="File", artifact_id=ART)
        payload = json.loads(s.build().split("\n")[1])
        assert f"workspaces/{WS}" in payload[0]["link"]

    def test_invalid_workspace_id_raises(self):
        with pytest.raises(ValueError, match="workspace_id must be a valid UUID"):
            Sources(workspace_id="bad", job_id=JOB)

    def test_invalid_job_id_raises(self):
        with pytest.raises(ValueError, match="job_id must be a valid UUID"):
            Sources(workspace_id=WS, job_id="bad")

    def test_missing_env_vars_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(KeyError):
                Sources()
