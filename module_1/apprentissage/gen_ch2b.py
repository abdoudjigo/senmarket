from _nb import build

C = []
C.append(("md", '''
# Chapitre 2b : SQL analytique, les 8 questions d'Awa (SM-120 à SM-127)

## À comprendre
Une question métier se traduit d'abord en **définition précise**, puis en requête, puis en **invariant** : une vérité qui doit tenir sur n'importe quel jeu de données (« la somme des régions égale le total »). Si l'invariant casse, c'est un bug.

Les requêtes sont dans `sql/10_questions.sql` (avec leurs commentaires). Chaque cellule ci-dessous affiche la requête puis son résultat.
'''))
C.append(("code", '''
import re
import duckdb, pandas as pd, psycopg
from IPython.display import Markdown, display
from senmarket_bases.connexions import RACINE, connexion_postgres

S = "principal"
PARQUET = RACINE / "data" / "processed" / "date=2026-10-29"
texte = (RACINE / "sql" / "10_questions.sql").read_text(encoding="utf-8")

# one chunk per ticket: split on the "-- ====" banner that precedes each "-- SM-xxx :" line
TICKETS = {re.match(r"-- (SM-\\d+)", m).group(1): m
           for m in re.split(r"(?m)^-- =+\\n(?=-- SM-\\d+ :)", texte)[1:]}

def instructions(chunk):
    """Split a ticket into statements (a statement ends with a line finishing by ';')."""
    buf, out = [], []
    for ligne in chunk.splitlines():
        buf.append(ligne)
        if ligne.strip().endswith(";") and not ligne.strip().startswith("--"):
            out.append("\\n".join(buf)); buf = []
    return out

def executer(stmt):
    code = "\\n".join(l for l in stmt.splitlines() if not l.strip().startswith("--"))
    try:
        with connexion_postgres() as conn:
            conn.execute(f"SET search_path TO {S}")
            cur = conn.execute(code)
            return pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description]), "PostgreSQL"
    except psycopg.errors.UndefinedTable:
        # navigation is not loaded in PostgreSQL: same SQL, run by DuckDB on the Parquet file
        con = duckdb.connect()
        con.execute(f"CREATE VIEW navigation AS SELECT * FROM read_parquet('{PARQUET}/navigation.parquet')")
        return con.execute(code.rstrip().rstrip(";")).df(), "DuckDB sur le Parquet (navigation absente de PostgreSQL)"

def ticket(num):
    for stmt in instructions(TICKETS[num]):
        display(Markdown("```sql\\n" + stmt + "\\n```"))
        df, moteur = executer(stmt)
        if moteur != "PostgreSQL":
            print("->", moteur)
        display(df)
'''))

def bloc(num, titre, comprendre, lire):
    C.append(("md", f"## {num} : {titre}\n**À comprendre.** {comprendre}"))
    C.append(("code", f'ticket("{num}")'))
    C.append(("md", f"**À lire.** {lire}"))

bloc("SM-120", "« Combien chaque région nous rapporte-t-elle ? »",
     "Chaîne de jointures `lignes -> commandes -> clients`, puis `GROUP BY`. Le CA est la somme de `montant_xof` de toutes les lignes.",
     "Première table : le CA par région avec sa part. Ensuite : `ecart` doit valoir 0 (la somme des régions égale le total), et `lignes_avant = lignes_apres` prouve que les jointures n'ont multiplié ni perdu aucune ligne (le piège classique).")
bloc("SM-121", "« Quels sont les trois produits les plus vendus de chaque catégorie ? »",
     "Une **fonction de fenêtre** (`PARTITION BY categorie`) classe sans réduire les lignes, contrairement à `GROUP BY`. `ROW_NUMBER` départage toujours ; `RANK` laisse un trou après une égalité ; `DENSE_RANK` n'en laisse pas.",
     "Premier résultat : au plus 3 produits par catégorie (la requête d'invariant doit être vide). Le dernier tableau montre une égalité (sur le nombre de commandes) : comparer les trois colonnes de rang.")
bloc("SM-122", "« Comment évolue le chiffre d'affaires mois après mois ? »",
     "`LAG` va chercher la valeur du mois précédent. Le premier mois n'a pas de variation : c'est `NULL`, pas 0 (0 % voudrait dire « aucun changement », ce qui est faux). La moyenne mobile ne s'affiche qu'avec 3 mois.",
     "Regarder `nb_jours` : un mois incomplet aux extrémités fausse la variation. L'invariant 1 doit valoir 0 ; l'invariant 2 doit afficher `1 | 1`.")
