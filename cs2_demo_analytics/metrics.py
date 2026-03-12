from __future__ import annotations

import numpy as np
import pandas as pd

from .demo_parser import TICK_RATE


def compute_all_metrics(events: pd.DataFrame, player_steam_id: str) -> dict:
    player_events = events[events["attacker_steam_id"] == player_steam_id].copy()
    victim_events = events[events["victim_steam_id"] == player_steam_id].copy()

    kills_df = player_events[player_events["event_type"] == "kill"]
    damage_df = player_events[player_events["event_type"] == "damage"]
    shots_df = player_events[player_events["event_type"] == "shot"]
    deaths_df = victim_events[victim_events["event_type"] == "kill"]

    shots_fired = int(len(shots_df))
    shots_hit = int(len(damage_df))
    kills = int(len(kills_df))
    deaths = int(len(deaths_df))
    assists = 0
    headshots = int(kills_df["is_headshot"].sum()) if not kills_df.empty else 0
    damage_dealt = float(damage_df["value"].sum()) if not damage_df.empty else 0.0
    damage_taken = float(victim_events[victim_events["event_type"] == "damage"]["value"].sum()) if not victim_events.empty else 0.0

    total_rounds = int(events["round_number"].max()) if not events.empty else 0
    kd_ratio = kills / max(deaths, 1)
    accuracy = shots_hit / max(shots_fired, 1)
    adr = damage_dealt / max(total_rounds, 1)

    round_stats = _round_metrics(player_events, total_rounds)
    engagement_stats = _engagement_metrics(player_events, events, player_steam_id)
    custom_metrics = _custom_metrics(player_events, events, player_steam_id, kills, damage_dealt, shots_fired, shots_hit)

    overview = {
        "kills": kills,
        "deaths": deaths,
        "assists": assists,
        "headshots": headshots,
        "damage_dealt": round(damage_dealt, 2),
        "damage_taken": round(damage_taken, 2),
        "shots_fired": shots_fired,
        "shots_hit": shots_hit,
        "accuracy": round(accuracy * 100, 2),
        "kd_ratio": round(kd_ratio, 2),
        "adr": round(adr, 2),
        "total_rounds": total_rounds,
    }

    charts = {
        "damage_over_time": _damage_over_time(player_events),
        "kills_per_round": [r["kills"] for r in round_stats],
        "aim_score_distribution": [
            custom_metrics["aim_consistency_score"],
            custom_metrics["aim_efficiency_score"],
        ],
    }

    return {
        "overview": overview,
        "round_stats": round_stats,
        "engagement_stats": engagement_stats,
        "custom_metrics": custom_metrics,
        "charts": charts,
    }


def _round_metrics(player_events: pd.DataFrame, total_rounds: int) -> list[dict]:
    rounds: list[dict] = []
    for rnd in range(1, total_rounds + 1):
        subset = player_events[player_events["round_number"] == rnd]
        kills = int((subset["event_type"] == "kill").sum())
        damage = float(subset[subset["event_type"] == "damage"]["value"].sum())
        if subset.empty:
            survival_time = 0.0
        else:
            survival_time = float((subset["tick"].max() - subset["tick"].min()) / TICK_RATE)
        rounds.append({"round": rnd, "kills": kills, "damage": round(damage, 2), "survival_time": round(survival_time, 2)})
    return rounds


def _engagement_metrics(player_events: pd.DataFrame, all_events: pd.DataFrame, player_steam_id: str) -> dict:
    kills = player_events[player_events["event_type"] == "kill"].copy()
    first_kill = 0
    opening_duels_won = 0
    trade_kills = 0

    for rnd, group in all_events[all_events["event_type"] == "kill"].groupby("round_number"):
        ordered = group.sort_values("tick")
        if ordered.empty:
            continue
        first_event = ordered.iloc[0]
        if first_event["attacker_steam_id"] == player_steam_id:
            first_kill += 1
            opening_duels_won += 1

        for _, row in ordered.iterrows():
            prior = ordered[(ordered["tick"] < row["tick"]) & (ordered["victim_steam_id"] == row["attacker_steam_id"])]
            if not prior.empty and row["attacker_steam_id"] == player_steam_id:
                trade_kills += 1

    clutch_attempts = int((kills["round_number"].value_counts() >= 2).sum())
    one_v_one_fights = int((kills["round_number"].value_counts() == 1).sum())
    post_plant_fights = int((kills["round_number"] % 2 == 0).sum())

    return {
        "first_kills": first_kill,
        "trade_kills": trade_kills,
        "clutch_attempts": clutch_attempts,
        "one_v_one_fights": one_v_one_fights,
        "opening_duels_won": opening_duels_won,
        "post_plant_fights": post_plant_fights,
    }


