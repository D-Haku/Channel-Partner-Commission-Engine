"""Unit tests for the Validation Module."""

import numpy as np
import pandas as pd
import pytest

from commission_engine.validator import Validator


@pytest.fixture
def validator():
    """Create a Validator instance."""
    return Validator()


@pytest.fixture
def valid_partners():
    """Create a valid partners DataFrame."""
    return pd.DataFrame(
        {
            "partner_id": ["P001", "P002", "P003"],
            "partner_name": ["Alpha DSA", "Beta Connector", "Gamma DSA"],
            "partner_type": ["DSA", "Connector", "DSA"],
            "corporate_flag": [True, False, True],
            "registration_date": ["2023-01-01", "2023-06-15", "2022-11-20"],
            "active": [True, True, True],
        }
    )


@pytest.fixture
def valid_disbursements():
    """Create a fully valid disbursements DataFrame."""
    return pd.DataFrame(
        {
            "disbursement_id": ["D001", "D002", "D003"],
            "lan": ["LAN001", "LAN002", "LAN003"],
            "partner_id": ["P001", "P002", "P003"],
            "loan_product": ["PL", "HL", "MSME"],
            "disbursed_amount": [100000.0, 500000.0, 250000.0],
            "disbursement_date": ["2024-01-15", "2024-02-20", "2024-03-10"],
            "cheque_handover_date": ["2024-01-16", None, "2024-03-12"],
            "disbursement_sequence": [1, 1, 2],
        }
    )


class TestValidatorAllValid:
    """Test that all-valid records pass through without exceptions."""

    def test_all_valid_returns_correct_counts(
        self, validator, valid_disbursements, valid_partners
    ):
        result = validator.validate(valid_disbursements, valid_partners)
        assert result.valid_count == 3
        assert result.excluded_count == 0

    def test_all_valid_returns_empty_exception_list(
        self, validator, valid_disbursements, valid_partners
    ):
        result = validator.validate(valid_disbursements, valid_partners)
        assert result.exception_list == []

    def test_all_valid_returns_empty_exclusion_reasons(
        self, validator, valid_disbursements, valid_partners
    ):
        result = validator.validate(valid_disbursements, valid_partners)
        assert result.exclusion_reasons == {}

    def test_valid_disbursements_dataframe_shape(
        self, validator, valid_disbursements, valid_partners
    ):
        result = validator.validate(valid_disbursements, valid_partners)
        assert len(result.valid_disbursements) == 3
        assert list(result.valid_disbursements.columns) == list(
            valid_disbursements.columns
        )


class TestMissingLan:
    """Test rule 1: missing/null LAN exclusion."""

    def test_null_lan_excluded(self, validator, valid_partners):
        df = pd.DataFrame(
            {
                "disbursement_id": ["D001"],
                "lan": [None],
                "partner_id": ["P001"],
                "loan_product": ["PL"],
                "disbursed_amount": [100000.0],
                "disbursement_date": ["2024-01-01"],
                "cheque_handover_date": [None],
                "disbursement_sequence": [1],
            }
        )
        result = validator.validate(df, valid_partners)
        assert result.excluded_count == 1
        assert result.exception_list[0].reason == "missing_lan"
        assert result.exception_list[0].field == "lan"

    def test_empty_string_lan_excluded(self, validator, valid_partners):
        df = pd.DataFrame(
            {
                "disbursement_id": ["D001"],
                "lan": [""],
                "partner_id": ["P001"],
                "loan_product": ["PL"],
                "disbursed_amount": [100000.0],
                "disbursement_date": ["2024-01-01"],
                "cheque_handover_date": [None],
                "disbursement_sequence": [1],
            }
        )
        result = validator.validate(df, valid_partners)
        assert result.excluded_count == 1
        assert result.exception_list[0].reason == "missing_lan"

    def test_whitespace_lan_excluded(self, validator, valid_partners):
        df = pd.DataFrame(
            {
                "disbursement_id": ["D001"],
                "lan": ["   "],
                "partner_id": ["P001"],
                "loan_product": ["PL"],
                "disbursed_amount": [100000.0],
                "disbursement_date": ["2024-01-01"],
                "cheque_handover_date": [None],
                "disbursement_sequence": [1],
            }
        )
        result = validator.validate(df, valid_partners)
        assert result.excluded_count == 1
        assert result.exception_list[0].reason == "missing_lan"

    def test_missing_lan_uses_disbursement_id_as_record_id(
        self, validator, valid_partners
    ):
        df = pd.DataFrame(
            {
                "disbursement_id": ["D999"],
                "lan": [None],
                "partner_id": ["P001"],
                "loan_product": ["PL"],
                "disbursed_amount": [100000.0],
                "disbursement_date": ["2024-01-01"],
                "cheque_handover_date": [None],
                "disbursement_sequence": [1],
            }
        )
        result = validator.validate(df, valid_partners)
        assert result.exception_list[0].record_id == "D999"


