FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

# --loop asyncio est obligatoire : uvloop (boucle par défaut d'uvicorn) casse les appels
# HTTP sortants d'httpx vers l'API GitHub (voir README, section Lancement local).
# $PORT est injecté par Cloud Run (8080 par défaut en local).
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080} --loop asyncio
