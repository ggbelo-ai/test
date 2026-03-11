"""Tests for the Semantic Scholar integration."""

from __future__ import annotations

from integrations.semantic_scholar import detect_industry_pivot, detect_publication_gap


class TestDetectPublicationGap:
    def test_no_papers(self):
        assert detect_publication_gap([]) is False

    def test_recent_papers_no_gap(self):
        papers = [{"year": 2025}, {"year": 2024}, {"year": 2023}]
        assert detect_publication_gap(papers) is False

    def test_old_papers_has_gap(self):
        papers = [{"year": 2022}, {"year": 2021}]
        # Current year is 2026, most recent is 2022 → 4-year gap
        assert detect_publication_gap(papers, gap_years=2) is True

    def test_papers_without_year(self):
        papers = [{"year": None}, {"title": "test"}]
        assert detect_publication_gap(papers) is False


class TestDetectIndustryPivot:
    def test_not_enough_papers(self):
        papers = [{"title": "A system for production", "abstract": ""}]
        assert detect_industry_pivot(papers, min_papers=3) is False

    def test_academic_papers_no_pivot(self):
        papers = [
            {"title": "Theoretical analysis of quantum states", "abstract": "Pure theory", "year": 2025},
            {"title": "Mathematical foundations of topology", "abstract": "Abstract math", "year": 2025},
            {"title": "Proof of novel theorem in algebra", "abstract": "Formal proof", "year": 2024},
        ]
        assert detect_industry_pivot(papers) is False

    def test_applied_papers_detect_pivot(self):
        papers = [
            {"title": "A scalable production system for ML", "abstract": "We deploy a framework", "year": 2025},
            {"title": "Real-world deployment of inference platform", "abstract": "Industry application", "year": 2025},
            {"title": "Building a commercial tool for NLP", "abstract": "Product launch", "year": 2024},
        ]
        assert detect_industry_pivot(papers) is True
