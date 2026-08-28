"""Mock-based unit tests for NetsuiteLakeflowConnect.

These tests stub ``requests.Session`` responses to cover the
``subsidiary``-is-not-a-valid-identifier fallback/caching logic added
after Task 5's live sandbox validation (see ``netsuite_api_doc.md`` Known
Quirks #7) — complementing the simulate-mode suite in
``test_netsuite_lakeflow_connect.py``. They run without credentials or the
source simulator and are therefore safe for CI.

Each test targets a specific property of the fallback:
1. the exact live-observed error is caught and triggers a retry without
   ``subsidiary``;
2. the decision is cached on the connector instance, so a later, separate
   call doesn't re-attempt (and re-fail on) ``subsidiary``;
3. anything that isn't this exact "unknown identifier for a column we
   requested" 400 is left alone and propagates as-is.
"""

import base64
import hashlib
import hmac
import re
from urllib.parse import parse_qs, quote, urlsplit
from unittest.mock import MagicMock

import pytest

from databricks.labs.community_connector.sources.netsuite import netsuite_utils
from databricks.labs.community_connector.sources.netsuite.netsuite import (
    NetsuiteLakeflowConnect,
    _unsupported_column_from_error,
)
from databricks.labs.community_connector.sources.netsuite.netsuite_schemas import (
    VENDOR_BILL_COLUMNS,
)
from databricks.labs.community_connector.sources.netsuite.netsuite_utils import (
    build_tba_authorization_header,
)

# Exact wording NetSuite returned live against a non-OneWorld sandbox
# account (see task-5-report.md / netsuite_api_doc.md Known Quirks #7).
_SUBSIDIARY_400_TEXT = (
    '{"type":"https://www.rfc-editor.org/rfc/rfc9110.html#section-15.5.1",'
    '"title":"Bad Request","status":400,"o:errorDetails":[{"detail":'
    '"Invalid search query. Detailed unprocessed description follows. '
    "Search error occurred: Unknown identifier 'subsidiary'. Available "
    'identifiers are: {transaction=transaction}.","o:errorQueryParam":"q",'
    '"o:errorCode":"INVALID_PARAMETER"}]}'
)


