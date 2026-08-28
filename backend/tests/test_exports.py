from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import uuid

import pytest

from app.core.enums import UserType
from app.core.exceptions import NotFoundError, ValidationError
from app.exports.models import ExportFormat
from app.exports.schemas import TransactionExportRequest
from app.exports.service import ExportService
from app.merchants.schemas import MerchantCreate
from app.merchants.service import MerchantService
from app.transactions.models import (
    LedgerEntryType,
    Transaction,
    TransactionCategory,
    TransactionStatus,
    TransactionType,
    WalletLedgerEntry,
)
from app.transactions.schemas import InternalTransferCreate
from app.transactions.service import TransactionService
from app.users.schemas import UserCreate
from app.users.service import UserService
from app.wallets.schemas import WalletCreate
from app.wallets.service import WalletService


@pytest.fixture()
def wallets_with_transfer(db_session):
    users = UserService(db_session)
    wallets = WalletService(db_session)

    business = users.create_user(
        UserCreate(
            email="export-business@example.com",
            password="Sup3rSecret!",
            first_name="Biz",
            last_name="Owner",
            user_type=UserType.BUSINESS,
        )
    )
    receiver = users.create_user(
        UserCreate(email="export-receiver@example.com", password="Sup3rSecret!", first_name="Rece", last_name="Iver")
    )
    business_wallet = wallets.create_wallet(business.id, WalletCreate(currency="RON"))
    receiver_wallet = wallets.create_wallet(receiver.id, WalletCreate(currency="RON"))
    business_wallet.available_balance = Decimal("500.00")
    db_session.flush()

    TransactionService(db_session).create_internal_transfer(
        business.id,
        InternalTransferCreate(
            source_wallet_id=business_wallet.id,
            destination_wallet_id=receiver_wallet.id,
            amount=Decimal("120.00"),
            description="Rent",
        ),
    )
    db_session.flush()

    return business, business_wallet, receiver, receiver_wallet


def _today_range():
    return date.today() - timedelta(days=1), date.today() + timedelta(days=1)


def test_export_lists_outgoing_transaction_for_business_sender(db_session, wallets_with_transfer):
    business, _business_wallet, _receiver, _receiver_wallet = wallets_with_transfer
    date_from, date_to = _today_range()

    preview = ExportService(db_session).build_preview(
        business.id, TransactionExportRequest(date_from=date_from, date_to=date_to)
    )

    assert preview.row_count == 1
    assert preview.transactions[0].amount == Decimal("120.00")
    assert preview.transactions[0].currency == "RON"
    assert preview.transactions[0].description == "Rent"
    assert preview.transactions[0].type == TransactionType.TRANSFER
    assert preview.transactions[0].category is None


def test_export_direction_filter_excludes_non_matching_entries(db_session, wallets_with_transfer):
    business, _business_wallet, _receiver, _receiver_wallet = wallets_with_transfer
    date_from, date_to = _today_range()

    incoming = ExportService(db_session).build_preview(
        business.id, TransactionExportRequest(date_from=date_from, date_to=date_to, direction="incoming")
    )
    outgoing = ExportService(db_session).build_preview(
        business.id, TransactionExportRequest(date_from=date_from, date_to=date_to, direction="outgoing")
    )

    assert incoming.transactions == []
    assert len(outgoing.transactions) == 1


def test_export_wallet_filter_narrows_to_one_wallet(db_session, wallets_with_transfer):
    business, business_wallet, _receiver, _receiver_wallet = wallets_with_transfer
    date_from, date_to = _today_range()

    preview = ExportService(db_session).build_preview(
        business.id, TransactionExportRequest(date_from=date_from, date_to=date_to, wallet_id=business_wallet.id)
    )

    assert preview.row_count == 1


def test_export_rejects_another_users_wallet(db_session, wallets_with_transfer):
    business, _business_wallet, _receiver, receiver_wallet = wallets_with_transfer
    date_from, date_to = _today_range()

    with pytest.raises(NotFoundError):
        ExportService(db_session).build_preview(
            business.id, TransactionExportRequest(date_from=date_from, date_to=date_to, wallet_id=receiver_wallet.id)
        )


