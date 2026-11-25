"""Regenerate dark_mode.svg / light_mode.svg with live GitHub stats.

Runs daily via GitHub Actions (.github/workflows/update.yml). Stdlib only.
Edit the PROFILE block below to change what the card says.
"""
import calendar
import html
import json
import os
import urllib.request
from datetime import date, datetime, timezone

USER = "saybbbb"
JOINED_YEAR = 2023  # GitHub account creation year (commit count starts here)

# "Uptime" counts from this date. It is your GitHub join date by default;
# swap in your birthday (e.g. date(2003, 5, 17)) if you'd rather show your age.
UPTIME_FROM = date(2023, 11, 27)

# ---- Edit me -----------------------------------------------------------------
# Each section is (title, [(key, value), ...]). A value of None hides the row.
# Keep each "key + value" under ~50 characters so the dots line up.
PROFILE = [
    ("", [
        ("OS", "Windows 11"),
        ("Uptime", "__UPTIME__"),          # filled in automatically
        ("Host", "USTP CDO"),
        ("Kernel", "BS Information Technology"),
        ("Build", "4th Year"),
        ("IDE", "VSCode, Antigravity, Android Studio"),
    ]),
    ("", [
        ("Languages.Programming", "Kotlin, Python"),
        ("Currently.Learning", "Jetpack Compose, ML"),
        ("Hobbies", "Gaming"),
    ]),
    ("Projects", [
        ("Featured", "DATAra (Android + ML)"),
        ("Open.To", "Internships, Hackathons"),
    ]),
    ("Contact", [
        ("GitHub", "github.com/saybbbb"),
        ("Email", None),
        ("LinkedIn", None),
    ]),
]
# -----------------------------------------------------------------------------

W = 56           # info column width in characters
ART_LINE_H = 14  # px between ASCII-art rows

ART = r"""
                               ..:----======++
                                .::----======+
                                 .::-----====+
                                   .:-----===+
                         -=-        .:--======
                       #@@@@@@       .:---====
                      %@%@@@@@#      ..:---===
                      =%@%@@@%        ..::---=
                        %%%%%%=        .:::---
                        .#%%@%@@%*-    ..::--=
                          -%%@@@@@@%.  ..::--=
                       .  -#%%@@@@@@%..:::----
                       =:=++#@@@@@@@@: ::::---
                       ==++*%@@@@@@@@+-:.::---
                       +=++#%%@@@@@@@%#*+--:--
                       =+*%@@%@@@@@@@%####*+--
                        *#%%@@@@@%@@@%######*+
                        +##%%%@@@#%@%######***
                       *#%%%%@@@@#%%######****
                     :%#@@@@@@@@@%%%#%####****
                     @@%@@@@@@@@%%@%#####*****
                    #@@@@@@@@@@@+*%#####****++
                   .@@@@@@@@@@@@*%%#####****++
                   -@@@@@@@@@@@@@@@%####****++
                   -@@@@@@@@@@@@@@%%%*##****++
           ......  -@@@@@@@@@@@%%@@@@%%##*****
         ...:...  .:#@@@@@@%@@@#+%@@@@@%###***
            .     ::-%@@@@#-#@#+%@@@@@@%###***
                  .::=@@@@**%@-*@@@@@@@%*#****
--::::... ..     ...:.=%@@@@@@%@@@@@@@%#******
 ..:-------======+===+=*%@@@@@@@@@@@%###******
                      ..:%@@@@@@@@@@%%%%%#####
                        :%@@@@@@@@%%%%%%%%%%%%
                        *@@@@@@@@@%###########
                       #@@@@@@@@@%####********
                       ====--=+*#*************
                               =++++++++******
"""

# GITHUB_TOKEN (from Actions) counts private contributions in the commit total;
# ACCESS_TOKEN (optional PAT secret) lets the repo list and LOC walk see private repos.
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("ACCESS_TOKEN") or ""
PRIV_TOKEN = os.environ.get("ACCESS_TOKEN") or TOKEN


