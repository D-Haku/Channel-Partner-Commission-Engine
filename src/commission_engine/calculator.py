"""Commission Calculator for the Channel Partner Commission Engine.

Computes gross commission amounts using product-wise, slab-based, and
sequence-based rules.
"""

from datetime import date
from decimal import Decimal
from typing import Optional

import pandas as pd

from commission_engine.config_loader import (
    EligibilityRule,
    LoanSequenceTier,
    PayoutSlab,
    SequenceRules,
    SlabConfig,
)
from commission_engine.models import CommissionResult


class CommissionCalculator:
    """Core commission calculation engine.

    Handles slab lookup, sequence determination, rate adjustment,
    eligibility checks, month allocation, and the full calculate pipeline.
    """

    def __init__(
        self,
        slab_config: dict[str, SlabConfig],
        eligibility_rules: list[EligibilityRule] | None = None,
        allocation_rules: dict[str, str] | None = None,
    ):
        """Initialize the CommissionCalculator.

        Args:
            slab_config: Mapping of product code to SlabConfig.
            eligibility_rules: List of eligibility rules for commission qualification.
            allocation_rules: Mapping of product to date field name
                ("cheque_handover_date" or "disbursement_date").
        """
        self.slab_config = slab_config
        self.eligibility_rules = eligibility_rules or []
        self.allocation_rules = allocation_rules or {}

    # ------------------------------------------------------------------
    # Task 6.1: Slab Lookup and Gross Commission Computation
    # ------------------------------------------------------------------

    def lookup_slab(self, product: str, basis_value: Decimal) -> Optional[PayoutSlab]:
        """Find the matching PayoutSlab for a product and basis value.

        Finds the slab where min <= basis_value <= max (max=None means unbounded).

        Args:
            product: The loan product code (e.g., 'PL', 'HL', 'PL_PRIME').
            basis_value: The slab basis value (e.g., disbursed amount).

        Returns:
            The matching PayoutSlab, or None if no slab matches.
        """
        slab_cfg = self.slab_config.get(product)
        if slab_cfg is None:
            return None

        for slab in slab_cfg.slabs:
            slab_min = Decimal(str(slab.min))
            slab_max = Decimal(str(slab.max)) if slab.max is not None else None

            if basis_value >= slab_min:
                if slab_max is None or basis_value <= slab_max:
                    return slab

        return None

    def compute_gross_commission(
        self,
        product: str,
        basis_value: Decimal,
        disbursement_sequence: int = 1,
        loan_sequence: int = 1,
    ) -> tuple[Decimal, list[str]]:
        """Compute gross commission incorporating slab rate, sequence multiplier, and tier adjustment.

        Formula:
            final_rate = slab_rate * sequence_multiplier + tier_adjustment
            gross = basis_value * final_rate / 100

        Args:
            product: The loan product code.
            basis_value: The slab basis value (disbursed amount).
            disbursement_sequence: 1 for first disbursement, 2+ for subsequent.
            loan_sequence: The loan sequence number for the partner.

        Returns:
            A tuple of (gross_commission, flags). If no slab matches,
            returns (Decimal('0'), ['slab_miss']).
        """
        slab = self.lookup_slab(product, basis_value)
        if slab is None:
            return Decimal("0"), ["slab_miss"]

        slab_rate = Decimal(str(slab.rate))

        # Apply sequence multiplier
        sequence_multiplier = self._get_sequence_multiplier(product, disbursement_sequence)

        # Apply loan sequence tier adjustment
        tier_adjustment = self._get_loan_sequence_adjustment(product, loan_sequence)

        # Final rate = slab_rate * sequence_multiplier + tier_adjustment
        final_rate = slab_rate * sequence_multiplier + tier_adjustment

        # gross = basis_value * final_rate / 100
        gross = basis_value * final_rate / Decimal("100")

        return gross, []

    # ------------------------------------------------------------------
    # Task 6.2: Sequence Determination and Rate Adjustment
    # ------------------------------------------------------------------

    def determine_sequence(self, partner_id: str, disbursements: pd.DataFrame) -> pd.DataFrame:
        """Determine loan sequence for a partner's disbursements.

        Orders disbursements by disbursement_date and assigns a loan_sequence
        number to each unique LAN based on order of first appearance.

        Args:
            partner_id: The partner identifier to filter disbursements for.
            disbursements: DataFrame containing disbursement records with columns:
                - partner_id, lan, disbursement_date, disbursement_sequence

        Returns:
            DataFrame filtered to the partner's disbursements with an added
            'loan_sequence' column numbering each unique LAN in chronological
            order of first appearance (1, 2, 3, ...).
        """
        partner_df = disbursements[disbursements["partner_id"] == partner_id].copy()

        if partner_df.empty:
            partner_df["loan_sequence"] = pd.Series(dtype="int64")
            return partner_df

        # Sort by disbursement_date to establish chronological ordering
        partner_df = partner_df.sort_values("disbursement_date").reset_index(drop=True)

        # Determine the order of first appearance of each LAN
        seen_lans: dict[str, int] = {}
        loan_sequences: list[int] = []
        sequence_counter = 1

        for lan in partner_df["lan"]:
            if lan not in seen_lans:
                seen_lans[lan] = sequence_counter
                sequence_counter += 1
            loan_sequences.append(seen_lans[lan])

        partner_df["loan_sequence"] = loan_sequences
        return partner_df

    def get_sequence_multiplier(self, product: str, disbursement_sequence: int) -> Decimal:
        """Get the commission multiplier based on disbursement sequence.

        Public wrapper around _get_sequence_multiplier for backward compatibility.

        Args:
            product: The loan product code (e.g., 'PL', 'HL').
            disbursement_sequence: The disbursement sequence number
                (1 = first disbursement, 2+ = subsequent).

        Returns:
            The multiplier as a Decimal.
        """
        return self._get_sequence_multiplier(product, disbursement_sequence)

    def get_loan_sequence_adjustment(self, product: str, loan_sequence: int) -> Decimal:
        """Get the rate adjustment based on a loan's sequence position.

        Public wrapper around _get_loan_sequence_adjustment for backward compatibility.

        Args:
            product: The loan product code (e.g., 'PL', 'HL').
            loan_sequence: The loan sequence number for the partner.

        Returns:
            The rate_adjustment as a Decimal for the matching tier,
            or Decimal('0') if no tier matches or product not found.
        """
        return self._get_loan_sequence_adjustment(product, loan_sequence)

    def _get_sequence_multiplier(self, product: str, disbursement_sequence: int) -> Decimal:
        """Get the commission multiplier based on disbursement sequence.

        Args:
            product: The loan product code.
            disbursement_sequence: 1 = first, 2+ = subsequent.

        Returns:
            first_disbursement_multiplier if sequence == 1, else
            subsequent_disbursement_multiplier. Returns Decimal('1') if product not found.
        """
        slab_cfg = self.slab_config.get(product)
        if slab_cfg is None:
            return Decimal("1")

        if disbursement_sequence == 1:
            return Decimal(str(slab_cfg.sequence_rules.first_disbursement_multiplier))
        else:
            return Decimal(str(slab_cfg.sequence_rules.subsequent_disbursement_multiplier))

    def _get_loan_sequence_adjustment(self, product: str, loan_sequence: int) -> Decimal:
        """Get the rate adjustment based on loan sequence tier.

        Finds the tier where sequence_min <= loan_sequence <= sequence_max
        (sequence_max=None means unbounded).

        Args:
            product: The loan product code.
            loan_sequence: The loan sequence number.

        Returns:
            The rate_adjustment for the matching tier, or Decimal('0').
        """
        slab_cfg = self.slab_config.get(product)
        if slab_cfg is None:
            return Decimal("0")

        for tier in slab_cfg.loan_sequence_tiers:
            if tier.sequence_min <= loan_sequence:
                if tier.sequence_max is None or loan_sequence <= tier.sequence_max:
                    return Decimal(str(tier.rate_adjustment))

        return Decimal("0")

    # ------------------------------------------------------------------
    # Task 6.3: Eligibility Check Logic
    # ------------------------------------------------------------------

    def check_eligibility(
        self, disbursement: dict, partner: dict
    ) -> tuple[bool, Optional[str]]:
        """Evaluate eligibility rules for a disbursement.

        Filters rules by product (rule.product == "ALL" or rule.product == disbursement product).
        Returns (False, rule.id) on first failure; (True, None) if all pass.

        Supported operators: gte (>=), gt (>), lte (<=), lt (<), eq (==).

        Field resolution:
            - "disbursed_amount" -> disbursement["disbursed_amount"]
            - "partner_active" -> partner["active"]

        Args:
            disbursement: Dictionary with disbursement data including
                'loan_product' and 'disbursed_amount'.
            partner: Dictionary with partner data (e.g., 'active' field).

        Returns:
            (True, None) if all applicable rules pass.
            (False, failed_rule_id) on the first rule failure.
        """
        product = disbursement.get("loan_product", "")

        for rule in self.eligibility_rules:
            # Filter by product applicability
            if rule.product != "ALL" and rule.product != product:
                continue

            # Resolve the field value
            if rule.field == "partner_active":
                actual_value = partner.get("active")
            elif rule.field == "disbursed_amount":
                actual_value = disbursement.get("disbursed_amount")
            else:
                actual_value = disbursement.get(rule.field)

            # If the actual value is None, the rule fails
            if actual_value is None:
                return False, rule.id

            # Evaluate operator
            if not self._evaluate_operator(actual_value, rule.operator, rule.value):
                return False, rule.id

        return True, None

    @staticmethod
    def _evaluate_operator(actual, operator: str, expected) -> bool:
        """Evaluate a comparison operator.

        Args:
            actual: The actual value from the record.
            operator: One of 'gte', 'gt', 'lte', 'lt', 'eq'.
            expected: The expected/threshold value from the rule.

        Returns:
            True if the comparison passes, False otherwise.
        """
        if operator == "gte":
            return actual >= expected
        elif operator == "gt":
            return actual > expected
        elif operator == "lte":
            return actual <= expected
        elif operator == "lt":
            return actual < expected
        elif operator == "eq":
            return actual == expected
        return False

    # ------------------------------------------------------------------
    # Task 6.4: Month Allocation Logic
    # ------------------------------------------------------------------

    def allocate_month(self, disbursement: dict) -> Optional[str]:
        """Assign a payout month based on the product's allocation rule.

        Uses self.allocation_rules to determine which date field to use for
        the given product. Defaults to "disbursement_date" if no rule is
        configured for the product.

        Args:
            disbursement: A dictionary representing a disbursement record,
                expected to contain 'loan_product', 'cheque_handover_date'
                and/or 'disbursement_date' keys.

        Returns:
            A string in "YYYY-MM" format representing the payout month,
            or None if the required date is missing.
        """
        product = disbursement.get("loan_product", "")
        allocation_rule = self.allocation_rules.get(product, "disbursement_date")

        if allocation_rule == "cheque_handover_date":
            date_value = disbursement.get("cheque_handover_date")
        elif allocation_rule == "disbursement_date":
            date_value = disbursement.get("disbursement_date")
        else:
            return None

        # Handle missing values: None, NaT, or any pandas null
        if date_value is None:
            return None
        try:
            if pd.isna(date_value):
                return None
        except (TypeError, ValueError):
            pass

        # Convert to a pandas Timestamp for consistent formatting
        ts = pd.Timestamp(date_value)
        return ts.strftime("%Y-%m")

    # ------------------------------------------------------------------
    # Task 6.5: PL Prime Commission Logic
    # ------------------------------------------------------------------

    def is_pl_prime(self, disbursement: dict) -> bool:
        """Check if a disbursement belongs to the PL Prime sub-category.

        Args:
            disbursement: Dictionary containing disbursement data.

        Returns:
            True if the disbursement has 'is_pl_prime' set to True,
            False otherwise.
        """
        return disbursement.get("is_pl_prime") is True

    def get_effective_product(self, disbursement: dict) -> str:
        """Determine the effective product code for slab lookup.

        For PL loans flagged as PL Prime, returns 'PL_PRIME' so the calculator
        uses the PL_PRIME slab config (with its distinct rates and sequence tiers)
        instead of the standard PL slabs.

        Args:
            disbursement: Dictionary containing disbursement data with at minimum
                'loan_product' and optionally 'is_pl_prime'.

        Returns:
            'PL_PRIME' if loan_product is 'PL' and is_pl_prime is True,
            otherwise the disbursement's loan_product value.
        """
        loan_product = disbursement.get("loan_product", "")
        if loan_product == "PL" and self.is_pl_prime(disbursement):
            return "PL_PRIME"
        return loan_product

    # ------------------------------------------------------------------
    # Task 6.6: Cutoff Date Filtering and Full Calculate Method
    # ------------------------------------------------------------------

    def calculate(
        self,
        disbursements: pd.DataFrame,
        partners: pd.DataFrame,
        loans: pd.DataFrame,
        cutoff_date: date,
    ) -> list[CommissionResult]:
        """Orchestrate the full commission calculation pipeline.

        Steps:
            1. Filter disbursements to include only those with disbursement_date <= cutoff_date
            2. Join loans onto disbursements to get is_pl_prime flag
            3. Join partners to get partner type and active status
            4. For each valid disbursement row:
               a. Get effective product (handle PL Prime)
               b. Determine loan_sequence for the partner's loans
               c. Check eligibility - if ineligible, set gross_commission=0, record failed rule
               d. If eligible, compute_gross_commission
               e. Allocate month
               f. Build CommissionResult

        Args:
            disbursements: DataFrame with columns: disbursement_id, lan, partner_id,
                loan_product, disbursed_amount, disbursement_date,
                cheque_handover_date, disbursement_sequence.
            partners: DataFrame with columns: partner_id, partner_name, partner_type,
                corporate_flag, registration_date, active.
            loans: DataFrame with columns: lan, partner_id, loan_product, is_pl_prime,
                sanctioned_amount, application_date.
            cutoff_date: Only disbursements on or before this date are processed.

        Returns:
            List of CommissionResult objects for each processed disbursement.
        """
        results: list[CommissionResult] = []

        # Step 1: Filter disbursements by cutoff date
        disb_dates = pd.to_datetime(disbursements["disbursement_date"])
        filtered = disbursements[disb_dates <= pd.Timestamp(cutoff_date)].copy()

        if filtered.empty:
            return results

        # Step 2: Join loans to get is_pl_prime flag
        loan_cols = ["lan", "is_pl_prime"]
        available_loan_cols = [c for c in loan_cols if c in loans.columns]
        if "lan" in available_loan_cols:
            filtered = filtered.merge(
                loans[available_loan_cols],
                on="lan",
                how="left",
                suffixes=("", "_loan"),
            )
            # Fill missing is_pl_prime with False
            if "is_pl_prime" in filtered.columns:
                filtered["is_pl_prime"] = filtered["is_pl_prime"].fillna(False)
            else:
                filtered["is_pl_prime"] = False

        # Step 3: Join partners to get partner_type and active status
        partner_cols = ["partner_id", "partner_type", "active"]
        available_partner_cols = [c for c in partner_cols if c in partners.columns]
        if "partner_id" in available_partner_cols:
            filtered = filtered.merge(
                partners[available_partner_cols],
                on="partner_id",
                how="left",
                suffixes=("", "_partner"),
            )

        # Pre-compute loan sequences per partner
        partner_sequences: dict[str, pd.DataFrame] = {}

        # Step 4: Process each disbursement row
        for _, row in filtered.iterrows():
            flags: list[str] = []
            lan = str(row.get("lan", ""))
            partner_id = str(row.get("partner_id", ""))
            loan_product = str(row.get("loan_product", ""))
            disbursed_amount = row.get("disbursed_amount", 0)
            disbursement_sequence = int(row.get("disbursement_sequence", 1))

            # Build disbursement dict for eligibility / allocation checks
            disb_dict: dict = {
                "lan": lan,
                "partner_id": partner_id,
                "loan_product": loan_product,
                "disbursed_amount": disbursed_amount,
                "disbursement_date": row.get("disbursement_date"),
                "cheque_handover_date": row.get("cheque_handover_date"),
                "disbursement_sequence": disbursement_sequence,
                "is_pl_prime": bool(row.get("is_pl_prime", False)),
            }

            # Build partner dict for eligibility checks
            partner_dict: dict = {
                "active": bool(row.get("active", False)),
                "partner_type": str(row.get("partner_type", "")),
            }

            # 4a: Get effective product (handle PL Prime)
            effective_product = self.get_effective_product(disb_dict)

            # 4b: Determine loan_sequence for this partner
            if partner_id not in partner_sequences:
                partner_sequences[partner_id] = self.determine_sequence(
                    partner_id, filtered
                )
            seq_df = partner_sequences[partner_id]
            loan_sequence = 1
            if not seq_df.empty:
                # Find matching row by lan in the sequence df
                matching = seq_df[seq_df["lan"] == lan]
                if not matching.empty:
                    loan_sequence = int(matching.iloc[0]["loan_sequence"])

            # 4c: Check eligibility
            eligible, failed_rule = self.check_eligibility(disb_dict, partner_dict)
            if not eligible:
                flags.append(failed_rule or "unknown_rule")
                gross_commission = Decimal("0")
            else:
                # 4d: Compute gross commission
                basis_value = Decimal(str(disbursed_amount))
                gross_commission, commission_flags = self.compute_gross_commission(
                    effective_product,
                    basis_value,
                    disbursement_sequence,
                    loan_sequence,
                )
                flags.extend(commission_flags)

            # 4e: Allocate month
            month_allocation = self.allocate_month(disb_dict)

            # Step 5: Handle missing month allocation
            if month_allocation is None:
                flags.append("missing_allocation_date")
                eligible = False
                month_allocation = ""

            # 4f: Build CommissionResult
            results.append(
                CommissionResult(
                    lan=lan,
                    partner_id=partner_id,
                    loan_product=loan_product,
                    gross_commission=gross_commission,
                    month_allocation=month_allocation,
                    eligible=eligible,
                    flags=flags,
                )
            )

        return results
