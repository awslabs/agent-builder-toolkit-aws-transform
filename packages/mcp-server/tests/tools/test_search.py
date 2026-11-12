# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for search tools (BM25 keyword search)."""

import json

from agent_builder_mcp.tools.search import _lite


class TestKeywordSearch:
    """Tests for keyword_search function."""

    def test_keyword_search_returns_results(self) -> None:
        """Test that search returns results."""
        result = _lite.keyword_search("register agent", top_k=3)
        parsed = json.loads(result)
        assert len(parsed) >= 1
        assert "content" in parsed[0]
        assert "citation" in parsed[0]


class TestSearchBySource:
    """Tests for search_by_source function."""

    def test_search_by_source_filters(self) -> None:
        """Test that search filters by source."""
        result = _lite.search_by_source("requestContext", source="agentic-api", top_k=3)
        parsed = json.loads(result)
        assert len(parsed) >= 1
        for item in parsed:
            assert item["source"] == "TransformAgenticApiModel"


class TestExcerpt:
    """The excerpt is the part of the chunk that shows the most query words."""

    def test_excerpt_starts_at_the_matching_heading(self) -> None:
        doc = "### How do I deploy? " + "Use the pipeline. " * 60 + "### How can my agent show tables? Use A2UI."
        out = _lite._excerpt(doc, _lite.tokenize("agent show tables"))
        assert out.startswith("### How can my agent show tables?")

    def test_excerpt_without_a_match_starts_at_the_beginning(self) -> None:
        doc = "### First. text ### Second. text"
        assert _lite._excerpt(doc, ["zzz"]).startswith("### First.")

    def test_excerpt_is_cut_at_the_limit(self) -> None:
        doc = "### How do I deploy? " + "Use the pipeline. " * 60
        assert len(_lite._excerpt(doc, _lite.tokenize("deploy"))) == _lite.MAX_CONTENT_LENGTH

    def test_section_is_scored_on_the_text_that_is_shown(self) -> None:
        # "Long" holds the words below the cut. "Short" shows them only in the text of the section after it.
        match = "### How can my agent show tables? Use A2UI."
        doc = "### Long. " + "filler " * 80 + "agent show tables ### Short. intro " + match
        assert _lite._excerpt(doc, _lite.tokenize("agent show tables")) == match

    def test_a_word_after_the_next_heading_counts_when_it_is_shown(self) -> None:
        # The excerpt must not show fewer query words than the chunk start shows.
        # Here the chunk start shows three. "Next" shows two, each of them twice: a repeated word counts once.
        doc = "zebra ends the last section. ### Next. yak emu ### Again. yak emu"
        assert _lite._excerpt(doc, _lite.tokenize("zebra yak emu")).startswith("zebra")

    def test_a_word_below_the_cut_does_not_count(self) -> None:
        # "Long" holds "tables" below the cut. Both headings show two query words, so the first one wins.
        doc = "### First. agent show ### Long. agent show " + "filler " * 80 + "tables"
        assert _lite._excerpt(doc, _lite.tokenize("agent show tables")).startswith("### First.")

    def test_h2_to_h6_start_a_section_and_a_code_comment_does_not(self) -> None:
        doc = "intro ## Install. pip # comment zebra #### Deploy. push ##### Deep. yak ###### Deeper. emu"
        for word, start in (
            ("pip", "## Install."),
            ("zebra", "## Install."),
            ("push", "#### Deploy."),
            ("yak", "##### Deep."),
            ("emu", "###### Deeper."),
        ):
            assert _lite._excerpt(doc, _lite.tokenize(word)).startswith(start)

    def test_hashes_inside_other_text_do_not_start_a_section(self) -> None:
        docstring = "# f\n\nExample output:\n    ## Available Skills\n    list skills"
        assert _lite._excerpt(docstring, _lite.tokenize("list skills")).startswith("# f")
        json_string = "intro text " * 3 + '"md": "## Instructions review"'
        assert _lite._excerpt(json_string, _lite.tokenize("instructions review")).startswith("intro")

    def test_excerpt_without_a_heading_shows_the_window_that_matches(self) -> None:
        doc = "# make_agent\n\n" + "Builds the agent. " * 60 + "enable_platform_skills: load the packaged skills."
        assert "enable_platform_skills" in _lite._excerpt(doc, _lite.tokenize("enable_platform_skills"))
        assert _lite._excerpt(doc, _lite.tokenize("builds the agent")).startswith("# make_agent")

    def test_windows_overlap_and_start_at_a_word(self) -> None:
        # "zebra" is before character 500, "yak" after it: only the window that starts at character 250 shows both.
        text = "Builds the agent. "
        doc = "# make_agent\n\n" + text * 16 + "zebra " + text * 11 + "yak"
        out = _lite._excerpt(doc, _lite.tokenize("zebra yak"))
        assert "zebra" in out and "yak" in out
        # Character 250 is inside "Builds", so that window starts at the next word.
        assert out.startswith("the agent.")

    def test_synonyms_do_not_choose_the_excerpt(self) -> None:
        # "hitl" expands to domTreeJson, component and more: words of the section after this heading.
        heading = "DynamicHITLRenderEngine Rendering Pipeline"
        top = json.loads(_lite.keyword_search(heading, top_k=1))[0]
        assert top["content"].startswith("## " + heading)

    def test_search_by_source_returns_the_matching_section(self) -> None:
        parsed = json.loads(_lite.search_by_source("validation common errors", source="hitl-validation", top_k=1))
        assert parsed[0]["content"].startswith("### Common Errors and Fixes")

    def test_a2ui_faq_is_in_the_top_results(self) -> None:
        parsed = json.loads(_lite.keyword_search("how can my agent show a table, a form or a chart in chat", top_k=5))
        faq = [r["content"] for r in parsed if r["content"].startswith("### How can my agent show tables")]
        assert faq
        # A search client reads only the excerpt, so the option, the two tools and the way form values
        # come back must stay in the first MAX_CONTENT_LENGTH characters of the answer.
        for shown in ("enable_platform_skills", "render_a2ui_surface", "suggest_replies", "Form submissions come back"):
            assert shown in faq[0]
