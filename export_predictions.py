"""Export today's XGBoost predictions to predictions.json for the dashboard.

Put this file in the repo root (next to main.py) and run:
    python3 export_predictions.py -odds=fanduel

It reuses the repo's own functions, so nothing in the repo needs to change.
If something fails, the previous predictions.json is left untouched.
"""
import argparse
import json
import sys
from datetime import datetime

import numpy as np

from main import DATA_URL, create_todays_games_data, load_schedule, resolve_games
from src.DataProviders.SbrOddsProvider import SbrOddsProvider
from src.Predict import XGBoost_Runner as runner
from src.Utils.Dictionaries import team_index_current
from src.Utils.tools import get_json_data, to_data_frame


def write(path, payload):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"Wrote {len(payload['games'])} games to {path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-odds", required=True, help="fanduel, draftkings, betmgm, ...")
    parser.add_argument("-out", default="predictions.json")
    args = parser.parse_args()

    now = datetime.now()
    header = {
        "date": f"{now.strftime('%A, %B')} {now.day}, {now.year}",
        "generated": now.isoformat(timespec="seconds"),
        "sportsbook": args.odds,
    }

    odds = SbrOddsProvider(sportsbook=args.odds).get_odds()
    games, odds = resolve_games(odds, args.odds)

    if games is None:  # no games today
        write(args.out, {**header, "games": []})
        return 0
    if odds is None:  # team list out of date, so don't publish bad data
        print("Odds did not match the team list. Keeping the previous file.")
        return 1

    # main.py silently skips unknown teams, so mirror that to keep rows aligned.
    games = [g for g in games if g[0] in team_index_current and g[1] in team_index_current]
    if not games:
        write(args.out, {**header, "games": []})
        return 0

    df = to_data_frame(get_json_data(DATA_URL))
    data, totals, frame_ml, home_odds, away_odds = create_todays_games_data(
        games, df, odds, load_schedule(), now
    )

    runner._load_models()
    ml = runner._predict_probs(runner.xgb_ml, data, runner.xgb_ml_calibrator)
    frame_uo = frame_ml.copy()
    frame_uo["OU"] = np.asarray(totals, dtype=float)
    ou = runner._predict_probs(runner.xgb_uo, frame_uo.values.astype(float), runner.xgb_uo_calibrator)

    out = []
    for i, (home, away) in enumerate(games):
        if not home_odds[i] or not away_odds[i]:
            continue  # no moneyline posted yet
        out.append({
            "away": away,
            "home": home,
            "time": "",
            "mlAway": int(away_odds[i]),
            "mlHome": int(home_odds[i]),
            "pHome": round(float(ml[i][1]), 4),   # class 1 = home win, as in XGBoost_Runner
            "total": float(totals[i]),
            "pOver": round(float(ou[i][1]), 4),   # class 1 = over, as in XGBoost_Runner
        })

    write(args.out, {**header, "games": out})
    return 0


if __name__ == "__main__":
    sys.exit(main())
