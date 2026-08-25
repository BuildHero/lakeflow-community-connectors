"""NetSuite connector for the LakeflowConnect interface.

Scope for this phase: the ``vendorbill`` table only (header rows from
NetSuite's built-in ``transaction`` SuiteQL table, filtered to
``type = 'VendBill'``). See ``netsuite_api_doc.md`` for the full API
reference, the deferred ``transactionline`` decision, and known quirks.

Auth: Token-Based Authentication (TBA) -- see ``netsuite_utils.py``.
Read path: SuiteQL (``POST /services/rest/query/v1/suiteql``) with a
sliding time-window (Strategy A) keyed on ``lastmodifieddate``, because
SuiteQL caps any single query at 100,000 total matching rows (the
``offset`` parameter cannot exceed that ceiling).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterator

import requests
from pyspark.sql.types import StructType

from databricks.labs.community_connector.interface import LakeflowConnect
from databricks.labs.community_connector.sources.netsuite.netsuite_schemas import (
    DATE_COLUMNS,
    SUPPORTED_TABLES,
    TABLE_METADATA,
    TABLE_SCHEMAS,
    VENDOR_BILL_COLUMNS,
)
from databricks.labs.community_connector.sources.netsuite.netsuite_utils import (
    DEFAULT_PAGE_SIZE,
    SUITEQL_MAX_OFFSET,
    run_suiteql,
)

_LASTMODIFIEDDATE_FORMAT = DATE_COLUMNS["lastmodifieddate"]
_ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"

# NetSuite rejects a SELECT column outright (HTTP 400, INVALID_PARAMETER)
# rather than returning it as null when the column doesn't exist on the
# account's schema at all -- e.g. ``subsidiary`` on accounts that don't have
# OneWorld/multi-subsidiary enabled. See netsuite_api_doc.md "Known Quirks"
# for the live-verified example. Deliberately narrow: only matches SuiteQL's
# specific "Unknown identifier '<col>'" wording for a column we ourselves
# requested, so unrelated 400s (bad syntax, permissions, etc.) still raise.
_UNKNOWN_IDENTIFIER_RE = re.compile(r"Unknown identifier '(\w+)'")


def _unsupported_column_from_error(message: str) -> str | None:
    """Return the offending column name if ``message`` is SuiteQL's specific
    "unknown identifier" 400 for one of ``VENDOR_BILL_COLUMNS``, else ``None``.
    """
    if "status 400" not in message or "INVALID_PARAMETER" not in message:
        return None
    match = _UNKNOWN_IDENTIFIER_RE.search(message)
    if not match:
        return None
    column = match.group(1)
    return column if column in VENDOR_BILL_COLUMNS else None


def _select_clause(exclude: frozenset[str] = frozenset()) -> str:
    parts = []
    for col in VENDOR_BILL_COLUMNS:
        if col in exclude:
            continue
        if col in DATE_COLUMNS:
            parts.append(f"TO_CHAR({col}, '{DATE_COLUMNS[col]}') AS {col}")
        else:
            parts.append(col)
    return ", ".join(parts)


class NetsuiteLakeflowConnect(LakeflowConnect):
    """LakeflowConnect implementation for NetSuite's ``vendorbill`` object."""

    def __init__(self, options: dict[str, str]) -> None:
        super().__init__(options)
        account_id = options.get("account_id")
        consumer_key = options.get("consumer_key")
        consumer_secret = options.get("consumer_secret")
        token_id = options.get("token_id")
        token_secret = options.get("token_secret")

        missing = [
            name
            for name, value in (
                ("account_id", account_id),
                ("consumer_key", consumer_key),
                ("consumer_secret", consumer_secret),
                ("token_id", token_id),
                ("token_secret", token_secret),
            )
            if not value
        ]
        if missing:
            raise ValueError(
                f"NetSuite connector requires the following option(s): {missing}"
            )

        self._account_id = account_id
        self._consumer_key = consumer_key
        self._consumer_secret = consumer_secret
        self._token_id = token_id
        self._token_secret = token_secret

        # NetSuite account IDs use "_" in the account record but "-" (and
        # lowercase) in the REST hostname, e.g. "1234567_SB1" ->
        # "1234567-sb1.suitetalk.api.netsuite.com".
        host_account = account_id.lower().replace("_", "-")
        self.base_url = f"https://{host_account}.suitetalk.api.netsuite.com"

        self._session = requests.Session()

        # Cap incremental cursors at init time so a single AvailableNow
        # trigger only drains data that existed when the connector started;
        # later edits are picked up by the next trigger with a fresh cap.
        self._init_ts = datetime.now(timezone.utc).strftime(_ISO_FMT)

        # Columns SuiteQL has told us, this run, are not valid identifiers on
        # this account (e.g. ``subsidiary`` on non-OneWorld accounts -- see
        # ``_unsupported_column_from_error`` / netsuite_api_doc.md). Populated
        # lazily on first failure and cached for the life of this instance so
        # later windows/pages build the query without the column from the
        # start instead of re-attempting and re-failing every call.
        self._unsupported_columns: frozenset[str] = frozenset()

    # ------------------------------------------------------------------ #
    # Interface methods
    # ------------------------------------------------------------------ #

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

    def read_table(
        self, table_name: str, start_offset: dict, table_options: dict[str, str]
    ) -> tuple[Iterator[dict], dict]:
        self._validate_table(table_name)
        return self._read_vendorbill_window(start_offset, table_options)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _validate_table(self, table_name: str) -> None:
        if table_name not in SUPPORTED_TABLES:
            raise ValueError(
                f"Table '{table_name}' is not supported. Supported tables: {SUPPORTED_TABLES}"
            )

    def _run_query(self, query: str, limit: int, offset: int) -> dict[str, Any]:
        return run_suiteql(
            self._session,
            base_url=self.base_url,
            account_id=self._account_id,
            consumer_key=self._consumer_key,
            consumer_secret=self._consumer_secret,
            token_id=self._token_id,
            token_secret=self._token_secret,
            query=query,
            limit=limit,
            offset=offset,
        )

    def _run_query_with_fallback(
        self,
        query_builder: Callable[[frozenset[str]], str],
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        """Run a SuiteQL query built by ``query_builder(exclude_columns)``.

        Builds first with whatever columns are already cached as
        unsupported on this instance (``self._unsupported_columns``, set by
        an earlier failure this run). If NetSuite still rejects a *new*
        column as an unknown identifier -- e.g. ``subsidiary`` on accounts
        without OneWorld/multi-subsidiary enabled, see
        ``_unsupported_column_from_error`` and netsuite_api_doc.md's "Known
        Quirks" -- cache it and retry once with it excluded too, so later
        windows/pages build the query without that column from the start
        rather than re-attempting and re-failing on every call. Any other
        error (bad syntax, permissions, rate limiting, ...) is raised
        unchanged.
        """
        query = query_builder(self._unsupported_columns)
        try:
            return self._run_query(query, limit=limit, offset=offset)
        except RuntimeError as exc:
            column = _unsupported_column_from_error(str(exc))
            if column is None or column in self._unsupported_columns:
                raise
            self._unsupported_columns = self._unsupported_columns | {column}
            query = query_builder(self._unsupported_columns)
            return self._run_query(query, limit=limit, offset=offset)

    def _peek_oldest_cursor(self) -> str | None:
        """Auto-discover the oldest ``lastmodifieddate`` among vendor bills.

        Used only when neither a checkpointed offset nor a user-supplied
        ``start_timestamp`` table option is available, so the first
        SuiteQL query always has a bounded lower cursor (see
        implement-connector's "Strategy A" auto-discovery guidance).
        """

        def build(exclude: frozenset[str]) -> str:
            return (
                f"SELECT {_select_clause(exclude)} FROM transaction "
                "WHERE type = 'VendBill' ORDER BY lastmodifieddate ASC"
            )

        body = self._run_query_with_fallback(build, limit=1, offset=0)
        items = body.get("items") or []
        if items:
            return items[0].get("lastmodifieddate")
        return None

    def _read_vendorbill_window(
        self, start_offset: dict | None, table_options: dict[str, str]
    ) -> tuple[Iterator[dict], dict]:
        since = (start_offset or {}).get("cursor")
        if not since:
            since = table_options.get("start_timestamp")
        if not since:
            since = self._peek_oldest_cursor()
        if not since:
            # No vendor bills at all -- nothing to read yet.
            return iter([]), start_offset or {}

        if since >= self._init_ts:
            return iter([]), start_offset or {}

        window_seconds = int(table_options.get("window_seconds", "86400"))
        max_records = int(table_options.get("max_records_per_batch", "200"))
        page_size = int(table_options.get("limit", str(DEFAULT_PAGE_SIZE)))

        since_dt = datetime.strptime(since, _ISO_FMT).replace(tzinfo=timezone.utc)
        window_end_dt = since_dt + timedelta(seconds=window_seconds)
        init_dt = datetime.strptime(self._init_ts, _ISO_FMT).replace(tzinfo=timezone.utc)
        window_end_dt = min(window_end_dt, init_dt)
        window_end = window_end_dt.strftime(_ISO_FMT)

        def build_window_query(exclude: frozenset[str]) -> str:
            return (
                f"SELECT {_select_clause(exclude)} FROM transaction "
                "WHERE type = 'VendBill' "
                f"AND lastmodifieddate >= TO_DATE('{since}', '{_LASTMODIFIEDDATE_FORMAT}') "
                f"AND lastmodifieddate <  TO_DATE('{window_end}', '{_LASTMODIFIEDDATE_FORMAT}') "
                "ORDER BY lastmodifieddate ASC"
            )

        def paginate(cap: int | None) -> tuple[list[dict[str, Any]], bool]:
            paged: list[dict[str, Any]] = []
            offset = 0
            while cap is None or len(paged) < cap:
                if offset >= SUITEQL_MAX_OFFSET:
                    # Row count within this window exceeds SuiteQL's per-query
                    # ceiling -- narrow window_seconds. See netsuite_api_doc.md
                    # "100,000-row per-query ceiling" known quirk.
                    raise RuntimeError(
                        "SuiteQL offset exceeded the 100,000-row ceiling within "
                        "one window; reduce the 'window_seconds' table option."
                    )
                body = self._run_query_with_fallback(
                    build_window_query, limit=page_size, offset=offset
                )
                batch = body.get("items") or []
                if not batch:
                    return paged, True

                paged.extend(batch)
                offset += len(batch)

                if not body.get("hasMore"):
                    return paged, True
            return paged, False

        records, window_drained = paginate(max_records)

        if not window_drained:
            # max_records cap hit mid-window. vendorbill is a `cdc` table
            # (upsert semantics), so client-side truncation to exactly
            # max_records is normally safe -- the next trigger re-fetches
            # from the truncation point and Databricks dedups via
            # primary-key merge.
            records = records[:max_records]
            resume_cursor = records[-1]["lastmodifieddate"] if records else since

            # Same-second cursor cluster larger than the cap: every capped
            # row shares one ``lastmodifieddate``, so the resume cursor
            # can't advance past ``since`` and the next call would re-fetch
            # this exact page forever, silently dropping every later row
            # (see mailchimp.py's identical guard for the sliding-window
            # pattern). Re-drain the window uncapped instead -- the cap
            # only trips because of low cardinality mid-window in this
            # case, and ``window_seconds`` already bounds total volume.
            if resume_cursor <= since:
                records, window_drained = paginate(None)

        if window_drained:
            end_offset = {"cursor": window_end}
        else:
            end_offset = {"cursor": records[-1]["lastmodifieddate"]}

        if start_offset and start_offset == end_offset:
            return iter([]), start_offset

        return iter(records), end_offset
