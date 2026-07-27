"""Commission Engine orchestrator for the Channel Partner Commission Engine.

Coordinates the full processing pipeline: extraction, validation, calculation,
contest evaluation, deductions, reconciliation, report generation, and upload.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Optional

import pandas as pd

from .config_loader import EngineConfig, load_config
from .extractor import DataExtractor, DuckDBBackend
from .validator import Validator
from .calculator import CommissionCalculator
from .contest import ContestModule
from .deductions import DeductionModule
from .reconciliation import ReconciliationModule
from .reporter import ReportGenerator
from .uploader import StorageUploader, LocalFSBackend
from .models import ProcessingRunResult, ReconciliationSummary
from .exceptions import WarehouseConnectionError, ConfigurationError


class CommissionEngine:
    """Top-level orchestrator that runs a Processing_Run end-to-end.

    Initializes all pipeline modules from an EngineConfig and executes them
    in sequence when `run()` is called.
    """

    def __init__(self, config: EngineConfig) -> None:
        """Initialize the engine and all sub-modules from configuration.

        Args:
            config: A fully populated EngineConfig instance.
        """
        self._config = config

        # Set up warehouse backend based on config
        warehouse_backend_type = config.warehouse.get("backend", "duckdb")
        if warehouse_backend_type == "duckdb":
            duckdb_config = config.warehouse.get("duckdb", {})
            database_path = duckdb_config.get("database_path", "data/warehouse.duckdb")
            self._warehouse_backend = DuckDBBackend(database_path)
        else:
            # Default to DuckDB for unsupported backends
            duckdb_config = config.warehouse.get("duckdb", {})
            database_path = duckdb_config.get("database_path", "data/warehouse.duckdb")
            self._warehouse_backend = DuckDBBackend(database_path)

        self._extractor = DataExtractor(self._warehouse_backend)
        self._validator = Validator()

        # Build allocation rules: HL and LAP use cheque_handover_date, all others use disbursement_date
        allocation_rules: dict[str, str] = {}
        for product in config.slabs:
            if product in ("HL", "LAP"):
                allocation_rules[product] = "cheque_handover_date"
            else:
                allocation_rules[product] = "disbursement_date"

        self._calculator = CommissionCalculator(
            slab_config=config.slabs,
            eligibility_rules=config.eligibility_rules,
            allocation_rules=allocation_rules,
        )

        self._contest_module = ContestModule(config.contests)
        self._deduction_module = DeductionModule(config.deductions)

        # Reconciliation tolerance
        tolerance = Decimal(str(config.reconciliation.get("tolerance", "0.01")))
        self._reconciliation_module = ReconciliationModule(tolerance)

        # Set up storage backend
        storage_backend_type = config.storage.get("backend", "local_fs")
        if storage_backend_type == "local_fs":
            local_fs_config = config.storage.get("local_fs", {})
            base_path = Path(local_fs_config.get("base_path", "output/"))
            self._storage_backend = LocalFSBackend(base_path)
        else:
            # Default to local filesystem for unsupported backends
            local_fs_config = config.storage.get("local_fs", {})
            base_path = Path(local_fs_config.get("base_path", "output/"))
            self._storage_backend = LocalFSBackend(base_path)

        self._uploader = StorageUploader(self._storage_backend)

        # Report generator writes to a reports subdirectory to avoid same-file
        # errors when LocalFSBackend uploads to the same base_path.
        self._report_output_dir = base_path / "reports"
        self._report_generator = ReportGenerator(self._report_output_dir)

        # Config ID for auditability
        # Use a string representation of warehouse config since nested dicts aren't hashable
        self._config_id = str(hash(str(sorted(config.warehouse.items()))))

    def run(
        self,
        cycle: str,
        cutoff_date: date,
        reference_data: Optional[pd.DataFrame] = None,
    ) -> ProcessingRunResult:
        """Execute a full processing run.

        Steps:
            1. Extract data via DataExtractor
            2. Validate via Validator
            3. Calculate commissions via CommissionCalculator
            4. Evaluate contests via ContestModule
            5. Apply deductions via DeductionModule
            6. Reconcile (if reference_data provided)
            7. Generate reports via ReportGenerator
            8. Upload via StorageUploader
            9. Return ProcessingRunResult with all metadata

        On connection/config errors: stop immediately, let exception propagate.
        On validation errors: collect and continue with valid records.

        Args:
            cycle: The processing cycle identifier (e.g., '2024-01').
            cutoff_date: The cutoff date bounding which disbursements are included.
            reference_data: Optional DataFrame with columns: lan, reference_amount.
                If provided, reconciliation is performed.

        Returns:
            ProcessingRunResult with full run metadata.

        Raises:
            WarehouseConnectionError: If the warehouse cannot be accessed.
            ConfigurationError: If configuration is invalid.
        """
        record_counts: dict[str, int] = {}

        # Step 1: Extract data
        extraction_result = self._extractor.extract(cycle, cutoff_date)
        record_counts["extracted_loans"] = extraction_result.record_counts.get("loans", 0)
        record_counts["extracted_disbursements"] = extraction_result.record_counts.get(
            "disbursements", 0
        )
        record_counts["extracted_partners"] = extraction_result.record_counts.get("partners", 0)

        loans_df = extraction_result.loans_df
        disbursements_df = extraction_result.disbursements_df
        partners_df = extraction_result.partners_df

        # Step 2: Validate
        validation_result = self._validator.validate(disbursements_df, partners_df)
        record_counts["valid_disbursements"] = validation_result.valid_count
        record_counts["excluded_disbursements"] = validation_result.excluded_count

        valid_disbursements = validation_result.valid_disbursements
        exceptions = validation_result.exception_list

        # Step 3: Calculate commissions
        commission_results = self._calculator.calculate(
            valid_disbursements, partners_df, loans_df, cutoff_date
        )
        eligible_commissions = [r for r in commission_results if r.eligible]
        record_counts["eligible_commissions"] = len(eligible_commissions)

        # Step 4: Evaluate contests
        contest_results = self._contest_module.evaluate(
            valid_disbursements, partners_df, cycle
        )
        contest_qualifications = [r for r in contest_results if r.qualified]
        record_counts["contest_qualifications"] = len(contest_qualifications)

        # Step 5: Apply deductions
        deduction_results = self._deduction_module.apply(commission_results, partners_df)

        # Step 6: Reconcile (if reference_data provided)
        reconciliation_summary: Optional[ReconciliationSummary] = None
        if reference_data is not None:
            reconciliation_summary = self._reconciliation_module.reconcile(
                deduction_results, reference_data
            )

        # Step 7: Generate reports
        # Build payout report data by combining CommissionResult + DeductionResult
        payout_data: list[dict] = []
        # Create a lookup from deduction results by lan
        deduction_lookup: dict[str, object] = {}
        for dr in deduction_results:
            deduction_lookup[dr.lan] = dr

        for cr in commission_results:
            dr = deduction_lookup.get(cr.lan)
            payout_entry = {
                "lan": cr.lan,
                "partner_id": cr.partner_id,
                "loan_product": cr.loan_product,
                "gross_commission": cr.gross_commission,
                "gst_amount": dr.gst_amount if dr else Decimal("0"),
                "tds_amount": dr.tds_amount if dr else Decimal("0"),
                "net_payout": dr.net_payout if dr else Decimal("0"),
                "month_allocation": cr.month_allocation,
            }
            payout_data.append(payout_entry)

        report_paths: list[Path] = []
        payout_report_path = self._report_generator.generate_payout_report(payout_data)
        report_paths.append(payout_report_path)

        contest_report_path = self._report_generator.generate_contest_report(contest_results)
        report_paths.append(contest_report_path)

        if reconciliation_summary is not None:
            recon_report_path = self._report_generator.generate_reconciliation_report(
                reconciliation_summary
            )
            report_paths.append(recon_report_path)

        # Step 8: Upload
        storage_locations = self._uploader.upload_reports(report_paths)

        # Step 9: Return ProcessingRunResult
        return ProcessingRunResult(
            cycle=cycle,
            cutoff_date=cutoff_date,
            config_id=self._config_id,
            record_counts=record_counts,
            report_paths=[str(p) for p in report_paths],
            storage_locations=storage_locations,
            exceptions=exceptions,
            reconciliation_summary=reconciliation_summary,
        )


def create_engine(config_dir: Path) -> CommissionEngine:
    """Load config and create an engine instance.

    Convenience function that loads all YAML configuration from a directory
    and returns a ready-to-use CommissionEngine.

    Args:
        config_dir: Path to the configuration directory.

    Returns:
        A fully initialized CommissionEngine.

    Raises:
        ConfigurationError: If configuration files are missing or malformed.
    """
    config = load_config(config_dir)
    return CommissionEngine(config)
