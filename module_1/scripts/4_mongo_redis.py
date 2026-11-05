"""ÉTAPE 4 : le catalogue et les avis dans MongoDB, le panier et le cache dans Redis.

    python scripts/4_mongo_redis.py --run-date 2026-10-29 --schema principal

Pourquoi ces deux bases :
- MongoDB : un téléphone et un sac de riz n'ont pas les mêmes caractéristiques. Un document
            s'adapte, une table obligerait à créer des colonnes presque toujours vides.
- Redis   : le panier et le cache doivent répondre en une fraction de milliseconde,
            et on peut les perdre sans drame (le panier se reconstruit, le cache aussi).
"""
import argparse
import time

import pandas as pd
import pymongo

from bases import dossier_partition, mongo, pg, redis_

# Les caractéristiques changent de forme selon la catégorie : c'est tout l'intérêt de Mongo.
def attributs(categorie, i):
    if categorie == "Électronique":     # contient un objet imbriqué et une liste
        return {"specs": {"ram_go": [4, 6, 8][i % 3], "stockage_go": [64, 128, 256][i % 3]},
                "couleurs": ["noir", "bleu"], "garantie_mois": 12}
    if categorie == "Alimentation":
        return {"poids_kg": [1, 5, 25][i % 3], "origine": ["Sénégal", "Inde", "Thaïlande"][i % 3]}
    if categorie == "Vêtements":
        return {"tailles": ["S", "M", "L"], "matiere": "coton"}
    return {}


def commentaire(note):
    return {1: "Très déçu, produit non conforme.", 2: "Qualité moyenne, livraison lente.",
            3: "Correct pour le prix.", 4: "Bon produit, je recommande.",
            5: "Excellent, je rachèterai."}[note]


def partie_mongo(dossier):
    produits = pd.read_parquet(dossier / "produits.parquet").sort_values("produit_id").reset_index(drop=True)
    avis = pd.read_parquet(dossier / "avis.parquet")
    db = mongo()["senmarket"]
    db.drop_collection("produits")
    db.drop_collection("avis")

    # Le validateur : « sans schéma » ne veut pas dire « sans règles ».
    db.create_collection("produits", validator={"$jsonSchema": {
        "bsonType": "object", "required": ["produit_id", "nom", "categorie", "attributs"],
        "properties": {"produit_id": {"bsonType": "string"}, "nom": {"bsonType": "string"},
                       "categorie": {"bsonType": "string"}, "attributs": {"bsonType": "object"}}}})
    db.create_collection("avis", validator={"$jsonSchema": {
        "bsonType": "object", "required": ["avis_id", "produit_id", "note"],
        "properties": {"note": {"bsonType": "int", "minimum": 1, "maximum": 5}}}})

    # Pas de prix ni de stock ici : ils changent, et leur seule vérité est dans PostgreSQL.
    db.produits.insert_many([{"produit_id": r.produit_id, "nom": r.nom_produit, "categorie": r.categorie,
                              "attributs": attributs(r.categorie, i)} for i, r in enumerate(produits.itertuples())])
    db.avis.insert_many([{"avis_id": r.avis_id, "produit_id": r.produit_id, "note": int(r.note),
                          "commentaire": commentaire(int(r.note))} for r in avis.itertuples()])
    db.avis.create_index("produit_id")

    print("=== MongoDB ===")
    print(f"{db.produits.count_documents({})} produits, {db.avis.count_documents({})} avis.")
    for cat in ["Électronique", "Alimentation"]:
        doc = db.produits.find_one({"categorie": cat}, {"_id": 0})
        print(f"Fiche {cat} : {doc}")

    try:
        db.avis.insert_one({"avis_id": "TEST", "produit_id": "PRO0001", "note": 9})
    except pymongo.errors.WriteError:
        print("Avis avec une note de 9 : REFUSÉ par le validateur.")

    print("\nTop 3 des produits les mieux notés (au moins 5 avis) :")
    top = db.avis.aggregate([
        {"$group": {"_id": "$produit_id", "note_moyenne": {"$avg": "$note"}, "nb_avis": {"$sum": 1}}},
        {"$match": {"nb_avis": {"$gte": 5}}},
        {"$sort": {"note_moyenne": -1}}, {"$limit": 3}])
    for t in top:
        print(f"  {t['_id']}  note {t['note_moyenne']:.2f}  ({t['nb_avis']} avis)")


def partie_redis(schema):
    r = redis_()
    print("\n=== Redis : le panier ===")
    cle = "demo:panier:CLI0000001"
    r.delete(cle)
    r.hset(cle, mapping={"PRO0001": 2, "PRO0003": 1})     # un Hash = un petit objet
    r.expire(cle, 2)                                       # TTL court pour la démo (30 min en vrai)
    print(f"Panier : {r.hgetall(cle)}   expire dans {r.ttl(cle)} s")
    time.sleep(3)
    print(f"3 secondes plus tard : {r.hgetall(cle) or 'panier vide : il a expiré tout seul'}")

    print("\n=== Redis : le cache devant PostgreSQL (cache-aside) ===")
    conn = pg(schema)
    r.delete("demo:cache:top5")

    def top_produits():
        trouve = r.get("demo:cache:top5")
        if trouve:
            return trouve, "dans Redis"
        lignes = conn.execute("SELECT produit_id, sum(quantite) FROM lignes_commande "
                              "GROUP BY 1 ORDER BY 2 DESC LIMIT 5").fetchall()
        texte = ", ".join(f"{p}:{q}" for p, q in lignes)
        r.set("demo:cache:top5", texte, ex=60)             # on garde la réponse 60 s
        return texte, "dans PostgreSQL"

    for essai in (1, 2):
        debut = time.perf_counter()
        _, d_ou = top_produits()
        print(f"Appel {essai} : réponse {d_ou:<16} en {(time.perf_counter() - debut) * 1000:.2f} ms")
    r.delete("demo:cache:top5")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--run-date", required=True)
    p.add_argument("--schema", default="principal")
    p.add_argument("--partie", choices=["mongo", "redis", "les-deux"], default="les-deux")
    a = p.parse_args()
    if a.partie in ("mongo", "les-deux"):
        partie_mongo(dossier_partition(a.run_date))
    if a.partie in ("redis", "les-deux"):
        partie_redis(a.schema)


if __name__ == "__main__":
    main()
