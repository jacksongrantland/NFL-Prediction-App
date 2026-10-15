"""Explicit source-to-canonical mappings and validation, without feature engineering."""

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

NORMALIZER_VERSION = "normalized/1"
TEAM_CODES = set(
    "ARI ATL BAL BUF CAR CHI CIN CLE DAL DEN DET GB HOU IND JAX KC LAC LAR LV "
    "MIA MIN NE NO NYG NYJ PHI PIT SEA SF TB TEN WAS".split()
)
TEAM_ALIASES = {"LA": "LAR", "JAC": "JAX", "WSH": "WAS"}
GAME_TYPES = {
    "REG": "REG",
    "POST": "POST",
    "WC": "POST",
    "DIV": "POST",
    "CON": "POST",
    "SB": "POST",
    "PRE": "PRE",
}
COUNT_STATS = (
    "completions",
    "attempts",
    "passing_tds",
    "passing_interceptions",
    "sacks_suffered",
    "carries",
    "rushing_tds",
    "targets",
    "receptions",
    "receiving_tds",
)
YARD_STATS = ("passing_yards", "sack_yards_lost", "rushing_yards", "receiving_yards")
PBP_COUNTS = (
    "pass_attempt",
    "complete_pass",
    "rush_attempt",
    "pass_touchdown",
    "rush_touchdown",
    "interception",
    "fumble_lost",
    "sack",
)
PBP_YARDS = ("yards_gained", "passing_yards", "rushing_yards", "receiving_yards")
PBP_IDS = ("passer_player_id", "rusher_player_id", "receiver_player_id")
SCHEDULE_COLUMNS = (
    "game_id",
    "season",
    "week",
    "game_type",
    "gameday",
    "gametime",
    "home_team",
    "away_team",
    "home_score",
    "away_score",
)
SOURCE_COLUMNS = {
    "games": SCHEDULE_COLUMNS,
    "player_stats": (
        "player_id",
        "game_id",
        "season",
        "week",
        "season_type",
        "team",
        "opponent_team",
        "position",
        *COUNT_STATS,
        *YARD_STATS,
    ),
    "team_stats": (
        "game_id",
        "season",
        "week",
        "season_type",
        "team",
        "opponent_team",
        *COUNT_STATS,
        *YARD_STATS,
    ),
    "rosters": (
        "season",
        "week",
        "game_type",
        "team",
        "gsis_id",
        "pfr_id",
        "position",
        "status",
        "full_name",
    ),
    "weekly_rosters": (
        "season",
        "week",
        "game_type",
        "team",
        "gsis_id",
        "pfr_id",
        "position",
        "status",
        "full_name",
    ),
    "plays": (
        "game_id",
        "play_id",
        "season",
        "week",
        "season_type",
        "posteam",
        "defteam",
        "home_team",
        "away_team",
        "play_type_nfl",
        "game_seconds_remaining",
        "total_home_score",
        "total_away_score",
        *PBP_IDS,
        *PBP_COUNTS,
        *PBP_YARDS,
    ),
}


def read_source(path: Path, dataset: str) -> tuple[pd.DataFrame, list[str]]:
    required = list(SOURCE_COLUMNS[dataset])
    if dataset == "games":
        columns = list(pd.read_csv(path, nrows=0).columns)
        missing = set(required) - set(columns)
        if missing:
            raise ValueError(f"{dataset}: missing columns {sorted(missing)}")
        frame = pd.read_csv(path, usecols=required, dtype="string")
    else:
        source = pq.ParquetFile(path)
        columns = source.schema_arrow.names
        missing = set(required) - set(columns)
        if missing:
            raise ValueError(f"{dataset}: missing columns {sorted(missing)}")
        frame = source.read(columns=required).to_pandas()
    frame["source_row_number"] = range(1, len(frame) + 1)
    return frame, columns


def integers(frame: pd.DataFrame, columns: tuple[str, ...], dtype: str = "Int32") -> None:
    for column in columns:
        values = pd.to_numeric(frame[column], errors="raise")
        if ((values.dropna() % 1) != 0).any():
            raise ValueError(f"Nonintegral count/yardage: {column}")
        frame[column] = values.astype(dtype)


def teams(frame: pd.DataFrame, column: str, target: str) -> None:
    raw = frame[column].astype("string").str.strip().replace("", pd.NA)
    normalized = raw.replace(TEAM_ALIASES)
    unknown = set(normalized.dropna()) - TEAM_CODES
    if unknown:
        raise ValueError(f"Unknown team codes: {sorted(unknown)}")
    frame[f"source_{column}"] = raw
    frame[target] = normalized
    frame.drop(columns=column, inplace=True)