bloc("SM-123", "« Quel est notre panier moyen ? »",
     "Agrégation **en deux temps** : une ligne par commande avec son panier (somme de ses lignes), puis la moyenne de ces paniers. Moyenner directement les lignes donnerait un autre chiffre.",
     "Comparer `panier_moyen_par_commande` et `moyenne_par_ligne` : ils diffèrent car une commande a plusieurs lignes (le rapport des deux vaut le nombre moyen de lignes par commande, `ecart_ratio` = 0).")
bloc("SM-124", "« Combien de temps un client met-il à repasser une deuxième commande ? »",
     "`ROW_NUMBER` numérote les commandes de chaque client ; le délai est la date de la 2e moins celle de la 1re. Seuls les clients ayant **au moins deux** commandes comptent (les autres n'ont pas de délai).",
     "Le nombre de clients retenus doit égaler `attendu = obtenu` dans l'invariant. La médiane est plus fiable que la moyenne si quelques délais sont très longs.")
bloc("SM-125", "« Quelles commandes n'ont aucun paiement réussi ? »",
     "**Anti-jointure** : chercher ce qui manque, avec `NOT EXISTS` ou `LEFT JOIN ... IS NULL`. Les valeurs réelles du statut s'écrivent avec accent (`réussi`) : on les lit avant de filtrer.",
     "On sépare deux causes : commandes **sans aucun paiement** et commandes dont le paiement est **non réussi**. L'écart entre les deux écritures doit valoir 0, et `paiements_sans_commande` aussi (la clé étrangère l'interdit).")
bloc("SM-126", "« Quel petit groupe de clients fait 80 % de notre chiffre d'affaires ? »",
     "Une **somme cumulée** en fenêtre (`ROWS UNBOUNDED PRECEDING`) sur les clients triés par CA décroissant ; on s'arrête au premier client qui atteint 80 %.",
     "`part_des_clients_pct` dit quelle fraction des clients fait 80 % du CA. L'invariant : le dernier cumul vaut 100 % et l'écart de CA vaut 0.")
bloc("SM-127", "« Combien de sessions finissent avec un article au panier mais sans début de paiement ? »",
     "On compte **par session** (`GROUP BY session_id`), jamais par événement : une session qui ajoute trois articles ne compte qu'une fois. L'ordre des événements n'est pas pris en compte.",
     "Le dernier tableau montre le piège : `lignes_sans_distinct` (une ligne par ajout au panier) est plus grand que `sessions_distinctes`.")

C.append(("md", "## Question : `NOT EXISTS` et `LEFT JOIN ... IS NULL` donnent-ils le même résultat, et le même plan ?\nRésultat identique : déjà prouvé dans SM-125 (écart = 0). Pour le plan, on demande à PostgreSQL ce qu'il compte faire."))
C.append(("code", '''
A = f"SELECT c.commande_id FROM {S}.commandes c WHERE NOT EXISTS (SELECT 1 FROM {S}.paiements p WHERE p.commande_id = c.commande_id AND p.statut_paiement = 'réussi')"
B = f"SELECT c.commande_id FROM {S}.commandes c LEFT JOIN {S}.paiements p ON p.commande_id = c.commande_id AND p.statut_paiement = 'réussi' WHERE p.paiement_id IS NULL"
with connexion_postgres() as conn:
    for nom, q in [("NOT EXISTS", A), ("LEFT JOIN ... IS NULL", B)]:
        plan = conn.execute(f"EXPLAIN (FORMAT JSON) {q}").fetchone()[0][0]["Plan"]
        print(f"{nom:<24} -> {plan['Node Type']}")
'''))
C.append(("md", '''
**Réponse.** Si les deux lignes affichent le même type de nœud (en général `Hash Anti Join`), PostgreSQL a reconnu que ce sont **la même question** posée de deux façons : il choisit la même stratégie. On choisit alors l'écriture la plus lisible (`NOT EXISTS`, qui dit « n'a aucun »).

## Ce qu'on retient
- Une définition écrite avant le code, un **invariant** vérifié après.
- Après une jointure, on revérifie le total : un montant de commande sommé sur des lignes est compté plusieurs fois.
- `NULL` n'est pas `0`, une anti-jointure cherche l'absence, et on compte par session, pas par événement.
'''))
build("ch2b_sql_analytique.ipynb", C)
print("ch2b_sql_analytique.ipynb créé")
