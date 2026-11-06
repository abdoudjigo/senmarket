from _nb import build

C = []
C.append(("md", '''
# Chapitre 2a : PostgreSQL, le coffre-fort des transactions (version courte)

> **Fatou (finance)** : « Le chiffre d'affaires du tableau de bord ne colle jamais avec les relevés Wave. Je trouve des commandes sans paiement et des paiements sans commande. »

## À comprendre
Dans des fichiers, rien n'empêche un paiement de pointer vers une commande qui n'existe pas : c'est un problème d'**intégrité référentielle**. Dans une base, c'est la **structure** qui l'interdit (clés étrangères, contraintes). Ce notebook montre quatre idées : **modéliser**, **charger**, **protéger** (transaction), **accélérer** (index). Les 8 questions d'Awa sont dans `ch2b`.
'''))
C.append(("code", '''
import statistics
import pandas as pd
import psycopg
from senmarket_bases.connexions import RACINE, connexion_postgres

S = "principal"
PARQUET = RACINE / "data" / "processed" / "date=2026-10-29"

def sql(requete, schema=S):
    with connexion_postgres() as conn:
        conn.execute(f"SET search_path TO {schema}")
        cur = conn.execute(requete)
        return pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])
'''))
C.append(("md", "## 1. Modéliser : les contraintes posées dans la base\nCombien de contraintes de chaque type par table ? Une règle posée dans la base protège **tous** les programmes, y compris ceux qu'on n'a pas encore écrits."))
C.append(("code", '''
df = sql("""SELECT table_name, constraint_type, COUNT(*) AS nb
            FROM information_schema.table_constraints
            WHERE table_schema = 'principal'
              AND constraint_type IN ('PRIMARY KEY', 'FOREIGN KEY', 'UNIQUE', 'CHECK')
              AND constraint_name NOT LIKE '%not_null'
            GROUP BY 1, 2""")
df.pivot(index="table_name", columns="constraint_type", values="nb").fillna(0).astype(int)
'''))
C.append(("md", "L'argent est-il bien un entier (jamais un `FLOAT`) ? Et que se passe-t-il à la suppression, pour chaque clé étrangère (`delete_rule`) ?"))
C.append(("code", '''
print(sql("""SELECT table_name, column_name, data_type FROM information_schema.columns
             WHERE table_schema = 'principal' AND column_name LIKE '%xof' ORDER BY 1, 2"""))
print(sql("""SELECT tc.table_name AS table_enfant, kcu.column_name, rc.delete_rule
             FROM information_schema.referential_constraints rc
             JOIN information_schema.table_constraints tc ON tc.constraint_name = rc.constraint_name AND tc.table_schema = rc.constraint_schema
             JOIN information_schema.key_column_usage kcu ON kcu.constraint_name = rc.constraint_name AND kcu.table_schema = rc.constraint_schema
             WHERE rc.constraint_schema = 'principal' ORDER BY 1, 2"""))
'''))
C.append(("md", "## 2. La preuve : une contrainte qu'on n'a jamais vue refuser n'est pas une contrainte testée\nOn tente quatre modifications interdites. Chacune est annulée (`rollback`) : les données ne bougent pas."))
C.append(("code", '''
def essayer(titre, requete, params=None):
    with connexion_postgres() as conn:
        try:
            conn.execute(requete, params)
            print(f"{titre:<12} PAS REFUSÉ")
        except psycopg.Error as e:
            print(f"{titre:<12} REFUSÉ -> {type(e).__name__}: {str(e).splitlines()[0]}")
        finally:
            conn.rollback()

essayer("clé étrangère", f"UPDATE {S}.paiements SET commande_id = 'CMD_INEXISTANT' WHERE paiement_id = (SELECT MIN(paiement_id) FROM {S}.paiements)")
essayer("CHECK", f"UPDATE {S}.lignes_commande SET quantite = 0 WHERE ligne_commande_id = (SELECT MIN(ligne_commande_id) FROM {S}.lignes_commande)")
essayer("NOT NULL", f"UPDATE {S}.commandes SET client_id = NULL WHERE commande_id = (SELECT MIN(commande_id) FROM {S}.commandes)")
ids = sql(f"SELECT paiement_id FROM {S}.paiements ORDER BY paiement_id LIMIT 2")["paiement_id"].tolist()
essayer("UNIQUE", f"UPDATE {S}.paiements SET reference_transaction = 'REF-DOUBLON' WHERE paiement_id IN (%s, %s)", ids)
'''))
C.append(("md", "## 3. Charger : la base est-elle fidèle aux fichiers ?\nPour chaque table chargée, le nombre de lignes doit être le même dans PostgreSQL et dans le Parquet."))
C.append(("code", '''
bilan = []
for t in sql(f"SELECT table_name FROM information_schema.tables WHERE table_schema = '{S}' ORDER BY 1")["table_name"]:
    fichier = PARQUET / f"{t}.parquet"
    if fichier.exists():
        n_pg = int(sql(f"SELECT COUNT(*) AS n FROM {S}.{t}")["n"][0])
        n_pq = len(pd.read_parquet(fichier))
        bilan.append((t, n_pg, n_pq, n_pg == n_pq))
bilan = pd.DataFrame(bilan, columns=["table", "postgresql", "parquet", "identique"])
print(bilan)
assert bilan["identique"].all()
print("OK : chaque table chargée a le même nombre de lignes que son Parquet")
'''))
C.append(("md", "## 4. Questions de Fatou : une commande peut-elle exister sans ligne ? Qui fait foi entre paiement et lignes ?"))
C.append(("code", '''
print(sql(f"""SELECT (SELECT COUNT(*) FROM {S}.commandes c WHERE NOT EXISTS (SELECT 1 FROM {S}.lignes_commande l WHERE l.commande_id = c.commande_id)) AS commandes_sans_ligne,
                     (SELECT COUNT(*) FROM {S}.paiements p WHERE NOT EXISTS (SELECT 1 FROM {S}.commandes c WHERE c.commande_id = p.commande_id)) AS paiements_sans_commande"""))
print(sql(f"""WITH l AS (SELECT commande_id, SUM(montant_xof) m FROM {S}.lignes_commande GROUP BY 1),
                   p AS (SELECT commande_id, SUM(montant_xof) m FROM {S}.paiements GROUP BY 1)
              SELECT COUNT(*) AS commandes_payees,
                     COUNT(*) FILTER (WHERE l.m <> p.m) AS montants_differents,
                     ROUND(100.0 * COUNT(*) FILTER (WHERE l.m <> p.m) / COUNT(*), 2) AS pct
              FROM l JOIN p USING (commande_id)"""))
'''))
C.append(("md", '''
**Réponses.**
- *Paiement sans commande :* le résultat ci-dessus le montre, la clé étrangère l'**interdit** : c'est exactement ce que Fatou subissait dans les fichiers.
- *Commande sans ligne :* le schéma ne l'empêche pas (une clé étrangère garantit qu'un enfant a un parent, pas l'inverse). Une commande vide est un défaut de qualité qu'on détecte par requête, comme ici.
- *Qui fait foi ?* Les **lignes de commande** (le prix réellement payé, produit par produit). Le montant du paiement est une **copie** qui peut légitimement différer (frais, remise) : l'écart mesuré ci-dessus est volontaire, c'est celui que la finance doit rapprocher.
'''))
C.append(("md", '''
## 5. Protéger : transaction et concurrence (tickets de Moussa et Fatou)
Deux problèmes, deux outils :
- **Atomicité** (commande + paiement forment un tout) -> une **transaction** : `ROLLBACK` annule tout.
- **Isolation** (deux acheteurs en même temps) -> une **mise à jour atomique conditionnelle** : `UPDATE ... SET stock = stock - 1 WHERE ... AND stock >= 1`, puis on regarde combien de lignes ont été touchées.
'''))
C.append(("code", '''
with connexion_postgres() as c:
    tbl = c.execute("SELECT table_name FROM information_schema.columns WHERE table_schema = %s AND column_name = 'stock'", (S,)).fetchone()[0]
    pid, v0 = c.execute(f"SELECT produit_id, stock FROM {S}.{tbl} WHERE stock >= 1 ORDER BY stock, produit_id LIMIT 1").fetchone()
    rupture = c.execute(f"SELECT produit_id FROM {S}.{tbl} WHERE stock = 0 ORDER BY produit_id LIMIT 1").fetchone()

DEC = f"UPDATE {S}.{tbl} SET stock = stock - 1 WHERE produit_id = %s AND stock >= 1"
lire = lambda conn: conn.execute(f"SELECT stock FROM {S}.{tbl} WHERE produit_id = %s", (pid,)).fetchone()[0]

# 1. atomicity: a failed order leaves nothing behind
with connexion_postgres() as a:
    a.execute(DEC, (pid,))
    print(f"{pid} : stock avant = {v0} | dans la transaction = {lire(a)}")
    a.rollback()  # simulates a crash before the payment is written
    print(f"{pid} : après ROLLBACK, stock = {lire(a)}  (rien n'a bougé)")
    assert lire(a) == v0

# 2. a sold-out product is refused, stock never goes negative
if rupture:
    with connexion_postgres() as a:
        n = a.execute(DEC, (rupture[0],)).rowcount
        print(f"{rupture[0]} (rupture) : {n} ligne modifiée -> commande REFUSÉE, pas de stock négatif")
        a.rollback()
'''))
C.append(("md", "**Concurrence.** Deux acheteurs pour le **dernier** article. A décrémente sans valider encore ; B tente la même chose. PostgreSQL verrouille la ligne : B **attend** A. Une fois A validé, B relit un stock à 0 et son `UPDATE` ne touche aucune ligne : la double vente est impossible. (On remet le stock d'origine à la fin.)"))
C.append(("code", '''
try:
    with connexion_postgres() as a, connexion_postgres() as b:
        a.execute(f"UPDATE {S}.{tbl} SET stock = 1 WHERE produit_id = %s", (pid,)); a.commit()  # scenario: last item
        a.execute(DEC, (pid,))                      # A buys it, not committed yet
        b.execute("SET lock_timeout = '1s'")
        try:
            b.execute(DEC, (pid,))
            print("B n'a PAS attendu (inattendu)")
        except psycopg.errors.LockNotAvailable:
            print("B attend A : la ligne est verrouillée par la transaction de A")
            b.rollback()
        a.commit()                                  # A validates: stock is now 0
        n = b.execute(DEC, (pid,)).rowcount
        print(f"Après le COMMIT de A, B modifie {n} ligne -> commande de B REFUSÉE (plus de stock)")
        b.rollback()
        assert n == 0
finally:
    with connexion_postgres() as c:                 # always restore the original stock
        c.execute(f"UPDATE {S}.{tbl} SET stock = %s WHERE produit_id = %s", (v0, pid)); c.commit()
        print("stock d'origine restauré :", lire(c))
'''))
C.append(("md", '''
**Réponse.** Une transaction seule ne suffit pas contre la concurrence : c'est la **condition dans l'`UPDATE`** (`stock >= 1`) plus le verrou de ligne qui garantissent une seule vente. Un `CHECK (stock >= 0)` empêche le pire (stock négatif) mais ferait échouer la 2e commande **après** coup, peut-être après avoir débité le client.
**Justificatif :** les sorties ci-dessus (B attend, puis 0 ligne modifiée).
**Refus métier ou panne technique ?** Un `rowcount = 0` est un refus normal (« plus de stock », à dire au client) ; une exception (`psycopg.Error`) est une panne (à journaliser et réessayer). Le code doit distinguer les deux.
'''))
C.append(("md", "## 6. Accélérer : un index, mesuré sur la partition volume (199 997 lignes)\nUne optimisation sans mesure avant/après est une opinion. On mesure 5 fois, on garde la médiane (la 1re exécution est à froid)."))
C.append(("code", '''
def mesurer(requete, schema="volume", n=5):
    with connexion_postgres() as conn:
        conn.execute(f"SET search_path TO {schema}")
        temps = []
        for _ in range(n):
            plan = conn.execute(f"EXPLAIN (ANALYZE, FORMAT JSON) {requete}").fetchone()[0][0]
            temps.append(plan["Execution Time"])
        return plan["Plan"]["Node Type"], statistics.median(temps)

with connexion_postgres() as conn:
    conn.execute("SET search_path TO volume")
    conn.execute("DROP INDEX IF EXISTS idx_lignes_produit"); conn.commit()
    produit = conn.execute("SELECT produit_id FROM lignes_commande GROUP BY 1 ORDER BY COUNT(*), 1 LIMIT 1").fetchone()[0]

Q = f"SELECT * FROM lignes_commande WHERE produit_id = '{produit}'"
noeud_avant, t_avant = mesurer(Q)
with connexion_postgres() as conn:
    conn.execute("SET search_path TO volume")
    conn.execute("CREATE INDEX idx_lignes_produit ON lignes_commande(produit_id)")
    conn.execute("ANALYZE lignes_commande"); conn.commit()
noeud_apres, t_apres = mesurer(Q)
print(f"Sans index : {noeud_avant:<20} {t_avant:7.2f} ms")
print(f"Avec index : {noeud_apres:<20} {t_apres:7.2f} ms   (x{t_avant / t_apres:.0f} plus rapide)")
assert t_apres < t_avant
'''))
C.append(("md", "**Contre-exemple : un index qui ne sert pas.** Si on applique une fonction à la colonne indexée (`lower(...)`), PostgreSQL ne peut plus utiliser l'index : il revient au balayage complet."))
C.append(("code", '''
noeud, t = mesurer(f"SELECT * FROM lignes_commande WHERE lower(produit_id) = lower('{produit}')")
print(f"Avec lower(produit_id) : {noeud} en {t:.2f} ms  (l'index existe, mais n'est pas utilisé)")
'''))
C.append(("md", '''
**Réponse.** Sans index, PostgreSQL lit **toute** la table (`Seq Scan`) puis jette presque tout ; avec l'index, il va droit aux bonnes lignes (`Bitmap`/`Index Scan`). Le prix : chaque écriture met aussi l'index à jour, donc on n'en met pas partout.
**Justificatif :** les deux lignes de temps médians ci-dessus, et le contre-exemple `lower()`.

## Ce qu'on retient
- Les contraintes **refusent** l'incohérence : on l'a vu refuser (clé étrangère, CHECK, NOT NULL, UNIQUE).
- Une transaction = tout ou rien ; une mise à jour **conditionnelle** + le verrou de ligne = pas de double vente.
- Un index se **prouve** par un plan et une médiane, sur un jeu assez gros.
'''))
build("ch2a_postgres_base.ipynb", C)
print("ch2a_postgres_base.ipynb créé")
