from flask import Flask, render_template, jsonify
import requests
import math
from datetime import datetime, date, timedelta

app = Flask(__name__)

FOOTBALL_DATA_KEY = "6b3ad23286124bc6affb698571a8b6ee"
ODDS_API_KEY      = "d179295063079a663e8fb6a681ace849"

LEAGUES = {
    "PL":  {"name": "Premier League",  "flag": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "odds_key": "soccer_epl"},
    "FL1": {"name": "Ligue 1",         "flag": "🇫🇷",       "odds_key": "soccer_france_ligue_one"},
    "PD":  {"name": "La Liga",         "flag": "🇪🇸",       "odds_key": "soccer_spain_la_liga"},
    "SA":  {"name": "Serie A",         "flag": "🇮🇹",       "odds_key": "soccer_italy_serie_a"},
    "BL1": {"name": "Bundesliga",      "flag": "🇩🇪",       "odds_key": "soccer_germany_bundesliga"},
    "CL":  {"name": "Champions League","flag": "⭐",        "odds_key": "soccer_uefa_champs_league"},
    "ELC": {"name": "Championship",    "flag": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "odds_key": "soccer_england_league2"},
    "PPL": {"name": "Primeira Liga",   "flag": "🇵🇹",       "odds_key": "soccer_portugal_primeira_liga"},
}

def poisson(lam, k):
    return (math.exp(-lam) * lam**k) / math.factorial(k)

def score_matrix(xg_h, xg_a, n=6):
    scores = []
    for i in range(n+1):
        for j in range(n+1):
            p = poisson(xg_h, i) * poisson(xg_a, j)
            scores.append({"score": f"{i}-{j}", "h": i, "a": j, "prob": round(p*100, 2)})
    return sorted(scores, key=lambda x: x["prob"], reverse=True)

def calc_xg(goals_for, goals_against, n_matches, avg=1.35):
    if n_matches == 0:
        return avg, avg
    att = (goals_for / n_matches) / avg
    deff = (goals_against / n_matches) / avg
    return att, deff

def get_team_stats(team_id, n=10):
    url = f"https://api.football-data.org/v4/teams/{team_id}/matches"
    params = {"status": "FINISHED", "limit": n}
    headers = {"X-Auth-Token": FOOTBALL_DATA_KEY}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=8)
        matches = r.json().get("matches", [])
        gf = ga = 0
        for m in matches:
            home = m["homeTeam"]["id"] == team_id
            s = m["score"]["fullTime"]
            if home:
                gf += s["home"] or 0
                ga += s["away"] or 0
            else:
                gf += s["away"] or 0
                ga += s["home"] or 0
        return gf, ga, len(matches)
    except:
        return 0, 0, 0

def get_todays_matches():
    today = date.today()
    date_from = today.isoformat()
    date_to = (today + timedelta(days=1)).isoformat()
    headers = {"X-Auth-Token": FOOTBALL_DATA_KEY}
    all_matches = []
    errors = []
    for code, info in LEAGUES.items():
        url = f"https://api.football-data.org/v4/competitions/{code}/matches"
        params = {"dateFrom": date_from, "dateTo": date_to, "status": "SCHEDULED,TIMED"}
        try:
            r = requests.get(url, headers=headers, params=params, timeout=10)
            data = r.json()
            if "error" in data or "errorCode" in data:
                errors.append(f"{code}: {data.get('message','unknown error')}")
                continue
            for m in data.get("matches", []):
                all_matches.append({
                    "id": m["id"],
                    "league": info["name"],
                    "flag": info["flag"],
                    "league_code": code,
                    "home": m["homeTeam"]["name"],
                    "home_id": m["homeTeam"]["id"],
                    "away": m["awayTeam"]["name"],
                    "away_id": m["awayTeam"]["id"],
                    "time": m["utcDate"][11:16],
                    "odds_key": info["odds_key"]
                })
        except Exception as e:
            errors.append(f"{code}: {str(e)}")
            continue
    return all_matches, errors

def get_exact_score_odds(sport_key, home_team, away_team):
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "eu",
        "markets": "h2h",
        "oddsFormat": "decimal"
    }
    try:
        r = requests.get(url, params=params, timeout=8)
        games = r.json()
        for g in games:
            if home_team.lower() in g.get("home_team","").lower() or \
               away_team.lower() in g.get("home_team","").lower():
                for bm in g.get("bookmakers", []):
                    for mkt in bm.get("markets", []):
                        if mkt["key"] == "h2h":
                            odds = {o["name"]: o["price"] for o in mkt["outcomes"]}
                            return odds
    except:
        pass
    return {}

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/debug")
def debug():
    headers = {"X-Auth-Token": FOOTBALL_DATA_KEY}
    today = date.today()
    results = {}
    for code in LEAGUES:
        url = f"https://api.football-data.org/v4/competitions/{code}/matches"
        params = {"dateFrom": today.isoformat(), "dateTo": (today + timedelta(days=2)).isoformat()}
        try:
            r = requests.get(url, headers=headers, params=params, timeout=10)
            data = r.json()
            count = len(data.get("matches", []))
            results[code] = {"status": r.status_code, "matches": count, "error": data.get("message")}
        except Exception as e:
            results[code] = {"error": str(e)}
    return jsonify(results)

@app.route("/api/matches")
def api_matches():
    matches, errors = get_todays_matches()
    results = []
    for m in matches:
        gf_h, ga_h, n_h = get_team_stats(m["home_id"])
        gf_a, ga_a, n_a = get_team_stats(m["away_id"])
        avg = 1.35
        att_h, def_h = calc_xg(gf_h, ga_h, n_h)
        att_a, def_a = calc_xg(gf_a, ga_a, n_a)
        xg_h = round(att_h * def_a * avg, 2)
        xg_a = round(att_a * def_h * avg, 2)
        top_scores = score_matrix(xg_h, xg_a)[:8]
        h2h_odds = get_exact_score_odds(m["odds_key"], m["home"], m["away"])
        value_bets = []
        prob_home = sum(s["prob"] for s in score_matrix(xg_h, xg_a) if s["h"] > s["a"])
        prob_draw = sum(s["prob"] for s in score_matrix(xg_h, xg_a) if s["h"] == s["a"])
        prob_away = sum(s["prob"] for s in score_matrix(xg_h, xg_a) if s["h"] < s["a"])
        for label, prob, key in [
            (m["home"], prob_home, m["home"]),
            ("Draw", prob_draw, "Draw"),
            (m["away"], prob_away, m["away"])
        ]:
            cote = h2h_odds.get(key)
            if cote:
                ev = round((prob/100) * cote - 1, 3)
                if ev > 0:
                    value_bets.append({
                        "label": label,
                        "prob": round(prob, 1),
                        "cote": cote,
                        "ev": ev
                    })
        results.append({
            **m,
            "xg_h": xg_h,
            "xg_a": xg_a,
            "top_scores": top_scores,
            "h2h_odds": h2h_odds,
            "value_bets": value_bets,
            "prob_home": round(prob_home, 1),
            "prob_draw": round(prob_draw, 1),
            "prob_away": round(prob_away, 1),
        })
    return jsonify({"matches": results, "date": date.today().isoformat(), "errors": errors})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
