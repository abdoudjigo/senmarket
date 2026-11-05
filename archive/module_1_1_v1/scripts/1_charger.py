"""ÉTAPE 1 : charger les données de SenMarket dans PostgreSQL.

    python scripts/1_charger.py --run-date 2026-10-29 --schema principal

Ce que le script garantit (et pourquoi) :
- rapide    : COPY = un seul envoi en masse, pas un INSERT par ligne ;
- atomique  : tout dans UNE transaction, si une table échoue il ne reste rien ;
- rejouable : on recrée le schéma à chaque fois, donc deux lancements = même résultat ;
- vérifié   : on compare avec le Parquet AVANT de valider.
"""
import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd
from psycopg import sql

from bases import RACINE, dossier_partition, pg

# Ordre = les parents avant les enfants (sinon la clé étrangère refuse).
COLONNES = {
    "vendeurs": ["vendeur_id", "nom_vendeur", "ville", "region"],
    "clients": ["client_id", "nom_client", "email", "telephone", "ville", "region", "date_inscription"],
    "produits": ["produit_id", "nom_produit", "categorie", "vendeur_id", "prix_catalogue_xof", "actif", "stock"],
    "commandes": ["commande_id", "client_id", "date_commande", "statut"],
    "lignes_commande": ["ligne_commande_id", "commande_id", "produit_id", "quantite",
                        "prix_unitaire_xof", "montant_xof"],
    "paiements": ["paiement_id", "commande_id", "methode_paiement", "statut_paiement",
                  "montant_xof", "date_paiement", "reference_transaction"],
}


def ajouter_stock(produits, run_date):
    """Le module 0 n'a pas de stock : on l'invente, de façon reproductible (même date = même stock).
    Les 3 premiers produits Électronique sont des produits « flash » (stock 1, 3, 5) :
    ils servent à l'expérience de la double vente."""
    rng = np.random.default_rng([42, int(run_date.replace("-", ""))])
    produits = produits.sort_values("produit_id").reset_index(drop=True)
    produits["stock"] = rng.integers(20, 301, len(produits))
    flash = produits.index[produits["categorie"] == "Électronique"][:3]
    produits.loc[flash, "stock"] = [1, 3, 5][: len(flash)]
    return produits, list(produits.loc[flash, "produit_id"])


def valeur(v):
    """Python natif pour COPY : les trous deviennent NULL, les dates des dates."""
    if pd.isna(v):
        return None
    if isinstance(v, pd.Timestamp):
        return v.date()
    return v.item() if hasattr(v, "item") else v


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--run-date", required=True, help="partition du module 0, AAAA-MM-JJ")
    p.add_argument("--schema", default="principal", help="jeu de tables (principal, volume...)")
    args = p.parse_args()

    dossier = dossier_partition(args.run_date)
    tables = {nom: pd.read_parquet(dossier / f"{nom}.parquet") for nom in COLONNES}
    tables["produits"], flash = ajouter_stock(tables["produits"], args.run_date)
    tables["paiements"]["reference_transaction"] = None   # sera rempli au module 3

    debut = time.perf_counter()
    schema = sql.Identifier(args.schema)
    with pg() as conn:                      # sortie normale = COMMIT, erreur = ROLLBACK
        with conn.cursor() as cur:
            cur.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(schema))
            cur.execute(sql.SQL("CREATE SCHEMA {}").format(schema))
            cur.execute(sql.SQL("SET LOCAL search_path TO {}").format(schema))
            cur.execute((RACINE / "sql" / "01_schema.sql").read_text(encoding="utf-8"))

            for nom, cols in COLONNES.items():
                requete = sql.SQL("COPY {} ({}) FROM STDIN").format(
                    sql.Identifier(nom), sql.SQL(", ").join(map(sql.Identifier, cols)))
                with cur.copy(requete) as copie:
                    for ligne in tables[nom][cols].itertuples(index=False, name=None):
                        copie.write_row([valeur(v) for v in ligne])

            print(f"{'table':<18}{'parquet':>9}{'postgres':>10}")
            for nom in COLONNES:
                n = cur.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(nom))).fetchone()[0]
                print(f"{nom:<18}{len(tables[nom]):>9}{n:>10}")
                assert n == len(tables[nom]), f"{nom} : {n} lignes en base, {len(tables[nom])} attendues"
            somme = cur.execute("SELECT sum(montant_xof) FROM lignes_commande").fetchone()[0]
            attendu = int(tables["lignes_commande"]["montant_xof"].sum())
            assert somme == attendu, f"Somme des montants différente : {somme} contre {attendu}"
            print(f"\nSomme des montants identique au Parquet : {somme:,} XOF".replace(",", " "))

    print(f"Chargé dans le schéma « {args.schema} » en {time.perf_counter() - debut:.1f} s.")
    print(f"Produits flash (stock 1, 3, 5) pour la double vente : {flash}")


if __name__ == "__main__":
    main()
