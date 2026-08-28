"""Pydantic schemas for the wallet-ledger reconciliation report."""
import uuid
from decimal import Decimal

from pydantic import BaseModel


class WalletDiscrepancy(BaseModel):
    wallet_id: uuid.UUID
    user_id: uuid.UUID
    currency: str
    # available_balance + reserved_balance, as currently stored on the wallet.
    stored_total_balance: Decimal
    # sum(CREDIT entries) - sum(DEBIT entries) for this wallet's ledger.
    # HOLD/RELEASE entries are deliberately excluded: each one only ever
    # moves an amount between available_balance and reserved_balance, never
    # changing their sum, so they contribute nothing to this total either.
    ledger_derived_balance: Decimal
    difference: Decimal


class ReconciliationReport(BaseModel):
    wallets_checked: int
    discrepancies: list[WalletDiscrepancy]
