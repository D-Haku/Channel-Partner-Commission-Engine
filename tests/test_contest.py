"""Unit tests for the ContestModule class."""

from decimal import Decimal

import pandas as pd
import pytest

from commission_engine.config_loader import ContestDefinition
from commission_engine.contest import ContestModule
from commission_engine.models import ContestResult


# --- Fixtures ---


def _make_partners(partner_ids: list[str]) -> pd.DataFrame:
    """Create a minimal partners DataFrame."""
    return pd.DataFrame({"partner_id": partner_ids})


def _make_disbursements(records: list[dict]) -> pd.DataFrame:
    """Create a disbursements DataFrame from a list of dicts."""
    if not records:
        return pd.DataFrame(
            columns=["partner_id", "loan_product", "disbursed_amount", "disbursement_date"]
        )
    return pd.DataFrame(records)


def _monthly_pl_contest() -> ContestDefinition:
    """Monthly PL volume contest: 10+ disbursements → fixed 5000."""
    return ContestDefinition(
        id="MONTHLY_PL_VOLUME",
        type="monthly",
        qualification_rule={
            "metric": "disbursement_count",
            "product": "PL",
            "operator": "gte",
            "threshold": 10,
        },
        payout={"type": "fixed", "amount": 5000},
    )


def _quarterly_revenue_contest() -> ContestDefinition:
    """Quarterly revenue contest: total >= 50M → 5% payout."""
    return ContestDefinition(
        id="QUARTERLY_REVENUE",
        type="quarterly",
        qualification_rule={
            "metric": "total_disbursed_amount",
            "product": "ALL",
            "operator": "gte",
            "threshold": 50000000,
        },
        payout={"type": "percentage", "rate": 0.05, "basis": "total_disbursed_amount"},
    )


# --- Tests: Basic qualification ---


class TestContestModuleMonthly:
    """Tests for monthly contest evaluation."""

    def test_partner_qualifies_monthly_contest(self):
        """Partner with 10+ PL disbursements in the cycle month qualifies."""
        contest = _monthly_pl_contest()
        module = ContestModule([contest])

        partners = _make_partners(["P001"])
        # 12 PL disbursements in January 2024
        records = [
            {
                "partner_id": "P001",
                "loan_product": "PL",
                "disbursed_amount": 100000,
                "disbursement_date": f"2024-01-{15 + i:02d}",
            }
            for i in range(12)
        ]
        disbursements = _make_disbursements(records)

        results = module.evaluate(disbursements, partners, "2024-01")

        assert len(results) == 1
        assert results[0].partner_id == "P001"
        assert results[0].contest_id == "MONTHLY_PL_VOLUME"
        assert results[0].qualified is True
        assert results[0].payout == Decimal("5000")

    def test_partner_does_not_qualify_monthly_contest(self):
        """Partner with fewer than 10 PL disbursements does not qualify."""
        contest = _monthly_pl_contest()
        module = ContestModule([contest])

        partners = _make_partners(["P001"])
        # Only 5 PL disbursements in January
        records = [
            {
                "partner_id": "P001",
                "loan_product": "PL",
                "disbursed_amount": 100000,
                "disbursement_date": f"2024-01-{10 + i:02d}",
            }
            for i in range(5)
        ]
        disbursements = _make_disbursements(records)

        results = module.evaluate(disbursements, partners, "2024-01")

        assert len(results) == 1
        assert results[0].qualified is False
        assert results[0].payout == Decimal("0")

    def test_monthly_contest_filters_by_product(self):
        """Only PL disbursements count toward PL volume contest."""
        contest = _monthly_pl_contest()
        module = ContestModule([contest])

        partners = _make_partners(["P001"])
        # 8 PL + 5 HL disbursements — should not qualify (only 8 PL)
        records = [
            {
                "partner_id": "P001",
                "loan_product": "PL",
                "disbursed_amount": 100000,
                "disbursement_date": f"2024-01-{10 + i:02d}",
            }
            for i in range(8)
        ] + [
            {
                "partner_id": "P001",
                "loan_product": "HL",
                "disbursed_amount": 500000,
                "disbursement_date": f"2024-01-{10 + i:02d}",
            }
            for i in range(5)
        ]
        disbursements = _make_disbursements(records)

        results = module.evaluate(disbursements, partners, "2024-01")

        assert results[0].qualified is False
        assert results[0].payout == Decimal("0")

    def test_monthly_contest_filters_by_month(self):
        """Only disbursements in the cycle month count."""
        contest = _monthly_pl_contest()
        module = ContestModule([contest])

        partners = _make_partners(["P001"])
        # 15 PL disbursements but in February, not January
        records = [
            {
                "partner_id": "P001",
                "loan_product": "PL",
                "disbursed_amount": 100000,
                "disbursement_date": f"2024-02-{10 + i:02d}",
            }
            for i in range(15)
        ]
        disbursements = _make_disbursements(records)

        results = module.evaluate(disbursements, partners, "2024-01")

        assert results[0].qualified is False
        assert results[0].payout == Decimal("0")


