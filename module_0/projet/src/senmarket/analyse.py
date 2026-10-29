"""Indicateurs commerciaux calculés à partir des tables SenMarket nettoyées.

Définitions (volontairement explicites) :
  - chiffre d'affaires = somme de ``montant_xof`` des lignes de commande
    acceptées, quel que soit le statut de la commande ou du paiement ;
  - panier moyen = moyenne du chiffre d'affaires par ``commande_id`` ;
  - taux de conversion des sessions = part des sessions de navigation qui
    contiennent au moins un événement ``debut_paiement``.

Lancement :
    python -m src.senmarket.analyse --run-date 2026-10-28
"""

from __future__ import annotations

import argparse
import logging
from datetime import date
from pathlib import Path

import pandas as pd

from .chemins import dossier_partition
from .nettoyage import COLONNES_DATE, VALEUR_INCONNUE

LOGGER = logging.getLogger(__name__)

TABLES_ANALYSE = ("clients", "produits", "commandes", "lignes_commande", "navigation")
EVENEMENT_CONVERSION = "debut_paiement"


def charger_tables(
    run_date: date,
    racine_donnees: Path | None = None,
) -> dict[str, pd.DataFrame]:
    """Charger depuis le Parquet les tables acceptées nécessaires à l'analyse."""
    dossier = dossier_partition("processed", run_date, racine_donnees)
    if not dossier.is_dir():
        raise FileNotFoundError(
            f"Partition nettoyée introuvable : {dossier}. "
            f"Lancez d'abord : python -m src.senmarket.nettoyage --run-date {run_date.isoformat()}"
        )

    tables: dict[str, pd.DataFrame] = {}
    for nom_table in TABLES_ANALYSE:
        chemin = dossier / f"{nom_table}.parquet"
        if not chemin.is_file():
            raise FileNotFoundError(f"Table nettoyée introuvable : {chemin}")
        df = pd.read_parquet(chemin)
        # Précaution : d'anciennes partitions peuvent stocker les dates en texte.
        for colonne in COLONNES_DATE.get(nom_table, ()):
            df[colonne] = pd.to_datetime(df[colonne], errors="coerce")
        tables[nom_table] = df
    return tables


