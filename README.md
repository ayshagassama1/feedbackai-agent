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
