"""Tests du chargeur PostgreSQL (chapitre 2.2).

Ils exigent que PostgreSQL tourne (dc up -d) et que la partition 2026-10-29
soit enrichie. Tout se passe dans un schéma jetable (essai_chargeur) :
principal et volume ne sont jamais touchés.
"""
import pytest
from psycopg.pq import TransactionStatus

from senmarket_bases import charger_postgres as cp
from senmarket_bases.charger_postgres import (
    ORDRE,
    ErreurChargement,
    charger,
    empreintes,
    preparer,
)
from senmarket_bases.connexions import ErreurConnexion, connexion_postgres
from senmarket_bases.enrichissement import DOSSIER_PROCESSED, DOSSIER_SORTIE
from senmarket_bases.preuves_contraintes import creer_schema, supprimer_schema

DATE = "2026-10-29"
SCHEMA = "essai_chargeur"


@pytest.fixture(scope="module")
def conn():
    """Connexion sur un schéma jetable, supprimé à la fin."""
    if not (DOSSIER_PROCESSED / f"date={DATE}").exists() or not (DOSSIER_SORTIE / f"date={DATE}").exists():
        pytest.skip(f"Partition {DATE} absente ou non enrichie")
    connexion = connexion_postgres()
    connexion.autocommit = True
    creer_schema(connexion, SCHEMA)
    yield connexion
    supprimer_schema(connexion, SCHEMA)
    connexion.close()


@pytest.fixture(scope="module")
def donnees():
    """Les huit tables telles que le chargeur les envoie à COPY."""
    return preparer(DATE, DOSSIER_PROCESSED, DOSSIER_SORTIE)


@pytest.fixture(scope="module")
def premier_chargement(conn):
    return charger(DATE, SCHEMA, conn=conn)


# --- Les chiffres sont les bons ---------------------------------------------
def test_nombres_de_lignes_egaux(conn, donnees, premier_chargement):
    for nom in ORDRE:
        charge = conn.execute(f'SELECT count(*) FROM "{SCHEMA}"."{nom}"').fetchone()[0]
        assert charge == len(donnees[nom]), nom


@pytest.mark.parametrize("nom", ["lignes_commande", "paiements"])
def test_sommes_des_montants_egales(conn, donnees, premier_chargement, nom):
    en_base = conn.execute(f'SELECT sum(montant_xof) FROM "{SCHEMA}"."{nom}"').fetchone()[0]
    assert int(en_base) == int(donnees[nom]["montant_xof"].sum())


# --- Idempotence -------------------------------------------------------------
def test_double_execution_ne_change_rien(conn, premier_chargement):
    avant = empreintes(conn, SCHEMA)
    charger(DATE, SCHEMA, conn=conn)
    assert empreintes(conn, SCHEMA) == avant


# --- Atomicité ---------------------------------------------------------------
def test_echec_au_milieu_de_paiements_ne_laisse_rien(conn, donnees, premier_chargement, monkeypatch):
    """Un paiement reçoit la référence d'un autre : UNIQUE refuse pendant le COPY de paiements."""
    avant = empreintes(conn, SCHEMA)

    abime = {nom: df.copy() for nom, df in donnees.items()}
    paiements = abime["paiements"]
    hors_especes = paiements.index[paiements["methode_paiement"] != "Espèces"]
    paiements.loc[hors_especes[-1], "reference_transaction"] = \
        paiements.loc[hors_especes[0], "reference_transaction"]
    monkeypatch.setattr(cp, "preparer", lambda *args, **kwargs: abime)

    with pytest.raises(ErreurChargement, match="23505"):
        charger(DATE, SCHEMA, conn=conn)

    assert empreintes(conn, SCHEMA) == avant                         # la base est revenue à l'état d'avant
    assert conn.info.transaction_status == TransactionStatus.IDLE    # aucune transaction restée ouverte


# --- Erreurs claires ---------------------------------------------------------
def test_partition_inexistante_liste_les_partitions():
    with pytest.raises(ErreurChargement, match="Partitions disponibles"):
        preparer("2030-01-01", DOSSIER_PROCESSED, DOSSIER_SORTIE)


def test_date_invalide():
    with pytest.raises(ErreurChargement, match="AAAA-MM-JJ"):
        charger("31/12/2026", SCHEMA)


def test_parquet_manquant(tmp_path):
    (tmp_path / f"date={DATE}").mkdir()
    with pytest.raises(ErreurChargement, match="Fichier manquant"):
        preparer(DATE, tmp_path, DOSSIER_SORTIE)


def test_fichier_enrichi_manquant(tmp_path):
    (tmp_path / f"date={DATE}").mkdir()
    with pytest.raises(ErreurChargement, match="enrichi manquant"):
        preparer(DATE, DOSSIER_PROCESSED, tmp_path)


def test_schema_introuvable_liste_les_schemas(conn):
    with pytest.raises(ErreurChargement, match="Schémas existants"):
        charger(DATE, "essai_inexistant", conn=conn)


def test_base_injoignable(monkeypatch):
    monkeypatch.setenv("POSTGRES_PORT", "1")
    with pytest.raises(ErreurConnexion):
        charger(DATE, SCHEMA)