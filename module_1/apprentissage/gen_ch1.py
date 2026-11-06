from _nb import build

C = []
C.append(("md", '''
# Chapitre 1 : enrichir SenMarket (tickets SM-101 et SM-102)

> **Moussa (logistique)** : « Hier, on a vendu un téléphone qu'on n'avait plus. Dans le fichier produits, je ne vois même pas le stock. »
>
> **Ibou (produit)** : « Pour le Black Friday, je veux des fiches produit avec des caractéristiques, et lire ce que disent les clients, pas seulement leur note. Et Fatou veut retrouver chaque paiement Wave chez Wave. »

## À comprendre
Les données du Module 0 servaient à tester le nettoyage, pas à faire tourner un magasin. Il leur manque **quatre choses**, et chacune servira plus tard :

| Ce qui manque | Pourquoi | Servira à |
|---|---|---|
| Le **stock** | Savoir si on peut vendre | Les transactions (PostgreSQL) |
| Des **attributs variables** par produit | Un téléphone a de la RAM, un sac de riz a un poids | Le catalogue (MongoDB) |
| Un **commentaire** par avis | Lire ce que disent les clients | Les agrégations sur les avis (MongoDB) |
| Une **référence de transaction** par paiement | Retrouver un paiement chez Wave | L'idempotence du Module 3 : sans identifiant unique, impossible de savoir si on a déjà importé un paiement |

Le script d'enrichissement produit quatre fichiers dans `bases_enriched/date=.../`. Ici on les **regarde et on vérifie leurs règles**.
'''))
C.append(("code", '''
import pandas as pd
from senmarket_bases.connexions import RACINE, connexion_postgres

DOSSIER = RACINE / "bases_enriched" / "date=2026-10-29"
S = "principal"  # PostgreSQL schema of the main partition

def sql(requete):
    """Run a query and return a readable table."""
    with connexion_postgres() as conn:
        cur = conn.execute(requete)
        return pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])

stock = pd.read_csv(DOSSIER / "stock.csv")
catalogue = pd.read_json(DOSSIER / "catalogue.jsonl", lines=True)
commentaires = pd.read_csv(DOSSIER / "avis_commentaires.csv")
references = pd.read_csv(DOSSIER / "paiements_references.csv")
print({"stock": len(stock), "catalogue": len(catalogue), "commentaires": len(commentaires), "references": len(references)})
'''))
C.append(("md", "## 1. Le stock (ticket de Moussa)\nRègles : entier >= 0, quelques ruptures (0), et au moins trois produits « flash » (1 à 5 unités) pour les épreuves de concurrence."))
C.append(("code", '''
print(stock.describe().loc[["min", "50%", "max"]].T)
nb_rupture = int((stock["stock"] == 0).sum())
nb_flash = int(stock["stock"].between(1, 5).sum())
print(f"ruptures (stock = 0) : {nb_rupture} | produits flash (1 a 5) : {nb_flash}")
assert (stock["stock"] >= 0).all() and nb_flash >= 3
print("OK : aucun stock négatif, au moins 3 produits flash")
'''))
C.append(("md", "## 2. Le catalogue (ticket d'Ibou)\nUn document par produit, avec des `attributs` qui **changent de forme** selon la catégorie. C'est exactement ce qu'un tableau relationnel gère mal."))
C.append(("code", '''
catalogue["cles_attributs"] = catalogue["attributs"].apply(lambda d: sorted(d.keys()))
formes = catalogue.groupby(catalogue["cles_attributs"].astype(str))["categorie"].agg(["count", lambda s: sorted(set(s))])
formes.columns = ["nb_produits", "categories"]
print(formes)
nb_formes = catalogue["cles_attributs"].astype(str).nunique()
assert nb_formes >= 3
print(f"OK : {nb_formes} formes d'attributs différentes dans {len(catalogue)} produits")
'''))
C.append(("md", "Le catalogue ne doit pas inventer de produit : chaque `produit_id` doit exister dans la table `produits` de PostgreSQL (la vérité), et inversement pour le stock."))
C.append(("code", '''
ids_pg = set(sql(f"SELECT produit_id FROM {S}.produits")["produit_id"])
print("catalogue absent de PostgreSQL :", set(catalogue["produit_id"]) - ids_pg or "aucun")
print("stock absent de PostgreSQL     :", set(stock["produit_id"]) - ids_pg or "aucun")
assert set(catalogue["produit_id"]) <= ids_pg and set(stock["produit_id"]) <= ids_pg
print("OK : les trois sources parlent des mêmes produits")
'''))
C.append(("md", "## 3. Les commentaires d'avis (ticket d'Ibou)\nUn texte pour **chaque** avis, cohérent avec la note. On regarde un commentaire par note pour vérifier le ton."))
C.append(("code", '''
avis = pd.read_parquet(RACINE / "data" / "processed" / "date=2026-10-29" / "avis.parquet")[["avis_id", "note"]]  # avis is not loaded in PostgreSQL
m = avis.merge(commentaires, on="avis_id", how="left")
print("avis sans commentaire :", int(m["commentaire"].isna().sum()))
for note in range(1, 6):
    ligne = m[m["note"] == note].iloc[0]
    print(f"note {note} -> {ligne['commentaire']}")
assert m["commentaire"].notna().all()
print("OK : un commentaire pour chaque avis")
'''))
C.append(("md", "## 4. Les références de transaction (ticket de Fatou)\nUne référence **unique** par paiement électronique, avec un **préfixe par méthode**, et **vide pour les espèces** (pas de trace chez un opérateur)."))
C.append(("code", '''
print(sql(f"""
    SELECT methode_paiement,
           COUNT(*) AS nb_paiements,
           COUNT(reference_transaction) AS avec_reference,
           COUNT(*) FILTER (WHERE reference_transaction IS NULL) AS nulls,
           COUNT(*) FILTER (WHERE reference_transaction = '') AS chaines_vides,
           MIN(LEFT(reference_transaction, 4)) AS exemple_prefixe
    FROM {S}.paiements GROUP BY methode_paiement ORDER BY nb_paiements DESC"""))
doublons = sql(f"""SELECT reference_transaction, COUNT(*) FROM {S}.paiements
                   WHERE reference_transaction IS NOT NULL GROUP BY 1 HAVING COUNT(*) > 1""")
assert int(sql(f"SELECT COUNT(reference_transaction) AS n FROM {S}.paiements")["n"][0]) > 0, "aucune référence chargée dans PostgreSQL"
assert doublons.empty
print("OK : aucune référence dupliquée")
'''))
C.append(("md", '''
## Question 1 : où le stock doit-il vivre ? (réponse en 3 phrases)

**Réponse initiale.** Le stock doit vivre dans **PostgreSQL**. Il touche à l'argent : si on se trompe, on vend un article qu'on n'a pas. PostgreSQL peut refuser un stock négatif et le modifier dans la **même transaction** que la commande.
*Pourquoi pas les autres ?* MongoDB dupliquerait une donnée qui change ailleurs (deux vérités). Redis redémarre vide : il ne doit jamais détenir la seule copie.

**Justificatif :** on tente de mettre un stock négatif dans PostgreSQL. La base doit refuser (on annule ensuite, rien n'est modifié).
'''))
C.append(("code", '''
import psycopg

with connexion_postgres() as conn:
    tbl = conn.execute(
        "SELECT table_name FROM information_schema.columns WHERE table_schema = %s AND column_name = 'stock'", (S,)
    ).fetchone()[0]
    print(f"Le stock est dans la table {S}.{tbl}")
    try:
        conn.execute(f"UPDATE {S}.{tbl} SET stock = -1 WHERE produit_id = (SELECT MIN(produit_id) FROM {S}.{tbl})")
        print("PAS REFUSÉ : il manque un CHECK (stock >= 0)")
    except psycopg.errors.CheckViolation as e:
        print("REFUSÉ par PostgreSQL ->", str(e).splitlines()[0])
    finally:
        conn.rollback()  # whatever happened, leave the data untouched
'''))
C.append(("md", '''
## Question 2 : pourquoi `UNIQUE` sur `reference_transaction` accepte-t-il plusieurs lignes vides pour les espèces ?

**Réponse.** Dans PostgreSQL, `NULL` signifie « inconnu » : deux inconnus ne sont pas considérés comme égaux, donc `UNIQUE` en accepte autant qu'on veut. Une chaîne vide `''`, elle, est une vraie valeur : deux `''` sont égales, donc `UNIQUE` les refuse.
Pour les espèces, il faut donc stocker `NULL` (« pas de référence »), pas `''`. **Justificatif :** une table temporaire qui montre les deux cas (elle disparaît à la fin de la session).
'''))
C.append(("code", '''
with connexion_postgres() as conn:
    conn.execute("CREATE TEMP TABLE essai (ref text UNIQUE)")
    conn.execute("INSERT INTO essai VALUES (NULL), (NULL), (NULL)")
    print("3 NULL acceptés ->", conn.execute("SELECT COUNT(*) FROM essai").fetchone()[0], "lignes")
    conn.execute("INSERT INTO essai VALUES ('')")
    try:
        conn.execute("INSERT INTO essai VALUES ('')")
    except psycopg.errors.UniqueViolation as e:
        print("2e chaîne vide REFUSÉE ->", str(e).splitlines()[0])
    finally:
        conn.rollback()
'''))
C.append(("md", '''
**Et chez nous ?** La cellule du paragraphe 4 le montre : pour les espèces, la colonne `nulls` contient les paiements sans référence et `chaines_vides` vaut 0. Une fois les références chargées, `nulls` ne doit concerner que les paiements sans opérateur et `chaines_vides` doit valoir 0 : les vides sont de vrais `NULL`.

## Ce qu'on retient
- Chaque manque a une raison : stock (transactions), attributs (MongoDB), commentaires (agrégations), références (idempotence au Module 3).
- Le **stock vit dans PostgreSQL** parce qu'il touche à l'argent.
- `NULL` n'est pas `''` : c'est ce qui rend l'`UNIQUE` utilisable sur une colonne facultative.
'''))

build("ch1_enrichir.ipynb", C)
print("ch1_enrichir.ipynb créé")