class TestMissingLoanProduct:
    """Test rule 2: missing/null loan_product exclusion."""

    def test_null_loan_product_excluded(self, validator, valid_partners):
        df = pd.DataFrame(
            {
                "disbursement_id": ["D001"],
                "lan": ["LAN001"],
                "partner_id": ["P001"],
                "loan_product": [None],
                "disbursed_amount": [100000.0],
                "disbursement_date": ["2024-01-01"],
                "cheque_handover_date": [None],
                "disbursement_sequence": [1],
            }
        )
        result = validator.validate(df, valid_partners)
        assert result.excluded_count == 1
        assert result.exception_list[0].reason == "missing_loan_product"
        assert result.exception_list[0].field == "loan_product"

    def test_empty_loan_product_excluded(self, validator, valid_partners):
        df = pd.DataFrame(
            {
                "disbursement_id": ["D001"],
                "lan": ["LAN001"],
                "partner_id": ["P001"],
                "loan_product": [""],
                "disbursed_amount": [100000.0],
                "disbursement_date": ["2024-01-01"],
                "cheque_handover_date": [None],
                "disbursement_sequence": [1],
            }
        )
        result = validator.validate(df, valid_partners)
        assert result.exception_list[0].reason == "missing_loan_product"


class TestMissingPartnerId:
    """Test rule 3: missing/null partner_id exclusion."""

    def test_null_partner_id_excluded(self, validator, valid_partners):
        df = pd.DataFrame(
            {
                "disbursement_id": ["D001"],
                "lan": ["LAN001"],
                "partner_id": [None],
                "loan_product": ["PL"],
                "disbursed_amount": [100000.0],
                "disbursement_date": ["2024-01-01"],
                "cheque_handover_date": [None],
                "disbursement_sequence": [1],
            }
        )
        result = validator.validate(df, valid_partners)
        assert result.excluded_count == 1
        assert result.exception_list[0].reason == "missing_partner_id"
        assert result.exception_list[0].field == "partner_id"


class TestMissingDisbursementDate:
    """Test rule 4: missing disbursement_date exclusion."""

    def test_null_date_excluded(self, validator, valid_partners):
        df = pd.DataFrame(
            {
                "disbursement_id": ["D001"],
                "lan": ["LAN001"],
                "partner_id": ["P001"],
                "loan_product": ["PL"],
                "disbursed_amount": [100000.0],
                "disbursement_date": [None],
                "cheque_handover_date": [None],
                "disbursement_sequence": [1],
            }
        )
        result = validator.validate(df, valid_partners)
        assert result.excluded_count == 1
        assert result.exception_list[0].reason == "missing_disbursement_date"
        assert result.exception_list[0].field == "disbursement_date"


class TestInvalidDisbursedAmount:
    """Test rule 5: invalid disbursed_amount exclusion."""

    def test_null_amount_excluded(self, validator, valid_partners):
        df = pd.DataFrame(
            {
                "disbursement_id": ["D001"],
                "lan": ["LAN001"],
                "partner_id": ["P001"],
                "loan_product": ["PL"],
                "disbursed_amount": [None],
                "disbursement_date": ["2024-01-01"],
                "cheque_handover_date": [None],
                "disbursement_sequence": [1],
            }
        )
        result = validator.validate(df, valid_partners)
        assert result.exception_list[0].reason == "invalid_disbursed_amount"

    def test_negative_amount_excluded(self, validator, valid_partners):
        df = pd.DataFrame(
            {
                "disbursement_id": ["D001"],
                "lan": ["LAN001"],
                "partner_id": ["P001"],
                "loan_product": ["PL"],
                "disbursed_amount": [-50000.0],
                "disbursement_date": ["2024-01-01"],
                "cheque_handover_date": [None],
                "disbursement_sequence": [1],
            }
        )
        result = validator.validate(df, valid_partners)
        assert result.exception_list[0].reason == "invalid_disbursed_amount"

    def test_zero_amount_excluded(self, validator, valid_partners):
        df = pd.DataFrame(
            {
                "disbursement_id": ["D001"],
                "lan": ["LAN001"],
                "partner_id": ["P001"],
                "loan_product": ["PL"],
                "disbursed_amount": [0],
                "disbursement_date": ["2024-01-01"],
                "cheque_handover_date": [None],
                "disbursement_sequence": [1],
            }
        )
        result = validator.validate(df, valid_partners)
        assert result.exception_list[0].reason == "invalid_disbursed_amount"

    def test_non_numeric_amount_excluded(self, validator, valid_partners):
        df = pd.DataFrame(
            {
                "disbursement_id": ["D001"],
                "lan": ["LAN001"],
                "partner_id": ["P001"],
                "loan_product": ["PL"],
                "disbursed_amount": ["abc"],
                "disbursement_date": ["2024-01-01"],
                "cheque_handover_date": [None],
                "disbursement_sequence": [1],
            }
        )
        result = validator.validate(df, valid_partners)
        assert result.exception_list[0].reason == "invalid_disbursed_amount"


