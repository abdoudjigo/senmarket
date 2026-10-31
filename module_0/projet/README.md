# SenMarket — Pipeline de Data Engineering

Projet pédagogique de Data Engineering (fil rouge du parcours Big Data, étape 0) :
génération de données synthétiques pour une marketplace sénégalaise fictive,
nettoyage avec mise en quarantaine, export, analyse commerciale, graphiques et
tests de qualité, le tout piloté par un seul script paramétré par date.

> **Les données sont synthétiques.** Elles ne représentent ni des transactions
> réelles ni des statistiques officielles du marché sénégalais. Tous les montants
> sont en francs CFA (XOF).

## 1. Ce que fait le projet

```
generateur  ->  nettoyage  ->  export JSON Lines  ->  analyse  ->  graphiques
(data/raw)      (data/processed + data/rejected)      (CSV)        (PNG)
```

- **8 tables** : `clients`, `vendeurs`, `produits`, `commandes`, `lignes_commande`,
  `paiements`, `avis`, `navigation`.
- **Partitions par date** : chaque exécution travaille sur un dossier `date=AAAA-MM-JJ`.
- **Aucune perte silencieuse** : les lignes invalides sont conservées en quarantaine,
  avec le ou les motifs du rejet.
- **Tests** : tests unitaires des règles de nettoyage, puis tests de qualité sur les
  données réellement produites.

## 2. Arborescence

```
projet/
├── src/senmarket/
│   ├── chemins.py        chemins et partitions (partagés par tous les modules)
│   ├── generateur.py     génération des 8 tables brutes, avec défauts optionnels
│   ├── nettoyage.py      validation, quarantaine, écriture CSV/Parquet
│   ├── export.py         export JSON Lines
│   ├── analyse.py        indicateurs commerciaux
│   └── visualisation.py  graphiques PNG
├── scripts/run_pipeline.py   orchestration de toutes les étapes
├── tests/
│   ├── test_nettoyage.py         tests unitaires des règles de nettoyage
│   └── test_qualite_donnees.py   contrôles sur une partition produite
├── data/        (créé automatiquement, ignoré par Git)
├── reports/figures/   graphiques produits
├── logs/        (journaux d'exécution, ignorés par Git)
├── notebooks/
└── requirements.txt
```

## 3. Installation

Prérequis : Linux (ou WSL/macOS), Python 3 et pip. Testé avec Python 3.14.4.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## 4. Utilisation

Toutes les commandes se lancent depuis la racine du projet, environnement activé.

**Pipeline complet sur une nouvelle date** (génération + nettoyage + analyse + graphiques + tests) :

```bash
python scripts/run_pipeline.py --run-date 2026-10-29 --generer --rows 10000 \
  --defauts ville_manquante quantite_negative doublon_ligne date_future montant_texte outlier
```

**Rejouer une partition existante** (sans régénérer) :

```bash
python scripts/run_pipeline.py --run-date 2026-10-29
```

**Options de `run_pipeline.py`**

