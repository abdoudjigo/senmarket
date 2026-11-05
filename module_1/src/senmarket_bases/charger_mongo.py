"""Load the product catalogue and the reviews into MongoDB, then run demo queries.

Usage: python -m senmarket_bases.charger_mongo 2026-10-29
"""
import json
import sys
from pathlib import Path

import pandas as pd

from senmarket_bases.connexions import RACINE, client_mongo

VALIDATEUR_PRODUITS = {"$jsonSchema": {
    "bsonType": "object",
    "required": ["produit_id", "nom", "categorie", "attributs"],
    "properties": {
        "produit_id": {"bsonType": "string"},
        "nom": {"bsonType": "string"},
        "categorie": {"bsonType": "string"},
        "attributs": {"bsonType": "object"},
    },
}}
VALIDATEUR_AVIS = {"$jsonSchema": {
    "bsonType": "object",
    "required": ["avis_id", "produit_id", "note"],
    "properties": {
        "avis_id": {"bsonType": "string"},
        "produit_id": {"bsonType": "string"},
        # note must be an integer between 1 and 5
        "note": {"bsonType": "int", "minimum": 1, "maximum": 5},
    },
}}


def charger(run_date: str) -> None:
    enrichi = RACINE / "bases_enriched" / f"date={run_date}"
    traite = RACINE / "data" / "processed" / f"date={run_date}"
    db = client_mongo()["senmarket"]

    # Idempotent: drop and recreate, so a second run leaves the same state
    for nom, validateur in [("produits", VALIDATEUR_PRODUITS), ("avis", VALIDATEUR_AVIS)]:
        db.drop_collection(nom)
        db.create_collection(nom, validator=validateur)

    with open(enrichi / "catalogue.jsonl", encoding="utf-8") as f:
        produits = [json.loads(ligne) for ligne in f]
    db.produits.insert_many(produits)

    avis = pd.read_parquet(traite / "avis.parquet")
    commentaires = pd.read_csv(enrichi / "avis_commentaires.csv")
    avis = avis.merge(commentaires, on="avis_id", how="left")
    avis["date_avis"] = avis["date_avis"].astype(str)
    avis["note"] = avis["note"].astype(int)
    db.avis.insert_many(avis.to_dict("records"))

    # Index so that "reviews of one product" does not scan the whole collection
    db.avis.create_index("produit_id")
    print(f"produits: {db.produits.count_documents({})} | avis: {db.avis.count_documents({})}")


def demo() -> None:
    db = client_mongo()["senmarket"]
    print("\nProducts without 'poids_kg':", db.produits.count_documents({"attributs.poids_kg": {"$exists": False}}))
    print("\nTop 5 average rating (at least 5 reviews):")
    pipeline = [
        {"$group": {"_id": "$produit_id", "note_moyenne": {"$avg": "$note"}, "nb_avis": {"$sum": 1}}},
        {"$match": {"nb_avis": {"$gte": 5}}},
        {"$sort": {"note_moyenne": -1}},
        {"$limit": 5},
    ]
    for ligne in db.avis.aggregate(pipeline):
        print(f"  {ligne['_id']}  {ligne['note_moyenne']:.2f}  ({ligne['nb_avis']} avis)")
    print("\nValidator test (invalid rating 9):")
    try:
        db.avis.insert_one({"avis_id": "TEST", "produit_id": "PRO0001", "note": 9})
    except Exception as e:
        print("  refused ->", type(e).__name__)


if __name__ == "__main__":
    charger(sys.argv[1] if len(sys.argv) > 1 else "2026-10-29")
    demo()
