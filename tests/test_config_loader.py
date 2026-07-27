"""Unit tests for config_loader module."""

import tempfile
from pathlib import Path

import pytest

from commission_engine.config_loader import (
    DeductionConfig,
    EligibilityRule,
    EngineConfig,
    ContestDefinition,
    LoanSequenceTier,
    PayoutSlab,
    SequenceRules,
    SlabConfig,
    load_config,
)
from commission_engine.exceptions import ConfigurationError


@pytest.fixture
def config_dir() -> Path:
    """Return the path to the actual config directory."""
    return Path(__file__).parent.parent / "config"


class TestLoadConfig:
    """Tests for the load_config function with actual config files."""

    def test_loads_successfully(self, config_dir: Path) -> None:
        config = load_config(config_dir)
        assert isinstance(config, EngineConfig)

    def test_warehouse_settings(self, config_dir: Path) -> None:
        config = load_config(config_dir)
        assert config.warehouse["backend"] == "duckdb"
        assert "duckdb" in config.warehouse
        assert config.warehouse["duckdb"]["database_path"] == "data/warehouse.duckdb"

    def test_storage_settings(self, config_dir: Path) -> None:
        config = load_config(config_dir)
        assert config.storage["backend"] == "local_fs"
        assert config.storage["local_fs"]["base_path"] == "output/"

    def test_reconciliation_settings(self, config_dir: Path) -> None:
        config = load_config(config_dir)
        assert config.reconciliation["tolerance"] == 0.01

    def test_processing_settings(self, config_dir: Path) -> None:
        config = load_config(config_dir)
        assert config.processing["spark_mode"] == "local"

    def test_slabs_loaded(self, config_dir: Path) -> None:
        config = load_config(config_dir)
        assert len(config.slabs) == 7
        expected_products = {"PL", "HL", "MSME", "LAP", "UBL", "CSC", "PL_PRIME"}
        assert set(config.slabs.keys()) == expected_products

    def test_slab_structure(self, config_dir: Path) -> None:
        config = load_config(config_dir)
        pl_slab = config.slabs["PL"]
        assert isinstance(pl_slab, SlabConfig)
        assert pl_slab.product == "PL"
        assert pl_slab.slab_basis == "disbursed_amount"
        assert len(pl_slab.slabs) == 3
        assert isinstance(pl_slab.slabs[0], PayoutSlab)
        assert isinstance(pl_slab.sequence_rules, SequenceRules)
        assert len(pl_slab.loan_sequence_tiers) == 2
        assert isinstance(pl_slab.loan_sequence_tiers[0], LoanSequenceTier)

    def test_slab_values(self, config_dir: Path) -> None:
        config = load_config(config_dir)
        pl_slab = config.slabs["PL"]
        assert pl_slab.slabs[0].min == 0
        assert pl_slab.slabs[0].max == 500000
        assert pl_slab.slabs[0].rate_type == "percentage"
        assert pl_slab.slabs[0].rate == 0.50
        # Last slab has unbounded upper
        assert pl_slab.slabs[2].max is None

    def test_sequence_rules(self, config_dir: Path) -> None:
        config = load_config(config_dir)
        pl_slab = config.slabs["PL"]
        assert pl_slab.sequence_rules.first_disbursement_multiplier == 1.0
        assert pl_slab.sequence_rules.subsequent_disbursement_multiplier == 0.5

    def test_loan_sequence_tiers(self, config_dir: Path) -> None:
        config = load_config(config_dir)
        pl_slab = config.slabs["PL"]
        assert pl_slab.loan_sequence_tiers[0].sequence_min == 1
        assert pl_slab.loan_sequence_tiers[0].sequence_max == 5
        assert pl_slab.loan_sequence_tiers[0].rate_adjustment == 0.0
        assert pl_slab.loan_sequence_tiers[1].sequence_max is None

    def test_eligibility_rules_loaded(self, config_dir: Path) -> None:
        config = load_config(config_dir)
        assert len(config.eligibility_rules) == 3
        assert all(isinstance(r, EligibilityRule) for r in config.eligibility_rules)

    def test_eligibility_rule_values(self, config_dir: Path) -> None:
        config = load_config(config_dir)
        min_disbursement = config.eligibility_rules[0]
        assert min_disbursement.id == "MIN_DISBURSEMENT"
        assert min_disbursement.product == "ALL"
        assert min_disbursement.field == "disbursed_amount"
        assert min_disbursement.operator == "gte"
        assert min_disbursement.value == 10000

    def test_contests_loaded(self, config_dir: Path) -> None:
        config = load_config(config_dir)
        assert len(config.contests) == 2
        assert all(isinstance(c, ContestDefinition) for c in config.contests)

    def test_contest_values(self, config_dir: Path) -> None:
        config = load_config(config_dir)
        monthly = config.contests[0]
        assert monthly.id == "MONTHLY_PL_VOLUME"
        assert monthly.type == "monthly"
        assert monthly.qualification_rule["metric"] == "disbursement_count"
        assert monthly.payout["type"] == "fixed"
        assert monthly.payout["amount"] == 5000

    def test_deductions_loaded(self, config_dir: Path) -> None:
        config = load_config(config_dir)
        assert isinstance(config.deductions, DeductionConfig)
        assert config.deductions.corporate_gst_rate == 0.18
        assert config.deductions.corporate_tds_rate == 0.10
        assert config.deductions.non_corporate_gst_rate == 0.0
        assert config.deductions.non_corporate_tds_rate == 0.05


