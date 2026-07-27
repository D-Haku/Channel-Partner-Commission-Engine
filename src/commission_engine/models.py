"""Data model dataclasses for the Channel Partner Commission Engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from .exceptions import ValidationException


@dataclass
class ExtractionResult:
    """DataFrames from extraction step plus record counts."""

    loans_df: Any
    disbursements_df: Any
    partners_df: Any
    record_counts: dict[str, int] = field(default_factory=dict)


@dataclass
class ValidationResult:
    """Results of the validation step."""

    valid_disbursements: Any
    exception_list: list[ValidationException] = field(default_factory=list)
    valid_count: int = 0
    excluded_count: int = 0
    exclusion_reasons: dict[str, int] = field(default_factory=dict)


@dataclass
class CommissionResult:
    """Single payout line result from commission calculation."""

    lan: str
    partner_id: str
    loan_product: str
    gross_commission: Decimal
    month_allocation: str
    eligible: bool
    flags: list[str] = field(default_factory=list)


@dataclass
class ContestResult:
    """Per-partner contest evaluation result."""

    partner_id: str
    contest_id: str
    qualified: bool
    payout: Decimal


@dataclass
class DeductionResult:
    """Net payout after GST and TDS deductions."""

    lan: str
    partner_id: str
    gross_commission: Decimal
    gst_amount: Decimal
    tds_amount: Decimal
    net_payout: Decimal


@dataclass
class Discrepancy:
    """A reconciliation mismatch between computed and reference amounts."""

    lan: str
    computed_amount: Decimal
    reference_amount: Decimal
    difference: Decimal


@dataclass
class ReconciliationSummary:
    """Reconciliation results summary."""

    matched_count: int
    discrepancy_count: int
    missing_computed_count: int
    missing_reference_count: int
    discrepancies: list[Discrepancy] = field(default_factory=list)


@dataclass
class ProcessingRunResult:
    """Full processing run outcome."""

    cycle: str
    cutoff_date: date
    config_id: str
    record_counts: dict[str, int] = field(default_factory=dict)
    report_paths: list[str] = field(default_factory=list)
    storage_locations: list[str] = field(default_factory=list)
    exceptions: list[ValidationException] = field(default_factory=list)
    reconciliation_summary: ReconciliationSummary | None = None
