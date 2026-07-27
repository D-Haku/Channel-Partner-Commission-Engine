"""Unit tests for the Commission Calculator module."""

from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from commission_engine.calculator import CommissionCalculator
from commission_engine.config_loader import (
    EligibilityRule,
    LoanSequenceTier,
    PayoutSlab,
    SequenceRules,
    SlabConfig,
)


@pytest.fixture
def pl_slab_config():
    """PL slab config for testing."""
    return SlabConfig(
        product="PL",
        slab_basis="disbursed_amount",
        slabs=[
            PayoutSlab(min=0, max=500000, rate_type="percentage", rate=0.50),
            PayoutSlab(min=500001, max=1500000, rate_type="percentage", rate=0.75),
            PayoutSlab(min=1500001, max=None, rate_type="percentage", rate=1.00),
        ],
        sequence_rules=SequenceRules(
            first_disbursement_multiplier=1.0,
            subsequent_disbursement_multiplier=0.5,
        ),
        loan_sequence_tiers=[
            LoanSequenceTier(sequence_min=1, sequence_max=5, rate_adjustment=0.0),
            LoanSequenceTier(sequence_min=6, sequence_max=None, rate_adjustment=-0.10),
        ],
    )


@pytest.fixture
def pl_prime_slab_config():
    """PL_PRIME slab config for testing."""
    return SlabConfig(
        product="PL_PRIME",
        slab_basis="disbursed_amount",
        slabs=[
            PayoutSlab(min=0, max=500000, rate_type="percentage", rate=0.60),
            PayoutSlab(min=500001, max=1500000, rate_type="percentage", rate=0.90),
            PayoutSlab(min=1500001, max=None, rate_type="percentage", rate=1.20),
        ],
        sequence_rules=SequenceRules(
            first_disbursement_multiplier=1.0,
            subsequent_disbursement_multiplier=0.5,
        ),
        loan_sequence_tiers=[
            LoanSequenceTier(sequence_min=1, sequence_max=3, rate_adjustment=0.0),
            LoanSequenceTier(sequence_min=4, sequence_max=7, rate_adjustment=0.05),
            LoanSequenceTier(sequence_min=8, sequence_max=None, rate_adjustment=0.10),
        ],
    )


@pytest.fixture
def sample_slab_config(pl_slab_config, pl_prime_slab_config):
    """Combined slab config with PL and PL_PRIME."""
    return {"PL": pl_slab_config, "PL_PRIME": pl_prime_slab_config}


@pytest.fixture
def eligibility_rules():
    """Standard eligibility rules for testing."""
    return [
        EligibilityRule(
            id="MIN_DISBURSEMENT",
            description="Minimum disbursement amount",
            product="ALL",
            field="disbursed_amount",
            operator="gte",
            value=10000,
        ),
        EligibilityRule(
            id="ACTIVE_PARTNER",
            description="Partner must be active",
            product="ALL",
            field="partner_active",
            operator="eq",
            value=True,
        ),
        EligibilityRule(
            id="HL_MIN_AMOUNT",
            description="Home Loan minimum amount",
            product="HL",
            field="disbursed_amount",
            operator="gte",
            value=500000,
        ),
    ]


@pytest.fixture
def allocation_rules():
    """Standard allocation rules mapping product to date field."""
    return {
        "PL": "disbursement_date",
        "HL": "cheque_handover_date",
        "MSME": "disbursement_date",
        "LAP": "cheque_handover_date",
        "UBL": "disbursement_date",
        "CSC": "disbursement_date",
        "PL_PRIME": "disbursement_date",
    }


@pytest.fixture
def calculator(sample_slab_config, eligibility_rules, allocation_rules):
    """Create a CommissionCalculator instance for testing."""
    return CommissionCalculator(
        slab_config=sample_slab_config,
        eligibility_rules=eligibility_rules,
        allocation_rules=allocation_rules,
    )


# ============================================================
# Task 6.1: Slab Lookup and Gross Commission Computation
# ============================================================


