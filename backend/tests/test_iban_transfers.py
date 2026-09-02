from decimal import Decimal
from uuid import UUID

from app.fx.models import FXQuote, FXQuoteStatus
from app.payments.models import Beneficiary
from app.transactions.models import LedgerEntryType, TransactionStatus, WalletLedgerEntry
from app.wallets.models import Wallet
from app.wallets.schemas import WalletCreate
from app.wallets.service import WalletService


def _register(client, email: str, phone: str) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "phone": phone,
            "password": "Sup3rSecret!",
            "first_name": email.split("@")[0].title(),
            "last_name": "User",
        },
    )
    assert response.status_code == 201
    return response.json()


def _auth_header(auth_response: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth_response['tokens']['access_token']}"}


def _create_wallet(db_session, user_id: str, currency: str, balance: Decimal = Decimal("0")) -> Wallet:
    wallet = WalletService(db_session).create_wallet(UUID(user_id), WalletCreate(currency=currency))
    wallet.available_balance = balance
    db_session.flush()
    return wallet


def test_iban_transfer_debits_sender_and_writes_outbound_transaction(client, db_session):
    sender = _register(client, "iban-sender@example.com", "+40750111111")
    source_wallet = _create_wallet(db_session, sender["user"]["id"], "RON", Decimal("500.00"))

    response = client.post(
        "/api/v1/payments/transfers/iban",
        headers=_auth_header(sender),
        json={
            "beneficiary_name": "Maria Dinu",
            "iban": "RO49AAAA1B31007593840000",
            "source_wallet_id": str(source_wallet.id),
            "amount": "125.00",
            "currency": "RON",
            "description": "Rent August",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == TransactionStatus.COMPLETED
    assert body["source_wallet_id"] == str(source_wallet.id)
    assert body["destination_wallet_id"] is None
    assert body["amount"] == "125.00"
    assert body["currency"] == "RON"

    db_session.refresh(source_wallet)
    assert source_wallet.available_balance == Decimal("375.00")

    ledger_entry = db_session.query(WalletLedgerEntry).filter_by(transaction_id=UUID(body["id"])).one()
    assert ledger_entry.wallet_id == source_wallet.id
    assert ledger_entry.entry_type == LedgerEntryType.DEBIT
    assert ledger_entry.amount == Decimal("125.00")


def test_iban_transfer_can_save_beneficiary(client, db_session):
    sender = _register(client, "iban-save@example.com", "+40750222222")
    source_wallet = _create_wallet(db_session, sender["user"]["id"], "EUR", Decimal("300.00"))

    response = client.post(
        "/api/v1/payments/transfers/iban",
        headers=_auth_header(sender),
        json={
            "beneficiary_name": "Andrei Pop",
            "iban": "RO12BBBB1B31007593844471",
            "source_wallet_id": str(source_wallet.id),
            "amount": "40.00",
            "currency": "EUR",
            "save_beneficiary": True,
            "is_favorite": True,
        },
    )

    assert response.status_code == 201
    saved = db_session.query(Beneficiary).filter_by(owner_user_id=UUID(sender["user"]["id"])).one()
    assert saved.name == "Andrei Pop"
    assert saved.iban == "RO12BBBB1B31007593844471"
    assert saved.phone is None
    assert saved.is_favorite is True


def test_cross_currency_iban_transfer_uses_fx_quote(client, db_session):
    sender = _register(client, "iban-fx@example.com", "+40750333333")
    source_wallet = _create_wallet(db_session, sender["user"]["id"], "RON", Decimal("1000.00"))

    quote_response = client.post(
        "/api/v1/payments/transfers/iban/fx-quote",
        headers=_auth_header(sender),
        json={
            "source_wallet_id": str(source_wallet.id),
            "amount": "50.00",
            "currency": "EUR",
        },
    )

    assert quote_response.status_code == 201
    quote_body = quote_response.json()
    assert quote_body["source_currency"] == "RON"
    assert quote_body["target_currency"] == "EUR"
    assert quote_body["target_amount"] == "50.00"

    response = client.post(
        "/api/v1/payments/transfers/iban",
        headers=_auth_header(sender),
        json={
            "beneficiary_name": "Maria Dinu",
            "iban": "RO49AAAA1B31007593840000",
            "source_wallet_id": str(source_wallet.id),
            "amount": "50.00",
            "currency": "EUR",
            "fx_quote_id": quote_body["id"],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == TransactionStatus.COMPLETED
    assert body["amount"] == "50.00"
    assert body["currency"] == "EUR"
    assert body["source_amount"] == quote_body["source_amount"]
    assert body["source_currency"] == "RON"
    assert body["exchange_rate"] == quote_body["exchange_rate"]

    db_session.refresh(source_wallet)
    assert source_wallet.available_balance == Decimal("1000.00") - Decimal(quote_body["source_amount"])

    quote = db_session.get(FXQuote, UUID(quote_body["id"]))
    assert quote.status == FXQuoteStatus.ACCEPTED


def test_iban_transfer_credits_matching_easyb_wallet(client, db_session):
    sender = _register(client, "iban-onus-sender@example.com", "+40750666666")
    recipient = _register(client, "iban-onus-recipient@example.com", "+40750777777")
    source_wallet = _create_wallet(db_session, sender["user"]["id"], "RON", Decimal("500.00"))
    destination_wallet = _create_wallet(db_session, recipient["user"]["id"], "RON", Decimal("0.00"))

    response = client.post(
        "/api/v1/payments/transfers/iban",
        headers=_auth_header(sender),
        json={
            "beneficiary_name": "Fellow EasyB customer",
            "iban": destination_wallet.iban,
            "source_wallet_id": str(source_wallet.id),
            "amount": "125.00",
            "currency": "RON",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == TransactionStatus.COMPLETED
    assert body["source_wallet_id"] == str(source_wallet.id)
    assert body["destination_wallet_id"] == str(destination_wallet.id)
    assert body["amount"] == "125.00"

    db_session.refresh(source_wallet)
    db_session.refresh(destination_wallet)
    assert source_wallet.available_balance == Decimal("375.00")
    assert destination_wallet.available_balance == Decimal("125.00")

    credit_entry = (
        db_session.query(WalletLedgerEntry)
        .filter_by(transaction_id=UUID(body["id"]), wallet_id=destination_wallet.id)
        .one()
    )
    assert credit_entry.entry_type == LedgerEntryType.CREDIT
    assert credit_entry.amount == Decimal("125.00")


def test_iban_transfer_rejects_currency_mismatch(client, db_session):
    sender = _register(client, "iban-currency@example.com", "+40750444444")
    source_wallet = _create_wallet(db_session, sender["user"]["id"], "RON", Decimal("500.00"))

    response = client.post(
        "/api/v1/payments/transfers/iban",
        headers=_auth_header(sender),
        json={
            "beneficiary_name": "External Payee",
            "iban": "RO88CCCC1B31007593841023",
            "source_wallet_id": str(source_wallet.id),
            "amount": "50.00",
            "currency": "EUR",
        },
    )

    assert response.status_code == 422


def test_iban_transfer_rejects_insufficient_balance(client, db_session):
    sender = _register(client, "iban-low@example.com", "+40750555555")
    source_wallet = _create_wallet(db_session, sender["user"]["id"], "RON", Decimal("10.00"))

    response = client.post(
        "/api/v1/payments/transfers/iban",
        headers=_auth_header(sender),
        json={
            "beneficiary_name": "External Payee",
            "iban": "RO88CCCC1B31007593841023",
            "source_wallet_id": str(source_wallet.id),
            "amount": "50.00",
            "currency": "RON",
        },
    )

    assert response.status_code == 409


def test_iban_transfer_to_an_easyb_wallet_in_another_currency_is_refused(client, db_session):
    """The IBAN is on-us but the recipient holds a different currency.

    Regression test for money loss: this used to fall through to the
    external "money leaves the bank" branch, which debited the sender, left
    destination_wallet_id NULL and marked the transfer COMPLETED — while the
    recipient, a real account on this system, was never credited.
    """
    sender = _register(client, "iban-xcur-sender@example.com", "+40750666661")
    recipient = _register(client, "iban-xcur-recipient@example.com", "+40750666662")
    source_wallet = _create_wallet(db_session, sender["user"]["id"], "EUR", Decimal("500.00"))
    recipient_wallet = _create_wallet(db_session, recipient["user"]["id"], "RON", Decimal("10.00"))

    response = client.post(
        "/api/v1/payments/transfers/iban",
        headers=_auth_header(sender),
        json={
            "beneficiary_name": "Recipient User",
            "iban": recipient_wallet.iban,
            "source_wallet_id": str(source_wallet.id),
            "amount": "100.00",
            "currency": "EUR",
        },
    )

    assert response.status_code == 422
    assert "RON" in response.json()["detail"]

    db_session.refresh(source_wallet)
    db_session.refresh(recipient_wallet)
    assert source_wallet.available_balance == Decimal("500.00")  # nothing left the sender
    assert recipient_wallet.available_balance == Decimal("10.00")
