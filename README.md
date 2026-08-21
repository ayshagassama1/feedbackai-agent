# feedbackai-agent

Agent d'analyse de feedback produit pour équipes SaaS early-stage — ingestion, triage,
clustering, insights, et action sur un tracker externe. Construit pour le hackathon
*All Things Agentic* (Devpost / Google Cloud).

## Stack technique

| Couche | Technologie |
|---|---|
| Agent | Google ADK (`LlmAgent` + `Runner`) |
| Raisonnement, chat, embeddings | Gemini 3.5 Flash (API Gemini directe) |
| Triage par item (ingestion) | Gemma (Vertex AI, Model Garden), fallback Gemini |
| Backend | FastAPI |
| Données | MongoDB Atlas + Atlas Vector Search |
| Frontend | React / Vite |
| Déploiement | Cloud Run (backend + frontend) |

## Architecture — deux modèles

- **Gemma** (Vertex AI, Model Garden) : triage par item à l'ingestion — langue, catégorie,
  sentiment, résumé, en un seul appel. Petit modèle dédié pour un travail à haut volume, coût
  maîtrisé.
- **Gemini 3.5 Flash** (API Gemini directe) : raisonnement à faible volume — labellisation de
  cluster, recommandations, chat agent — et **fallback automatique** du triage si l'endpoint
  Gemma n'est pas déployé ou ne répond pas.

```
feedback texte/CSV/URL
       │
       ▼
  scrub PII (regex : emails, téléphones)
       │
       ▼
  triage : Gemma ──(indisponible)──▶ Gemini 3.5 Flash (fallback)
       │
       ▼
  embedding (Gemini) → MongoDB Atlas (+ Vector Search)
       │
       ▼
  clustering, insights, chat agent (ADK) → Gemini 3.5 Flash
```

## Déploiement de l'endpoint Gemma (à faire manuellement)

Claude Code ne touche pas à l'infrastructure GCP. Séquence exacte pour déployer l'endpoint
Gemma, une fois le crédit hackathon confirmé :

1. **Sélectionner le modèle en Model Garden**
   Console GCP → Vertex AI → Model Garden → rechercher « Gemma ». Choisir une variante
   instruction-tuned : `gemma-3-1b-it` (coût minimal) ou `gemma-3-4b-it` (plus robuste FR/EN) —
   à trancher selon la qualité observée sur le triage.

2. **Déployer sur un endpoint dédié**
   Depuis la fiche du modèle : « Deploy » → conteneur vLLM (image fournie par Model Garden).
   Machine `g2-standard-12` + 1 GPU `NVIDIA_L4`. Nommer l'endpoint clairement (ex.
   `feedbackai-gemma-triage`).

3. **Récupérer l'ENDPOINT_ID**
   ```bash
   gcloud ai endpoints list --region=<GEMMA_LOCATION> --format="table(name,displayName)"
   ```
   L'`ENDPOINT_ID` est le dernier segment du `name` (`projects/.../endpoints/<ID>`).

4. **Renseigner les variables d'environnement** (`.env`, jamais commitées) :
   ```
   GCP_PROJECT_ID=<ton projet>
   GEMMA_ENDPOINT_ID=<l'ID récupéré>
   GEMMA_LOCATION=<région du déploiement>
   ```

5. **Vérifier le format réel des instances/réponses** de ton déploiement vLLM contre
   `agent/gemma_client.py`. Le format `prompt`/`max_tokens` en entrée et
   `predictions[0].text` en sortie correspond aux déploiements vLLM standards sur Vertex, mais
   peut varier selon l'image exacte utilisée par Model Garden au moment du déploiement —
   ajuster le client si besoin, une fois l'endpoint réel disponible pour tester.

6. **Undeploy après la démo** (facturation à la durée, pas à la requête) :
   ```bash
   gcloud ai endpoints undeploy-model <ENDPOINT_ID> \
     --deployed-model-id=<DEPLOYED_MODEL_ID> --region=<GEMMA_LOCATION>
   ```
   Le fallback Gemini garantit que couper l'endpoint ne casse rien : l'app continue de
   fonctionner sans lui.

## Déclenchement planifié (Cloud Scheduler + Pub/Sub)

**Préalable : le backend doit déjà tourner sur Cloud Run** (étape 5.3) — la subscription push a
besoin d'une URL réelle. Si ce n'est pas encore fait, garde cette section pour plus tard.

Architecture : `Cloud Scheduler` publie sur un topic `Pub/Sub`, qui pousse (avec un jeton OIDC)
vers `POST /api/agent/run-cycle` sur Cloud Run. L'endpoint vérifie ce jeton lui-même (voir
`agent/main.py`) — jamais de service public non authentifié.

1. **Variables** (à adapter) :
   ```bash
   PROJECT_ID=feedbackai-497622
   REGION=us-central1
   SERVICE_NAME=feedback-agent
   ```

2. **Compte de service dédié à Pub/Sub** :
   ```bash
   gcloud iam service-accounts create pubsub-run-cycle-invoker \
     --display-name="Pub/Sub push invoker pour run-cycle" \
     --project=$PROJECT_ID
   ```

3. **Autoriser ce compte à appeler le service Cloud Run** :
   ```bash
   gcloud run services add-iam-policy-binding $SERVICE_NAME \
     --region=$REGION \
     --member="serviceAccount:pubsub-run-cycle-invoker@${PROJECT_ID}.iam.gserviceaccount.com" \
     --role="roles/run.invoker"
   ```