def test_export_status_filter(db_session, wallets_with_transfer):
    business, _business_wallet, _receiver, _receiver_wallet = wallets_with_transfer
    date_from, date_to = _today_range()

    completed = ExportService(db_session).build_preview(
        business.id,
        TransactionExportRequest(date_from=date_from, date_to=date_to, status=TransactionStatus.COMPLETED),
    )
    failed = ExportService(db_session).build_preview(
        business.id, TransactionExportRequest(date_from=date_from, date_to=date_to, status=TransactionStatus.FAILED)
    )

    assert len(completed.transactions) == 1
    assert failed.transactions == []


def test_export_excludes_entries_outside_period(db_session, wallets_with_transfer):
    business, _business_wallet, _receiver, _receiver_wallet = wallets_with_transfer
    future_from = date.today() + timedelta(days=10)
    future_to = date.today() + timedelta(days=20)

    preview = ExportService(db_session).build_preview(
        business.id, TransactionExportRequest(date_from=future_from, date_to=future_to)
    )

    assert preview.transactions == []


def test_export_rejects_inverted_date_range(db_session, wallets_with_transfer):
    business, _business_wallet, _receiver, _receiver_wallet = wallets_with_transfer

    with pytest.raises(ValidationError):
        ExportService(db_session).build_preview(
            business.id,
            TransactionExportRequest(date_from=date.today(), date_to=date.today() - timedelta(days=1)),
        )


def test_export_rejects_a_date_range_over_the_cap(db_session, wallets_with_transfer):
    business, _business_wallet, _receiver, _receiver_wallet = wallets_with_transfer

    with pytest.raises(ValidationError):
        ExportService(db_session).build_preview(
            business.id,
            TransactionExportRequest(date_from=date.today() - timedelta(days=400), date_to=date.today()),
        )


