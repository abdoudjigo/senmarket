-- Le coffre-fort de SenMarket : tout ce qui touche à l'argent et au stock.
-- Règle : la base REFUSE l'incohérence, quel que soit le programme qui écrit.
-- Ce script est lancé par scripts/1_charger.py, dans le schéma choisi.

CREATE TABLE vendeurs (
    vendeur_id  TEXT PRIMARY KEY,
    nom_vendeur TEXT NOT NULL,
    ville       TEXT,
    region      TEXT
);

CREATE TABLE clients (
    client_id        TEXT PRIMARY KEY,
    nom_client       TEXT NOT NULL,
    email            TEXT,
    telephone        TEXT,
    ville            TEXT,
    region           TEXT,
    date_inscription DATE NOT NULL
);

CREATE TABLE produits (
    produit_id         TEXT PRIMARY KEY,
    nom_produit        TEXT NOT NULL,
    categorie          TEXT NOT NULL,
    vendeur_id         TEXT NOT NULL REFERENCES vendeurs (vendeur_id),
    prix_catalogue_xof BIGINT NOT NULL CHECK (prix_catalogue_xof > 0),  -- XOF : entier, jamais FLOAT
    actif              BOOLEAN NOT NULL,
    stock              INTEGER NOT NULL CHECK (stock >= 0)              -- filet de sécurité
);

CREATE TABLE commandes (
    commande_id   TEXT PRIMARY KEY,
    client_id     TEXT NOT NULL REFERENCES clients (client_id),         -- pas de commande sans client
    date_commande DATE NOT NULL,
    statut        TEXT NOT NULL
);

CREATE TABLE lignes_commande (
    ligne_commande_id TEXT PRIMARY KEY,
    commande_id       TEXT NOT NULL REFERENCES commandes (commande_id) ON DELETE CASCADE,  -- une ligne n'a pas de sens sans sa commande
    produit_id        TEXT NOT NULL REFERENCES produits (produit_id),                       -- un produit vendu reste dans l'historique
    quantite          INTEGER NOT NULL CHECK (quantite > 0),
    prix_unitaire_xof BIGINT  NOT NULL CHECK (prix_unitaire_xof > 0),                       -- le prix PAYE (peut différer du catalogue)
    montant_xof       BIGINT  NOT NULL,
    CHECK (montant_xof = quantite * prix_unitaire_xof)
);

CREATE TABLE paiements (
    paiement_id           TEXT PRIMARY KEY,
    commande_id           TEXT NOT NULL REFERENCES commandes (commande_id),
    methode_paiement      TEXT NOT NULL,
    statut_paiement       TEXT NOT NULL,
    montant_xof           BIGINT NOT NULL CHECK (montant_xof >= 0),
    date_paiement         DATE,
    -- Identifiant côté Wave / Orange Money : le module 3 s'en servira pour ne jamais
    -- importer deux fois le même paiement. UNIQUE accepte plusieurs NULL (espèces).
    reference_transaction TEXT UNIQUE
);