class TestLookupSlab:
    """Tests for CommissionCalculator.lookup_slab."""

    def test_matches_first_slab_lower_boundary(self, calculator):
        """Value at lower boundary of first slab matches."""
        slab = calculator.lookup_slab("PL", Decimal("0"))
        assert slab is not None
        assert slab.rate == 0.50

    def test_matches_first_slab_upper_boundary(self, calculator):
        """Value at upper boundary of first slab matches."""
        slab = calculator.lookup_slab("PL", Decimal("500000"))
        assert slab is not None
        assert slab.rate == 0.50

    def test_matches_second_slab_lower_boundary(self, calculator):
        """Value at lower boundary of second slab matches."""
        slab = calculator.lookup_slab("PL", Decimal("500001"))
        assert slab is not None
        assert slab.rate == 0.75

    def test_matches_unbounded_upper_slab(self, calculator):
        """Value in unbounded upper slab (max=None) matches."""
        slab = calculator.lookup_slab("PL", Decimal("5000000"))
        assert slab is not None
        assert slab.rate == 1.00

    def test_no_match_unknown_product(self, calculator):
        """Unknown product returns None."""
        slab = calculator.lookup_slab("UNKNOWN", Decimal("100000"))
        assert slab is None

    def test_mid_range_value(self, calculator):
        """Value in middle of a slab range matches correctly."""
        slab = calculator.lookup_slab("PL", Decimal("750000"))
        assert slab is not None
        assert slab.rate == 0.75


class TestComputeGrossCommission:
    """Tests for CommissionCalculator.compute_gross_commission."""

    def test_basic_commission_first_disbursement(self, calculator):
        """First disbursement in low sequence: rate * 1.0 + 0.0 adjustment."""
        # PL, 200000 -> slab rate 0.50%, first disbursement (mult=1.0), loan_seq=1 (adj=0.0)
        # final_rate = 0.50 * 1.0 + 0.0 = 0.50
        # gross = 200000 * 0.50 / 100 = 1000
        gross, flags = calculator.compute_gross_commission("PL", Decimal("200000"), 1, 1)
        assert gross == Decimal("200000") * Decimal("0.50") / Decimal("100")
        assert flags == []

    def test_subsequent_disbursement_applies_multiplier(self, calculator):
        """Subsequent disbursement (seq=2) applies 0.5 multiplier."""
        # PL, 200000 -> slab rate 0.50%, subsequent (mult=0.5), loan_seq=1 (adj=0.0)
        # final_rate = 0.50 * 0.5 + 0.0 = 0.25
        # gross = 200000 * 0.25 / 100 = 500
        gross, flags = calculator.compute_gross_commission("PL", Decimal("200000"), 2, 1)
        expected = Decimal("200000") * Decimal("0.25") / Decimal("100")
        assert gross == expected
        assert flags == []

    def test_loan_sequence_tier_adjustment(self, calculator):
        """High loan sequence (>=6) applies -0.10 rate adjustment."""
        # PL, 200000 -> slab rate 0.50%, first (mult=1.0), loan_seq=6 (adj=-0.10)
        # final_rate = 0.50 * 1.0 + (-0.10) = 0.40
        # gross = 200000 * 0.40 / 100 = 800
        gross, flags = calculator.compute_gross_commission("PL", Decimal("200000"), 1, 6)
        expected = Decimal("200000") * Decimal("0.40") / Decimal("100")
        assert gross == expected
        assert flags == []

    def test_combined_subsequent_and_tier_adjustment(self, calculator):
        """Subsequent disbursement + high loan sequence applies both."""
        # PL, 200000 -> slab rate 0.50%, subsequent (mult=0.5), loan_seq=6 (adj=-0.10)
        # final_rate = 0.50 * 0.5 + (-0.10) = 0.15
        # gross = 200000 * 0.15 / 100 = 300
        gross, flags = calculator.compute_gross_commission("PL", Decimal("200000"), 2, 6)
        expected = Decimal("200000") * Decimal("0.15") / Decimal("100")
        assert gross == expected
        assert flags == []

    def test_slab_miss_returns_zero_with_flag(self, calculator):
        """No matching slab returns zero and 'slab_miss' flag."""
        gross, flags = calculator.compute_gross_commission("UNKNOWN", Decimal("100000"), 1, 1)
        assert gross == Decimal("0")
        assert "slab_miss" in flags

    def test_unbounded_slab_commission(self, calculator):
        """Commission from unbounded upper slab computes correctly."""
        # PL, 2000000 -> slab rate 1.00%, first (mult=1.0), loan_seq=1 (adj=0.0)
        # final_rate = 1.00 * 1.0 + 0.0 = 1.00
        # gross = 2000000 * 1.00 / 100 = 20000
        gross, flags = calculator.compute_gross_commission("PL", Decimal("2000000"), 1, 1)
        expected = Decimal("2000000") * Decimal("1.00") / Decimal("100")
        assert gross == expected
        assert flags == []


