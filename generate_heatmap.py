#!/usr/bin/env python3
"""
Generates vishwakumarv-contrib-heatmap.svg (and contrib-heatmap.svg) from
real GitHub contribution data, in the same visual style as the existing
hand-built SVG (pop + flash animation, GitHub dark-theme palette).

Requires:
  GITHUB_TOKEN  - any token with public read access (the default
                   Actions GITHUB_TOKEN works fine, contribution
                   calendars are public data)
  GH_USERNAME   - the GitHub login to fetch (defaults to "vishwakumarv")

Run locally:
  GITHUB_TOKEN=ghp_xxx GH_USERNAME=vishwakumarv python3 scripts/generate_heatmap.py
"""

import json
import os
import sys
import urllib.request

GRAPHQL_URL = "https://api.github.com/graphql"

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            date
            weekday
            contributionCount
          }
        }
      }
    }
  }
}
"""

# GitHub's dark-theme contribution palette (matches the levels already
# used in the hand-built SVG this replaces).
LEVEL_COLORS = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]

CELL = 13
GAP = 3
STEP = CELL + GAP  # 16
GRID_LEFT = 34
GRID_TOP = 24
LABEL_ROW_Y = 16
TOTAL_ROW_Y_OFFSET = 32  # below the grid

MONTH_NAMES = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]
WEEKDAY_LABELS = {1: "Mon", 3: "Wed", 5: "Fri"}  # weekday index -> label


def fetch_calendar(login, token):
    body = json.dumps({"query": QUERY, "variables": {"login": login}}).encode()
    req = urllib.request.Request(
        GRAPHQL_URL,
        data=body,
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "contrib-heatmap-generator",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    if "errors" in payload:
        raise RuntimeError(f"GitHub GraphQL error: {payload['errors']}")
    return payload["data"]["user"]["contributionsCollection"]["contributionCalendar"]


def levels_for(weeks):
    """Assign each day a 0-4 level using quartiles of the nonzero counts,
    the same bucketing approach GitHub itself uses."""
    counts = sorted(
        d["contributionCount"]
        for w in weeks
        for d in w["contributionDays"]
        if d["contributionCount"] > 0
    )

    def pct(p):
        if not counts:
            return 0
        idx = min(int(len(counts) * p), len(counts) - 1)
        return counts[idx]

    q1, q2, q3 = pct(0.25), pct(0.5), pct(0.75)

    def level(count):
        if count == 0:
            return 0
        if count <= q1:
            return 1
        if count <= q2:
            return 2
        if count <= q3:
            return 3
        return 4

    return level


def build_svg(calendar):
    weeks = calendar["weeks"]
    total = calendar["totalContributions"]
    level_of = levels_for(weeks)

    n_cols = len(weeks)
    width = GRID_LEFT + n_cols * STEP
    height = GRID_TOP + 7 * STEP + TOTAL_ROW_Y_OFFSET

    cells = []
    month_labels = []
    last_month = None
    delay_index = 0
    total_cells = sum(len(w["contributionDays"]) for w in weeks)
    max_delay = 3.5
    delay_step = max_delay / max(total_cells, 1)

    for col, week in enumerate(weeks):
        x = GRID_LEFT + col * STEP
        for day in week["contributionDays"]:
            weekday = day["weekday"]  # 0=Sun .. 6=Sat
            y = GRID_TOP + weekday * STEP
            count = day["contributionCount"]
            lvl = level_of(count)
            fill = LEVEL_COLORS[lvl]
            cls = "c e" if lvl == 0 else "c g"
            delay = round(delay_index * delay_step, 3)
            cells.append(
                f'<rect class="{cls}" x="{x}" y="{y}" width="{CELL}" '
                f'height="{CELL}" rx="2.5" fill="{fill}" '
                f'style="animation-delay:{delay}s">'
                f'<title>{day["date"]}: {count} contribution'
                f'{"s" if count != 1 else ""}</title></rect>'
            )
            delay_index += 1

            # Month label: first Sunday-row day of a new month in this column
            if weekday == 0:
                month = int(day["date"].split("-")[1]) - 1
                if month != last_month:
                    month_labels.append(
                        f'<text class="lbl" x="{x}" y="{LABEL_ROW_Y}">'
                        f'{MONTH_NAMES[month]}</text>'
                    )
                    last_month = month

    weekday_labels = "".join(
        f'<text class="lbl" x="2" y="{GRID_TOP + wd * STEP + 11}">{label}</text>'
        for wd, label in WEEKDAY_LABELS.items()
    )

    total_y = GRID_TOP + 7 * STEP + 8
    total_text = (
        f'<text class="total" x="{GRID_LEFT}" y="{total_y}">'
        f'{total:,} contributions in the last year</text>'
    )

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" font-family="-apple-system,Segoe UI,Helvetica,Arial,sans-serif">
<style>
  text.lbl {{ fill:#7d8590; font-size:13px; font-weight:600; }}
  text.total {{ fill:#e6edf3; font-size:15px; font-weight:700; }}
  .c {{ transform-box:fill-box; transform-origin:center; opacity:0; animation:pop 0.55s ease-out both; }}
  .g {{ animation:pop 0.55s ease-out both, flash 0.7s ease-out both; }}
  @keyframes pop {{ 0%{{opacity:0;transform:scale(0.3)}} 60%{{opacity:1;transform:scale(1.15)}} 100%{{opacity:1;transform:scale(1)}} }}
  @keyframes flash {{ 0%{{filter:brightness(1)}} 40%{{filter:brightness(1.8)}} 100%{{filter:brightness(1)}} }}
</style>
{weekday_labels}{''.join(month_labels)}
{''.join(cells)}
{total_text}
</svg>"""
    return svg


def main():
    token = os.environ.get("GITHUB_TOKEN")
    login = os.environ.get("GH_USERNAME", "vishwakumarv")
    if not token:
        print("GITHUB_TOKEN is not set", file=sys.stderr)
        sys.exit(1)

    calendar = fetch_calendar(login, token)
    svg = build_svg(calendar)

    out_paths = ["contrib-heatmap.svg", "vishwakumarv-contrib-heatmap.svg"]
    for path in out_paths:
        with open(path, "w") as f:
            f.write(svg)
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
