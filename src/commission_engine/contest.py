"""Contest Module for the Channel Partner Commission Engine.

Evaluates monthly and quarterly contest qualification for partners
and computes contest payouts based on configured contest definitions.
"""

from __future__ import annotations

import math
import operator as op
from decimal import Decimal

import pandas as pd

from .config_loader import ContestDefinition
from .models import ContestResult


# Mapping of operator strings to comparison functions
_OPERATORS: dict[str, callable] = {
    "gte": op.ge,
    "gt": op.gt,
    "lte": op.le,
    "lt": op.lt,
    "eq": op.eq,
}


class ContestModule:
    """Evaluates partner contest qualification and computes contest payouts.

    For each configured contest, the module:
    1. Determines the relevant time window (month or quarter)
    2. Filters disbursements by product (if specified)
    3. Computes the qualification metric per partner
    4. Compares against the threshold using the configured operator
    5. Computes payouts for qualifying partners
    """

    def __init__(self, contest_config: list[ContestDefinition]) -> None:
        """Initialize the ContestModule with contest definitions.

        Parameters
        ----------
        contest_config : list[ContestDefinition]
            List of contest definitions from configuration.
        """
        self._contests = contest_config

    def evaluate(
        self,
        disbursements: pd.DataFrame,
        partners: pd.DataFrame,
        cycle: str,
    ) -> list[ContestResult]:
        """Evaluate all configured contests for all partners.

        Parameters
        ----------
        disbursements : pd.DataFrame
            DataFrame with columns including: partner_id, loan_product,
            disbursed_amount, disbursement_date.
        partners : pd.DataFrame
            DataFrame with columns including: partner_id.
        cycle : str
            The processing cycle in "YYYY-MM" format.

        Returns
        -------
        list[ContestResult]
            A ContestResult per partner per contest.
        """
        results: list[ContestResult] = []

        # Parse cycle to determine year and month
        year, month = self._parse_cycle(cycle)

        # Get unique partner IDs from the partners DataFrame
        partner_ids = partners["partner_id"].unique().tolist()

        for contest in self._contests:
            # Determine the time window for this contest
            filtered = self._filter_by_time_window(
                disbursements, contest.type, year, month
            )

            # Filter by product if not ALL
            product = contest.qualification_rule.get("product", "ALL")
            if product != "ALL":
                filtered = filtered[filtered["loan_product"] == product]

            # Evaluate each partner
            for partner_id in partner_ids:
                partner_disb = filtered[filtered["partner_id"] == partner_id]
                metric_value = self._compute_metric(
                    partner_disb, contest.qualification_rule.get("metric", "")
                )
                qualified = self._check_qualification(
                    metric_value,
                    contest.qualification_rule.get("operator", "gte"),
                    contest.qualification_rule.get("threshold", 0),
                )

                if qualified:
                    payout = self._compute_payout(contest.payout, metric_value)
                else:
                    payout = Decimal("0")

                results.append(
                    ContestResult(
                        partner_id=str(partner_id),
                        contest_id=contest.id,
                        qualified=qualified,
                        payout=payout,
                    )
                )

        return results

    @staticmethod
    def _parse_cycle(cycle: str) -> tuple[int, int]:
        """Parse a cycle string 'YYYY-MM' into (year, month)."""
        parts = cycle.split("-")
        return int(parts[0]), int(parts[1])

    @staticmethod
    def _filter_by_time_window(
        disbursements: pd.DataFrame,
        contest_type: str,
        year: int,
        month: int,
    ) -> pd.DataFrame:
        """Filter disbursements to the relevant time window.

        Parameters
        ----------
        disbursements : pd.DataFrame
            All disbursements with a disbursement_date column.
        contest_type : str
            'monthly' or 'quarterly'.
        year : int
            The cycle year.
        month : int
            The cycle month.

        Returns
        -------
        pd.DataFrame
            Disbursements within the time window.
        """
        if disbursements.empty:
            return disbursements

        # Ensure disbursement_date is datetime
        dates = pd.to_datetime(disbursements["disbursement_date"], errors="coerce")

        if contest_type == "monthly":
            mask = (dates.dt.year == year) & (dates.dt.month == month)
        elif contest_type == "quarterly":
            quarter = math.ceil(month / 3)
            quarter_start_month = (quarter - 1) * 3 + 1
            quarter_end_month = quarter * 3
            mask = (
                (dates.dt.year == year)
                & (dates.dt.month >= quarter_start_month)
                & (dates.dt.month <= quarter_end_month)
            )
        else:
            # Unknown type — return empty
            mask = pd.Series([False] * len(disbursements), index=disbursements.index)

        return disbursements[mask]

    @staticmethod
    def _compute_metric(partner_disbursements: pd.DataFrame, metric: str) -> Decimal:
        """Compute the qualification metric value for a partner's disbursements.

        Parameters
        ----------
        partner_disbursements : pd.DataFrame
            Filtered disbursements for a single partner.
        metric : str
            One of 'disbursement_count' or 'total_disbursed_amount'.

        Returns
        -------
        Decimal
            The computed metric value.
        """
        if metric == "disbursement_count":
            return Decimal(str(len(partner_disbursements)))
        elif metric == "total_disbursed_amount":
            if partner_disbursements.empty:
                return Decimal("0")
            total = partner_disbursements["disbursed_amount"].sum()
            return Decimal(str(total))
        else:
            return Decimal("0")

    @staticmethod
    def _check_qualification(
        metric_value: Decimal, operator_str: str, threshold: float | int
    ) -> bool:
        """Check if the metric value satisfies the qualification rule.

        Parameters
        ----------
        metric_value : Decimal
            The computed metric value for the partner.
        operator_str : str
            Comparison operator (gte, gt, lte, lt, eq).
        threshold : float | int
            The threshold value to compare against.

        Returns
        -------
        bool
            True if the partner qualifies.
        """
        compare_fn = _OPERATORS.get(operator_str)
        if compare_fn is None:
            return False
        return compare_fn(metric_value, Decimal(str(threshold)))

    @staticmethod
    def _compute_payout(payout_config: dict, metric_value: Decimal) -> Decimal:
        """Compute the contest payout for a qualifying partner.

        Parameters
        ----------
        payout_config : dict
            Payout configuration with 'type' and either 'amount' or 'rate'+'basis'.
        metric_value : Decimal
            The computed metric value (used as basis for percentage payouts).

        Returns
        -------
        Decimal
            The payout amount.
        """
        payout_type = payout_config.get("type", "")

        if payout_type == "fixed":
            amount = payout_config.get("amount", 0)
            return Decimal(str(amount))
        elif payout_type == "percentage":
            rate = Decimal(str(payout_config.get("rate", 0)))
            # For percentage payouts, the basis is the metric_value
            # (e.g., total_disbursed_amount)
            return rate * metric_value
        else:
            return Decimal("0")
