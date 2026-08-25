"""Utility functions for the NetSuite connector.

Token-Based Authentication (TBA) request signing (OAuth 1.0a-style,
HMAC-SHA256) and a small SuiteQL REST helper with retry. See
``netsuite_api_doc.md`` for the full auth + endpoint reference.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

import requests

RETRIABLE_STATUS_CODES = {429, 500, 502, 503}
MAX_RETRIES = 5
INITIAL_BACKOFF = 1.0  # seconds; doubled after each retry
REQUEST_TIMEOUT_SECONDS = 20

# SuiteQL hard cap: offset cannot exceed 100,000 total matching rows.
SUITEQL_MAX_OFFSET = 100_000
DEFAULT_PAGE_SIZE = 1000


def _percent_encode(value: str) -> str:
    """RFC 3986 percent-encoding, matching OAuth 1.0a's encoding rules."""
    return quote(str(value), safe="~")


def build_tba_authorization_header(
    *,
    method: str,
    url: str,
    account_id: str,
    consumer_key: str,
    consumer_secret: str,
    token_id: str,
    token_secret: str,
) -> str:
    """Build the ``Authorization: OAuth ...`` header for one TBA request.

    Implements the OAuth 1.0a-style HMAC-SHA256 signing scheme NetSuite
    requires for Token-Based Authentication (RFC 5849). Per RFC 5849
    ss3.4.1.3.2, the signature's normalized parameter string is built from
    *all* protocol (``oauth_*``) parameters **and** every query-string
    parameter on the request URL (``limit``/``offset`` for SuiteQL calls)
    -- not just the oauth_* set. The request body is JSON here, not
    ``application/x-www-form-urlencoded``, so per the same RFC section
    body parameters are correctly excluded; only the query string and the
    oauth_* params are signed. The base string URI (the second signature
    component) still excludes the query string -- only the normalized
    parameter string carries it.
    """
    parsed = urlsplit(url)
    base_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    query_params = parse_qsl(parsed.query, keep_blank_values=True)

    oauth_params = {
        "oauth_consumer_key": consumer_key,
        "oauth_token": token_id,
        "oauth_signature_method": "HMAC-SHA256",
        "oauth_timestamp": str(int(time.time())),
        "oauth_nonce": secrets.token_hex(16),
        "oauth_version": "1.0",
    }

    # RFC 5849 ss3.4.1.3.2: combine oauth_* params with every query-string
    # param, then sort by (encoded key, encoded value) -- not just by key --
    # so parameters that repeat with the same name sort deterministically.
    all_params = list(oauth_params.items()) + query_params
    encoded_params = sorted(
        (_percent_encode(k), _percent_encode(v)) for k, v in all_params
    )
    sorted_params = "&".join(f"{k}={v}" for k, v in encoded_params)
    base_string = "&".join(
        [
            method.upper(),
            _percent_encode(base_url),
            _percent_encode(sorted_params),
        ]
    )
    signing_key = f"{_percent_encode(consumer_secret)}&{_percent_encode(token_secret)}"
    signature = base64.b64encode(
        hmac.new(
            signing_key.encode("utf-8"),
            base_string.encode("utf-8"),
            hashlib.sha256,
        ).digest()
    ).decode("utf-8")

    header_params = {**oauth_params, "oauth_signature": signature}
    header_str = ", ".join(
        f'{k}="{_percent_encode(v)}"' for k, v in header_params.items()
    )
    return f'OAuth realm="{account_id}", {header_str}'


def request_with_retry(
    session: requests.Session,
    method: str,
    url: str,
    **kwargs: Any,
) -> requests.Response:
    """Issue a request with exponential backoff on 429/500/502/503.

    Every call sets an explicit timeout so a slow/hanging NetSuite
    response can't stall the connector indefinitely.
    """
    kwargs.setdefault("timeout", REQUEST_TIMEOUT_SECONDS)
    backoff = INITIAL_BACKOFF
    resp = None
    for attempt in range(MAX_RETRIES):
        resp = session.request(method, url, **kwargs)
        if resp.status_code not in RETRIABLE_STATUS_CODES:
            return resp
        if attempt < MAX_RETRIES - 1:
            retry_after = resp.headers.get("Retry-After")
            try:
                wait = float(retry_after) if retry_after else backoff
            except (TypeError, ValueError):
                wait = backoff
            time.sleep(wait)
            backoff *= 2
    return resp


def run_suiteql(
    session: requests.Session,
    *,
    base_url: str,
    account_id: str,
    consumer_key: str,
    consumer_secret: str,
    token_id: str,
    token_secret: str,
    query: str,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    """POST one SuiteQL query and return the parsed JSON response.

    ``limit``/``offset`` are URL query-string parameters (NOT part of the
    JSON body) per NetSuite's SuiteQL REST contract.
    """
    url = f"{base_url}/services/rest/query/v1/suiteql?{urlencode({'limit': limit, 'offset': offset})}"
    auth_header = build_tba_authorization_header(
        method="POST",
        url=url,
        account_id=account_id,
        consumer_key=consumer_key,
        consumer_secret=consumer_secret,
        token_id=token_id,
        token_secret=token_secret,
    )
    resp = request_with_retry(
        session,
        "POST",
        url,
        headers={
            "Authorization": auth_header,
            "Content-Type": "application/json",
            "Prefer": "transient",
        },
        json={"q": query},
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"SuiteQL query failed with status {resp.status_code}: {resp.text}"
        )
    return resp.json()
