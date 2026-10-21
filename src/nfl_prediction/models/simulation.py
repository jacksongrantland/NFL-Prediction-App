"""Seeded joint box-score approximation, governed by docs/simulation_contract.md."""

import numpy as np
import pandas as pd

from nfl_prediction.models.players import OPPORTUNITIES, RATES

STATS = list(OPPORTUNITIES) + list(RATES)


def weights(values):
    values = np.maximum(np.asarray(values, dtype=float), 0)
    return values / values.sum() if values.sum() else np.r_[np.zeros(len(values) - 1), 1.0]


def simulate(game: dict, players: pd.DataFrame, *, count: int = 500, seed: int = 2026) -> dict:
    if not 100 <= count <= 5000:
        raise ValueError("Simulation count must be between 100 and 5000")
    expected = np.array([game["home_expected"], game["away_expected"]], dtype=float)
    if not np.isfinite(expected).all() or (expected < 0).any():
        raise ValueError("Expected scores must be finite and nonnegative")
    rng = np.random.default_rng(seed)
    environment = rng.lognormal(-0.5 * 0.15**2, 0.15, count)
    team_draws, player_draws = [], []
    for side in ("home", "away"):
        team = game[f"{side}_team_id"]
        rows = players.loc[players.team_id.eq(team)].copy()
        rows = rows.loc[rows.offense_participation_probability.notna()]
        ids = rows.player_id.tolist() + ["other"]
        size = len(ids)
        values = {stat: np.zeros((count, size), dtype=float) for stat in STATS}
        if len(rows):
            volumes = rows.iloc[0].team_volume
            remaining = rows.iloc[0].other_opportunities
        else:
            raise ValueError(f"No supported player/team volume for {team}")
        probability = rows.offense_participation_probability.to_numpy(dtype=float)
        active = rng.random((count, len(rows))) < probability
        target_total = float(rows.unconditional_targets.sum())
        completion_rate = (
            float(rows.unconditional_receptions.sum()) / target_total if target_total > 0 else 0.65
        )
        completion_rate = float(np.clip(completion_rate, 0, 1))
        team_scores = []
        for draw in range(count):
            opportunities = {}
            allocations = {}
            for stat in OPPORTUNITIES:
                volume = max(0, float(volumes[stat]))
                opportunities[stat] = int(rng.poisson(volume * environment[draw]))
                if stat == "targets":
                    opportunities[stat] = min(opportunities[stat], opportunities["attempts"])
                raw = rows[f"conditional_{stat}"].fillna(0).to_numpy(dtype=float) * active[draw]
                # Unknown/omitted role work survives; sampled absences redistribute by weights.
                other = max(float(remaining[stat]), volume * 0.01)
                allocations[stat] = weights(np.r_[raw, other])
            attempts = opportunities["attempts"]
            targets = opportunities["targets"]
            carries = opportunities["carries"]
            completions = int(rng.binomial(targets, completion_rate))
            receiver_counts = rng.multinomial(completions, allocations["targets"])
            incomplete_targets = rng.multinomial(targets - completions, allocations["targets"])
            rush_counts = rng.multinomial(carries, allocations["carries"])
            # One passer per draw preserves team/player accounting, including backup scenarios.
            passer = int(rng.choice(size, p=allocations["attempts"]))
            yards, rush_yards = np.zeros(size), np.zeros(size)
            for index in range(size):
                if index < len(rows):
                    row = rows.iloc[index]
                    catches = float(row.conditional_receptions or 0)
                    rush = float(row.conditional_carries or 0)
                    receive_rate = (
                        float(row.conditional_receiving_yards or 0) / catches
                        if catches > 0
                        else 10.0
                    )
                    rush_rate = (
                        float(row.conditional_rushing_yards or 0) / rush if rush > 0 else 4.0
                    )
                else:
                    receive_rate, rush_rate = 10.0, 4.0
                # Signed aggregate production; no fabricated individual play realism.
                yards[index] = round(
                    rng.normal(
                        receiver_counts[index] * receive_rate, 8 * np.sqrt(receiver_counts[index])
                    )
                )
                rush_yards[index] = round(
                    rng.normal(rush_counts[index] * rush_rate, 4 * np.sqrt(rush_counts[index]))
                )
            raw_expected = float(game[f"{side}_expected"])
            base_td = max(0.05, (raw_expected - 6.0 - 0.7) / 7)
            td_scale = base_td / max(1, completions * 0.07 + carries * 0.03)
            receiving_td = rng.binomial(receiver_counts, min(0.5, 0.07 * td_scale))
            rushing_td = rng.binomial(rush_counts, min(0.5, 0.03 * td_scale))
            touchdowns = int(receiving_td.sum() + rushing_td.sum())
            dst_td = int(rng.poisson(0.1 * environment[draw]))
            touchdowns_all = touchdowns + dst_td
            two_attempts = int(rng.binomial(touchdowns_all, 0.03))
            two_made = int(rng.binomial(two_attempts, 0.48))
            extra_points = int(rng.binomial(touchdowns_all - two_attempts, 0.95))
            field_goals = int(rng.poisson(2.0 * environment[draw]))
            safeties = int(rng.binomial(1, 0.015))
            score = (
                6 * touchdowns_all + extra_points + 2 * two_made + 3 * field_goals + 2 * safeties
            )
            sacks = int(rng.poisson(0.065 * attempts))
            sack_yards = int(rng.poisson(7 * sacks))
            interceptions = int(rng.binomial(attempts - completions, 0.06))
            fumbles = int(rng.binomial(carries + completions + sacks, 0.015))
            lost = int(rng.binomial(fumbles, 0.5))
            values["attempts"][draw, passer] = attempts
            values["completions"][draw, passer] = completions
            values["passing_yards"][draw, passer] = yards.sum()
            values["passing_tds"][draw, passer] = receiving_td.sum()
            values["passing_interceptions"][draw, passer] = interceptions
            for stat, data in (
                ("targets", receiver_counts + incomplete_targets),
                ("receptions", receiver_counts),
                ("receiving_yards", yards),
                ("receiving_tds", receiving_td),
                ("carries", rush_counts),
                ("rushing_yards", rush_yards),
                ("rushing_tds", rushing_td),
            ):
                values[stat][draw] = data
            team_scores.append(
                {
                    "draw": draw,
                    "team_id": team,
                    "side": side,
                    "score": score,
                    "sacks_allowed": sacks,
                    "sack_yards": sack_yards,
                    "net_passing_yards": int(yards.sum()) - sack_yards,
                    "defense_st_tds": dst_td,
                    "field_goals": field_goals,
                    "extra_points": extra_points,
                    "two_point_attempts": two_attempts,
                    "two_point_made": two_made,
                    "safeties": safeties,
                    "fumbles": fumbles,
                    "fumbles_lost": lost,
                    "overtime_points": 0,
                }
            )
        team_draws.extend(team_scores)
        for index, player_id in enumerate(ids):
            for draw in range(count):
                player_draws.append(
                    {
                        "draw": draw,
                        "team_id": team,
                        "player_id": player_id,
                        "participated": bool(active[draw, index]) if index < len(rows) else True,
                        **{stat: int(values[stat][draw, index]) for stat in STATS},
                    }
                )
    teams = pd.DataFrame(team_draws)
    samples = pd.DataFrame(player_draws)
    home = teams.loc[teams.side.eq("home"), "score"].to_numpy()
    away = teams.loc[teams.side.eq("away"), "score"].to_numpy()
    # Approximate one extra opportunity. Playoffs cannot end tied.
    for draw in np.flatnonzero(home == away):
        if game.get("game_type") == "POST" or rng.random() < 0.9:
            side = "home" if rng.random() < expected[0] / max(expected.sum(), 1) else "away"
            index = teams.index[teams.draw.eq(draw) & teams.side.eq(side)][0]
            teams.loc[index, ["score", "field_goals", "overtime_points"]] += [3, 1, 3]
    home = teams.loc[teams.side.eq("home"), "score"].to_numpy()
    away = teams.loc[teams.side.eq("away"), "score"].to_numpy()
    for side, other in (("home", "away"), ("away", "home")):
        teams.loc[teams.side.eq(side), "defensive_sacks"] = teams.loc[
            teams.side.eq(other), "sacks_allowed"
        ].to_numpy()
    summary = {
        "game_id": game["game_id"],
        "seed": seed,
        "count": count,
        "accounting_version": "simulation/1",
        "forecast_type": "experimental_joint_preview",
        "recommended_for_decisions": False,
        "raw_home_expected": expected[0],
        "raw_away_expected": expected[1],
        "home_expected": float(home.mean()),
        "away_expected": float(away.mean()),
        "home_win": float((home > away).mean()),
        "tie": float((home == away).mean()),
        "away_win": float((home < away).mean()),
        "home_p10_p90": np.quantile(home, [0.1, 0.9]).tolist(),
        "away_p10_p90": np.quantile(away, [0.1, 0.9]).tolist(),
        "player_summaries": [],
    }
    for (team, player), group in samples.groupby(["team_id", "player_id"]):
        summary["player_summaries"].append(
            {
                "team_id": team,
                "player_id": player,
                "offense_participation_probability": float(group.participated.mean()),
                "active_conditional": {
                    stat: {
                        "mean": float(group.loc[group.participated, stat].mean()),
                        "p10": float(group.loc[group.participated, stat].quantile(0.1)),
                        "p90": float(group.loc[group.participated, stat].quantile(0.9)),
                    }
                    if group.participated.any()
                    else None
                    for stat in STATS
                },
                "stats": {
                    stat: {
                        "mean": float(group[stat].mean()),
                        "p10": float(group[stat].quantile(0.1)),
                        "p90": float(group[stat].quantile(0.9)),
                    }
                    for stat in STATS
                },
            }
        )
    return {"summary": summary, "teams": teams, "players": samples}


