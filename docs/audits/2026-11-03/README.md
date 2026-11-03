# Évaluation de l’API LangExtract déployée — 3 novembre 2026

Cible : https://langextract.ailab.infocepo.com/docs

## Verdict

Le parcours API fonctionne sur le petit PDF synthétique testé : authentification,
validation, extraction réelle, JSONL et visualisation HTML. La documentation
Swagger est utilisable pour un essai manuel, mais son contrat OpenAPI demeure
incomplet pour intégrer l’API proprement dans d’autres outils.

**Priorité : rediriger HTTP vers HTTPS au reverse proxy.** Swagger reste accessible
en HTTP et pourrait y être utilisé pour saisir un token. Ce test n’a transmis
aucun identifiant en HTTP. Aucun vol de token ni contournement d’authentification
n’a été observé dans ce périmètre.

## Périmètre et méthode

Tests HTTP directs, avec vérification TLS active, sans suivi automatique des
redirections. Le token communiqué par le propriétaire a été utilisé littéralement,
y compris son caractère `$`, exclusivement dans l’en-tête Authorization des appels
HTTPS. Sa valeur, son empreinte et les en-têtes d’authentification ne figurent
pas dans ces fichiers. Aucun document réel n’a été envoyé.

Une seule extraction a été demandée au modèle : PDF minimal d’une page contenant
`FACTURE DEMO-2026 - ACME SAS - Montant: 42 EUR.`, une passe, un worker. Les autres
contrôles sont des lectures ou des requêtes invalides rejetées avant inférence.
Aucun changement n’a été appliqué au service déployé.

