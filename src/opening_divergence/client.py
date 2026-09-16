"""Client for the Lichess Opening Explorer API.

As of 2026 the Opening Explorer (``/masters``, ``/lichess``, ``/player``)
requires OAuth authentication -- see
https://github.com/lichess-org/lila-openingexplorer/issues/323 and the
current spec at
https://github.com/lichess-org/api/blob/master/doc/specs/tags/openingexplorer/lichess.yaml
(``security: [OAuth2: []]``). This was not the case when this project was
scoped (the API used to be fully public), so a personal access token
(free, no scopes required) is now mandatory. See README.md for setup.

The client caches every successful response to disk (keyed by endpoint +
params) so re-running analysis scripts never re-hits the network for a
position that has already been fetched, and enforces a minimum delay
between requests plus exponential backoff on 429/5xx, per the API's
"only make one request at a time" / rate-limiting guidance.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import requests

DEFAULT_BASE_URL = "https://explorer.lichess.org"
TOKEN_HELP_URL = "https://lichess.org/account/oauth/token"
ISSUE_URL = "https://github.com/lichess-org/lila-openingexplorer/issues/323"


class ExplorerError(RuntimeError):
    """Raised for non-auth API failures (after retries are exhausted)."""


class ExplorerAuthError(ExplorerError):
    """Raised when a request is rejected for missing/invalid credentials."""


def _stable_key(endpoint: str, params: Mapping[str, Any]) -> str:
    normalized = {k: v for k, v in params.items() if v is not None}
    payload = json.dumps({"endpoint": endpoint, "params": normalized}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


class ExplorerClient:
    """Thin, caching, rate-limit-respecting client for explorer.lichess.org."""

    def __init__(
        self,
        token: str | None = None,
        cache_dir: str | Path = "data/raw",
        base_url: str = DEFAULT_BASE_URL,
        min_interval: float = 1.0,
        max_retries: int = 6,
        session: requests.Session | None = None,
    ) -> None:
        self.token = token if token is not None else os.environ.get("LICHESS_TOKEN") or None
        self.cache_dir = Path(cache_dir)
        self.base_url = base_url.rstrip("/")
        self.min_interval = min_interval
        self.max_retries = max_retries
        self.session = session or requests.Session()
        self._last_request_monotonic = 0.0
        self.requests_made = 0
        self.cache_hits = 0

    def _headers(self) -> dict:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _cache_path(self, endpoint: str, params: Mapping[str, Any]) -> Path:
        digest = _stable_key(endpoint, params)
        return self.cache_dir / endpoint / f"{digest}.json"

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_monotonic
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)

    def query(
        self,
        endpoint: str,
        params: Mapping[str, Any],
        use_cache: bool = True,
    ) -> dict:
        """GET explorer.lichess.org/<endpoint> with the given query params.

        ``endpoint`` is one of "lichess", "masters", "player". Results are
        cached to ``<cache_dir>/<endpoint>/<hash>.json`` and reused on
        subsequent calls with the same params.
        """
        cache_path = self._cache_path(endpoint, params)
        if use_cache and cache_path.exists():
            self.cache_hits += 1
            with open(cache_path, encoding="utf-8") as f:
                return json.load(f)["response"]

        if not self.token:
            raise ExplorerAuthError(
                "LICHESS_TOKEN is not set. As of 2026 the Lichess Opening "
                "Explorer API requires an OAuth personal access token; it "
                "used to be fully public (see "
                f"{ISSUE_URL}). Generate a free token with no scopes at "
                f"{TOKEN_HELP_URL} and put it in a .env file as "
                "LICHESS_TOKEN=<token> (see .env.example)."
            )

        url = f"{self.base_url}/{endpoint}"
        attempt = 0
        while True:
            self._throttle()
            response = self.session.get(url, params=dict(params), headers=self._headers(), timeout=30)
            self._last_request_monotonic = time.monotonic()
            self.requests_made += 1

            if response.status_code == 200:
                data = response.json()
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump({"endpoint": endpoint, "params": dict(params), "response": data}, f)
                return data

            if response.status_code == 401:
                raise ExplorerAuthError(
                    f"401 Unauthorized from {response.url}. Token missing/invalid/expired. "
                    f"Generate a new one at {TOKEN_HELP_URL}."
                )

            if response.status_code == 429 or response.status_code >= 500:
                attempt += 1
                if attempt > self.max_retries:
                    raise ExplorerError(
                        f"Giving up on {response.url} after {attempt} attempts "
                        f"(last status {response.status_code})."
                    )
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else min(60.0, 2.0**attempt)
                time.sleep(delay)
                continue

            response.raise_for_status()

    def lichess(
        self,
        play: str = "",
        speeds: list[str] | None = None,
        ratings: list[int] | None = None,
        variant: str = "standard",
        moves: int = 12,
        top_games: int = 0,
        recent_games: int = 0,
        use_cache: bool = True,
    ) -> dict:
        params: dict[str, Any] = {
            "variant": variant,
            "play": play,
            "moves": moves,
            "topGames": top_games,
            "recentGames": recent_games,
        }
        if speeds:
            params["speeds"] = ",".join(speeds)
        if ratings:
            params["ratings"] = ",".join(str(r) for r in ratings)
        return self.query("lichess", params, use_cache=use_cache)

    def masters(
        self,
        play: str = "",
        moves: int = 12,
        top_games: int = 0,
        use_cache: bool = True,
    ) -> dict:
        params = {"play": play, "moves": moves, "topGames": top_games}
        return self.query("masters", params, use_cache=use_cache)
