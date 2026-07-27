"""Unit tests for the ReportGenerator module."""

import csv
from decimal import Decimal
from pathlib import Path

import pytest

from commission_engine.models import ContestResult, Discrepancy, ReconciliationSummary
from commission_engine.reporter import ReportGenerator


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    """Provide a temporary output directory for reports."""
    return tmp_path / "reports"


@pytest.fixture
def generator(output_dir: Path) -> ReportGenerator:
    """Create a ReportGenerator with a temporary output directory."""
    return ReportGenerator(output_dir)


class TestGeneratePayoutReport:
    """Tests for generate_payout_report."""

    def test_creates_output_directory(self, generator: ReportGenerator, output_dir: Path):
        """Output directory is created if it does not exist."""
        assert not output_dir.exists()
        generator.generate_payout_report([])
        assert output_dir.exists()

    def test_empty_payouts_produces_header_only(self, generator: ReportGenerator):
        """An empty payout list produces a CSV with only a header row."""
        path = generator.generate_payout_report([])
        with open(path) as f:
            reader = csv.reader(f)
            rows = list(reader)
        assert len(rows) == 1
        assert rows[0] == ReportGenerator.PAYOUT_COLUMNS

    def test_single_payout_row(self, generator: ReportGenerator):
        """A single payout dict produces a header + one data row."""
        payouts = [
            {
                "lan": "LAN001",
                "partner_id": "P001",
                "loan_product": "PL",
                "gross_commission": Decimal("1000.00"),
                "gst_amount": Decimal("180.00"),
                "tds_amount": Decimal("100.00"),
                "net_payout": Decimal("1080.00"),
                "month_allocation": "2024-01",
            }
        ]
        path = generator.generate_payout_report(payouts)
        with open(path) as f:
            reader = csv.reader(f)
            rows = list(reader)
        assert len(rows) == 2
        assert rows[1][0] == "LAN001"
        assert rows[1][1] == "P001"
        assert rows[1][2] == "PL"
        assert rows[1][7] == "2024-01"

    def test_multiple_payouts(self, generator: ReportGenerator):
        """Multiple payout dicts produce the correct number of rows."""
        payouts = [
            {
                "lan": f"LAN{i:03d}",
                "partner_id": f"P{i:03d}",
                "loan_product": "HL",
                "gross_commission": Decimal("500.00"),
                "gst_amount": Decimal("90.00"),
                "tds_amount": Decimal("50.00"),
                "net_payout": Decimal("540.00"),
                "month_allocation": "2024-02",
            }
            for i in range(5)
        ]
        path = generator.generate_payout_report(payouts)
        with open(path) as f:
            reader = csv.reader(f)
            rows = list(reader)
        assert len(rows) == 6  # 1 header + 5 data rows

    def test_returns_correct_path(self, generator: ReportGenerator, output_dir: Path):
        """Returns the path to the payout_report.csv file."""
        path = generator.generate_payout_report([])
        assert path == output_dir / "payout_report.csv"
        assert path.exists()


class TestGenerateContestReport:
    """Tests for generate_contest_report."""

    def test_empty_contests_produces_header_only(self, generator: ReportGenerator):
        """An empty contest list produces a CSV with only a header row."""
        path = generator.generate_contest_report([])
        with open(path) as f:
            reader = csv.reader(f)
            rows = list(reader)
        assert len(rows) == 1
        assert rows[0] == ReportGenerator.CONTEST_COLUMNS

    def test_single_contest_result(self, generator: ReportGenerator):
        """A single ContestResult produces a header + one data row."""
        contests = [
            ContestResult(
                partner_id="P001",
                contest_id="MONTHLY_PL_VOLUME",
                qualified=True,
                payout=Decimal("5000.00"),
            )
        ]
        path = generator.generate_contest_report(contests)
        with open(path) as f:
            reader = csv.reader(f)
            rows = list(reader)
        assert len(rows) == 2
        assert rows[1][0] == "P001"
        assert rows[1][1] == "MONTHLY_PL_VOLUME"
        assert rows[1][2] == "5000.00"

    def test_multiple_contests(self, generator: ReportGenerator):
        """Multiple ContestResults produce the correct number of rows."""
        contests = [
            ContestResult(
                partner_id=f"P{i:03d}",
                contest_id="Q_REVENUE",
                qualified=True,
                payout=Decimal("2500.00"),
            )
            for i in range(3)
        ]
        path = generator.generate_contest_report(contests)
        with open(path) as f:
            reader = csv.reader(f)
            rows = list(reader)
        assert len(rows) == 4  # 1 header + 3 data

    def test_returns_correct_path(self, generator: ReportGenerator, output_dir: Path):
        """Returns the path to the contest_report.csv file."""
        path = generator.generate_contest_report([])
        assert path == output_dir / "contest_report.csv"
        assert path.exists()


