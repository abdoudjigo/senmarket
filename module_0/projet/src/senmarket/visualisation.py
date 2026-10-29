"""Graphiques construits à partir des CSV d'analyse.

Lancement :
    python -m src.senmarket.visualisation --run-date 2026-10-28
"""

from __future__ import annotations

import argparse
import logging
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # sortie en fichier uniquement : aucun affichage requis (serveur, CI, WSL)
import matplotlib.pyplot as plt  # noqa: E402  (doit venir après matplotlib.use)
import pandas as pd  # noqa: E402

from .chemins import DOSSIER_FIGURES, dossier_partition  # noqa: E402

LOGGER = logging.getLogger(__name__)

# Matplotlib signale en INFO que les mois sont traités comme des catégories : sans intérêt ici.
logging.getLogger("matplotlib").setLevel(logging.WARNING)

NB_TOP = 10  # nombre de catégories affichées dans les graphiques en barres


def _lire_analyse(run_date: date, nom: str, racine_donnees: Path | None) -> pd.DataFrame:
    """Lire un CSV d'analyse, avec une erreur exploitable s'il est absent."""
    chemin = dossier_partition("processed", run_date, racine_donnees) / "analyses" / f"{nom}.csv"
    if not chemin.is_file():
        raise FileNotFoundError(
            f"Analyse introuvable : {chemin}. "
            f"Lancez d'abord : python -m src.senmarket.analyse --run-date {run_date.isoformat()}"
        )
    return pd.read_csv(chemin)


def _graphique_barres(
    donnees: pd.DataFrame,
    colonne_libelle: str,
    titre: str,
    chemin: Path,
) -> None:
    """Barres horizontales des meilleures catégories par chiffre d'affaires."""
    # Ordre inversé pour que la plus grande barre soit dessinée en haut.
    top = donnees.head(NB_TOP).iloc[::-1]

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.barh(top[colonne_libelle], top["chiffre_affaires_xof"] / 1e6)
    ax.set_title(titre)
    ax.set_xlabel("Chiffre d'affaires (millions de XOF)")
    ax.set_ylabel("")
    ax.grid(axis="x", alpha=0.3)  # les barres partent de zéro : l'échelle reste honnête
    fig.tight_layout()
    fig.savefig(chemin, dpi=150, bbox_inches="tight")
    plt.close(fig)  # libérer la mémoire


def _graphique_evolution(donnees: pd.DataFrame, titre: str, chemin: Path) -> None:
    """Courbe du chiffre d'affaires mensuel."""
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(donnees["mois"], donnees["chiffre_affaires_xof"] / 1e6, marker="o")
    ax.set_title(titre)
    ax.set_xlabel("Mois")
    ax.set_ylabel("Chiffre d'affaires (millions de XOF)")
    ax.set_ylim(bottom=0)  # ne pas tronquer l'axe Y
    ax.grid(alpha=0.3)
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    fig.tight_layout()
    fig.savefig(chemin, dpi=150, bbox_inches="tight")
    plt.close(fig)


def generer_graphiques(
    run_date: date,
    racine_donnees: Path | None = None,
    dossier_figures: Path | None = None,
) -> list[Path]:
    """Créer les graphiques PNG et retourner leurs chemins."""
    dossier_figures = Path(dossier_figures) if dossier_figures else DOSSIER_FIGURES
    dossier_figures.mkdir(parents=True, exist_ok=True)

    par_ville = _lire_analyse(run_date, "analyse_par_ville", racine_donnees)
    par_produit = _lire_analyse(run_date, "analyse_par_produit", racine_donnees)
    mensuel = _lire_analyse(run_date, "ca_mensuel", racine_donnees)

    fichiers = [
        dossier_figures / "chiffre_affaires_par_ville.png",
        dossier_figures / "chiffre_affaires_par_produit.png",
        dossier_figures / "chiffre_affaires_mensuel.png",
    ]
    _graphique_barres(par_ville, "ville", f"Top {NB_TOP} villes par chiffre d'affaires", fichiers[0])
    _graphique_barres(par_produit, "nom_produit", f"Top {NB_TOP} produits par chiffre d'affaires", fichiers[1])
    _graphique_evolution(mensuel, "Évolution mensuelle du chiffre d'affaires", fichiers[2])

    LOGGER.info("Graphiques enregistrés dans : %s", dossier_figures)
    return fichiers


def main() -> None:
    """Point d'entrée en ligne de commande."""
    parser = argparse.ArgumentParser(description="Générer les graphiques SenMarket.")
    parser.add_argument("--run-date", type=date.fromisoformat, required=True)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    try:
        generer_graphiques(args.run_date)
    except FileNotFoundError as erreur:
        raise SystemExit(f"ERREUR : {erreur}")


if __name__ == "__main__":
    main()
