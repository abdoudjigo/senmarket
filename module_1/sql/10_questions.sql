-- Questions d'Awa (chapitre 2.3). Une requête par question, commentée.
-- Usage (depuis module_1/) :
--   dc exec -T postgres sh -c 'psql -U $POSTGRES_USER -d $POSTGRES_DB -v ON_ERROR_STOP=1' < sql/10_questions.sql
-- Pour la partition volume, remplace « principal » par « volume » ci-dessous.

SET search_path TO principal;

-- ===========================================================================
-- SM-120 : « Combien chaque région nous rapporte-t-elle ? »
-- CA = somme de lignes_commande.montant_xof (toutes les lignes, quel que soit
-- le statut de la commande ou du paiement : même définition qu'au module 0).
-- Chaîne de jointures : lignes_commande -> commandes -> clients.
-- ===========================================================================
SELECT
    cl.region,
    SUM(l.montant_xof)                                            AS ca_xof,
    COUNT(DISTINCT c.commande_id)                                 AS nb_commandes,
    ROUND(100.0 * SUM(l.montant_xof) / SUM(SUM(l.montant_xof)) OVER (), 1) AS part_pct
FROM lignes_commande l
JOIN commandes c  ON c.commande_id = l.commande_id
JOIN clients   cl ON cl.client_id  = c.client_id
GROUP BY cl.region
ORDER BY ca_xof DESC;

-- Invariant 1 : la somme des régions égale le CA total (l'écart doit valoir 0).
WITH par_region AS (
    SELECT cl.region, SUM(l.montant_xof) AS ca_xof
    FROM lignes_commande l
    JOIN commandes c  ON c.commande_id = l.commande_id
    JOIN clients   cl ON cl.client_id  = c.client_id
    GROUP BY cl.region
)
SELECT
    (SELECT SUM(montant_xof) FROM lignes_commande)                    AS ca_total,
    SUM(ca_xof)                                                        AS somme_des_regions,
    (SELECT SUM(montant_xof) FROM lignes_commande) - SUM(ca_xof)       AS ecart
FROM par_region;

-- Invariant 2 (anti-piège) : les jointures ne multiplient ni ne perdent aucune ligne.
SELECT
    (SELECT COUNT(*) FROM lignes_commande) AS lignes_avant,
    COUNT(*)                               AS lignes_apres_jointures
FROM lignes_commande l
JOIN commandes c  ON c.commande_id = l.commande_id
JOIN clients   cl ON cl.client_id  = c.client_id;

-- Contrôle de données : les clients de ville « Inconnue » ont-ils une région cohérente ?
SELECT ville, region, COUNT(*) AS nb_clients
FROM clients
WHERE ville = 'Inconnue' OR region = 'Inconnue'
GROUP BY ville, region
ORDER BY nb_clients DESC;

-- ===========================================================================
-- SM-121 : « Quels sont les trois produits les plus vendus de chaque catégorie ? »
-- Définition : « le plus vendu » = quantité totale vendue (SUM(quantite)).
-- PARTITION BY categorie : le classement repart de 1 dans chaque catégorie.
-- Deux fenêtres : ROW_NUMBER a besoin d'un départage fixe (produit_id), sinon
-- le résultat pourrait changer d'une exécution à l'autre ; RANK et DENSE_RANK
-- doivent classer SANS départage pour montrer ce qu'elles font des égalités.
-- ===========================================================================
-- Résultat final : au plus 3 produits par catégorie
WITH ventes AS (
    SELECT p.categorie, p.produit_id, p.nom_produit, SUM(l.quantite) AS qte_vendue
    FROM lignes_commande l
    JOIN produits p ON p.produit_id = l.produit_id
    GROUP BY p.categorie, p.produit_id, p.nom_produit
),
classes AS (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY categorie ORDER BY qte_vendue DESC, produit_id) AS rang
    FROM ventes
)
SELECT categorie, rang, produit_id, nom_produit, qte_vendue
FROM classes
WHERE rang <= 3
ORDER BY categorie, rang;

-- Invariant : au plus 3 produits par catégorie (cette requête doit renvoyer 0 ligne)
WITH ventes AS (
    SELECT p.categorie, p.produit_id, SUM(l.quantite) AS qte_vendue
    FROM lignes_commande l JOIN produits p ON p.produit_id = l.produit_id
    GROUP BY p.categorie, p.produit_id
),
classes AS (
    SELECT categorie,
           ROW_NUMBER() OVER (PARTITION BY categorie ORDER BY qte_vendue DESC, produit_id) AS rang
    FROM ventes
)
SELECT categorie, COUNT(*) AS nb
FROM classes WHERE rang <= 3
GROUP BY categorie HAVING COUNT(*) > 3;

-- Les égalités : les trois fonctions côte à côte, là où deux produits ont la même quantité
WITH ventes AS (
    SELECT p.categorie, p.produit_id, SUM(l.quantite) AS qte_vendue
    FROM lignes_commande l JOIN produits p ON p.produit_id = l.produit_id
    GROUP BY p.categorie, p.produit_id
),
classes AS (
    SELECT categorie, produit_id, qte_vendue,
           ROW_NUMBER() OVER (PARTITION BY categorie ORDER BY qte_vendue DESC, produit_id) AS row_number,
           RANK()       OVER (PARTITION BY categorie ORDER BY qte_vendue DESC) AS rank,
           DENSE_RANK() OVER (PARTITION BY categorie ORDER BY qte_vendue DESC) AS dense_rank,
           COUNT(*)     OVER (PARTITION BY categorie, qte_vendue)              AS nb_ex_aequo
    FROM ventes
)
SELECT categorie, produit_id, qte_vendue, row_number, rank, dense_rank
FROM classes
WHERE nb_ex_aequo > 1
ORDER BY categorie, qte_vendue DESC, produit_id;

-- ---------------------------------------------------------------------------
-- SM-121, les égalités (variante de mesure) : aucune égalité n'existe sur la
-- quantité vendue (voir plus haut : 0 ligne), ni sur la partition volume. On en a
-- trouvé sur le NOMBRE DE COMMANDES contenant le produit. La définition de SM-121
-- reste « quantité vendue » ; cette mesure sert seulement à montrer comment
-- ROW_NUMBER, RANK et DENSE_RANK traitent une égalité.
-- On affiche toute la catégorie (pas seulement les ex æquo) pour voir le « trou » de RANK.
-- ---------------------------------------------------------------------------
WITH v AS (
    SELECT p.categorie, p.produit_id, p.nom_produit,
           COUNT(DISTINCT l.commande_id) AS nb_commandes
    FROM lignes_commande l
    JOIN produits p ON p.produit_id = l.produit_id
    GROUP BY p.categorie, p.produit_id, p.nom_produit
),
c AS (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY categorie ORDER BY nb_commandes DESC, produit_id) AS row_number,
           RANK()       OVER (PARTITION BY categorie ORDER BY nb_commandes DESC)             AS rank,
           DENSE_RANK() OVER (PARTITION BY categorie ORDER BY nb_commandes DESC)             AS dense_rank,
           COUNT(*)     OVER (PARTITION BY categorie, nb_commandes)                          AS nb_ex_aequo
    FROM v
),
d AS (   -- une fonction de fenêtre ne s'imbrique pas dans une autre : d'où cette étape
    SELECT *, MAX(nb_ex_aequo) OVER (PARTITION BY categorie) AS egalite_dans_categorie
    FROM c
)
SELECT categorie, produit_id, nom_produit, nb_commandes, row_number, rank, dense_rank
FROM d
WHERE egalite_dans_categorie > 1
ORDER BY categorie, row_number;

