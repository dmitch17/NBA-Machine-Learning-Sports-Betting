"""Build Data/nba-2026-UTC.csv, the schedule main.py reads for days-rest.

Source: the free NBA fixtures feed at https://sporting-events.org/data/nba/
(CSV at /data/nba.csv). Their terms ask that published projects credit them
with a link, which the site footer does.

Run from the repo root:
    python3 make_schedule.py              # downloads the feed
    python3 make_schedule.py nba.csv      # or use a CSV you downloaded by hand

Team names are matched to the repo's own spelling (for example "LA Clippers"
vs "Los Angeles Clippers") using src.Utils.Dictionaries.team_index_current.
"""
import csv
import io
import sys
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

URL = "https://sporting-events.org/data/nba.csv"
OUT = Path("Data/nba-2026-UTC.csv")


def nick(name):
    return name.strip().split()[-1].lower()   # "Trail Blazers" -> "blazers"


def repo_names():
    try:
        from src.Utils.Dictionaries import team_index_current
        return {nick(k): k for k in team_index_current}
    except Exception as err:
        print(f"Warning: could not read the repo's team names ({err}). Using names as published.")
        return {}


def pick(row, *keys):
    for k in keys:
        v = row.get(k)
        if v and v.strip():
            return v.strip()
    return ""


def teams_from_fixture(fixture):
    if " at " in fixture:                      # "Away Team at Home Team"
        away, home = fixture.split(" at ", 1)
        return home.strip(), away.strip()
    return "", ""


def read_text():
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).read_text(encoding="utf-8-sig")
    req = Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8-sig")


def main():
    try:
        text = read_text()
    except Exception as err:
        print(f"Could not get the schedule: {err}")
        return 0 if OUT.exists() else 1        # keep the old file if we have one

    names = repo_names()
    unmatched, rows = set(), []
    for raw in csv.DictReader(io.StringIO(text)):
        row = {(k or "").strip().lower(): v for k, v in raw.items()}
        home, away = pick(row, "home_team"), pick(row, "away_team")
        if not (home and away):
            home, away = teams_from_fixture(pick(row, "fixture", "title", "name"))
        if not (home and away) or pick(row, "status").lower() == "cancelled":
            continue                           # skips non-game rows like "Season Tip-Off"

        time = pick(row, "time_utc", "time")
        time = time[:5] if time[:1].isdigit() else "00:00"
        try:
            when = datetime.strptime(f"{pick(row, 'date_utc', 'date')} {time}", "%Y-%m-%d %H:%M")
        except ValueError:
            continue

        if names:
            for name in (home, away):
                if nick(name) not in names:
                    unmatched.add(name)
            home, away = names.get(nick(home), home), names.get(nick(away), away)
        rows.append((when, home, away))

    if not rows:
        print("No games found in the schedule feed. Keeping any existing file.")
        return 0 if OUT.exists() else 1

    rows.sort()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Date", "Home Team", "Away Team"])
        for when, home, away in rows:
            w.writerow([when.strftime("%d/%m/%Y %H:%M"), home, away])

    print(f"Wrote {len(rows)} games to {OUT}")
    if unmatched:
        print("Names not found in the repo's team list: " + ", ".join(sorted(unmatched)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
