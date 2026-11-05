"""ÉTAPE 2 : deux clients veulent le DERNIER article en même temps.

    python scripts/2_double_vente.py --produit PRO0025

On compare deux façons d'écrire la commande, sur 200 essais chacune :
- NAÏVE : lire le stock, vérifier, réécrire le stock, puis insérer commande + ligne + paiement,
          sans transaction (chaque instruction est validée seule) ;
- SÛRE  : UNE transaction + une mise à jour atomique « retire 1 SI stock >= 1 ».

Deux tests : la double vente (2 acheteurs, stock 1) et le plantage (le programme
meurt entre la commande et le paiement).
"""
import argparse
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from bases import pg


def ecrire_commande(cur, produit, prix, client, planter):
    """Insère commande + ligne + paiement. `planter` simule un crash entre commande et paiement."""
    tag = uuid.uuid4().hex[:10]
    cur.execute("INSERT INTO commandes VALUES (%s, %s, %s, 'en_preparation')",
                (f"TST-{tag}", client, date.today()))
    cur.execute("INSERT INTO lignes_commande VALUES (%s, %s, %s, 1, %s, %s)",
                (f"TSTL-{tag}", f"TST-{tag}", produit, prix, prix))
    if planter:
        raise RuntimeError("plantage simulé")
    cur.execute("INSERT INTO paiements VALUES (%s, %s, 'Wave', 'en_attente', %s, %s, NULL)",
                (f"TSTP-{tag}", f"TST-{tag}", prix, date.today()))


def commande_naive(conn, produit, client, planter=False):
    cur = conn.cursor()                                   # autocommit : chaque ordre est validé seul
    stock, prix = cur.execute("SELECT stock, prix_catalogue_xof FROM produits WHERE produit_id=%s",
                              (produit,)).fetchone()      # 1) je LIS
    if stock < 1:                                         # 2) je décide
        return "refus"
    cur.execute("UPDATE produits SET stock=%s WHERE produit_id=%s", (stock - 1, produit))  # 3) j'ÉCRIS
    try:
        ecrire_commande(cur, produit, prix, client, planter)
    except RuntimeError:
        return "plantage"
    return "ok"


def commande_sure(conn, produit, client, planter=False):
    cur = conn.cursor()
    try:
        with conn.transaction():                          # tout réussit ou tout est annulé
            cur.execute("UPDATE produits SET stock = stock - 1 WHERE produit_id=%s AND stock >= 1",
                        (produit,))                       # lire + décider + écrire en UN seul geste
            if cur.rowcount == 0:
                return "refus"
            prix = cur.execute("SELECT prix_catalogue_xof FROM produits WHERE produit_id=%s",
                               (produit,)).fetchone()[0]
            ecrire_commande(cur, produit, prix, client, planter)
        return "ok"
    except RuntimeError:
        return "plantage"                                # la transaction a été annulée toute seule


def nettoyer(conn):
    conn.execute("DELETE FROM paiements WHERE commande_id LIKE 'TST-%'")
    conn.execute("DELETE FROM commandes WHERE commande_id LIKE 'TST-%'")   # les lignes partent avec (CASCADE)


def double_vente(variante, c1, c2, produit, client, n):
    doubles = refus = 0
    debut = time.perf_counter()
    for _ in range(n):
        c1.execute("UPDATE produits SET stock=1 WHERE produit_id=%s", (produit,))
        depart = threading.Barrier(2)                     # les deux acheteurs partent au même instant

        def acheteur(conn):
            depart.wait()
            return variante(conn, produit, client)

        with ThreadPoolExecutor(2) as pool:
            res = list(pool.map(acheteur, [c1, c2]))
        doubles += res.count("ok") == 2
        refus += res.count("refus")
    return doubles, refus, time.perf_counter() - debut


def plantage(variante, conn, produit, client, n):
    nettoyer(conn)
    sans_paiement = stock_debite = 0
    for _ in range(n):
        conn.execute("UPDATE produits SET stock=1 WHERE produit_id=%s", (produit,))
        variante(conn, produit, client, planter=True)
        stock = conn.execute("SELECT stock FROM produits WHERE produit_id=%s", (produit,)).fetchone()[0]
        stock_debite += stock == 0
    sans_paiement = conn.execute(
        "SELECT count(*) FROM commandes c WHERE commande_id LIKE 'TST-%' "
        "AND NOT EXISTS (SELECT 1 FROM paiements p WHERE p.commande_id = c.commande_id)").fetchone()[0]
    nettoyer(conn)
    return sans_paiement, stock_debite


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--schema", default="principal")
    p.add_argument("--produit", default="PRO0025", help="un produit flash (affiché par 1_charger.py)")
    p.add_argument("--essais", type=int, default=200)
    a = p.parse_args()

    c1, c2 = pg(a.schema), pg(a.schema)                   # chaque acheteur a SA connexion
    c1.autocommit = c2.autocommit = True
    client = c1.execute("SELECT client_id FROM clients ORDER BY client_id LIMIT 1").fetchone()[0]
    stock_depart = c1.execute("SELECT stock FROM produits WHERE produit_id=%s", (a.produit,)).fetchone()[0]
    nettoyer(c1)

    print(f"\n=== Double vente : 2 acheteurs, stock 1, {a.essais} essais ===")
    print(f"{'variante':<10}{'doubles ventes':>16}{'refus':>8}{'temps':>9}")
    for nom, f in [("naïve", commande_naive), ("sûre", commande_sure)]:
        d, r, t = double_vente(f, c1, c2, a.produit, client, a.essais)
        print(f"{nom:<10}{d:>16}{r:>8}{t:>8.1f}s")
        nettoyer(c1)

    n = 50
    print(f"\n=== Plantage entre commande et paiement : {n} essais ===")
    print(f"{'variante':<10}{'commandes sans paiement':>26}{'stock débité pour rien':>25}")
    for nom, f in [("naïve", commande_naive), ("sûre", commande_sure)]:
        sp, sd = plantage(f, c1, a.produit, client, n)
        print(f"{nom:<10}{sp:>26}{sd:>25}")

    c1.execute("UPDATE produits SET stock=%s WHERE produit_id=%s", (stock_depart, a.produit))
    nettoyer(c1)


if __name__ == "__main__":
    main()