class TestConfigErrors:
    """Tests for error handling in config loading."""

    def test_nonexistent_directory(self) -> None:
        with pytest.raises(ConfigurationError) as exc_info:
            load_config(Path("/nonexistent/path"))
        assert "Configuration directory not found" in str(exc_info.value)

    def test_missing_settings_file(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigurationError) as exc_info:
            load_config(tmp_path)
        assert "File not found" in str(exc_info.value)

    def test_malformed_yaml(self, tmp_path: Path) -> None:
        (tmp_path / "settings.yaml").write_text(": invalid: [[[")
        with pytest.raises(ConfigurationError) as exc_info:
            load_config(tmp_path)
        assert "YAML parse error" in str(exc_info.value)

    def test_missing_settings_section(self, tmp_path: Path) -> None:
        (tmp_path / "settings.yaml").write_text("warehouse:\n  backend: duckdb\n")
        with pytest.raises(ConfigurationError) as exc_info:
            load_config(tmp_path)
        assert "Missing required section" in str(exc_info.value)

    def test_missing_slabs_directory(self, tmp_path: Path) -> None:
        (tmp_path / "settings.yaml").write_text(
            "warehouse:\n  backend: x\nstorage:\n  backend: y\n"
            "reconciliation:\n  tolerance: 0.01\nprocessing:\n  spark_mode: local\n"
        )
        with pytest.raises(ConfigurationError) as exc_info:
            load_config(tmp_path)
        assert "Slabs directory not found" in str(exc_info.value)

    def test_empty_slabs_directory(self, tmp_path: Path) -> None:
        (tmp_path / "settings.yaml").write_text(
            "warehouse:\n  backend: x\nstorage:\n  backend: y\n"
            "reconciliation:\n  tolerance: 0.01\nprocessing:\n  spark_mode: local\n"
        )
        (tmp_path / "slabs").mkdir()
        with pytest.raises(ConfigurationError) as exc_info:
            load_config(tmp_path)
        assert "No slab YAML files found" in str(exc_info.value)

    def test_slab_missing_required_key(self, tmp_path: Path) -> None:
        (tmp_path / "settings.yaml").write_text(
            "warehouse:\n  backend: x\nstorage:\n  backend: y\n"
            "reconciliation:\n  tolerance: 0.01\nprocessing:\n  spark_mode: local\n"
        )
        (tmp_path / "slabs").mkdir()
        (tmp_path / "slabs" / "bad.yaml").write_text("product: PL\n")
        with pytest.raises(ConfigurationError) as exc_info:
            load_config(tmp_path)
        assert "Missing required key" in str(exc_info.value)
