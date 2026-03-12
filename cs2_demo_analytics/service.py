from __future__ import annotations

from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

from .demo_parser import parse_demo_file
from .metrics import compute_all_metrics
from .models import Event, Match, Metric, Player, Round


def ingest_demo(db: Session, demo_path: Path, demo_filename: str) -> int:
    parsed = parse_demo_file(demo_path)

    total_rounds = int(parsed.rounds["round_number"].nunique()) if not parsed.rounds.empty else 0
    total_ticks = int(parsed.events["tick"].max()) if not parsed.events.empty else 0

    match = Match(
        demo_filename=demo_filename,
        map_name=parsed.map_name,
        total_rounds=total_rounds,
        parse_source=parsed.parse_source,
        tick_rate=64,
        total_ticks=total_ticks,
    )
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
        elif str(row.get("name", "")).strip() and player.name != str(row.get("name")):
            player.name = str(row.get("name"))
        players_by_steam[steam_id] = player

    if not players_by_steam:
        raise RuntimeError("No players parsed from demo")

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

    for _, row in parsed.rounds.iterrows():
        db.add(
            Round(
                match_id=match.id,
                round_number=int(row["round_number"]),
                start_tick=int(row["start_tick"]),
                end_tick=int(row["end_tick"]),
            )
        )

    _persist_initial_metrics(db, match.id, parsed.events, parsed.rounds, players_by_steam)

    db.commit()
    return match.id


def _persist_initial_metrics(
    db: Session,
    match_id: int,
    events: pd.DataFrame,
    rounds: pd.DataFrame,
    players_by_steam: dict[str, Player],
) -> None:
    for steam_id, player in players_by_steam.items():
        player_attack = events[events["attacker_steam_id"] == steam_id]
        if player_attack.empty:
            continue

        analytics = compute_all_metrics(events, rounds, steam_id)
        for key, value in analytics["overview"].items():
            db.add(
                Metric(
                    match_id=match_id,
                    player_id=player.id,
                    key=key,
                    value=float(value),
                    details={},
                    is_custom=False,
                )
            )
        for key, value in analytics["custom_metrics"].items():
            db.add(
                Metric(
                    match_id=match_id,
                    player_id=player.id,
                    key=key,
                    value=float(value),
                    details={},
                    is_custom=True,
                )
            )


def fetch_analytics(db: Session, match_id: int, player_steam_id: str | None = None) -> dict:
    match = db.query(Match).filter(Match.id == match_id).one()
    players = _players_for_match(db, match_id)
    if not players:
        raise RuntimeError("No players found for match")

    selected_steam = player_steam_id or players[0]["steam_id"]
    if not any(p["steam_id"] == selected_steam for p in players):
        raise RuntimeError(f"Player {selected_steam} not found in match")

    events = _events_dataframe(db, match_id)
    rounds = _rounds_dataframe(db, match_id)
    analytics = compute_all_metrics(events, rounds, selected_steam)

    return {
        "match_id": match.id,
        "match_info": {
            "demo_filename": match.demo_filename,
            "map_name": match.map_name,
            "uploaded_at": match.uploaded_at.isoformat(),
            "total_rounds": match.total_rounds,
            "parse_source": match.parse_source,
            "tick_rate": match.tick_rate,
            "duration_seconds": round(match.total_ticks / max(match.tick_rate, 1), 2),
        },
        "players": players,
        "selected_player": selected_steam,
        **analytics,
    }


def _players_for_match(db: Session, match_id: int) -> list[dict]:
    rows = (
        db.query(Player.steam_id, Player.name)
        .join(Event, (Event.attacker_id == Player.id) | (Event.victim_id == Player.id))
        .filter(Event.match_id == match_id)
        .distinct()
        .all()
    )
    return [{"steam_id": r.steam_id, "name": r.name} for r in rows]


def _events_dataframe(db: Session, match_id: int) -> pd.DataFrame:
    rows = (
        db.query(
            Event.event_type,
            Event.tick,
            Event.round_number,
            Player.steam_id.label("attacker_steam_id"),
            Player.name.label("attacker_name"),
            Event.victim_id,
            Event.value,
            Event.payload,
        )
        .join(Player, Event.attacker_id == Player.id, isouter=True)
        .filter(Event.match_id == match_id)
        .all()
    )

    victim_lookup = {p.id: p.steam_id for p in db.query(Player.id, Player.steam_id).all()}
    values = []
    for row in rows:
        payload = row.payload or {}
        values.append(
            {
                "event_type": row.event_type,
                "tick": int(row.tick),
                "round_number": int(row.round_number),
                "attacker_steam_id": row.attacker_steam_id or "0",
                "victim_steam_id": victim_lookup.get(row.victim_id, "0"),
                "value": float(row.value),
                "is_headshot": bool(payload.get("is_headshot", False)),
            }
        )

    if not values:
        return pd.DataFrame(columns=["event_type", "tick", "round_number", "attacker_steam_id", "victim_steam_id", "value", "is_headshot"])
    return pd.DataFrame(values).sort_values("tick").reset_index(drop=True)


def _rounds_dataframe(db: Session, match_id: int) -> pd.DataFrame:
    rows = db.query(Round.round_number, Round.start_tick, Round.end_tick).filter(Round.match_id == match_id).all()
    if not rows:
        return pd.DataFrame(columns=["round_number", "start_tick", "end_tick"])
    return pd.DataFrame(
        [{"round_number": int(r.round_number), "start_tick": int(r.start_tick), "end_tick": int(r.end_tick)} for r in rows]
    ).sort_values("round_number")
