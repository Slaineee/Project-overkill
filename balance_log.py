from __future__ import annotations

import csv
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


FIELDS = (
    "logged_at",
    "run_id",
    "world",
    "elapsed_seconds",
    "start_population",
    "final_population",
    "start_base_damage",
    "final_base_damage",
    "start_shot_damage",
    "final_shot_damage",
    "start_fire_rate",
    "final_fire_rate",
    "start_volley_multiplier",
    "final_volley_multiplier",
    "start_dps",
    "final_dps",
    "dps_growth",
    "gold_before_reward",
    "enemy_kills",
    "cards",
)


def create_run_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S-%f")


def default_balance_log_path() -> Path:
    if getattr(sys, "frozen", False):
        root = Path(sys.executable).resolve().parent
    else:
        root = Path(__file__).resolve().parent
    return root / "balance_logs" / "world_dps.csv"


def append_world_balance_log(record: dict[str, Any], path: Path | None = None) -> Path:
    destination = path or default_balance_log_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    is_new = not destination.exists() or destination.stat().st_size == 0
    encoding = "utf-8-sig" if is_new else "utf-8"
    with destination.open("a", encoding=encoding, newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS, extrasaction="ignore")
        if is_new:
            writer.writeheader()
        writer.writerow({field: record.get(field, "") for field in FIELDS})
    return destination