4. **Autoriser l'agent de service Pub/Sub à émettre des jetons au nom de ce compte** :
   ```bash
   PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
   gcloud iam service-accounts add-iam-policy-binding \
     pubsub-run-cycle-invoker@${PROJECT_ID}.iam.gserviceaccount.com \
     --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-pubsub.iam.gserviceaccount.com" \
     --role="roles/iam.serviceAccountTokenCreator"
   ```

5. **Créer le topic** :
   ```bash
   gcloud pubsub topics create feedback-cycle --project=$PROJECT_ID
   ```

6. **Créer la subscription push, avec l'audience OIDC** :
   ```bash
   SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --format='value(status.url)')

   gcloud pubsub subscriptions create feedback-cycle-push \
     --topic=feedback-cycle \
     --push-endpoint="${SERVICE_URL}/api/agent/run-cycle" \
     --push-auth-service-account="pubsub-run-cycle-invoker@${PROJECT_ID}.iam.gserviceaccount.com" \
     --push-auth-token-audience="${SERVICE_URL}/api/agent/run-cycle" \
     --project=$PROJECT_ID
   ```

7. **Renseigner les variables d'environnement du service Cloud Run** (en plus des existantes) :
   ```
   PUBSUB_PUSH_SERVICE_ACCOUNT=pubsub-run-cycle-invoker@<PROJECT_ID>.iam.gserviceaccount.com
   RUN_CYCLE_AUDIENCE=<SERVICE_URL>/api/agent/run-cycle
   ```

8. **Créer le job Cloud Scheduler** (exemple : toutes les 6h) :
   ```bash
   gcloud scheduler jobs create pubsub feedback-cycle-scheduler \
     --schedule="0 */6 * * *" \
     --topic=feedback-cycle \
     --message-body='{"project_id":"demo"}' \
     --location=$REGION \
     --time-zone="Europe/Paris" \
     --project=$PROJECT_ID
   ```
   `message-body` devient le contenu du message Pub/Sub (encodé en base64 automatiquement) —
   c'est exactement ce que `agent/main.py` attend de décoder pour retrouver `project_id`.

**Rôles IAM nécessaires (résumé)**

| Identité | Rôle | Sur quelle ressource | Pourquoi |
|---|---|---|---|
| SA `pubsub-run-cycle-invoker` | `roles/run.invoker` | Le service Cloud Run | Autorise Pub/Sub (via ce SA) à appeler l'endpoint |
| Agent de service Pub/Sub (`service-<PROJECT_NUMBER>@gcp-sa-pubsub.iam.gserviceaccount.com`) | `roles/iam.serviceAccountTokenCreator` | Le SA `pubsub-run-cycle-invoker` | Autorise Pub/Sub à générer des jetons OIDC au nom de ce SA |
| Agent de service Cloud Scheduler | `roles/pubsub.publisher` | Le topic `feedback-cycle` | Généralement accordé automatiquement par `gcloud scheduler jobs create pubsub` — à vérifier après coup (`gcloud pubsub topics get-iam-policy feedback-cycle`) |

**Validation** : attendre la prochaine exécution planifiée (ou forcer avec
`gcloud scheduler jobs run feedback-cycle-scheduler --location=$REGION`), puis vérifier dans les
logs Cloud Run (`gcloud run services logs read $SERVICE_NAME --region=$REGION`) qu'un cycle
s'est exécuté. Garder une capture pour la preuve GCP / la vidéo.

## Lancement local

```bash
cd agent
uvicorn main:app --host 0.0.0.0 --port 8000 --loop asyncio
```

**`--loop asyncio` est obligatoire**, pas juste une option : `uvloop` (la boucle par défaut
d'uvicorn) casse silencieusement les appels HTTP sortants d'`httpx` vers l'API GitHub
(`ConnectTimeout`), utilisée par `create_ticket`. Mesuré et reproduit hors serveur pendant
l'étape 3.1 — sans ce flag, `POST /api/agent/run-cycle` échoue en 500 dès qu'un ticket doit
être créé.

## Variables d'environnement

Voir `.env.example` pour la liste complète. Résumé :

| Variable | Rôle | Obligatoire ? |
|---|---|---|
| `GEMINI_API_KEY` | Chat, raisonnement, embeddings, fallback triage | Oui |
| `MONGODB_URI` / `MONGODB_DB` | Base de données | Oui |
| `GCP_PROJECT_ID` | Résolution de l'endpoint Gemma | Non — sans elle, fallback Gemini systématique |
| `GEMMA_ENDPOINT_ID` / `GEMMA_LOCATION` | Endpoint Gemma déployé | Non — idem |
| `GITHUB_TOKEN` / `GITHUB_REPO_MAP` | Création de tickets GitHub | Oui, pour `create_ticket` |
| `RUN_CYCLE_SECRET` | Auth directe de `run-cycle` (tests/débogage) | Non |
| `PUBSUB_PUSH_SERVICE_ACCOUNT` / `RUN_CYCLE_AUDIENCE` | Auth OIDC de `run-cycle` par Pub/Sub | Non — sans elles, seul `RUN_CYCLE_SECRET` fonctionne |
