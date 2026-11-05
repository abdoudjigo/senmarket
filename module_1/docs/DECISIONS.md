# Fiche de décision — Module 1 : où vit chaque donnée de SenMarket ?

Pour chaque donnée, quatre questions : **quelle forme ? quel accès ? quelle cohérence exigée ? que se passe-t-il si la base tombe ?**

## 1. Où met-on quoi

| Donnée | Base | Pourquoi | Alternative rejetée | Si la base tombe |
|---|---|---|---|---|
| Clients, vendeurs | PostgreSQL | Tableau régulier, liens avec les commandes | MongoDB : pas de clés étrangères | On ne peut plus commander |
| Commandes, lignes, paiements | PostgreSQL | De l'argent : tout ou rien (transaction), pas d'orphelin (clé étrangère) | Fichiers : pas de transaction | Le paiement s'arrête (voulu) |
| **Stock** | PostgreSQL | Une erreur = deux clients promis pour un seul article | Redis : un redémarrage efface tout | Plus de vente (voulu : mieux vaut refuser que mentir) |
| Fiche produit | MongoDB | Chaque catégorie a ses caractéristiques | Table à 40 colonnes presque vides | Fiche minimale depuis PostgreSQL ; le prix reste en PostgreSQL |
| Avis | MongoDB | Beaucoup, croissants, lus en groupe | Dans la fiche produit : elle grossirait sans fin | Avis indisponibles, les commandes continuent |
| Panier, session | Redis | Réponse très rapide, expire seul (TTL) | PostgreSQL : un aller-retour à chaque clic | Panier perdu, le client le refait |
| Cache « top produits » | Redis | Évite de recalculer à chaque page | Recalculer à chaque affichage | Pages plus lentes, rien n'est perdu |

**Règle du lead** : une base de plus = une panne de plus à gérer. On n'en ajoute une que si PostgreSQL ne ferait pas assez bien.

## 2. Mes trois preuves (à remplir avec les sorties de MES scripts)

| Preuve | Commande | Mon résultat |
|---|---|---|
| Double vente | `python scripts/2_double_vente.py` | Naïve : ___ doubles ventes sur 200. Sûre : ___ |
| Plantage | idem | Naïve : ___ commandes sans paiement sur 50. Sûre : ___ |
| Index | `python scripts/3_index.py` | `Seq Scan` ___ ms → `Index Scan` ___ ms (x___) |
| Cache Redis | `python scripts/4_mongo_redis.py` | PostgreSQL ___ ms → Redis ___ ms |

## 3. Coupure réseau (Dakar ↔ un second serveur)

| Donnée | Je choisis | Pourquoi |
|---|---|---|
| Stock | **Cohérence** : on refuse la vente | Une double vente coûte de l'argent |
| Panier | **Disponibilité** : on accepte | Un panier se rattrape |
| Avis | **Disponibilité** | Un avis en retard ne fait de mal à personne |

## 4. Pourquoi pas tout dans PostgreSQL ? (l'avocat du diable)

PostgreSQL sait aussi stocker du JSON et faire du cache. Je garde MongoDB et Redis pour deux raisons que je peux nommer :
1. la forme variable des fiches produit (ex. : un téléphone a `specs.ram_go`, un sac de riz a `poids_kg`) ;
2. la vitesse du panier et du cache (voir ma mesure Redis ci-dessus).
Si mes mesures montrent que ce n'est pas assez différent, je simplifie.

## 5. Ma réponse initiale « où vit le stock ? »

Mon avis au départ : ______. Ce que j'ai gardé / changé après l'expérience de double vente : ______.
