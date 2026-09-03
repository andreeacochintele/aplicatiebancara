"""Data-access layer for payment beneficiaries."""
import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.supabase import is_supabase_session
from app.payments.models import (
    Beneficiary,
    BillSplit,
    BillSplitParticipant,
    BulkTransferTemplate,
    BulkTransferTemplateRow,
    PaymentRequest,
    ScheduledPayment,
    ScheduledPaymentStatus,
    TransactionFolder,
    TransactionFolderItem,
)


class BeneficiaryRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_owned_by_id(self, owner_user_id: uuid.UUID, beneficiary_id: uuid.UUID) -> Beneficiary | None:
        if is_supabase_session(self.db):
            return self.db.fetch_one(
                Beneficiary,
                {"id": f"eq.{beneficiary_id}", "owner_user_id": f"eq.{owner_user_id}"},
            )
        return self.db.scalar(
            select(Beneficiary).where(
                Beneficiary.id == beneficiary_id,
                Beneficiary.owner_user_id == owner_user_id,
            )
        )

    def list_for_owner(self, owner_user_id: uuid.UUID, limit: int = 100, offset: int = 0) -> list[Beneficiary]:
        if is_supabase_session(self.db):
            return self.db.fetch_many(
                Beneficiary,
                {
                    "owner_user_id": f"eq.{owner_user_id}",
                    "order": "created_at.desc",
                    "limit": str(limit),
                    "offset": str(offset),
                },
            )
        stmt = (
            select(Beneficiary)
            .where(Beneficiary.owner_user_id == owner_user_id)
            .order_by(Beneficiary.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.db.scalars(stmt))

    def add(self, beneficiary: Beneficiary) -> Beneficiary:
        if is_supabase_session(self.db):
            return self.db.add(beneficiary)
        self.db.add(beneficiary)
        self.db.flush()
        return beneficiary

    def delete(self, beneficiary: Beneficiary) -> None:
        if is_supabase_session(self.db):
            self.db.delete(beneficiary)
            return
        self.db.delete(beneficiary)
        self.db.flush()


class PaymentRequestRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, request_id: uuid.UUID) -> PaymentRequest | None:
        if is_supabase_session(self.db):
            return self.db.get(PaymentRequest, request_id)
        return self.db.get(PaymentRequest, request_id)

    def get_owned_by_id(self, creator_user_id: uuid.UUID, request_id: uuid.UUID) -> PaymentRequest | None:
        if is_supabase_session(self.db):
            return self.db.fetch_one(
                PaymentRequest, {"id": f"eq.{request_id}", "creator_user_id": f"eq.{creator_user_id}"}
            )
        return self.db.scalar(
            select(PaymentRequest).where(
                PaymentRequest.id == request_id, PaymentRequest.creator_user_id == creator_user_id
            )
        )

    def list_for_creator(self, creator_user_id: uuid.UUID, limit: int = 100, offset: int = 0) -> list[PaymentRequest]:
        if is_supabase_session(self.db):
            return self.db.fetch_many(
                PaymentRequest,
                {
                    "creator_user_id": f"eq.{creator_user_id}",
                    "order": "created_at.desc",
                    "limit": str(limit),
                    "offset": str(offset),
                },
            )
        stmt = (
            select(PaymentRequest)
            .where(PaymentRequest.creator_user_id == creator_user_id)
            .order_by(PaymentRequest.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.db.scalars(stmt))

    def add(self, payment_request: PaymentRequest) -> PaymentRequest:
        if is_supabase_session(self.db):
            return self.db.add(payment_request)
        self.db.add(payment_request)
        self.db.flush()
        return payment_request


class ScheduledPaymentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_owned_by_id(self, owner_user_id: uuid.UUID, scheduled_payment_id: uuid.UUID) -> ScheduledPayment | None:
        if is_supabase_session(self.db):
            return self.db.fetch_one(
                ScheduledPayment,
                {"id": f"eq.{scheduled_payment_id}", "owner_user_id": f"eq.{owner_user_id}"},
            )
        return self.db.scalar(
            select(ScheduledPayment).where(
                ScheduledPayment.id == scheduled_payment_id,
                ScheduledPayment.owner_user_id == owner_user_id,
            )
        )

    def list_for_owner(self, owner_user_id: uuid.UUID, limit: int = 100, offset: int = 0) -> list[ScheduledPayment]:
        if is_supabase_session(self.db):
            return self.db.fetch_many(
                ScheduledPayment,
                {
                    "owner_user_id": f"eq.{owner_user_id}",
                    "order": "next_run_on.asc,created_at.desc",
                    "limit": str(limit),
                    "offset": str(offset),
                },
            )
        stmt = (
            select(ScheduledPayment)
            .where(ScheduledPayment.owner_user_id == owner_user_id)
            .order_by(ScheduledPayment.next_run_on.asc(), ScheduledPayment.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.db.scalars(stmt))

    def list_due_loan_autopayments(self, run_on: date) -> list[ScheduledPayment]:
        if is_supabase_session(self.db):
            return self.db.fetch_many(
                ScheduledPayment,
                {
                    "status": "eq.ACTIVE",
                    "next_run_on": f"lte.{run_on.isoformat()}",
                    "description": "like.LOAN_AUTOPAY:*",
                    "order": "next_run_on.asc",
                    "limit": "500",
                },
            )
        stmt = (
            select(ScheduledPayment)
            .where(
                ScheduledPayment.status == ScheduledPaymentStatus.ACTIVE,
                ScheduledPayment.next_run_on <= run_on,
                ScheduledPayment.description.like("LOAN_AUTOPAY:%"),
            )
            .order_by(ScheduledPayment.next_run_on.asc())
            .limit(500)
        )
        return list(self.db.scalars(stmt))

    def add(self, scheduled_payment: ScheduledPayment) -> ScheduledPayment:
        if is_supabase_session(self.db):
            return self.db.add(scheduled_payment)
        self.db.add(scheduled_payment)
        self.db.flush()
        return scheduled_payment

    def delete(self, scheduled_payment: ScheduledPayment) -> None:
        if is_supabase_session(self.db):
            self.db.delete(scheduled_payment)
            return
        self.db.delete(scheduled_payment)
        self.db.flush()


class BillSplitRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, bill_split: BillSplit) -> BillSplit:
        if is_supabase_session(self.db):
            return self.db.add(bill_split)
        self.db.add(bill_split)
        self.db.flush()
        return bill_split

    def add_participant(self, participant: BillSplitParticipant) -> BillSplitParticipant:
        if is_supabase_session(self.db):
            return self.db.add(participant)
        self.db.add(participant)
        self.db.flush()
        return participant

    def get_owned_by_id(self, owner_user_id: uuid.UUID, bill_split_id: uuid.UUID) -> BillSplit | None:
        if is_supabase_session(self.db):
            return self.db.fetch_one(BillSplit, {"id": f"eq.{bill_split_id}", "owner_user_id": f"eq.{owner_user_id}"})
        return self.db.scalar(select(BillSplit).where(BillSplit.id == bill_split_id, BillSplit.owner_user_id == owner_user_id))

    def get_visible_by_id(self, user_id: uuid.UUID, bill_split_id: uuid.UUID) -> BillSplit | None:
        bill_split = self.get_owned_by_id(user_id, bill_split_id)
        if bill_split is not None:
            return bill_split
        participant = self.get_participant_for_user(user_id, bill_split_id)
        if participant is None:
            return None
        if is_supabase_session(self.db):
            return self.db.get(BillSplit, bill_split_id)
        return self.db.get(BillSplit, bill_split_id)

    def list_for_user(self, user_id: uuid.UUID, limit: int = 100, offset: int = 0) -> list[BillSplit]:
        if is_supabase_session(self.db):
            owned = self.db.fetch_many(
                BillSplit,
                {"owner_user_id": f"eq.{user_id}", "order": "created_at.desc", "limit": str(limit), "offset": str(offset)},
            )
            participant_rows = self.db.fetch_many(BillSplitParticipant, {"participant_user_id": f"eq.{user_id}"})
            seen = {item.id for item in owned}
            missing_ids = {p.bill_split_id for p in participant_rows if p.bill_split_id not in seen}
            if missing_ids:
                # One batched fetch instead of one self.db.get() per
                # participant row -- each was a separate HTTP round-trip.
                joined = ",".join(str(split_id) for split_id in missing_ids)
                for bill_split in self.db.fetch_many(BillSplit, {"id": f"in.({joined})"}):
                    owned.append(bill_split)
                    seen.add(bill_split.id)
            return sorted(owned, key=lambda item: item.created_at, reverse=True)[:limit]

        participant_split_ids = select(BillSplitParticipant.bill_split_id).where(BillSplitParticipant.participant_user_id == user_id)
        stmt = (
            select(BillSplit)
            .where((BillSplit.owner_user_id == user_id) | (BillSplit.id.in_(participant_split_ids)))
            .order_by(BillSplit.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.db.scalars(stmt))

    def list_participants(self, bill_split_id: uuid.UUID) -> list[BillSplitParticipant]:
        if is_supabase_session(self.db):
            return self.db.fetch_many(
                BillSplitParticipant,
                {"bill_split_id": f"eq.{bill_split_id}", "order": "created_at.asc"},
            )
        return list(
            self.db.scalars(
                select(BillSplitParticipant)
                .where(BillSplitParticipant.bill_split_id == bill_split_id)
                .order_by(BillSplitParticipant.created_at.asc())
            )
        )

    def list_participants_for_splits(
        self, bill_split_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[BillSplitParticipant]]:
        """Batched form of list_participants -- one query for every split
        instead of one query per split. Listing splits used to call
        list_participants per row, which under the Supabase REST backend
        means one extra HTTP round-trip per split; an account with a dozen
        splits took 2+ seconds just to load its list."""
        grouped: dict[uuid.UUID, list[BillSplitParticipant]] = {split_id: [] for split_id in bill_split_ids}
        if not bill_split_ids:
            return grouped
        if is_supabase_session(self.db):
            joined = ",".join(str(split_id) for split_id in bill_split_ids)
            rows = self.db.fetch_many(
                BillSplitParticipant,
                {"bill_split_id": f"in.({joined})", "order": "created_at.asc"},
            )
        else:
            rows = list(
                self.db.scalars(
                    select(BillSplitParticipant)
                    .where(BillSplitParticipant.bill_split_id.in_(bill_split_ids))
                    .order_by(BillSplitParticipant.created_at.asc())
                )
            )
        for row in rows:
            grouped[row.bill_split_id].append(row)
        return grouped

    def get_participant(self, participant_id: uuid.UUID) -> BillSplitParticipant | None:
        if is_supabase_session(self.db):
            return self.db.get(BillSplitParticipant, participant_id)
        return self.db.get(BillSplitParticipant, participant_id)

    def get_participant_for_user(self, user_id: uuid.UUID, bill_split_id: uuid.UUID) -> BillSplitParticipant | None:
        if is_supabase_session(self.db):
            return self.db.fetch_one(
                BillSplitParticipant,
                {"bill_split_id": f"eq.{bill_split_id}", "participant_user_id": f"eq.{user_id}"},
            )
        return self.db.scalar(
            select(BillSplitParticipant).where(
                BillSplitParticipant.bill_split_id == bill_split_id,
                BillSplitParticipant.participant_user_id == user_id,
            )
        )


class TransactionFolderRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, folder: TransactionFolder) -> TransactionFolder:
        if is_supabase_session(self.db):
            return self.db.add(folder)
        self.db.add(folder)
        self.db.flush()
        return folder

    def get_owned_by_id(self, owner_user_id: uuid.UUID, folder_id: uuid.UUID) -> TransactionFolder | None:
        if is_supabase_session(self.db):
            return self.db.fetch_one(TransactionFolder, {"id": f"eq.{folder_id}", "owner_user_id": f"eq.{owner_user_id}"})
        return self.db.scalar(
            select(TransactionFolder).where(TransactionFolder.id == folder_id, TransactionFolder.owner_user_id == owner_user_id)
        )

    def get_by_name(self, owner_user_id: uuid.UUID, name: str) -> TransactionFolder | None:
        if is_supabase_session(self.db):
            return self.db.fetch_one(TransactionFolder, {"owner_user_id": f"eq.{owner_user_id}", "name": f"eq.{name}"})
        return self.db.scalar(select(TransactionFolder).where(TransactionFolder.owner_user_id == owner_user_id, TransactionFolder.name == name))

    def list_for_owner(self, owner_user_id: uuid.UUID, limit: int = 100, offset: int = 0) -> list[TransactionFolder]:
        if is_supabase_session(self.db):
            return self.db.fetch_many(
                TransactionFolder,
                {"owner_user_id": f"eq.{owner_user_id}", "order": "created_at.desc", "limit": str(limit), "offset": str(offset)},
            )
        stmt = (
            select(TransactionFolder)
            .where(TransactionFolder.owner_user_id == owner_user_id)
            .order_by(TransactionFolder.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.db.scalars(stmt))

    def delete(self, folder: TransactionFolder) -> None:
        for item in self.list_items(folder.id):
            self.delete_item(item)
        if is_supabase_session(self.db):
            self.db.delete(folder)
            return
        self.db.delete(folder)
        self.db.flush()

    def add_item(self, item: TransactionFolderItem) -> TransactionFolderItem:
        if is_supabase_session(self.db):
            return self.db.add(item)
        self.db.add(item)
        self.db.flush()
        return item

    def get_item(self, folder_id: uuid.UUID, transaction_id: uuid.UUID) -> TransactionFolderItem | None:
        if is_supabase_session(self.db):
            return self.db.fetch_one(
                TransactionFolderItem,
                {"folder_id": f"eq.{folder_id}", "transaction_id": f"eq.{transaction_id}"},
            )
        return self.db.scalar(
            select(TransactionFolderItem).where(
                TransactionFolderItem.folder_id == folder_id,
                TransactionFolderItem.transaction_id == transaction_id,
            )
        )

    def get_item_for_transaction(self, transaction_id: uuid.UUID) -> TransactionFolderItem | None:
        """The transaction's folder membership, whichever folder that is.

        Unscoped by folder on purpose: a transaction belongs to exactly one
        folder (see TransactionFolderService.add_transaction), so this is
        what answers "is it already filed somewhere". Safe to leave unscoped
        by user too — only CARD_PAYMENT/SCHEDULED_PAYMENT/CASHBACK can be
        foldered, and none of those are visible to a second user the way a
        transfer's receiving side is.
        """
        if is_supabase_session(self.db):
            return self.db.fetch_one(TransactionFolderItem, {"transaction_id": f"eq.{transaction_id}"})
        return self.db.scalar(
            select(TransactionFolderItem).where(TransactionFolderItem.transaction_id == transaction_id)
        )

    def list_items(self, folder_id: uuid.UUID) -> list[TransactionFolderItem]:
        if is_supabase_session(self.db):
            return self.db.fetch_many(TransactionFolderItem, {"folder_id": f"eq.{folder_id}", "order": "added_at.asc"})
        return list(
            self.db.scalars(
                select(TransactionFolderItem)
                .where(TransactionFolderItem.folder_id == folder_id)
                .order_by(TransactionFolderItem.added_at.asc())
            )
        )

    def list_items_for_folders(self, folder_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[TransactionFolderItem]]:
        """Batched form of list_items -- see list_participants_for_splits."""
        grouped: dict[uuid.UUID, list[TransactionFolderItem]] = {folder_id: [] for folder_id in folder_ids}
        if not folder_ids:
            return grouped
        if is_supabase_session(self.db):
            joined = ",".join(str(folder_id) for folder_id in folder_ids)
            rows = self.db.fetch_many(TransactionFolderItem, {"folder_id": f"in.({joined})", "order": "added_at.asc"})
        else:
            rows = list(
                self.db.scalars(
                    select(TransactionFolderItem)
                    .where(TransactionFolderItem.folder_id.in_(folder_ids))
                    .order_by(TransactionFolderItem.added_at.asc())
                )
            )
        for row in rows:
            grouped[row.folder_id].append(row)
        return grouped

    def delete_item(self, item: TransactionFolderItem) -> None:
        if is_supabase_session(self.db):
            self.db.delete(item)
            return
        self.db.delete(item)
        self.db.flush()


class BulkTransferTemplateRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_owned_by_id(self, owner_user_id: uuid.UUID, template_id: uuid.UUID) -> BulkTransferTemplate | None:
        if is_supabase_session(self.db):
            return self.db.fetch_one(
                BulkTransferTemplate,
                {"id": f"eq.{template_id}", "owner_user_id": f"eq.{owner_user_id}"},
            )
        return self.db.scalar(
            select(BulkTransferTemplate).where(
                BulkTransferTemplate.id == template_id,
                BulkTransferTemplate.owner_user_id == owner_user_id,
            )
        )

    def list_for_owner(self, owner_user_id: uuid.UUID, limit: int = 100) -> list[BulkTransferTemplate]:
        if is_supabase_session(self.db):
            return self.db.fetch_many(
                BulkTransferTemplate,
                {"owner_user_id": f"eq.{owner_user_id}", "order": "created_at.desc", "limit": str(limit)},
            )
        stmt = (
            select(BulkTransferTemplate)
            .where(BulkTransferTemplate.owner_user_id == owner_user_id)
            .order_by(BulkTransferTemplate.created_at.desc())
            .limit(limit)
        )
        return list(self.db.scalars(stmt))

    def add(self, template: BulkTransferTemplate) -> BulkTransferTemplate:
        if is_supabase_session(self.db):
            return self.db.add(template)
        self.db.add(template)
        self.db.flush()
        return template

    def add_row(self, row: BulkTransferTemplateRow) -> BulkTransferTemplateRow:
        if is_supabase_session(self.db):
            return self.db.add(row)
        self.db.add(row)
        self.db.flush()
        return row

    def delete_row(self, row: BulkTransferTemplateRow) -> None:
        if is_supabase_session(self.db):
            self.db.delete(row)
            return
        self.db.delete(row)
        self.db.flush()

    def list_rows_for_template(self, template_id: uuid.UUID) -> list[BulkTransferTemplateRow]:
        if is_supabase_session(self.db):
            return self.db.fetch_many(
                BulkTransferTemplateRow,
                {"template_id": f"eq.{template_id}", "order": "created_at.asc", "limit": "200"},
            )
        stmt = (
            select(BulkTransferTemplateRow)
            .where(BulkTransferTemplateRow.template_id == template_id)
            .order_by(BulkTransferTemplateRow.created_at.asc())
        )
        return list(self.db.scalars(stmt))
