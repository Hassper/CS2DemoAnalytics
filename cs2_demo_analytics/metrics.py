from __future__ import annotations

import numpy as np
import pandas as pd

from .demo_parser import TICK_RATE


def compute_all_metrics(events: pd.DataFrame, rounds: pd.DataFrame, player_steam_id: str) -> dict:
    player_attack = events[events["attacker_steam_id"] == player_steam_id].copy()
    player_victim = events[events["victim_steam_id"] == player_steam_id].copy()

    kills_df = player_attack[player_attack["event_type"] == "kill"]
    damage_df = player_attack[player_attack["event_type"] == "damage"]
    shots_df = player_attack[player_attack["event_type"] == "shot"]
    deaths_df = player_victim[player_victim["event_type"] == "kill"]

    shots_fired = int(len(shots_df))
    shots_hit = int(len(damage_df))
    kills = int(len(kills_df))
    deaths = int(len(deaths_df))
    headshots = int(kills_df["is_headshot"].sum()) if not kills_df.empty else 0
    damage_dealt = float(damage_df["value"].sum()) if not damage_df.empty else 0.0
    damage_taken = float(player_victim[player_victim["event_type"] == "damage"]["value"].sum()) if not player_victim.empty else 0.0

    total_rounds = int(rounds["round_number"].nunique()) if not rounds.empty else int(events["round_number"].max())
    kd_ratio = kills / max(deaths, 1)
    accuracy = shots_hit / max(shots_fired, 1)
    adr = damage_dealt / max(total_rounds, 1)

    round_stats = _round_metrics(player_attack, rounds, total_rounds)
    engagement_stats = _engagement_metrics(events, rounds, player_steam_id)
    custom_metrics = _custom_metrics(player_attack, kills, damage_dealt, shots_fired, shots_hit)

    overview = {
        "kills": kills,
        "deaths": deaths,
        "assists": 0,
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
        "damage_over_time": _damage_over_time(player_attack),
        "kills_per_round": [row["kills"] for row in round_stats],
        "aim_score_distribution": [custom_metrics["aim_consistency_score"], custom_metrics["aim_efficiency_score"]],
    }

    return {
        "overview": overview,
        "round_stats": round_stats,
        "engagement_stats": engagement_stats,
        "custom_metrics": custom_metrics,
        "charts": charts,
    }


def _round_metrics(player_attack: pd.DataFrame, rounds: pd.DataFrame, total_rounds: int) -> list[dict]:
    round_time_lookup: dict[int, float] = {}
    if not rounds.empty:
        for _, row in rounds.iterrows():
            round_time_lookup[int(row["round_number"])] = max(0.0, (float(row["end_tick"]) - float(row["start_tick"])) / TICK_RATE)

    out: list[dict] = []
    for round_number in range(1, total_rounds + 1):
        subset = player_attack[player_attack["round_number"] == round_number]
        kills = int((subset["event_type"] == "kill").sum())
        damage = float(subset[subset["event_type"] == "damage"]["value"].sum())
        survival = round_time_lookup.get(round_number)
        if survival is None:
            survival = float((subset["tick"].max() - subset["tick"].min()) / TICK_RATE) if not subset.empty else 0.0
        out.append({"round": round_number, "kills": kills, "damage": round(damage, 2), "survival_time": round(survival, 2)})
    return out


def _engagement_metrics(events: pd.DataFrame, rounds: pd.DataFrame, player_steam_id: str) -> dict:
    all_kills = events[events["event_type"] == "kill"].sort_values("tick")
    player_kills = all_kills[all_kills["attacker_steam_id"] == player_steam_id]

    first_kills = 0
    opening_duels_won = 0
    trade_kills = 0

    for _, group in all_kills.groupby("round_number"):
        first = group.iloc[0] if not group.empty else None
        if first is not None and first["attacker_steam_id"] == player_steam_id:
            first_kills += 1
            opening_duels_won += 1

        for _, kill in group.iterrows():
            if kill["attacker_steam_id"] != player_steam_id:
                continue
            prior_death = group[(group["tick"] < kill["tick"]) & (group["victim_steam_id"] == player_steam_id)]
            if not prior_death.empty:
                trade_kills += 1

    kills_per_round = player_kills.groupby("round_number").size()
    clutch_attempts = int((kills_per_round >= 2).sum())
    one_v_one_fights = int((kills_per_round == 1).sum())

    post_plant_fights = 0
    if not rounds.empty:
        midpoint_by_round = {
            int(r["round_number"]): (int(r["start_tick"]) + int(r["end_tick"])) / 2 for _, r in rounds.iterrows()
        }
        for _, kill in player_kills.iterrows():
            midpoint = midpoint_by_round.get(int(kill["round_number"]))
            if midpoint and kill["tick"] >= midpoint:
                post_plant_fights += 1

    return {
        "first_kills": first_kills,
        "trade_kills": trade_kills,
        "clutch_attempts": clutch_attempts,
        "one_v_one_fights": one_v_one_fights,
        "opening_duels_won": opening_duels_won,
        "post_plant_fights": post_plant_fights,
    }


