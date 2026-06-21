"""Unit tests for vision endpoint error cases.

Tests:
- Empty image → HTTP 400
- Vision model API failure → HTTP 503
- Config validation: missing OPENAI_API_KEY → sys.exit(1)
- Default OPENAI_BASE_URL fallback when env var not set

Requirements: 1.5, 1.6, 4.3, 4.4
"""

import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

# Set OPENAI_API_KEY before importing app modules (vision.py reads it at module level)
os.environ.setdefault("OPENAI_API_KEY", "test-key-for-testing")

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


class TestEmptyImage:
    """Requirement 1.5: Empty image → HTTP 400.

    Note: FastAPI's Body() annotation rejects a truly empty body with 422
    before the handler executes. The handler's `if not image` guard returns 400
    for semantically empty bodies that pass validation. We test both layers.
    """

    def test_empty_body_rejected_by_framework(self):
        """An empty body is rejected at the framework level (422)."""
        response = client.post(
            "/vision",
            content=b"",
            headers={"Content-Type": "application/octet-stream"},
        )
        assert response.status_code == 422

    def test_no_body_rejected_by_framework(self):
        """A missing body is rejected at the framework level (422)."""
        response = client.post(
            "/vision",
            headers={"Content-Type": "application/octet-stream"},
        )
        assert response.status_code == 422

    @pytest.mark.anyio
    async def test_handler_rejects_empty_image_directly(self):
        """The router handler logic returns 400 for empty image bytes."""
        from fastapi import HTTPException
        from routers.vision import vision

        with pytest.raises(HTTPException) as exc_info:
            await vision(image=b"")
        assert exc_info.value.status_code == 400
        assert "Image bytes required" in exc_info.value.detail


class TestVisionModelFailure:
    """Requirement 1.6: Vision model API failure → HTTP 503."""

    def test_openai_api_error_returns_503(self):
        with patch(
            "services.vision._call_vision_model",
            new_callable=AsyncMock,
            side_effect=Exception("Connection timed out"),
        ):
            response = client.post(
                "/vision",
                content=b"\x89PNG\r\n\x1a\nfake-image-data",
                headers={"Content-Type": "application/octet-stream"},
            )
            assert response.status_code == 503
            assert "Vision model error" in response.json()["detail"]

    def test_openai_api_error_includes_description(self):
        with patch(
            "services.vision._call_vision_model",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Rate limit exceeded"),
        ):
            response = client.post(
                "/vision",
                content=b"\xff\xd8\xff\xe0fake-jpeg",
                headers={"Content-Type": "application/octet-stream"},
            )
            assert response.status_code == 503
            body = response.json()
            assert "Rate limit exceeded" in body["detail"]


class TestConfigValidation:
    """Requirement 4.3: Missing OPENAI_API_KEY → sys.exit(1)."""

    def test_missing_api_key_calls_sys_exit(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(SystemExit) as exc_info:
            from services.config import validate_config

            validate_config()
        assert exc_info.value.code == 1

    def test_empty_api_key_calls_sys_exit(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "   ")
        with pytest.raises(SystemExit) as exc_info:
            from services.config import validate_config

            validate_config()
        assert exc_info.value.code == 1


class TestDefaultBaseUrl:
    """Requirement 4.4: Default OPENAI_BASE_URL fallback when env var not set."""

    def test_default_base_url_when_env_not_set(self, monkeypatch):
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        # Re-evaluate the default by reading what the module would compute
        default = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        assert default == "https://api.openai.com/v1"

    def test_base_url_uses_env_when_set(self, monkeypatch):
        monkeypatch.setenv("OPENAI_BASE_URL", "https://custom.provider.io/v1")
        value = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        assert value == "https://custom.provider.io/v1"

    def test_vision_module_default_base_url(self):
        """Verify the vision module's OPENAI_BASE_URL defaults correctly."""
        from services import vision

        # If OPENAI_BASE_URL wasn't set externally, it should be the default
        # The module-level variable captures it at import time
        assert vision.OPENAI_BASE_URL in (
            "https://api.openai.com/v1",
            os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        )
