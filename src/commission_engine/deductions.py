"""Deduction Module: applies GST and TDS based on partner corporate classification."""

from decimal import Decimal, ROUND_HALF_UP

import pandas as pd

from commission_engine.config_loader import DeductionConfig
from commission_engine.models import CommissionResult, DeductionResult


TWO_PLACES = Decimal("0.01")


class DeductionModule:
    """Applies statutory deductions (GST/TDS) to gross commissions."""

    def __init__(self, deduction_config: DeductionConfig) -> None:
        self._config = deduction_config

    def apply(
        self, commissions: list[CommissionResult], partners: pd.DataFrame
    ) -> list[DeductionResult]:
        """Apply GST and TDS deductions to eligible commissions.

        Args:
            commissions: List of CommissionResult from the calculator.
            partners: DataFrame with at least partner_id and corporate_flag columns.

        Returns:
            List of DeductionResult with gross, gst, tds, and net amounts.
        """
        # Build lookup: partner_id -> corporate_flag
        corporate_lookup: dict[str, bool] = dict(
            zip(partners["partner_id"], partners["corporate_flag"])
        )

        results: list[DeductionResult] = []

        for comm in commissions:
            if not comm.eligible or comm.gross_commission <= Decimal(0):
                # Ineligible or zero gross: no deductions
                results.append(
                    DeductionResult(
                        lan=comm.lan,
                        partner_id=comm.partner_id,
                        gross_commission=comm.gross_commission,
                        gst_amount=Decimal(0),
                        tds_amount=Decimal(0),
                        net_payout=Decimal(0),
                    )
                )
                continue

            is_corporate = corporate_lookup.get(comm.partner_id, False)
            gross = comm.gross_commission

            if is_corporate:
                gst_rate = Decimal(str(self._config.corporate_gst_rate))
                tds_rate = Decimal(str(self._config.corporate_tds_rate))
                gst_amount = (gross * gst_rate).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
                tds_amount = (gross * tds_rate).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
                # Formula: net = gross + gst - tds
                net_payout = gross + gst_amount - tds_amount
            else:
                # Non-corporate: no GST, only TDS
                tds_rate = Decimal(str(self._config.non_corporate_tds_rate))
                gst_amount = Decimal(0)
                tds_amount = (gross * tds_rate).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
                # Formula: net = gross - tds
                net_payout = gross - tds_amount

            net_payout = net_payout.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

            results.append(
                DeductionResult(
                    lan=comm.lan,
                    partner_id=comm.partner_id,
                    gross_commission=gross,
                    gst_amount=gst_amount,
                    tds_amount=tds_amount,
                    net_payout=net_payout,
                )
            )

        return results
