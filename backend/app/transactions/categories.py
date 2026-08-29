"""How a transaction's spending category is decided, in one place.

Two things can name a category and they have to agree, or the Analytics
donut and the Budgets page end up reporting different numbers for the same
month:

  1. Transaction.category_id -- the user's own choice for this one
     transaction, set from the Transactions page. Wins when present.
  2. Merchant.category -- what the merchant is generally classified as.
     The fallback, and what everything used before per-transaction
     categorisation existed.

Both are drawn from the same vocabulary (see the transaction_categories
seed in migration 0052): a user re-filing a payment must be able to pick
any category a merchant could already have been in, otherwise the donut
would show "Entertainment" and "Restaurants" as unrelated slices of the
same spending.

Every consumer resolves through here -- AnalyticsRepository (the donut and
the insight flags) and BudgetRepository (spent-so-far). Adding a fourth
consumer means calling one of these, not writing the COALESCE again.
"""
import uuid
from typing import Mapping

from sqlalchemy import func
from sqlalchemy.sql.elements import ColumnElement

from app.merchants.models import Merchant
from app.transactions.models import Transaction, TransactionCategory

# What a card payment with neither an override nor a recognised merchant
# falls back to. Kept as "Other" -- the value the donut already grouped
# these under before overrides existed, and a real entry in the seeded
# category list, so it is also pickable.
UNCATEGORIZED = "Other"


def effective_category_column() -> ColumnElement[str]:
    """SQL side of the resolution. Requires join_category_sources() to have
    added both outer joins to the statement."""
    return func.coalesce(TransactionCategory.name, Merchant.category, UNCATEGORIZED)


def join_category_sources(stmt):
    """Outer joins, both of them: a card payment can have no merchant on
    record, no override, or neither, and must still be counted under
    UNCATEGORIZED rather than dropped from the results by an inner join."""
    return stmt.outerjoin(Merchant, Merchant.id == Transaction.merchant_id).outerjoin(
        TransactionCategory, TransactionCategory.id == Transaction.category_id
    )


def resolve_effective_category(
    transaction: Transaction,
    merchants_by_id: Mapping[uuid.UUID, Merchant],
    categories_by_id: Mapping[uuid.UUID, TransactionCategory],
) -> str:
    """Python side of the same resolution, for the Supabase REST backend
    (no SQL joins available there -- see app/supabase.py). Must stay in step
    with effective_category_column()."""
    if transaction.category_id is not None:
        category = categories_by_id.get(transaction.category_id)
        if category is not None:
            return category.name
    if transaction.merchant_id is not None:
        merchant = merchants_by_id.get(transaction.merchant_id)
        if merchant is not None and merchant.category:
            return merchant.category
    return UNCATEGORIZED
