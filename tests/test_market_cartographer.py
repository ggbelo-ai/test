"""Tests for the Market Cartographer agent."""

from __future__ import annotations

from integrations.edgar import EdgarCompanyData, estimate_tam_from_comparables


class TestEstimateTAM:
    def test_no_revenue_data(self):
        result = estimate_tam_from_comparables([])
        assert result["tam_estimate"] is None
        assert result["tam_confidence"] == "low"
        assert result["comparable_count"] == 0

    def test_single_comparable_low_confidence(self):
        companies = [
            EdgarCompanyData(cik="123", company_name="Acme", revenue=1_000_000, revenue_year=2024)
        ]
        result = estimate_tam_from_comparables(companies)
        assert result["tam_confidence"] == "low"
        assert result["tam_estimate"] == 10_000_000  # 1M * 10x multiplier
        assert result["comparable_count"] == 1

    def test_two_comparables_medium_confidence(self):
        companies = [
            EdgarCompanyData(cik="123", company_name="Acme", revenue=1_000_000, revenue_year=2024),
            EdgarCompanyData(cik="456", company_name="Beta", revenue=2_000_000, revenue_year=2024),
        ]
        result = estimate_tam_from_comparables(companies)
        assert result["tam_confidence"] == "medium"
        assert result["tam_estimate"] == 15_000_000  # 3M * 5x multiplier

    def test_three_comparables_high_confidence(self):
        companies = [
            EdgarCompanyData(cik="1", company_name="A", revenue=1_000_000, revenue_year=2024),
            EdgarCompanyData(cik="2", company_name="B", revenue=2_000_000, revenue_year=2024),
            EdgarCompanyData(cik="3", company_name="C", revenue=3_000_000, revenue_year=2024),
        ]
        result = estimate_tam_from_comparables(companies)
        assert result["tam_confidence"] == "high"
        assert result["tam_estimate"] == 18_000_000  # 6M * 3x multiplier

    def test_companies_with_no_revenue_excluded(self):
        companies = [
            EdgarCompanyData(cik="1", company_name="A", revenue=1_000_000, revenue_year=2024),
            EdgarCompanyData(cik="2", company_name="B", revenue=None),
            EdgarCompanyData(cik="3", company_name="C", revenue=0),
        ]
        result = estimate_tam_from_comparables(companies)
        assert result["comparable_count"] == 1
        assert result["tam_confidence"] == "low"
