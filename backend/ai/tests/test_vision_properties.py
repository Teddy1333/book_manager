"""
Property-based tests for the vision service.

These tests validate universal correctness properties of the vision service logic
using mocked OpenAI client and httpx calls.

Validates: Requirements 1.3, 1.4, 3.1, 3.2, 3.3, 3.4, 3.5
"""

import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

# Set required env vars BEFORE importing the vision module
os.environ.setdefault("OPENAI_API_KEY", "test-key-for-testing")
os.environ.setdefault("OPENAI_BASE_URL", "http://test-openai:8080/v1")
os.environ.setdefault("SCRAPER_SERVICE_URL", "http://test-scraper:8002")

# Now import the module under test
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from services.vision import extract_book_metadata, _enrich_via_scraper


# --- Strategies ---

BOOK_METADATA_KEYS = ["title", "author", "isbn", "description"]

nullable_text = st.one_of(st.none(), st.text(min_size=1, max_size=100))


@st.composite
def vision_model_output(draw):
    """Generate arbitrary vision model outputs — may include extra keys,
    missing keys, or any combination of null/non-null fields."""
    # Decide which keys to include (may be all, some, or none)
    included_keys = draw(st.lists(st.sampled_from(BOOK_METADATA_KEYS), unique=True))
    result = {}
    for key in included_keys:
        result[key] = draw(nullable_text)
    # Optionally add extra unexpected keys
    extra_keys = draw(
        st.lists(
            st.text(
                alphabet=st.characters(whitelist_categories=("L", "N")),
                min_size=1,
                max_size=20,
            ),
            max_size=3,
        )
    )
    for extra_key in extra_keys:
        if extra_key not in BOOK_METADATA_KEYS:
            result[extra_key] = draw(st.text(max_size=50))
    return result


@st.composite
def scraper_results(draw):
    """Generate plausible scraper search results."""
    count = draw(st.integers(min_value=1, max_value=3))
    results = []
    for _ in range(count):
        results.append(
            {
                "title": draw(st.text(min_size=1, max_size=50)),
                "author": draw(st.text(min_size=1, max_size=50)),
                "url": draw(st.text(min_size=5, max_size=80)),
            }
        )
    return results


# --- Helpers ---


def make_openai_response(content_dict: dict):
    """Create a mock OpenAI completion response."""
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps(content_dict)
    mock_response.choices = [mock_choice]
    return mock_response


