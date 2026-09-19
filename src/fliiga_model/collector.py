from __future__ import annotations

import html
import time
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DEFAULT_API_URL = "https://fliiga.com/wp-json/wp/v2/ottelut"


@dataclass(frozen=True)
class CollectionResult:
    completed: pd.DataFrame
    fixtures: pd.DataFrame


class FliigaCollector:
    """Read public match metadata from F-liiga's WordPress REST API."""

    def __init__(
        self,
        api_url: str = DEFAULT_API_URL,
        timeout: float = 30.0,
        request_delay: float = 0.15,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.timeout = timeout
        self.request_delay = request_delay
        self.session = requests.Session()
        retries = Retry(
            total=4,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retries))
        self.session.headers.update({"User-Agent": "fliiga-value-model/0.5.0 (+research)"})

    def _page(self, page: int) -> tuple[list[dict[str, Any]], int]:
        response = self.session.get(
            self.api_url,
            params={
                "page": page,
                "per_page": 100,
                "orderby": "id",
                "order": "asc",
                "_fields": "id,link,title,meta",
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        total_pages = int(response.headers.get("X-WP-TotalPages", "1"))
        return response.json(), total_pages

    def fetch_posts(self) -> list[dict[str, Any]]:
        first, total_pages = self._page(1)
        posts = list(first)
        for page in range(2, total_pages + 1):
            if self.request_delay:
                time.sleep(self.request_delay)
            batch, _ = self._page(page)
            posts.extend(batch)
        return posts

    @staticmethod
    def _team_names(post: dict[str, Any]) -> tuple[str, str]:
        title = html.unescape(post.get("title", {}).get("rendered", "")).strip()
        parts = title.split(" vs ", maxsplit=1)
        if len(parts) != 2:
            raise ValueError(f"Cannot parse teams from match title: {title!r}")
        return parts[0].strip(), parts[1].strip()

    @classmethod
    def normalize(cls, posts: Iterable[dict[str, Any]]) -> CollectionResult:
        completed_columns = [
            "match_id",
            "date",
            "season",
            "competition",
            "round",
            "home_team",
            "away_team",
            "source_url",
            "home_goals",
            "away_goals",
        ]
        fixture_columns = completed_columns[:-2]
        completed: list[dict[str, Any]] = []
        fixtures: list[dict[str, Any]] = []
        now = pd.Timestamp.now(tz="Europe/Helsinki").tz_localize(None)
        for post in posts:
            meta = post.get("meta", {})
            if str(meta.get("_sarja", "")).casefold() != "miehet":
                continue
            try:
                home_team, away_team = cls._team_names(post)
                date = pd.Timestamp(meta.get("_ottelu_aika"))
                if pd.isna(date):
                    continue
                if date.tzinfo is not None:
                    date = date.tz_localize(None)
            except (TypeError, ValueError):
                continue

            common = {
                "match_id": str(meta.get("_torneopal_id") or post.get("id")),
                "date": date,
                "season": str(meta.get("_kausi", "")),
                "competition": str(meta.get("_ryhma_nimi", "")),
                "round": str(meta.get("_kierros_nimi", "")),
                "home_team": home_team,
                "away_team": away_team,
                "source_url": post.get("link", ""),
            }
            home_goals = meta.get("_kotimaalit")
            away_goals = meta.get("_vierasmaalit")
            is_scored = home_goals not in (None, "") and away_goals not in (None, "")
            is_placeholder = is_scored and int(home_goals) == 0 and int(away_goals) == 0
            if date <= now and is_scored and not is_placeholder:
                completed.append(
                    {
                        **common,
                        "home_goals": int(home_goals),
                        "away_goals": int(away_goals),
                    }
                )
            elif date > now:
                fixtures.append(common)

        completed_frame = pd.DataFrame(completed, columns=completed_columns)
        fixtures_frame = pd.DataFrame(fixtures, columns=fixture_columns)
        if not completed_frame.empty:
            completed_frame = (
                completed_frame.sort_values(["date", "match_id"])
                .drop_duplicates("match_id", keep="last")
                .reset_index(drop=True)
            )
        if not fixtures_frame.empty:
            fixtures_frame = (
                fixtures_frame.sort_values(["date", "match_id"])
                .drop_duplicates("match_id", keep="last")
                .reset_index(drop=True)
            )
        return CollectionResult(completed=completed_frame, fixtures=fixtures_frame)

    def collect(self) -> CollectionResult:
        return self.normalize(self.fetch_posts())
