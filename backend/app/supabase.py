"""Small Supabase REST adapter used when direct Postgres ports are unavailable.

This is intentionally narrow: it preserves the service/repository shape while
we migrate modules gradually from SQLAlchemy sessions to Supabase REST calls.
"""
import json
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
        self.request("POST", table, body=payload, prefer="return=minimal")
        self._track(model)
        return model

    def delete(self, model: object) -> None:
        primary_key = self._primary_key_name(type(model))
        row_id = getattr(model, primary_key, None)
        if row_id is None:
            return
        table = self._table_name(type(model))
        self.request("DELETE", table, params={primary_key: f"eq.{row_id}"}, prefer="return=minimal")
        self._tracked.pop((table, str(row_id)), None)

    def flush(self) -> None:
        for model in list(self._tracked.values()):
            primary_key = self._primary_key_name(type(model))
            row_id = getattr(model, primary_key, None)
            if row_id is None:
                continue
            table = self._table_name(type(model))
            self.request(
                "PATCH",
                table,
                params={primary_key: f"eq.{row_id}"},
                body=self._model_payload(model, excluded_columns={primary_key}),
                prefer="return=minimal",
            )

    def commit(self) -> None:
        self.flush()

    def close(self) -> None:
        self._tracked.clear()

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
            self._tracked[(self._table_name(type(model)), str(row_id))] = model

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
    ) -> dict[str, object]:
        excluded_columns = excluded_columns or set()
        payload: dict[str, object] = {}
        for column in sa_inspect(type(model)).columns:
            if column.name in excluded_columns:
                continue
            value = getattr(model, column.name)
            if value is not None:
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
