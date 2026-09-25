"""Sage Intacct connector (XML Gateway / "Intacct Web Services").

Reads 5 tables -- ``customers`` (CUSTOMER), ``vendors`` (VENDOR), ``invoices``
(ARINVOICE header), ``bills`` (APBILL header), and ``gl_entries`` (GLDETAIL)
-- via the legacy XML Gateway (``xmlgw.phtml``), chosen over the REST API
because REST has no equivalent for ``GLDETAIL`` (see
``intacct_api_doc.md`` for the full rationale).

Approach: standard ``LakeflowConnect`` (no partitioning). The XML Gateway
documents a hard per-company concurrency limit of **1 concurrent job**
(a 2nd request queues, a 3rd+ errors after ~30s) -- parallel reads across
Spark executors would be actively counterproductive here, so this connector
reads sequentially on the driver using the sliding time-window strategy
(Strategy A): every object exposes ``WHENMODIFIED`` and the query language
supports a genuine bounded range (``<and>`` of ``greaterthanorequalto`` +
``lessthan``), so each ``read_table`` call scopes its query to
``[since, since + window_seconds)`` rather than scanning to "now". This is
also required for ``gl_entries``: Sage's own docs warn that unfiltered (or
loosely filtered) ``GLDETAIL`` queries can time out because it's a
cross-subledger reporting view, not a table.

All 5 objects are read the same way (single query per window, offset-based
paging, ascending ``WHENMODIFIED`` order) since they share one
homogeneous API pattern.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Iterator

import requests
from pyspark.sql.types import BooleanType, DateType, StructType, TimestampType

from databricks.labs.community_connector.interface import LakeflowConnect
from databricks.labs.community_connector.sources.intacct.intacct_schemas import (
    CURSOR_FIELD,
    DEFAULT_PAGESIZE,
    INITIAL_BACKOFF,
    MAX_PAGESIZE,
    MAX_RETRIES,
    PRIMARY_KEY_FIELD,
    RETRIABLE_ERROR_KEYWORDS,
    RETRIABLE_HTTP_STATUS_CODES,
    TABLE_FIELDS,
    TABLE_SCHEMAS,
    TABLE_TO_OBJECT,
)
from databricks.labs.community_connector.sources.intacct.intacct_xml import (
    IntacctApiError,
    IntacctSessionExpiredError,
    build_login_envelope,
    build_session_envelope,
    from_intacct_timestamp,
    get_api_session_function_xml,
    parse_response,
    query_function_xml,
    range_filter_xml,
    to_intacct_timestamp,
)

DEFAULT_XMLGW_URL = "https://api.intacct.com/ia/xml/xmlgw.phtml"


class IntacctLakeflowConnect(LakeflowConnect):
    """LakeflowConnect implementation for Sage Intacct (XML Gateway)."""

    def __init__(self, options: dict[str, str]) -> None:
        super().__init__(options)
        self._sender_id = options["sender_id"]
        self._sender_password = options["sender_password"]
        self._company_id = options["company_id"]
        self._user_id = options["user_id"]
        self._user_password = options["user_password"]
        self._location_id = options.get("location_id") or None
        self._base_url = options.get("base_url", DEFAULT_XMLGW_URL)

        # Session cache -- obtained lazily via getAPISession and reused
        # across calls, per the doc's recommended auth flow. Refreshed
        # transparently on session-expiry.
        self._session_id: str | None = None
        self._session_endpoint: str | None = None
        self._control_seq = 0

        # Cap cursors at init time so a trigger never chases continuously
        # arriving GL/AR/AP activity. The next trigger run creates a fresh
        # connector instance with a newer cap.
        self._init_ts = datetime.now(timezone.utc).isoformat()

    # ------------------------------------------------------------------
    # LakeflowConnect interface
    # ------------------------------------------------------------------

    def list_tables(self) -> list[str]:
        return list(TABLE_TO_OBJECT.keys())

    def get_table_schema(self, table_name: str, table_options: dict[str, str]) -> StructType:
        # TODO: the doc recommends calling `lookup` per-object at connector
        # init to discover tenant-specific custom fields; this hard-codes
        # the documented core fields instead (see intacct_schemas.py). A
        # follow-up could merge `lookup`'s field list on top of this base
        # schema for full custom-field fidelity.
        self._validate_table(table_name)
        return TABLE_SCHEMAS[table_name]

    def read_table_metadata(self, table_name: str, table_options: dict[str, str]) -> dict:
        self._validate_table(table_name)
        # All 5 objects: WHENMODIFIED-based CDC, no delete-tombstone feed
        # documented (deactivation/void+reversal show up as WHENMODIFIED
        # bumps, not deletes) -- see "Object's ingestion type" in the doc.
        return {
            "primary_keys": [PRIMARY_KEY_FIELD],
            "cursor_field": CURSOR_FIELD,
            "ingestion_type": "cdc",
        }

    def read_table(
        self, table_name: str, start_offset: dict, table_options: dict[str, str]
    ) -> tuple[Iterator[dict], dict]:
        self._validate_table(table_name)
        return self._read_incremental_by_window(table_name, start_offset or {}, table_options)

    # ------------------------------------------------------------------
    # Incremental read (Strategy A -- sliding time-window)
    # ------------------------------------------------------------------

    def _read_incremental_by_window(
        self, table_name: str, start_offset: dict, table_options: dict[str, str]
    ) -> tuple[Iterator[dict], dict]:
        object_name = TABLE_TO_OBJECT[table_name]
        fields = TABLE_FIELDS[table_name]

        since = start_offset.get("cursor")
        if not since:
            since = table_options.get("start_timestamp")
        if not since:
            since = self._peek_oldest_cursor(object_name)
        if not since:
            # No records exist yet for this object -- nothing to read.
            return iter([]), start_offset or {}

        # Already caught up to init time -- skip the API call entirely.
        if since >= self._init_ts:
            return iter([]), start_offset if start_offset else {}

        window_seconds = int(table_options.get("window_seconds", "86400"))
        max_records = int(table_options.get("max_records_per_batch", str(MAX_PAGESIZE)))
        pagesize = min(
            int(table_options.get("pagesize", str(DEFAULT_PAGESIZE))), MAX_PAGESIZE
        )

        window_end_dt = datetime.fromisoformat(since) + timedelta(seconds=window_seconds)
        window_end = min(window_end_dt.isoformat(), self._init_ts)

        records: list[dict] = []
        offset = 0
        window_drained = False
        while len(records) < max_records:
            parsed = self._query(object_name, fields, since, window_end, pagesize, offset)
            batch = parsed.get("records") or []
            if not batch:
                window_drained = True
                break

            records.extend(_normalize_record(table_name, r) for r in batch)
            offset += len(batch)

            if parsed.get("numremaining", 0) <= 0:
                window_drained = True
                break

        # When the window is fully drained, advance the cursor to
        # window_end rather than the last record's cursor -- otherwise a
        # follow-up call would re-scan the (now empty) tail of the window
        # and return the same offset it started with, breaking
        # Trigger.AvailableNow convergence.
        if window_drained:
            end_offset = {"cursor": window_end}
        else:
            # max_records cap hit mid-window. Safe to resume from the last
            # processed record's cursor: this table is `cdc` (has a primary
            # key), so any re-fetched overlap on the next call is deduped
            # by upsert.
            end_offset = {"cursor": records[-1][CURSOR_FIELD]}

        if start_offset and start_offset == end_offset:
            return iter([]), start_offset

        return iter(records), end_offset

    def _peek_oldest_cursor(self, object_name: str) -> str | None:
        """Auto-discover the oldest record's cursor to bound the first call.

        Requests a single record ordered ascending by WHENMODIFIED with no
        filter -- the first (and only) record returned is the oldest.
        """
        function_xml = query_function_xml(
            object_name=object_name,
            fields=[CURSOR_FIELD],
            filter_xml="",
            pagesize=1,
            offset=0,
        )
        parsed = self._call_function(function_xml, "peek")
        records = parsed.get("records") or []
        if not records:
            return None
        raw = records[0].get(CURSOR_FIELD)
        return from_intacct_timestamp(raw) if raw else None

    def _query(
        self,
        object_name: str,
        fields: list[str],
        since_iso: str,
        until_iso: str,
        pagesize: int,
        offset: int,
    ) -> dict:
        filter_xml = range_filter_xml(
            CURSOR_FIELD,
            to_intacct_timestamp(since_iso) if since_iso else None,
            to_intacct_timestamp(until_iso) if until_iso else None,
        )
        function_xml = query_function_xml(
            object_name=object_name,
            fields=fields,
            filter_xml=filter_xml,
            pagesize=pagesize,
            offset=offset,
        )
        return self._call_function(function_xml, "query")

    # ------------------------------------------------------------------
    # XML Gateway plumbing -- session management, request/retry
    # ------------------------------------------------------------------

    def _validate_table(self, table_name: str) -> None:
        if table_name not in TABLE_TO_OBJECT:
            raise ValueError(
                f"Table '{table_name}' is not supported. "
                f"Supported tables: {list(TABLE_TO_OBJECT)}"
            )

    def _next_control_id(self, prefix: str) -> str:
        self._control_seq += 1
        return f"{prefix}_{self._control_seq}"

    def _ensure_session(self) -> None:
        if self._session_id:
            return
        control_id = self._next_control_id("get_session")
        envelope = build_login_envelope(
            sender_id=self._sender_id,
            sender_password=self._sender_password,
            control_id=control_id,
            user_id=self._user_id,
            company_id=self._company_id,
            user_password=self._user_password,
            location_id=self._location_id,
            function_xml=get_api_session_function_xml(),
        )
        parsed = self._post(self._base_url, envelope, expect_session=True)
        if not parsed.get("session_id"):
            raise RuntimeError(
                f"Failed to obtain Intacct API session: {parsed.get('error_message')}"
            )
        self._session_id = parsed["session_id"]
        self._session_endpoint = parsed.get("session_endpoint") or self._base_url

    def _call_function(self, function_xml: str, control_prefix: str) -> dict:
        self._ensure_session()
        control_id = self._next_control_id(control_prefix)
        envelope = build_session_envelope(
            sender_id=self._sender_id,
            sender_password=self._sender_password,
            control_id=control_id,
            session_id=self._session_id,
            function_xml=function_xml,
        )
        try:
            return self._post(self._session_endpoint or self._base_url, envelope)
        except IntacctSessionExpiredError:
            # Session died between calls (expiry / server-side eviction).
            # Refresh once and retry the same function.
            self._session_id = None
            self._ensure_session()
            control_id = self._next_control_id(control_prefix)
            envelope = build_session_envelope(
                sender_id=self._sender_id,
                sender_password=self._sender_password,
                control_id=control_id,
                session_id=self._session_id,
                function_xml=function_xml,
            )
            return self._post(self._session_endpoint or self._base_url, envelope)

    def _post(self, url: str, envelope: str, expect_session: bool = False) -> dict:
        """POST one XML envelope, retrying on transport and transient API errors.

        Retries (with exponential backoff) on:
          - Retriable HTTP status codes (429/5xx).
          - XML Gateway failures whose error text matches a transient-error
            heuristic (the doc documents queueing/backoff *behavior* for
            the 1-concurrent-job limit, but not a specific error code, so
            this is a conservative keyword match rather than an exact code).
        Raises ``IntacctSessionExpiredError`` (not retried here -- handled
        by the caller, which refreshes the session) when a session-based
        call's authentication block reports failure.
        """
        backoff = INITIAL_BACKOFF
        for attempt in range(MAX_RETRIES):
            resp = requests.post(
                url,
                data=envelope.encode("utf-8"),
                headers={"Content-Type": "application/xml"},
                timeout=30,
            )

            if resp.status_code in RETRIABLE_HTTP_STATUS_CODES:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                resp.raise_for_status()

            if resp.status_code != 200:
                raise RuntimeError(f"Intacct API HTTP {resp.status_code}: {resp.text[:500]}")

            parsed = parse_response(resp.text)
            if parsed["status"] == "success":
                return parsed

            if not expect_session and parsed.get("auth_status") == "failure":
                raise IntacctSessionExpiredError(
                    parsed.get("error_message") or "Intacct session expired"
                )

            message = (parsed.get("error_message") or "").lower()
            if attempt < MAX_RETRIES - 1 and any(k in message for k in RETRIABLE_ERROR_KEYWORDS):
                time.sleep(backoff)
                backoff *= 2
                continue

            raise IntacctApiError(parsed.get("error_message") or "Intacct API request failed")

        raise RuntimeError("Intacct API request failed after exhausting retries")


def _normalize_record(table_name: str, raw: dict) -> dict:
    """Convert Intacct's wire formats to framework-castable values.

    Intacct dates/timestamps are ``mm/dd/yyyy`` / ``mm/dd/yyyy hh:mm:ss``,
    which Spark's default string->Date/Timestamp cast does not parse.
    Values are rewritten to ISO-8601 here; other fields (numeric/string)
    are passed through as raw text and left for the framework's schema-
    driven type coercion (per the "do not pre-convert JSON" rule). Fields
    absent from the response (Intacct omits some empty fields) are
    explicitly set to ``None`` rather than left as an empty dict.
    """
    schema = TABLE_SCHEMAS[table_name]
    normalized: dict = {}
    for f in schema.fields:
        value = raw.get(f.name)
        if value is not None:
            if isinstance(f.dataType, TimestampType):
                value = from_intacct_timestamp(value)
            elif isinstance(f.dataType, DateType):
                value = from_intacct_timestamp(value)[:10]
            elif isinstance(f.dataType, BooleanType):
                value = str(value).strip().lower() in ("true", "t", "1", "yes")
        normalized[f.name] = value
    return normalized