def construire_lignes_enrichies(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Joindre chaque ligne de commande à sa date, à la localisation du client et au produit.

    Les clés des tables de dimension sont uniques après nettoyage : les
    jointures ne doivent donc pas changer le nombre de lignes. Cela est vérifié
    et une erreur est levée dans le cas contraire.
    """
    lignes = tables["lignes_commande"]
    commandes = tables["commandes"][["commande_id", "client_id", "date_commande"]]
    clients = tables["clients"][["client_id", "ville", "region"]]
    produits = tables["produits"][["produit_id", "nom_produit", "categorie"]]

    enrichies = (
        lignes.merge(commandes, on="commande_id", how="left")
        .merge(clients, on="client_id", how="left")
        .merge(produits, on="produit_id", how="left")
    )
    if len(enrichies) != len(lignes):
        raise ValueError(
            "Les jointures ont modifié le nombre de lignes : clés dupliquées "
            "dans une table de dimension."
        )

    for colonne in ("ville", "region"):
        enrichies[colonne] = enrichies[colonne].fillna(VALEUR_INCONNUE)
    return enrichies


def chiffre_affaires_par(enrichies: pd.DataFrame, colonnes: list[str]) -> pd.DataFrame:
    """Agréger chiffre d'affaires, commandes et quantités selon les colonnes données."""
    resultat = (
        enrichies.groupby(colonnes, as_index=False)
        .agg(
            nombre_commandes=("commande_id", "nunique"),
            nombre_lignes=("ligne_commande_id", "count"),
            chiffre_affaires_xof=("montant_xof", "sum"),
            quantite_vendue=("quantite", "sum"),
        )
        .sort_values("chiffre_affaires_xof", ascending=False)
    )
    return resultat.reset_index(drop=True)


def chiffre_affaires_mensuel(enrichies: pd.DataFrame) -> pd.DataFrame:
    """Chiffre d'affaires par mois calendaire (ordre chronologique)."""
    avec_mois = enrichies.assign(mois=enrichies["date_commande"].dt.to_period("M").astype(str))
    resultat = chiffre_affaires_par(avec_mois, ["mois"])
    return resultat.sort_values("mois").reset_index(drop=True)


def calculer_indicateurs(
    tables: dict[str, pd.DataFrame],
    enrichies: pd.DataFrame,
) -> dict[str, float]:
    """Calculer les indicateurs principaux."""
    ca_par_commande = enrichies.groupby("commande_id")["montant_xof"].sum()

    navigation = tables["navigation"]
    sessions_total = navigation["session_id"].nunique()
    sessions_conversion = navigation.loc[
        navigation["type_evenement"] == EVENEMENT_CONVERSION, "session_id"
    ].nunique()

    return {
        "nombre_clients": int(len(tables["clients"])),
        "nombre_commandes": int(len(tables["commandes"])),
        "nombre_lignes_commande": int(len(enrichies)),
        "chiffre_affaires_total_xof": int(enrichies["montant_xof"].sum()),
        "panier_moyen_xof": round(float(ca_par_commande.mean()), 2),
        "quantite_totale": int(enrichies["quantite"].sum()),
        "nombre_villes": int(
            tables["clients"].loc[tables["clients"]["ville"] != VALEUR_INCONNUE, "ville"].nunique()
        ),  # « Inconnue » n'est pas une vraie ville
        "nombre_produits": int(tables["produits"]["produit_id"].nunique()),
        "taux_conversion_sessions": (
            round(sessions_conversion / sessions_total, 4) if sessions_total else 0.0
        ),
    }


def executer_analyse(
    run_date: date,
    racine_donnees: Path | None = None,
) -> dict[str, Path]:
    """Exécuter l'analyse complète et écrire les CSV de résultats.

    Les fichiers sont écrits dans ``processed/date=<run_date>/analyses/``.
    Retourne une correspondance ``nom -> chemin du fichier``.
    """
    tables = charger_tables(run_date, racine_donnees)
    enrichies = construire_lignes_enrichies(tables)

    dossier = dossier_partition("processed", run_date, racine_donnees) / "analyses"
    dossier.mkdir(exist_ok=True)

    indicateurs = calculer_indicateurs(tables, enrichies)
    sorties = {
        "indicateurs": pd.DataFrame(list(indicateurs.items()), columns=["indicateur", "valeur"]),
        "analyse_par_ville": chiffre_affaires_par(enrichies, ["ville"]),
        "analyse_par_produit": chiffre_affaires_par(enrichies, ["nom_produit", "categorie"]),
        "ca_mensuel": chiffre_affaires_mensuel(enrichies),
    }

    fichiers: dict[str, Path] = {}
    for nom, df in sorties.items():
        chemin = dossier / f"{nom}.csv"
        df.to_csv(chemin, index=False)
        fichiers[nom] = chemin
        LOGGER.info("Analyse écrite : %s (%d lignes)", chemin.name, len(df))

    LOGGER.info("Indicateurs : %s", indicateurs)
    return fichiers


def main() -> None:
    """Point d'entrée en ligne de commande."""
    parser = argparse.ArgumentParser(description="Calculer les indicateurs SenMarket.")
    parser.add_argument("--run-date", type=date.fromisoformat, required=True)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    try:
        fichiers = executer_analyse(args.run_date)
    except FileNotFoundError as erreur:
        raise SystemExit(f"ERREUR : {erreur}")

    print("\n=== INDICATEURS ===")
    print(pd.read_csv(fichiers["indicateurs"]).to_string(index=False))


if __name__ == "__main__":
    main()
