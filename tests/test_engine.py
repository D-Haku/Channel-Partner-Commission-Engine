"""Tests for the CommissionEngine orchestrator."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from commission_engine.config_loader import (
    DeductionConfig,
    EngineConfig,
    EligibilityRule,
    ContestDefinition,
    SlabConfig,
    PayoutSlab,
    SequenceRules,
    LoanSequenceTier,
)
from commission_engine.engine import CommissionEngine, create_engine
from commission_engine.exceptions import WarehouseConnectionError


@pytest.fixture
def sample_slab_config() -> dict[str, SlabConfig]:
    """Minimal slab config for PL product."""
    return {
        "PL": SlabConfig(
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
        ),
    }


@pytest.fixture
def sample_eligibility_rules() -> list[EligibilityRule]:
    """Minimal eligibility rules."""
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
    ]


@pytest.fixture
def sample_contests() -> list[ContestDefinition]:
    """Minimal contest definitions."""
    return [
        ContestDefinition(
            id="MONTHLY_PL_VOLUME",
            type="monthly",
            qualification_rule={
                "metric": "disbursement_count",
                "product": "PL",
                "operator": "gte",
                "threshold": 3,
            },
            payout={"type": "fixed", "amount": 5000},
        ),
    ]


@pytest.fixture
def sample_deduction_config() -> DeductionConfig:
    """Standard deduction configuration."""
    return DeductionConfig(
        corporate_gst_rate=0.18,
        corporate_tds_rate=0.10,
        corporate_formula="net = gross + gst - tds",
        non_corporate_gst_rate=0.0,
        non_corporate_tds_rate=0.05,
        non_corporate_formula="net = gross - tds",
    )


@pytest.fixture
def sample_engine_config(
    sample_slab_config,
    sample_eligibility_rules,
    sample_contests,
    sample_deduction_config,
    tmp_path,
) -> EngineConfig:
    """Build an EngineConfig pointing to a tmp_path DuckDB."""
    db_path = str(tmp_path / "test_warehouse.duckdb")
    return EngineConfig(
        warehouse={
            "backend": "duckdb",
            "duckdb": {"database_path": db_path},
        },
        storage={
            "backend": "local_fs",
            "local_fs": {"base_path": str(tmp_path / "output")},
        },
        reconciliation={"tolerance": 0.01},
        processing={"spark_mode": "local"},
        slabs=sample_slab_config,
        eligibility_rules=sample_eligibility_rules,
        contests=sample_contests,
        deductions=sample_deduction_config,
    )


@pytest.fixture
def seeded_db(sample_engine_config) -> str:
    """Create and seed a DuckDB database with test data, return the path."""
    db_path = sample_engine_config.warehouse["duckdb"]["database_path"]
    conn = duckdb.connect(db_path)

    # Create tables
    conn.execute("""
        CREATE TABLE loans (
            lan VARCHAR,
            partner_id VARCHAR,
            loan_product VARCHAR,
            is_pl_prime BOOLEAN,
            sanctioned_amount DECIMAL(15,2),
            application_date DATE
        )
    """)
    conn.execute("""
        CREATE TABLE disbursements (
            disbursement_id VARCHAR,
            lan VARCHAR,
            partner_id VARCHAR,
            loan_product VARCHAR,
            disbursed_amount DECIMAL(15,2),
            disbursement_date DATE,
            cheque_handover_date DATE,
            disbursement_sequence INTEGER
        )
    """)
    conn.execute("""
        CREATE TABLE partners (
            partner_id VARCHAR,
            partner_name VARCHAR,
            partner_type VARCHAR,
            corporate_flag BOOLEAN,
            registration_date DATE,
            active BOOLEAN
        )
    """)

    # Seed partners
    conn.execute("""
        INSERT INTO partners VALUES
            ('P001', 'Alpha Corp', 'DSA', true, '2023-01-01', true),
            ('P002', 'Beta Individual', 'Connector', false, '2023-06-15', true),
            ('P003', 'Gamma Corp', 'DSA', true, '2022-03-01', false)
    """)

    # Seed loans
    conn.execute("""
        INSERT INTO loans VALUES
            ('LAN001', 'P001', 'PL', false, 200000.00, '2024-01-05'),
            ('LAN002', 'P001', 'PL', false, 800000.00, '2024-01-10'),
            ('LAN003', 'P002', 'PL', false, 300000.00, '2024-01-15'),
            ('LAN004', 'P003', 'PL', false, 100000.00, '2024-01-20')
    """)

    # Seed disbursements
    conn.execute("""
        INSERT INTO disbursements VALUES
            ('D001', 'LAN001', 'P001', 'PL', 200000.00, '2024-01-10', '2024-01-12', 1),
            ('D002', 'LAN002', 'P001', 'PL', 800000.00, '2024-01-15', '2024-01-18', 1),
            ('D003', 'LAN003', 'P002', 'PL', 300000.00, '2024-01-20', '2024-01-22', 1),
            ('D004', 'LAN004', 'P003', 'PL', 100000.00, '2024-01-25', '2024-01-28', 1)
    """)

    conn.close()
    return db_path


class TestCommissionEngineInstantiation:
    """Tests for engine construction."""

    def test_engine_instantiation(self, sample_engine_config):
        """Engine can be created from a valid EngineConfig."""
        engine = CommissionEngine(sample_engine_config)
        assert engine is not None
        assert engine._config is sample_engine_config

    def test_engine_sets_allocation_rules(self, sample_engine_config):
        """Engine sets default allocation rules: HL/LAP use cheque_handover_date."""
        # Add HL slab to test allocation rules
        sample_engine_config.slabs["HL"] = SlabConfig(
            product="HL",
            slab_basis="disbursed_amount",
            slabs=[PayoutSlab(min=0, max=None, rate_type="percentage", rate=0.30)],
            sequence_rules=SequenceRules(
                first_disbursement_multiplier=1.0,
                subsequent_disbursement_multiplier=0.5,
            ),
            loan_sequence_tiers=[
                LoanSequenceTier(sequence_min=1, sequence_max=None, rate_adjustment=0.0)
            ],
        )
        engine = CommissionEngine(sample_engine_config)
        assert engine._calculator.allocation_rules["HL"] == "cheque_handover_date"
        assert engine._calculator.allocation_rules["PL"] == "disbursement_date"

    def test_engine_config_id_generated(self, sample_engine_config):
        """Engine generates a config_id from warehouse config."""
        engine = CommissionEngine(sample_engine_config)
        assert engine._config_id is not None
        assert isinstance(engine._config_id, str)


class TestCommissionEngineRun:
    """Tests for the full engine.run() pipeline."""

    def test_full_run_returns_processing_run_result(
        self, sample_engine_config, seeded_db
    ):
        """Engine.run() returns a ProcessingRunResult with expected fields."""
        engine = CommissionEngine(sample_engine_config)
        result = engine.run(cycle="2024-01", cutoff_date=date(2024, 1, 31))

        assert result.cycle == "2024-01"
        assert result.cutoff_date == date(2024, 1, 31)
        assert result.config_id is not None
        assert "extracted_loans" in result.record_counts
        assert "extracted_disbursements" in result.record_counts
        assert "extracted_partners" in result.record_counts
        assert "valid_disbursements" in result.record_counts
        assert "excluded_disbursements" in result.record_counts
        assert "eligible_commissions" in result.record_counts
        assert "contest_qualifications" in result.record_counts

    def test_full_run_generates_reports(self, sample_engine_config, seeded_db, tmp_path):
        """Engine.run() generates report files."""
        engine = CommissionEngine(sample_engine_config)
        result = engine.run(cycle="2024-01", cutoff_date=date(2024, 1, 31))

        # At least payout and contest reports
        assert len(result.report_paths) >= 2
        for path in result.report_paths:
            assert Path(path).exists()

    def test_full_run_uploads_reports(self, sample_engine_config, seeded_db, tmp_path):
        """Engine.run() uploads reports and returns storage locations."""
        engine = CommissionEngine(sample_engine_config)
        result = engine.run(cycle="2024-01", cutoff_date=date(2024, 1, 31))

        assert len(result.storage_locations) >= 2
        for loc in result.storage_locations:
            assert Path(loc).exists()

    def test_full_run_record_counts_consistent(
        self, sample_engine_config, seeded_db
    ):
        """Extracted records flow through pipeline: valid + excluded == extracted."""
        engine = CommissionEngine(sample_engine_config)
        result = engine.run(cycle="2024-01", cutoff_date=date(2024, 1, 31))

        extracted = result.record_counts["extracted_disbursements"]
        valid = result.record_counts["valid_disbursements"]
        excluded = result.record_counts["excluded_disbursements"]
        assert valid + excluded == extracted

    def test_full_run_with_reconciliation(self, sample_engine_config, seeded_db):
        """Engine.run() with reference_data produces a reconciliation summary."""
        engine = CommissionEngine(sample_engine_config)

        # Provide reference data that partially matches
        reference_data = pd.DataFrame({
            "lan": ["LAN001", "LAN002", "LAN005"],
            "reference_amount": [950.00, 5600.00, 1000.00],
        })

        result = engine.run(
            cycle="2024-01",
            cutoff_date=date(2024, 1, 31),
            reference_data=reference_data,
        )

        assert result.reconciliation_summary is not None
        assert len(result.report_paths) >= 3  # payout, contest, reconciliation

    def test_full_run_without_reconciliation(self, sample_engine_config, seeded_db):
        """Engine.run() without reference_data skips reconciliation."""
        engine = CommissionEngine(sample_engine_config)
        result = engine.run(cycle="2024-01", cutoff_date=date(2024, 1, 31))

        assert result.reconciliation_summary is None
        assert len(result.report_paths) == 2  # payout and contest only

    def test_connection_error_propagates(self, sample_engine_config):
        """Engine.run() propagates WarehouseConnectionError."""
        # Point to non-existent DB path that will fail
        sample_engine_config.warehouse["duckdb"]["database_path"] = "/nonexistent/path.duckdb"
        engine = CommissionEngine(sample_engine_config)

        with pytest.raises(WarehouseConnectionError):
            engine.run(cycle="2024-01", cutoff_date=date(2024, 1, 31))

    def test_validation_exceptions_collected(self, sample_engine_config, tmp_path):
        """Engine collects validation exceptions and continues with valid records."""
        # Create a DB with some invalid records
        db_path = sample_engine_config.warehouse["duckdb"]["database_path"]
        conn = duckdb.connect(db_path)

        conn.execute("""
            CREATE TABLE loans (
                lan VARCHAR, partner_id VARCHAR, loan_product VARCHAR,
                is_pl_prime BOOLEAN, sanctioned_amount DECIMAL(15,2), application_date DATE
            )
        """)
        conn.execute("""
            CREATE TABLE disbursements (
                disbursement_id VARCHAR, lan VARCHAR, partner_id VARCHAR,
                loan_product VARCHAR, disbursed_amount DECIMAL(15,2),
                disbursement_date DATE, cheque_handover_date DATE, disbursement_sequence INTEGER
            )
        """)
        conn.execute("""
            CREATE TABLE partners (
                partner_id VARCHAR, partner_name VARCHAR, partner_type VARCHAR,
                corporate_flag BOOLEAN, registration_date DATE, active BOOLEAN
            )
        """)

        conn.execute("INSERT INTO partners VALUES ('P001', 'Test', 'DSA', true, '2024-01-01', true)")
        conn.execute("INSERT INTO loans VALUES ('LAN001', 'P001', 'PL', false, 200000, '2024-01-01')")

        # Valid record
        conn.execute("""
            INSERT INTO disbursements VALUES
                ('D001', 'LAN001', 'P001', 'PL', 200000, '2024-01-10', '2024-01-12', 1)
        """)
        # Invalid record - missing LAN
        conn.execute("""
            INSERT INTO disbursements VALUES
                ('D002', NULL, 'P001', 'PL', 100000, '2024-01-15', NULL, 1)
        """)
        # Invalid record - unmatched partner
        conn.execute("""
            INSERT INTO disbursements VALUES
                ('D003', 'LAN002', 'P999', 'PL', 50000, '2024-01-20', NULL, 1)
        """)

        conn.close()

        engine = CommissionEngine(sample_engine_config)
        result = engine.run(cycle="2024-01", cutoff_date=date(2024, 1, 31))

        assert result.record_counts["valid_disbursements"] == 1
        assert result.record_counts["excluded_disbursements"] == 2
        assert len(result.exceptions) == 2


class TestCreateEngine:
    """Tests for the create_engine convenience function."""

    def test_create_engine_from_config_dir(self, tmp_path):
        """create_engine loads config from directory and returns a CommissionEngine."""
        # Set up minimal config directory
        config_dir = tmp_path / "config"
        config_dir.mkdir()

        # settings.yaml
        (config_dir / "settings.yaml").write_text(
            """