| Option | Rôle |
|---|---|
| `--run-date AAAA-MM-JJ` | Date de la partition (défaut : aujourd'hui) |
| `--generer` | Génère la partition brute avant le nettoyage |
| `--ecraser` | Avec `--generer` : autorise à régénérer une partition brute existante |
| `--rows N` | Nombre de lignes de commande à générer (défaut : 10 000) |
| `--defauts ...` | Défauts à injecter dans les données brutes (voir §7) |
| `--sans-tests` | Ne pas lancer pytest |

Si la partition demandée n'existe pas et que `--generer` n'est pas fourni, le pipeline
s'arrête avec un message qui indique la marche à suivre (code de retour 1) et ne crée aucun dossier.

**Chaque étape peut aussi se lancer seule :**

```bash
python -m src.senmarket.generateur --rows 10000 --run-date 2026-10-29
python -m src.senmarket.nettoyage --run-date 2026-10-29
python -m src.senmarket.export --run-date 2026-10-29
python -m src.senmarket.analyse --run-date 2026-10-29
python -m src.senmarket.visualisation --run-date 2026-10-29
```

## 5. Les 8 tables

Granularité : une ligne de `commandes` est une commande ; une ligne de
`lignes_commande` est un produit dans une commande. L'option `--rows` correspond
au nombre de lignes de commande.

| Table | Clé primaire | Colonnes |
|---|---|---|
| `clients` | `client_id` | `nom_client`, `email`, `telephone`, `ville`, `region`, `date_inscription` |
| `vendeurs` | `vendeur_id` | `nom_vendeur`, `ville`, `region` |
| `produits` | `produit_id` | `nom_produit`, `categorie`, `vendeur_id`, `prix_catalogue_xof`, `actif` |
| `commandes` | `commande_id` | `client_id`, `date_commande`, `statut` |
| `lignes_commande` | `ligne_commande_id` | `commande_id`, `produit_id`, `quantite`, `prix_unitaire_xof`, `montant_xof` |
| `paiements` | `paiement_id` | `commande_id`, `methode_paiement`, `statut_paiement`, `montant_xof`, `date_paiement` |
| `avis` | `avis_id` | `client_id`, `produit_id`, `commande_id`, `note`, `date_avis` |
| `navigation` | `evenement_id` | `session_id`, `client_id`, `produit_id`, `type_evenement`, `date_evenement` |

Relations (clés étrangères) : `produits → vendeurs`, `commandes → clients`,
`lignes_commande → commandes, produits`, `paiements → commandes`,
`avis → clients, produits, commandes`, `navigation → clients, produits`
(`client_id` et `produit_id` y sont facultatifs : événements anonymes possibles).

## 6. Organisation des données

```
data/
├── raw/date=AAAA-MM-JJ/        8 CSV bruts, tels que générés
├── processed/date=AAAA-MM-JJ/  données acceptées
│   ├── <table>.csv             lecture humaine
│   ├── <table>.parquet         types propres (entiers, vraies dates) pour la suite
│   ├── json/<table>.jsonl      un objet JSON par ligne (futur format d'ingestion)
│   └── analyses/               résultats de l'analyse (CSV)
└── rejected/date=AAAA-MM-JJ/   quarantaine
    ├── <table>_rejetes.csv     lignes rejetées + colonne raison_rejet
    ├── bilan_nettoyage.csv     brut / accepté / rejeté par table
    └── motifs_rejet.csv        nombre de lignes par motif de rejet
```

Les données brutes ne sont jamais modifiées par le nettoyage. Tout `data/` est
régénérable avec le pipeline et n'est donc pas versionné.

## 7. Nettoyage et motifs de rejet

Les tables sont nettoyées dans l'ordre de leurs dépendances : une clé étrangère
n'est valide que si la ligne parente a elle-même été **acceptée**.

| Motif de rejet | Signification |
|---|---|
| `champ_obligatoire_absent:<colonne>` | Valeur vide dans une colonne obligatoire |
| `cle_primaire_absente:<cle>` / `cle_primaire_dupliquee:<cle>` | Clé manquante, ou clé présente plusieurs fois |
| `date_invalide:<colonne>` / `date_future:<colonne>` | Date illisible, ou postérieure à `--run-date` |
| `quantite_invalide`, `prix_unitaire_invalide`, `prix_unitaire_outlier` | Quantité ou prix ≤ 0, prix > 1 000 000 XOF |
| `montant_non_numerique`, `montant_incoherent` | Montant illisible, ou différent de quantité × prix unitaire |
| `montant_paiement_invalide`, `note_hors_intervalle` | Paiement négatif, note hors de 1 à 5 |
| `prix_catalogue_non_positif_ou_invalide`, `prix_catalogue_outlier` | Prix catalogue ≤ 0 ou > 1 000 000 XOF |
| `cle_etrangere_invalide:<colonne>` | La ligne parente n'existe pas ou a été rejetée |

Une ligne peut cumuler plusieurs motifs (séparés par `;`).

**Défauts injectables** (option `--defauts`) : `ville_manquante`, `quantite_negative`,
`doublon_ligne`, `date_future`, `montant_texte`, `outlier`, `encodage_latin1`,
`colonne_manquante`. Sans option, aucune anomalie n'est injectée.

## 8. Indicateurs

Définitions retenues :

- **Chiffre d'affaires** = somme de `montant_xof` des lignes de commande acceptées,
  quel que soit le statut de la commande ou du paiement.
- **Panier moyen** = moyenne du chiffre d'affaires par `commande_id`.
- **Taux de conversion des sessions** = part des sessions de navigation contenant
  au moins un événement `debut_paiement`.
- **Villes** : la valeur « Inconnue » n'est pas comptée comme une ville.

Fichiers produits dans `data/processed/date=.../analyses/` : `indicateurs.csv`,
`analyse_par_ville.csv`, `analyse_par_produit.csv`, `ca_mensuel.csv`.
Graphiques dans `reports/figures/` : `chiffre_affaires_par_ville.png`,
`chiffre_affaires_par_produit.png`, `chiffre_affaires_mensuel.png`.

## 9. Tests

```bash
python -m pytest tests/test_nettoyage.py -q          # règles de nettoyage
SENMARKET_RUN_DATE=2026-10-29 python -m pytest tests/test_qualite_donnees.py -q
```

Les tests de qualité contrôlent la partition indiquée par `SENMARKET_RUN_DATE`
(sinon la plus récente partition nettoyée) : schémas, unicité des clés primaires,
cohérence quantité × prix, clés étrangères, absence de dates futures, motif présent
sur chaque rejet, bilan cohérent avec les fichiers. Ils sont ignorés (et non en échec)
s'il n'existe aucune partition.

## 10. Résultat de référence

Partition `2026-10-29`, 10 000 lignes de commande, six défauts injectés (commande ci-dessus). Ces chiffres sont un repère, pas des constantes.

| Table           | Lignes brutes | Acceptées | Rejetées |
|-----------------|--------------:|----------:|---------:|
| clients         |         3 333 |     3 333 |        0 |
| vendeurs        |            20 |        20 |        0 |
| produits        |            40 |        40 |        0 |
| commandes       |         4 085 |     4 084 |        1 |
| lignes_commande |        10 001 |     9 995 |        6 |
| paiements       |         4 003 |     4 002 |        1 |
| avis            |         1 000 |       999 |        1 |
| navigation      |        20 000 |    20 000 |        0 |

Il y a moins de paiements que de commandes : environ 2 % des commandes n'ont volontairement aucun paiement. Ce n'est pas un défaut.

Indicateurs : chiffre d'affaires total 163 011 763 XOF, panier moyen 39 914,73 XOF, 30 163 unités vendues, 20 villes, 40 produits, taux de conversion des sessions 14,64 %. Contrôle : 68 tests réussis.

## 11. Reproductibilité

Pour une même date et les mêmes paramètres, la génération produit les mêmes fichiers
(graine fixée pour NumPy et pour Faker). Pour le vérifier :

```bash
python -m src.senmarket.generateur --rows 10000 --run-date 2026-10-29
(cd data/raw/date=2026-10-29 && sha256sum *.csv) > /tmp/h1.txt
python -m src.senmarket.generateur --rows 10000 --run-date 2026-10-29
(cd data/raw/date=2026-10-29 && sha256sum *.csv) > /tmp/h2.txt
diff /tmp/h1.txt /tmp/h2.txt && echo "identique"
```

Les dates générées dépendent de `--run-date` : deux dates différentes donnent donc
des fichiers différents.

## 12. Décisions de conception

- **Une ligne de commande = un produit dans une commande** (table `lignes_commande`),
  pour pouvoir calculer un vrai panier par `commande_id`.
- **Clés primaires dupliquées : toutes les occurrences sont rejetées**, y compris
  l'originale, car aucune règle ne permet de choisir laquelle garder.
- **Ville ou région manquante : le client est conservé** avec la valeur « Inconnue »,
  car supprimer un client fausserait ses commandes en aval.
- **Tout est calculé en mémoire avant d'écrire**, et les entrées sont vérifiées avant de
  créer le moindre dossier : un échec ne laisse pas de sorties à moitié écrites.
- **CSV + Parquet + JSON Lines** : le CSV pour lire à l'œil, le Parquet pour garder les
  types (entiers, dates), le JSON Lines pour l'ingestion à venir.

## 13. Limites connues

- Les défauts injectés ne touchent que très peu de lignes : le jeu est presque propre
  et les règles de nettoyage sont peu sollicitées.
- `encodage_latin1` et `colonne_manquante` existent dans le générateur mais n'ont pas
  été testés de bout en bout.
- Le pipeline tourne sur une seule machine, sur des fichiers (pas de base de données).
- Pas de cohortes de clients ni de rétention dans l'analyse pour l'instant.
- Le code importe encore `src.senmarket` (qui ne marche que depuis la racine du projet). `pip install -e .` permet aussi `import senmarket` ; les deux écritures coexistent, à unifier plus tard.
- Testé uniquement avec Python 3.14.4 : à revalider (3.12 recommandé) avant Airflow,
  dbt et PySpark.

## 14. Suite du parcours

Prochaines étapes du fil rouge : charger ces tables dans PostgreSQL, MongoDB et Redis
(étape 1), puis traiter de plus gros volumes avec Spark (étape 2).

## Documentation du projet (dossier `docs/`)

Le README dit comment utiliser le projet. Le détail est réparti dans `docs/`, un fichier par question, pour ne jamais écrire la même chose à deux endroits :

| Fichier | Il répond à la question | Il contient |
|---|---|---|
| [`CONTRAT_DONNEES.md`](docs/CONTRAT_DONNEES.md) | Que contient chaque table ? | schéma des relations, colonnes et types, règles métier, trois définitions du chiffre d'affaires, écarts voulus et limites connues, organisation des données en partitions |
| [`DECISIONS.md`](docs/DECISIONS.md) | Pourquoi ce choix plutôt qu'un autre ? | une ligne par décision : ce qui est retenu, l'alternative rejetée, la raison |
| [`MESURES.md`](docs/MESURES.md) | Quelles preuves chiffrées, sur ma machine ? | machine, volume, temps de lecture et taille de chaque format ; généré par `python scripts/mesurer_formats.py`, ne pas modifier à la main |

Les données sont rangées par **partitions** (un dossier `date=AAAA-MM-JJ` par exécution, dans `data/raw`, `data/processed` et `data/rejected`) : voir la section 10 de `docs/CONTRAT_DONNEES.md`.
