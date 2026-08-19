"""Card endpoints, scoped to the authenticated user."""
import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.cards.schemas import CardCreate, CardPaymentPreferencesPublic, CardPaymentPreferencesUpdate, CardPublic
from app.cards.service import CardService
from app.database import get_db
from app.users.models import User

router = APIRouter(prefix="/cards", tags=["cards"])


@router.get("", response_model=list[CardPublic])
def list_my_cards(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CardPublic]:
    return CardService(db).list_cards(current_user.id)


@router.post("", response_model=CardPublic, status_code=201)
def create_card(
    payload: CardCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CardPublic:
    card = CardService(db).create_card(current_user.id, payload)
    db.commit()
    return card


@router.get("/{card_id}", response_model=CardPublic)
def get_card(
    card_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CardPublic:
    return CardService(db).get_for_user(current_user.id, card_id)


@router.delete("/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_card(
    card_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    CardService(db).delete_card(current_user.id, card_id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/{card_id}/freeze", response_model=CardPublic)
def freeze_card(
    card_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CardPublic:
    card = CardService(db).freeze_card(current_user.id, card_id)
    db.commit()
    return card


@router.patch("/{card_id}/unfreeze", response_model=CardPublic)
def unfreeze_card(
    card_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CardPublic:
    card = CardService(db).unfreeze_card(current_user.id, card_id)
    db.commit()
    return card


@router.get("/{card_id}/payment-preferences", response_model=CardPaymentPreferencesPublic)
def get_payment_preferences(
    card_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CardPaymentPreferencesPublic:
    preferences = CardService(db).get_payment_preferences(current_user.id, card_id)
    db.commit()
    return preferences


@router.patch("/{card_id}/payment-preferences", response_model=CardPaymentPreferencesPublic)
def update_payment_preferences(
    card_id: uuid.UUID,
    payload: CardPaymentPreferencesUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CardPaymentPreferencesPublic:
    preferences = CardService(db).update_payment_preferences(current_user.id, card_id, payload)
    db.commit()
    return preferences
