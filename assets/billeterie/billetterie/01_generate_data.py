# scripts/01_generate_data.py
from __future__ import annotations

import random
from pathlib import Path
from datetime import datetime, timedelta

import numpy as np
import pandas as pd


# -----------------------------
# Config simple (tu peux ajuster)
# -----------------------------
SEED = 42
N_EVENTS = 24
TARGET_TRANSACTIONS = 9000  # transactions (pas tickets)
START_DATE = "2026-03-01"   # période des événements
END_DATE = "2026-06-30"
OUTPUT_DIR = Path("data/raw")


# Marseille (fictif mais crédible)
ZONES = [
    "Vieux-Port", "Le Panier", "Noailles", "La Plaine", "Cours Julien",
    "Castellane", "Prado", "Endoume", "Les Goudes", "L’Estaque",
    "Belle de Mai", "Saint-Charles", "La Joliette", "Euroméditerranée",
    "La Timone", "Mazargues", "Pointe Rouge", "Saint-Loup", "Saint-Barnabé"
]

VENUES = [
    "Salle du Vieux-Port", "Théâtre du Panier", "La Friche (scène)", "Le Dôme (club)",
    "Dock des Suds (fiction)", "Espace Joliette", "Théâtre Canebière", "Salle Prado"
]

GENRES = [
    "Concert", "Théâtre", "Stand-up", "Festival", "Projection", "Conférence", "Danse"
]

CHANNELS = ["web", "partenaire", "guichet", "pass"]
TARIFFS = ["plein", "reduit", "early_bird", "last_minute"]


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def pick_weighted(values, weights, size=1):
    return random.choices(values, weights=weights, k=size)


def dt_range(start: datetime, end: datetime) -> datetime:
    """Random datetime in [start, end]."""
    delta = end - start
    sec = random.randint(0, int(delta.total_seconds()))
    return start + timedelta(seconds=sec)