def normalize(
    raw: pd.DataFrame, dataset: str, season: int, manifest_id: str
) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    frame = raw.copy()
    for column in ("player_id", "gsis_id", "source_pfr_id", *PBP_IDS):
        if column in frame:
            frame[column] = frame[column].astype("string").str.strip().replace("", pd.NA)
    integers(frame, ("season", "week"), "Int16")
    if dataset != "games" and not frame["season"].eq(season).all():
        raise ValueError(f"{dataset}: wrong season in annual source")
    frame = frame.loc[frame.season.eq(season)].copy()
    if frame.empty:
        raise ValueError(f"{dataset}: no rows for {season}")
    raw_count = len(frame)
    frame["source_manifest_id"] = manifest_id
    frame["schema_version"] = NORMALIZER_VERSION
    type_column = "season_type" if "season_type" in frame else "game_type"
    source_type = frame[type_column].astype("string")
    if not source_type.dropna().isin(GAME_TYPES).all():
        raise ValueError(f"{dataset}: unknown game types")
    frame["source_game_type"] = source_type
    frame["game_type"] = source_type.map(GAME_TYPES).astype("string")
    frame["playoff_round"] = source_type.where(source_type.isin(("WC", "DIV", "CON", "SB")))
    if type_column == "season_type":
        frame.drop(columns="season_type", inplace=True)
    rejected = pd.DataFrame()
    if dataset in ("rosters", "weekly_rosters"):
        frame.rename(
            columns={"gsis_id": "player_id", "pfr_id": "source_pfr_id", "status": "roster_status"},
            inplace=True,
        )
        resolved = frame.player_id.str.fullmatch(r"\d{2}-\d{7}").fillna(False)
        rejected = frame.loc[~resolved].copy()
        if not rejected.empty:
            rejected["rejection_reason"] = "unresolved_gsis_id"
        frame = frame.loc[resolved].copy()
        teams(frame, "team", "team_id")
        keys = ["season", "week", "game_type", "player_id", "team_id"]
    elif dataset == "games":
        teams(frame, "home_team", "home_team_id")
        teams(frame, "away_team", "away_team_id")
        integers(frame, ("home_score", "away_score"), "Int16")
        if (frame[["home_score", "away_score"]] < 0).any().any():
            raise ValueError("Negative game score")
        if frame.home_score.isna().ne(frame.away_score.isna()).any():
            raise ValueError("Only one team has a recorded score")
        frame.rename(
            columns={"gameday": "source_gameday", "gametime": "source_gametime"}, inplace=True
        )
        date = pd.to_datetime(frame.source_gameday, format="%Y-%m-%d", errors="raise")
        time_text = frame.source_gametime.replace({"TBD": pd.NA})
        kickoff = pd.to_datetime(
            date.dt.strftime("%Y-%m-%d") + " " + time_text, format="%Y-%m-%d %H:%M", errors="raise"
        )
        frame["kickoff_at"] = kickoff.dt.tz_localize("America/New_York").dt.tz_convert("UTC")
        frame["source_gameday"] = date.dt.date
        frame["result_status"] = "unknown"
        frame.loc[frame.home_score.notna(), "result_status"] = "provisional"
        keys = ["game_id"]
    elif dataset == "plays":
        for source, target in (
            ("posteam", "possession_team_id"),
            ("defteam", "defense_team_id"),
            ("home_team", "home_team_id"),
            ("away_team", "away_team_id"),
        ):
            teams(frame, source, target)
        integers(frame, ("play_id",), "Int64")
        integers(frame, PBP_COUNTS + PBP_YARDS + ("total_home_score", "total_away_score"))
        frame["game_seconds_remaining"] = pd.to_numeric(frame.game_seconds_remaining)
        keys = ["game_id", "play_id"]
    else:
        teams(frame, "team", "team_id")
        teams(frame, "opponent_team", "opponent_team_id")
        integers(frame, COUNT_STATS + YARD_STATS)
        if (frame[list(COUNT_STATS)] < 0).any().any():
            raise ValueError(f"{dataset}: negative opportunity/scoring count")
        if frame.completions.gt(frame.attempts).any() or frame.receptions.gt(frame.targets).any():
            raise ValueError(f"{dataset}: invalid opportunity accounting")
        keys = ["game_id", "team_id"]
        if dataset == "player_stats":
            keys.append("player_id")
    if dataset == "player_stats":
        resolved = frame.player_id.str.fullmatch(r"\d{2}-\d{7}").fillna(False)
        rejected = frame.loc[~resolved].copy()
        if not rejected.empty:
            rejected["rejection_reason"] = "unresolved_gsis_id"
        frame = frame.loc[resolved].copy()
    if frame.empty:
        raise ValueError(f"{dataset}: no rows with usable identities")
    required_ids = [key for key in keys if key not in ("week", "game_type")]
    if frame[required_ids].isna().any().any():
        raise ValueError(f"{dataset}: missing required identity")
    if (
        "player_id" in frame
        and not frame.player_id.astype("string").str.fullmatch(r"\d{2}-\d{7}").all()
    ):
        raise ValueError(f"{dataset}: non-GSIS player ID")
    if (
        "game_id" in frame
        and not frame.game_id.astype("string")
        .str.fullmatch(r"\d{4}_\d{2}_[A-Z]{2,3}_[A-Z]{2,3}")
        .all()
    ):
        raise ValueError(f"{dataset}: malformed game ID")
    # Retain raw bytes and record dropped row numbers; exact duplicate removal
    # must never collapse different positions, teams, values, or statuses.
    compare = [column for column in frame if column != "source_row_number"]
    duplicates = frame.duplicated(compare)
    dropped = frame.loc[duplicates, "source_row_number"].astype(int).tolist()
    frame = frame.loc[~duplicates].copy()
    if frame.duplicated(keys).any():
        raise ValueError(f"{dataset}: conflicting duplicate candidate keys")
    frame.sort_values(keys, inplace=True, na_position="last")
    frame.reset_index(drop=True, inplace=True)
    summary = {
        "source_rows_for_season": raw_count,
        "rows": len(frame),
        "rejected_rows": len(rejected),
        "duplicate_rows_removed": len(dropped),
        "duplicate_source_row_numbers": dropped,
        "null_counts": {column: int(count) for column, count in frame.isna().sum().items()},
        "weeks": sorted(int(week) for week in frame.week.dropna().unique()),
        "game_types": sorted(frame.game_type.dropna().unique().tolist()),
    }
    team_columns = [c for c in ("team_id", "home_team_id", "away_team_id") if c in frame]
    summary["teams"] = sorted(set().union(*(set(frame[c].dropna()) for c in team_columns)))
    return frame, summary, rejected


