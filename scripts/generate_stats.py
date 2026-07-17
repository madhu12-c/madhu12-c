"""Self-built stats engine for the profile README.

Draws two panels in GitHub's own Primer dark palette:
  assets/stats-panel.svg    totals + language mix
  assets/heatmap-panel.svg  contribution heatmap + streaks, computed from raw data

Runs daily via GitHub Actions using the built-in GITHUB_TOKEN (GraphQL).
Falls back to the public REST API + contributions page when run locally.

The contribution numbers include private contributions because the
"include private contributions" setting is enabled on the profile.
"""

import json
import os
import re
import urllib.request
from datetime import date, datetime, timedelta, timezone

USER = "madhu12-c"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATS_OUT = os.path.join(ROOT, "assets", "stats-panel.svg")
HEAT_OUT = os.path.join(ROOT, "assets", "heatmap-panel.svg")

GREENS = ["#39d353", "#26a641", "#006d32", "#0e4429", "#484f58"]
LEVEL_FILL = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]

FONT = ("<style>text { font-family: 'Cascadia Code', 'Fira Code', Consolas, "
        "'DejaVu Sans Mono', monospace; } .bar { font-size: 11px; fill: #484f58; } "
        ".num { font-size: 38px; font-weight: bold; fill: #e6edf3; } "
        ".mid { font-size: 26px; font-weight: bold; fill: #e6edf3; } "
        ".lbl { font-size: 11px; fill: #8b949e; letter-spacing: 2px; } "
        ".leg { font-size: 12px; fill: #8b949e; }</style>")


