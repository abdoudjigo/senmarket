# Preuves : les contraintes du schéma refusent ce qu'elles doivent refuser

Fichier généré par `scripts/prouver_contraintes.py`, ne pas modifier à la main.
Les essais ont lieu dans un schéma jetable créé avec `sql/01_schema.sql`, puis supprimé : `principal` et `volume` ne sont jamais touchés.

Une règle qu'on n'a jamais vue refuser n'est pas une règle testée. Pour chaque type de contrainte, on tente donc une insertion interdite et on note la réponse exacte de PostgreSQL. Le **code SQLSTATE** est le numéro d'erreur standard : il dit de quel type de règle il s'agit, quelle que soit la langue du message.

## 1. Ce que PostgreSQL refuse

### 1. NOT NULL : Un client sans nom

```sql
INSERT INTO clients (client_id, nom_client, ville, region, date_inscription) VALUES ('CLI9', NULL, 'Dakar', 'Dakar', '2026-01-01')
```

- Verdict : **refusé comme prévu**
- Erreur attendue : `NotNullViolation`, obtenue : `NotNullViolation` (SQLSTATE 23502)
- Contrainte en cause : `colonne nom_client`
- Message de PostgreSQL : null value in column "nom_client" of relation "clients" violates not-null constraint

### 2. Clé primaire : Deux clients avec le même identifiant

```sql
INSERT INTO clients (client_id, nom_client, ville, region, date_inscription) VALUES ('CLI1', 'Doublon', 'Dakar', 'Dakar', '2026-01-01')
```

- Verdict : **refusé comme prévu**
- Erreur attendue : `UniqueViolation`, obtenue : `UniqueViolation` (SQLSTATE 23505)
- Contrainte en cause : `clients_pkey`
- Message de PostgreSQL : duplicate key value violates unique constraint "clients_pkey"

### 3. Clé étrangère : Une commande pour un client qui n'existe pas

```sql
INSERT INTO commandes (commande_id, client_id, date_commande, statut) VALUES ('CMD9', 'CLI_INCONNU', '2026-02-01', 'livrée')
```

- Verdict : **refusé comme prévu**
- Erreur attendue : `ForeignKeyViolation`, obtenue : `ForeignKeyViolation` (SQLSTATE 23503)
- Contrainte en cause : `fk_commandes_client`
- Message de PostgreSQL : insert or update on table "commandes" violates foreign key constraint "fk_commandes_client"

### 4. Clé étrangère : Un paiement pour une commande qui n'existe pas (le cauchemar de Fatou)

```sql
INSERT INTO paiements (paiement_id, commande_id, methode_paiement, statut_paiement, montant_xof, date_paiement, reference_transaction) VALUES ('PAI9', 'CMD_INCONNUE', 'Wave', 'réussi', 1000, '2026-02-02', 'WAV-100000002')
```

- Verdict : **refusé comme prévu**
- Erreur attendue : `ForeignKeyViolation`, obtenue : `ForeignKeyViolation` (SQLSTATE 23503)
- Contrainte en cause : `fk_paiements_commande`
- Message de PostgreSQL : insert or update on table "paiements" violates foreign key constraint "fk_paiements_commande"

### 5. CHECK : Une ligne de commande de quantité 0

```sql
INSERT INTO lignes_commande (ligne_commande_id, commande_id, produit_id, quantite, prix_unitaire_xof, montant_xof) VALUES ('LIG9', 'CMD1', 'PRO1', 0, 1000, 0)
```

- Verdict : **refusé comme prévu**
- Erreur attendue : `CheckViolation`, obtenue : `CheckViolation` (SQLSTATE 23514)
- Contrainte en cause : `ck_lignes_quantite_positive`
- Message de PostgreSQL : new row for relation "lignes_commande" violates check constraint "ck_lignes_quantite_positive"

### 6. CHECK : Un montant de ligne qui ne vaut pas quantité x prix

```sql
INSERT INTO lignes_commande (ligne_commande_id, commande_id, produit_id, quantite, prix_unitaire_xof, montant_xof) VALUES ('LIG9', 'CMD1', 'PRO1', 2, 1000, 1500)
```

- Verdict : **refusé comme prévu**
- Erreur attendue : `CheckViolation`, obtenue : `CheckViolation` (SQLSTATE 23514)
- Contrainte en cause : `ck_lignes_montant_coherent`
- Message de PostgreSQL : new row for relation "lignes_commande" violates check constraint "ck_lignes_montant_coherent"

### 7. CHECK : Un stock négatif

```sql
UPDATE produits SET stock = -1 WHERE produit_id = 'PRO1'
```

- Verdict : **refusé comme prévu**
- Erreur attendue : `CheckViolation`, obtenue : `CheckViolation` (SQLSTATE 23514)
- Contrainte en cause : `ck_produits_stock_positif`
- Message de PostgreSQL : new row for relation "produits" violates check constraint "ck_produits_stock_positif"

### 8. CHECK : Une note de 6

```sql
INSERT INTO avis (avis_id, client_id, produit_id, commande_id, note, date_avis, commentaire) VALUES ('AVI9', 'CLI1', 'PRO1', 'CMD1', 6, '2026-02-02', 'Test')
```