-- ===========================================================================
-- SM-122 : « Comment évolue le CA mois après mois, et quelle est la variation ? »
-- CA = somme de lignes_commande.montant_xof, rattaché au mois de date_commande.
-- LAG : valeur du mois précédent ; NULL pour le premier mois (pas 0 : 0 % voudrait
-- dire « aucun changement », ce qui est faux). Moyenne mobile : mois courant + 2
-- précédents ; NULL tant qu'il n'y a pas 3 mois. nb_jours / premier_jour / dernier_jour
-- repèrent les mois incomplets aux deux extrémités.
-- ===========================================================================
WITH mensuel AS (
    SELECT date_trunc('month', c.date_commande)::date AS mois,
           SUM(l.montant_xof)                          AS ca_xof,
           COUNT(DISTINCT c.date_commande)             AS nb_jours,
           MIN(c.date_commande)                        AS premier_jour,
           MAX(c.date_commande)                        AS dernier_jour
    FROM lignes_commande l
    JOIN commandes c ON c.commande_id = l.commande_id
    GROUP BY 1
)
SELECT mois, ca_xof,
       LAG(ca_xof) OVER (ORDER BY mois)                                        AS ca_mois_precedent,
       ROUND(100.0 * (ca_xof - LAG(ca_xof) OVER (ORDER BY mois))
             / NULLIF(LAG(ca_xof) OVER (ORDER BY mois), 0), 1)                 AS variation_pct,
       CASE WHEN COUNT(*) OVER w = 3 THEN ROUND(AVG(ca_xof) OVER w, 0) END     AS moyenne_mobile_3m,
       nb_jours, premier_jour, dernier_jour
FROM mensuel
WINDOW w AS (ORDER BY mois ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)
ORDER BY mois;

