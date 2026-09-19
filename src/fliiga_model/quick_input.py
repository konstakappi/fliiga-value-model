from __future__ import annotations

import re


def parse_bookmaker_odds(
    text: str, bookmakers: list[str]
) -> dict[str, tuple[float, float]]:
    """Parse two decimal odds from each bookmaker line of pasted text."""
    parsed: dict[str, tuple[float, float]] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        bookmaker = next(
            (name for name in bookmakers if name.casefold() in line.casefold()), None
        )
        if bookmaker is None:
            continue
        values = [
            float(token.replace(",", "."))
            for token in re.findall(r"(?<!\d)\d{1,2}[.,]\d{1,3}(?!\d)", line)
        ]
        valid_odds = [value for value in values if 1.01 <= value <= 20.0]
        if len(valid_odds) >= 2:
            parsed[bookmaker] = (valid_odds[-2], valid_odds[-1])
    return parsed
