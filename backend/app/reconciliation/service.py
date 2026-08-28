"""Wallet-ledger reconciliation (architecture.md §7's ledger-is-truth model,
checked rather than just assumed): for every wallet, the stored
available_balance + reserved_balance should always equal what its own
ledger entries add up to. A mismatch means some code path mutated a
balance without writing a matching ledger entry, or vice versa — exactly
the class of bug the row-locking fix (see transactions/service.py) closed
one instance of. Nothing currently runs this automatically; it's an
admin-triggered, on-demand check (see reconciliation/router.py) since this
codebase has no background job scheduler to hang a periodic run off of."""
from decimal import Decimal

from sqlalchemy.orm import Session

from app.reconciliation.repository import ReconciliationRepository
from app.reconciliation.schemas import ReconciliationReport, WalletDiscrepancy
from app.transactions.models import LedgerEntryType


class ReconciliationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = ReconciliationRepository(db)

    def check_all_wallets(self) -> ReconciliationReport:
        wallets = self.repository.list_all_wallets()
        discrepancies: list[WalletDiscrepancy] = []

        for wallet in wallets:
            entries = self.repository.list_all_entries_for_wallet(wallet.id)
            ledger_balance = sum(
                (e.amount if e.entry_type == LedgerEntryType.CREDIT else -e.amount)
                for e in entries
                if e.entry_type in (LedgerEntryType.CREDIT, LedgerEntryType.DEBIT)
            ) or Decimal("0")
            stored_total = wallet.available_balance + wallet.reserved_balance

            if stored_total != ledger_balance:
                discrepancies.append(
                    WalletDiscrepancy(
                        wallet_id=wallet.id,
                        user_id=wallet.user_id,
                        currency=wallet.currency,
                        stored_total_balance=stored_total,
                        ledger_derived_balance=ledger_balance,
                        difference=stored_total - ledger_balance,
                    )
                )

        return ReconciliationReport(wallets_checked=len(wallets), discrepancies=discrepancies)
