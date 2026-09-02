"""Shared, static "app & product knowledge" — general information about
what this app/bank offers, available to any agent that wants it as system-
prompt context.

Not a tool, not DB-backed, never user-specific: this is one markdown file
loaded once at import time, same mechanism ai/support/agent.py already uses
for its own knowledge/*.md files (see that module's docstring). The
difference is ownership — this one lives here, outside any single agent's
package, because more than one agent reads it (ai/support/agent.py as
primary consumer, ai/personal_finance/agent.py for conceptual "what does my
card tier get me"-style questions) and it would be wrong for one of them to
reach into the other's private knowledge/ directory.

Deliberately excludes anything fraud/security-sensitive — that stays in
ai/support/knowledge/fraud_policy.md, kept separate on purpose — and
anything requiring a live lookup (a specific user's real tier, points
balance, or benefits). This is reference material only: what tiers exist,
what they generally offer, what the app can do, described the way a bank's
own product pages would describe it to any customer.
"""
from pathlib import Path

_KNOWLEDGE_DIR = Path(__file__).parent


def get_app_overview() -> str:
    return (_KNOWLEDGE_DIR / "app_overview.md").read_text(encoding="utf-8")
