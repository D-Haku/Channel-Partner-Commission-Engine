"""Reconciliation Module: compares computed payouts against reference values."""

from __future__ import annotations

from decimal import Decimal

import pandas as pd

from .models import DeductionResult, Discrepancy, ReconciliationSummary


class ReconciliationModule:
    """Compares computed net payouts against reference data and classifies differences."""

    def __init__(self, tolerance: Decimal) -> None:
        """Initialize with an absolute difference threshold for matching.

        Args:
            tolerance: Maximum absolute difference to still consider a match.
        """
        self.tolerance = tolerance

    def reconcile(
        self, computed: list[DeductionResult], reference: pd.DataFrame
    ) -> ReconciliationSummary:
        """Reconcile computed payouts against reference amounts.

        Args:
            computed: List of DeductionResult from the deduction module.
            reference: DataFrame with columns 'lan' and 'reference_amount'.

        Returns:
            ReconciliationSummary with match/discrepancy/missing counts and details.
        """
        # Build dict: lan -> net_payout from computed results
        computed_map: dict[str, Decimal] = {
            result.lan: result.net_payout for result in computed
        }

        # Build dict: lan -> reference_amount from reference DataFrame
        reference_map: dict[str, Decimal] = {}
        for _, row in reference.iterrows():
            lan = str(row["lan"])
            amount = Decimal(str(row["reference_amount"]))
            reference_map[lan] = amount

        # Classify each LAN in the union of both sets
        all_lans = set(computed_map.keys()) | set(reference_map.keys())

        matched_count = 0
        discrepancies: list[Discrepancy] = []
        missing_computed_count = 0
        missing_reference_count = 0

        for lan in all_lans:
            in_computed = lan in computed_map
            in_reference = lan in reference_map

            if in_computed and in_reference:
                computed_amount = computed_map[lan]
                reference_amount = reference_map[lan]
                difference = abs(computed_amount - reference_amount)

                if difference <= self.tolerance:
                    matched_count += 1
                else:
                    discrepancies.append(
                        Discrepancy(
                            lan=lan,
                            computed_amount=computed_amount,
                            reference_amount=reference_amount,
                            difference=difference,
                        )
                    )
            elif in_reference and not in_computed:
                missing_computed_count += 1
            else:
                # in_computed and not in_reference
                missing_reference_count += 1

        return ReconciliationSummary(
            matched_count=matched_count,
            discrepancy_count=len(discrepancies),
            missing_computed_count=missing_computed_count,
            missing_reference_count=missing_reference_count,
            discrepancies=discrepancies,
        )