def validate(result: dict) -> None:
    """Reject broken accounting before writing an artifact."""
    players, teams = result["players"], result["teams"]
    totals = players.groupby(["draw", "team_id"])[STATS].sum().sort_index()
    team = teams.set_index(["draw", "team_id"]).sort_index()
    checks = [
        totals.completions.le(totals.attempts),
        totals.targets.le(totals.attempts),
        totals.receptions.eq(totals.completions),
        totals.receiving_yards.eq(totals.passing_yards),
        totals.receiving_tds.eq(totals.passing_tds),
        totals.receiving_tds.le(totals.receptions),
        totals.rushing_tds.le(totals.carries),
        totals.passing_interceptions.le(totals.attempts - totals.completions),
        team.net_passing_yards.eq(totals.passing_yards - team.sack_yards),
    ]
    score = (
        6 * (totals.passing_tds + totals.rushing_tds + team.defense_st_tds)
        + team.extra_points
        + 2 * team.two_point_made
        + 3 * team.field_goals
        + 2 * team.safeties
    )
    checks.append(score.eq(team.score))
    nonnegative = [s for s in STATS if not s.endswith("yards")]
    checks.append(players[nonnegative].ge(0).all(axis=1))
    checks.append(players.completions.le(players.attempts))
    checks.append(players.receptions.le(players.targets))
    if not all(check.all() for check in checks):
        raise ValueError("Joint football accounting constraint failed")