def make_httpx_response(json_data, status_code=200):
    """Create a mock httpx response."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = json_data
    mock_resp.raise_for_status = MagicMock()
    if status_code >= 400:
        import httpx

        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=mock_resp
        )
    return mock_resp


# --- Property Tests ---


class TestResponseStructureCompleteness:
    """
    Property 1: Response structure completeness

    For any vision model output, the response always contains exactly the four
    Book_Metadata keys with null for missing fields.

    **Validates: Requirements 1.3, 1.4**
    """

    @given(raw_output=vision_model_output())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @pytest.mark.asyncio
    async def test_response_always_has_four_metadata_keys(self, raw_output):
        """For any vision model output, the response contains title, author,
        isbn, description — with None for fields not identified."""
        mock_client = AsyncMock()
        mock_client.chat.completions.create.return_value = make_openai_response(
            raw_output
        )

        mock_enrich = AsyncMock(return_value=(None, False))

        with patch("services.vision.client", mock_client), patch(
            "services.vision._enrich_via_scraper", mock_enrich
        ):
            result = await extract_book_metadata(b"fake-image-bytes")

        # All four Book_Metadata keys must be present
        for key in BOOK_METADATA_KEYS:
            assert key in result, f"Missing key '{key}' in response"

        # Each value should be either a string or None
        for key in BOOK_METADATA_KEYS:
            assert result[key] is None or isinstance(
                result[key], str
            ), f"Key '{key}' has unexpected type: {type(result[key])}"

        # Response also has enrichment fields
        assert "enriched" in result
        assert "enrichment" in result


class TestEnrichmentTriggerCondition:
    """
    Property 2: Enrichment trigger condition

    Scraper is called if and only if title or author is non-null.

    **Validates: Requirements 3.1, 3.4**
    """

    @given(raw_output=vision_model_output())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @pytest.mark.asyncio
    async def test_scraper_called_iff_title_or_author_nonnull(self, raw_output):
        """Scraper is called if and only if at least one of title or author
        is non-null in the extracted metadata."""
        mock_client = AsyncMock()
        mock_client.chat.completions.create.return_value = make_openai_response(
            raw_output
        )

        mock_enrich = AsyncMock(return_value=(None, False))

        with patch("services.vision.client", mock_client), patch(
            "services.vision._enrich_via_scraper", mock_enrich
        ):
            result = await extract_book_metadata(b"fake-image-bytes")

        title = raw_output.get("title")
        author = raw_output.get("author")
        has_query = title is not None or author is not None

        if has_query:
            mock_enrich.assert_called_once()
        else:
            mock_enrich.assert_not_called()


class TestEnrichmentMergePreservesOriginal:
    """
    Property 3: Enrichment merge preserves original metadata

    Enrichment never modifies extracted values.

    **Validates: Requirements 3.2**
    """

    @given(raw_output=vision_model_output(), enrichment_data=scraper_results())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @pytest.mark.asyncio
    async def test_enrichment_never_modifies_extracted_values(
        self, raw_output, enrichment_data
    ):
        """After enrichment, the original four Book_Metadata field values are
        unchanged."""
        # Ensure we have a title or author so enrichment triggers
        assume(raw_output.get("title") is not None or raw_output.get("author") is not None)

        mock_client = AsyncMock()
        mock_client.chat.completions.create.return_value = make_openai_response(
            raw_output
        )

        mock_enrich = AsyncMock(return_value=(enrichment_data, True))

        with patch("services.vision.client", mock_client), patch(
            "services.vision._enrich_via_scraper", mock_enrich
        ):
            result = await extract_book_metadata(b"fake-image-bytes")

        # Original metadata values must be preserved exactly
        for key in BOOK_METADATA_KEYS:
            expected = raw_output.get(key)
            assert (
                result[key] == expected
            ), f"Key '{key}' was modified: expected {expected!r}, got {result[key]!r}"


class TestGracefulDegradationOnScraperFailure:
    """
    Property 4: Graceful degradation on scraper failure

    On any scraper error, response contains original metadata with enriched=false.

    **Validates: Requirements 3.3**
    """

    @given(raw_output=vision_model_output())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @pytest.mark.asyncio
    async def test_scraper_failure_returns_metadata_with_enriched_false(
        self, raw_output
    ):
        """When scraper fails, response still contains original metadata,
        enriched is false, and enrichment is null."""
        # Ensure enrichment is triggered
        assume(raw_output.get("title") is not None or raw_output.get("author") is not None)

        mock_client = AsyncMock()
        mock_client.chat.completions.create.return_value = make_openai_response(
            raw_output
        )

        # Simulate scraper failure — returns (None, False)
        mock_enrich = AsyncMock(return_value=(None, False))

        with patch("services.vision.client", mock_client), patch(
            "services.vision._enrich_via_scraper", mock_enrich
        ):
            result = await extract_book_metadata(b"fake-image-bytes")

        # Original metadata preserved
        for key in BOOK_METADATA_KEYS:
            expected = raw_output.get(key)
            assert result[key] == expected

        # Enrichment flags indicate failure
        assert result["enriched"] is False
        assert result["enrichment"] is None


class TestEnrichmentStatusAccuracy:
    """
    Property 5: Enrichment status accuracy

    enriched is true if and only if scraper was called and succeeded.

    **Validates: Requirements 3.5**
    """

    @given(
        raw_output=vision_model_output(),
        scraper_succeeds=st.booleans(),
        enrichment_data=scraper_results(),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @pytest.mark.asyncio
    async def test_enriched_true_iff_scraper_called_and_succeeded(
        self, raw_output, scraper_succeeds, enrichment_data
    ):
        """enriched field is true if and only if the scraper was called and
        returned a successful response."""
        mock_client = AsyncMock()
        mock_client.chat.completions.create.return_value = make_openai_response(
            raw_output
        )

        title = raw_output.get("title")
        author = raw_output.get("author")
        has_query = title is not None or author is not None

        if scraper_succeeds:
            mock_enrich = AsyncMock(return_value=(enrichment_data, True))
        else:
            mock_enrich = AsyncMock(return_value=(None, False))

        with patch("services.vision.client", mock_client), patch(
            "services.vision._enrich_via_scraper", mock_enrich
        ):
            result = await extract_book_metadata(b"fake-image-bytes")

        if has_query and scraper_succeeds:
            assert result["enriched"] is True
            assert result["enrichment"] == enrichment_data
        else:
            assert result["enriched"] is False
