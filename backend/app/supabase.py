"""Small Supabase REST adapter used when direct Postgres ports are unavailable.

This is intentionally narrow: it preserves the service/repository shape while
we migrate modules gradually from SQLAlchemy sessions to Supabase REST calls.
"""
import json
import re
import uuid
from collections.abc import Iterable, Mapping
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, TypeVar
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from sqlalchemy import inspect as sa_inspect

from app.config import get_settings

ModelT = TypeVar("ModelT")


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def seed_uuid(namespace: uuid.UUID, name: str) -> str:
    return str(uuid.uuid5(namespace, name))


class SupabaseRestSession:
    def __init__(self, url: str | None = None, key: str | None = None) -> None:
        settings = get_settings()
        self.url = (url or settings.SUPABASE_URL or "").rstrip("/")
        self.key = key or settings.SUPABASE_KEY or ""
        if not self.url or not self.key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set for Supabase REST mode.")
        self.base_url = f"{self.url}/rest/v1"
        self.headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }
        self._tracked: dict[tuple[str, str], Any] = {}
        # A snapshot of each tracked row's payload as of the last time we
        # fetched or wrote it — lets flush() skip PATCHing rows nothing
        # actually changed on (see flush() below).
        self._snapshots: dict[tuple[str, str], dict[str, object]] = {}
        self._unsupported_patch_columns: dict[str, set[str]] = {}

    def get(self, model: type[ModelT], row_id: uuid.UUID) -> ModelT | None:
        primary_key = self._primary_key_name(model)
        return self.fetch_one(model, {primary_key: f"eq.{row_id}"})

    def fetch_one(self, model: type[ModelT], filters: Mapping[str, str]) -> ModelT | None:
        rows = self.fetch_many(model, {**filters, "limit": "1"})
        return rows[0] if rows else None

    def fetch_many(self, model: type[ModelT], params: Mapping[str, str]) -> list[ModelT]:
        rows = self.request("GET", self._table_name(model), params=params) or []
        return [self._hydrate(model, row) for row in rows]

    def request(
        self,
        method: str,
        table: str,
        *,
        params: Mapping[str, str] | None = None,
        body: object | None = None,
        prefer: str | None = None,
    ) -> object:
        query = f"?{urlencode(params)}" if params else ""
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = dict(self.headers)
        if prefer:
            headers["Prefer"] = prefer
        request = Request(f"{self.base_url}/{table}{query}", data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=30) as response:
                raw = response.read()
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Supabase REST request failed with HTTP {exc.code}: {detail}") from exc
        if not raw:
            return None
        return json.loads(raw.decode("utf-8"))

    def add(self, model: object) -> object:
        self._ensure_defaults(model)
        table = self._table_name(type(model))
        payload = self._model_payload(model)
        for column in self._unsupported_patch_columns.get(table, set()):
            payload.pop(column, None)
        self._insert_row(table, payload)
        self._track(model)
        return model

    def delete(self, model: object) -> None:
        primary_key = self._primary_key_name(type(model))
        row_id = getattr(model, primary_key, None)
        if row_id is None:
            return
        table = self._table_name(type(model))
        self.request("DELETE", table, params={primary_key: f"eq.{row_id}"}, prefer="return=minimal")
        key = (table, str(row_id))
        self._tracked.pop(key, None)
        self._snapshots.pop(key, None)

    def flush(self) -> None:
        # Every fetched row is "tracked" (see _track), but most of them were
        # only ever read — re-PATCHing all of them on every flush() (and
        # flush() runs more than once per request) is what made a handful of
        # real writes balloon into 50+ HTTP round-trips. Comparing against
        # the snapshot taken at fetch/write time skips the ones nothing
        # actually changed on; this never alters what gets written, only
        # skips writes that would be a no-op anyway.
        #
        # include_nulls=True here (and in the matching _track() snapshot
        # below) is deliberate: unlike add()'s INSERT, a tracked row already
        # exists, so a column holding None in memory means "the app wants
        # this cleared", not "let the DB default apply" — omitting it would
        # silently no-op the clear against PostgREST, which only touches
        # keys present in the PATCH body.
        for key, model in list(self._tracked.items()):
            primary_key = self._primary_key_name(type(model))
            row_id = getattr(model, primary_key, None)
            if row_id is None:
                continue
            payload = self._model_payload(model, excluded_columns={primary_key}, include_nulls=True)
            table = self._table_name(type(model))
            for column in self._unsupported_patch_columns.get(table, set()):
                payload.pop(column, None)
            if payload == self._snapshots.get(key):
                continue
            self._patch_row(table, primary_key, row_id, payload)
            self._snapshots[key] = payload

    def _insert_row(self, table: str, payload: dict[str, object]) -> None:
        while True:
            try:
                self.request("POST", table, body=payload, prefer="return=minimal")
                return
            except RuntimeError as exc:
                missing_column = self._missing_schema_column(table, exc)
                if missing_column is None or missing_column not in payload:
                    raise
                self._unsupported_patch_columns.setdefault(table, set()).add(missing_column)
                payload.pop(missing_column, None)

    def _patch_row(self, table: str, primary_key: str, row_id: object, payload: dict[str, object]) -> None:
        while True:
            if not payload:
                return
            try:
                self.request(
                    "PATCH",
                    table,
                    params={primary_key: f"eq.{row_id}"},
                    body=payload,
                    prefer="return=minimal",
                )
                return
            except RuntimeError as exc:
                missing_column = self._missing_schema_column(table, exc)
                if missing_column is None or missing_column not in payload:
                    raise
                self._unsupported_patch_columns.setdefault(table, set()).add(missing_column)
                payload.pop(missing_column, None)

    def _missing_schema_column(self, table: str, exc: RuntimeError) -> str | None:
        match = re.search(r"Could not find the '([^']+)' column of '([^']+)'", str(exc))
        if match is None:
            return None
        column_name, table_name = match.groups()
        return column_name if table_name == table else None

    def commit(self) -> None:
        self.flush()

    def close(self) -> None:
        self._tracked.clear()
        self._snapshots.clear()

    def _hydrate(self, model: type[ModelT], row: Mapping[str, Any]) -> ModelT:
        values = {
            column.name: self._python_value(row[column.name], column.type)
            for column in sa_inspect(model).columns
            if column.name in row
        }
        item = model(**values)
        self._track(item)
        return item

    def _track(self, model: object) -> None:
        primary_key = self._primary_key_name(type(model))
        row_id = getattr(model, primary_key, None)
        if row_id is not None:
            key = (self._table_name(type(model)), str(row_id))
            self._tracked[key] = model
            self._snapshots[key] = self._model_payload(model, excluded_columns={primary_key}, include_nulls=True)

    def _ensure_defaults(self, model: object) -> None:
        if hasattr(model, "id") and getattr(model, "id", None) is None:
            setattr(model, "id", uuid.uuid4())
        for column in sa_inspect(type(model)).columns:
            if getattr(model, column.name) is None and column.default is not None:
                default = column.default.arg
                if not callable(default):
                    setattr(model, column.name, default)
        now = datetime.now(timezone.utc)
        for field in ("created_at", "updated_at", "last_activity_at", "first_seen_at", "last_seen_at"):
            if hasattr(model, field) and getattr(model, field, None) is None:
                setattr(model, field, now)

    def _model_payload(
        self,
        model: object,
        *,
        excluded_columns: set[str] | None = None,
        include_nulls: bool = False,
    ) -> dict[str, object]:
        excluded_columns = excluded_columns or set()
        payload: dict[str, object] = {}
        for column in sa_inspect(type(model)).columns:
            if column.name in excluded_columns:
                continue
            value = getattr(model, column.name)
            if value is not None or include_nulls:
                payload[column.name] = self._json_value(value)
        return payload

    def _json_value(self, value: object) -> object:
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, uuid.UUID):
            return str(value)
        if isinstance(value, Decimal):
            return f"{value:.2f}"
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        return value

    def _python_value(self, value: object, column_type: object) -> object:
        if value is None:
            return None
        enum_class = getattr(column_type, "enum_class", None)
        if enum_class is not None:
            return enum_class(value)
        try:
            python_type = column_type.python_type
        except (AttributeError, NotImplementedError):
            python_type = None
        if python_type is uuid.UUID and isinstance(value, str):
            return uuid.UUID(value)
        if python_type is Decimal and not isinstance(value, Decimal):
            return Decimal(str(value))
        if python_type is datetime and isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        if python_type is date and isinstance(value, str):
            return date.fromisoformat(value)
        return value

    def _table_name(self, model: type[object]) -> str:
        return model.__tablename__

    def _primary_key_name(self, model: type[object]) -> str:
        keys = [column.name for column in sa_inspect(model).primary_key]
        if len(keys) != 1:
            raise RuntimeError(f"Supabase REST adapter only supports single-column primary keys for {model.__name__}.")
        return keys[0]


def is_supabase_session(db: object) -> bool:
    return isinstance(db, SupabaseRestSession)