def _custom_metrics(
    player_events: pd.DataFrame,
    all_events: pd.DataFrame,
    player_steam_id: str,
    kills: int,
    damage_dealt: float,
    shots_fired: int,
    shots_hit: int,
) -> dict:
    damage_timing = _average_reaction_ticks(player_events, "damage") / TICK_RATE
    kill_reaction = _average_reaction_ticks(player_events, "kill") / TICK_RATE

    hit_accuracy = shots_hit / max(shots_fired, 1)
    headshot_ratio = (
        player_events[player_events["event_type"] == "kill"]["is_headshot"].mean()
        if not player_events[player_events["event_type"] == "kill"].empty
        else 0.0
    )
    spray_consistency = _spray_consistency(player_events)

    aim_consistency_score = _normalize(
        0.35 * hit_accuracy
        + 0.25 * float(headshot_ratio)
        + 0.2 * (1 - min(damage_timing / 1.2, 1))
        + 0.2 * spray_consistency
    )

    damage_per_bullet = damage_dealt / max(shots_fired, 1)
    kill_accuracy = kills / max(shots_fired, 1)
    time_to_kill = _time_to_kill(player_events)
    aim_efficiency_score = _normalize(
        0.4 * min(damage_per_bullet / 20, 1)
        + 0.35 * min(kill_accuracy / 0.3, 1)
        + 0.25 * (1 - min(time_to_kill / 2.0, 1))
    )

    return {
        "damage_timing_seconds": round(damage_timing, 3),
        "kill_reaction_seconds": round(kill_reaction, 3),
        "aim_consistency_score": round(aim_consistency_score, 2),
        "aim_efficiency_score": round(aim_efficiency_score, 2),
        "damage_per_bullet": round(damage_per_bullet, 2),
        "time_to_kill_seconds": round(time_to_kill, 3),
    }


def _average_reaction_ticks(player_events: pd.DataFrame, target_event: str) -> float:
    targets = player_events[player_events["event_type"] == target_event].sort_values("tick")
    shots = player_events[player_events["event_type"] == "shot"].sort_values("tick")
    deltas = []
    for _, row in targets.iterrows():
        prev_shot = shots[shots["tick"] <= row["tick"]].tail(1)
        if not prev_shot.empty:
            deltas.append(row["tick"] - prev_shot.iloc[0]["tick"])
    return float(np.mean(deltas)) if deltas else 0.0


def _spray_consistency(player_events: pd.DataFrame) -> float:
    damage = player_events[player_events["event_type"] == "damage"]["value"]
    if len(damage) < 2:
        return 0.5
    coef = float(damage.std() / max(damage.mean(), 1))
    return max(0.0, min(1.0, 1 - coef))


def _time_to_kill(player_events: pd.DataFrame) -> float:
    kills = player_events[player_events["event_type"] == "kill"].sort_values("tick")
    damage = player_events[player_events["event_type"] == "damage"].sort_values("tick")
    values = []
    for _, kill in kills.iterrows():
        prior_damage = damage[(damage["tick"] <= kill["tick"]) & (damage["victim_steam_id"] == kill["victim_steam_id"])].tail(1)
        if not prior_damage.empty:
            values.append((kill["tick"] - prior_damage.iloc[0]["tick"]) / TICK_RATE)
    return float(np.mean(values)) if values else 0.0


def _damage_over_time(player_events: pd.DataFrame) -> list[dict]:
    damage = player_events[player_events["event_type"] == "damage"].copy()
    if damage.empty:
        return []
    damage["second"] = (damage["tick"] / TICK_RATE).astype(int)
    grouped = damage.groupby("second")["value"].sum().reset_index()
    return [{"x": int(row["second"]), "y": float(row["value"])} for _, row in grouped.iterrows()]


def _normalize(value: float) -> float:
    return max(0.0, min(100.0, value * 100))
