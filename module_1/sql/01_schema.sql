-- Schéma SenMarket : les huit tables, avec leurs contraintes.
--
-- Usage (le nom du schéma est un paramètre) :
--   psql -v schema=principal -v ON_ERROR_STOP=1 < sql/01_schema.sql
--
-- Tout se passe dans UNE transaction : en cas d'erreur, rien n'est créé à moitié.
-- CREATE SCHEMA sans IF NOT EXISTS : le script refuse d'écraser un schéma existant.
-- Les colonnes de clé étrangère ne sont PAS indexées ici, exprès : les mesures
-- « avant / après index » du chapitre 2.5 doivent partir d'un état honnête.

BEGIN;

CREATE SCHEMA :"schema";
SET LOCAL search_path TO :"schema";

-- Met à jour modifie_le à chaque modification d'une ligne (sert aux chargements
-- incrémentaux du module 3 : un simple DEFAULT ne jouerait qu'à l'insertion).
CREATE FUNCTION maj_modifie_le() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.modifie_le := now();
    RETURN NEW;
END;
$$;

-- ---------------------------------------------------------------------------
-- clients : un client. email et telephone sont facultatifs (NULL = absent).
-- ---------------------------------------------------------------------------
CREATE TABLE clients (
    client_id         TEXT PRIMARY KEY,
    nom_client        TEXT NOT NULL,
    email             TEXT,
    telephone         TEXT,
    ville             TEXT NOT NULL,
    region            TEXT NOT NULL,
    date_inscription  DATE NOT NULL,
    cree_le           TIMESTAMPTZ NOT NULL DEFAULT now(),
    modifie_le        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- vendeurs : un vendeur.
-- ---------------------------------------------------------------------------
CREATE TABLE vendeurs (
    vendeur_id   TEXT PRIMARY KEY,
    nom_vendeur  TEXT NOT NULL,
    ville        TEXT NOT NULL,
    region       TEXT NOT NULL,
    cree_le      TIMESTAMPTZ NOT NULL DEFAULT now(),
    modifie_le   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- produits : un produit du catalogue. Le prix payé n'est PAS ici : il est dans
-- lignes_commande (le catalogue peut changer sans réécrire l'historique).
-- stock : pas de valeur par défaut, un chargement qui l'oublie doit échouer.
-- ---------------------------------------------------------------------------
CREATE TABLE produits (
    produit_id          TEXT PRIMARY KEY,
    nom_produit         TEXT NOT NULL,
    categorie           TEXT NOT NULL,
    vendeur_id          TEXT NOT NULL,
    prix_catalogue_xof  BIGINT NOT NULL,
    actif               BOOLEAN NOT NULL,
    stock               INTEGER NOT NULL,
    cree_le             TIMESTAMPTZ NOT NULL DEFAULT now(),
    modifie_le          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_produits_vendeur
        FOREIGN KEY (vendeur_id) REFERENCES vendeurs (vendeur_id) ON DELETE RESTRICT,
    CONSTRAINT ck_produits_prix_positif CHECK (prix_catalogue_xof > 0),
    CONSTRAINT ck_produits_stock_positif CHECK (stock >= 0)
);

-- ---------------------------------------------------------------------------
-- commandes : une commande (statuts : les libellés exacts des données du module 0).
-- RESTRICT : on ne supprime pas un client qui a des commandes (on garde l'historique).
-- ---------------------------------------------------------------------------
CREATE TABLE commandes (
    commande_id    TEXT PRIMARY KEY,
    client_id      TEXT NOT NULL,
    date_commande  DATE NOT NULL,
    statut         TEXT NOT NULL,
    cree_le        TIMESTAMPTZ NOT NULL DEFAULT now(),
    modifie_le     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_commandes_client
        FOREIGN KEY (client_id) REFERENCES clients (client_id) ON DELETE RESTRICT,
    CONSTRAINT ck_commandes_statut
        CHECK (statut IN ('en_preparation', 'expédiée', 'livrée', 'annulée'))
);

-- ---------------------------------------------------------------------------
-- lignes_commande : un produit dans une commande. prix_unitaire_xof = le prix PAYÉ.
-- CASCADE : une ligne n'a aucun sens sans sa commande.
-- ---------------------------------------------------------------------------
CREATE TABLE lignes_commande (
    ligne_commande_id  TEXT PRIMARY KEY,
    commande_id        TEXT NOT NULL,
    produit_id         TEXT NOT NULL,
    quantite           INTEGER NOT NULL,
    prix_unitaire_xof  BIGINT NOT NULL,
    montant_xof        BIGINT NOT NULL,
    cree_le            TIMESTAMPTZ NOT NULL DEFAULT now(),
    modifie_le         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_lignes_commande
        FOREIGN KEY (commande_id) REFERENCES commandes (commande_id) ON DELETE CASCADE,
    CONSTRAINT fk_lignes_produit
        FOREIGN KEY (produit_id) REFERENCES produits (produit_id) ON DELETE RESTRICT,
    CONSTRAINT ck_lignes_quantite_positive CHECK (quantite > 0),
    CONSTRAINT ck_lignes_prix_positif CHECK (prix_unitaire_xof > 0),
    -- La base vérifie l'arithmétique : montant = quantité x prix payé
    CONSTRAINT ck_lignes_montant_coherent CHECK (montant_xof = quantite * prix_unitaire_xof)
);

-- ---------------------------------------------------------------------------
-- paiements : une TENTATIVE de paiement (une commande peut en avoir plusieurs).
-- reference_transaction : vide (NULL) si et seulement si le paiement est en espèces.
-- UNIQUE accepte plusieurs NULL (deux absences ne sont pas « égales ») : c'est ce qui
-- permet plusieurs paiements en espèces. Une chaîne vide '' est interdite : elle,
-- serait une vraie valeur, et deux '' violeraient le UNIQUE.
-- ---------------------------------------------------------------------------
CREATE TABLE paiements (
    paiement_id            TEXT PRIMARY KEY,
    commande_id            TEXT NOT NULL,
    methode_paiement       TEXT NOT NULL,
    statut_paiement        TEXT NOT NULL,
    montant_xof            BIGINT NOT NULL,
    date_paiement          DATE NOT NULL,
    reference_transaction  TEXT,
    cree_le                TIMESTAMPTZ NOT NULL DEFAULT now(),
    modifie_le             TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_paiements_commande
        FOREIGN KEY (commande_id) REFERENCES commandes (commande_id) ON DELETE RESTRICT,
    CONSTRAINT ck_paiements_methode
        CHECK (methode_paiement IN ('Wave', 'Orange Money', 'Carte bancaire', 'Espèces')),
    CONSTRAINT ck_paiements_statut
        CHECK (statut_paiement IN ('en_attente', 'réussi', 'échoué')),
    CONSTRAINT ck_paiements_montant_positif CHECK (montant_xof >= 0),
    CONSTRAINT uq_paiements_reference UNIQUE (reference_transaction),
    CONSTRAINT ck_paiements_reference_non_vide CHECK (reference_transaction <> ''),
    -- Pas de référence pour l'argent liquide, une référence pour tout le reste
    CONSTRAINT ck_paiements_reference_selon_methode
        CHECK ((methode_paiement = 'Espèces') = (reference_transaction IS NULL))
);

-- ---------------------------------------------------------------------------
-- avis : un avis client. Il se rattache à un client, un produit ET une commande.
-- Une commande peut avoir plusieurs avis (un par produit acheté).
-- ---------------------------------------------------------------------------
CREATE TABLE avis (
    avis_id      TEXT PRIMARY KEY,
    client_id    TEXT NOT NULL,
    produit_id   TEXT NOT NULL,
    commande_id  TEXT NOT NULL,
    note         SMALLINT NOT NULL,
    date_avis    DATE NOT NULL,
    commentaire  TEXT NOT NULL,
    cree_le      TIMESTAMPTZ NOT NULL DEFAULT now(),
    modifie_le   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_avis_client
        FOREIGN KEY (client_id) REFERENCES clients (client_id) ON DELETE RESTRICT,
    CONSTRAINT fk_avis_produit
        FOREIGN KEY (produit_id) REFERENCES produits (produit_id) ON DELETE RESTRICT,
    CONSTRAINT fk_avis_commande
        FOREIGN KEY (commande_id) REFERENCES commandes (commande_id) ON DELETE RESTRICT,
    CONSTRAINT ck_avis_note_1_a_5 CHECK (note BETWEEN 1 AND 5)
);

-- ---------------------------------------------------------------------------
-- navigation : un événement de navigation. client_id et produit_id sont facultatifs
-- (sessions anonymes, pages sans produit) : SET NULL, le trafic reste utile.
-- ---------------------------------------------------------------------------
CREATE TABLE navigation (
    evenement_id     TEXT PRIMARY KEY,
    session_id       TEXT NOT NULL,
    client_id        TEXT,
    produit_id       TEXT,
    type_evenement   TEXT NOT NULL,
    date_evenement   TIMESTAMPTZ NOT NULL,
    cree_le          TIMESTAMPTZ NOT NULL DEFAULT now(),
    modifie_le       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_navigation_client
        FOREIGN KEY (client_id) REFERENCES clients (client_id) ON DELETE SET NULL,
    CONSTRAINT fk_navigation_produit
        FOREIGN KEY (produit_id) REFERENCES produits (produit_id) ON DELETE SET NULL,
    CONSTRAINT ck_navigation_type_evenement
        CHECK (type_evenement IN ('page_vue', 'recherche', 'vue_produit',
                                  'ajout_panier', 'debut_paiement'))
);

-- ---------------------------------------------------------------------------
-- Un déclencheur par table : modifie_le suit chaque modification.
-- ---------------------------------------------------------------------------
CREATE TRIGGER trg_maj_clients BEFORE UPDATE ON clients
    FOR EACH ROW EXECUTE FUNCTION maj_modifie_le();
CREATE TRIGGER trg_maj_vendeurs BEFORE UPDATE ON vendeurs
    FOR EACH ROW EXECUTE FUNCTION maj_modifie_le();
CREATE TRIGGER trg_maj_produits BEFORE UPDATE ON produits
    FOR EACH ROW EXECUTE FUNCTION maj_modifie_le();
CREATE TRIGGER trg_maj_commandes BEFORE UPDATE ON commandes
    FOR EACH ROW EXECUTE FUNCTION maj_modifie_le();
CREATE TRIGGER trg_maj_lignes_commande BEFORE UPDATE ON lignes_commande
    FOR EACH ROW EXECUTE FUNCTION maj_modifie_le();
CREATE TRIGGER trg_maj_paiements BEFORE UPDATE ON paiements
    FOR EACH ROW EXECUTE FUNCTION maj_modifie_le();
CREATE TRIGGER trg_maj_avis BEFORE UPDATE ON avis
    FOR EACH ROW EXECUTE FUNCTION maj_modifie_le();
CREATE TRIGGER trg_maj_navigation BEFORE UPDATE ON navigation
    FOR EACH ROW EXECUTE FUNCTION maj_modifie_le();

COMMIT;
