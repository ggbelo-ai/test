"""Tests for the embedding pipeline."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest


class TestEmbedTexts:
    @patch("integrations.embeddings._get_client")
    def test_embed_texts_returns_correct_shape(self, mock_get_client):
        from integrations.embeddings import embed_texts

        # Mock the OpenAI response
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_embedding = MagicMock()
        mock_embedding.index = 0
        mock_embedding.embedding = [0.1] * 1536

        mock_response = MagicMock()
        mock_response.data = [mock_embedding]
        mock_client.embeddings.create.return_value = mock_response

        result = embed_texts(["test text"], dimensions=1536)
        assert result.shape == (1, 1536)
        assert result.dtype == np.float32

    def test_embed_texts_empty_input(self):
        from integrations.embeddings import embed_texts
        result = embed_texts([], dimensions=1536)
        assert result.shape == (0, 1536)

    @patch("integrations.embeddings._get_client")
    def test_embed_texts_preserves_order(self, mock_get_client):
        from integrations.embeddings import embed_texts

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Simulate out-of-order response (API can return in any order)
        emb1 = MagicMock(index=1, embedding=[0.2] * 1536)
        emb0 = MagicMock(index=0, embedding=[0.1] * 1536)

        mock_response = MagicMock()
        mock_response.data = [emb1, emb0]  # Out of order
        mock_client.embeddings.create.return_value = mock_response

        result = embed_texts(["first", "second"], dimensions=1536)
        assert result.shape == (2, 1536)
        # Should be sorted: index 0 first
        assert result[0][0] == pytest.approx(0.1)
        assert result[1][0] == pytest.approx(0.2)