class TestContestModuleQuarterly:
    """Tests for quarterly contest evaluation."""

    def test_partner_qualifies_quarterly_contest(self):
        """Partner with total disbursed >= 50M in the quarter qualifies."""
        contest = _quarterly_revenue_contest()
        module = ContestModule([contest])

        partners = _make_partners(["P001"])
        # 10 disbursements of 6M each = 60M total in Q1
        records = [
            {
                "partner_id": "P001",
                "loan_product": "HL",
                "disbursed_amount": 6000000,
                "disbursement_date": f"2024-0{(i % 3) + 1}-15",
            }
            for i in range(10)
        ]
        disbursements = _make_disbursements(records)

        results = module.evaluate(disbursements, partners, "2024-02")

        assert len(results) == 1
        assert results[0].qualified is True
        # Payout = 0.05 * 60000000 = 3000000
        assert results[0].payout == Decimal("3000000.0")

    def test_partner_does_not_qualify_quarterly_contest(self):
        """Partner with total < 50M in the quarter does not qualify."""
        contest = _quarterly_revenue_contest()
        module = ContestModule([contest])

        partners = _make_partners(["P001"])
        # 5 disbursements of 5M each = 25M total (below 50M)
        records = [
            {
                "partner_id": "P001",
                "loan_product": "PL",
                "disbursed_amount": 5000000,
                "disbursement_date": "2024-01-15",
            }
            for _ in range(5)
        ]
        disbursements = _make_disbursements(records)

        results = module.evaluate(disbursements, partners, "2024-01")

        assert results[0].qualified is False
        assert results[0].payout == Decimal("0")

    def test_quarterly_contest_includes_all_quarter_months(self):
        """Q1 contest includes Jan, Feb, and Mar disbursements."""
        contest = _quarterly_revenue_contest()
        module = ContestModule([contest])

        partners = _make_partners(["P001"])
        # Spread across Jan, Feb, Mar: 20M each = 60M total
        records = [
            {
                "partner_id": "P001",
                "loan_product": "PL",
                "disbursed_amount": 20000000,
                "disbursement_date": f"2024-0{m}-15",
            }
            for m in [1, 2, 3]
        ]
        disbursements = _make_disbursements(records)

        # Cycle is any month in Q1
        results = module.evaluate(disbursements, partners, "2024-03")

        assert results[0].qualified is True

    def test_quarterly_contest_excludes_other_quarter(self):
        """Q1 contest excludes Q2 disbursements."""
        contest = _quarterly_revenue_contest()
        module = ContestModule([contest])

        partners = _make_partners(["P001"])
        # All disbursements in April (Q2), evaluating for cycle 2024-01 (Q1)
        records = [
            {
                "partner_id": "P001",
                "loan_product": "PL",
                "disbursed_amount": 60000000,
                "disbursement_date": "2024-04-15",
            }
        ]
        disbursements = _make_disbursements(records)

        results = module.evaluate(disbursements, partners, "2024-01")

        assert results[0].qualified is False