# ============================================================
# Task 6.2: Sequence Determination and Rate Adjustment
# ============================================================


class TestDetermineSequence:
    """Tests for CommissionCalculator.determine_sequence."""

    def test_assigns_loan_sequence_by_first_appearance(self, calculator):
        """Each unique LAN gets a sequence number in order of first appearance."""
        disbursements = pd.DataFrame({
            "partner_id": ["P1", "P1", "P1", "P1"],
            "lan": ["LAN_A", "LAN_B", "LAN_A", "LAN_C"],
            "disbursement_date": [
                date(2024, 1, 1),
                date(2024, 1, 5),
                date(2024, 1, 10),
                date(2024, 1, 15),
            ],
            "disbursement_sequence": [1, 1, 2, 1],
        })
        result = calculator.determine_sequence("P1", disbursements)
        assert list(result["loan_sequence"]) == [1, 2, 1, 3]

    def test_filters_to_specific_partner(self, calculator):
        """Only the specified partner's disbursements are returned."""
        disbursements = pd.DataFrame({
            "partner_id": ["P1", "P2", "P1"],
            "lan": ["LAN_A", "LAN_B", "LAN_C"],
            "disbursement_date": [
                date(2024, 1, 1),
                date(2024, 1, 2),
                date(2024, 1, 3),
            ],
            "disbursement_sequence": [1, 1, 1],
        })
        result = calculator.determine_sequence("P1", disbursements)
        assert len(result) == 2
        assert list(result["partner_id"]) == ["P1", "P1"]

    def test_empty_partner_returns_empty_df(self, calculator):
        """Partner with no disbursements returns empty DataFrame."""
        disbursements = pd.DataFrame({
            "partner_id": ["P2"],
            "lan": ["LAN_A"],
            "disbursement_date": [date(2024, 1, 1)],
            "disbursement_sequence": [1],
        })
        result = calculator.determine_sequence("P1", disbursements)
        assert len(result) == 0


class TestSequenceMultiplier:
    """Tests for get_sequence_multiplier."""

    def test_first_disbursement_multiplier(self, calculator):
        """First disbursement (sequence=1) gets first_disbursement_multiplier."""
        mult = calculator.get_sequence_multiplier("PL", 1)
        assert mult == Decimal("1.0")

    def test_subsequent_disbursement_multiplier(self, calculator):
        """Subsequent disbursement (sequence>1) gets subsequent_disbursement_multiplier."""
        mult = calculator.get_sequence_multiplier("PL", 2)
        assert mult == Decimal("0.5")

    def test_unknown_product_returns_one(self, calculator):
        """Unknown product returns multiplier of 1."""
        mult = calculator.get_sequence_multiplier("UNKNOWN", 1)
        assert mult == Decimal("1")


class TestLoanSequenceAdjustment:
    """Tests for get_loan_sequence_adjustment."""

    def test_first_tier_no_adjustment(self, calculator):
        """Loan sequence 1-5 for PL has 0.0 adjustment."""
        adj = calculator.get_loan_sequence_adjustment("PL", 3)
        assert adj == Decimal("0.0")

    def test_second_tier_negative_adjustment(self, calculator):
        """Loan sequence >= 6 for PL has -0.10 adjustment."""
        adj = calculator.get_loan_sequence_adjustment("PL", 6)
        assert adj == Decimal("-0.10")

    def test_unbounded_tier(self, calculator):
        """Very high loan sequence still matches unbounded tier."""
        adj = calculator.get_loan_sequence_adjustment("PL", 100)
        assert adj == Decimal("-0.10")

    def test_unknown_product_returns_zero(self, calculator):
        """Unknown product returns 0 adjustment."""
        adj = calculator.get_loan_sequence_adjustment("UNKNOWN", 1)
        assert adj == Decimal("0")


