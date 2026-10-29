"""Fonctions de chemins partagées pour l'organisation des données par date.

Tous les modules calculent leurs chemins à partir de ce fichier, afin que la
génération, le nettoyage, l'analyse et les tests s'accordent toujours sur
l'emplacement d'une partition :

    data/<zone>/date=AAAA-MM-JJ/

où <zone> vaut ``raw``, ``processed`` ou ``rejected``.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

# Racine du projet = deux niveaux au-dessus de ce fichier (src/senmarket/chemins.py).
RACINE_PROJET = Path(__file__).resolve().parents[2]
DOSSIER_DONNEES = RACINE_PROJET / "data"
DOSSIER_FIGURES = RACINE_PROJET / "reports" / "figures"
DOSSIER_LOGS = RACINE_PROJET / "logs"

ZONES = ("raw", "processed", "rejected")
PREFIXE_PARTITION = "date="


def _base(racine_donnees: Path | None) -> Path:
    """Retourner la racine des données (par défaut le dossier ``data/`` du projet)."""
    return Path(racine_donnees) if racine_donnees is not None else DOSSIER_DONNEES


def dossier_partition(
    zone: str,
    run_date: date,
    racine_donnees: Path | None = None,
) -> Path:
    """Construire le chemin d'une partition (le dossier peut ne pas exister)."""
    if zone not in ZONES:
        raise ValueError(f"Zone inconnue : {zone!r}. Zones valides : {ZONES}")
    return _base(racine_donnees) / zone / f"{PREFIXE_PARTITION}{run_date.isoformat()}"


def partitions_disponibles(
    zone: str,
    racine_donnees: Path | None = None,
) -> list[date]:
    """Lister les dates de partition existantes d'une zone, de la plus ancienne à la plus récente.

    Les dossiers dont le nom n'est pas un ``date=AAAA-MM-JJ`` valide sont ignorés.
    """
    if zone not in ZONES:
        raise ValueError(f"Zone inconnue : {zone!r}. Zones valides : {ZONES}")
    base = _base(racine_donnees) / zone
    if not base.is_dir():
        return []

    dates: list[date] = []
    for chemin in base.glob(f"{PREFIXE_PARTITION}*"):
        if not chemin.is_dir():
            continue
        try:
            dates.append(date.fromisoformat(chemin.name.removeprefix(PREFIXE_PARTITION)))
        except ValueError:
            continue  # ce n'est pas une partition datée, on l'ignore
    return sorted(dates)
