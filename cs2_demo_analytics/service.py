from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from .demo_parser import parse_demo_file
from .metrics import compute_all_metrics
from .models import Event, Match, Metric, Player, Round


def ingest_demo(db: Session, demo_path: Path, demo_filename: str) -> int:
    parsed = parse_demo_file(demo_path)

    match = Match(demo_filename=demo_filename, map_name=parsed.map_name, total_rounds=int(parsed.events["round_number"].max()))
    db.add(match)
    db.flush()

    players_by_steam: dict[str, Player] = {}
    for _, row in parsed.players.iterrows():
        steam_id = str(row["steam_id"])
        player = db.query(Player).filter(Player.steam_id == steam_id).one_or_none()
        if player is None:
            player = Player(steam_id=steam_id, name=str(row.get("name", steam_id)))
            db.add(player)
            db.flush()
        players_by_steam[steam_id] = player

    if not players_by_steam:
        raise RuntimeError("No players parsed from demo.")

    main_player_steam = next(iter(players_by_steam.keys()))
    analytics = compute_all_metrics(parsed.events, main_player_steam)

    for _, row in parsed.events.iterrows():
        attacker = players_by_steam.get(str(row["attacker_steam_id"]))
        victim = players_by_steam.get(str(row["victim_steam_id"]))
        db.add(
            Event(
                match_id=match.id,
                event_type=str(row["event_type"]),
                tick=int(row["tick"]),
                round_number=int(row["round_number"]),
                attacker_id=attacker.id if attacker else None,
                victim_id=victim.id if victim else None,
                value=float(row.get("value", 0.0)),
                payload={"is_headshot": bool(row.get("is_headshot", False))},
            )
        )

    for row in analytics["round_stats"]:
        db.add(
            Round(
                match_id=match.id,
                round_number=int(row["round"]),
                kills=int(row["kills"]),
                damage=int(row["damage"]),
                survival_time=float(row["survival_time"]),
            )
        )

    main_player = players_by_steam[main_player_steam]
    for key, value in analytics["overview"].items():
        db.add(Metric(match_id=match.id, player_id=main_player.id, key=key, value=float(value), details={}, is_custom=False))

    for key, value in analytics["custom_metrics"].items():
        db.add(Metric(match_id=match.id, player_id=main_player.id, key=key, value=float(value), details={}, is_custom=True))

    db.commit()
    return match.id


def fetch_analytics(db: Session, match_id: int) -> dict:
    match = db.query(Match).filter(Match.id == match_id).one()
    main_metric = db.query(Metric).filter(Metric.match_id == match_id).first()
    if main_metric is None:
        raise RuntimeError("Metrics not found for match")

    player_id = main_metric.player_id
    overview_metrics = db.query(Metric).filter(Metric.match_id == match_id, Metric.player_id == player_id, Metric.is_custom.is_(False)).all()
    custom_metrics = db.query(Metric).filter(Metric.match_id == match_id, Metric.player_id == player_id, Metric.is_custom.is_(True)).all()
    rounds = db.query(Round).filter(Round.match_id == match_id).order_by(Round.round_number.asc()).all()

    overview = {m.key: m.value for m in overview_metrics}
    custom = {m.key: m.value for m in custom_metrics}
    round_stats = [
        {
            "round": r.round_number,
            "kills": r.kills,
            "damage": r.damage,
            "survival_time": r.survival_time,
        }
        for r in rounds
    ]

    charts = {
        "kills_per_round": [r["kills"] for r in round_stats],
        "damage_over_time": [],
        "aim_score_distribution": [custom.get("aim_consistency_score", 0), custom.get("aim_efficiency_score", 0)],
    }

    engagement_stats = {
        "first_kills": 0,
        "trade_kills": 0,
        "clutch_attempts": 0,
        "one_v_one_fights": 0,
        "opening_duels_won": 0,
        "post_plant_fights": 0,
    }

    return {
        "match_id": match.id,
        "overview": overview,
        "round_stats": round_stats,
        "engagement_stats": engagement_stats,
        "custom_metrics": custom,
        "charts": charts,
    }