# ============================================================
# Task 6.3: Eligibility Check Logic
# ============================================================


class TestCheckEligibility:
    """Tests for CommissionCalculator.check_eligibility."""

    def test_all_rules_pass(self, calculator):
        """Disbursement meeting all criteria returns (True, None)."""
        disbursement = {"loan_product": "PL", "disbursed_amount": 50000}
        partner = {"active": True}
        eligible, failed_rule = calculator.check_eligibility(disbursement, partner)
        assert eligible is True
        assert failed_rule is None

    def test_fails_on_min_disbursement(self, calculator):
        """Disbursement below minimum amount fails with rule id."""
        disbursement = {"loan_product": "PL", "disbursed_amount": 5000}
        partner = {"active": True}
        eligible, failed_rule = calculator.check_eligibility(disbursement, partner)
        assert eligible is False
        assert failed_rule == "MIN_DISBURSEMENT"

    def test_fails_on_inactive_partner(self, calculator):
        """Inactive partner fails ACTIVE_PARTNER rule."""
        disbursement = {"loan_product": "PL", "disbursed_amount": 50000}
        partner = {"active": False}
        eligible, failed_rule = calculator.check_eligibility(disbursement, partner)
        assert eligible is False
        assert failed_rule == "ACTIVE_PARTNER"

    def test_product_specific_rule_applies(self, calculator):
        """HL-specific rule applies only to HL products."""
        # HL with 400000 fails HL_MIN_AMOUNT (needs >= 500000)
        disbursement = {"loan_product": "HL", "disbursed_amount": 400000}
        partner = {"active": True}
        eligible, failed_rule = calculator.check_eligibility(disbursement, partner)
        assert eligible is False
        assert failed_rule == "HL_MIN_AMOUNT"

    def test_product_specific_rule_does_not_apply_to_other_products(self, calculator):
        """HL-specific rule does NOT apply to PL products."""
        # PL with 400000 should pass (HL_MIN_AMOUNT doesn't apply)
        disbursement = {"loan_product": "PL", "disbursed_amount": 400000}
        partner = {"active": True}
        eligible, failed_rule = calculator.check_eligibility(disbursement, partner)
        assert eligible is True
        assert failed_rule is None

    def test_first_failing_rule_returned(self, calculator):
        """Returns the first failing rule id when multiple rules fail."""
        # Amount below min and partner inactive - MIN_DISBURSEMENT checked first
        disbursement = {"loan_product": "PL", "disbursed_amount": 5000}
        partner = {"active": False}
        eligible, failed_rule = calculator.check_eligibility(disbursement, partner)
        assert eligible is False
        assert failed_rule == "MIN_DISBURSEMENT"

    def test_missing_field_fails_rule(self, calculator):
        """Missing required field causes rule failure."""
        disbursement = {"loan_product": "PL"}  # no disbursed_amount
        partner = {"active": True}
        eligible, failed_rule = calculator.check_eligibility(disbursement, partner)
        assert eligible is False
        assert failed_rule == "MIN_DISBURSEMENT"


# ============================================================
# Task 6.4: Month Allocation Logic
# ============================================================


class TestAllocateMonth:
    """Tests for CommissionCalculator.allocate_month."""

    def test_disbursement_date_allocation(self, calculator):
        """PL uses disbursement_date for month allocation."""
        disbursement = {
            "loan_product": "PL",
            "disbursement_date": date(2024, 3, 15),
            "cheque_handover_date": date(2024, 2, 20),
        }
        result = calculator.allocate_month(disbursement)
        assert result == "2024-03"

    def test_cheque_handover_date_allocation(self, calculator):
        """HL uses cheque_handover_date for month allocation."""
        disbursement = {
            "loan_product": "HL",
            "disbursement_date": date(2024, 3, 15),
            "cheque_handover_date": date(2024, 2, 20),
        }
        result = calculator.allocate_month(disbursement)
        assert result == "2024-02"

    def test_missing_disbursement_date_returns_none(self, calculator):
        """Missing disbursement_date returns None."""
        disbursement = {
            "loan_product": "PL",
            "disbursement_date": None,
        }
        result = calculator.allocate_month(disbursement)
        assert result is None

    def test_missing_cheque_handover_date_returns_none(self, calculator):
        """Missing cheque_handover_date returns None when required."""
        disbursement = {
            "loan_product": "HL",
            "cheque_handover_date": None,
            "disbursement_date": date(2024, 3, 15),
        }
        result = calculator.allocate_month(disbursement)
        assert result is None

    def test_default_rule_uses_disbursement_date(self, calculator):
        """Product without explicit allocation rule defaults to disbursement_date."""
        disbursement = {
            "loan_product": "NEW_PRODUCT",
            "disbursement_date": date(2024, 6, 1),
        }
        result = calculator.allocate_month(disbursement)
        assert result == "2024-06"

    def test_pandas_nat_returns_none(self, calculator):
        """Pandas NaT value returns None."""
        disbursement = {
            "loan_product": "PL",
            "disbursement_date": pd.NaT,
        }
        result = calculator.allocate_month(disbursement)
        assert result is None