def _response(status_code: int = 200, json_body=None, text: str | None = None):
    """Build a mock ``requests.Response``-like object."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = {}
    resp.text = text if text is not None else (str(json_body) if json_body is not None else "")
    if json_body is not None:
        resp.json.return_value = json_body
    return resp


def _items_response(items: list, has_more: bool = False):
    return _response(
        status_code=200,
        json_body={"items": items, "hasMore": has_more, "count": len(items)},
    )


def _now_response(now_ts: str = "2030-01-01T00:00:00Z"):
    """Mocked response for the connector's ``_fetch_account_now`` (``FROM
    DUAL``) probe -- issued once, lazily, on a connector instance's first
    ``read_table`` call (see ``_ensure_init_ts`` in netsuite.py)."""
    return _items_response([{"now_ts": now_ts}])


def _query_text(call) -> str:
    """Pull the SuiteQL query text out of a mocked ``session.request`` call."""
    return call.kwargs["json"]["q"]


def _paginated_window_response(rows: list[dict]):
    """Fake ``session.request`` that pages ``rows`` by the request URL's
    ``limit``/``offset`` query params (as ``run_suiteql`` encodes them)."""

    def fake(method, url, **kwargs):
        query = parse_qs(urlsplit(url).query)
        limit = int(query.get("limit", ["1000"])[0])
        offset = int(query.get("offset", ["0"])[0])
        page = rows[offset : offset + limit]
        has_more = offset + limit < len(rows)
        return _items_response(page, has_more=has_more)

    return fake


@pytest.fixture
def conn():
    """NetsuiteLakeflowConnect with a stubbed ``requests.Session``."""
    c = NetsuiteLakeflowConnect(
        {
            "account_id": "1234567_SB1",
            "consumer_key": "fake-consumer-key",
            "consumer_secret": "fake-consumer-secret",
            "token_id": "fake-token-id",
            "token_secret": "fake-token-secret",
        }
    )
    c._session = MagicMock()
    return c


# ---------------------------------------------------------------------------
# _unsupported_column_from_error — pure-logic matching
# ---------------------------------------------------------------------------


def test_unsupported_column_from_error_matches_live_subsidiary_case():
    """The exact live-observed 400 must resolve to 'subsidiary'."""
    message = f"SuiteQL query failed with status 400: {_SUBSIDIARY_400_TEXT}"
    assert _unsupported_column_from_error(message) == "subsidiary"


def test_unsupported_column_from_error_ignores_unrelated_400():
    """A 400/INVALID_PARAMETER naming a column we never requested must not
    match -- only columns in VENDOR_BILL_COLUMNS are eligible."""
    assert "not_a_real_column" not in VENDOR_BILL_COLUMNS
    body = (
        '{"status":400,"o:errorDetails":[{"detail":"Unknown identifier '
        "'not_a_real_column'. Available identifiers are: "
        '{transaction=transaction}.","o:errorCode":"INVALID_PARAMETER"}]}'
    )
    message = f"SuiteQL query failed with status 400: {body}"
    assert _unsupported_column_from_error(message) is None


def test_unsupported_column_from_error_ignores_non_400():
    """A different status code (e.g. 403 permissions) must not match, even
    if the text coincidentally mentions a column name."""
    body = (
        '{"status":403,"o:errorDetails":[{"detail":"Insufficient permission '
        'for subsidiary.","o:errorCode":"INSUFFICIENT_PERMISSION"}]}'
    )
    message = f"SuiteQL query failed with status 403: {body}"
    assert _unsupported_column_from_error(message) is None


def test_unsupported_column_from_error_ignores_400_without_unknown_identifier():
    """A 400/INVALID_PARAMETER that isn't an 'Unknown identifier' error
    (e.g. a genuine syntax error) must not match."""
    body = (
        '{"status":400,"o:errorDetails":[{"detail":"Invalid search query: '
        'unexpected token near WHERE.","o:errorCode":"INVALID_PARAMETER"}]}'
    )
    message = f"SuiteQL query failed with status 400: {body}"
    assert _unsupported_column_from_error(message) is None


# ---------------------------------------------------------------------------
# End-to-end fallback + caching behavior
# ---------------------------------------------------------------------------


def test_read_table_retries_without_subsidiary_and_caches(conn):
    """First live call rejects 'subsidiary'; the connector must retry the
    same (peek) query with it excluded, succeed, and cache the decision --
    then the window-fetch that follows must build its query already
    excluding 'subsidiary', with no further failure."""
    conn._session.request.side_effect = [
        # 1) _ensure_init_ts's lazy FROM DUAL probe (see netsuite.py) --
        #    happens once, before the peek/window logic below.
        _now_response(),
        # 2) _peek_oldest_cursor, attempt 1 (includes subsidiary) -> 400
        _response(status_code=400, text=_SUBSIDIARY_400_TEXT),
        # 3) _peek_oldest_cursor, retry (excludes subsidiary) -> succeeds,
        #    just establishing a 'since' cursor.
        _items_response(
            [{"id": "0", "lastmodifieddate": "2026-01-01T00:00:00Z"}]
        ),
        # 4) window fetch, first page -- already excludes subsidiary from
        #    the cache, no failure expected here.
        _items_response(
            [{"id": "1", "tranid": "VB-1", "lastmodifieddate": "2026-01-01T00:00:01Z"}],
            has_more=False,
        ),
    ]

    iterator, offset = conn.read_table("vendorbill", {}, {})
    records = list(iterator)

    assert len(records) == 1
    assert records[0]["id"] == "1"
    assert offset is not None

    calls = conn._session.request.call_args_list
    assert len(calls) == 4
    assert "subsidiary" in _query_text(calls[1])  # first attempt requested it
    assert "subsidiary" not in _query_text(calls[2])  # retry excluded it
    assert "subsidiary" not in _query_text(calls[3])  # window fetch, cached already

    assert conn._unsupported_columns == frozenset({"subsidiary"})


def test_cached_unsupported_column_is_not_retried_on_a_later_call(conn):
    """Once cached (e.g. by an earlier call on this same instance), a
    later, separate ``read_table`` call must build its query without
    'subsidiary' from the start -- no failure, no retry, exactly one
    request."""
    conn._unsupported_columns = frozenset({"subsidiary"})

    conn._session.request.side_effect = [
        # 1) _ensure_init_ts's lazy FROM DUAL probe -- still happens once
        #    per instance regardless of the unsupported-column cache.
        _now_response(),
        # 2) window fetch.
        _items_response(
            [{"id": "2", "tranid": "VB-2", "lastmodifieddate": "2026-01-02T00:00:00Z"}],
            has_more=False,
        ),
    ]

    # Non-empty start_offset -- this is what a real 2nd+ call looks like,
    # and it also skips _peek_oldest_cursor entirely (since is already
    # known), isolating this assertion to the window-fetch path.
    iterator, offset = conn.read_table(
        "vendorbill", {"cursor": "2026-01-01T00:00:00Z"}, {}
    )
    records = list(iterator)

    assert len(records) == 1
    assert offset is not None

    calls = conn._session.request.call_args_list
    assert len(calls) == 2  # now-probe + window fetch; no failed attempt, no retry
    assert "subsidiary" not in _query_text(calls[1])

    assert conn._unsupported_columns == frozenset({"subsidiary"})


def test_unrelated_400_is_not_swallowed(conn):
    """A 400 that isn't the specific 'unknown identifier for a column we
    requested' case must propagate as a RuntimeError, not be treated as
    the subsidiary fallback case."""
    unrelated_body = (
        '{"status":400,"o:errorDetails":[{"detail":"Invalid search query: '
        'unexpected token near WHERE.","o:errorCode":"INVALID_PARAMETER"}]}'
    )
    conn._session.request.return_value = _response(
        status_code=400, text=unrelated_body
    )

    with pytest.raises(RuntimeError, match="status 400"):
        conn.read_table("vendorbill", {}, {})

    # Exactly one attempt -- an unmatched error must not trigger a retry.
    assert conn._session.request.call_count == 1
    assert conn._unsupported_columns == frozenset()


# ---------------------------------------------------------------------------
# Timezone finding: self._init_ts is fetched live from SuiteQL, not Python's
# clock (final-review follow-up, 2026-08-27 -- see netsuite_api_doc.md Known
# Quirks #8). Live investigation found SuiteQL's TO_CHAR(...) output is
# rendered in the account's configured timezone despite the literal "Z"
# suffix, not true UTC -- so the AvailableNow cap must be fetched from the
# same clock domain as the cursor values it's compared against.
# ---------------------------------------------------------------------------


def test_init_ts_starts_unset_and_is_fetched_lazily(conn):
    """A fresh instance must not compute _init_ts from Python's clock at
    construction time -- it stays None until the first read_table call."""
    assert conn._init_ts is None


def test_init_ts_is_populated_from_a_suiteql_dual_probe(conn):
    """The first read_table call must fetch 'now' via a 'FROM DUAL' SuiteQL
    probe (not datetime.now()), and cache the result on the instance."""
    conn._session.request.side_effect = [
        _now_response("2031-06-15T12:00:00Z"),
        _items_response(
            [{"id": "0", "lastmodifieddate": "2026-01-01T00:00:00Z"}]
        ),
        _items_response(
            [{"id": "1", "tranid": "VB-1", "lastmodifieddate": "2026-01-01T00:00:01Z"}],
            has_more=False,
        ),
    ]

    conn.read_table("vendorbill", {}, {})

    assert conn._init_ts == "2031-06-15T12:00:00Z"
    calls = conn._session.request.call_args_list
    assert "FROM DUAL" in _query_text(calls[0])
    assert "CURRENT_DATE" in _query_text(calls[0])


def test_init_ts_probe_runs_once_per_instance_not_once_per_call(conn):
    """A second, separate read_table call on the same instance must reuse
    the cached _init_ts -- no repeat 'FROM DUAL' probe."""
    conn._session.request.side_effect = [
        _now_response("2031-06-15T12:00:00Z"),
        _items_response(
            [{"id": "0", "lastmodifieddate": "2026-01-01T00:00:00Z"}],
            has_more=False,
        ),
        _items_response(
            [{"id": "1", "tranid": "VB-1", "lastmodifieddate": "2026-01-02T00:00:00Z"}],
            has_more=False,
        ),
        _items_response(
            [{"id": "2", "tranid": "VB-2", "lastmodifieddate": "2026-01-03T00:00:00Z"}],
            has_more=False,
        ),
    ]

    conn.read_table("vendorbill", {}, {})
    assert conn._init_ts == "2031-06-15T12:00:00Z"

    conn.read_table("vendorbill", {"cursor": "2026-01-01T00:00:00Z"}, {})

    calls = conn._session.request.call_args_list
    dual_probes = [c for c in calls if "FROM DUAL" in _query_text(c)]
    assert len(dual_probes) == 1  # not re-fetched on the second call


# ---------------------------------------------------------------------------
# Mid-window truncation / same-second cursor cluster (final-review Critical)
# ---------------------------------------------------------------------------


def test_same_second_cluster_larger_than_cap_does_not_stall(conn):
    """5000 vendor bills sharing one ``lastmodifieddate``, cap=200 -> all rows
    ingest in one call and the cursor advances past the stalled timestamp.

    Reproduces the mid-window truncation bug: pre-fix, ``records[:max_records]``
    truncates to a page where every row shares the same ``lastmodifieddate``
    as ``since``, so ``end_offset == start_offset`` and the next call's
    "no more data" early-return stalls the cursor forever, silently dropping
    every row modified after that timestamp. The fix (ported from
    mailchimp.py's identical sliding-window guard) re-drains the window
    uncapped when the resume cursor can't advance past ``since``.
    """
    conn._init_ts = "2030-01-01T00:00:00Z"
    stalled_ts = "2026-01-01T00:00:00Z"
    rows = [
        {"id": str(i), "tranid": f"VB-{i}", "lastmodifieddate": stalled_ts}
        for i in range(5000)
    ]
    conn._session.request.side_effect = _paginated_window_response(rows)

    iterator, end_offset = conn.read_table(
        "vendorbill",
        {"cursor": stalled_ts},
        {"limit": "1000", "max_records_per_batch": "200", "window_seconds": "86400"},
    )
    records = list(iterator)

    assert len(records) == 5000  # nothing dropped despite the cap
    assert end_offset != {"cursor": stalled_ts}  # no stall
    assert end_offset["cursor"] > stalled_ts  # cursor advanced past the cluster


def test_capped_partial_window_below_cluster_still_resumes_mid_window(conn):
    """A cap trip whose resume cursor is *older* than the newest rows in the
    cluster (i.e. it genuinely advances past ``since``) must still truncate
    and resume mid-window as before -- the uncapped re-drain is only for the
    stalled case, not a general behavior change."""
    conn._init_ts = "2030-01-01T00:00:00Z"
    rows = [
        {"id": "0", "tranid": "VB-0", "lastmodifieddate": "2026-01-01T00:00:00Z"},
        {"id": "1", "tranid": "VB-1", "lastmodifieddate": "2026-01-01T00:00:01Z"},
        {"id": "2", "tranid": "VB-2", "lastmodifieddate": "2026-01-01T00:00:02Z"},
        {"id": "3", "tranid": "VB-3", "lastmodifieddate": "2026-01-01T00:00:03Z"},
    ]
    conn._session.request.side_effect = _paginated_window_response(rows)

    iterator, end_offset = conn.read_table(
        "vendorbill",
        {"cursor": "2026-01-01T00:00:00Z"},
        {"limit": "2", "max_records_per_batch": "2", "window_seconds": "86400"},
    )
    records = list(iterator)

    assert len(records) == 2  # capped, not re-drained uncapped
    assert end_offset == {"cursor": "2026-01-01T00:00:01Z"}
    # Only a single page fetched -- the uncapped re-drain path was not taken.
    assert conn._session.request.call_count == 1


# ---------------------------------------------------------------------------
# Multi-window advance path (final-review follow-up, 2026-08-27)
#
# Every prior test either bypasses windowing entirely (single-shot cluster
# fixtures whose ``window_seconds`` is wide enough to never need a second
# window) or -- in the only end-to-end config ever exercised
# (``configs/dev_table_config.json``) -- uses a single 10-year window that
# never advances past its own boundary. None of that exercises the
# "advance to the next window" branch a real deployment (hour/day-sized
# ``window_seconds``, per the README's own guidance) hits on every single
# ``read_table`` call. These tests drive a *sequence* of ``read_table``
# calls, each with the previous call's real returned offset as its
# ``start_offset`` (as the framework itself would), across a short,
# realistic ``window_seconds``.
# ---------------------------------------------------------------------------

_WINDOW_SINCE_RE = re.compile(r"lastmodifieddate\s*>=\s*TO_DATE\('([^']+)'")
_WINDOW_UNTIL_RE = re.compile(r"lastmodifieddate\s*<\s*TO_DATE\('([^']+)'")


def _windowed_session(rows: list[dict]):
    """Fake ``session.request`` that answers each call according to the
    ``[since, until)`` bounds embedded in *that specific call's* SuiteQL
    query text (mirroring the source-simulator's real ``suiteql`` handler
    logic), then paginates the matching subset by the URL's
    ``limit``/``offset``. Unlike ``_paginated_window_response`` (which pages
    one fixed row set with no window filtering), this lets one mocked
    session correctly answer a *sequence* of distinct windowed calls."""

    def fake(method, url, **kwargs):
        query = kwargs["json"]["q"]
        since_match = _WINDOW_SINCE_RE.search(query)
        until_match = _WINDOW_UNTIL_RE.search(query)
        since = since_match.group(1) if since_match else None
        until = until_match.group(1) if until_match else None

        def in_window(row: dict) -> bool:
            value = row["lastmodifieddate"]
            if since is not None and value < since:
                return False
            if until is not None and value >= until:
                return False
            return True

        filtered = sorted(
            (r for r in rows if in_window(r)), key=lambda r: r["lastmodifieddate"]
        )
        parsed = parse_qs(urlsplit(url).query)
        limit = int(parsed.get("limit", ["1000"])[0])
        offset = int(parsed.get("offset", ["0"])[0])
        page = filtered[offset : offset + limit]
        has_more = offset + len(page) < len(filtered)
        return _items_response(page, has_more=has_more)

    return fake


def test_multiple_windows_advance_in_sequence_including_an_empty_one(conn):
    """Three consecutive 1-hour windows -- data, then nothing, then data
    again -- driven exactly as the real framework would: each call's
    ``start_offset`` is the previous call's actual returned offset.

    Asserts the cursor advances window-by-window (not stuck re-fetching the
    same bound, not skipping a window), records from each non-empty window
    are correctly emitted, and the empty middle window still advances the
    cursor by a full ``window_seconds`` rather than stalling.
    """
    conn._init_ts = "2030-01-01T00:00:00Z"
    rows = [
        {"id": "1", "tranid": "VB-1", "lastmodifieddate": "2026-01-01T00:15:00Z"},
        # 01:00:00Z-02:00:00Z window is deliberately empty.
        {"id": "2", "tranid": "VB-2", "lastmodifieddate": "2026-01-01T02:10:00Z"},
        {"id": "3", "tranid": "VB-3", "lastmodifieddate": "2026-01-01T02:45:00Z"},
    ]
    conn._session.request.side_effect = _windowed_session(rows)
    table_options = {"window_seconds": "3600"}  # 1 hour -- realistic, not the 10yr PoC config

    # Window 1: 00:00:00Z-01:00:00Z -- one record.
    iterator1, offset1 = conn.read_table(
        "vendorbill", {"cursor": "2026-01-01T00:00:00Z"}, table_options
    )
    records1 = list(iterator1)
    assert [r["id"] for r in records1] == ["1"]
    assert offset1 == {"cursor": "2026-01-01T01:00:00Z"}

    # Window 2: 01:00:00Z-02:00:00Z -- empty. Must still advance a full
    # window_seconds, not stall on the same cursor.
    iterator2, offset2 = conn.read_table("vendorbill", offset1, table_options)
    records2 = list(iterator2)
    assert records2 == []
    assert offset2 == {"cursor": "2026-01-01T02:00:00Z"}
    assert offset2 != offset1  # advanced, not stuck

    # Window 3: 02:00:00Z-03:00:00Z -- two records.
    iterator3, offset3 = conn.read_table("vendorbill", offset2, table_options)
    records3 = list(iterator3)
    assert [r["id"] for r in records3] == ["2", "3"]
    assert offset3 == {"cursor": "2026-01-01T03:00:00Z"}
    assert offset3 != offset2  # advanced again

    # Cursor strictly increased across all three calls -- no skipped window
    # (which would jump further than one window_seconds) and no repeats.
    cursors = [offset1["cursor"], offset2["cursor"], offset3["cursor"]]
    assert cursors == sorted(cursors)
    assert len(set(cursors)) == 3


def test_many_consecutive_empty_windows_each_advance_the_cursor(conn):
    """Five empty windows in a row must each independently advance the
    cursor by one ``window_seconds`` -- no stall, no skip, no early
    short-circuit across multiple empty windows."""
    conn._init_ts = "2030-01-01T00:00:00Z"
    rows: list[dict] = []  # no data at all in the probed range
    conn._session.request.side_effect = _windowed_session(rows)
    table_options = {"window_seconds": "3600"}

    offset = {"cursor": "2026-01-01T00:00:00Z"}
    expected_cursors = [
        "2026-01-01T01:00:00Z",
        "2026-01-01T02:00:00Z",
        "2026-01-01T03:00:00Z",
        "2026-01-01T04:00:00Z",
        "2026-01-01T05:00:00Z",
    ]
    seen_cursors = []
    for _ in expected_cursors:
        iterator, offset = conn.read_table("vendorbill", offset, table_options)
        assert list(iterator) == []
        seen_cursors.append(offset["cursor"])

    assert seen_cursors == expected_cursors


# ---------------------------------------------------------------------------
# TBA (OAuth 1.0a) signing -- deterministic unit coverage
# ---------------------------------------------------------------------------

_FAKE_NONCE = "deadbeefdeadbeefdeadbeefdeadbeef"
_FAKE_TIMESTAMP = 1750000000


def _expected_tba_signature(
    *,
    method: str,
    base_url: str,
    query_params: list[tuple[str, str]],
    consumer_key: str,
    consumer_secret: str,
    token_id: str,
    token_secret: str,
    timestamp: int = _FAKE_TIMESTAMP,
    nonce: str = _FAKE_NONCE,
) -> str:
    """Independently recompute the expected OAuth1/HMAC-SHA256 signature
    straight from RFC 5849 primitives -- deliberately not by calling
    ``build_tba_authorization_header`` or its internal helpers -- so this
    catches the exact class of bug fixed in b41f2aa (query-string params
    omitted from the signature base string)."""
    oauth_params = {
        "oauth_consumer_key": consumer_key,
        "oauth_token": token_id,
        "oauth_signature_method": "HMAC-SHA256",
        "oauth_timestamp": str(timestamp),
        "oauth_nonce": nonce,
        "oauth_version": "1.0",
    }
    all_params = list(oauth_params.items()) + query_params
    encoded_params = sorted(
        (quote(k, safe="~"), quote(v, safe="~")) for k, v in all_params
    )
    normalized = "&".join(f"{k}={v}" for k, v in encoded_params)
    base_string = "&".join(
        [method.upper(), quote(base_url, safe="~"), quote(normalized, safe="~")]
    )
    signing_key = f"{quote(consumer_secret, safe='~')}&{quote(token_secret, safe='~')}".encode()
    return base64.b64encode(
        hmac.new(signing_key, base_string.encode("utf-8"), hashlib.sha256).digest()
    ).decode("utf-8")


@pytest.fixture
def _frozen_tba_nonce_and_clock(monkeypatch):
    """Freeze ``time.time`` and ``secrets.token_hex`` so the signature is
    deterministic and can be independently recomputed by the test."""
    monkeypatch.setattr(netsuite_utils.time, "time", lambda: _FAKE_TIMESTAMP)
    monkeypatch.setattr(netsuite_utils.secrets, "token_hex", lambda n: _FAKE_NONCE)


def test_build_tba_authorization_header_signs_query_params(
    _frozen_tba_nonce_and_clock,
):
    """limit/offset query params must be part of the signed base string, and
    the resulting signature must match an independently-computed value --
    regression coverage for the base-string bug fixed in b41f2aa (query
    params were previously omitted). Also covers the realm-uppercasing fix:
    the account ID is entered lowercase but the realm must be uppercase."""
    base_url = "https://1234567-sb1.suitetalk.api.netsuite.com/services/rest/query/v1/suiteql"
    url = f"{base_url}?limit=1000&offset=200"

    header = build_tba_authorization_header(
        method="POST",
        url=url,
        account_id="1234567_sb1",
        consumer_key="fake-consumer-key",
        consumer_secret="fake-consumer-secret",
        token_id="fake-token-id",
        token_secret="fake-token-secret",
    )

    expected_sig = _expected_tba_signature(
        method="POST",
        base_url=base_url,
        query_params=[("limit", "1000"), ("offset", "200")],
        consumer_key="fake-consumer-key",
        consumer_secret="fake-consumer-secret",
        token_id="fake-token-id",
        token_secret="fake-token-secret",
    )

    assert f'oauth_signature="{quote(expected_sig, safe="~")}"' in header
    # Realm is the account ID, uppercased -- independent of the (lowercase)
    # hostname derived from the same account_id.
    assert header.startswith('OAuth realm="1234567_SB1"')


def test_build_tba_authorization_header_signature_changes_with_query_params(
    _frozen_tba_nonce_and_clock,
):
    """Changing limit/offset must change the signature -- proves they are
    actually part of what's signed, not merely present on the URL."""
    base_url = "https://1234567-sb1.suitetalk.api.netsuite.com/services/rest/query/v1/suiteql"
    kwargs = dict(
        method="POST",
        account_id="1234567_sb1",
        consumer_key="fake-consumer-key",
        consumer_secret="fake-consumer-secret",
        token_id="fake-token-id",
        token_secret="fake-token-secret",
    )

    header_a = build_tba_authorization_header(url=f"{base_url}?limit=1000&offset=200", **kwargs)
    header_b = build_tba_authorization_header(url=f"{base_url}?limit=1&offset=0", **kwargs)

    assert header_a != header_b
