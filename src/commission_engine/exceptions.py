"""Custom exceptions for the Channel Partner Commission Engine."""

from dataclasses import dataclass, field


class CommissionEngineError(Exception):
    """Base exception for all engine errors."""

    pass


class WarehouseConnectionError(CommissionEngineError):
    """Warehouse or storage connection failure."""

    def __init__(self, target: str, detail: str) -> None:
        self.target = target
        self.detail = detail
        super().__init__(f"Connection to '{target}' failed: {detail}")


class ConfigurationError(CommissionEngineError):
    """Invalid or incomplete configuration."""

    def __init__(self, config_path: str, issue: str) -> None:
        self.config_path = config_path
        self.issue = issue
        super().__init__(f"Configuration error in '{config_path}': {issue}")


@dataclass
class ValidationException:
    """A record-level validation failure (not raised, collected)."""

    record_id: str
    field: str
    reason: str
    record_data: dict = field(default_factory=dict)