def gh(url, payload=None, token=None):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode() if payload else None,
        headers={"Authorization": f"Bearer {token or TOKEN}", "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read() or "{}")


def graphql(query, variables=None, token=None):
    resp = gh("https://api.github.com/graphql", {"query": query, "variables": variables or {}}, token)
    if resp.get("errors"):
        raise RuntimeError(resp["errors"])
    return resp["data"]


def elapsed(start, today):
    """(years, months, days) between two dates, calendar-correct."""
    years = today.year - start.year - ((today.month, today.day) < (start.month, start.day))
    months = (today.month - start.month - (today.day < start.day)) % 12
    if today.day >= start.day:
        days = today.day - start.day
    else:
        py, pm = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
        days = calendar.monthrange(py, pm)[1] - start.day + today.day
    return years, months, days


def fetch_stats():
    years = range(JOINED_YEAR, datetime.now(timezone.utc).year + 1)
    aliases = "\n".join(
        f'y{y}: contributionsCollection(from: "{y}-01-01T00:00:00Z", to: "{y + 1}-01-01T00:00:00Z")'
        " { totalCommitContributions restrictedContributionsCount }"
        for y in years
    )
    contrib = graphql(f'query {{ user(login: "{USER}") {{ {aliases} }} }}')["user"]
    commits = sum(v["totalCommitContributions"] + v["restrictedContributionsCount"] for v in contrib.values())

    u = graphql(f"""
    query {{
      user(login: "{USER}") {{
        id
        followers {{ totalCount }}
        repositories(first: 100, ownerAffiliations: OWNER) {{
          totalCount
          nodes {{ name stargazerCount isFork }}
        }}
        repositoriesContributedTo(first: 1, contributionTypes: [COMMIT, PULL_REQUEST, REPOSITORY]) {{
          totalCount
        }}
      }}
    }}""", token=PRIV_TOKEN)["user"]
    stats = {
        "followers": u["followers"]["totalCount"],
        "repos": u["repositories"]["totalCount"],
        "contributed": u["repositoriesContributedTo"]["totalCount"],
        "stars": sum(n["stargazerCount"] for n in u["repositories"]["nodes"]),
        "commits": commits,
    }
    own = [n["name"] for n in u["repositories"]["nodes"] if not n["isFork"]]
    stats.update(lines_of_code(own, u["id"]))
    return stats


LOC_QUERY = """
query($owner: String!, $name: String!, $id: ID!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    defaultBranchRef { target { ... on Commit {
      history(first: 100, author: {id: $id}, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes { additions deletions }
      }
    } } }
  }
}"""


def lines_of_code(repo_names, user_id):
    # Walk your own commits on each default branch; the REST contributor-stats
    # endpoint tends to return 202 indefinitely for Actions tokens.
    add = rem = 0
    for name in repo_names:
        cursor = None
        try:
            while True:
                repo = graphql(LOC_QUERY, {"owner": USER, "name": name, "id": user_id, "cursor": cursor},
                               token=PRIV_TOKEN)["repository"]
                ref = repo["defaultBranchRef"]
                if ref is None:
                    break  # empty repo
                h = ref["target"]["history"]
                add += sum(n["additions"] for n in h["nodes"])
                rem += sum(n["deletions"] for n in h["nodes"])
                if not h["pageInfo"]["hasNextPage"]:
                    break
                cursor = h["pageInfo"]["endCursor"]
        except Exception as e:
            print(f"loc {name}: {e}")
    return {"loc_add": add, "loc_del": rem, "loc": add - rem}


PALETTES = {
    "dark": {"bg": "#0d1117", "border": "#30363d", "art": "#8b949e", "h": "#58a6ff",
             "k": "#ffa657", "v": "#c9d1d9", "d": "#484f58", "g": "#3fb950", "r": "#f85149"},
    "light": {"bg": "#ffffff", "border": "#d0d7de", "art": "#57606a", "h": "#0969da",
              "k": "#953800", "v": "#24292f", "d": "#afb8c1", "g": "#1a7f37", "r": "#cf222e"},
}


def kv(key, val, width=W):
    dots = "." * max(width - len(key) - len(str(val)) - 3, 1)
    return [(f"{key}: ", "k"), (dots + " ", "d"), (str(val), "v")]


def kv2(k1, v1, k2, v2):
    return kv(k1, v1, 30) + [(" | ", "d")] + kv(k2, v2, 23)


def rule(title=""):
    label = f"─ {title} " if title else ""
    return [(label, "h"), ("─" * (W - len(label)), "d")]


def info_lines(s):
    y, m, d = elapsed(UPTIME_FROM, date.today())
    uptime = f"{y} years, {m} months, {d} days"
    n = lambda x: f"{x:,}"
    lines = [[(f"{USER.lower()}@github ", "h"), ("─" * (W - len(USER) - 8), "d")]]
    for title, rows in PROFILE:
        rows = [(k, uptime if v == "__UPTIME__" else v) for k, v in rows if v is not None]
        if not rows:
            continue
        lines.append([])
        if title:
            lines.append(rule(title))
        lines += [kv(k, v) for k, v in rows]
    lines += [
        [],
        rule("GitHub Stats"),
        kv2("Repos", f"{s['repos']} {{Contributed: {s['contributed']}}}", "Stars", n(s["stars"])),
        kv2("Commits", n(s["commits"]), "Followers", n(s["followers"])),
        [("Lines of Code: ", "k"), (n(s["loc"]), "v"), (" ( ", "d"),
         (n(s["loc_add"]) + "++", "g"), (", ", "d"), (n(s["loc_del"]) + "--", "r"), (" )", "d")],
    ]
    return lines


def render(mode, stats):
    p = PALETTES[mode]
    art = ART.strip("\n").split("\n")
    info = info_lines(stats)
    height = max(40 + len(art) * ART_LINE_H, 45 + len(info) * 21) + 20
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="840" height="{height}" viewBox="0 0 840 {height}" '
        'font-family="Consolas, Menlo, monospace" font-size="13px">',
        f'<rect x="0.5" y="0.5" width="839" height="{height - 1}" rx="10" fill="{p["bg"]}" stroke="{p["border"]}"/>',
    ]
    for i, line in enumerate(art):
        out.append(f'<text x="25" y="{40 + i * ART_LINE_H}" fill="{p["art"]}" xml:space="preserve">'
                   f'{html.escape(line)}</text>')
    for i, segs in enumerate(info):
        if segs:
            spans = "".join(f'<tspan fill="{p[c]}">{html.escape(t)}</tspan>' for t, c in segs)
            out.append(f'<text x="390" y="{45 + i * 21}" xml:space="preserve">{spans}</text>')
    out.append("</svg>")
    return "\n".join(out)


def selfcheck():
    assert elapsed(date(2000, 3, 31), date(2026, 4, 1)) == (26, 0, 1)
    assert elapsed(date(2000, 1, 1), date(2026, 1, 1)) == (26, 0, 0)
    assert len("".join(t for t, _ in kv("OS", "Windows 11"))) == W


if __name__ == "__main__":
    selfcheck()
    stats = fetch_stats()
    print("stats:", stats)
    for mode in PALETTES:
        with open(f"{mode}_mode.svg", "w", encoding="utf-8") as f:
            f.write(render(mode, stats))
    print("wrote dark_mode.svg, light_mode.svg")