# ============================================================
# Task 6.5: PL Prime Commission Logic
# ============================================================


class TestPLPrime:
    """Tests for PL Prime detection and effective product routing."""

    def test_is_pl_prime_true(self, calculator):
        """Disbursement with is_pl_prime=True is detected."""
        disbursement = {"loan_product": "PL", "is_pl_prime": True}
        assert calculator.is_pl_prime(disbursement) is True

    def test_is_pl_prime_false(self, calculator):
        """Disbursement without is_pl_prime is not PL Prime."""
        disbursement = {"loan_product": "PL", "is_pl_prime": False}
        assert calculator.is_pl_prime(disbursement) is False

    def test_is_pl_prime_missing_key(self, calculator):
        """Disbursement without is_pl_prime key is not PL Prime."""
        disbursement = {"loan_product": "PL"}
        assert calculator.is_pl_prime(disbursement) is False

    def test_effective_product_pl_prime(self, calculator):
        """PL with is_pl_prime=True returns 'PL_PRIME'."""
        disbursement = {"loan_product": "PL", "is_pl_prime": True}
        assert calculator.get_effective_product(disbursement) == "PL_PRIME"

    def test_effective_product_regular_pl(self, calculator):
        """PL without is_pl_prime returns 'PL'."""
        disbursement = {"loan_product": "PL", "is_pl_prime": False}
        assert calculator.get_effective_product(disbursement) == "PL"

    def test_effective_product_non_pl_ignored(self, calculator):
        """Non-PL product ignores is_pl_prime flag."""
        disbursement = {"loan_product": "HL", "is_pl_prime": True}
        assert calculator.get_effective_product(disbursement) == "HL"

    def test_pl_prime_uses_different_slab_rates(self, calculator):
        """PL_PRIME slab lookup returns different rates than PL."""
        # PL slab for 200000 -> rate 0.50
        pl_slab = calculator.lookup_slab("PL", Decimal("200000"))
        # PL_PRIME slab for 200000 -> rate 0.60
        pl_prime_slab = calculator.lookup_slab("PL_PRIME", Decimal("200000"))

        assert pl_slab is not None
        assert pl_prime_slab is not None
        assert pl_slab.rate == 0.50
        assert pl_prime_slab.rate == 0.60

    def test_pl_prime_commission_differs_from_pl(self, calculator):
        """PL_PRIME commission is different from standard PL for same amount."""
        gross_pl, _ = calculator.compute_gross_commission("PL", Decimal("200000"), 1, 1)
        gross_prime, _ = calculator.compute_gross_commission("PL_PRIME", Decimal("200000"), 1, 1)

        # PL: 200000 * 0.50 / 100 = 1000
        # PL_PRIME: 200000 * 0.60 / 100 = 1200
        assert gross_pl == Decimal("1000")
        assert gross_prime == Decimal("1200")
        assert gross_prime > gross_pl

    def test_pl_prime_has_different_tier_adjustments(self, calculator):
        """PL_PRIME has different loan sequence tier thresholds."""
        # PL tier 2 starts at seq 6 with -0.10 adjustment
        pl_adj = calculator.get_loan_sequence_adjustment("PL", 6)
        assert pl_adj == Decimal("-0.10")

        # PL_PRIME tier 2 starts at seq 4 with +0.05 adjustment
        prime_adj = calculator.get_loan_sequence_adjustment("PL_PRIME", 4)
        assert prime_adj == Decimal("0.05")