class TestGenerateReconciliationReport:
    """Tests for generate_reconciliation_report."""

    def test_empty_discrepancies_produces_header_only(self, generator: ReportGenerator):
        """A summary with no discrepancies produces a header-only CSV."""
        summary = ReconciliationSummary(
            matched_count=10,
            discrepancy_count=0,
            missing_computed_count=0,
            missing_reference_count=0,
            discrepancies=[],
        )
        path = generator.generate_reconciliation_report(summary)
        with open(path) as f:
            reader = csv.reader(f)
            rows = list(reader)
        assert len(rows) == 1
        assert rows[0] == ReportGenerator.RECONCILIATION_COLUMNS

    def test_discrepancy_status(self, generator: ReportGenerator):
        """A standard discrepancy is classified with status 'discrepancy'."""
        summary = ReconciliationSummary(
            matched_count=0,
            discrepancy_count=1,
            missing_computed_count=0,
            missing_reference_count=0,
            discrepancies=[
                Discrepancy(
                    lan="LAN001",
                    computed_amount=Decimal("1000.00"),
                    reference_amount=Decimal("1050.00"),
                    difference=Decimal("-50.00"),
                )
            ],
        )
        path = generator.generate_reconciliation_report(summary)
        with open(path) as f:
            reader = csv.reader(f)
            rows = list(reader)
        assert len(rows) == 2
        assert rows[1][0] == "LAN001"
        assert rows[1][4] == "discrepancy"

    def test_missing_computed_status(self, generator: ReportGenerator):
        """A discrepancy with None computed_amount is classified as 'missing_computed'."""
        summary = ReconciliationSummary(
            matched_count=0,
            discrepancy_count=0,
            missing_computed_count=1,
            missing_reference_count=0,
            discrepancies=[
                Discrepancy(
                    lan="LAN002",
                    computed_amount=None,
                    reference_amount=Decimal("500.00"),
                    difference=Decimal("500.00"),
                )
            ],
        )
        path = generator.generate_reconciliation_report(summary)
        with open(path) as f:
            reader = csv.reader(f)
            rows = list(reader)
        assert rows[1][4] == "missing_computed"

    def test_missing_reference_status(self, generator: ReportGenerator):
        """A discrepancy with None reference_amount is classified as 'missing_reference'."""
        summary = ReconciliationSummary(
            matched_count=0,
            discrepancy_count=0,
            missing_computed_count=0,
            missing_reference_count=1,
            discrepancies=[
                Discrepancy(
                    lan="LAN003",
                    computed_amount=Decimal("750.00"),
                    reference_amount=None,
                    difference=Decimal("750.00"),
                )
            ],
        )
        path = generator.generate_reconciliation_report(summary)
        with open(path) as f:
            reader = csv.reader(f)
            rows = list(reader)
        assert rows[1][4] == "missing_reference"

    def test_returns_correct_path(self, generator: ReportGenerator, output_dir: Path):
        """Returns the path to the reconciliation_report.csv file."""
        summary = ReconciliationSummary(
            matched_count=0,
            discrepancy_count=0,
            missing_computed_count=0,
            missing_reference_count=0,
            discrepancies=[],
        )
        path = generator.generate_reconciliation_report(summary)
        assert path == output_dir / "reconciliation_report.csv"
        assert path.exists()
