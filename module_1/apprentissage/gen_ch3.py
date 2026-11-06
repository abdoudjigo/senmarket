from _nb import build
C = []
C.append(("md", '''
# Chapitre 3 : MongoDB, le catalogue qui change de forme et les avis qui grossissent

> **Ibou (produit)** : « J'ajoute des téléphones, des tissus, des sacs de riz. Chaque fiche a ses propres caractéristiques. Je ne veux pas une table de quarante colonnes dont trente restent vides. Et je veux voir les produits les mieux notés, avec un minimum d'avis. »

## À comprendre
Deux données de nature différente :
- la **fiche produit** : lue en entier, de forme variable -> on l'**embarque** (un document JSON) ;
- les **avis** : nombreux, toujours plus nombreux -> on les **référence** dans leur propre collection (un document ne dépasse pas 16 Mo, et on ne veut pas réécrire la fiche à chaque avis).

Frontière avec PostgreSQL : le **stock** et le **prix payé** restent dans PostgreSQL. Copier ici une donnée qui change ailleurs créerait deux vérités. Le lien entre les deux mondes est `produit_id`.
'''))
C.append(("code", '''
import json
import pandas as pd
from senmarket_bases.connexions import RACINE, client_mongo
from senmarket_bases.charger_mongo import charger

charger("2026-10-29")   # drop + reload: running it twice leaves the same state
db = client_mongo()["senmarket"]
'''))
C.append(("md", "## 1. Des fiches de formes différentes\nOn regroupe les produits par forme d'attributs : chaque forme est une colonne qui n'existerait que pour une catégorie dans un tableau relationnel."))
C.append(("code", '''
formes = {}
for d in db.produits.find({}, {"_id": 0}):
    formes.setdefault(tuple(sorted(d["attributs"])), d)
for cles, ex in formes.items():
    print(f"{str(cles):<55} ex : {ex['nom']} ({ex['categorie']})")
print(len(formes), "formes d'attributs différentes dans", db.produits.count_documents({}), "produits")
'''))
C.append(("md", "## 2. Interroger des attributs qui n'existent pas partout"))
C.append(("code", '''
total = db.produits.count_documents({})
sans = db.produits.count_documents({"attributs.poids_kg": {"$exists": False}})
avec = db.produits.count_documents({"attributs.poids_kg": {"$gte": 1}})
print(f"produits avec poids_kg >= 1 kg : {avec} | sans poids_kg : {sans} sur {total}")
'''))
C.append(("md", "**À lire.** Un produit sans `poids_kg` (un téléphone) n'est pas une erreur : c'est la forme normale de sa fiche. En relationnel, ce serait une colonne vide."))
C.append(("md", "## 3. Les produits les mieux notés (au moins 5 avis), avec un contrôle croisé\nUn pipeline d'agrégation peut se tromper en silence. Filet de sécurité : on recalcule la même chose avec pandas sur le Parquet et on compare."))
C.append(("code", '''
avis = pd.read_parquet(RACINE / "data" / "processed" / "date=2026-10-29" / "avis.parquet")
ref = avis.groupby("produit_id")["note"].agg(["mean", "count"])
ref = ref[ref["count"] >= 5]

mongo = {l["_id"]: (l["m"], l["n"]) for l in db.avis.aggregate([
    {"$group": {"_id": "$produit_id", "m": {"$avg": "$note"}, "n": {"$sum": 1}}},
    {"$match": {"n": {"$gte": 5}}}])}

assert set(mongo) == set(ref.index)
assert all(abs(mongo[p][0] - ref.loc[p, "mean"]) < 1e-9 for p in mongo)
print(len(mongo), "produits comparés : moyennes identiques entre MongoDB et pandas")
for p, (m, n) in sorted(mongo.items(), key=lambda x: (-x[1][0], x[0]))[:5]:
    print(f"  {p}  {m:.2f}  ({n} avis)")
'''))
C.append(("md", "## 4. Le validateur : « sans schéma » ne veut pas dire « sans règles »\nOn tente d'insérer deux avis invalides : une note de 9, et une note écrite en texte."))
C.append(("code", '''
for doc in [{"avis_id": "T1", "produit_id": "PRO0001", "note": 9},
            {"avis_id": "T2", "produit_id": "PRO0001", "note": "5"}]:
    try:
        db.avis.insert_one(doc)
        print("ACCEPTÉ (problème !)", doc)
        db.avis.delete_one({"avis_id": doc["avis_id"]})
    except Exception as e:
        print("REFUSÉ ->", type(e).__name__, doc)
'''))
C.append(("md", "## 5. Index : COLLSCAN contre IXSCAN\nSans index, MongoDB parcourt toute la collection. On compte les documents examinés pour la recherche des avis d'un produit."))
C.append(("code", '''
pid = db.avis.find_one()["produit_id"]

def examiner():
    r = db.command("explain", {"find": "avis", "filter": {"produit_id": pid}}, verbosity="executionStats")
    plan = "IXSCAN" if "IXSCAN" in json.dumps(r["queryPlanner"]["winningPlan"]) else "COLLSCAN"
    return plan, r["executionStats"]["totalDocsExamined"], r["executionStats"]["nReturned"]

db.avis.drop_index("produit_id_1")
print("sans index :", examiner(), "(plan, documents examinés, renvoyés)")
db.avis.create_index("produit_id")
print("avec index :", examiner())
'''))
C.append(("md", '''
## Questions

**1. PostgreSQL a aussi `JSONB`. Pourquoi ajouter MongoDB ?**
Honnêtement, à cette taille PostgreSQL (`JSONB` + index) suffirait pour les attributs. MongoDB se justifie ici par la **forme variable** des fiches (la section 1 en montre plusieurs), les **avis qui s'accumulent** dans leur propre collection, et un **validateur** natif (section 4). Le prix : une base de plus à superviser et sauvegarder. L'argument ne tient que si on le défend avec ces constats.

**2. Si Ibou ajoute un champ `origine` aux produits alimentaires ?**
MongoDB : rien à migrer, les nouveaux documents ont le champ, les anciens ne l'ont pas (`$exists` les distingue). PostgreSQL : un `ALTER TABLE ... ADD COLUMN`, une colonne vide pour tous les autres produits.

## Ce qu'on retient
- Embarquer ce qui se lit ensemble, référencer ce qui grossit.
- Un résultat d'agrégation se **recoupe** avec un autre calcul.
- Le validateur empêche le désordre ; l'index évite de tout parcourir.
'''))
build("ch3_mongodb.ipynb", C)