# ============================================================
# Task 6.6: Cutoff Date Filtering and Full Calculate Method
# ============================================================


class TestCalculate:
    """Tests for CommissionCalculator.calculate() pipeline method."""

    @pytest.fixture
    def loans_df(self):
        """Sample loans DataFrame."""
        return pd.DataFrame({
            "lan": ["LAN001", "LAN002", "LAN003", "LAN004"],
            "partner_id": ["P1", "P1", "P2", "P1"],
            "loan_product": ["PL", "PL", "PL", "PL"],
            "is_pl_prime": [False, True, False, False],
            "sanctioned_amount": [200000, 600000, 100000, 300000],
            "application_date": [
                date(2024, 1, 1),
                date(2024, 1, 10),
                date(2024, 1, 5),
                date(2024, 2, 1),
            ],
        })

    @pytest.fixture
    def partners_df(self):
        """Sample partners DataFrame."""
        return pd.DataFrame({
            "partner_id": ["P1", "P2", "P3"],
            "partner_name": ["Partner One", "Partner Two", "Partner Three"],
            "partner_type": ["DSA", "Connector", "DSA"],
            "corporate_flag": [True, False, True],
            "registration_date": [
                date(2023, 1, 1),
                date(2023, 6, 1),
                date(2023, 3, 1),
            ],
            "active": [True, True, False],
        })

    @pytest.fixture
    def disbursements_df(self):
        """Sample disbursements DataFrame."""
        return pd.DataFrame({
            "disbursement_id": ["D1", "D2", "D3", "D4", "D5"],
            "lan": ["LAN001", "LAN002", "LAN003", "LAN001", "LAN004"],
            "partner_id": ["P1", "P1", "P2", "P1", "P1"],
            "loan_product": ["PL", "PL", "PL", "PL", "PL"],
            "disbursed_amount": [200000, 600000, 100000, 200000, 300000],
            "disbursement_date": [
                date(2024, 1, 15),
                date(2024, 1, 20),
                date(2024, 1, 25),
                date(2024, 2, 5),
                date(2024, 2, 28),
            ],
            "cheque_handover_date": [
                date(2024, 1, 16),
                date(2024, 1, 21),
                None,
                date(2024, 2, 6),
                date(2024, 2, 28),
            ],
            "disbursement_sequence": [1, 1, 1, 2, 1],
        })

    def test_cutoff_date_filters_future_disbursements(
        self, calculator, disbursements_df, partners_df, loans_df
    ):
        """Disbursements after cutoff_date are excluded."""
        cutoff = date(2024, 1, 31)
        results = calculator.calculate(disbursements_df, partners_df, loans_df, cutoff)
        # D1, D2, D3 are on or before Jan 31; D4 and D5 are in Feb
        result_lans = [r.lan for r in results]
        assert "LAN001" in result_lans
        assert "LAN002" in result_lans
        assert "LAN003" in result_lans
        # D4 (LAN001 again) and D5 (LAN004) are after cutoff
        assert len(results) == 3

    def test_cutoff_date_includes_boundary_date(
        self, calculator, disbursements_df, partners_df, loans_df
    ):
        """Disbursements on the exact cutoff date are included."""
        cutoff = date(2024, 1, 25)
        results = calculator.calculate(disbursements_df, partners_df, loans_df, cutoff)
        # D1 (Jan 15), D2 (Jan 20), D3 (Jan 25) included
        assert len(results) == 3

    def test_all_disbursements_included_with_late_cutoff(
        self, calculator, disbursements_df, partners_df, loans_df
    ):
        """Cutoff well in the future includes all disbursements."""
        cutoff = date(2025, 12, 31)
        results = calculator.calculate(disbursements_df, partners_df, loans_df, cutoff)
        assert len(results) == 5

    def test_eligible_disbursement_has_positive_commission(
        self, calculator, disbursements_df, partners_df, loans_df
    ):
        """Eligible disbursement with valid amount gets positive commission."""
        cutoff = date(2024, 1, 31)
        results = calculator.calculate(disbursements_df, partners_df, loans_df, cutoff)
        # D1: PL, 200000, active partner, meets min disbursement
        d1 = [r for r in results if r.lan == "LAN001"][0]
        assert d1.eligible is True
        assert d1.gross_commission > Decimal("0")

    def test_pl_prime_uses_prime_slab_rates(
        self, calculator, disbursements_df, partners_df, loans_df
    ):
        """PL Prime disbursement uses PL_PRIME slab config."""
        cutoff = date(2024, 1, 31)
        results = calculator.calculate(disbursements_df, partners_df, loans_df, cutoff)
        # D2: LAN002 is_pl_prime=True, amount=600000
        # PL_PRIME slab for 600000: rate=0.90 (500001-1500000)
        # first disbursement (mult=1.0), loan_sequence for LAN002 is 2 (appeared second for P1)
        # loan_sequence 2 is in tier seq_min=1, seq_max=3, adj=0.0
        # final_rate = 0.90 * 1.0 + 0.0 = 0.90
        # gross = 600000 * 0.90 / 100 = 5400
        d2 = [r for r in results if r.lan == "LAN002"][0]
        assert d2.eligible is True
        assert d2.gross_commission == Decimal("600000") * Decimal("0.90") / Decimal("100")
        assert d2.loan_product == "PL"  # original product stored

    def test_ineligible_disbursement_has_zero_commission(self, calculator, partners_df, loans_df):
        """Disbursement below minimum gets zero commission with failed rule flag."""
        # Create a disbursement below the min threshold (10000)
        disb_df = pd.DataFrame({
            "disbursement_id": ["D_LOW"],
            "lan": ["LAN_LOW"],
            "partner_id": ["P1"],
            "loan_product": ["PL"],
            "disbursed_amount": [5000],
            "disbursement_date": [date(2024, 1, 10)],
            "cheque_handover_date": [date(2024, 1, 11)],
            "disbursement_sequence": [1],
        })
        low_loans = pd.DataFrame({
            "lan": ["LAN_LOW"],
            "partner_id": ["P1"],
            "loan_product": ["PL"],
            "is_pl_prime": [False],
            "sanctioned_amount": [5000],
            "application_date": [date(2024, 1, 1)],
        })
        cutoff = date(2024, 1, 31)
        results = calculator.calculate(disb_df, partners_df, low_loans, cutoff)
        assert len(results) == 1
        assert results[0].eligible is False
        assert results[0].gross_commission == Decimal("0")
        assert "MIN_DISBURSEMENT" in results[0].flags

    def test_inactive_partner_ineligible(self, calculator, loans_df):
        """Inactive partner's disbursements are ineligible."""
        partners = pd.DataFrame({
            "partner_id": ["P_INACTIVE"],
            "partner_name": ["Inactive Partner"],
            "partner_type": ["DSA"],
            "corporate_flag": [True],
            "registration_date": [date(2023, 1, 1)],
            "active": [False],
        })
        disb_df = pd.DataFrame({
            "disbursement_id": ["D_INACT"],
            "lan": ["LAN_INACT"],
            "partner_id": ["P_INACTIVE"],
            "loan_product": ["PL"],
            "disbursed_amount": [200000],
            "disbursement_date": [date(2024, 1, 10)],
            "cheque_handover_date": [date(2024, 1, 11)],
            "disbursement_sequence": [1],
        })
        inactive_loans = pd.DataFrame({
            "lan": ["LAN_INACT"],
            "partner_id": ["P_INACTIVE"],
            "loan_product": ["PL"],
            "is_pl_prime": [False],
            "sanctioned_amount": [200000],
            "application_date": [date(2024, 1, 1)],
        })
        cutoff = date(2024, 1, 31)
        results = calculator.calculate(disb_df, partners, inactive_loans, cutoff)
        assert len(results) == 1
        assert results[0].eligible is False
        assert results[0].gross_commission == Decimal("0")
        assert "ACTIVE_PARTNER" in results[0].flags

    def test_missing_allocation_date_flags_and_marks_ineligible(self, calculator, loans_df):
        """Missing allocation date adds flag and sets eligible=False."""
        partners = pd.DataFrame({
            "partner_id": ["P1"],
            "partner_name": ["Partner One"],
            "partner_type": ["DSA"],
            "corporate_flag": [True],
            "registration_date": [date(2023, 1, 1)],
            "active": [True],
        })
        # HL uses cheque_handover_date; make it None
        disb_df = pd.DataFrame({
            "disbursement_id": ["D_HL"],
            "lan": ["LAN_HL"],
            "partner_id": ["P1"],
            "loan_product": ["HL"],
            "disbursed_amount": [600000],
            "disbursement_date": [date(2024, 1, 10)],
            "cheque_handover_date": [None],
            "disbursement_sequence": [1],
        })
        hl_loans = pd.DataFrame({
            "lan": ["LAN_HL"],
            "partner_id": ["P1"],
            "loan_product": ["HL"],
            "is_pl_prime": [False],
            "sanctioned_amount": [600000],
            "application_date": [date(2024, 1, 1)],
        })

        # Need HL slab config for this to work
        from commission_engine.config_loader import SlabConfig, PayoutSlab, SequenceRules, LoanSequenceTier
        hl_config = SlabConfig(
            product="HL",
            slab_basis="disbursed_amount",
            slabs=[
                PayoutSlab(min=0, max=None, rate_type="percentage", rate=0.30),
            ],
            sequence_rules=SequenceRules(
                first_disbursement_multiplier=1.0,
                subsequent_disbursement_multiplier=0.5,
            ),
            loan_sequence_tiers=[
                LoanSequenceTier(sequence_min=1, sequence_max=None, rate_adjustment=0.0),
            ],
        )
        # Add HL_MIN_AMOUNT rule applies: 600000 >= 500000 so should pass eligibility
        calc = CommissionCalculator(
            slab_config={**calculator.slab_config, "HL": hl_config},
            eligibility_rules=calculator.eligibility_rules,
            allocation_rules=calculator.allocation_rules,
        )
        cutoff = date(2024, 1, 31)
        results = calc.calculate(disb_df, partners, hl_loans, cutoff)
        assert len(results) == 1
        assert "missing_allocation_date" in results[0].flags
        assert results[0].eligible is False

    def test_empty_disbursements_returns_empty_list(
        self, calculator, partners_df, loans_df
    ):
        """Empty disbursements DataFrame returns empty results."""
        empty_df = pd.DataFrame(columns=[
            "disbursement_id", "lan", "partner_id", "loan_product",
            "disbursed_amount", "disbursement_date", "cheque_handover_date",
            "disbursement_sequence",
        ])
        results = calculator.calculate(empty_df, partners_df, loans_df, date(2024, 12, 31))
        assert results == []

    def test_no_disbursements_before_cutoff_returns_empty(
        self, calculator, disbursements_df, partners_df, loans_df
    ):
        """Cutoff date before all disbursements returns empty results."""
        cutoff = date(2023, 1, 1)
        results = calculator.calculate(disbursements_df, partners_df, loans_df, cutoff)
        assert results == []

    def test_month_allocation_uses_disbursement_date_for_pl(
        self, calculator, disbursements_df, partners_df, loans_df
    ):
        """PL products allocate month from disbursement_date."""
        cutoff = date(2024, 1, 31)
        results = calculator.calculate(disbursements_df, partners_df, loans_df, cutoff)
        # D1: disbursement_date=2024-01-15 -> month "2024-01"
        d1 = [r for r in results if r.lan == "LAN001"][0]
        assert d1.month_allocation == "2024-01"

    def test_result_preserves_original_loan_product(
        self, calculator, disbursements_df, partners_df, loans_df
    ):
        """CommissionResult stores the original loan_product, not effective product."""
        cutoff = date(2024, 1, 31)
        results = calculator.calculate(disbursements_df, partners_df, loans_df, cutoff)
        # LAN002 is PL_PRIME but loan_product in result should be "PL"
        d2 = [r for r in results if r.lan == "LAN002"][0]
        assert d2.loan_product == "PL"

    def test_connector_partner_gets_commission(self, calculator, disbursements_df, partners_df, loans_df):
        """Connector partner type also receives commission (same slab rules for now)."""
        cutoff = date(2024, 1, 31)
        results = calculator.calculate(disbursements_df, partners_df, loans_df, cutoff)
        # D3: partner P2 is a Connector, amount=100000, active=True
        d3 = [r for r in results if r.lan == "LAN003"][0]
        assert d3.eligible is True
        assert d3.gross_commission > Decimal("0")
        assert d3.partner_id == "P2"