-- Invariant 1 : la somme des mois égale le CA total (l'écart doit valoir 0).
WITH mensuel AS (
    SELECT date_trunc('month', c.date_commande)::date AS mois, SUM(l.montant_xof) AS ca_xof
    FROM lignes_commande l JOIN commandes c ON c.commande_id = l.commande_id
    GROUP BY 1
)
SELECT (SELECT SUM(montant_xof) FROM lignes_commande) - SUM(ca_xof) AS ecart FROM mensuel;

-- Invariant 2 : la variation du premier mois est NULL, et elle est la seule (doit afficher 1 | 1).
WITH mensuel AS (
    SELECT date_trunc('month', c.date_commande)::date AS mois, SUM(l.montant_xof) AS ca_xof
    FROM lignes_commande l JOIN commandes c ON c.commande_id = l.commande_id
    GROUP BY 1
),
v AS (
    SELECT mois, ca_xof - LAG(ca_xof) OVER (ORDER BY mois) AS variation FROM mensuel
)
SELECT COUNT(*) FILTER (WHERE variation IS NULL)                              AS nb_null,
       COUNT(*) FILTER (WHERE variation IS NULL AND mois = (SELECT MIN(mois) FROM mensuel)) AS dont_premier_mois
FROM v;

-- ===========================================================================
-- SM-123 : « Quel est notre panier moyen ? »
-- Panier d'une commande = somme de ses lignes (jamais la valeur d'une seule ligne).
-- Agrégation en DEUX temps : (1) une ligne par commande avec son panier, (2) la moyenne de ces paniers.
-- Piège évité : joindre commandes et lignes puis faire AVG d'une valeur de commande
-- compterait chaque commande autant de fois qu'elle a de lignes.
-- ===========================================================================
WITH panier AS (
    SELECT commande_id, SUM(montant_xof) AS montant_panier, COUNT(*) AS nb_lignes
    FROM lignes_commande
    GROUP BY commande_id
)
SELECT
    COUNT(*)                                                                      AS nb_commandes_avec_lignes,
    (SELECT COUNT(*) FROM commandes)                                              AS nb_commandes_total,
    ROUND(AVG(montant_panier), 0)                                                 AS panier_moyen_par_commande,
    ROUND((percentile_cont(0.5) WITHIN GROUP (ORDER BY montant_panier))::numeric, 0) AS panier_median,
    (SELECT ROUND(AVG(montant_xof), 0) FROM lignes_commande)                      AS moyenne_par_ligne,
    ROUND(AVG(nb_lignes), 2)                                                      AS lignes_par_commande
FROM panier;

-- Invariant 1 : la somme des paniers égale le CA total (écart 0).
-- Invariant 2 : panier moyen / moyenne par ligne = nombre moyen de lignes par commande (écart 0).
WITH panier AS (
    SELECT commande_id, SUM(montant_xof) AS montant_panier, COUNT(*) AS nb_lignes
    FROM lignes_commande GROUP BY commande_id
)
SELECT
    (SELECT SUM(montant_xof) FROM lignes_commande) - SUM(montant_panier)                AS ecart_ca,
    ROUND(AVG(montant_panier) / (SELECT AVG(montant_xof) FROM lignes_commande)
          - AVG(nb_lignes), 6)                                                          AS ecart_ratio
FROM panier;

-- ===========================================================================
-- SM-124 : « Combien de temps un client met-il à repasser une deuxième commande ? »
-- ROW_NUMBER numérote les commandes de chaque client (date, puis commande_id pour départager).
-- Délai = date de la 2e commande - date de la 1re (en jours).
-- Seuls les clients ayant AU MOINS 2 commandes comptent : les autres n'ont pas de 2e commande
-- (ce n'est pas un délai de 0 jour).
-- ===========================================================================
WITH ordonnees AS (
    SELECT client_id, date_commande,
           ROW_NUMBER() OVER (PARTITION BY client_id ORDER BY date_commande, commande_id) AS rang
    FROM commandes
),
delais AS (
    SELECT client_id,
           MAX(date_commande) FILTER (WHERE rang = 2) - MAX(date_commande) FILTER (WHERE rang = 1) AS jours
    FROM ordonnees
    WHERE rang <= 2
    GROUP BY client_id
    HAVING COUNT(*) = 2
)
SELECT
    COUNT(*)                                                           AS nb_clients_avec_2_commandes,
    (SELECT COUNT(DISTINCT client_id) FROM commandes)                  AS nb_clients_acheteurs,
    ROUND((percentile_cont(0.5) WITHIN GROUP (ORDER BY jours))::numeric, 1) AS delai_median_jours,
    ROUND(AVG(jours), 1)                                               AS delai_moyen_jours,
    MIN(jours)                                                         AS delai_min,
    MAX(jours)                                                         AS delai_max,
    COUNT(*) FILTER (WHERE jours = 0)                                  AS meme_jour
FROM delais;

-- Invariant : chaque client n'apparaît qu'une fois ; le nombre de clients retenus égale
-- le nombre de clients ayant au moins 2 commandes (écart attendu : 0).
SELECT
    (SELECT COUNT(*) FROM (SELECT client_id FROM commandes GROUP BY client_id HAVING COUNT(*) >= 2) t) AS attendu,
    (SELECT COUNT(*) FROM (
        SELECT client_id FROM (
            SELECT client_id, ROW_NUMBER() OVER (PARTITION BY client_id ORDER BY date_commande, commande_id) AS rang
            FROM commandes) o
        WHERE rang = 2) t)                                                                              AS obtenu;
