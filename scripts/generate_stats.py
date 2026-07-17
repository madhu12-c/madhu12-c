"""Self-built stats engine for the profile README.

Draws assets/stats-panel.svg in GitHub's own Primer dark palette.
Runs daily via GitHub Actions using the built-in GITHUB_TOKEN (GraphQL).
Falls back to the public REST API when run locally without a token.

The contribution total includes private contributions because the
"include private contributions" setting is enabled on the profile.
"""

import json
import os
import re
import urllib.request
from datetime import datetime, timezone

USER = "madhu12-c"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets", "stats-panel.svg")

GREENS = ["#39d353", "#26a641", "#006d32", "#0e4429", "#484f58"]


def _get(url, headers=None, data=None):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


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
          contributionCalendar { totalContributions }
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
    return {
        "contributions": user["contributionsCollection"]["contributionCalendar"]["totalContributions"],
        "stars": sum(r["stargazerCount"] for r in repos),
        "followers": user["followers"]["totalCount"],
        "repos": user["repositories"]["totalCount"],
        "langs": langs,
    }


def fetch_rest():
    api_headers = {"User-Agent": USER, "Accept": "application/vnd.github+json"}
    profile = json.loads(_get("https://api.github.com/users/%s" % USER, api_headers))
    repos = json.loads(_get(
        "https://api.github.com/users/%s/repos?per_page=100&type=owner" % USER, api_headers))
    html = _get("https://github.com/users/%s/contributions" % USER,
                {"User-Agent": "Mozilla/5.0"})
    match = re.search(r"([\d,]+)\s+contributions", html)
    langs = {}
    for r in repos:
        if not r["fork"] and r["language"]:
            langs[r["language"]] = langs.get(r["language"], 0) + 1
    return {
        "contributions": int(match.group(1).replace(",", "")) if match else 0,
        "stars": sum(r["stargazers_count"] for r in repos),
        "followers": profile["followers"],
        "repos": profile["public_repos"],
        "langs": langs,
    }


def render(stats):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    top = sorted(stats["langs"].items(), key=lambda kv: -kv[1])[:5]
    total_repos_with_lang = sum(stats["langs"].values()) or 1

    svg = []
    svg.append(
        '<svg viewBox="0 0 880 300" width="880" height="300" '
        'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="github stats">')
    svg.append(
        "<style>text { font-family: 'Cascadia Code', 'Fira Code', Consolas, "
        "'DejaVu Sans Mono', monospace; } .bar { font-size: 11px; fill: #484f58; } "
        ".num { font-size: 38px; font-weight: bold; fill: #e6edf3; } "
        ".lbl { font-size: 11px; fill: #8b949e; letter-spacing: 2px; } "
        ".leg { font-size: 12px; fill: #8b949e; }</style>")
    svg.append('<rect x="0.5" y="0.5" width="879" height="299" rx="6" fill="#0d1117" stroke="#30363d"/>')
    svg.append('<path d="M 0.5 6.5 a 6 6 0 0 1 6 -6 h 867 a 6 6 0 0 1 6 6 v 25.5 h -879 z" fill="#161b22"/>')
    for cx in (22, 42, 62):
        svg.append('<circle cx="%d" cy="16" r="5" fill="#30363d"/>' % cx)
    svg.append('<text x="440" y="21" text-anchor="middle" class="bar">$ ./stats --render --daily</text>')
    svg.append('<text x="856" y="21" text-anchor="end" class="bar">synced %s</text>' % today)

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
        widths = [max(10, round(816 * count / total_repos_with_lang)) for _, count in top]
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
            pct = round(100 * count / total_repos_with_lang)
            svg.append('<rect x="%d" y="238" width="10" height="10" rx="2" fill="%s"/>' % (x, GREENS[i]))
            svg.append('<text x="%d" y="247" class="leg">%s %d%%</text>' % (x + 16, name.lower(), pct))
            x += 160

    svg.append('<text x="32" y="282" class="bar">generated by scripts/generate_stats.py in this repo, '
               'refreshed daily by github actions, zero third-party card services</text>')
    svg.append('</svg>')
    return "\n".join(svg) + "\n"


def main():
    token = os.environ.get("GITHUB_TOKEN")
    stats = fetch_graphql(token) if token else fetch_rest()
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(render(stats))
    print("stats-panel.svg written:", {k: v for k, v in stats.items() if k != "langs"})
    print("languages:", stats["langs"])


if __name__ == "__main__":
    main()
