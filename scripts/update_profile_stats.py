from __future__ import annotations

import os
import re
import html
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup


USERNAME = "sachinbhati779"
OUTPUT_DIR = Path("assets")

GITHUB_API = "https://api.github.com"
CONTRIBUTIONS_URL = f"https://github.com/users/{USERNAME}/contributions"

def fetch_profile_stats(session: requests.Session) -> dict:
    query = """
    query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          totalCommitContributions
          totalPullRequestContributions
          totalIssueContributions
          totalRepositoryContributions
        }
      }
    }
    """

    response = session.post(
        "https://api.github.com/graphql",
        json={
            "query": query,
            "variables": {"login": USERNAME},
        },
        timeout=30,
    )

    response.raise_for_status()

    payload = response.json()

    if "errors" in payload:
        raise RuntimeError(payload["errors"])

    return payload["data"]["user"]["contributionsCollection"]

def github_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2026-03-10",
        "User-Agent": "sachinbhati779-profile-stats",
    })

    token = os.getenv("GITHUB_TOKEN")
    if token:
        session.headers["Authorization"] = f"Bearer {token}"

    return session


def fetch_contributions(session: requests.Session) -> list[tuple[date, int]]:
    response = session.get(CONTRIBUTIONS_URL, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    days: list[tuple[date, int]] = []

    for node in soup.select("[data-date][data-level]"):
        raw_date = node.get("data-date")
        raw_level = node.get("data-level")

        if not raw_date:
            continue

        try:
            day = date.fromisoformat(raw_date)
            level = int(raw_level or 0)
        except ValueError:
            continue

        # GitHub contribution cells expose contribution count in accessible text.
        text = " ".join(node.stripped_strings)
        match = re.search(r"(\d[\d,]*)\s+contribution", text, re.I)

        count = int(match.group(1).replace(",", "")) if match else level
        days.append((day, count))

    # Fallback for markup variations: use accessible aria-label.
    if not days:
        for node in soup.select("[aria-label]"):
            label = node.get("aria-label", "")
            match = re.search(
                r"(\d[\d,]*)\s+contribution[s]?\s+on\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})",
                label,
                re.I,
            )
            if not match:
                continue

            count = int(match.group(1).replace(",", ""))
            day = datetime.strptime(match.group(2), "%B %d, %Y").date()
            days.append((day, count))

    if not days:
        raise RuntimeError("Could not parse GitHub contribution data.")

    return sorted(set(days))


def calculate_streaks(days: list[tuple[date, int]]) -> dict:
    contribution_map = {day: count for day, count in days}

    all_dates = sorted(contribution_map)
    if not all_dates:
        return {
            "total": 0,
            "current": 0,
            "longest": 0,
            "current_start": None,
            "current_end": None,
            "longest_start": None,
            "longest_end": None,
        }

    total = sum(contribution_map.values())

    # Fill the calendar from min to max so missing dates count as zero.
    start = min(all_dates)
    end = max(all_dates)

    cursor = start
    present_dates: list[tuple[date, int]] = []

    while cursor <= end:
        present_dates.append((cursor, contribution_map.get(cursor, 0)))
        cursor += timedelta(days=1)

    # Longest streak.
    longest = 0
    longest_start = None
    longest_end = None

    run_start = None
    run_length = 0

    for day, count in present_dates:
        if count > 0:
            if run_start is None:
                run_start = day
                run_length = 1
            else:
                run_length += 1

            if run_length > longest:
                longest = run_length
                longest_start = run_start
                longest_end = day
        else:
            run_start = None
            run_length = 0

    # Current streak.
    current = 0
    current_start = None
    current_end = end

    cursor = end

    while cursor >= start:
        if contribution_map.get(cursor, 0) > 0:
            current += 1
            current_start = cursor
            cursor -= timedelta(days=1)
        else:
            break

    if current == 0:
        current_start = None

    return {
        "total": total,
        "current": current,
        "longest": longest,
        "current_start": current_start,
        "current_end": current_end if current else None,
        "longest_start": longest_start,
        "longest_end": longest_end,
    }


def fetch_languages(session: requests.Session) -> dict[str, int]:
    totals: dict[str, int] = defaultdict(int)

    page = 1

    while True:
        response = session.get(
            f"{GITHUB_API}/users/{USERNAME}/repos",
            params={
                "type": "owner",
                "per_page": 100,
                "page": page,
            },
            timeout=30,
        )
        response.raise_for_status()

        repos = response.json()

        if not repos:
            break

        for repo in repos:
            if repo.get("fork"):
                continue

            owner = repo["owner"]["login"]
            name = repo["name"]

            lang_response = session.get(
                f"{GITHUB_API}/repos/{owner}/{name}/languages",
                timeout=30,
            )
            if lang_response.status_code != 200:
                continue

            for language, byte_count in lang_response.json().items():
                totals[language] += int(byte_count)

        page += 1

    return dict(
        sorted(
            totals.items(),
            key=lambda item: item[1],
            reverse=True,
        )
    )


def write_streak_svg(stats: dict) -> None:
    def fmt(value: date | None) -> str:
        return value.strftime("%b %-d, %Y") if value else "—"

    svg = f"""<svg width="760" height="250" viewBox="0 0 760 250"
xmlns="http://www.w3.org/2000/svg">

<rect width="760" height="250" rx="14" fill="#0d1117"/>
<rect x="1" y="1" width="758" height="248" rx="13"
fill="none" stroke="#30363d" stroke-width="2"/>

<rect x="2" y="2" width="756" height="46" rx="12" fill="#161b22"/>

<circle cx="24" cy="25" r="7" fill="#ff5f56"/>
<circle cx="46" cy="25" r="7" fill="#ffbd2e"/>
<circle cx="68" cy="25" r="7" fill="#27c93f"/>

<text x="88" y="30"
font-family="monospace"
font-size="14"
fill="#8b949e">
sachin@github:~$ streak
</text>

<text x="34" y="86"
font-family="monospace"
font-size="14"
fill="#3fb950">
total_commits
</text>

<text x="34" y="126"
font-family="monospace"
font-size="38"
font-weight="bold"
fill="#f0f6fc">
{stats["total_commits"]}
</text>

<text x="34" y="151"
font-family="monospace"
font-size="12"
fill="#8b949e">
all-time commits
</text>

<line x1="250" y1="72" x2="250" y2="194"
stroke="#30363d"/>

<text x="286" y="86"
font-family="monospace"
font-size="14"
fill="#58a6ff">
current_streak
</text>

<text x="286" y="126"
font-family="monospace"
font-size="38"
font-weight="bold"
fill="#f0f6fc">
{stats["current"]}
</text>

<text x="286" y="151"
font-family="monospace"
font-size="12"
fill="#8b949e">
{fmt(stats["current_start"])} → {fmt(stats["current_end"])}
</text>

<line x1="510" y1="72" x2="510" y2="194"
stroke="#30363d"/>

<text x="546" y="86"
font-family="monospace"
font-size="14"
fill="#58a6ff">
longest_streak
</text>

<text x="546" y="126"
font-family="monospace"
font-size="38"
font-weight="bold"
fill="#f0f6fc">
{stats["longest"]}
</text>

<text x="546" y="151"
font-family="monospace"
font-size="12"
fill="#8b949e">
days
</text>

<line x1="34" y1="194" x2="726" y2="194"
stroke="#21262d"/>

<text x="34" y="220"
font-family="monospace"
font-size="12"
fill="#3fb950">
status:
</text>

<text x="94" y="220"
font-family="monospace"
font-size="12"
fill="#8b949e">
live GitHub data
</text>

</svg>
"""

    (OUTPUT_DIR / "streak.svg").write_text(svg, encoding="utf-8")


def write_languages_svg(languages: dict[str, int]) -> None:
    top = list(languages.items())[:6]
    total = max(sum(languages.values()), 1)

    colors = [
        "#3178c6",
        "#b07219",
        "#f37726",
        "#3776ab",
        "#e34c26",
        "#6f42c1",
    ]

    svg = f"""<svg width="760" height="320" viewBox="0 0 760 320"
xmlns="http://www.w3.org/2000/svg">

<rect width="760" height="320" rx="14" fill="#0d1117"/>
<rect x="1" y="1" width="758" height="318" rx="13"
fill="none" stroke="#30363d" stroke-width="2"/>

<rect x="2" y="2" width="756" height="46" rx="12" fill="#161b22"/>

<circle cx="24" cy="25" r="7" fill="#ff5f56"/>
<circle cx="46" cy="25" r="7" fill="#ffbd2e"/>
<circle cx="68" cy="25" r="7" fill="#27c93f"/>

<text x="88" y="30"
font-family="monospace"
font-size="14"
fill="#8b949e">
sachin@github:~$ languages
</text>

<text x="34" y="82"
font-family="monospace"
font-size="14"
fill="#3fb950">
language_usage
</text>
"""

    y = 116

    for index, (language, byte_count) in enumerate(top):
        percentage = byte_count / total * 100
        bar_width = min(360, max(5, percentage / 100 * 360))
        color = colors[index % len(colors)]

        svg += f"""
<text x="34" y="{y}"
font-family="monospace"
font-size="13"
fill="#c9d1d9">
{html.escape(language)}
</text>

<rect x="150" y="{y - 11}"
width="360" height="14" rx="7"
fill="#21262d"/>

<rect x="150" y="{y - 11}"
width="{bar_width:.1f}" height="14" rx="7"
fill="{color}"/>

<text x="530" y="{y}"
font-family="monospace"
font-size="12"
fill="#8b949e">
{percentage:.2f}%
</text>
"""

        y += 34

    svg += """
</svg>
"""

    (OUTPUT_DIR / "languages.svg").write_text(svg, encoding="utf-8")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    session = github_session()

    contributions = fetch_contributions(session)
stats = calculate_streaks(contributions)

profile_stats = fetch_profile_stats(session)

stats["total_commits"] = profile_stats["totalCommitContributions"]

languages = fetch_languages(session)

write_streak_svg(stats)
write_languages_svg(languages)

print(f"Total commits: {stats['total_commits']}")
print(f"Total contributions: {stats['total']}")
print(f"Current streak: {stats['current']}")
print(f"Longest streak: {stats['longest']}")

    print("Updated assets/streak.svg")
    print("Updated assets/languages.svg")
    print(f"Total contributions: {stats['total']}")
    print(f"Current streak: {stats['current']}")
    print(f"Longest streak: {stats['longest']}")
    print("Languages:", ", ".join(languages.keys()))


if __name__ == "__main__":
    main()
