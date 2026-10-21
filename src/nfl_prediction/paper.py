"""Paper-only arithmetic, immutable manual lines and conservative settlement policies."""

import json
from datetime import UTC, datetime, timedelta
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from typing import Literal
from uuid import uuid4

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import text

from nfl_prediction.data.ingest import json_hash
from nfl_prediction.models.simulation_io import read
from nfl_prediction.storage.database import Database
from nfl_prediction.storage.forecasts import timestamp, utc


def decimal_odds(value: str, form: str) -> Decimal:
    try:
        number = Decimal(value)
    except InvalidOperation as error:
        raise ValueError("Invalid odds") from error
    if not number.is_finite():
        raise ValueError("Odds must be finite")
    if form == "american":
        if number != number.to_integral_value() or abs(number) < 100:
            raise ValueError("American odds must be integers at least +100 or at most -100")
        number = 1 + (number / 100 if number > 0 else 100 / -number)
    elif form != "decimal":
        raise ValueError("Unknown odds format")
    if not Decimal("1.01") <= number <= 1000:
        raise ValueError("Decimal odds must be between 1.01 and 1000")
    return number


def american_odds(decimal: Decimal) -> str:
    value = (decimal - 1) * 100 if decimal >= 2 else -100 / (decimal - 1)
    return str(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class Line(BaseModel):
    model_config = ConfigDict(extra="forbid")
    forecast_id: str = Field(min_length=1, max_length=64)
    market: Literal["moneyline", "spread", "total"]
    selection: Literal["home", "away", "over", "under"]
    points: str | None = None
    odds: str
    odds_format: Literal["american", "decimal"] = "american"

    @model_validator(mode="after")
    def valid(self):
        decimal_odds(self.odds, self.odds_format)
        if self.market == "total" and self.selection not in ("over", "under"):
            raise ValueError("Total selection must be over/under")
        if self.market != "total" and self.selection not in ("home", "away"):
            raise ValueError("Team market selection must be home/away")
        if self.market == "moneyline":
            if self.points is not None:
                raise ValueError("Moneyline has no point line")
        else:
            try:
                value = Decimal(self.points or "")
            except InvalidOperation as error:
                raise ValueError("A point line is required") from error
            if (
                not value.is_finite()
                or abs(value) > 200
                or value * 2 != (value * 2).to_integral_value()
            ):
                raise ValueError("Use a finite integer/half-point line within 200 points")
            if self.market == "total" and value < 0:
                raise ValueError("Total must be nonnegative")
        return self


def outcomes(home, away, line: dict):
    home, away = np.asarray(home, dtype=float), np.asarray(away, dtype=float)
    point = float(Decimal(line.get("points") or "0"))
    if line["market"] == "total":
        difference = home + away - point
        if line["selection"] == "under":
            difference = -difference
    else:
        difference = home - away if line["selection"] == "home" else away - home
        if line["market"] == "spread":
            difference += point
    return np.sign(difference).astype(int)


def payout(stake_minor: int, outcome: str, odds: Decimal) -> int:
    if outcome in ("push", "void_cancelled", "void_rescheduled"):
        return stake_minor
    if outcome == "loss":
        return 0
    if outcome != "win":
        raise ValueError("Unknown settlement outcome")
    return int((Decimal(stake_minor) * odds).to_integral_value(rounding=ROUND_DOWN))


@lru_cache(maxsize=2)
def team_samples(folder: str, identity: str):
    manifest = read(Path(folder))
    if manifest["simulation_id"] != identity:
        raise ValueError("Simulation identity mismatch")
    return pd.read_parquet(Path(folder) / "team_draws.parquet")


def estimate(version: dict, line: dict, artifacts: Path):
    folder = Path(version["simulation_config"]["artifact_path"]).resolve()
    if not folder.is_relative_to(artifacts.resolve()):
        raise ValueError("Simulation must be inside the local artifact directory")
    frame = team_samples(str(folder), version["simulation_config"]["simulation_id"])
    frame = frame.loc[frame.game_id.eq(version["game_id"])]
    scores = frame.pivot(index="draw", columns="side", values="score")
    if scores.empty or scores[["home", "away"]].isna().any().any():
        raise ValueError("Incomplete joint score samples")
    result = outcomes(scores.home, scores.away, line)
    odds = Decimal(line["decimal_odds"])
    net = np.where(result > 0, float(odds - 1), np.where(result < 0, -1.0, 0.0))
    n = len(result)
    probability = float((result > 0).mean())
    z = 1.96
    center = (probability + z * z / (2 * n)) / (1 + z * z / n)
    radius = (
        z * np.sqrt(probability * (1 - probability) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    )
    stderr = float(net.std(ddof=1) / np.sqrt(n)) if n > 1 else 0
    return {
        "draws": n,
        "win": probability,
        "push": float((result == 0).mean()),
        "loss": float((result < 0).mean()),
        "expected_net_per_credit": float(net.mean()),
        "win_monte_carlo_95": [float(max(0, center - radius)), float(min(1, center + radius))],
        "ev_monte_carlo_95": [float(net.mean() - 1.96 * stderr), float(net.mean() + 1.96 * stderr)],
        "limitations": (
            "Monte Carlo uncertainty only; model/role/calibration errors are "
            "larger and unquantified. Manual lines are not live market data."
        ),
    }


class PaperStore:
    def __init__(self, root: Path, clock=None):
        self.db = Database(root.resolve())
        self.clock = clock or (lambda: datetime.now(UTC))

    def close(self):
        self.db.close()

    @staticmethod
    def _serialize(connection):
        connection.execute(text("UPDATE alembic_version SET version_num=version_num"))

    def initialize(self, account: str, credits_minor: int):
        if not account or len(account) > 64 or any(not (c.isalnum() or c in "-_") for c in account):
            raise ValueError("Invalid virtual account name")
        if type(credits_minor) is not int or not 1 <= credits_minor <= 1_000_000_000:
            raise ValueError("Seed virtual credits must be positive integer minor units")
        now = utc(self.clock())
        with self.db.engine.begin() as connection:
            self._serialize(connection)
            if connection.execute(
                text("SELECT 1 FROM paper_accounts WHERE id=:id"), {"id": account}
            ).first():
                raise ValueError("Virtual account already initialized")
            connection.execute(
                text("INSERT INTO paper_accounts VALUES (:id,:now)"), {"id": account, "now": now}
            )
            connection.execute(
                text(
                    (
                        "INSERT INTO paper_ledger(account_id,created_at,kind,amount_minor) "
                        "VALUES (:account,:now,'seed',:amount)"
                    )
                ),
                {"account": account, "now": now, "amount": credits_minor},
            )
        return {
            "account_id": account,
            "seed_minor": credits_minor,
            "unit": "virtual credits only; 100 minor units = 1 credit",
        }

    def _forecast(self, connection, identity: str, now):
        row = (
            connection.execute(
                text("SELECT * FROM forecast_versions WHERE id=:id"), {"id": identity}
            )
            .mappings()
            .first()
        )
        if not row or row["kind"] != "published_pregame":
            raise ValueError("Only published pregame forecasts are eligible")
        payload = json.loads(row["payload_json"])
        kickoff = timestamp(payload["kickoff_at"])
        if (
            timestamp(row["generated_at"]) >= kickoff
            or timestamp(payload["cutoff"]) >= kickoff
            or now >= kickoff - timedelta(minutes=5)
        ):
            raise ValueError(
                "Entry/line cutoff is five minutes before kickoff; late forecast rejected"
            )
        locked = (
            connection.execute(
                text("SELECT * FROM forecast_locks WHERE game_id=:game"), {"game": row["game_id"]}
            )
            .mappings()
            .first()
        )
        if locked:
            if locked["forecast_id"] != identity:
                raise ValueError("Forecast differs from the official lock")
            cutoff = json.loads(locked["payload_json"])["lock_cutoff"]
            if now >= timestamp(cutoff):
                raise ValueError("Official pregame entry cutoff passed")
        schedules = (
            connection.execute(
                text("SELECT * FROM forecast_schedule WHERE game_id=:game ORDER BY id"),
                {"game": row["game_id"]},
            )
            .mappings()
            .all()
        )
        if schedules and timestamp(schedules[-1]["kickoff_at"]) != kickoff:
            raise ValueError("Rescheduled game requires a new eligible forecast")
        if any(
            timestamp(s["kickoff_at"]) <= now
            and (
                i == len(schedules) - 1
                or timestamp(schedules[i + 1]["observed_at"]) >= timestamp(s["kickoff_at"])
            )
            for i, s in enumerate(schedules)
        ):
            raise ValueError("Previously observed kickoff passed; entry rejected")
        return {"id": identity, **payload}

    def line(self, line: Line):
        now = timestamp(self.clock())
        with self.db.engine.begin() as connection:
            self._serialize(connection)
            forecast = self._forecast(connection, line.forecast_id, now)
            odds = decimal_odds(line.odds, line.odds_format)
            record = {
                **line.model_dump(),
                "game_id": forecast["game_id"],
                "entered_at": utc(now),
                "kickoff_at": forecast["kickoff_at"],
                "decimal_odds": str(odds),
                "american_odds_rounded": american_odds(odds),
                "source": "manual_not_live",
                "rules": "two-way moneyline ties push; integer/half lines; any reschedule voids",
            }
            identity = json_hash(record)
            connection.execute(
                text("INSERT OR IGNORE INTO paper_lines VALUES (:id,:game,:now,:payload)"),
                {
                    "id": identity,
                    "game": record["game_id"],
                    "now": utc(now),
                    "payload": json.dumps(record),
                },
            )
            return {"id": identity, **record}

    def enter(self, account: str, forecast_id: str, line_id: str, stake_minor: int, key: str):
        if type(stake_minor) is not int or not 1 <= stake_minor <= 1_000_000_000:
            raise ValueError("Stake must be positive integer minor virtual-credit units")
        if not key or len(key) > 100:
            raise ValueError("An idempotency key is required")
        now = timestamp(self.clock())
        with self.db.engine.begin() as connection:
            self._serialize(connection)
            forecast = self._forecast(connection, forecast_id, now)
            row = (
                connection.execute(text("SELECT * FROM paper_lines WHERE id=:id"), {"id": line_id})
                .mappings()
                .first()
            )
            if not row or row["game_id"] != forecast["game_id"]:
                raise ValueError("Manual line and forecast must reference the same game")
            line = json.loads(row["payload_json"])
            if line["forecast_id"] != forecast_id:
                raise ValueError("Line version is bound to a different forecast")
            if timestamp(line["entered_at"]) > now or timestamp(line["kickoff_at"]) != timestamp(
                forecast["kickoff_at"]
            ):
                raise ValueError("Line is late or tied to a different kickoff")
            duplicate = connection.execute(
                text(
                    "SELECT 1 FROM paper_entries WHERE account_id=:account AND idempotency_key=:key"
                ),
                {"account": account, "key": key},
            ).first()
            if duplicate:
                raise ValueError("Duplicate virtual entry")
            balance = connection.execute(
                text(
                    (
                        "SELECT COALESCE(SUM(amount_minor),0) FROM paper_ledger WHERE "
                        "account_id=:account"
                    )
                ),
                {"account": account},
            ).scalar_one()
            if balance < stake_minor:
                raise ValueError("Insufficient virtual credits")
            identity = uuid4().hex
            connection.execute(
                text(
                    (
                        "INSERT INTO paper_entries VALUES "
                        "(:id,:account,:forecast,:line,:stake,:now,:key)"
                    )
                ),
                {
                    "id": identity,
                    "account": account,
                    "forecast": forecast_id,
                    "line": line_id,
                    "stake": stake_minor,
                    "now": utc(now),
                    "key": key,
                },
            )
            connection.execute(
                text(
                    (
                        "INSERT INTO "
                        "paper_ledger(account_id,entry_id,created_at,kind,amount_minor) VALUES "
                        "(:account,:entry,:now,'stake',:amount)"
                    )
                ),
                {"account": account, "entry": identity, "now": utc(now), "amount": -stake_minor},
            )
            return {
                "id": identity,
                "account_id": account,
                "forecast_id": forecast_id,
                "line_id": line_id,
                "stake_minor": stake_minor,
                "created_at": utc(now),
            }

    def settle(self, entry_id: str):
        now = utc(self.clock())
        with self.db.engine.begin() as connection:
            self._serialize(connection)
            entry = (
                connection.execute(
                    text("SELECT * FROM paper_entries WHERE id=:id"), {"id": entry_id}
                )
                .mappings()
                .first()
            )
            if not entry:
                raise ValueError("Unknown virtual entry")
            line_row = (
                connection.execute(
                    text("SELECT * FROM paper_lines WHERE id=:id"), {"id": entry["line_id"]}
                )
                .mappings()
                .one()
            )
            line = json.loads(line_row["payload_json"])
            reschedules = (
                connection.execute(
                    text(
                        (
                            "SELECT * FROM forecast_schedule WHERE game_id=:game AND "
                            "observed_at>=:entered ORDER BY id"
                        )
                    ),
                    {"game": line["game_id"], "entered": entry["created_at"]},
                )
                .mappings()
                .all()
            )
            changed = next(
                (
                    s
                    for s in reschedules
                    if timestamp(s["kickoff_at"]) != timestamp(line["kickoff_at"])
                ),
                None,
            )
            if changed:
                evidence, outcome = f"schedule:{changed['id']}", "void_rescheduled"
            else:
                result = (
                    connection.execute(
                        text(
                            (
                                "SELECT * FROM result_revisions WHERE game_id=:game ORDER BY "
                                "recorded_at DESC,rowid DESC LIMIT 1"
                            )
                        ),
                        {"game": line["game_id"]},
                    )
                    .mappings()
                    .first()
                )
                if not result:
                    raise ValueError("No versioned actual result yet")
                payload = json.loads(result["payload_json"])
                if payload["status"] == "provisional":
                    raise ValueError("Provisional result cannot settle a virtual entry")
                evidence = result["id"]
                if payload["status"] == "cancelled":
                    outcome = "void_cancelled"
                else:
                    if timestamp(self.clock()) < timestamp(line["kickoff_at"]):
                        raise ValueError("Game has not started; actual settlement is ineligible")
                    actual = payload["actual"]
                    sign = int(outcomes([actual["home_score"]], [actual["away_score"]], line)[0])
                    outcome = "win" if sign > 0 else "loss" if sign < 0 else "push"
            previous = (
                connection.execute(
                    text(
                        (
                            "SELECT * FROM paper_settlements WHERE entry_id=:id ORDER BY id "
                            "DESC LIMIT 1"
                        )
                    ),
                    {"id": entry_id},
                )
                .mappings()
                .first()
            )
            if previous and previous["evidence_id"] == evidence:
                raise ValueError("Duplicate settlement for this evidence revision")
            returned = payout(entry["stake_minor"], outcome, Decimal(line["decimal_odds"]))
            adjustment = returned - (previous["return_minor"] if previous else 0)
            connection.execute(
                text(
                    (
                        "INSERT INTO "
                        "paper_settlements(entry_id,evidence_id,outcome,return_minor,created_at) "
                        "VALUES (:entry,:evidence,:outcome,:returned,:now)"
                    )
                ),
                {
                    "entry": entry_id,
                    "evidence": evidence,
                    "outcome": outcome,
                    "returned": returned,
                    "now": now,
                },
            )
            connection.execute(
                text(
                    (
                        "INSERT INTO "
                        "paper_ledger(account_id,entry_id,created_at,kind,"
                        "amount_minor,evidence_id) "
                        "VALUES (:account,:entry,:now,:kind,:amount,:evidence)"
                    )
                ),
                {
                    "account": entry["account_id"],
                    "entry": entry_id,
                    "now": now,
                    "kind": "correction" if previous else "settlement",
                    "amount": adjustment,
                    "evidence": evidence,
                },
            )
            return {
                "entry_id": entry_id,
                "evidence_id": evidence,
                "outcome": outcome,
                "return_minor": returned,
                "adjustment_minor": adjustment,
            }


def account(root: Path, identity: str):
    from nfl_prediction.api.reads import query

    ledger = query(
        root,
        (
            "SELECT *,SUM(amount_minor) OVER (ORDER BY id) AS balance_minor FROM paper_ledger "
            "WHERE account_id=? ORDER BY id"
        ),
        (identity,),
    )
    entries = query(
        root,
        (
            "SELECT e.*,l.payload_json AS line_json FROM paper_entries e JOIN paper_lines l ON "
            "l.id=e.line_id WHERE e.account_id=? ORDER BY e.created_at,e.id"
        ),
        (identity,),
    )
    settlements = query(
        root,
        (
            "SELECT s.* FROM paper_settlements s JOIN paper_entries e ON e.id=s.entry_id WHERE "
            "e.account_id=? ORDER BY s.id"
        ),
        (identity,),
    )
    latest = {s["entry_id"]: s for s in settlements}
    settled_stakes = sum(e["stake_minor"] for e in entries if e["id"] in latest)
    net = sum(
        latest[e["id"]]["return_minor"] - e["stake_minor"] for e in entries if e["id"] in latest
    )
    return {
        "account_id": identity,
        "initialized": bool(ledger),
        "balance_minor": ledger[-1]["balance_minor"] if ledger else 0,
        "ledger": ledger,
        "entries": [
            {**e, "line": json.loads(e["line_json"]), "settlement": latest.get(e["id"])}
            for e in entries
        ],
        "settled_count": len(latest),
        "roi": float(Decimal(net) / settled_stakes) if settled_stakes else None,
        "net_settled_minor": net,
        "unit": "virtual credits only; 100 minor units = 1 credit",
        "policy": (
            "Corrections append compensating entries; a negative correction balance "
            "blocks new stakes. No real money or automatic wagering."
        ),
    }


def reconcile(root: Path):
    from nfl_prediction.api.reads import query

    entries = query(root, "SELECT id FROM paper_entries ORDER BY created_at,id")
    if not entries:
        return {"settled_or_corrected": 0, "pending_or_unchanged": 0}
    store = PaperStore(root)
    updated, unchanged = 0, 0
    try:
        for entry in entries:
            try:
                store.settle(entry["id"])
                updated += 1
            except ValueError as error:
                if any(
                    reason in str(error)
                    for reason in ("No versioned actual", "Provisional", "Duplicate settlement")
                ):
                    unchanged += 1
                else:
                    raise
        return {"settled_or_corrected": updated, "pending_or_unchanged": unchanged}
    finally:
        store.close()