def _custom_metrics(player_attack: pd.DataFrame, kills: int, damage_dealt: float, shots_fired: int, shots_hit: int) -> dict:
    damage_timing = _average_reaction_ticks(player_attack, "damage") / TICK_RATE
    kill_reaction = _average_reaction_ticks(player_attack, "kill") / TICK_RATE

    hit_accuracy = shots_hit / max(shots_fired, 1)
    kills_df = player_attack[player_attack["event_type"] == "kill"]
    headshot_ratio = float(kills_df["is_headshot"].mean()) if not kills_df.empty else 0.0
    spray_consistency = _spray_consistency(player_attack)

    aim_consistency_score = _normalize(
        (0.35 * hit_accuracy)
        + (0.25 * headshot_ratio)
        + (0.20 * (1 - min(damage_timing / 1.2, 1)))
        + (0.20 * spray_consistency)
    )

    damage_per_bullet = damage_dealt / max(shots_fired, 1)
    kill_accuracy = kills / max(shots_fired, 1)
    time_to_kill = _time_to_kill(player_attack)

    aim_efficiency_score = _normalize(
        (0.40 * min(damage_per_bullet / 20, 1))
        + (0.35 * min(kill_accuracy / 0.3, 1))
        + (0.25 * (1 - min(time_to_kill / 2.0, 1)))
    )

    return {
        "damage_timing_seconds": round(damage_timing, 3),
        "kill_reaction_seconds": round(kill_reaction, 3),
        "aim_consistency_score": round(aim_consistency_score, 2),
        "aim_efficiency_score": round(aim_efficiency_score, 2),
        "damage_per_bullet": round(damage_per_bullet, 2),
        "time_to_kill_seconds": round(time_to_kill, 3),
    }


def _average_reaction_ticks(player_attack: pd.DataFrame, target_event: str) -> float:
    targets = player_attack[player_attack["event_type"] == target_event].sort_values("tick")
    shots = player_attack[player_attack["event_type"] == "shot"].sort_values("tick")
    deltas: list[float] = []
    for _, row in targets.iterrows():
        prev_shot = shots[shots["tick"] <= row["tick"]].tail(1)
        if not prev_shot.empty:
            deltas.append(float(row["tick"] - prev_shot.iloc[0]["tick"]))
    return float(np.mean(deltas)) if deltas else 0.0


def _spray_consistency(player_attack: pd.DataFrame) -> float:
    damage = player_attack[player_attack["event_type"] == "damage"]["value"]
    if len(damage) < 2:
        return 0.5
    coef = float(damage.std() / max(damage.mean(), 1.0))
    return max(0.0, min(1.0, 1.0 - coef))


def _time_to_kill(player_attack: pd.DataFrame) -> float:
    kills = player_attack[player_attack["event_type"] == "kill"].sort_values("tick")
    damage = player_attack[player_attack["event_type"] == "damage"].sort_values("tick")
    timings: list[float] = []
    for _, kill in kills.iterrows():
        prior_damage = damage[
            (damage["tick"] <= kill["tick"]) & (damage["victim_steam_id"] == kill["victim_steam_id"])
        ].tail(1)
        if not prior_damage.empty:
            timings.append(float((kill["tick"] - prior_damage.iloc[0]["tick"]) / TICK_RATE))
    return float(np.mean(timings)) if timings else 0.0


def _damage_over_time(player_attack: pd.DataFrame) -> list[dict]:
    damage = player_attack[player_attack["event_type"] == "damage"].copy()
    if damage.empty:
        return []
    damage["second"] = (damage["tick"] / TICK_RATE).astype(int)
    grouped = damage.groupby("second")["value"].sum().reset_index()
    return [{"x": int(row["second"]), "y": float(row["value"])} for _, row in grouped.iterrows()]


def _normalize(value: float) -> float:
    return max(0.0, min(100.0, value * 100.0))
