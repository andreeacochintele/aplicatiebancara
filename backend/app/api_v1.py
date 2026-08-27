"""Aggregates every module's router under a single /api/v1 prefix."""
from fastapi import APIRouter

from app.ai.orchestrator.router import router as ai_orchestrator_router
from app.analytics.router import router as analytics_router
from app.audit.router import router as audit_router
from app.auth.router import router as auth_router
from app.budgets.router import router as budgets_router
from app.business.router import router as business_router
from app.cards.router import router as cards_router
from app.credit.router import router as credit_router
from app.exports.router import router as exports_router
from app.fraud.router import router as fraud_router
from app.fx.router import router as fx_router
from app.merchants.router import router as merchants_router
from app.notifications.router import router as notifications_router
from app.payments.router import router as payments_router
from app.rewards.router import router as rewards_router
from app.savings.router import router as savings_router
from app.statements.router import router as statements_router
from app.transactions.router import router as transactions_router
from app.users.router import router as users_router
from app.wallets.router import router as wallets_router

api_router = APIRouter()

# Implemented in Phase 1
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(wallets_router)
api_router.include_router(transactions_router)
api_router.include_router(statements_router)

# Structural placeholders for later phases (architecture.md §36, §40-42)
api_router.include_router(fx_router)
api_router.include_router(payments_router)
api_router.include_router(cards_router)
api_router.include_router(rewards_router)
api_router.include_router(merchants_router)
api_router.include_router(credit_router)
api_router.include_router(fraud_router)
api_router.include_router(notifications_router)
api_router.include_router(exports_router)
api_router.include_router(analytics_router)
api_router.include_router(budgets_router)
api_router.include_router(savings_router)
api_router.include_router(audit_router)
api_router.include_router(business_router)

# Phase 5 AI (in progress) — orchestrator only; specialized agents are stubs
api_router.include_router(ai_orchestrator_router)
