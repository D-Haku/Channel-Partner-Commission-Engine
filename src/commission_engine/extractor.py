"""Data Extractor module with warehouse backend abstraction.

Provides a Protocol-based interface for warehouse backends and a DuckDB
implementation for local development. The DataExtractor class orchestrates
extraction of loans, disbursements, and partners into pandas DataFrames.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

import duckdb
import pandas as pd

from .exceptions import WarehouseConnectionError
from .models import ExtractionResult


@runtime_checkable
class WarehouseBackend(Protocol):
    """Protocol defining the interface for warehouse data access."""

    def connect(self) -> None:
        """Establish a connection to the warehouse.

        Raises:
            WarehouseConnectionError: If the connection cannot be established.
        """
        ...

    def extract_loans(self, cycle: str, cutoff_date: date) -> pd.DataFrame:
        """Extract loan records for the given cycle.

        Args:
            cycle: The processing cycle identifier (e.g., '2024-01').
            cutoff_date: The cutoff date for the cycle.

        Returns:
            A pandas DataFrame containing loan records.
        """
        ...

    def extract_disbursements(self, cycle: str, cutoff_date: date) -> pd.DataFrame:
        """Extract disbursement records up to the cutoff date.

        Args:
            cycle: The processing cycle identifier.
            cutoff_date: Only disbursements on or before this date are included.

        Returns:
            A pandas DataFrame containing disbursement records.
        """
        ...

    def extract_partners(self) -> pd.DataFrame:
        """Extract all partner records.

        Returns:
            A pandas DataFrame containing partner records.
        """
        ...


class DuckDBBackend:
    """DuckDB-based warehouse backend for local development.

    Connects to a DuckDB database file and extracts loan, disbursement,
    and partner data using SQL queries.
    """

    def __init__(self, database_path: str) -> None:
        """Initialize with the path to a DuckDB database file.

        Args:
            database_path: File path to the DuckDB database.
        """
        self._database_path = database_path
        self._connection: duckdb.DuckDBPyConnection | None = None

    def connect(self) -> None:
        """Open a connection to the DuckDB database.

        Raises:
            WarehouseConnectionError: If the database cannot be opened.
        """
        try:
            self._connection = duckdb.connect(self._database_path)
        except Exception as e:
            raise WarehouseConnectionError(
                target=self._database_path,
                detail=str(e),
            )

    def extract_loans(self, cycle: str, cutoff_date: date) -> pd.DataFrame:
        """Extract loan records for the given cycle.

        Retrieves all loans with an application_date up to the cutoff_date.

        Args:
            cycle: The processing cycle identifier.
            cutoff_date: The cutoff date bounding which loans are included.

        Returns:
            A pandas DataFrame of loan records.

        Raises:
            WarehouseConnectionError: If the query fails.
        """
        try:
            query = """
                SELECT *
                FROM loans
                WHERE application_date <= ?
            """
            return self._connection.execute(query, [cutoff_date]).fetchdf()
        except Exception as e:
            raise WarehouseConnectionError(
                target=self._database_path,
                detail=f"Failed to extract loans: {e}",
            )

    def extract_disbursements(self, cycle: str, cutoff_date: date) -> pd.DataFrame:
        """Extract disbursement records up to the cutoff date.

        Args:
            cycle: The processing cycle identifier.
            cutoff_date: Only disbursements on or before this date are included.

        Returns:
            A pandas DataFrame of disbursement records.

        Raises:
            WarehouseConnectionError: If the query fails.
        """
        try:
            query = """
                SELECT *
                FROM disbursements
                WHERE disbursement_date <= ?
            """
            return self._connection.execute(query, [cutoff_date]).fetchdf()
        except Exception as e:
            raise WarehouseConnectionError(
                target=self._database_path,
                detail=f"Failed to extract disbursements: {e}",
            )

    def extract_partners(self) -> pd.DataFrame:
        """Extract all partner records.

        Returns:
            A pandas DataFrame of partner records.

        Raises:
            WarehouseConnectionError: If the query fails.
        """
        try:
            query = "SELECT * FROM partners"
            return self._connection.execute(query).fetchdf()
        except Exception as e:
            raise WarehouseConnectionError(
                target=self._database_path,
                detail=f"Failed to extract partners: {e}",
            )


class DataExtractor:
    """Orchestrates data extraction from a warehouse backend.

    Connects to the backend, extracts all required datasets, and
    returns an ExtractionResult with record counts.
    """

    def __init__(self, backend: WarehouseBackend) -> None:
        """Initialize with a warehouse backend.

        Args:
            backend: An object implementing the WarehouseBackend protocol.
        """
        self._backend = backend

    def extract(self, cycle: str, cutoff_date: date) -> ExtractionResult:
        """Run full extraction for a processing cycle.

        Connects to the warehouse, extracts loans, disbursements, and
        partners, then returns an ExtractionResult with record counts.

        Args:
            cycle: The processing cycle identifier (e.g., '2024-01').
            cutoff_date: The cutoff date for the cycle.

        Returns:
            An ExtractionResult containing DataFrames and record counts.

        Raises:
            WarehouseConnectionError: If connection or extraction fails.
        """
        self._backend.connect()

        loans_df = self._backend.extract_loans(cycle, cutoff_date)
        disbursements_df = self._backend.extract_disbursements(cycle, cutoff_date)
        partners_df = self._backend.extract_partners()

        record_counts = {
            "loans": len(loans_df),
            "disbursements": len(disbursements_df),
            "partners": len(partners_df),
        }

        return ExtractionResult(
            loans_df=loans_df,
            disbursements_df=disbursements_df,
            partners_df=partners_df,
            record_counts=record_counts,
        )
