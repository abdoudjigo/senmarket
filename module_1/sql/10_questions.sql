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