class TestContestModuleMultiplePartners:
    """Tests for multiple partner evaluation."""

    def test_multiple_partners_mixed_qualification(self):
        """Some partners qualify while others don't."""
        contest = _monthly_pl_contest()
        module = ContestModule([contest])

        partners = _make_partners(["P001", "P002", "P003"])

        records = (
            # P001: 11 PL disbursements → qualifies
            [
                {
                    "partner_id": "P001",
                    "loan_product": "PL",
                    "disbursed_amount": 100000,
                    "disbursement_date": f"2024-01-{10 + i:02d}",
                }
                for i in range(11)
            ]
            # P002: 3 PL disbursements → does not qualify
            + [
                {
                    "partner_id": "P002",
                    "loan_product": "PL",
                    "disbursed_amount": 200000,
                    "disbursement_date": f"2024-01-{10 + i:02d}",
                }
                for i in range(3)
            ]
            # P003: 10 PL disbursements → qualifies (exactly at threshold)
            + [
                {
                    "partner_id": "P003",
                    "loan_product": "PL",
                    "disbursed_amount": 150000,
                    "disbursement_date": f"2024-01-{10 + i:02d}",
                }
                for i in range(10)
            ]
        )
        disbursements = _make_disbursements(records)

        results = module.evaluate(disbursements, partners, "2024-01")

        result_map = {r.partner_id: r for r in results}
        assert result_map["P001"].qualified is True
        assert result_map["P001"].payout == Decimal("5000")
        assert result_map["P002"].qualified is False
        assert result_map["P002"].payout == Decimal("0")
        assert result_map["P003"].qualified is True
        assert result_map["P003"].payout == Decimal("5000")


class TestContestModuleMultipleContests:
    """Tests for evaluating multiple contests simultaneously."""

    def test_evaluates_all_configured_contests(self):
        """Module evaluates every configured contest for each partner."""
        monthly = _monthly_pl_contest()
        quarterly = _quarterly_revenue_contest()
        module = ContestModule([monthly, quarterly])

        partners = _make_partners(["P001"])
        # 12 PL disbursements of 5M each = 60M in January
        records = [
            {
                "partner_id": "P001",
                "loan_product": "PL",
                "disbursed_amount": 5000000,
                "disbursement_date": f"2024-01-{10 + i:02d}",
            }
            for i in range(12)
        ]
        disbursements = _make_disbursements(records)

        results = module.evaluate(disbursements, partners, "2024-01")

        # Should have 2 results: one per contest
        assert len(results) == 2
        result_map = {r.contest_id: r for r in results}

        # Monthly PL: 12 disbursements >= 10 → qualifies
        assert result_map["MONTHLY_PL_VOLUME"].qualified is True
        assert result_map["MONTHLY_PL_VOLUME"].payout == Decimal("5000")

        # Quarterly Revenue: 60M >= 50M → qualifies
        assert result_map["QUARTERLY_REVENUE"].qualified is True
        # 0.05 * 60000000 = 3000000
        assert result_map["QUARTERLY_REVENUE"].payout == Decimal("3000000.0")


