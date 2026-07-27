"""Unit tests for the DeductionModule."""

from decimal import Decimal

import pandas as pd
import pytest

from commission_engine.config_loader import DeductionConfig
from commission_engine.deductions import DeductionModule
from commission_engine.models import CommissionResult, DeductionResult


@pytest.fixture
def deduction_config() -> DeductionConfig:
    """Standard deduction config matching config/deductions.yaml."""
    return DeductionConfig(
        corporate_gst_rate=0.18,
        corporate_tds_rate=0.10,
        corporate_formula="net = gross + gst - tds",
        non_corporate_gst_rate=0.0,
        non_corporate_tds_rate=0.05,
        non_corporate_formula="net = gross - tds",
    )


@pytest.fixture
def partners_df() -> pd.DataFrame:
    """Partners DataFrame with mixed corporate flags."""
    return pd.DataFrame(
        {
            "partner_id": ["P001", "P002", "P003"],
            "corporate_flag": [True, False, True],
        }
    )


@pytest.fixture
def module(deduction_config: DeductionConfig) -> DeductionModule:
    """DeductionModule instance with standard config."""
    return DeductionModule(deduction_config)


class TestDeductionModuleCorporate:
    """Tests for corporate partner deductions."""

    def test_corporate_partner_gst_applied(
        self, module: DeductionModule, partners_df: pd.DataFrame
    ) -> None:
        """Corporate partner should have GST = gross * 0.18."""
        commissions = [
            CommissionResult(
                lan="LAN001",
                partner_id="P001",
                loan_product="PL",
                gross_commission=Decimal("1000.00"),
                month_allocation="2024-01",
                eligible=True,
            )
        ]
        results = module.apply(commissions, partners_df)

        assert len(results) == 1
        assert results[0].gst_amount == Decimal("180.00")

    def test_corporate_partner_tds_applied(
        self, module: DeductionModule, partners_df: pd.DataFrame
    ) -> None:
        """Corporate partner should have TDS = gross * 0.10."""
        commissions = [
            CommissionResult(
                lan="LAN001",
                partner_id="P001",
                loan_product="PL",
                gross_commission=Decimal("1000.00"),
                month_allocation="2024-01",
                eligible=True,
            )
        ]
        results = module.apply(commissions, partners_df)

        assert results[0].tds_amount == Decimal("100.00")

    def test_corporate_partner_net_formula(
        self, module: DeductionModule, partners_df: pd.DataFrame
    ) -> None:
        """Corporate net = gross + gst - tds = 1000 + 180 - 100 = 1080."""
        commissions = [
            CommissionResult(
                lan="LAN001",
                partner_id="P001",
                loan_product="PL",
                gross_commission=Decimal("1000.00"),
                month_allocation="2024-01",
                eligible=True,
            )
        ]
        results = module.apply(commissions, partners_df)

        assert results[0].net_payout == Decimal("1080.00")


class TestDeductionModuleNonCorporate:
    """Tests for non-corporate partner deductions."""

    def test_non_corporate_no_gst(
        self, module: DeductionModule, partners_df: pd.DataFrame
    ) -> None:
        """Non-corporate partner should have GST = 0."""
        commissions = [
            CommissionResult(
                lan="LAN002",
                partner_id="P002",
                loan_product="PL",
                gross_commission=Decimal("2000.00"),
                month_allocation="2024-01",
                eligible=True,
            )
        ]
        results = module.apply(commissions, partners_df)

        assert results[0].gst_amount == Decimal("0")

    def test_non_corporate_tds_applied(
        self, module: DeductionModule, partners_df: pd.DataFrame
    ) -> None:
        """Non-corporate partner should have TDS = gross * 0.05."""
        commissions = [
            CommissionResult(
                lan="LAN002",
                partner_id="P002",
                loan_product="PL",
                gross_commission=Decimal("2000.00"),
                month_allocation="2024-01",
                eligible=True,
            )
        ]
        results = module.apply(commissions, partners_df)

        assert results[0].tds_amount == Decimal("100.00")

    def test_non_corporate_net_formula(
        self, module: DeductionModule, partners_df: pd.DataFrame
    ) -> None:
        """Non-corporate net = gross - tds = 2000 - 100 = 1900."""
        commissions = [
            CommissionResult(
                lan="LAN002",
                partner_id="P002",
                loan_product="PL",
                gross_commission=Decimal("2000.00"),
                month_allocation="2024-01",
                eligible=True,
            )
        ]
        results = module.apply(commissions, partners_df)

        assert results[0].net_payout == Decimal("1900.00")


