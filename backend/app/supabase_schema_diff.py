"""Generate the exact SQL needed to bring the shared Supabase schema up to the
current Alembic head, using Supabase's own `alembic_version` row as the
starting point instead of assuming an empty schema.

`alembic upgrade head --sql` alone always starts from `base` in offline/--sql
mode — it has no DB connection to detect what's already applied. Against a
shared Supabase DB that already has migrations applied, that regenerates
CREATE TABLE statements for tables that already exist. This script reads the
real starting point over the Supabase REST API first (see
docs/supabase_rest_backend.md), then asks Alembic for only the delta.

Not imported by the application at runtime — run explicitly:

    docker compose exec backend python -m app.supabase_schema_diff

Requires SUPABASE_URL and SUPABASE_KEY to already be set (same as
DATABASE_BACKEND=supabase_rest). Prints the SQL to stdout — redirect it to a
file, review it, then paste into the Supabase SQL Editor:

    docker compose exec backend python -m app.supabase_schema_diff > supabase_update_pending.sql
"""
import subprocess
import sys
from pathlib import Path

from app.supabase import SupabaseRestSession

BACKEND_DIR = Path(__file__).resolve().parent.parent


def current_supabase_revisions() -> list[str]:
    session = SupabaseRestSession()
    rows = session.request("GET", "alembic_version", params={"select": "version_num"})
    return [row["version_num"] for row in rows or []]


def main() -> None:
    revisions = current_supabase_revisions()

    if not revisions:
        print(
            "alembic_version is empty on Supabase — schema hasn't been initialized "
            "there at all. Run the full history instead:\n"
            "  docker compose exec backend alembic upgrade head --sql > supabase_full_schema.sql",
            file=sys.stderr,
        )
        raise SystemExit(1)

    if len(revisions) > 1:
        print(
            f"Supabase has {len(revisions)} current revisions (mid-merge, unresolved "
            f"heads): {revisions}. This script only handles a single starting "
            "revision — resolve the merge manually, or generate per-branch ranges "
            "yourself with `alembic upgrade <rev>:head --sql` for each.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    start = revisions[0]
    result = subprocess.run(
        ["alembic", "upgrade", f"{start}:head", "--sql"],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        raise SystemExit(result.returncode)

    sql = result.stdout.strip()
    if sql == "BEGIN;\n\nCOMMIT;" or not sql:
        print(f"Supabase is already at head ({start}) — nothing to do.", file=sys.stderr)
        return

    print(sql)
    print(f"Generated {start} -> head.", file=sys.stderr)


if __name__ == "__main__":
    main()