def test_export_resolves_merchant_counterparty(db_session, wallets_with_transfer):
    business, business_wallet, _receiver, _receiver_wallet = wallets_with_transfer
    merchant = MerchantService(db_session).create_merchant(MerchantCreate(name="CoffeeCo", category="Food"))
    card_payment = Transaction(
        initiator_user_id=business.id,
        source_wallet_id=business_wallet.id,
        merchant_id=merchant.id,
        type=TransactionType.CARD_PAYMENT,
        status=TransactionStatus.COMPLETED,
        amount=Decimal("15.00"),
        currency="RON",
        description="Coffee",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(card_payment)
    db_session.flush()
    db_session.add(
        WalletLedgerEntry(
            wallet_id=business_wallet.id,
            transaction_id=card_payment.id,
            entry_type=LedgerEntryType.DEBIT,
            amount=Decimal("15.00"),
            currency="RON",
            balance_after=Decimal("365.00"),
            created_at=datetime.now(timezone.utc),
        )
    )
    db_session.flush()
    date_from, date_to = _today_range()

    preview = ExportService(db_session).build_preview(
        business.id, TransactionExportRequest(date_from=date_from, date_to=date_to, currency="RON")
    )

    coffee_row = next(row for row in preview.transactions if row.description == "Coffee")
    assert coffee_row.counterparty == "CoffeeCo"


def test_export_resolves_category_name(db_session, wallets_with_transfer):
    business, business_wallet, _receiver, _receiver_wallet = wallets_with_transfer
    category = TransactionCategory(id=uuid.uuid4(), name="Bills")
    db_session.add(category)
    db_session.flush()
    payment = Transaction(
        initiator_user_id=business.id,
        source_wallet_id=business_wallet.id,
        category_id=category.id,
        type=TransactionType.CARD_PAYMENT,
        status=TransactionStatus.COMPLETED,
        amount=Decimal("40.00"),
        currency="RON",
        description="Electricity",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(payment)
    db_session.flush()
    db_session.add(
        WalletLedgerEntry(
            wallet_id=business_wallet.id,
            transaction_id=payment.id,
            entry_type=LedgerEntryType.DEBIT,
            amount=Decimal("40.00"),
            currency="RON",
            balance_after=Decimal("340.00"),
            created_at=datetime.now(timezone.utc),
        )
    )
    db_session.flush()
    date_from, date_to = _today_range()

    preview = ExportService(db_session).build_preview(
        business.id, TransactionExportRequest(date_from=date_from, date_to=date_to, currency="RON")
    )

    bill_row = next(row for row in preview.transactions if row.description == "Electricity")
    assert bill_row.category == "Bills"


def test_export_summary_totals_by_currency(db_session, wallets_with_transfer):
    business, _business_wallet, _receiver, _receiver_wallet = wallets_with_transfer
    date_from, date_to = _today_range()

    preview = ExportService(db_session).build_preview(
        business.id, TransactionExportRequest(date_from=date_from, date_to=date_to)
    )

    assert len(preview.totals) == 1
    assert preview.totals[0].currency == "RON"
    assert preview.totals[0].total_outgoing == Decimal("120.00")
    assert preview.totals[0].total_incoming == Decimal("0")


def test_export_csv_contains_expected_columns_and_totals(db_session, wallets_with_transfer):
    business, _business_wallet, _receiver, _receiver_wallet = wallets_with_transfer
    date_from, date_to = _today_range()
    service = ExportService(db_session)

    preview = service.build_preview(business.id, TransactionExportRequest(date_from=date_from, date_to=date_to))
    csv_text = service.to_csv(preview)

    header = csv_text.splitlines()[0]
    assert header == "date,transaction_id,type,counterparty,description,category,direction,amount,currency,status"
    assert "Rent" in csv_text
    assert "120.00" in csv_text
    assert "TOTALS" in csv_text


def test_export_xlsx_is_a_real_workbook(db_session, wallets_with_transfer):
    business, _business_wallet, _receiver, _receiver_wallet = wallets_with_transfer
    date_from, date_to = _today_range()
    service = ExportService(db_session)

    preview = service.build_preview(business.id, TransactionExportRequest(date_from=date_from, date_to=date_to))
    xlsx_bytes = service.to_xlsx(preview)

    assert xlsx_bytes[:2] == b"PK"  # xlsx is a zip container


def test_export_pdf_is_a_real_pdf(db_session, wallets_with_transfer):
    business, _business_wallet, _receiver, _receiver_wallet = wallets_with_transfer
    date_from, date_to = _today_range()
    service = ExportService(db_session)

    preview = service.build_preview(business.id, TransactionExportRequest(date_from=date_from, date_to=date_to))
    pdf_bytes = service.to_pdf(preview)

    assert pdf_bytes[:5] == b"%PDF-"
    assert pdf_bytes.rstrip().endswith(b"%%EOF")


def test_export_mt940_requires_a_wallet_id(db_session, wallets_with_transfer):
    business, _business_wallet, _receiver, _receiver_wallet = wallets_with_transfer
    date_from, date_to = _today_range()
    service = ExportService(db_session)

    with pytest.raises(ValidationError):
        service.to_mt940(business.id, TransactionExportRequest(date_from=date_from, date_to=date_to))


def test_export_mt940_has_the_expected_swift_tags(db_session, wallets_with_transfer):
    business, business_wallet, _receiver, _receiver_wallet = wallets_with_transfer
    date_from, date_to = _today_range()
    service = ExportService(db_session)

    text = service.to_mt940(
        business.id, TransactionExportRequest(date_from=date_from, date_to=date_to, wallet_id=business_wallet.id)
    )
    lines = text.splitlines()

    assert lines[0].startswith(":20:")
    assert lines[1] == f":25:{business_wallet.iban}"
    assert lines[2].startswith(":28C:")
    assert lines[3].startswith(":60F:")
    assert any(line.startswith(":61:") for line in lines)
    assert any(line.startswith(":86:") and "Rent" in line for line in lines)
    assert lines[-2].startswith(":62F:")
    assert lines[-1] == "-"
    # Outgoing 120.00 debit -> a "D" marker on the :61: line, comma decimal.
    assert any(line.startswith(":61:") and "D120,00" in line for line in lines)


def test_generate_and_log_supports_pdf_and_mt940(db_session, wallets_with_transfer):
    business, business_wallet, _receiver, _receiver_wallet = wallets_with_transfer
    date_from, date_to = _today_range()
    service = ExportService(db_session)

    pdf_job, pdf_content, pdf_meta = service.generate_and_log(
        business.id, TransactionExportRequest(date_from=date_from, date_to=date_to), ExportFormat.PDF
    )
    assert pdf_meta.startswith("application/pdf|")
    assert pdf_content[:5] == b"%PDF-"
    assert pdf_job.format == ExportFormat.PDF

    mt940_job, mt940_content, mt940_meta = service.generate_and_log(
        business.id,
        TransactionExportRequest(date_from=date_from, date_to=date_to, wallet_id=business_wallet.id),
        ExportFormat.MT940,
    )
    assert mt940_meta.startswith("application/octet-stream|")
    assert b":25:" in mt940_content
    assert mt940_job.format == ExportFormat.MT940
    assert mt940_job.row_count == 1

    _redownload_job, redownload_content, _redownload_meta = service.download_job(business.id, mt940_job.id)
    assert redownload_content == mt940_content


def test_generate_and_log_records_history_and_supports_redownload(db_session, wallets_with_transfer):
    business, _business_wallet, _receiver, _receiver_wallet = wallets_with_transfer
    date_from, date_to = _today_range()
    service = ExportService(db_session)
    request = TransactionExportRequest(date_from=date_from, date_to=date_to)

    job, content, meta = service.generate_and_log(business.id, request, ExportFormat.CSV)
    media_type, filename = meta.split("|", 1)

    assert media_type == "text/csv"
    assert filename.endswith(".csv")
    assert b"Rent" in content

    history = service.list_history(business.id)
    assert any(entry.id == job.id for entry in history)

    _redownload_job, redownload_content, _redownload_meta = service.download_job(business.id, job.id)
    assert redownload_content == content


def test_download_job_rejects_other_users_export(db_session, wallets_with_transfer):
    business, _business_wallet, receiver, _receiver_wallet = wallets_with_transfer
    date_from, date_to = _today_range()
    service = ExportService(db_session)
    job, _content, _meta = service.generate_and_log(
        business.id, TransactionExportRequest(date_from=date_from, date_to=date_to), ExportFormat.CSV
    )

    with pytest.raises(NotFoundError):
        service.download_job(receiver.id, job.id)


def test_export_endpoint_rejects_personal_user(client):
    register = client.post(
        "/api/v1/auth/register",
        json={
            "email": "export-personal@example.com",
            "phone": "+40744444450",
            "password": "Sup3rSecret!",
            "first_name": "Per",
            "last_name": "Sonal",
        },
    )
    assert register.status_code == 201
    token = register.json()["tokens"]["access_token"]

    response = client.get(
        "/api/v1/exports/transactions",
        headers={"Authorization": f"Bearer {token}"},
        params={"date_from": str(date.today()), "date_to": str(date.today())},
    )

    assert response.status_code == 403


def test_export_endpoint_returns_csv_for_business_user(client, db_session):
    # RegisterRequest has no user_type field (no business signup flow yet via
    # HTTP) — seed the business user directly, same as seed.py does, then log
    # in over HTTP for a real token.
    UserService(db_session).create_user(
        UserCreate(
            email="export-biz-http@example.com",
            phone="+40744444451",
            password="Sup3rSecret!",
            first_name="Biz",
            last_name="Http",
            user_type=UserType.BUSINESS,
        )
    )
    db_session.commit()
    login = client.post(
        "/api/v1/auth/login", json={"email": "export-biz-http@example.com", "password": "Sup3rSecret!"}
    )
    assert login.status_code == 200
    token = login.json()["tokens"]["access_token"]
    date_from, date_to = _today_range()

    response = client.get(
        "/api/v1/exports/transactions",
        headers={"Authorization": f"Bearer {token}"},
        params={"date_from": str(date_from), "date_to": str(date_to)},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert (
        response.text.splitlines()[0]
        == "date,transaction_id,type,counterparty,description,category,direction,amount,currency,status"
    )

    history = client.get("/api/v1/exports", headers={"Authorization": f"Bearer {token}"})
    assert history.status_code == 200
    assert len(history.json()) == 1

    job_id = history.json()[0]["id"]
    redownload = client.get(f"/api/v1/exports/{job_id}/download", headers={"Authorization": f"Bearer {token}"})
    assert redownload.status_code == 200
    assert redownload.text == response.text


def test_export_endpoint_supports_xlsx_format(client, db_session):
    UserService(db_session).create_user(
        UserCreate(
            email="export-biz-xlsx@example.com",
            phone="+40744444452",
            password="Sup3rSecret!",
            first_name="Biz",
            last_name="Xlsx",
            user_type=UserType.BUSINESS,
        )
    )
    db_session.commit()
    login = client.post("/api/v1/auth/login", json={"email": "export-biz-xlsx@example.com", "password": "Sup3rSecret!"})
    token = login.json()["tokens"]["access_token"]
    date_from, date_to = _today_range()

    response = client.get(
        "/api/v1/exports/transactions",
        headers={"Authorization": f"Bearer {token}"},
        params={"date_from": str(date_from), "date_to": str(date_to), "format": "xlsx"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert response.content[:2] == b"PK"