class TestContestModuleEdgeCases:
    """Edge case tests."""

    def test_empty_disbursements(self):
        """No disbursements means no one qualifies."""
        contest = _monthly_pl_contest()
        module = ContestModule([contest])

        partners = _make_partners(["P001"])
        disbursements = _make_disbursements([])

        results = module.evaluate(disbursements, partners, "2024-01")

        assert len(results) == 1
        assert results[0].qualified is False
        assert results[0].payout == Decimal("0")

    def test_no_contests_configured(self):
        """No contests configured produces no results."""
        module = ContestModule([])

        partners = _make_partners(["P001"])
        records = [
            {
                "partner_id": "P001",
                "loan_product": "PL",
                "disbursed_amount": 100000,
                "disbursement_date": "2024-01-15",
            }
        ]
        disbursements = _make_disbursements(records)

        results = module.evaluate(disbursements, partners, "2024-01")
        assert results == []

    def test_product_all_includes_all_products(self):
        """Contest with product=ALL counts all loan products."""
        contest = ContestDefinition(
            id="ALL_PRODUCT_COUNT",
            type="monthly",
            qualification_rule={
                "metric": "disbursement_count",
                "product": "ALL",
                "operator": "gte",
                "threshold": 5,
            },
            payout={"type": "fixed", "amount": 1000},
        )
        module = ContestModule([contest])

        partners = _make_partners(["P001"])
        # Mix of products totaling 6 disbursements
        records = [
            {"partner_id": "P001", "loan_product": "PL", "disbursed_amount": 100000, "disbursement_date": "2024-01-10"},
            {"partner_id": "P001", "loan_product": "HL", "disbursed_amount": 500000, "disbursement_date": "2024-01-11"},
            {"partner_id": "P001", "loan_product": "MSME", "disbursed_amount": 200000, "disbursement_date": "2024-01-12"},
            {"partner_id": "P001", "loan_product": "LAP", "disbursed_amount": 300000, "disbursement_date": "2024-01-13"},
            {"partner_id": "P001", "loan_product": "UBL", "disbursed_amount": 150000, "disbursement_date": "2024-01-14"},
            {"partner_id": "P001", "loan_product": "CSC", "disbursed_amount": 250000, "disbursement_date": "2024-01-15"},
        ]
        disbursements = _make_disbursements(records)

        results = module.evaluate(disbursements, partners, "2024-01")

        assert results[0].qualified is True
        assert results[0].payout == Decimal("1000")

    def test_gt_operator(self):
        """The 'gt' operator requires strictly greater than threshold."""
        contest = ContestDefinition(
            id="GT_TEST",
            type="monthly",
            qualification_rule={
                "metric": "disbursement_count",
                "product": "ALL",
                "operator": "gt",
                "threshold": 5,
            },
            payout={"type": "fixed", "amount": 500},
        )
        module = ContestModule([contest])

        partners = _make_partners(["P001"])
        # Exactly 5 disbursements — should NOT qualify with 'gt'
        records = [
            {
                "partner_id": "P001",
                "loan_product": "PL",
                "disbursed_amount": 100000,
                "disbursement_date": f"2024-01-{10 + i:02d}",
            }
            for i in range(5)
        ]
        disbursements = _make_disbursements(records)

        results = module.evaluate(disbursements, partners, "2024-01")

        assert results[0].qualified is False

    def test_quarter_mapping_q2(self):
        """Cycle 2024-04 maps to Q2 (Apr, May, Jun)."""
        contest = ContestDefinition(
            id="Q2_TEST",
            type="quarterly",
            qualification_rule={
                "metric": "disbursement_count",
                "product": "ALL",
                "operator": "gte",
                "threshold": 3,
            },
            payout={"type": "fixed", "amount": 2000},
        )
        module = ContestModule([contest])

        partners = _make_partners(["P001"])
        # Disbursements in Apr, May, Jun (Q2)
        records = [
            {"partner_id": "P001", "loan_product": "PL", "disbursed_amount": 100000, "disbursement_date": "2024-04-15"},
            {"partner_id": "P001", "loan_product": "PL", "disbursed_amount": 100000, "disbursement_date": "2024-05-15"},
            {"partner_id": "P001", "loan_product": "PL", "disbursed_amount": 100000, "disbursement_date": "2024-06-15"},
        ]
        disbursements = _make_disbursements(records)

        results = module.evaluate(disbursements, partners, "2024-05")

        assert results[0].qualified is True
        assert results[0].payout == Decimal("2000")

    def test_percentage_payout_uses_metric_as_basis(self):
        """Percentage payout computes rate × metric_value."""
        contest = ContestDefinition(
            id="PCT_TEST",
            type="monthly",
            qualification_rule={
                "metric": "total_disbursed_amount",
                "product": "ALL",
                "operator": "gte",
                "threshold": 1000000,
            },
            payout={"type": "percentage", "rate": 0.02, "basis": "total_disbursed_amount"},
        )
        module = ContestModule([contest])

        partners = _make_partners(["P001"])
        records = [
            {"partner_id": "P001", "loan_product": "PL", "disbursed_amount": 500000, "disbursement_date": "2024-01-10"},
            {"partner_id": "P001", "loan_product": "PL", "disbursed_amount": 700000, "disbursement_date": "2024-01-15"},
        ]
        disbursements = _make_disbursements(records)

        results = module.evaluate(disbursements, partners, "2024-01")

        assert results[0].qualified is True
        # 0.02 * 1200000 = 24000
        assert results[0].payout == Decimal("24000.0")
