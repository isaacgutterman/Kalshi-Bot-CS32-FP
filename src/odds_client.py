import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

ODDS_API_BASE_URL = "https://api.the-odds-api.com/v4"


@dataclass
class OddsSnapshot:
    home_team: str
    away_team: str
    home_win_prob: float
    away_win_prob: float


def _normalize_team_name(name: str) -> str:
    return " ".join(name.lower().replace(".", "").replace("-", " ").split())


def _american_to_prob(price: float) -> Optional[float]:
    if price == 0:
        return None
    if price > 0:
        return 100.0 / (price + 100.0)
    return abs(price) / (abs(price) + 100.0)


def project_dotenv_path() -> Path:
    return Path(__file__).resolve().parent.parent / ".env"


def _resolve_odds_api_key_with_source(cli_api_key: Optional[str]) -> Tuple[str, str]:
    """Returns (key, human-readable source). Order: CLI > project .env > OS env."""
    cli = (cli_api_key or "").strip()
    if cli:
        return cli, "CLI --odds-api-key"
    env_path = project_dotenv_path()
    from_dotenv = _read_env_key_from_project_root("ODDS_API_KEY").strip()
    if from_dotenv:
        return from_dotenv, f".env file ({env_path})"
    os_key = (os.getenv("ODDS_API_KEY", "") or "").strip()
    if os_key:
        return os_key, "environment variable ODDS_API_KEY"
    return "", "not set"


class TheOddsApiClient:
    """Moneyline implied probabilities from The Odds API (the-odds-api.com) for one bookmaker key."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        sport_key: str = "baseball_mlb",
        bookmaker: str = "draftkings",
        timeout: int = 12,
    ) -> None:
        self.api_key, self.api_key_source = _resolve_odds_api_key_with_source(api_key)
        self.sport_key = sport_key
        self.bookmaker = bookmaker.strip().lower() or "draftkings"
        self.timeout = timeout
        self.session = requests.Session()

    def _get_json(self, path: str, params: Dict[str, str]) -> object:
        if not self.api_key:
            raise RuntimeError("Missing Odds API key. Set ODDS_API_KEY or pass --odds-api-key.")
        url = f"{ODDS_API_BASE_URL}{path}"
        full_params = dict(params)
        full_params["apiKey"] = self.api_key
        response = self.session.get(url, params=full_params, timeout=self.timeout)
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            code = response.status_code
            if code == 401:
                raise RuntimeError(
                    "The Odds API returned 401 Unauthorized: the server rejected this API key. "
                    "Open https://the-odds-api.com/ → Account, copy the key again (no spaces), save as "
                    "ODDS_API_KEY=... in the project .env next to src/, or pass --odds-api-key. "
                    "Regenerate the key if it was ever pasted into chat or a public repo. "
                    "On startup, the bot prints which file/source was used and the key length—if the length "
                    "does not match your dashboard key, the wrong file or line is being read."
                ) from exc
            if code == 403:
                raise RuntimeError(
                    "The Odds API returned 403 Forbidden: your plan may not include this endpoint or region."
                ) from exc
            if code == 429:
                raise RuntimeError(
                    "The Odds API returned 429 Too Many Requests: wait or upgrade your plan."
                ) from exc
            raise RuntimeError(f"The Odds API request failed with HTTP {code}.") from exc
        return response.json()

    def get_moneyline_probabilities(self) -> Dict[str, float]:
        payload = self._get_json(
            f"/sports/{self.sport_key}/odds",
            {
                "regions": "us",
                "markets": "h2h",
                "bookmakers": self.bookmaker,
                "oddsFormat": "american",
            },
        )
        if not isinstance(payload, list):
            return {}

        out: Dict[str, float] = {}
        for event in payload:
            if not isinstance(event, dict):
                continue
            home_team = str(event.get("home_team", "")).strip()
            away_team = str(event.get("away_team", "")).strip()
            bookmakers = event.get("bookmakers", []) or []
            if not home_team or not away_team or not bookmakers:
                continue
            markets = bookmakers[0].get("markets", []) if isinstance(bookmakers[0], dict) else []
            if not markets:
                continue

            outcomes = markets[0].get("outcomes", []) if isinstance(markets[0], dict) else []
            probs: Dict[str, float] = {}
            for outcome in outcomes:
                if not isinstance(outcome, dict):
                    continue
                name = str(outcome.get("name", "")).strip()
                price = outcome.get("price")
                if not name or price is None:
                    continue
                try:
                    p = _american_to_prob(float(price))
                except (TypeError, ValueError):
                    p = None
                if p is not None:
                    probs[_normalize_team_name(name)] = p

            h_key = _normalize_team_name(home_team)
            a_key = _normalize_team_name(away_team)
            if h_key not in probs or a_key not in probs:
                continue

            total = probs[h_key] + probs[a_key]
            if total <= 0.0:
                continue
            # Remove bookmaker vig by normalizing to 1.0.
            out[h_key] = probs[h_key] / total
            out[a_key] = probs[a_key] / total
        return out


def _read_env_key_from_project_root(key: str) -> str:
    env_path = project_dotenv_path()
    if not env_path.exists():
        return ""
    try:
        for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            if name.strip() == key:
                return value.strip().strip('"').strip("'")
    except OSError:
        return ""
    return ""


# Backward-compatible alias (calls go to The Odds API; bookmaker is configurable).
DraftKingsOddsClient = TheOddsApiClient
