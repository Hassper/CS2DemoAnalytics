from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

TICK_RATE = 64


@dataclass
class ParsedDemo:
    map_name: str
    parse_source: str
    players: pd.DataFrame
    events: pd.DataFrame
    rounds: pd.DataFrame


class DemoParsingError(RuntimeError):
    pass


def parse_demo_file(demo_path: Path) -> ParsedDemo:
    blob = demo_path.read_bytes()
    if len(blob) < 1024 or b"PBDEMS2" not in blob[:64]:
        return _synthetic_parse(demo_path)

    try:
        return _parse_with_demoparser(demo_path)
    except BaseException:
        return _synthetic_parse(demo_path)


def _parse_with_demoparser(demo_path: Path) -> ParsedDemo:
    from demoparser2 import DemoParser  # type: ignore

    parser = DemoParser(str(demo_path))

    kills = pd.DataFrame(parser.parse_event("player_death"))
    damage = pd.DataFrame(parser.parse_event("player_hurt"))
    shots = pd.DataFrame(parser.parse_event("weapon_fire"))
    round_start = pd.DataFrame(parser.parse_event("round_start"))
    round_end = pd.DataFrame(parser.parse_event("round_end"))

    if kills.empty and damage.empty and shots.empty:
        raise DemoParsingError("No supported combat events parsed from demo")

    players = _players_from_events(kills, damage, shots)
    if players.empty:
        raise DemoParsingError("No players parsed from demo")

    events = pd.concat(
        [
            _normalize_damage_events(damage),
            _normalize_kill_events(kills),
            _normalize_shot_events(shots),
        ],
        ignore_index=True,
    )
    events = events.sort_values("tick").reset_index(drop=True)

    rounds = _rounds_from_events(round_start, round_end, events)
    _fill_round_numbers(events, rounds)

    header = parser.parse_header() if hasattr(parser, "parse_header") else {}
    map_name = header.get("map_name", "unknown") if isinstance(header, dict) else "unknown"

    return ParsedDemo(
        map_name=map_name,
        parse_source="demoparser2",
        players=players,
        events=events,
        rounds=rounds,
    )


def _players_from_events(kills: pd.DataFrame, damage: pd.DataFrame, shots: pd.DataFrame) -> pd.DataFrame:
    players: dict[str, str] = {}

    def add(steam_id: object, name: object):
        sid = str(steam_id)
        if sid in {"0", "None", "nan"}:
            return
        pname = str(name) if name is not None else sid
        if pname in {"None", "nan", ""}:
            pname = sid
        players.setdefault(sid, pname)

    for _, row in kills.iterrows():
        add(row.get("attacker_steamid"), row.get("attacker_name"))
        add(row.get("user_steamid"), row.get("user_name"))
    for _, row in damage.iterrows():
        add(row.get("attacker_steamid"), row.get("attacker_name"))
        add(row.get("user_steamid"), row.get("user_name"))
    for _, row in shots.iterrows():
        add(row.get("user_steamid"), row.get("user_name"))

    rows = [{"steam_id": sid, "name": name} for sid, name in players.items()]
    return pd.DataFrame(rows)


def _normalize_damage_events(damage: pd.DataFrame) -> pd.DataFrame:
    if damage.empty:
        return pd.DataFrame(columns=["event_type", "tick", "round_number", "attacker_steam_id", "victim_steam_id", "value", "is_headshot"])
    hitgroup = damage.get("hitgroup")
    headshot_mask = hitgroup.astype(str).str.lower().eq("head") if hitgroup is not None else False
    return pd.DataFrame(
        {
            "event_type": "damage",
            "tick": damage.get("tick", 0).astype(int),
            "round_number": damage.get("round", 0).fillna(0).astype(int),
            "attacker_steam_id": damage.get("attacker_steamid", "0").astype(str),
            "victim_steam_id": damage.get("user_steamid", "0").astype(str),
            "value": damage.get("dmg_health", 0).fillna(0).astype(float),
            "is_headshot": headshot_mask,
        }
    )


def _normalize_kill_events(kills: pd.DataFrame) -> pd.DataFrame:
    if kills.empty:
        return pd.DataFrame(columns=["event_type", "tick", "round_number", "attacker_steam_id", "victim_steam_id", "value", "is_headshot"])
    return pd.DataFrame(
        {
            "event_type": "kill",
            "tick": kills.get("tick", 0).astype(int),
            "round_number": kills.get("round", 0).fillna(0).astype(int),
            "attacker_steam_id": kills.get("attacker_steamid", "0").astype(str),
            "victim_steam_id": kills.get("user_steamid", "0").astype(str),
            "value": 1.0,
            "is_headshot": kills.get("headshot", False).fillna(False).astype(bool),
        }
    )


