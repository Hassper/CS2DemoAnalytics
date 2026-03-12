from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

TICK_RATE = 64


@dataclass
class ParsedDemo:
    map_name: str
    players: pd.DataFrame
    events: pd.DataFrame


class DemoParsingError(RuntimeError):
    pass


def parse_demo_file(demo_path: Path) -> ParsedDemo:
    """Parse CS2 demo file into normalized event tables.

    Falls back to deterministic synthetic events if parser import/runtime fails,
    allowing local development without depending on real demo internals.
    """
    blob = demo_path.read_bytes()
    # Avoid calling the Rust parser on clearly invalid uploads to prevent native panics.
    if len(blob) < 1024 or b"PBDEMS2" not in blob[:64]:
        return _synthetic_parse(demo_path)

    try:
        return _parse_with_demoparser(demo_path)
    except BaseException:
        return _synthetic_parse(demo_path)


def _parse_with_demoparser(demo_path: Path) -> ParsedDemo:
    from demoparser2 import DemoParser  # type: ignore

    parser = DemoParser(str(demo_path))

    players_raw = parser.parse_ticks(
        ["steamid", "name"],
        ticks=[0],
    )
    players = pd.DataFrame(players_raw).dropna().drop_duplicates(subset=["steamid"])
    players = players.rename(columns={"steamid": "steam_id"})[["steam_id", "name"]]

    damage = pd.DataFrame(parser.parse_event("player_hurt"))
    kills = pd.DataFrame(parser.parse_event("player_death"))
    shots = pd.DataFrame(parser.parse_event("weapon_fire"))

    if damage.empty and kills.empty:
        raise DemoParsingError("No parseable events in demo.")

    damage_events = pd.DataFrame(
        {
            "event_type": "damage",
            "tick": damage.get("tick", 0),
            "round_number": damage.get("round", 0),
            "attacker_steam_id": damage.get("attacker_steamid", "0"),
            "victim_steam_id": damage.get("user_steamid", "0"),
            "value": damage.get("dmg_health", 0),
            "is_headshot": damage.get("hitgroup", "") == "head",
        }
    )

    kill_events = pd.DataFrame(
        {
            "event_type": "kill",
            "tick": kills.get("tick", 0),
            "round_number": kills.get("round", 0),
            "attacker_steam_id": kills.get("attacker_steamid", "0"),
            "victim_steam_id": kills.get("user_steamid", "0"),
            "value": 1,
            "is_headshot": kills.get("headshot", False),
        }
    )

    shot_events = pd.DataFrame(
        {
            "event_type": "shot",
            "tick": shots.get("tick", 0),
            "round_number": shots.get("round", 0),
            "attacker_steam_id": shots.get("user_steamid", "0"),
            "victim_steam_id": None,
            "value": 1,
            "is_headshot": False,
        }
    )

    events = pd.concat([damage_events, kill_events, shot_events], ignore_index=True).fillna(0)
    events["attacker_steam_id"] = events["attacker_steam_id"].astype(str)
    events["victim_steam_id"] = events["victim_steam_id"].astype(str)
    header = parser.parse_header() if hasattr(parser, "parse_header") else {}
    map_name = header.get("map_name", "unknown") if isinstance(header, dict) else "unknown"
    return ParsedDemo(map_name=map_name, players=players, events=events)


def _synthetic_parse(demo_path: Path) -> ParsedDemo:
    content = demo_path.read_bytes()
    digest = hashlib.sha256(content).hexdigest()

    players = pd.DataFrame(
        [
            {"steam_id": "76561198000000001", "name": "You"},
            {"steam_id": "76561198000000002", "name": "Teammate"},
            {"steam_id": "BOT_01", "name": "Enemy1"},
            {"steam_id": "BOT_02", "name": "Enemy2"},
        ]
    )

    seed_vals = [int(digest[i : i + 2], 16) for i in range(0, 60, 2)]
    rows: list[dict] = []
    tick = 256
    for rnd in range(1, 13):
        shots = 8 + (seed_vals[rnd] % 7)
        for s in range(shots):
            tick += 18
            rows.append(
                {
                    "event_type": "shot",
                    "tick": tick,
                    "round_number": rnd,
                    "attacker_steam_id": "76561198000000001",
                    "victim_steam_id": "0",
                    "value": 1,
                    "is_headshot": False,
                }
            )
            if s % 2 == 0:
                tick += 3
                dmg = 18 + (seed_vals[(rnd + s) % len(seed_vals)] % 28)
                hs = (seed_vals[(rnd * 2 + s) % len(seed_vals)] % 5) == 0
                rows.append(
                    {
                        "event_type": "damage",
                        "tick": tick,
                        "round_number": rnd,
                        "attacker_steam_id": "76561198000000001",
                        "victim_steam_id": "BOT_01",
                        "value": dmg,
                        "is_headshot": hs,
                    }
                )
        if seed_vals[rnd] % 2 == 0:
            tick += 4
            rows.append(
                {
                    "event_type": "kill",
                    "tick": tick,
                    "round_number": rnd,
                    "attacker_steam_id": "76561198000000001",
                    "victim_steam_id": "BOT_01",
                    "value": 1,
                    "is_headshot": bool(seed_vals[rnd] % 3 == 0),
                }
            )
        tick += 128

    events = pd.DataFrame(rows)
    return ParsedDemo(map_name="synthetic_training_map", players=players, events=events)