- Verdict : **refusé comme prévu**
- Erreur attendue : `CheckViolation`, obtenue : `CheckViolation` (SQLSTATE 23514)
- Contrainte en cause : `ck_avis_note_1_a_5`
- Message de PostgreSQL : new row for relation "avis" violates check constraint "ck_avis_note_1_a_5"

### 9. CHECK : Un statut de commande sans accent (livree au lieu de livrée)

```sql
INSERT INTO commandes (commande_id, client_id, date_commande, statut) VALUES ('CMD9', 'CLI1', '2026-02-01', 'livree')
```

- Verdict : **refusé comme prévu**
- Erreur attendue : `CheckViolation`, obtenue : `CheckViolation` (SQLSTATE 23514)
- Contrainte en cause : `ck_commandes_statut`
- Message de PostgreSQL : new row for relation "commandes" violates check constraint "ck_commandes_statut"

### 10. CHECK : Un paiement en espèces avec une référence de transaction

```sql
INSERT INTO paiements (paiement_id, commande_id, methode_paiement, statut_paiement, montant_xof, date_paiement, reference_transaction) VALUES ('PAI9', 'CMD1', 'Espèces', 'réussi', 1000, '2026-02-02', 'ESP-1')
```

- Verdict : **refusé comme prévu**
- Erreur attendue : `CheckViolation`, obtenue : `CheckViolation` (SQLSTATE 23514)
- Contrainte en cause : `ck_paiements_reference_selon_methode`
- Message de PostgreSQL : new row for relation "paiements" violates check constraint "ck_paiements_reference_selon_methode"

### 11. CHECK : Un paiement Wave sans référence de transaction

```sql
INSERT INTO paiements (paiement_id, commande_id, methode_paiement, statut_paiement, montant_xof, date_paiement, reference_transaction) VALUES ('PAI9', 'CMD1', 'Wave', 'réussi', 1000, '2026-02-02', NULL)
```

- Verdict : **refusé comme prévu**
- Erreur attendue : `CheckViolation`, obtenue : `CheckViolation` (SQLSTATE 23514)
- Contrainte en cause : `ck_paiements_reference_selon_methode`
- Message de PostgreSQL : new row for relation "paiements" violates check constraint "ck_paiements_reference_selon_methode"

### 12. CHECK : Une référence de transaction vide (texte vide, pas NULL)

```sql
INSERT INTO paiements (paiement_id, commande_id, methode_paiement, statut_paiement, montant_xof, date_paiement, reference_transaction) VALUES ('PAI9', 'CMD1', 'Wave', 'réussi', 1000, '2026-02-02', '')
```

- Verdict : **refusé comme prévu**
- Erreur attendue : `CheckViolation`, obtenue : `CheckViolation` (SQLSTATE 23514)
- Contrainte en cause : `ck_paiements_reference_non_vide`
- Message de PostgreSQL : new row for relation "paiements" violates check constraint "ck_paiements_reference_non_vide"

### 13. UNIQUE : Deux paiements avec la même référence de transaction

```sql
INSERT INTO paiements (paiement_id, commande_id, methode_paiement, statut_paiement, montant_xof, date_paiement, reference_transaction) VALUES ('PAI9', 'CMD1', 'Wave', 'réussi', 1000, '2026-02-02', 'WAV-100000001')
```

- Verdict : **refusé comme prévu**
- Erreur attendue : `UniqueViolation`, obtenue : `UniqueViolation` (SQLSTATE 23505)
- Contrainte en cause : `uq_paiements_reference`
- Message de PostgreSQL : duplicate key value violates unique constraint "uq_paiements_reference"

## 2. Ce que PostgreSQL accepte, et ce que font les ON DELETE

1. **Un client sans aucune commande est accepté**
   - Observé : CLI2 créé, nombre de ses commandes : 0
   - Verdict : conforme

2. **Une commande sans aucune ligne est acceptée : la base ne l'empêche pas, c'est la transaction du chapitre 2.4 qui garantit commande + lignes + paiement**
   - Observé : CMD3 créée, nombre de ses lignes : 0
   - Verdict : conforme

3. **Plusieurs paiements en espèces sans référence sont acceptés malgré UNIQUE : PostgreSQL ne considère pas deux NULL comme égaux**
   - Observé : 2 paiements avec une référence NULL
   - Verdict : conforme

4. **Supprimer un client qui a des commandes est refusé (RESTRICT)**
   - Observé : suppression refusée par fk_commandes_client, le client existe toujours (1)
   - Verdict : conforme

5. **Supprimer une commande qui a un paiement est refusé (RESTRICT sur le paiement), et ses lignes restent intactes malgré le CASCADE (tout ou rien)**
   - Observé : suppression refusée par fk_paiements_commande, lignes restantes : 1
   - Verdict : conforme

6. **Supprimer une commande sans paiement supprime aussi ses lignes (CASCADE)**
   - Observé : CMD2 supprimée, lignes restantes : 0
   - Verdict : conforme

7. **Supprimer un client met à NULL son client_id dans la navigation (SET NULL) : l'événement est conservé, devenu anonyme**
   - Observé : événement conservé : True, client_id vaut maintenant : None
   - Verdict : conforme

8. **Modifier une ligne met à jour modifie_le (déclencheur)**
   - Observé : modifie_le est postérieur à cree_le : True
   - Verdict : conforme
