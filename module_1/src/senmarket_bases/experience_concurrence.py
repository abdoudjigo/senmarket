"""Expérience de concurrence : deux acheteurs pour le dernier article.

Tout se passe dans un schéma jetable (essai_concurrence), supprimé à la fin :
principal et volume ne sont jamais touchés.
"""
import threading
import time
from collections.abc import Callable

import psycopg

from senmarket_bases.commande import StockInsuffisant
from senmarket_bases.connexions import connexion_postgres
from senmarket_bases.preuves_contraintes import creer_schema

SCHEMA = "essai_concurrence"
STOCK_DE_DEPART = 1   # un seul article : les deux acheteurs se le disputent


def preparer_schema(conn: psycopg.Connection) -> tuple[str, str, list[str]]:
    """Crée le schéma jetable et y copie un produit flash réel, son vendeur et deux clients.

    Le produit est trouvé par une requête (stock de 1 à 5), jamais par un numéro codé en dur.
    Renvoie (produit_id, nom du produit, [client A, client B]).
    """
    creer_schema(conn, SCHEMA)   # même fichier sql/01_schema.sql que pour le vrai schéma
    produit = conn.execute(
        "SELECT produit_id, nom_produit FROM principal.produits "
        "WHERE stock BETWEEN 1 AND 5 ORDER BY produit_id LIMIT 1"
    ).fetchone()
    if produit is None:
        raise ValueError("Aucun produit flash dans principal : charge d'abord la partition 2026-10-29.")
    produit_id, nom = produit
    clients = [r[0] for r in conn.execute(
        "SELECT client_id FROM principal.clients ORDER BY client_id LIMIT 2")]

    conn.execute(
        "INSERT INTO vendeurs (vendeur_id, nom_vendeur, ville, region) "
        "SELECT v.vendeur_id, v.nom_vendeur, v.ville, v.region FROM principal.vendeurs v "
        "JOIN principal.produits p ON p.vendeur_id = v.vendeur_id WHERE p.produit_id = %s",
        (produit_id,))
    conn.execute(
        "INSERT INTO produits (produit_id, nom_produit, categorie, vendeur_id, "
        "prix_catalogue_xof, actif, stock) "
        "SELECT produit_id, nom_produit, categorie, vendeur_id, prix_catalogue_xof, actif, %s "
        "FROM principal.produits WHERE produit_id = %s",
        (STOCK_DE_DEPART, produit_id))
    conn.execute(
        "INSERT INTO clients (client_id, nom_client, email, telephone, ville, region, date_inscription) "
        "SELECT client_id, nom_client, email, telephone, ville, region, date_inscription "
        "FROM principal.clients WHERE client_id = ANY(%s)",
        (clients,))
    return produit_id, nom, clients


def connexion_acheteur() -> psycopg.Connection:
    """Une connexion à soi pour un acheteur (deux threads ne partagent jamais une connexion)."""
    conn = connexion_postgres()
    conn.autocommit = True
    conn.execute(f'SET search_path TO "{SCHEMA}"')
    return conn


def remettre_a_zero(conn: psycopg.Connection, produit_id: str) -> None:
    """Efface les commandes de l'essai précédent et remet le stock à 1."""
    conn.execute("DELETE FROM paiements")
    conn.execute("DELETE FROM commandes")   # les lignes partent avec (CASCADE)
    conn.execute("UPDATE produits SET stock = %s WHERE produit_id = %s", (STOCK_DE_DEPART, produit_id))


def _un_essai(commande: Callable, connexions: list, clients: list[str], produit_id: str,
              numero: str, options: dict) -> list[str]:
    """Lance deux acheteurs en parallèle et note ce que chacun a obtenu."""
    barriere = threading.Barrier(2)    # les deux partent exactement en même temps
    resultats = ["?", "?"]

    def acheteur(i: int) -> None:
        barriere.wait()
        try:
            commande(connexions[i], f"{numero}_{i}", clients[i], produit_id, **options)
            resultats[i] = "ok"
        except StockInsuffisant:
            resultats[i] = "refusee"   # refus normal : plus de stock
        except Exception:
            resultats[i] = "erreur"    # panne technique

    threads = [threading.Thread(target=acheteur, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return resultats


def executer_variante(nom: str, commande: Callable, essais: int, produit_id: str,
                      clients: list[str], connexions: list, principale: psycopg.Connection,
                      options: dict) -> dict:
    """Répète l'expérience `essais` fois et compte les anomalies."""
    doubles = orphelines = refusees = erreurs = 0
    stock_apres_double = None
    debut = time.perf_counter()
    for essai in range(essais):
        remettre_a_zero(principale, produit_id)
        resultats = _un_essai(commande, connexions, clients, produit_id, f"{essai}", options)
        refusees += resultats.count("refusee")
        erreurs += resultats.count("erreur")

        ventes = principale.execute(
            "SELECT count(*) FROM lignes_commande WHERE produit_id = %s", (produit_id,)).fetchone()[0]
        if ventes > STOCK_DE_DEPART:   # plus de commandes que d'articles
            doubles += 1
            if stock_apres_double is None:
                stock_apres_double = principale.execute(
                    "SELECT stock FROM produits WHERE produit_id = %s", (produit_id,)).fetchone()[0]
        orphelines += principale.execute(
            "SELECT count(*) FROM commandes c WHERE NOT EXISTS "
            "(SELECT 1 FROM paiements p WHERE p.commande_id = c.commande_id)").fetchone()[0]
    return {"variante": nom, "essais": essais, "doubles_ventes": doubles,
            "orphelines": orphelines, "refusees": refusees, "erreurs": erreurs,
            "stock_apres_double": stock_apres_double,
            "duree": time.perf_counter() - debut}


def tableau_markdown(resultats: list[dict]) -> str:
    """Le tableau demandé par le document (à coller dans docs/MESURES.md)."""
    lignes = [
        "| Variante | Essais | Doubles ventes | Commandes sans paiement | Refus « plus de stock » | Erreurs techniques | Temps total |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in resultats:
        lignes.append(
            f"| {r['variante']} | {r['essais']} | {r['doubles_ventes']} | {r['orphelines']} "
            f"| {r['refusees']} | {r['erreurs']} | {r['duree']:.2f} s |")
    return "\n".join(lignes)