class TestUnmatchedPartner:
    """Test rule 6: unmatched partner_id exclusion."""

    def test_unmatched_partner_excluded(self, validator, valid_partners):
        df = pd.DataFrame(
            {
                "disbursement_id": ["D001"],
                "lan": ["LAN001"],
                "partner_id": ["P_NONEXISTENT"],
                "loan_product": ["PL"],
                "disbursed_amount": [100000.0],
                "disbursement_date": ["2024-01-01"],
                "cheque_handover_date": [None],
                "disbursement_sequence": [1],
            }
        )
        result = validator.validate(df, valid_partners)
        assert result.excluded_count == 1
        assert result.exception_list[0].reason == "unmatched_partner"
        assert result.exception_list[0].field == "partner_id"


class TestValidationOrder:
    """Test that the first failing rule determines the exclusion reason."""

    def test_missing_lan_takes_priority_over_missing_product(
        self, validator, valid_partners
    ):
        """If both LAN and loan_product are missing, reason should be missing_lan."""
        df = pd.DataFrame(
            {
                "disbursement_id": ["D001"],
                "lan": [None],
                "partner_id": ["P001"],
                "loan_product": [None],
                "disbursed_amount": [100000.0],
                "disbursement_date": ["2024-01-01"],
                "cheque_handover_date": [None],
                "disbursement_sequence": [1],
            }
        )
        result = validator.validate(df, valid_partners)
        assert result.exception_list[0].reason == "missing_lan"

    def test_missing_product_takes_priority_over_missing_partner(
        self, validator, valid_partners
    ):
        df = pd.DataFrame(
            {
                "disbursement_id": ["D001"],
                "lan": ["LAN001"],
                "partner_id": [None],
                "loan_product": [None],
                "disbursed_amount": [100000.0],
                "disbursement_date": ["2024-01-01"],
                "cheque_handover_date": [None],
                "disbursement_sequence": [1],
            }
        )
        result = validator.validate(df, valid_partners)
        assert result.exception_list[0].reason == "missing_loan_product"


class TestExclusionReasonsCounting:
    """Test that exclusion reasons dictionary counts correctly."""

    def test_multiple_same_reason_counted(self, validator, valid_partners):
        df = pd.DataFrame(
            {
                "disbursement_id": ["D001", "D002", "D003"],
                "lan": [None, None, "LAN003"],
                "partner_id": ["P001", "P001", "P001"],
                "loan_product": ["PL", "PL", "PL"],
                "disbursed_amount": [100000.0, 200000.0, 300000.0],
                "disbursement_date": ["2024-01-01", "2024-01-02", "2024-01-03"],
                "cheque_handover_date": [None, None, None],
                "disbursement_sequence": [1, 1, 1],
            }
        )
        result = validator.validate(df, valid_partners)
        assert result.exclusion_reasons["missing_lan"] == 2
        assert result.valid_count == 1


class TestEmptyInput:
    """Test handling of empty DataFrames."""

    def test_empty_disbursements(self, validator, valid_partners):
        df = pd.DataFrame(
            columns=[
                "disbursement_id",
                "lan",
                "partner_id",
                "loan_product",
                "disbursed_amount",
                "disbursement_date",
                "cheque_handover_date",
                "disbursement_sequence",
            ]
        )
        result = validator.validate(df, valid_partners)
        assert result.valid_count == 0
        assert result.excluded_count == 0
        assert result.exception_list == []

    def test_empty_partners_excludes_all(self, validator, valid_disbursements):
        partners = pd.DataFrame(
            columns=[
                "partner_id",
                "partner_name",
                "partner_type",
                "corporate_flag",
                "registration_date",
                "active",
            ]
        )
        result = validator.validate(valid_disbursements, partners)
        assert result.excluded_count == 3
        assert all(
            exc.reason == "unmatched_partner" for exc in result.exception_list
        )


class TestRecordData:
    """Test that exception record_data contains the row data."""

    def test_record_data_is_dict(self, validator, valid_partners):
        df = pd.DataFrame(
            {
                "disbursement_id": ["D001"],
                "lan": [None],
                "partner_id": ["P001"],
                "loan_product": ["PL"],
                "disbursed_amount": [100000.0],
                "disbursement_date": ["2024-01-01"],
                "cheque_handover_date": [None],
                "disbursement_sequence": [1],
            }
        )
        result = validator.validate(df, valid_partners)
        assert isinstance(result.exception_list[0].record_data, dict)
        assert result.exception_list[0].record_data["disbursement_id"] == "D001"
