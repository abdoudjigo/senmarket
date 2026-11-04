"""Passer une commande : la version naïve (volontairement fausse), puis les versions réparées.

La version naïve sert à PROUVER le bug de concurrence avant de le réparer (chapitre 2.4).
"""
import time
from datetime import date

import psycopg


class StockInsuffisant(Exception):
    """Commande refusée : il n'y a plus assez de stock (un refus normal, pas une panne)."""


class PlantageSimule(Exception):
    """Plantage volontaire du programme, pour prouver l'atomicité."""


def passer_commande_naive(
    conn: psycopg.Connection,
    numero: str,
    client_id: str,
    produit_id: str,
    quantite: int = 1,
    pause: float = 0.0,
    planter_avant_paiement: bool = False,
) -> str:
    """Version NAÏVE : lire le stock, vérifier, écrire, puis créer commande, ligne, paiement.

    Volontairement dangereuse : en autocommit, sans transaction ni verrou.
    - pause : délai (en secondes) entre la lecture et l'écriture du stock. Il élargit la
      fenêtre de course et rend la double vente visible.
    - planter_avant_paiement : lève une erreur après la commande et sa ligne, avant le
      paiement (sert à l'étape suivante : l'atomicité).
    """
    if not conn.autocommit:
        raise ValueError("La version naïve s'exécute en autocommit : c'est ce qui la rend dangereuse.")

    # 1. Lire le stock et le prix
    ligne = conn.execute(
        "SELECT stock, prix_catalogue_xof FROM produits WHERE produit_id = %s", (produit_id,)
    ).fetchone()
    if ligne is None:
        raise ValueError(f"Produit inconnu : {produit_id}")
    stock, prix = ligne

    # 2. Vérifier qu'il y en a assez
    if stock < quantite:
        raise StockInsuffisant(f"{produit_id} : stock {stock}, demandé {quantite}")

    # La fenêtre de course : pendant ce délai, l'autre acheteur peut lire la même valeur
    if pause:
        time.sleep(pause)

    # 3. Écrire le nouveau stock : valeur calculée ICI, pas par la base
    conn.execute("UPDATE produits SET stock = %s WHERE produit_id = %s", (stock - quantite, produit_id))

    # 4. Créer la commande et sa ligne
    commande_id = f"CMD_{numero}"
    montant = quantite * prix
    conn.execute(
        "INSERT INTO commandes (commande_id, client_id, date_commande, statut) "
        "VALUES (%s, %s, %s, 'en_preparation')",
        (commande_id, client_id, date.today()),
    )
    conn.execute(
        "INSERT INTO lignes_commande (ligne_commande_id, commande_id, produit_id, quantite, "
        "prix_unitaire_xof, montant_xof) VALUES (%s, %s, %s, %s, %s, %s)",
        (f"LIG_{numero}", commande_id, produit_id, quantite, prix, montant),
    )

    if planter_avant_paiement:
        raise PlantageSimule(f"plantage simulé : {commande_id} existe, son paiement non")

    # 5. Créer le paiement
    conn.execute(
        "INSERT INTO paiements (paiement_id, commande_id, methode_paiement, statut_paiement, "
        "montant_xof, date_paiement, reference_transaction) "
        "VALUES (%s, %s, 'Wave', 'réussi', %s, %s, %s)",
        (f"PAI_{numero}", commande_id, montant, date.today(), f"WAV-{numero}"),
    )
    return commande_id


# ===========================================================================
# Versions réparées (chapitre 2.4) : trois remèdes à la double vente.
# Toutes tournent dans UNE transaction : un plantage annule commande, ligne et stock.
# ===========================================================================
class TropDeConflits(Exception):
    """Trop de nouvelles tentatives en SERIALIZABLE : panne, pas un refus."""