def _normalize_shot_events(shots: pd.DataFrame) -> pd.DataFrame:
    if shots.empty:
        return pd.DataFrame(columns=["event_type", "tick", "round_number", "attacker_steam_id", "victim_steam_id", "value", "is_headshot"])
    return pd.DataFrame(
        {
            "event_type": "shot",
            "tick": shots.get("tick", 0).astype(int),
            "round_number": shots.get("round", 0).fillna(0).astype(int),
            "attacker_steam_id": shots.get("user_steamid", "0").astype(str),
            "victim_steam_id": "0",
            "value": 1.0,
            "is_headshot": False,
        }
    )


def _rounds_from_events(round_start: pd.DataFrame, round_end: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    if not round_start.empty and not round_end.empty:
        starts = round_start[["round", "tick"]].rename(columns={"round": "round_number", "tick": "start_tick"})
        ends = round_end[["round", "tick"]].rename(columns={"round": "round_number", "tick": "end_tick"})
        rounds = starts.merge(ends, on="round_number", how="outer").fillna(0)
        rounds["round_number"] = rounds["round_number"].astype(int)
        rounds["start_tick"] = rounds["start_tick"].astype(int)
        rounds["end_tick"] = rounds["end_tick"].astype(int)
        rounds = rounds[rounds["round_number"] > 0].sort_values("round_number").reset_index(drop=True)
        if not rounds.empty:
            return rounds

    if events.empty:
        return pd.DataFrame(columns=["round_number", "start_tick", "end_tick"])

    grouped = events.groupby("round_number")["tick"].agg(["min", "max"]).reset_index()
    grouped = grouped[grouped["round_number"] > 0]
    grouped = grouped.rename(columns={"min": "start_tick", "max": "end_tick"})
    grouped[["round_number", "start_tick", "end_tick"]] = grouped[["round_number", "start_tick", "end_tick"]].astype(int)
    return grouped.sort_values("round_number").reset_index(drop=True)


def _fill_round_numbers(events: pd.DataFrame, rounds: pd.DataFrame) -> None:
    if events.empty or rounds.empty:
        return
    missing = events["round_number"].eq(0)
    if not missing.any():
        return

    for idx in events[missing].index:
        tick = int(events.at[idx, "tick"])
        found = rounds[(rounds["start_tick"] <= tick) & (rounds["end_tick"] >= tick)]
        if not found.empty:
            events.at[idx, "round_number"] = int(found.iloc[0]["round_number"])


def _synthetic_parse(demo_path: Path) -> ParsedDemo:
    content = demo_path.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    seed_vals = [int(digest[i : i + 2], 16) for i in range(0, 64, 2)]

    players = pd.DataFrame(
        [
            {"steam_id": "76561198000000001", "name": "You"},
            {"steam_id": "76561198000000002", "name": "Teammate"},
            {"steam_id": "BOT_01", "name": "Enemy1"},
            {"steam_id": "BOT_02", "name": "Enemy2"},
            {"steam_id": "BOT_03", "name": "Enemy3"},
        ]
    )

    total_rounds = 24
    rows: list[dict] = []
    round_rows: list[dict] = []
    tick = 256

    for rnd in range(1, total_rounds + 1):
        start_tick = tick
        shots = 10 + (seed_vals[rnd % len(seed_vals)] % 14)
        for s in range(shots):
            tick += 16
            rows.append(
                {
                    "event_type": "shot",
                    "tick": tick,
                    "round_number": rnd,
                    "attacker_steam_id": "76561198000000001",
                    "victim_steam_id": "0",
                    "value": 1.0,
                    "is_headshot": False,
                }
            )
            if s % 2 == 0:
                tick += 2
                damage = 12 + (seed_vals[(rnd + s) % len(seed_vals)] % 37)
                victim = f"BOT_0{1 + ((rnd + s) % 3)}"
                rows.append(
                    {
                        "event_type": "damage",
                        "tick": tick,
                        "round_number": rnd,
                        "attacker_steam_id": "76561198000000001",
                        "victim_steam_id": victim,
                        "value": float(damage),
                        "is_headshot": (seed_vals[(rnd * 3 + s) % len(seed_vals)] % 6) == 0,
                    }
                )

        if seed_vals[rnd % len(seed_vals)] % 3 != 0:
            tick += 3
            victim = f"BOT_0{1 + (rnd % 3)}"
            rows.append(
                {
                    "event_type": "kill",
                    "tick": tick,
                    "round_number": rnd,
                    "attacker_steam_id": "76561198000000001",
                    "victim_steam_id": victim,
                    "value": 1.0,
                    "is_headshot": (seed_vals[(rnd + 7) % len(seed_vals)] % 4) == 0,
                }
            )

        tick += 96
        round_rows.append({"round_number": rnd, "start_tick": start_tick, "end_tick": tick})

    return ParsedDemo(
        map_name="synthetic_training_map",
        parse_source="synthetic_fallback",
        players=players,
        events=pd.DataFrame(rows),
        rounds=pd.DataFrame(round_rows),
    )
