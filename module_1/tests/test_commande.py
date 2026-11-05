"""Tests des commandes : concurrence et atomicité, dans un schéma jetable (essai_tests_commande)."""
import threading

import pytest

from senmarket_bases.commande import (
    PlantageSimule,
    StockInsuffisant,
    passer_commande_atomique,
    passer_commande_naive,
    passer_commande_serializable,
    passer_commande_verrou,
)
from senmarket_bases.connexions import connexion_postgres
from senmarket_bases.experience_concurrence import connexion_acheteur, remettre_a_zero
from senmarket_bases.preuves_contraintes import creer_schema, supprimer_schema

SCHEMA = "essai_tests_commande"
PRODUIT = "PRO1"
CLIENT = "CLI1"
REMEDES = {
    "atomique": passer_commande_atomique,
    "verrou": passer_commande_verrou,
    "serializable": passer_commande_serializable,
}
DONNEES = [
    "INSERT INTO vendeurs (vendeur_id, nom_vendeur, ville, region) "
    "VALUES ('VEN1', 'Vendeur Un', 'Dakar', 'Dakar')",
    "INSERT INTO clients (client_id, nom_client, ville, region, date_inscription) "
    "VALUES ('CLI1', 'Awa Diop', 'Dakar', 'Dakar', '2026-01-01')",
    "INSERT INTO produits (produit_id, nom_produit, categorie, vendeur_id, prix_catalogue_xof, "
    "actif, stock) VALUES ('PRO1', 'Téléphone', 'Électronique', 'VEN1', 85000, true, 1)",
]


@pytest.fixture(scope="module")
def principale():
    """Connexion de contrôle sur un schéma jetable, supprimé à la fin."""
    conn = connexion_postgres()
    conn.autocommit = True
    creer_schema(conn, SCHEMA)
    for sql in DONNEES:
        conn.execute(sql)
    yield conn
    supprimer_schema(conn, SCHEMA)
    conn.close()


def _compter(conn, table: str) -> int:
    return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def _stock(conn) -> int:
    return conn.execute("SELECT stock FROM produits WHERE produit_id = %s", (PRODUIT,)).fetchone()[0]


def _lancer(commande, connexions, essai: int) -> list[str]:
    """Tous les acheteurs partent en même temps sur le même article."""
    barriere = threading.Barrier(len(connexions))
    resultats = [""] * len(connexions)

    def acheteur(i: int) -> None:
        barriere.wait()
        try:
            commande(connexions[i], f"{essai}_{i}", CLIENT, PRODUIT, pause=0.005)
            resultats[i] = "ok"
        except StockInsuffisant:
            resultats[i] = "refusee"
        except Exception as erreur:
            resultats[i] = f"erreur : {type(erreur).__name__}"

    threads = [threading.Thread(target=acheteur, args=(i,)) for i in range(len(connexions))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return resultats


# --- Concurrence : 8 acheteurs, 1 article -----------------------------------------

@pytest.mark.parametrize("nom", REMEDES)
def test_un_seul_acheteur_obtient_le_dernier_article(principale, nom):
    connexions = [connexion_acheteur(SCHEMA) for _ in range(8)]
    try:
        for essai in range(20):
            remettre_a_zero(principale, PRODUIT)
            resultats = _lancer(REMEDES[nom], connexions, essai)
            assert resultats.count("ok") == 1, resultats
            assert resultats.count("refusee") == 7, resultats
            assert _stock(principale) == 0
            assert _compter(principale, "lignes_commande") == 1
    finally:
        for c in connexions:
            c.close()


def test_la_version_naive_vend_plusieurs_fois_le_meme_article(principale):
    """Contrôle : le test détecte bien le bug (sinon il ne prouverait rien)."""
    connexions = [connexion_acheteur(SCHEMA) for _ in range(8)]
    try:
        meilleur = 0
        for essai in range(10):
            remettre_a_zero(principale, PRODUIT)
            meilleur = max(meilleur, _lancer(passer_commande_naive, connexions, essai).count("ok"))
        assert meilleur > 1
    finally:
        for c in connexions:
            c.close()


# --- Atomicité : un plantage ne laisse aucune écriture ----------------------------

@pytest.mark.parametrize("nom", REMEDES)
def test_un_plantage_ne_laisse_aucune_ecriture(principale, nom):
    remettre_a_zero(principale, PRODUIT)
    conn = connexion_acheteur(SCHEMA)
    try:
        with pytest.raises(PlantageSimule):
            REMEDES[nom](conn, "crash", CLIENT, PRODUIT, planter_avant_paiement=True)
    finally:
        conn.close()
    assert _compter(principale, "commandes") == 0
    assert _compter(principale, "lignes_commande") == 0
    assert _compter(principale, "paiements") == 0
    assert _stock(principale) == 1          # le stock n'a pas été débité


def test_la_version_naive_laisse_une_commande_orpheline(principale):
    """Contrôle : le test d'atomicité détecte bien le bug de la version naïve."""
    remettre_a_zero(principale, PRODUIT)
    conn = connexion_acheteur(SCHEMA)
    try:
        with pytest.raises(PlantageSimule):
            passer_commande_naive(conn, "crash", CLIENT, PRODUIT, planter_avant_paiement=True)
    finally:
        conn.close()
    assert _compter(principale, "commandes") == 1
    assert _compter(principale, "paiements") == 0
    assert _stock(principale) == 0


# --- Refus normal : plus de stock, sans aucune écriture ---------------------------

@pytest.mark.parametrize("nom", REMEDES)
def test_refus_quand_il_n_y_a_plus_de_stock(principale, nom):
    remettre_a_zero(principale, PRODUIT, stock=0)
    conn = connexion_acheteur(SCHEMA)
    try:
        with pytest.raises(StockInsuffisant):
            REMEDES[nom](conn, "refus", CLIENT, PRODUIT)
    finally:
        conn.close()
    assert _compter(principale, "commandes") == 0
    assert _stock(principale) == 0
