"""Report Generator module for the Channel Partner Commission Engine.

Produces CSV payout, contest, and reconciliation reports.
"""

from __future__ import annotations

import csv
from pathlib import Path

from .models import ContestResult, Discrepancy, ReconciliationSummary


class ReportGenerator:
    """Generates CSV report files from commission engine results."""

    PAYOUT_COLUMNS = [
        "LAN",
        "Partner_ID",
        "Loan_Product",
        "Gross_Commission",
        "GST_Amount",
        "TDS_Amount",
        "Net_Payout",
        "Month_Allocation",
    ]

    CONTEST_COLUMNS = [
        "Partner_ID",
        "Contest_ID",
        "Payout",
    ]

    RECONCILIATION_COLUMNS = [
        "LAN",
        "Computed_Amount",
        "Reference_Amount",
        "Difference",
        "Status",
    ]

    def __init__(self, output_dir: Path) -> None:
        """Initialize ReportGenerator.

        Args:
            output_dir: Directory where CSV report files will be written.
        """
        self.output_dir = output_dir

    def generate_payout_report(self, payouts: list[dict]) -> Path:
        """Generate a payout CSV report.

        Each dict should contain keys: lan, partner_id, loan_product,
        gross_commission, gst_amount, tds_amount, net_payout, month_allocation.

        Args:
            payouts: List of dicts with payout data.

        Returns:
            Path to the written CSV file.
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.output_dir / "payout_report.csv"

        with open(output_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(self.PAYOUT_COLUMNS)
            for payout in payouts:
                writer.writerow([
                    payout.get("lan", ""),
                    payout.get("partner_id", ""),
                    payout.get("loan_product", ""),
                    payout.get("gross_commission", ""),
                    payout.get("gst_amount", ""),
                    payout.get("tds_amount", ""),
                    payout.get("net_payout", ""),
                    payout.get("month_allocation", ""),
                ])

        return output_path

    def generate_contest_report(self, contests: list[ContestResult]) -> Path:
        """Generate a contest payout CSV report.

        Args:
            contests: List of ContestResult objects.

        Returns:
            Path to the written CSV file.
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.output_dir / "contest_report.csv"

        with open(output_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(self.CONTEST_COLUMNS)
            for contest in contests:
                writer.writerow([
                    contest.partner_id,
                    contest.contest_id,
                    contest.payout,
                ])

        return output_path

    def generate_reconciliation_report(
        self, summary: ReconciliationSummary
    ) -> Path:
        """Generate a reconciliation CSV report.

        Includes discrepancies, missing-computed, and missing-reference entries.

        Args:
            summary: ReconciliationSummary containing discrepancy details.

        Returns:
            Path to the written CSV file.
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.output_dir / "reconciliation_report.csv"

        with open(output_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(self.RECONCILIATION_COLUMNS)
            for disc in summary.discrepancies:
                status = self._classify_discrepancy(disc)
                writer.writerow([
                    disc.lan,
                    disc.computed_amount,
                    disc.reference_amount,
                    disc.difference,
                    status,
                ])

        return output_path

    @staticmethod
    def _classify_discrepancy(disc: Discrepancy) -> str:
        """Classify a discrepancy entry by its type.

        - missing_computed: reference exists but no computed amount
        - missing_reference: computed exists but no reference amount
        - discrepancy: both exist but differ beyond tolerance
        """
        if disc.computed_amount is None:
            return "missing_computed"
        if disc.reference_amount is None:
            return "missing_reference"
        return "discrepancy"
