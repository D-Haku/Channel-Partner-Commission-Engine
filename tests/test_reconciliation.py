"""Unit tests for the Reconciliation Module."""

from decimal import Decimal

import pandas as pd
import pytest

from commission_engine.models import DeductionResult, Discrepancy, ReconciliationSummary
from commission_engine.reconciliation import ReconciliationModule


def _make_deduction(lan: str, net_payout: Decimal) -> DeductionResult:
    """Helper to create a DeductionResult with only lan and net_payout relevant."""
    return DeductionResult(
        lan=lan,
        partner_id="P001",
        gross_commission=Decimal("1000"),
        gst_amount=Decimal("180"),
        tds_amount=Decimal("100"),
        net_payout=net_payout,
    )


def _make_reference_df(data: dict[str, Decimal]) -> pd.DataFrame:
    """Helper to create a reference DataFrame from a lan -> amount mapping."""
    rows = [{"lan": lan, "reference_amount": float(amount)} for lan, amount in data.items()]
    return pd.DataFrame(rows, columns=["lan", "reference_amount"])


class TestReconciliationModule:
    """Tests for ReconciliationModule.reconcile()."""

    def test_all_matched_within_tolerance(self):
        """All LANs match within tolerance — all counted as matched."""
        module = ReconciliationModule(tolerance=Decimal("0.01"))
        computed = [
            _make_deduction("LAN001", Decimal("1000.00")),
            _make_deduction("LAN002", Decimal("2000.005")),
        ]
        reference = _make_reference_df(
            {"LAN001": Decimal("1000.00"), "LAN002": Decimal("2000.01")}
        )

        result = module.reconcile(computed, reference)

        assert result.matched_count == 2
        assert result.discrepancy_count == 0
        assert result.missing_computed_count == 0
        assert result.missing_reference_count == 0
        assert result.discrepancies == []

    def test_discrepancy_detected(self):
        """LANs with difference > tolerance are classified as discrepancies."""
        module = ReconciliationModule(tolerance=Decimal("0.01"))
        computed = [
            _make_deduction("LAN001", Decimal("1000.00")),
            _make_deduction("LAN002", Decimal("2000.00")),
        ]
        reference = _make_reference_df(
            {"LAN001": Decimal("1000.00"), "LAN002": Decimal("2050.00")}
        )

        result = module.reconcile(computed, reference)

        assert result.matched_count == 1
        assert result.discrepancy_count == 1
        assert len(result.discrepancies) == 1
        disc = result.discrepancies[0]
        assert disc.lan == "LAN002"
        assert disc.computed_amount == Decimal("2000.00")
        assert disc.reference_amount == Decimal("2050.00")
        assert disc.difference == Decimal("50.00")

    def test_missing_computed(self):
        """LANs only in reference are counted as missing_computed."""
        module = ReconciliationModule(tolerance=Decimal("0.01"))
        computed = [_make_deduction("LAN001", Decimal("1000.00"))]
        reference = _make_reference_df(
            {"LAN001": Decimal("1000.00"), "LAN002": Decimal("500.00")}
        )

        result = module.reconcile(computed, reference)

        assert result.matched_count == 1
        assert result.missing_computed_count == 1
        assert result.missing_reference_count == 0

    def test_missing_reference(self):
        """LANs only in computed are counted as missing_reference."""
        module = ReconciliationModule(tolerance=Decimal("0.01"))
        computed = [
            _make_deduction("LAN001", Decimal("1000.00")),
            _make_deduction("LAN002", Decimal("2000.00")),
        ]
        reference = _make_reference_df({"LAN001": Decimal("1000.00")})

        result = module.reconcile(computed, reference)

        assert result.matched_count == 1
        assert result.missing_reference_count == 1
        assert result.missing_computed_count == 0

    def test_empty_computed_list(self):
        """All reference LANs become missing_computed when computed is empty."""
        module = ReconciliationModule(tolerance=Decimal("0.01"))
        computed: list[DeductionResult] = []
        reference = _make_reference_df(
            {"LAN001": Decimal("1000.00"), "LAN002": Decimal("2000.00")}
        )

        result = module.reconcile(computed, reference)

        assert result.matched_count == 0
        assert result.discrepancy_count == 0
        assert result.missing_computed_count == 2
        assert result.missing_reference_count == 0

    def test_empty_reference(self):
        """All computed LANs become missing_reference when reference is empty."""
        module = ReconciliationModule(tolerance=Decimal("0.01"))
        computed = [
            _make_deduction("LAN001", Decimal("1000.00")),
            _make_deduction("LAN002", Decimal("2000.00")),
        ]
        reference = pd.DataFrame(columns=["lan", "reference_amount"])

        result = module.reconcile(computed, reference)

        assert result.matched_count == 0
        assert result.discrepancy_count == 0
        assert result.missing_computed_count == 0
        assert result.missing_reference_count == 2

    def test_both_empty(self):
        """Empty computed and reference yields all-zero summary."""
        module = ReconciliationModule(tolerance=Decimal("0.01"))
        computed: list[DeductionResult] = []
        reference = pd.DataFrame(columns=["lan", "reference_amount"])

        result = module.reconcile(computed, reference)

        assert result.matched_count == 0
        assert result.discrepancy_count == 0
        assert result.missing_computed_count == 0
        assert result.missing_reference_count == 0

    def test_exact_tolerance_boundary_matched(self):
        """Difference exactly equal to tolerance is classified as matched."""
        module = ReconciliationModule(tolerance=Decimal("0.50"))
        computed = [_make_deduction("LAN001", Decimal("100.00"))]
        reference = _make_reference_df({"LAN001": Decimal("100.50")})

        result = module.reconcile(computed, reference)

        assert result.matched_count == 1
        assert result.discrepancy_count == 0

    def test_just_over_tolerance_is_discrepancy(self):
        """Difference just over tolerance is classified as discrepancy."""
        module = ReconciliationModule(tolerance=Decimal("0.50"))
        computed = [_make_deduction("LAN001", Decimal("100.00"))]
        reference = _make_reference_df({"LAN001": Decimal("100.51")})

        result = module.reconcile(computed, reference)

        assert result.matched_count == 0
        assert result.discrepancy_count == 1

    def test_count_invariant(self):
        """matched + discrepancy + missing_computed + missing_reference == total unique LANs."""
        module = ReconciliationModule(tolerance=Decimal("0.01"))
        computed = [
            _make_deduction("LAN001", Decimal("1000.00")),
            _make_deduction("LAN002", Decimal("2000.00")),
            _make_deduction("LAN003", Decimal("3000.00")),
        ]
        reference = _make_reference_df(
            {
                "LAN001": Decimal("1000.00"),  # matched
                "LAN002": Decimal("2500.00"),  # discrepancy
                "LAN004": Decimal("4000.00"),  # missing_computed
            }
        )

        result = module.reconcile(computed, reference)

        total_lans = len({"LAN001", "LAN002", "LAN003", "LAN004"})
        assert (
            result.matched_count
            + result.discrepancy_count
            + result.missing_computed_count
            + result.missing_reference_count
        ) == total_lans

    def test_zero_tolerance(self):
        """With zero tolerance, only exact matches are classified as matched."""
        module = ReconciliationModule(tolerance=Decimal("0"))
        computed = [
            _make_deduction("LAN001", Decimal("1000.00")),
            _make_deduction("LAN002", Decimal("2000.001")),
        ]
        reference = _make_reference_df(
            {"LAN001": Decimal("1000.00"), "LAN002": Decimal("2000.00")}
        )

        result = module.reconcile(computed, reference)

        assert result.matched_count == 1
        assert result.discrepancy_count == 1
