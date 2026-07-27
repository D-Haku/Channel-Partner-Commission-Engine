"""Validation Module for the Channel Partner Commission Engine.

Checks extracted disbursement records for completeness, type conformance,
and referential integrity before commission calculation.
"""

from __future__ import annotations

import pandas as pd

from .exceptions import ValidationException
from .models import ValidationResult


class Validator:
    """Validates disbursement records against completeness and integrity rules.

    Validation rules are applied in order per record; the first failure
    determines the exclusion reason for that record.
    """

    def validate(
        self, disbursements: pd.DataFrame, partners: pd.DataFrame
    ) -> ValidationResult:
        """Validate disbursement records and return a ValidationResult.

        Parameters
        ----------
        disbursements : pd.DataFrame
            DataFrame with columns: disbursement_id, lan, partner_id,
            loan_product, disbursed_amount, disbursement_date,
            cheque_handover_date, disbursement_sequence.
        partners : pd.DataFrame
            DataFrame with columns: partner_id, partner_name, partner_type,
            corporate_flag, registration_date, active.

        Returns
        -------
        ValidationResult
            Contains valid records, exception list, counts, and reasons.
        """
        exception_list: list[ValidationException] = []
        exclusion_reasons: dict[str, int] = {}
        valid_mask = pd.Series([True] * len(disbursements), index=disbursements.index)

        # Build set of valid partner IDs for efficient lookup
        valid_partner_ids = set(partners["partner_id"].dropna().astype(str))

        for idx, row in disbursements.iterrows():
            reason = self._check_record(row, valid_partner_ids)
            if reason is not None:
                field, reason_str = reason
                valid_mask.at[idx] = False

                # Determine record_id: use lan if available, otherwise disbursement_id
                record_id = str(row.get("disbursement_id", ""))
                lan_value = row.get("lan")
                if not self._is_null_or_empty(lan_value):
                    record_id = str(lan_value)

                exception_list.append(
                    ValidationException(
                        record_id=record_id,
                        field=field,
                        reason=reason_str,
                        record_data=row.to_dict(),
                    )
                )
                exclusion_reasons[reason_str] = (
                    exclusion_reasons.get(reason_str, 0) + 1
                )

        valid_disbursements = disbursements[valid_mask].reset_index(drop=True)
        valid_count = len(valid_disbursements)
        excluded_count = len(exception_list)

        return ValidationResult(
            valid_disbursements=valid_disbursements,
            exception_list=exception_list,
            valid_count=valid_count,
            excluded_count=excluded_count,
            exclusion_reasons=exclusion_reasons,
        )

    def _check_record(
        self, row: pd.Series, valid_partner_ids: set[str]
    ) -> tuple[str, str] | None:
        """Check a single record against validation rules in order.

        Returns the first failing (field, reason) tuple, or None if valid.
        """
        # Rule 1: LAN must be present and non-empty
        lan = row.get("lan")
        if self._is_null_or_empty(lan):
            return ("lan", "missing_lan")

        # Rule 2: loan_product must be present and non-empty
        loan_product = row.get("loan_product")
        if self._is_null_or_empty(loan_product):
            return ("loan_product", "missing_loan_product")

        # Rule 3: partner_id must be present and non-empty
        partner_id = row.get("partner_id")
        if self._is_null_or_empty(partner_id):
            return ("partner_id", "missing_partner_id")

        # Rule 4: disbursement_date must not be null
        disbursement_date = row.get("disbursement_date")
        if pd.isna(disbursement_date):
            return ("disbursement_date", "missing_disbursement_date")

        # Rule 5: disbursed_amount must be numeric, positive (> 0)
        disbursed_amount = row.get("disbursed_amount")
        if not self._is_valid_amount(disbursed_amount):
            return ("disbursed_amount", "invalid_disbursed_amount")

        # Rule 6: partner_id must have a matching record in partners
        if str(partner_id) not in valid_partner_ids:
            return ("partner_id", "unmatched_partner")

        return None

    @staticmethod
    def _is_null_or_empty(value) -> bool:
        """Check if a value is null, NaN, or an empty string."""
        if value is None:
            return True
        if isinstance(value, float) and pd.isna(value):
            return True
        if pd.isna(value):
            return True
        if isinstance(value, str) and value.strip() == "":
            return True
        return False

    @staticmethod
    def _is_valid_amount(value) -> bool:
        """Check if a value is numeric and positive (greater than zero)."""
        if value is None:
            return False
        if isinstance(value, float) and pd.isna(value):
            return False
        try:
            if pd.isna(value):
                return False
        except (TypeError, ValueError):
            pass
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            return False
        if numeric_value <= 0:
            return False
        return True
