"""HTTP client for the BuildOps public API.

Handles the client-credentials token exchange (``POST /v1/auth/token``),
token caching / refresh, the per-request ``Authorization`` + ``tenantId``
headers, and retry with exponential backoff on 429 / 5xx / transport errors.
"""

import random
import time
from typing import Any, Optional

import requests

from databricks.labs.community_connector.sources.buildops.buildops_schemas import (
    DEFAULT_TOKEN_TTL_SECONDS,
    INITIAL_BACKOFF_SECONDS,
    MAX_BACKOFF_SECONDS,
    MAX_RETRIES,
    REQUEST_TIMEOUT_SECONDS,
    RETRIABLE_STATUS_CODES,
    TOKEN_PATH,
    TOKEN_REFRESH_MARGIN_SECONDS,
)


class BuildOpsAPIError(RuntimeError):
    """Raised when the BuildOps API returns a non-retriable error response."""

    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _body_excerpt(resp: requests.Response, limit: int = 500) -> str:
    try:
        return resp.text[:limit]
    except Exception:  # pylint: disable=broad-except
        return "<unreadable response body>"


class BuildOpsClient:
    """Thin authenticated wrapper around ``requests`` for the BuildOps API."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        tenant_id: str,
        base_url: str,
        timeout: float = REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.tenant_id = tenant_id
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session: Optional[requests.Session] = None
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0

    # The session is recreated lazily so the client (and the connector that
    # owns it) stays cheaply picklable when Spark ships it to executors.
    def __getstate__(self) -> dict:
        state = self.__dict__.copy()
        state["_session"] = None
        return state

    @property
    def session(self) -> requests.Session:
        if self._session is None:
            self._session = requests.Session()
        return self._session

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _token_is_fresh(self) -> bool:
        return bool(self._access_token) and time.time() < self._token_expires_at

    def invalidate_token(self) -> None:
        self._access_token = None
        self._token_expires_at = 0.0

    def get_access_token(self) -> str:
        """Return a cached bearer token, exchanging credentials if needed."""
        if self._token_is_fresh():
            return self._access_token  # type: ignore[return-value]

        url = f"{self.base_url}{TOKEN_PATH}"
        payload = {"clientId": self.client_id, "clientSecret": self.client_secret}
        resp = self._send_with_retry(
            "POST",
            url,
            json=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        if resp.status_code != 200:
            raise BuildOpsAPIError(
                f"BuildOps token exchange failed (HTTP {resp.status_code}) at "
                f"{url}. Verify the client_id / client_secret connection options "
                f"and base_url. Response: {_body_excerpt(resp)}",
                status_code=resp.status_code,
            )
        try:
            body = resp.json()
            token = body["access_token"]
        except (ValueError, KeyError, TypeError) as e:
            raise BuildOpsAPIError(
                f"BuildOps token response did not contain 'access_token': "
                f"{_body_excerpt(resp)}"
            ) from e

        try:
            ttl = float(body.get("expires_in") or DEFAULT_TOKEN_TTL_SECONDS)
        except (TypeError, ValueError):
            ttl = float(DEFAULT_TOKEN_TTL_SECONDS)
        margin = min(TOKEN_REFRESH_MARGIN_SECONDS, ttl / 2)
        self._access_token = token
        self._token_expires_at = time.time() + ttl - margin
        return token

    # ------------------------------------------------------------------
    # Requests
    # ------------------------------------------------------------------

    def request(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        json: Any = None,
    ) -> requests.Response:
        """Issue an authenticated request and return the final response.

        Retries 429 / 5xx with backoff. On a 401 the cached token is dropped,
        a new one is exchanged, and the request is retried exactly once.
        Callers inspect ``status_code`` for everything else.
        """
        url = f"{self.base_url}{path}"
        resp = self._send_authenticated(method, url, params=params, json=json)
        if resp.status_code == 401:
            self.invalidate_token()
            resp = self._send_authenticated(method, url, params=params, json=json)
            if resp.status_code == 401:
                raise BuildOpsAPIError(
                    f"BuildOps rejected the access token (HTTP 401) for "
                    f"{method} {path} even after re-authenticating. Verify the "
                    f"client credentials. Response: {_body_excerpt(resp)}",
                    status_code=401,
                )
        return resp

    def _send_authenticated(
        self, method: str, url: str, params: Optional[dict], json: Any
    ) -> requests.Response:
        headers = {
            "Authorization": f"Bearer {self.get_access_token()}",
            "tenantId": self.tenant_id,
            "Accept": "application/json",
        }
        if json is not None:
            headers["Content-Type"] = "application/json"
        return self._send_with_retry(method, url, params=params, json=json, headers=headers)

    def _send_with_retry(
        self,
        method: str,
        url: str,
        params: Optional[dict] = None,
        json: Any = None,
        headers: Optional[dict] = None,
    ) -> requests.Response:
        backoff = INITIAL_BACKOFF_SECONDS
        last_exc: Optional[Exception] = None
        resp: Optional[requests.Response] = None
        for attempt in range(MAX_RETRIES):
            try:
                resp = self.session.request(
                    method,
                    url,
                    params=params,
                    json=json,
                    headers=headers,
                    timeout=self.timeout,
                )
            except (requests.ConnectionError, requests.Timeout) as e:
                last_exc = e
                resp = None
            else:
                if resp.status_code not in RETRIABLE_STATUS_CODES:
                    return resp

            if attempt == MAX_RETRIES - 1:
                break
            time.sleep(self._retry_delay(resp, backoff))
            backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)

        if resp is not None:
            return resp
        raise BuildOpsAPIError(
            f"BuildOps request {method} {url} failed after {MAX_RETRIES} "
            f"attempts: {last_exc}"
        ) from last_exc

    @staticmethod
    def _retry_delay(resp: Optional[requests.Response], backoff: float) -> float:
        if resp is not None:
            retry_after = resp.headers.get("Retry-After")
            if retry_after:
                try:
                    return min(max(float(retry_after), 0.0), MAX_BACKOFF_SECONDS)
                except ValueError:
                    pass
        # Small jitter so parallel readers don't retry in lock-step.
        return min(backoff + random.uniform(0, backoff / 4), MAX_BACKOFF_SECONDS)