def main() -> None:
    random.seed(SEED)
    np.random.seed(SEED)
    ensure_dir(OUTPUT_DIR)

    start_dt = datetime.fromisoformat(START_DATE)
    end_dt = datetime.fromisoformat(END_DATE)

    # -----------------------------
    # 1) events.csv
    # -----------------------------
    events = []
    for i in range(1, N_EVENTS + 1):
        event_id = f"E{i:03d}"

        genre = random.choice(GENRES)
        venue = random.choice(VENUES)
        zone = random.choice(ZONES)

        # date/heure de séance
        event_dt = dt_range(start_dt, end_dt).replace(minute=0, second=0, microsecond=0)
        # plutôt soir / week-end
        hour = random.choice([18, 19, 20, 21])
        event_dt = event_dt.replace(hour=hour)

        capacity = int(np.random.choice([150, 250, 400, 700, 1200, 2000], p=[.10, .18, .22, .20, .18, .12]))
        base_price = float(np.random.choice([12, 15, 18, 22, 28, 35, 45], p=[.10, .18, .20, .20, .16, .10, .06]))

        event_name = f"{genre} — Session {i}"

        events.append(
            dict(
                event_id=event_id,
                event_name=event_name,
                venue_name=venue,
                date_time=event_dt.isoformat(sep=" "),
                capacity=capacity,
                base_price=base_price,
                genre=genre,
                quartier_zone=zone,
            )
        )

    df_events = pd.DataFrame(events).sort_values("date_time").reset_index(drop=True)

    # -----------------------------
    # 2) transactions.csv
    # -----------------------------
    tx_rows = []
    tx_id = 1

    tariff_multiplier = {
        "plein": 1.00,
        "reduit": 0.80,
        "early_bird": 0.75,
        "last_minute": 0.90,
    }
    channel_fee = {
        "web": 1.00,
        "partenaire": 1.02,
        "guichet": 1.00,
        "pass": 0.00,
    }

    geo_values = ["local", "touriste"]
    geo_weights = [0.78, 0.22]

    def sample_lead_time(tariff: str) -> int:
        if tariff == "early_bird":
            return int(np.clip(np.random.normal(35, 12), 7, 90))
        if tariff == "last_minute":
            return int(np.clip(np.random.normal(2, 2), 0, 10))
        return int(np.clip(np.random.normal(14, 10), 0, 60))

    def sample_qty() -> int:
        return int(np.random.choice([1, 2, 3, 4, 5], p=[0.52, 0.30, 0.12, 0.05, 0.01]))

    # Fill-rate cible réaliste par event (tu peux ajuster)
    def sample_fill_target(genre: str, tier: str) -> float:
        # Base par genre (léger biais)
        base_by_genre = {
            "Festival": 0.80,
            "Concert": 0.78,
            "Stand-up": 0.74,
            "Théâtre": 0.70,
            "Danse": 0.68,
            "Projection": 0.62,
            "Conférence": 0.58,
        }
        base = base_by_genre.get(genre, 0.70)

        # Tiers "réalistes"
        tier_params = {
            "sold_out": (0.97, 0.02),   # moyenne, std
            "good":     (0.86, 0.05),
            "mid":      (0.70, 0.06),
            "flop":     (0.45, 0.07),
            "special":  (0.62, 0.10),   # imprévisible
        }
        mu, sigma = tier_params[tier]

        # On combine : genre influence un peu, tier pilote vraiment
        target = np.random.normal(mu, sigma) + (base - 0.70) * 0.35

        # bornes réalistes
        if tier == "sold_out":
            return float(np.clip(target, 0.92, 1.00))
        if tier == "flop":
            return float(np.clip(target, 0.30, 0.60))
        return float(np.clip(target, 0.35, 0.98))

    # Répartition réaliste sur N_EVENTS
    tiers = (["sold_out"] * 3) + (["good"] * 6) + (["mid"] * 10) + (["flop"] * 3) + (["special"] * 2)
    tiers = tiers[:len(df_events)]
    random.shuffle(tiers)

    # Pour debug si tu veux voir la répartition
    df_events = df_events.copy()
    df_events["tier"] = tiers

    for _, ev in df_events.iterrows():
        ev_dt = datetime.fromisoformat(str(ev["date_time"]))
        capacity = int(ev["capacity"])
        base = float(ev["base_price"])

        fill_target = sample_fill_target(ev["genre"], ev["tier"])
        target_tickets = max(0, int(round(capacity * fill_target)))

        tickets_sold = 0

        while tickets_sold < target_tickets:
            tariff = pick_weighted(TARIFFS, [0.58, 0.18, 0.14, 0.10], size=1)[0]
            # "special" = ventes plus tardives (pub tard, météo, concurrence…)
            if ev.get("tier") == "special":
                tariff = pick_weighted(TARIFFS, [0.50, 0.16, 0.08, 0.26], size=1)[0]  # + last_minute

            channel = pick_weighted(CHANNELS, [0.68, 0.12, 0.14, 0.06], size=1)[0]
            buyer_geo = pick_weighted(geo_values, geo_weights, size=1)[0]

            lead_days = sample_lead_time(tariff)
            purchase_dt = ev_dt - timedelta(days=lead_days) + timedelta(
                hours=random.randint(9, 21),
                minutes=random.choice([0, 10, 20, 30, 40, 50])
            )
            if purchase_dt > ev_dt:
                purchase_dt = ev_dt - timedelta(hours=random.randint(1, 6))

            qty = sample_qty()

            # IMPORTANT: on ne dépasse pas l'objectif
            if tickets_sold + qty > target_tickets:
                qty = target_tickets - tickets_sold
            if qty <= 0:
                break

            if channel == "pass":
                total = 0.0
            else:
                unit = base * tariff_multiplier[tariff] * channel_fee[channel]
                unit = max(5.0, unit + np.random.normal(0, 0.6))
                total = round(unit * qty, 2)

            tx_rows.append(
                dict(
                    transaction_id=f"T{tx_id:06d}",
                    event_id=ev["event_id"],
                    purchase_datetime=purchase_dt.isoformat(sep=" "),
                    tickets_qty=qty,
                    price_paid_total=total,
                    channel=channel,
                    tariff=tariff,
                    buyer_geo=buyer_geo,
                    lead_time_days=lead_days,
                )
            )
            tx_id += 1
            tickets_sold += qty

    df_tx = pd.DataFrame(tx_rows)


    # -----------------------------
    # 3) attendance.csv (optionnel mais utile)
    # -----------------------------
    # proba no-show un peu plus forte si achat très tôt, et si "touriste"
    att_rows = []
    tier_map = dict(zip(df_events["event_id"], df_events.get("tier", ["mid"] * len(df_events))))

    for _, r in df_tx.iterrows():
        lead = int(r["lead_time_days"])
        geo = r["buyer_geo"]
        channel = r["channel"]

        tier = tier_map.get(r["event_id"], "mid")
        if tier == "special":
            p_attend -= 0.04


        # base attendance
        p_attend = 0.92
        if lead >= 45:
            p_attend -= 0.05
        if lead >= 75:
            p_attend -= 0.04
        if geo == "touriste":
            p_attend -= 0.03
        if channel == "pass":
            p_attend -= 0.02

        p_attend = float(np.clip(p_attend, 0.75, 0.98))
        attended = 1 if random.random() < p_attend else 0

        att_rows.append(
            dict(
                transaction_id=r["transaction_id"],
                attended=attended
            )
        )

    df_att = pd.DataFrame(att_rows)

    # -----------------------------
    # Save
    # -----------------------------
    events_path = OUTPUT_DIR / "events.csv"
    tx_path = OUTPUT_DIR / "transactions.csv"
    att_path = OUTPUT_DIR / "attendance.csv"

    df_events.to_csv(events_path, index=False, encoding="utf-8")
    df_tx.to_csv(tx_path, index=False, encoding="utf-8")
    df_att.to_csv(att_path, index=False, encoding="utf-8")

    print("✅ Génération terminée")
    print(f"- {events_path}  ({len(df_events)} lignes)")
    print(f"- {tx_path}  ({len(df_tx)} lignes)")
    print(f"- {att_path}  ({len(df_att)} lignes)")
    print("Astuce: ouvre les CSV dans Excel / Power BI ou fais un quick check avec pandas.")


if __name__ == "__main__":
    main()
