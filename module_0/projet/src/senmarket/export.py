"""Export of the cleaned tables to JSON Lines.

CSV and Parquet are already written by the cleaning step. JSON Lines (one JSON
object per line) is added because it is the natural input format for the
ingestion step (APIs, Kafka, dlt).

Run it with:
    python -m src.senmarket.export --run-date 2026-10-28
"""

from __future__ import annotations

import argparse
import logging
from datetime import date
from pathlib import Path

import pandas as pd

from .chemins import dossier_partition
from .nettoyage import TABLES

LOGGER = logging.getLogger(__name__)


def exporter_json_lines(
    run_date: date,
    racine_donnees: Path | None = None,
) -> dict[str, Path]:
    """Convert every accepted Parquet table to ``json/<table>.jsonl``.

    Returns a mapping ``table -> written file``.
    """
    dossier_propre = dossier_partition("processed", run_date, racine_donnees)
    if not dossier_propre.is_dir():
        raise FileNotFoundError(
            f"Partition nettoyée introuvable : {dossier_propre}. "
            f"Lancez d'abord : python -m src.senmarket.nettoyage --run-date {run_date.isoformat()}"
        )

    dossier_json = dossier_propre / "json"
    dossier_json.mkdir(exist_ok=True)

    fichiers: dict[str, Path] = {}
    for nom_table in TABLES:
        source = dossier_propre / f"{nom_table}.parquet"
        if not source.is_file():
            raise FileNotFoundError(f"Table nettoyée introuvable : {source}")

        df = pd.read_parquet(source)
        cible = dossier_json / f"{nom_table}.jsonl"
        # ISO dates and real accents keep the file readable and portable.
        df.to_json(cible, orient="records", lines=True, date_format="iso", force_ascii=False)
        fichiers[nom_table] = cible
        LOGGER.info("Export JSON Lines : %s (%d lignes)", cible.name, len(df))

    return fichiers


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Exporter les tables nettoyées en JSON Lines.")
    parser.add_argument("--run-date", type=date.fromisoformat, required=True)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    try:
        exporter_json_lines(args.run_date)
    except FileNotFoundError as erreur:
        raise SystemExit(f"ERREUR : {erreur}")


if __name__ == "__main__":
    main()