def reconcile(frames: dict[str, pd.DataFrame]) -> dict:
    """Require terminal PBP evidence and matching scores, including walk-off OT."""
    games, plays = frames["games"], frames["plays"]
    indexed = games.set_index("game_id")
    terminals = plays.loc[plays.play_type_nfl.eq("END_GAME")].copy()
    if terminals.game_id.duplicated().any():
        raise ValueError("Multiple END_GAME rows for one game")
    final_ids = set()
    for row in terminals.itertuples():
        if row.game_id not in indexed.index:
            raise ValueError(f"PBP game absent from schedule: {row.game_id}")
        game = indexed.loc[row.game_id]
        if pd.isna(game.home_score) or pd.isna(game.away_score):
            raise ValueError(f"Completed PBP has missing schedule scores: {row.game_id}")
        if (row.total_home_score, row.total_away_score) != (game.home_score, game.away_score):
            raise ValueError(f"PBP/schedule score mismatch: {row.game_id}")
        if pd.isna(game.kickoff_at) or game.kickoff_at >= datetime.now(UTC):
            raise ValueError(f"Completed game has missing/future kickoff: {row.game_id}")
        final_ids.add(row.game_id)
    games["finality_evidence"] = pd.Series(pd.NA, index=games.index, dtype="string")
    mask = games.game_id.isin(final_ids)
    games.loc[mask, "result_status"] = "final"
    games.loc[mask, "finality_evidence"] = "pbp_end_game_and_matching_schedule_scores"
    if not final_ids:
        raise ValueError("No independently reconciled completed games")
    coverage = {
        "completed_games": len(final_ids),
        "scheduled_games": len(games),
        "scored_but_unfinalized_games": games.loc[
            games.home_score.notna() & ~games.game_id.isin(final_ids), "game_id"
        ].tolist(),
        "scheduled_without_results": int(games.home_score.isna().sum()),
        "unfinalized_rows_excluded": {},
    }
    for dataset in ("plays", "player_stats", "team_stats"):
        frame = frames[dataset]
        if not frame.game_id.isin(indexed.index).all():
            raise ValueError(f"{dataset}: game absent from schedule")
        context = frame.merge(
            games[["game_id", "season", "week", "game_type", "home_team_id", "away_team_id"]],
            on="game_id",
            suffixes=("", "_schedule"),
            validate="many_to_one",
        )
        context_columns = ["season", "week", "game_type"]
        if dataset == "plays":
            context_columns.extend(("home_team_id", "away_team_id"))
        for column in context_columns:
            if context[column].ne(context[column + "_schedule"]).any():
                raise ValueError(f"{dataset}: incorrect game context ({column})")
        if "team_id" in context:
            valid = (
                context.team_id.eq(context.home_team_id)
                & context.opponent_team_id.eq(context.away_team_id)
            ) | (
                context.team_id.eq(context.away_team_id)
                & context.opponent_team_id.eq(context.home_team_id)
            )
            if not valid.all():
                raise ValueError(f"{dataset}: teams do not match historical schedule")
        completed = frame.loc[frame.game_id.isin(final_ids)].copy()
        coverage["unfinalized_rows_excluded"][dataset] = len(frame) - len(completed)
        frames[dataset] = completed
    team_counts = frames["team_stats"].groupby("game_id").size()
    if set(team_counts.index) != final_ids or not team_counts.eq(2).all():
        raise ValueError("Completed games must have exactly two team-stat rows")
    if set(frames["player_stats"].game_id) != final_ids:
        raise ValueError("Completed game missing player-stat rows")
    if not frames["player_stats"].groupby("game_id").team_id.nunique().eq(2).all():
        raise ValueError("Completed games must have player statistics for both teams")
    return coverage