def _ecrire_commande(conn, numero, client_id, produit_id, quantite, prix, planter_avant_paiement) -> str:
    """Écrit commande, ligne et paiement. À appeler DANS une transaction."""
    commande_id = f"CMD_{numero}"
    montant = quantite * prix
    conn.execute(
        "INSERT INTO commandes (commande_id, client_id, date_commande, statut) "
        "VALUES (%s, %s, %s, 'en_preparation')", (commande_id, client_id, date.today()))
    conn.execute(
        "INSERT INTO lignes_commande (ligne_commande_id, commande_id, produit_id, quantite, "
        "prix_unitaire_xof, montant_xof) VALUES (%s, %s, %s, %s, %s, %s)",
        (f"LIG_{numero}", commande_id, produit_id, quantite, prix, montant))
    if planter_avant_paiement:
        raise PlantageSimule(f"plantage simulé : {commande_id} existe, son paiement non")
    conn.execute(
        "INSERT INTO paiements (paiement_id, commande_id, methode_paiement, statut_paiement, "
        "montant_xof, date_paiement, reference_transaction) "
        "VALUES (%s, %s, 'Wave', 'réussi', %s, %s, %s)",
        (f"PAI_{numero}", commande_id, montant, date.today(), f"WAV-{numero}"))
    return commande_id


def passer_commande_atomique(conn, numero, client_id, produit_id, quantite=1,
                             pause=0.0, planter_avant_paiement=False) -> str:
    """Remède 1 : une transaction + mise à jour conditionnelle du stock.

    UPDATE ... WHERE stock >= q lit et écrit en un geste indivisible : le second acheteur
    attend la fin du premier, puis ne trouve plus de stock (0 ligne modifiée).
    """
    with conn.transaction():
        ligne = conn.execute(
            "UPDATE produits SET stock = stock - %s "
            "WHERE produit_id = %s AND stock >= %s RETURNING prix_catalogue_xof",
            (quantite, produit_id, quantite)).fetchone()
        if ligne is None:
            raise StockInsuffisant(f"{produit_id} : stock insuffisant (ou produit inconnu)")
        if pause:
            time.sleep(pause)   # même stress que la version naïve : le verrou est tenu pendant la pause
        return _ecrire_commande(conn, numero, client_id, produit_id, quantite, ligne[0],
                                planter_avant_paiement)


def passer_commande_verrou(conn, numero, client_id, produit_id, quantite=1,
                           pause=0.0, planter_avant_paiement=False) -> str:
    """Remède 2 : une transaction + verrou de ligne (SELECT ... FOR UPDATE).

    Le premier acheteur réserve la ligne du produit jusqu'au COMMIT ; le second attend
    à son SELECT, puis lit le stock déjà mis à jour.
    """
    with conn.transaction():
        ligne = conn.execute(
            "SELECT stock, prix_catalogue_xof FROM produits WHERE produit_id = %s FOR UPDATE",
            (produit_id,)).fetchone()
        if ligne is None:
            raise ValueError(f"Produit inconnu : {produit_id}")
        stock, prix = ligne
        if stock < quantite:
            raise StockInsuffisant(f"{produit_id} : stock {stock}, demandé {quantite}")
        if pause:
            time.sleep(pause)
        conn.execute("UPDATE produits SET stock = %s WHERE produit_id = %s",
                     (stock - quantite, produit_id))
        return _ecrire_commande(conn, numero, client_id, produit_id, quantite, prix,
                                planter_avant_paiement)


def passer_commande_serializable(conn, numero, client_id, produit_id, quantite=1,
                                 pause=0.0, planter_avant_paiement=False, tentatives=50) -> str:
    """Remède 3 : code naïf, mais en isolation SERIALIZABLE, avec nouvelle tentative.

    PostgreSQL détecte que deux transactions se marchent dessus et en annule une
    (erreur 40001) : on rejoue alors toute la commande, qui trouve cette fois stock = 0.
    """
    for essai in range(tentatives):
        try:
            with conn.transaction():
                conn.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")   # 1re instruction
                ligne = conn.execute(
                    "SELECT stock, prix_catalogue_xof FROM produits WHERE produit_id = %s",
                    (produit_id,)).fetchone()
                if ligne is None:
                    raise ValueError(f"Produit inconnu : {produit_id}")
                stock, prix = ligne
                if stock < quantite:
                    raise StockInsuffisant(f"{produit_id} : stock {stock}, demandé {quantite}")
                if pause:
                    time.sleep(pause)
                conn.execute("UPDATE produits SET stock = %s WHERE produit_id = %s",
                             (stock - quantite, produit_id))
                return _ecrire_commande(conn, numero, client_id, produit_id, quantite, prix,
                                        planter_avant_paiement)
        except psycopg.errors.SerializationFailure:
            time.sleep(0.002 * (essai + 1))   # attente croissante avant de rejouer
    raise TropDeConflits(f"{produit_id} : {tentatives} tentatives sans succès")
