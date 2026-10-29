"""Contrôles de qualité des données sur une partition nettoyée.

La partition contrôlée est, par ordre de priorité :
  1. celle indiquée par la variable d'environnement ``SENMARKET_RUN_DATE`` ;
  2. sinon la plus récente partition contenant un bilan de nettoyage.

S'il n'existe aucune partition complète, les tests sont ignorés (« skip ») et
ne sont jamais mis en échec par un dossier vide.
"""

from __future__ import annotations

import os
from datetime import date

import pandas as pd
import pytest

from src.senmarket.chemins import dossier_partition, partitions_disponibles
from src.senmarket.nettoyage import (
    CHAMPS_OPTIONNELS,
    CLES_PRIMAIRES,
    COLONNE_MOTIF_REJET,
    COLONNES_DATE,
    COLONNES_REQUISES,
    RELATIONS,
    TABLES,
)


@pytest.fixture(scope="module")
def run_date() -> date:
    """Choisir la partition à contrôler (voir la docstring du module)."""
    valeur = os.environ.get("SENMARKET_RUN_DATE")
    if valeur:
        return date.fromisoformat(valeur)

    completes = [
        d for d in partitions_disponibles("rejected")
        if (dossier_partition("rejected", d) / "bilan_nettoyage.csv").is_file()
    ]
    if not completes:
        pytest.skip("Aucune partition nettoyée disponible.")
    return max(completes)


def lire_acceptee(nom_table: str, run_date: date) -> pd.DataFrame:
    """Lire une table acceptée en texte (pour comparer exactement les clés)."""
    chemin = dossier_partition("processed", run_date) / f"{nom_table}.csv"
    assert chemin.is_file(), f"Fichier accepté introuvable : {chemin}"
    return pd.read_csv(chemin, dtype=str)


def lire_rejetee(nom_table: str, run_date: date) -> pd.DataFrame:
    """Lire une table de quarantaine en texte."""
    chemin = dossier_partition("rejected", run_date) / f"{nom_table}_rejetes.csv"
    assert chemin.is_file(), f"Fichier de rejets introuvable : {chemin}"
    return pd.read_csv(chemin, dtype=str)


@pytest.mark.parametrize("nom_table", TABLES)
def test_schema_des_tables_acceptees(nom_table, run_date):
    """Chaque table acceptée contient toutes ses colonnes requises."""
    df = lire_acceptee(nom_table, run_date)
    assert set(COLONNES_REQUISES[nom_table]) <= set(df.columns)


@pytest.mark.parametrize("nom_table", TABLES)
def test_cles_primaires_uniques(nom_table, run_date):
    """Les clés primaires sont présentes et uniques dans les lignes acceptées."""
    cle = CLES_PRIMAIRES[nom_table]
    valeurs = lire_acceptee(nom_table, run_date)[cle]
    assert valeurs.notna().all(), f"{nom_table}.{cle} contient des valeurs vides"
    assert valeurs.is_unique, f"{nom_table}.{cle} contient des doublons"


def test_quantites_et_montants_coherents(run_date):
    """Les quantités sont positives et montant == quantité x prix unitaire."""
    lignes = lire_acceptee("lignes_commande", run_date)
    quantite = pd.to_numeric(lignes["quantite"])
    prix = pd.to_numeric(lignes["prix_unitaire_xof"])
    montant = pd.to_numeric(lignes["montant_xof"])

    assert (quantite > 0).all()
    assert (prix > 0).all()
    assert (montant == quantite * prix).all()


@pytest.mark.parametrize("nom_table", list(RELATIONS))
def test_relations_entre_tables_acceptees(nom_table, run_date):
    """Toute clé étrangère non vide pointe vers une ligne parente acceptée."""
    enfant = lire_acceptee(nom_table, run_date)
    for colonne, parent in RELATIONS[nom_table].items():
        valeurs = enfant[colonne]
        if colonne in CHAMPS_OPTIONNELS.get(nom_table, frozenset()):
            valeurs = valeurs.dropna()  # clé étrangère optionnelle : vide autorisé
        cles_parent = set(lire_acceptee(parent, run_date)[CLES_PRIMAIRES[parent]])
        inconnues = set(valeurs) - cles_parent
        assert not inconnues, f"{nom_table}.{colonne} : clés inconnues {sorted(inconnues)[:5]}"


@pytest.mark.parametrize("nom_table", [t for t in TABLES if t in COLONNES_DATE])
def test_aucune_date_future(nom_table, run_date):
    """Aucune date acceptée n'est postérieure à la date d'exécution."""
    df = lire_acceptee(nom_table, run_date)
    for colonne in COLONNES_DATE[nom_table]:
        dates = pd.to_datetime(df[colonne], errors="raise")
        assert (dates <= pd.Timestamp(run_date)).all(), f"{nom_table}.{colonne} : date future"


@pytest.mark.parametrize("nom_table", TABLES)
def test_rejets_ont_un_motif(nom_table, run_date):
    """Chaque ligne en quarantaine explique pourquoi elle a été rejetée."""
    rejetes = lire_rejetee(nom_table, run_date)
    if rejetes.empty:
        return
    assert COLONNE_MOTIF_REJET in rejetes.columns
    assert rejetes[COLONNE_MOTIF_REJET].notna().all()
    assert (rejetes[COLONNE_MOTIF_REJET].str.strip() != "").all()


def test_bilan_coherent_avec_les_fichiers(run_date):
    """Le bilan correspond aux fichiers réels et brut == accepté + rejeté."""
    chemin = dossier_partition("rejected", run_date) / "bilan_nettoyage.csv"
    assert chemin.is_file(), "Le bilan de nettoyage est absent"
    bilan = pd.read_csv(chemin).set_index("table")

    assert set(bilan.index) == set(TABLES)
    for nom_table in TABLES:
        ligne = bilan.loc[nom_table]
        assert ligne["lignes_brutes"] == ligne["lignes_acceptees"] + ligne["lignes_rejetees"]
        assert ligne["lignes_acceptees"] == len(lire_acceptee(nom_table, run_date))
        assert ligne["lignes_rejetees"] == len(lire_rejetee(nom_table, run_date))