Rapport basé sur les observations externes et le schéma OpenAPI téléchargé.
L’API annonce la version `0.2.0` ; elle ne fournit pas de SHA de déploiement.
La branche de rapport part de `main` au commit
`03b3ed05ae783550c7ee88ac427757849759d319` (fusion de la PR #8), sans prétendre
que le service exécutait nécessairement ce SHA exact.

## Résultats observés

| Contrôle | Résultat | Lecture |
| --- | --- | --- |
| `GET /docs` en HTTPS | 200, SwaggerUIBundle présent | Document HTML accessible ; pas de contrôle visuel navigateur |
| `GET /openapi.json` | 200, document JSON | Trois chemins : healthz, config, extractions |
| `GET /healthz` | 200, `status=ok` | Application disponible ; ne prouve pas à lui seul la santé du modèle |
| Config sans token | 401 + `WWW-Authenticate: Bearer` | Accès refusé |
| Config avec token synthétique invalide | 401 | Accès refusé |
| Config avec le token fourni | 200 | Le caractère `$` est préservé et l’authentification fonctionne |
| Upload sans token | 401 | Le traitement demandé est refusé |
| Fichier non PDF avec token valide | 422 | Validation du fichier opérationnelle |
| `max_workers=25` avec PDF valide | 422 | Borne de paramètres appliquée |
| Extraction du PDF synthétique | 200 en 1,56 s | 3 entités : invoice, org, amount ; aucun avertissement |
| Exports de cette extraction | JSONL parsable et HTML non vide | Présence/structure vérifiées, sans ouvrir le HTML dans un navigateur |
| `GET /docs` en HTTP, sans identifiant | 200, SwaggerUIBundle présent, pas de Location | Absence de redirection HTTPS confirmée |
| Préflight CORS depuis une origine synthétique étrangère | 405, aucun Allow-Origin | Pas de CORS ouvert constaté ; refus normal pour cette architecture même origine |

La config expose une limite annoncée de 20 Mio et les cinq options attendues.
La limite d’upload n’a pas été éprouvée avec un fichier de cette taille.
Les appels courts ont pris environ 0,16–0,17 s ; le premier chargement de `/docs`
a pris 8,28 s. Ce sont des mesures ponctuelles depuis l’environnement de test,
pas un benchmark ni une mesure du temps de rendu dans le navigateur.
Le résultat de trois entités est cohérent avec le document synthétique ; cette
vérification n’évalue pas exhaustivement les attributs, offsets ou le rappel.

## Constats et actions recommandées

### 1. Priorité haute — HTTP sert Swagger sans redirection

Preuve : le contrôle HTTP a renvoyé le HTML Swagger avec le statut 200, sans
redirection. L’en-tête `Strict-Transport-Security` était absent des réponses HTTPS
consignées. Le problème est le transport potentiel du secret si un utilisateur
ouvre cette version HTTP puis s’authentifie ; ce chemin n’a pas été testé avec
une vraie clé.

Action : redirection permanente HTTP vers HTTPS au reverse proxy, puis HSTS
sur HTTPS une fois la configuration validée. Ne pas étendre HSTS à tous les
sous-domaines sans vérifier leurs capacités TLS. Refaire les contrôles après
configuration ; cette branche ne modifie pas le proxy.

### 2. Priorité moyenne — OpenAPI ne décrit que le succès

Preuve : les trois opérations n’annoncent que 200. Or les tests produisent 401
et 422 ; les autres erreurs prévues par l’application (413, 415, 500, 502, 503,
504) ne sont pas documentées dans ce schéma. Les en-têtes `WWW-Authenticate` et
`Retry-After` ne sont pas décrits non plus.

Action : déclarer des modèles de réponse d’erreur et les statuts réellement
possibles par opération, avec exemples fixes sans informations sensibles.
Cela permettra aux clients générés de gérer correctement les rejets et reprises.

### 3. Priorité moyenne — Paramètres peu découvrables dans Swagger

`options` est une chaîne JSON multipart sans exemple ni schéma détaillé de ses
champs. La réponse de config et `document` sont peu typées. Swagger ne permet
pas de découvrir les bornes, valeurs par défaut ou la structure des entités.
Le champ `file` et le mécanisme Bearer sont néanmoins correctement déclarés.

Action : documenter un exemple multipart complet, les options (types/bornes/
valeurs par défaut), la réponse de config et les entités/attributs/offsets.
Préciser que les exports et `document.text` contiennent le texte du PDF ;
`include_text` ne contrôle que le champ supplémentaire `text` de la réponse.
Ce dernier point provient du contrat/code du dépôt, pas d’un second test
avec `include_text=false` sur le service.

### 4. Priorité moyenne — Assets Swagger externes et version flottante

Le HTML charge CSS et JavaScript depuis
`https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/` et un favicon FastAPI externe.
La CSP de `/docs` observée se limite à `frame-ancestors 'none'`, contrairement
aux routes API qui possèdent une politique plus restrictive.

Action : héberger les assets Swagger localement avec une version verrouillée,
puis définir une CSP adaptée à cette page. Cela réduit la dépendance à un CDN
pour une interface manipulant des identifiants et facilite un usage sans Internet.
La présence de ces références ne démontre ni compromission ni fuite actuelle.

## Points satisfaisants

- Bearer correctement déclaré dans OpenAPI ; token valide accepté, absent/invalide refusé.
- Clé fournisseur non renvoyée par la config observée.
- Erreurs de validation françaises et structurées sous `detail`.
- `Cache-Control: no-store` et `X-Content-Type-Options: nosniff` sur les réponses testées.
- CSP restrictive sur les réponses API ; encadrement des frames sur la documentation.
- Extraction réelle réussie, avec exports JSONL et HTML, sur un document sans données personnelles.

## Limites

Pas d’audit RGAA, de rendu visuel Swagger/Vue, de test de charge, de brute force,
de saturation concurrente, de gros fichier, d’OCR, de PDF hostile ou de qualité
multidocument. Aucun accès aux logs serveur ni à la configuration du reverse
proxy. Les résultats ne constituent pas une certification de sécurité.
Aucune modification du code applicatif n’a été nécessaire pour produire ce
rapport ; les recommandations ci-dessus ne sont pas déployées.

## Pièces de preuve

- [http-results.json](http-results.json) : réponses et métadonnées sélectionnées,
  sans requêtes authentifiées ni contenu de documents réels.
- [openapi.json](openapi.json) : schéma public téléchargé, reformaté en JSON lisible.
- SHA-256 du fichier OpenAPI reformaté :
  `1482bbaf7208be297901745f8121a5484be790e6e40cff58233c8694e84647b9`.
