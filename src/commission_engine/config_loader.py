"""Configuration loading and validation for the Channel Partner Commission Engine."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

from commission_engine.exceptions import ConfigurationError


# --- Slab-related dataclasses ---


@dataclass
class PayoutSlab:
    """A single commission rate slab with min/max range."""

    min: float
    max: Optional[float]
    rate_type: str
    rate: float


@dataclass
class SequenceRules:
    """Multiplier rules for first vs subsequent disbursements."""

    first_disbursement_multiplier: float
    subsequent_disbursement_multiplier: float


@dataclass
class LoanSequenceTier:
    """Rate adjustment tier based on loan sequence position."""

    sequence_min: int
    sequence_max: Optional[int]
    rate_adjustment: float


@dataclass
class SlabConfig:
    """Commission slab configuration for a specific loan product."""

    product: str
    slab_basis: str
    slabs: list[PayoutSlab]
    sequence_rules: SequenceRules
    loan_sequence_tiers: list[LoanSequenceTier]


# --- Eligibility rule dataclass ---


@dataclass
class EligibilityRule:
    """A single eligibility rule for commission qualification."""

    id: str
    description: str
    product: str
    field: str
    operator: str
    value: Any


# --- Contest dataclass ---


@dataclass
class ContestDefinition:
    """A contest incentive program definition."""

    id: str
    type: str
    qualification_rule: dict[str, Any]
    payout: dict[str, Any]


# --- Deduction dataclass ---


@dataclass
class DeductionConfig:
    """Deduction rate configuration for corporate and non-corporate partners."""

    corporate_gst_rate: float
    corporate_tds_rate: float
    corporate_formula: str
    non_corporate_gst_rate: float
    non_corporate_tds_rate: float
    non_corporate_formula: str


# --- Top-level engine config ---


@dataclass
class EngineConfig:
    """Top-level configuration holding all engine settings."""

    warehouse: dict[str, Any]
    storage: dict[str, Any]
    reconciliation: dict[str, Any]
    processing: dict[str, Any]
    slabs: dict[str, SlabConfig] = field(default_factory=dict)
    eligibility_rules: list[EligibilityRule] = field(default_factory=list)
    contests: list[ContestDefinition] = field(default_factory=list)
    deductions: Optional[DeductionConfig] = None


# --- Parsing helpers ---


def _parse_slab_file(filepath: Path) -> SlabConfig:
    """Parse a single slab YAML file into a SlabConfig."""
    data = _load_yaml(filepath)

    required_keys = ["product", "slab_basis", "slabs", "sequence_rules", "loan_sequence_tiers"]
    for key in required_keys:
        if key not in data:
            raise ConfigurationError(str(filepath), f"Missing required key: '{key}'")

    slabs = [
        PayoutSlab(
            min=s["min"],
            max=s.get("max"),
            rate_type=s["rate_type"],
            rate=s["rate"],
        )
        for s in data["slabs"]
    ]

    seq_rules_data = data["sequence_rules"]
    sequence_rules = SequenceRules(
        first_disbursement_multiplier=seq_rules_data["first_disbursement_multiplier"],
        subsequent_disbursement_multiplier=seq_rules_data["subsequent_disbursement_multiplier"],
    )

    loan_sequence_tiers = [
        LoanSequenceTier(
            sequence_min=t["sequence_min"],
            sequence_max=t.get("sequence_max"),
            rate_adjustment=t["rate_adjustment"],
        )
        for t in data["loan_sequence_tiers"]
    ]

    return SlabConfig(
        product=data["product"],
        slab_basis=data["slab_basis"],
        slabs=slabs,
        sequence_rules=sequence_rules,
        loan_sequence_tiers=loan_sequence_tiers,
    )


def _parse_eligibility_rules(filepath: Path) -> list[EligibilityRule]:
    """Parse eligibility_rules.yaml into a list of EligibilityRule."""
    data = _load_yaml(filepath)

    if "rules" not in data:
        raise ConfigurationError(str(filepath), "Missing required key: 'rules'")

    rules = []
    for rule_data in data["rules"]:
        required_fields = ["id", "description", "product", "field", "operator", "value"]
        for f in required_fields:
            if f not in rule_data:
                raise ConfigurationError(
                    str(filepath),
                    f"Rule missing required field: '{f}'",
                )
        rules.append(
            EligibilityRule(
                id=rule_data["id"],
                description=rule_data["description"],
                product=rule_data["product"],
                field=rule_data["field"],
                operator=rule_data["operator"],
                value=rule_data["value"],
            )
        )
    return rules


def _parse_contests(filepath: Path) -> list[ContestDefinition]:
    """Parse contests.yaml into a list of ContestDefinition."""
    data = _load_yaml(filepath)

    if "contests" not in data:
        raise ConfigurationError(str(filepath), "Missing required key: 'contests'")

    contests = []
    for contest_data in data["contests"]:
        required_fields = ["id", "type", "qualification_rule", "payout"]
        for f in required_fields:
            if f not in contest_data:
                raise ConfigurationError(
                    str(filepath),
                    f"Contest missing required field: '{f}'",
                )
        contests.append(
            ContestDefinition(
                id=contest_data["id"],
                type=contest_data["type"],
                qualification_rule=contest_data["qualification_rule"],
                payout=contest_data["payout"],
            )
        )
    return contests


def _parse_deductions(filepath: Path) -> DeductionConfig:
    """Parse deductions.yaml into a DeductionConfig."""
    data = _load_yaml(filepath)

    for section in ["corporate", "non_corporate"]:
        if section not in data:
            raise ConfigurationError(str(filepath), f"Missing required section: '{section}'")
        required_keys = ["gst_rate", "tds_rate", "formula"]
        for key in required_keys:
            if key not in data[section]:
                raise ConfigurationError(
                    str(filepath),
                    f"Section '{section}' missing required key: '{key}'",
                )

    return DeductionConfig(
        corporate_gst_rate=data["corporate"]["gst_rate"],
        corporate_tds_rate=data["corporate"]["tds_rate"],
        corporate_formula=data["corporate"]["formula"],
        non_corporate_gst_rate=data["non_corporate"]["gst_rate"],
        non_corporate_tds_rate=data["non_corporate"]["tds_rate"],
        non_corporate_formula=data["non_corporate"]["formula"],
    )


def _load_yaml(filepath: Path) -> dict[str, Any]:
    """Load and parse a YAML file, raising ConfigurationError on failure."""
    if not filepath.exists():
        raise ConfigurationError(str(filepath), "File not found")

    try:
        with open(filepath, "r") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigurationError(str(filepath), f"YAML parse error: {e}")

    if not isinstance(data, dict):
        raise ConfigurationError(str(filepath), "Expected a YAML mapping at top level")

    return data


def _parse_settings(filepath: Path) -> dict[str, Any]:
    """Parse settings.yaml and validate required top-level sections."""
    data = _load_yaml(filepath)

    required_sections = ["warehouse", "storage", "reconciliation", "processing"]
    for section in required_sections:
        if section not in data:
            raise ConfigurationError(str(filepath), f"Missing required section: '{section}'")

    return data


# --- Public API ---


def load_config(config_dir: Path) -> EngineConfig:
    """Load all configuration files from config_dir and return a fully populated EngineConfig.

    Args:
        config_dir: Path to the configuration directory containing settings.yaml,
                    slabs/, eligibility_rules.yaml, contests.yaml, deductions.yaml.

    Returns:
        A fully populated EngineConfig instance.

    Raises:
        ConfigurationError: If any config file is missing, malformed, or incomplete.
    """
    config_dir = Path(config_dir)

    if not config_dir.is_dir():
        raise ConfigurationError(str(config_dir), "Configuration directory not found")

    # 1. Load settings.yaml
    settings_path = config_dir / "settings.yaml"
    settings = _parse_settings(settings_path)

    # 2. Load all slab YAML files from config/slabs/
    slabs_dir = config_dir / "slabs"
    slabs: dict[str, SlabConfig] = {}

    if slabs_dir.is_dir():
        slab_files = sorted(slabs_dir.glob("*.yaml"))
        if not slab_files:
            raise ConfigurationError(str(slabs_dir), "No slab YAML files found")
        for slab_file in slab_files:
            slab_config = _parse_slab_file(slab_file)
            slabs[slab_config.product] = slab_config
    else:
        raise ConfigurationError(str(slabs_dir), "Slabs directory not found")

    # 3. Load eligibility_rules.yaml
    eligibility_path = config_dir / "eligibility_rules.yaml"
    eligibility_rules = _parse_eligibility_rules(eligibility_path)

    # 4. Load contests.yaml
    contests_path = config_dir / "contests.yaml"
    contests = _parse_contests(contests_path)

    # 5. Load deductions.yaml
    deductions_path = config_dir / "deductions.yaml"
    deductions = _parse_deductions(deductions_path)

    # 6. Return fully populated EngineConfig
    return EngineConfig(
        warehouse=settings["warehouse"],
        storage=settings["storage"],
        reconciliation=settings["reconciliation"],
        processing=settings["processing"],
        slabs=slabs,
        eligibility_rules=eligibility_rules,
        contests=contests,
        deductions=deductions,
    )
