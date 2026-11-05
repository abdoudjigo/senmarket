"""Contrôle de pré-vol du module 1 : mes données sont-elles prêtes ?

Usage : python scripts/preflight_module1.py [AAAA-MM-JJ]
Sans argument, contrôle la dernière partition (ordre alphabétique des dates).
"""
import sys
from pathlib import Path

import pandas as pd

# Racine de module_1 : scripts -> module_1. Le raccourci "data" y mène aux données du module 0.
RACINE = Path(__file__).resolve().parents[1]

# Clé primaire de chaque table
CLES = {
    "clients": "client_id", "vendeurs": "vendeur_id", "produits": "produit_id",
    "commandes": "commande_id", "lignes_commande": "ligne_commande_id",
    "paiements": "paiement_id", "avis": "avis_id", "navigation": "evenement_id",
}

# (table enfant, colonne, table parente) : chaque valeur de la colonne doit exister chez le parent
RELATIONS = [
    ("commandes", "client_id", "clients"),
    ("lignes_commande", "commande_id", "commandes"),
    ("lignes_commande", "produit_id", "produits"),
    ("paiements", "commande_id", "commandes"),
    ("avis", "produit_id", "produits"),
]

partitions = sorted((RACINE / "data" / "processed").glob("date=*"))
if not partitions:
    raise SystemExit("Aucune partition nettoyée : lance le pipeline du module 0 avant.")

# Choix de la partition : celle donnée en argument, sinon la dernière
if len(sys.argv) > 1:
    dossier = RACINE / "data" / "processed" / f"date={sys.argv[1]}"
    if not dossier.exists():
        dispo = ", ".join(p.name for p in partitions)
        raise SystemExit(f"Partition introuvable : {dossier.name}. Disponibles : {dispo}")
else:
    dossier = partitions[-1]

print("Partition contrôlée :", dossier.name)
tables = {nom: pd.read_parquet(dossier / f"{nom}.parquet") for nom in CLES}
problemes = 0

# 1. Chaque clé primaire est-elle unique ?
for nom, df in tables.items():
    unique = bool(df[CLES[nom]].is_unique)
    print(f"{nom:<16}{len(df):>9} lignes | clé primaire unique : {unique}")
    if not unique:
        problemes += 1

# 2. Existe-t-il des orphelins (clé étrangère sans parent) ?
for enfant, colonne, parent in RELATIONS:
    orphelins = ~tables[enfant][colonne].isin(tables[parent][CLES[parent]])
    print(f"{enfant}.{colonne} -> {parent} : {orphelins.sum()} orphelin(s)")
    problemes += int(orphelins.sum())

# 3. Le paiement est-il égal à la somme des lignes de sa commande ?
# (un écart n'est pas une erreur : Fatou l'exploitera au chapitre 2)
lignes = tables["lignes_commande"].groupby("commande_id")["montant_xof"].sum()
paye = tables["paiements"].groupby("commande_id")["montant_xof"].sum()
comparaison = pd.concat([lignes, paye], axis=1, keys=["lignes", "paye"]).dropna()
print(f"Paiement égal à la somme des lignes : {(comparaison.lignes == comparaison.paye).mean():.1%}")

# 4. Les colonnes que le chapitre 1 va créer ne doivent pas exister encore
for table, colonne in [("produits", "stock"), ("avis", "commentaire"),
                       ("paiements", "reference_transaction")]:
    print(f"{table}.{colonne} présent : {colonne in tables[table].columns}")

# Verdict : le script échoue s'il y a un problème bloquant
if problemes:
    raise SystemExit(f"PRÉ-VOL ÉCHOUÉ : {problemes} problème(s) à corriger.")
print("PRÉ-VOL OK")
