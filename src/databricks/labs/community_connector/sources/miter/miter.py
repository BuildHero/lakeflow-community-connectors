"""Miter connector — general-ledger tables from the Miter v2 REST API."""

import json
import math
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator, Sequence

import requests
from pyspark.sql.types import StructType

from databricks.labs.community_connector.interface import (
    LakeflowConnect,
    SupportsPartitionedStream,
)
from databricks.labs.community_connector.sources.miter.miter_schemas import (
    CURSOR_FIELD,
    DEFAULT_BASE_URL,
    DEFAULT_MAX_PARTITIONS,
    DEFAULT_MAX_RECORDS_PER_BATCH,
    DEFAULT_PAGE_SIZE,
    DEFAULT_PARENTS_PER_PARTITION,
    DEFAULT_WINDOW_SECONDS,
    INITIAL_BACKOFF,
    LEDGER_LINE_ITEMS,
    MAX_PAGE_SIZE,
    MAX_RETRIES,
    REQUEST_TIMEOUT,
    RETRIABLE_STATUS_CODES,
    STRUCT_FIELDS,
    SUPPORTED_TABLES,
    TABLE_ENDPOINTS,
    TABLE_METADATA,
    TABLE_SCHEMAS,
)


def _now_iso() -> str:
    return _to_iso(datetime.now(timezone.utc))


def _to_iso(value: datetime) -> str:
    """Canonical Miter datetime: millisecond precision, ``Z`` suffix."""
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _parse_iso(value: str) -> datetime:
    """Parse an ISO-8601 timestamp; naive values are treated as UTC.

    Cursors arrive in several shapes (API values with or without
    milliseconds, user-supplied option strings, canonical values this
    connector emits), so ordering is always decided on parsed datetimes
    rather than on the raw strings.
    """
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _scalar_to_str(value: Any) -> Any:
    """Flatten a polymorphic custom-field value to a string."""
    if value is None or isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


