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

from unittest.mock import MagicMock

import pytest

from databricks.labs.community_connector.sources.netsuite.netsuite import (
    NetsuiteLakeflowConnect,
    _unsupported_column_from_error,
)
from databricks.labs.community_connector.sources.netsuite.netsuite_schemas import (
    VENDOR_BILL_COLUMNS,
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


def _query_text(call) -> str:
    """Pull the SuiteQL query text out of a mocked ``session.request`` call."""
    return call.kwargs["json"]["q"]


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
        # 1) _peek_oldest_cursor, attempt 1 (includes subsidiary) -> 400
        _response(status_code=400, text=_SUBSIDIARY_400_TEXT),
        # 2) _peek_oldest_cursor, retry (excludes subsidiary) -> succeeds,
        #    just establishing a 'since' cursor.
        _items_response(
            [{"id": "0", "lastmodifieddate": "2026-01-01T00:00:00Z"}]
        ),
        # 3) window fetch, first page -- already excludes subsidiary from
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
    assert len(calls) == 3
    assert "subsidiary" in _query_text(calls[0])  # first attempt requested it
    assert "subsidiary" not in _query_text(calls[1])  # retry excluded it
    assert "subsidiary" not in _query_text(calls[2])  # window fetch, cached already

    assert conn._unsupported_columns == frozenset({"subsidiary"})


def test_cached_unsupported_column_is_not_retried_on_a_later_call(conn):
    """Once cached (e.g. by an earlier call on this same instance), a
    later, separate ``read_table`` call must build its query without
    'subsidiary' from the start -- no failure, no retry, exactly one
    request."""
    conn._unsupported_columns = frozenset({"subsidiary"})

    conn._session.request.side_effect = [
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
    assert len(calls) == 1  # no failed attempt, no retry needed
    assert "subsidiary" not in _query_text(calls[0])

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
