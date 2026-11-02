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