def _get(url, headers=None, data=None):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def _frame(width, height, title, right_note):
    parts = [
        '<svg viewBox="0 0 %d %d" width="%d" height="%d" '
        'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="%s">' % (width, height, width, height, title),
        FONT,
        '<rect x="0.5" y="0.5" width="%d" height="%d" rx="6" fill="#0d1117" stroke="#30363d"/>' % (width - 1, height - 1),
        '<path d="M 0.5 6.5 a 6 6 0 0 1 6 -6 h %d a 6 6 0 0 1 6 6 v 25.5 h -%d z" fill="#161b22"/>' % (width - 13, width - 1),
        '<circle cx="22" cy="16" r="5" fill="#30363d"/>',
        '<circle cx="42" cy="16" r="5" fill="#30363d"/>',
        '<circle cx="62" cy="16" r="5" fill="#30363d"/>',
        '<text x="%d" y="21" text-anchor="middle" class="bar">%s</text>' % (width // 2, title),
        '<text x="%d" y="21" text-anchor="end" class="bar">%s</text>' % (width - 24, right_note),
    ]
    return parts


def level_for(count):
    if count <= 0:
        return 0
    if count <= 2:
        return 1
    if count <= 5:
        return 2
    if count <= 9:
        return 3
    return 4


def fetch_graphql(token):
    query = """
    query {
      user(login: "%s") {
        followers { totalCount }
        repositories(first: 100, ownerAffiliations: OWNER, privacy: PUBLIC) {
          totalCount
          nodes { isFork stargazerCount primaryLanguage { name } }
        }
        contributionsCollection {
          contributionCalendar {
            totalContributions
            weeks { contributionDays { date contributionCount } }
          }
        }
      }
    }""" % USER
    body = json.dumps({"query": query}).encode("utf-8")
    raw = _get(
        "https://api.github.com/graphql",
        headers={
            "Authorization": "bearer " + token,
            "Content-Type": "application/json",
            "User-Agent": USER,
        },
        data=body,
    )
    user = json.loads(raw)["data"]["user"]
    repos = user["repositories"]["nodes"]
    langs = {}
    for r in repos:
        if not r["isFork"] and r["primaryLanguage"]:
            name = r["primaryLanguage"]["name"]
            langs[name] = langs.get(name, 0) + 1
    calendar = user["contributionsCollection"]["contributionCalendar"]
    days = []
    for week in calendar["weeks"]:
        for d in week["contributionDays"]:
            days.append((date.fromisoformat(d["date"]), d["contributionCount"]))
    days.sort()
    return {
        "contributions": calendar["totalContributions"],
        "stars": sum(r["stargazerCount"] for r in repos),
        "followers": user["followers"]["totalCount"],
        "repos": user["repositories"]["totalCount"],
        "langs": langs,
        "days": days,
    }


def fetch_rest():
    api_headers = {"User-Agent": USER, "Accept": "application/vnd.github+json"}
    profile = json.loads(_get("https://api.github.com/users/%s" % USER, api_headers))
    repos = json.loads(_get(
        "https://api.github.com/users/%s/repos?per_page=100&type=owner" % USER, api_headers))
    html = _get("https://github.com/users/%s/contributions" % USER,
                {"User-Agent": "Mozilla/5.0"})
    total_match = re.search(r"([\d,]+)\s+contributions", html)

    cells = {}
    levels = {}
    for m in re.finditer(r"<td[^>]*contribution-day-component[^>]*>", html):
        tag = m.group(0)
        dm = re.search(r'data-date="([\d-]+)"', tag)
        im = re.search(r'id="([^"]+)"', tag)
        lm = re.search(r'data-level="(\d)"', tag)
        if dm and im:
            cells[im.group(1)] = date.fromisoformat(dm.group(1))
            # representative count per level so the drawn shade round-trips
            levels[im.group(1)] = {0: 0, 1: 1, 2: 3, 3: 6, 4: 10}[int(lm.group(1)) if lm else 0]
    counts = {}
    for m in re.finditer(r'<tool-tip[^>]*for="(contribution-day-component[^"]+)"[^>]*>([^<]*)</tool-tip>', html):
        num = re.match(r"(\d+|No)\s+contribution", m.group(2).strip())
        if num:
            counts[m.group(1)] = 0 if num.group(1) == "No" else int(num.group(1))
    days = sorted((d, counts.get(cid, levels.get(cid, 0))) for cid, d in cells.items())

    langs = {}
    for r in repos:
        if not r["fork"] and r["language"]:
            langs[r["language"]] = langs.get(r["language"], 0) + 1
    return {
        "contributions": int(total_match.group(1).replace(",", "")) if total_match else 0,
        "stars": sum(r["stargazers_count"] for r in repos),
        "followers": profile["followers"],
        "repos": profile["public_repos"],
        "langs": langs,
        "days": days,
    }


def streaks(days):
    longest = run = 0
    for _, count in days:
        run = run + 1 if count > 0 else 0
        longest = max(longest, run)
    current = 0
    i = len(days) - 1
    if i >= 0 and days[i][1] == 0:
        i -= 1                     # today may simply have no commits yet
    while i >= 0 and days[i][1] > 0:
        current += 1
        i -= 1
    return current, longest


def render_stats(stats, today):
    top = sorted(stats["langs"].items(), key=lambda kv: -kv[1])[:5]
    lang_total = sum(stats["langs"].values()) or 1

    svg = _frame(880, 300, "$ ./stats --render --daily", "synced %s" % today)
    columns = [
        (128, "{:,}".format(stats["contributions"]), "CONTRIBUTIONS", "#39d353", "past year, public + private"),
        (337, str(stats["stars"]), "STARS EARNED", "#e6edf3", None),
        (543, str(stats["followers"]), "FOLLOWERS", "#e6edf3", None),
        (749, str(stats["repos"]), "PUBLIC REPOS", "#e6edf3", None),
    ]
    for x, value, label, color, note in columns:
        svg.append('<text x="%d" y="118" text-anchor="middle" class="num" fill="%s">%s</text>' % (x, color, value))
        svg.append('<text x="%d" y="146" text-anchor="middle" class="lbl">%s</text>' % (x, label))
        if note:
            svg.append('<text x="%d" y="163" text-anchor="middle" class="bar">%s</text>' % (x, note))
    for x in (234, 440, 646):
        svg.append('<line x1="%d" y1="80" x2="%d" y2="160" stroke="#21262d"/>' % (x, x))

    svg.append('<text x="32" y="200" class="lbl">LANGUAGE MIX</text>')
    if top:
        svg.append('<defs><clipPath id="lb"><rect x="32" y="208" width="816" height="12" rx="6"/></clipPath></defs>')
        widths = [max(10, round(816 * count / lang_total)) for _, count in top]
        overflow = sum(widths) - 816
        if overflow > 0:
            widths[0] -= overflow
        x = 32
        svg.append('<g clip-path="url(#lb)">')
        svg.append('<rect x="32" y="208" width="816" height="12" fill="#161b22"/>')
        for i, w in enumerate(widths):
            svg.append('<rect x="%d" y="208" width="%d" height="12" fill="%s"/>' % (x, w, GREENS[i]))
            x += w
        svg.append('</g>')
        x = 32
        for i, (name, count) in enumerate(top):
            pct = round(100 * count / lang_total)
            svg.append('<rect x="%d" y="238" width="10" height="10" rx="2" fill="%s"/>' % (x, GREENS[i]))
            svg.append('<text x="%d" y="247" class="leg">%s %d%%</text>' % (x + 16, name.lower(), pct))
            x += 160

    svg.append('<text x="32" y="282" class="bar">generated by scripts/generate_stats.py in this repo, '
               'refreshed daily by github actions, zero third-party card services</text>')
    svg.append('</svg>')
    return "\n".join(svg) + "\n"


def render_heatmap(stats, today):
    days = stats["days"]
    svg = _frame(880, 280, "$ git log --graph --since=1.year", "streaks computed from raw data")

    if days:
        start = days[0][0]
        start_sunday = start - timedelta(days=(start.isoweekday() % 7))
        weeks = {}
        for d, count in days:
            col = (d - start_sunday).days // 7
            row = d.isoweekday() % 7
            weeks.setdefault(col, []).append((row, count))

        x0, y0, step = 32, 50, 12
        for col in sorted(weeks):
            cells = []
            for row, count in weeks[col]:
                lvl = level_for(count)
                x, y = x0 + col * step, y0 + row * step
                if lvl == 0:
                    cells.append('<rect x="%d" y="%d" width="10" height="10" rx="2" '
                                 'fill="#161b22" stroke="#21262d"/>' % (x, y))
                elif lvl == 4:
                    cells.append('<rect x="%d" y="%d" width="10" height="10" rx="2" fill="%s">'
                                 '<animate attributeName="opacity" values="1;0.55;1" dur="2.6s" '
                                 'begin="%.2fs" repeatCount="indefinite"/></rect>'
                                 % (x, y, LEVEL_FILL[lvl], 1.8 + col * 0.05))
                else:
                    cells.append('<rect x="%d" y="%d" width="10" height="10" rx="2" fill="%s"/>'
                                 % (x, y, LEVEL_FILL[lvl]))
            svg.append('<g opacity="0"><animate attributeName="opacity" from="0" to="1" '
                       'begin="%.2fs" dur="0.3s" fill="freeze"/>%s</g>'
                       % (0.2 + col * 0.025, "".join(cells)))

        current, longest = streaks(days)
        busiest_day, busiest = max(days, key=lambda dc: dc[1])
        active = sum(1 for _, c in days if c > 0)
        columns = [
            (128, "%d days" % current, "CURRENT STREAK", "#39d353"),
            (337, "%d days" % longest, "LONGEST STREAK", "#e6edf3"),
            (543, str(busiest), "BUSIEST DAY, %s" % busiest_day.strftime("%b %d").upper(), "#e6edf3"),
            (749, str(active), "DAYS ACTIVE", "#e6edf3"),
        ]
        for x, value, label, color in columns:
            svg.append('<text x="%d" y="200" text-anchor="middle" class="mid" fill="%s">%s</text>' % (x, color, value))
            svg.append('<text x="%d" y="224" text-anchor="middle" class="lbl">%s</text>' % (x, label))
        for x in (234, 440, 646):
            svg.append('<line x1="%d" y1="176" x2="%d" y2="228" stroke="#21262d"/>' % (x, x))

    svg.append('<text x="32" y="262" class="bar">every cell above is drawn by scripts/generate_stats.py, '
               'private contributions included</text>')
    svg.append('</svg>')
    return "\n".join(svg) + "\n"


def main():
    token = os.environ.get("GITHUB_TOKEN")
    stats = fetch_graphql(token) if token else fetch_rest()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with open(STATS_OUT, "w", encoding="utf-8") as f:
        f.write(render_stats(stats, today))
    with open(HEAT_OUT, "w", encoding="utf-8") as f:
        f.write(render_heatmap(stats, today))
    print("panels written:", {k: v for k, v in stats.items() if k not in ("langs", "days")})
    print("calendar days parsed:", len(stats["days"]))


if __name__ == "__main__":
    main()