class MiterLakeflowConnect(LakeflowConnect, SupportsPartitionedStream):
    """LakeflowConnect implementation for the Miter v2 REST API.

    Connection options:
        api_token   Miter API token, sent as ``Authorization: Bearer``.
        base_url    Optional API root. Defaults to the production URL
                    ``https://api.miter.com/api/v2``; point it at
                    ``https://api.staging.miter.com/api/v2`` when using a
                    staging token.

    Per-table options:
        page_size               API ``limit`` per request (default 100, max 1000).
        window_seconds          Partition / microbatch width in seconds (default 86400).
        max_partitions          Upper bound on partitions per microbatch (default 200).
        max_records_per_batch   Cap on records returned by one ``read_table`` call.
        start_timestamp         Lower bound for the very first read.
        lookback_seconds        Seconds subtracted from the start cursor at query time.
        max_pages               Safety cap on pages per paginated call (0 = unlimited).
        parent_ids              ledger_line_items only: comma-separated parent
                                ledger-entry ids to restrict the sync to.
        max_parents             ledger_line_items only: cap on parents (0 = unlimited).
        parents_per_partition   ledger_line_items only: parents per partition (default 20).
    """

    def __init__(self, options: dict[str, str]) -> None:
        super().__init__(options)

        api_token = options.get("api_token")
        if not api_token:
            raise ValueError("Miter connector requires connection option 'api_token'")
        self._api_token = api_token
        self._base_url = (options.get("base_url") or DEFAULT_BASE_URL).rstrip("/")

        # Cap every offset at construction time so Trigger.AvailableNow
        # converges instead of chasing rows written while the run is in
        # flight. The next trigger builds a fresh instance with a newer cap.
        self._init_time = _now_iso()

    # ------------------------------------------------------------------
    # LakeflowConnect — discovery
    # ------------------------------------------------------------------

    def list_tables(self) -> list[str]:
        return list(SUPPORTED_TABLES)

    def get_table_schema(
        self, table_name: str, table_options: dict[str, str]
    ) -> StructType:
        self._validate_table(table_name)
        return TABLE_SCHEMAS[table_name]

    def read_table_metadata(
        self, table_name: str, table_options: dict[str, str]
    ) -> dict:
        self._validate_table(table_name)
        return dict(TABLE_METADATA[table_name])

    # ------------------------------------------------------------------
    # SupportsPartitionedStream
    # ------------------------------------------------------------------

    def is_partitioned(self, table_name: str) -> bool:
        return table_name in SUPPORTED_TABLES

    def latest_offset(
        self,
        table_name: str,
        table_options: dict[str, str],
        start_offset: dict | None = None,
    ) -> dict:
        """High-water mark for the table, capped at the connector's init time.

        Metadata-only: the cap is a wall-clock snapshot, so no API call is
        needed. Returning a constant also guarantees the second call of a
        trigger matches the first, which is how Trigger.AvailableNow stops.
        """
        self._validate_table(table_name)
        return {"cursor": self._init_time}

    def get_partitions(
        self,
        table_name: str,
        table_options: dict[str, str],
        start_offset: dict | None = None,
        end_offset: dict | None = None,
    ) -> Sequence[dict]:
        """Split the ``(start, end]`` updated_at range into parallel units."""
        self._validate_table(table_name)

        if start_offset is None and end_offset is None:
            since = table_options.get("start_timestamp")
            until = self._init_time
        else:
            since = (start_offset or {}).get("cursor") or table_options.get(
                "start_timestamp"
            )
            until = (end_offset or {}).get("cursor") or self._init_time

        until_dt = _parse_iso(until)
        if since is not None and _parse_iso(since) >= until_dt:
            return []

        since = self._apply_lookback(since, table_options)

        if table_name == LEDGER_LINE_ITEMS:
            return self._parent_partitions(table_options, since, until)

        if since is None:
            since = self._discover_oldest_cursor(table_name, table_options)
        if since is None:
            # Empty table, or the peek failed — one unbounded partition.
            return [{"until": until}]

        return self._window_partitions(since, until, table_options)

    def read_partition(
        self,
        table_name: str,
        partition: dict,
        table_options: dict[str, str],
    ) -> Iterator[dict]:
        """Read one partition on an executor."""
        self._validate_table(table_name)
        since = partition.get("since")
        until = partition.get("until")

        if table_name == LEDGER_LINE_ITEMS:
            for parent_id in partition.get("parent_ids") or []:
                yield from self._read_line_items(parent_id, since, until, table_options)
            return

        path = TABLE_ENDPOINTS[table_name]["path"]
        params = self._list_params(since, until, table_options)
        for record in self._paginate(path, params, table_options):
            yield self._normalize(table_name, record)

    # ------------------------------------------------------------------
    # LakeflowConnect — single-driver fallback read
    # ------------------------------------------------------------------

    def read_table(
        self, table_name: str, start_offset: dict, table_options: dict[str, str]
    ) -> tuple[Iterator[dict], dict]:
        """Sequential sliding-window read, used when partitioning is off.

        Each call drains one ``window_seconds`` slice of the cursor range and
        advances the offset to the window end, so the offset converges on the
        init-time cap and the trigger terminates.
        """
        self._validate_table(table_name)
        start_offset = start_offset or {}

        since = start_offset.get("cursor") or table_options.get("start_timestamp")
        if since is None and table_name != LEDGER_LINE_ITEMS:
            since = self._discover_oldest_cursor(table_name, table_options)

        if since is not None and _parse_iso(since) >= _parse_iso(self._init_time):
            return iter([]), start_offset or {"cursor": self._init_time}

        if since is None:
            # No lower bound available: read the whole history in one batch.
            window_end = self._init_time
        else:
            window_seconds = self._int_option(
                table_options, "window_seconds", DEFAULT_WINDOW_SECONDS, minimum=1
            )
            window_end_dt = _parse_iso(since) + timedelta(seconds=window_seconds)
            window_end = min(_to_iso(window_end_dt), self._init_time, key=_parse_iso)

        query_since = self._apply_lookback(since, table_options)

        # ledger_line_items fans out over parents, so a partial window would
        # strand the parents not yet visited. The window must be drained;
        # window_seconds governs the batch size instead of the record cap.
        max_records = (
            None
            if table_name == LEDGER_LINE_ITEMS
            else self._int_option(
                table_options,
                "max_records_per_batch",
                DEFAULT_MAX_RECORDS_PER_BATCH,
                minimum=1,
            )
        )

        records: list[dict] = []
        drained = True
        for record in self._iter_window(
            table_name, query_since, window_end, table_options
        ):
            records.append(record)
            if max_records is None or len(records) < max_records:
                continue
            # Only stop early once the cursor has moved past the incoming
            # offset; otherwise (with a lookback in play) the next call would
            # resume at or before where this one started and never progress.
            if since is None or _parse_iso(record[CURSOR_FIELD]) > _parse_iso(since):
                drained = False
                break

        if drained and not records and table_name != LEDGER_LINE_ITEMS:
            # Empty window: skip ahead to the next row that actually exists
            # instead of stepping through every intervening window.
            end_offset = {
                "cursor": self._next_data_cursor(table_name, window_end, table_options)
            }
        elif drained:
            end_offset = {"cursor": window_end}
        else:
            # ``after_exclusive`` guarantees every record's cursor is strictly
            # greater than ``since``, so resuming here always makes progress.
            end_offset = {"cursor": records[-1][CURSOR_FIELD]}

        if start_offset == end_offset:
            return iter([]), start_offset
        return iter(records), end_offset

    # ------------------------------------------------------------------
    # Partition planning
    # ------------------------------------------------------------------

    def _window_partitions(
        self, since: str, until: str, table_options: dict[str, str]
    ) -> list[dict]:
        window_seconds = self._int_option(
            table_options, "window_seconds", DEFAULT_WINDOW_SECONDS, minimum=1
        )
        max_partitions = self._int_option(
            table_options, "max_partitions", DEFAULT_MAX_PARTITIONS, minimum=1
        )

        since_dt = _parse_iso(since)
        until_dt = _parse_iso(until)
        total_seconds = (until_dt - since_dt).total_seconds()
        if total_seconds <= 0:
            return []

        count = math.ceil(total_seconds / window_seconds)
        if count > max_partitions:
            window_seconds = math.ceil(total_seconds / max_partitions)

        partitions: list[dict] = []
        cursor_dt = since_dt
        while cursor_dt < until_dt:
            next_dt = min(cursor_dt + timedelta(seconds=window_seconds), until_dt)
            partitions.append(
                {"since": _to_iso(cursor_dt), "until": _to_iso(next_dt)}
            )
            cursor_dt = next_dt
        # The final boundary must match the requested end exactly so the
        # committed offset and the data read stay in step.
        if partitions:
            partitions[-1]["until"] = until
        return partitions

    def _parent_partitions(
        self, table_options: dict[str, str], since: str | None, until: str
    ) -> list[dict]:
        parent_ids = self._resolve_parent_ids(table_options)
        if not parent_ids:
            return []

        chunk = self._int_option(
            table_options,
            "parents_per_partition",
            DEFAULT_PARENTS_PER_PARTITION,
            minimum=1,
        )
        partitions: list[dict] = []
        for start in range(0, len(parent_ids), chunk):
            partition: dict = {
                "parent_ids": parent_ids[start : start + chunk],
                "until": until,
            }
            if since is not None:
                partition["since"] = since
            partitions.append(partition)
        return partitions

    def _resolve_parent_ids(self, table_options: dict[str, str]) -> list[str]:
        """Parent ledger-entry ids to fan the nested read out over.

        Parents are listed unbounded by the child's cursor: a line item can be
        updated long after its parent entry was, so restricting parents to the
        current window would silently drop those children.
        """
        configured = table_options.get("parent_ids")
        if configured:
            ids = [pid.strip() for pid in configured.split(",") if pid.strip()]
        else:
            parent_table = TABLE_ENDPOINTS[LEDGER_LINE_ITEMS]["parent_table"]
            params = self._list_params(None, None, table_options)
            params["output_fields"] = "id"
            ids = [
                record["id"]
                for record in self._paginate(
                    TABLE_ENDPOINTS[parent_table]["path"], params, table_options
                )
                if record.get("id")
            ]

        max_parents = self._int_option(table_options, "max_parents", 0, minimum=0)
        if max_parents:
            ids = ids[:max_parents]
        return ids

    def _discover_oldest_cursor(
        self, table_name: str, table_options: dict[str, str]
    ) -> str | None:
        """Peek at the oldest row so the first read has a bounded lower edge.

        The API sorts ascending on request, so a single one-row page returns
        the oldest record. One second is subtracted because the resulting
        value is used as an *exclusive* lower bound.
        """
        params = {
            "sort[field]": CURSOR_FIELD,
            "sort[direction]": "ascending",
            "limit": "1",
            "output_fields": CURSOR_FIELD,
        }
        body = self._get(TABLE_ENDPOINTS[table_name]["path"], params)
        results = (body.get("data") or {}).get("results") or []
        if not results:
            return None
        oldest = results[0].get(CURSOR_FIELD)
        if not oldest:
            return None
        return _to_iso(_parse_iso(oldest) - timedelta(seconds=1))

    def _next_data_cursor(
        self, table_name: str, after: str, table_options: dict[str, str]
    ) -> str:
        """Cursor just before the oldest row newer than ``after``.

        Used to collapse long empty stretches in the sequential read path.
        Falls back to the init-time cap when nothing newer exists, which is
        what makes ``read_table`` converge in a bounded number of calls.
        """
        params = {
            "sort[field]": CURSOR_FIELD,
            "sort[direction]": "ascending",
            "sort[after_exclusive]": after,
            "sort[before_inclusive]": self._init_time,
            "limit": "1",
            "output_fields": CURSOR_FIELD,
        }
        body = self._get(TABLE_ENDPOINTS[table_name]["path"], params)
        results = (body.get("data") or {}).get("results") or []
        next_value = results[0].get(CURSOR_FIELD) if results else None
        if not next_value:
            return self._init_time
        candidate = _to_iso(_parse_iso(next_value) - timedelta(seconds=1))
        return max(candidate, after, key=_parse_iso)

    def _apply_lookback(
        self, since: str | None, table_options: dict[str, str]
    ) -> str | None:
        lookback = self._int_option(table_options, "lookback_seconds", 0, minimum=0)
        if since is None or lookback <= 0:
            return since
        return _to_iso(_parse_iso(since) - timedelta(seconds=lookback))

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    def _iter_window(
        self,
        table_name: str,
        since: str | None,
        until: str,
        table_options: dict[str, str],
    ) -> Iterator[dict]:
        if table_name == LEDGER_LINE_ITEMS:
            for parent_id in self._resolve_parent_ids(table_options):
                yield from self._read_line_items(
                    parent_id, since, until, table_options
                )
            return

        params = self._list_params(since, until, table_options)
        for record in self._paginate(
            TABLE_ENDPOINTS[table_name]["path"], params, table_options
        ):
            yield self._normalize(table_name, record)

    def _read_line_items(
        self,
        parent_id: str,
        since: str | None,
        until: str | None,
        table_options: dict[str, str],
    ) -> Iterator[dict]:
        path = TABLE_ENDPOINTS[LEDGER_LINE_ITEMS]["path"].format(parent_id=parent_id)
        params = self._list_params(since, until, table_options)
        for record in self._paginate(path, params, table_options):
            yield self._normalize(LEDGER_LINE_ITEMS, record)

    def _list_params(
        self,
        since: str | None,
        until: str | None,
        table_options: dict[str, str],
    ) -> dict[str, str]:
        params = {
            "sort[field]": CURSOR_FIELD,
            "sort[direction]": "ascending",
            "limit": str(self._page_size(table_options)),
        }
        if since:
            params["sort[after_exclusive]"] = since
        if until:
            params["sort[before_inclusive]"] = until
        return params

    def _paginate(
        self, path: str, params: dict[str, str], table_options: dict[str, str]
    ) -> Iterator[dict]:
        """Walk the opaque ``data.next_page`` cursor until it goes null."""
        max_pages = self._int_option(table_options, "max_pages", 0, minimum=0)
        query = dict(params)
        seen_cursors: set[str] = set()
        pages = 0

        while True:
            body = self._get(path, query)
            data = body.get("data") or {}
            yield from data.get("results") or []

            pages += 1
            if max_pages and pages >= max_pages:
                return

            next_page = data.get("next_page")
            # A repeated cursor would loop forever; treat it as the end.
            if not next_page or next_page in seen_cursors:
                return
            seen_cursors.add(next_page)
            query["page"] = next_page

    def _get(self, path: str, params: dict[str, str]) -> dict:
        url = f"{self._base_url}{path}"
        headers = {
            "Authorization": f"Bearer {self._api_token}",
            "Accept": "application/json",
        }

        backoff = INITIAL_BACKOFF
        response = None
        for attempt in range(MAX_RETRIES):
            response = self._session().get(
                url, headers=headers, params=params, timeout=REQUEST_TIMEOUT
            )
            if response.status_code not in RETRIABLE_STATUS_CODES:
                break
            if attempt < MAX_RETRIES - 1:
                time.sleep(self._retry_delay(response, backoff))
                backoff *= 2

        if response.status_code != 200:
            raise RuntimeError(
                f"Miter API request failed: GET {path} -> "
                f"{response.status_code} {response.text[:500]}"
            )
        return response.json()

    @staticmethod
    def _retry_delay(response, backoff: float) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return max(float(retry_after), 0.0)
            except ValueError:
                pass
        return backoff

    def _session(self) -> requests.Session:
        session = getattr(self, "_http_session", None)
        if session is None:
            session = requests.Session()
            self._http_session = session
        return session

    def __getstate__(self) -> dict:
        # The HTTP session is not picklable; executors build their own.
        state = dict(self.__dict__)
        state.pop("_http_session", None)
        return state

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize(table_name: str, record: dict) -> dict:
        for field_name in STRUCT_FIELDS.get(table_name, ()):  # empty struct -> None
            if record.get(field_name) == {}:
                record[field_name] = None

        if table_name == LEDGER_LINE_ITEMS:
            values = record.get("custom_field_values")
            if isinstance(values, list):
                record["custom_field_values"] = [
                    {
                        "custom_field_id": item.get("custom_field_id"),
                        "value": _scalar_to_str(item.get("value")),
                    }
                    for item in values
                    if isinstance(item, dict)
                ]
        return record

    def _page_size(self, table_options: dict[str, str]) -> int:
        size = self._int_option(
            table_options, "page_size", DEFAULT_PAGE_SIZE, minimum=1
        )
        return min(size, MAX_PAGE_SIZE)

    @staticmethod
    def _int_option(
        table_options: dict[str, str], key: str, default: int, *, minimum: int
    ) -> int:
        raw = table_options.get(key)
        if raw is None or raw == "":
            return default
        try:
            return max(int(raw), minimum)
        except (TypeError, ValueError):
            return default

    def _validate_table(self, table_name: str) -> None:
        if table_name not in SUPPORTED_TABLES:
            raise ValueError(
                f"Table '{table_name}' is not supported. "
                f"Supported tables: {list(SUPPORTED_TABLES)}"
            )
