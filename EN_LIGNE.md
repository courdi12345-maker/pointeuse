# Pointage Max en ligne

Cette version met Pointage Max sur Internet : on l'ouvre depuis n'importe quel PC ou téléphone,
sans laisser un ordinateur allumé au bureau. L'adresse est en **HTTPS**, donc la caméra des
téléphones peut scanner les badges QR directement.

## Ce que ça coûte

Hébergeur conseillé : **Render** (render.com), serveur à Francfort, le plus proche du Maroc.

| Élément | Prix |
|---|---|
| Serveur « Starter » (toujours allumé) | 7 $ / mois |
| Disque de 1 Go pour les données | 0,25 $ / mois |
| **Total** | **environ 7,25 $ / mois (≈ 73 DH)** |

L'offre gratuite de Render ne convient pas : elle n'a pas de disque permanent (les données
seraient effacées à chaque redémarrage) et le site s'endort après 15 minutes.

## Mise en ligne (15 minutes, tout se fait à la souris)

1. **Fusionner le code sur GitHub** : ouvrez les pull requests en attente de
   `courdi12345-maker/pointeuse` et cliquez sur « Merge pull request » puis « Confirm merge ».
2. **Créer un compte Render** sur https://render.com avec « Sign in with GitHub ».
   Ajoutez une carte bancaire dans *Billing*.
3. Dans Render : **New +** → **Blueprint** → choisissez le dépôt **pointeuse** → **Connect**.
4. Render lit le fichier `render.yaml` et prépare tout. Il vous demande une seule valeur :
   **POINTAGE_ADMIN_PASSWORD** = le mot de passe du compte administrateur
   (au moins 10 caractères, pas uniquement des chiffres, pas un mot courant).
   Notez-le : c'est avec lui que vous vous connecterez.
5. Cliquez sur **Apply** (ou *Deploy Blueprint*). La première installation prend 3 à 5 minutes.
6. Quand le service est **Live**, cliquez sur son adresse en haut
   (du type `https://pointage-max-xxxx.onrender.com`) et connectez-vous avec
   l'identifiant **admin** et le mot de passe choisi à l'étape 4.

## Transférer les données du PC vers la version en ligne

0. Le PC doit avoir **la même version** du logiciel que le site (décompressez le dernier
   PointageMax.zip et lancez-le une fois), sinon la base ne correspond pas au code.
1. Sur le PC : **Paramètres → Sauvegardes → Sauvegarder maintenant**, puis **Télécharger**.
2. Sur la version en ligne : **Paramètres → Sauvegardes → Restaurer**, choisissez le fichier `.zip`,
   tapez `RESTAURER` et validez.
3. Reconnectez-vous **avec les comptes et mots de passe du PC** (la restauration remplace tout,
   comptes compris).

Faites ce transfert une seule fois, puis travaillez uniquement sur la version en ligne :
deux bases utilisées en même temps ne se mélangent pas.

## Mises à jour

Chaque fusion sur la branche `master` de GitHub met le site à jour automatiquement en
2 à 4 minutes. Les données sont sur le disque séparé et ne sont jamais touchées.

## Sécurité (déjà réglée)

- HTTPS obligatoire, cookies sécurisés, le navigateur retient l'obligation HTTPS (HSTS).
- Aucun mot de passe par défaut : le compte admin est créé avec le mot de passe que vous choisissez.
- Après 5 mots de passe faux depuis la même adresse, celle-ci est bloquée 15 minutes.
- Mots de passe d'au moins 10 caractères pour les nouveaux comptes.
- Photos, CIN et documents accessibles seulement aux utilisateurs connectés.
- Le code est public sur GitHub, mais **jamais les données** : elles restent sur le disque Render.

## Sauvegardes

- Une sauvegarde à chaque démarrage et une par jour, les 30 plus récentes sont gardées sur le disque.
- **Téléchargez une sauvegarde chaque semaine** (Paramètres → Sauvegardes → Télécharger) et
  gardez-la sur Google Drive ou une clé USB : si le compte Render est supprimé, son disque l'est aussi.

## Utiliser votre propre nom de domaine (facultatif)

Exemple : `pointage.svnet.ma`.
1. Dans Render : le service → **Settings → Custom Domains → Add**.
2. Chez votre fournisseur de domaine, créez l'enregistrement CNAME que Render affiche.
3. Dans Render : **Environment** → ajoutez `POINTAGE_HOSTS` = `pointage.svnet.ma` → **Save**.

## Autres hébergeurs

Le `Dockerfile` fonctionne partout (Railway, Fly.io, un VPS…). Il faut :
- monter un disque persistant sur `/data` ;
- définir `POINTAGE_SECRET_KEY` (longue chaîne aléatoire), `POINTAGE_ADMIN_PASSWORD`
  et `POINTAGE_HOSTS` (l'adresse du site) ;
- un seul serveur (la base SQLite est sur le disque).

## Variables reconnues

| Variable | Rôle |
|---|---|
| `POINTAGE_EN_LIGNE=1` | active la sécurité Internet (réglée dans le Dockerfile) |
| `POINTAGE_DATA_DIR=/data` | dossier des données sur le disque persistant |
| `POINTAGE_SECRET_KEY` | clé secrète de chiffrement des sessions |
| `POINTAGE_ADMIN_USER` / `POINTAGE_ADMIN_PASSWORD` | premier compte administrateur |
| `POINTAGE_HOSTS` | noms de domaine autorisés, séparés par des virgules |
| `POINTAGE_ESSAIS_MAX` / `POINTAGE_BLOCAGE_MINUTES` | blocage des connexions (5 / 15 par défaut) |
| `POINTAGE_WORKERS` | nombre de processus serveur (2 par défaut) |
