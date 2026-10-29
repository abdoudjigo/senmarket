"""Point d'entrée du pipeline SenMarket.

Étapes, dans l'ordre :
  0. tests unitaires des règles de nettoyage
  1. génération de la partition brute (uniquement avec --generer)
  2. nettoyage + quarantaine
  3. export JSON Lines
  4. analyse commerciale
  5. graphiques
  6. tests de qualité sur la partition produite

Exemples :
    python scripts/run_pipeline.py --run-date 2026-10-28
    python scripts/run_pipeline.py --run-date 2026-10-29 --generer --rows 10000
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

# Rend le package ``src`` importable quand le fichier est lancé comme simple script.
RACINE_PROJET = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE_PROJET))

from src.senmarket.analyse import executer_analyse  # noqa: E402
from src.senmarket.chemins import DOSSIER_LOGS, dossier_partition  # noqa: E402
from src.senmarket.export import exporter_json_lines  # noqa: E402
from src.senmarket.nettoyage import nettoyer_partition  # noqa: E402
from src.senmarket.visualisation import generer_graphiques  # noqa: E402

LOGGER = logging.getLogger("pipeline")
NB_ETAPES = 6


def configurer_logging(run_date: date) -> None:
    """Journaliser dans la console et dans ``logs/pipeline_<run_date>.log``."""
    DOSSIER_LOGS.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(DOSSIER_LOGS / f"pipeline_{run_date.isoformat()}.log", encoding="utf-8"),
        ],
    )


def lancer_pytest(cibles: list[str], run_date: date | None = None) -> None:
    """Lancer pytest dans un sous-processus ; lève CalledProcessError en cas d'échec."""
    env = os.environ.copy()
    if run_date is not None:
        # Indique aux tests de qualité quelle partition contrôler.
        env["SENMARKET_RUN_DATE"] = run_date.isoformat()
    subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *cibles],
        cwd=RACINE_PROJET,
        env=env,
        check=True,
    )


def generer_partition(run_date: date, nb_lignes: int, ecraser: bool, defauts: list[str]) -> None:
    """Générer la partition brute, en refusant d'écraser sauf demande explicite."""
    existe = dossier_partition("raw", run_date).is_dir()
    if existe and not ecraser:
        raise FileExistsError(
            f"La partition brute du {run_date.isoformat()} existe déjà. "
            "Ajoutez --ecraser pour la régénérer."
        )
    commande = [
        sys.executable, "-m", "src.senmarket.generateur",
        "--rows", str(nb_lignes),
        "--run-date", run_date.isoformat(),
    ]
    # Transmettre les défauts à injecter, s'il y en a.
    if defauts:
        commande += ["--defauts", *defauts]
    subprocess.run(commande, cwd=RACINE_PROJET, check=True)


def executer_pipeline(args: argparse.Namespace) -> None:
    """Exécuter toutes les étapes pour ``args.run_date``."""
    run_date: date = args.run_date
    LOGGER.info("=== DÉMARRAGE DU PIPELINE SENMARKET | run_date=%s ===", run_date)

    # Échouer tout de suite s'il n'y a rien à traiter et que la génération n'est pas demandée.
    if not args.generer and not dossier_partition("raw", run_date).is_dir():
        raise FileNotFoundError(
            f"Partition brute introuvable pour le {run_date.isoformat()}. "
            "Utilisez --generer pour la créer, ou choisissez une date existante."
        )

    if not args.sans_tests:
        LOGGER.info("[0/%d] Tests unitaires du nettoyage", NB_ETAPES)
        lancer_pytest(["tests/test_nettoyage.py"])

    if args.generer:
        LOGGER.info("[1/%d] Génération des données brutes (%d lignes)", NB_ETAPES, args.rows)
        generer_partition(run_date, args.rows, args.ecraser, args.defauts)
    else:
        LOGGER.info("[1/%d] Génération ignorée : partition brute existante", NB_ETAPES)

    LOGGER.info("[2/%d] Nettoyage", NB_ETAPES)
    bilan = nettoyer_partition(run_date)
    for table, compteurs in bilan.items():
        LOGGER.info("  %-16s %s", table, compteurs)

    LOGGER.info("[3/%d] Export JSON Lines", NB_ETAPES)
    exporter_json_lines(run_date)

    LOGGER.info("[4/%d] Analyse commerciale", NB_ETAPES)
    executer_analyse(run_date)

    LOGGER.info("[5/%d] Graphiques", NB_ETAPES)
    generer_graphiques(run_date)

    if not args.sans_tests:
        LOGGER.info("[6/%d] Tests de qualité sur la partition produite", NB_ETAPES)
        lancer_pytest(["tests/test_qualite_donnees.py"], run_date)

    LOGGER.info("=== PIPELINE TERMINÉ AVEC SUCCÈS ===")


def lire_arguments() -> argparse.Namespace:
    """Lire les arguments de la ligne de commande."""
    parser = argparse.ArgumentParser(description="Pipeline SenMarket de bout en bout.")
    parser.add_argument("--run-date", type=date.fromisoformat, default=date.today(),
                        help="Date de la partition (AAAA-MM-JJ). Défaut : aujourd'hui.")
    parser.add_argument("--generer", action="store_true",
                        help="Générer la partition brute avant le nettoyage.")
    parser.add_argument("--ecraser", action="store_true",
                        help="Avec --generer : régénérer une partition brute existante.")
    parser.add_argument("--rows", type=int, default=10_000,
                        help="Nombre de lignes de commande à générer (avec --generer).")
    parser.add_argument("--defauts", nargs="*", default=[],
                        help="Défauts à injecter (avec --generer), ex. : doublon_ligne date_future.")
    parser.add_argument("--sans-tests", action="store_true", help="Ne pas lancer pytest.")
    return parser.parse_args()


def main() -> None:
    """Point d'entrée avec messages d'erreur clairs et codes de retour."""
    args = lire_arguments()
    configurer_logging(args.run_date)
    try:
        executer_pipeline(args)
    except (FileNotFoundError, FileExistsError) as erreur:
        LOGGER.error("%s", erreur)
        sys.exit(1)
    except subprocess.CalledProcessError as erreur:
        LOGGER.error("Étape en échec (code %s) : %s", erreur.returncode, " ".join(map(str, erreur.cmd)))
        sys.exit(erreur.returncode or 1)


if __name__ == "__main__":
    main()
