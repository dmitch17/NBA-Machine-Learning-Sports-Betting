"""Log today's moneyline picks, grade past picks, and add a `results` list to predictions.json.

Run from the repo root AFTER export_predictions.py:
    python3 log_results.py

Files:
  predictions.json  read for today's games, then rewritten with a `results` list
  pick_log.json     permanent record of every logged pick (commit this file)

A pick is logged when the model's edge over the vig-free market line is at least MIN_EDGE.
Final scores come from ESPN's public scoreboard feed (unofficial, no key needed).
"""
import json
import sys
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

MIN_EDGE = 0.02          # same 2% threshold the dashboard highlights
RESULTS_SHOWN = 15
PRED, LOG = Path("predictions.json"), Path("pick_log.json")
ESPN = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={d}"


def implied(odds):
    return -odds / (-odds + 100) if odds < 0 else 100 / (odds + 100)


def payout(odds):
    return odds / 100 if odds > 0 else 100 / -odds


def nick(name):
    """'Los Angeles Clippers' and 'LA Clippers' both become 'clippers'."""
    return name.strip().split()[-1].lower()


def choose_pick(g):
    a, h = implied(g["mlAway"]), implied(g["mlHome"])
    total = a + h
    m_away, m_home = a / total, h / total
    p_home = g["pHome"]
    e_home, e_away = p_home - m_home, (1 - p_home) - m_away
    if e_home >= e_away:
        return dict(side="home", team=g["home"], odds=g["mlHome"],
                    modelProb=p_home, marketProb=m_home, edge=e_home)
    return dict(side="away", team=g["away"], odds=g["mlAway"],
                modelProb=1 - p_home, marketProb=m_away, edge=e_away)


def fetch_winners(date_iso):
    """Return {(home_nick, away_nick): 'home' | 'away'} for finished games on a date."""
    url = ESPN.format(d=date_iso.replace("-", ""))
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=20) as resp:
        data = json.load(resp)
    winners = {}
    for ev in data.get("events", []):
        comp = ev["competitions"][0]
        if not comp["status"]["type"]["completed"]:
            continue
        side = {c["homeAway"]: c for c in comp["competitors"]}
        h, a = side["home"], side["away"]
        key = (nick(h["team"]["displayName"]), nick(a["team"]["displayName"]))
        winners[key] = "home" if int(h["score"]) > int(a["score"]) else "away"
    return winners


def load(path, default):
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def label(date_iso):
    d = datetime.strptime(date_iso, "%Y-%m-%d")
    return f"{d.strftime('%b')} {d.day}"


def main():
    pred = load(PRED, {})
    log = load(LOG, [])
    today = (pred.get("generated") or datetime.now().isoformat())[:10]

    # 1. Log today's picks (skips any already logged, so reruns are safe).
    known = {p["id"] for p in log}
    added = 0
    for g in pred.get("games", []):
        pick = choose_pick(g)
        pid = f"{today}|{g['home']}|{g['away']}"
        if pick["edge"] < MIN_EDGE or pid in known:
            continue
        pick = {k: round(v, 4) if isinstance(v, float) else v for k, v in pick.items()}
        log.append({"id": pid, "date": today, "home": g["home"], "away": g["away"],
                    **pick, "status": "pending"})
        added += 1

    # 2. Grade pending picks from earlier days.
    graded = 0
    pending_dates = sorted({p["date"] for p in log if p["status"] == "pending" and p["date"] < today})
    for date_iso in pending_dates:
        try:
            winners = fetch_winners(date_iso)
        except Exception as err:  # network or format problem: try again next run
            print(f"Could not fetch scores for {date_iso}: {err}")
            continue
        for p in log:
            if p["status"] != "pending" or p["date"] != date_iso:
                continue
            winner = winners.get((nick(p["home"]), nick(p["away"])))
            if winner:
                p["status"] = "win" if winner == p["side"] else "loss"
                graded += 1

    # 3. Publish the most recent graded picks for the dashboard.
    done = [p for p in log if p["status"] in ("win", "loss")]
    done.sort(key=lambda p: p["date"], reverse=True)
    results = [{"date": label(p["date"]), "pick": f"{p['team']} ML",
                "odds": int(p["odds"]), "won": p["status"] == "win"}
               for p in done[:RESULTS_SHOWN]]

    with open(LOG, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2)
    if PRED.exists():
        pred["results"] = results
        with open(PRED, "w", encoding="utf-8") as f:
            json.dump(pred, f, indent=2)

    still = sum(1 for p in log if p["status"] == "pending")
    print(f"Logged {added} new picks, graded {graded}, {still} pending, {len(results)} results published.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