warehouse:
  backend: duckdb
  duckdb:
    database_path: data/warehouse.duckdb
storage:
  backend: local_fs
  local_fs:
    base_path: output/
reconciliation:
  tolerance: 0.01
processing:
  spark_mode: local
"""
        )

        # slabs directory
        slabs_dir = config_dir / "slabs"
        slabs_dir.mkdir()
        (slabs_dir / "personal_loan.yaml").write_text(
            """
product: PL
slab_basis: disbursed_amount
slabs:
  - min: 0
    max: 500000
    rate_type: percentage
    rate: 0.50
  - min: 500001
    max: null
    rate_type: percentage
    rate: 0.75
sequence_rules:
  first_disbursement_multiplier: 1.0
  subsequent_disbursement_multiplier: 0.5
loan_sequence_tiers:
  - sequence_min: 1
    sequence_max: null
    rate_adjustment: 0.0
"""
        )

        # eligibility_rules.yaml
        (config_dir / "eligibility_rules.yaml").write_text(
            """
rules:
  - id: MIN_DISBURSEMENT
    description: Minimum disbursement amount
    product: ALL
    field: disbursed_amount
    operator: gte
    value: 10000
"""
        )

        # contests.yaml
        (config_dir / "contests.yaml").write_text(
            """
contests:
  - id: MONTHLY_PL_VOLUME
    type: monthly
    qualification_rule:
      metric: disbursement_count
      product: PL
      operator: gte
      threshold: 10
    payout:
      type: fixed
      amount: 5000
"""
        )

        # deductions.yaml
        (config_dir / "deductions.yaml").write_text(
            """
corporate:
  gst_rate: 0.18
  tds_rate: 0.10
  formula: "net = gross + gst - tds"
non_corporate:
  gst_rate: 0.0
  tds_rate: 0.05
  formula: "net = gross - tds"
"""
        )

        engine = create_engine(config_dir)
        assert isinstance(engine, CommissionEngine)