class TestDeductionModuleIneligible:
    """Tests for ineligible commissions."""

    def test_ineligible_commission_zero_deductions(
        self, module: DeductionModule, partners_df: pd.DataFrame
    ) -> None:
        """Ineligible commissions should produce zero gst, tds, and net."""
        commissions = [
            CommissionResult(
                lan="LAN003",
                partner_id="P001",
                loan_product="PL",
                gross_commission=Decimal("500.00"),
                month_allocation="2024-01",
                eligible=False,
            )
        ]
        results = module.apply(commissions, partners_df)

        assert results[0].gst_amount == Decimal("0")
        assert results[0].tds_amount == Decimal("0")
        assert results[0].net_payout == Decimal("0")

    def test_zero_gross_commission_zero_deductions(
        self, module: DeductionModule, partners_df: pd.DataFrame
    ) -> None:
        """Zero gross commission should produce zero gst, tds, and net."""
        commissions = [
            CommissionResult(
                lan="LAN004",
                partner_id="P001",
                loan_product="PL",
                gross_commission=Decimal("0"),
                month_allocation="2024-01",
                eligible=True,
            )
        ]
        results = module.apply(commissions, partners_df)

        assert results[0].gst_amount == Decimal("0")
        assert results[0].tds_amount == Decimal("0")
        assert results[0].net_payout == Decimal("0")


class TestDeductionModuleEdgeCases:
    """Edge case tests."""

    def test_empty_commissions_list(
        self, module: DeductionModule, partners_df: pd.DataFrame
    ) -> None:
        """Empty commissions list returns empty results."""
        results = module.apply([], partners_df)
        assert results == []

    def test_multiple_commissions_mixed_partners(
        self, module: DeductionModule, partners_df: pd.DataFrame
    ) -> None:
        """Multiple commissions with different partner types are handled correctly."""
        commissions = [
            CommissionResult(
                lan="LAN001",
                partner_id="P001",  # Corporate
                loan_product="PL",
                gross_commission=Decimal("1000.00"),
                month_allocation="2024-01",
                eligible=True,
            ),
            CommissionResult(
                lan="LAN002",
                partner_id="P002",  # Non-corporate
                loan_product="HL",
                gross_commission=Decimal("5000.00"),
                month_allocation="2024-01",
                eligible=True,
            ),
            CommissionResult(
                lan="LAN003",
                partner_id="P003",  # Corporate, ineligible
                loan_product="MSME",
                gross_commission=Decimal("3000.00"),
                month_allocation="2024-01",
                eligible=False,
            ),
        ]
        results = module.apply(commissions, partners_df)

        assert len(results) == 3
        # P001 corporate: net = 1000 + 180 - 100 = 1080
        assert results[0].net_payout == Decimal("1080.00")
        # P002 non-corporate: net = 5000 - 250 = 4750
        assert results[1].net_payout == Decimal("4750.00")
        assert results[1].tds_amount == Decimal("250.00")
        # P003 ineligible: all zero
        assert results[2].net_payout == Decimal("0")

    def test_unknown_partner_defaults_to_non_corporate(
        self, module: DeductionModule, partners_df: pd.DataFrame
    ) -> None:
        """Partner not in DataFrame defaults to non-corporate treatment."""
        commissions = [
            CommissionResult(
                lan="LAN099",
                partner_id="UNKNOWN",
                loan_product="PL",
                gross_commission=Decimal("1000.00"),
                month_allocation="2024-01",
                eligible=True,
            )
        ]
        results = module.apply(commissions, partners_df)

        # Should get non-corporate treatment (no gst, 5% tds)
        assert results[0].gst_amount == Decimal("0")
        assert results[0].tds_amount == Decimal("50.00")
        assert results[0].net_payout == Decimal("950.00")

    def test_rounding_to_two_decimal_places(
        self, module: DeductionModule, partners_df: pd.DataFrame
    ) -> None:
        """Amounts that produce fractional pennies are rounded to 2 decimal places."""
        commissions = [
            CommissionResult(
                lan="LAN005",
                partner_id="P001",  # Corporate
                loan_product="PL",
                gross_commission=Decimal("333.33"),
                month_allocation="2024-01",
                eligible=True,
            )
        ]
        results = module.apply(commissions, partners_df)

        # GST = 333.33 * 0.18 = 59.9994 -> rounded to 60.00
        assert results[0].gst_amount == Decimal("60.00")
        # TDS = 333.33 * 0.10 = 33.333 -> rounded to 33.33
        assert results[0].tds_amount == Decimal("33.33")
        # Net = 333.33 + 60.00 - 33.33 = 360.00
        assert results[0].net_payout == Decimal("360.00")

    def test_preserves_lan_and_partner_id(
        self, module: DeductionModule, partners_df: pd.DataFrame
    ) -> None:
        """DeductionResult preserves the original LAN and partner_id."""
        commissions = [
            CommissionResult(
                lan="LOAN-ABC-123",
                partner_id="P002",
                loan_product="HL",
                gross_commission=Decimal("10000.00"),
                month_allocation="2024-03",
                eligible=True,
            )
        ]
        results = module.apply(commissions, partners_df)

        assert results[0].lan == "LOAN-ABC-123"
        assert results[0].partner_id == "P002"
        assert results[0].gross_commission == Decimal("10000.00")
