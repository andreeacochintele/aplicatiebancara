"""HTTP layer for confirming / cancelling / polling an agent-drafted action.

No business logic here. The confirm endpoint takes only the action_id in
the path — never an amount or recipient in a body — so a tampered client
cannot change what gets executed. ActionService re-validates everything
from the stored draft.
"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.ai.actions.schemas import AgentActionResultPublic, CreditCardCollateralSelection, WalletCurrencySelection
from app.ai.actions.service import ActionService
from app.auth.dependencies import get_current_user
from app.database import get_db
from app.users.models import User

router = APIRouter(prefix="/ai/actions", tags=["ai-actions"])


@router.get("/{action_id}", response_model=AgentActionResultPublic)
def get_action(
    action_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentActionResultPublic:
    return ActionService(db).get(current_user.id, action_id)


@router.post("/{action_id}/confirm", response_model=AgentActionResultPublic)
def confirm_action(
    action_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentActionResultPublic:
    result = ActionService(db).confirm(current_user.id, action_id)
    db.commit()
    return result


@router.post("/{action_id}/cancel", response_model=AgentActionResultPublic)
def cancel_action(
    action_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentActionResultPublic:
    result = ActionService(db).cancel(current_user.id, action_id)
    db.commit()
    return result


@router.post("/{action_id}/credit-card-collateral", response_model=AgentActionResultPublic)
def select_credit_card_collateral(
    action_id: uuid.UUID,
    payload: CreditCardCollateralSelection,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentActionResultPublic:
    result = ActionService(db).select_credit_card_collateral(current_user.id, action_id, payload.wallet_id)
    db.commit()
    return result


@router.post("/{action_id}/wallet-currency", response_model=AgentActionResultPublic)
def select_wallet_currency(
    action_id: uuid.UUID,
    payload: WalletCurrencySelection,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentActionResultPublic:
    result = ActionService(db).select_wallet_currency(current_user.id, action_id, payload.currency)
    db.commit()
    return result
