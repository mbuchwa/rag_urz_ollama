<p align="center">
  <img src="frontend/imgs/urz/logo.png" alt="URZ logo" height="80" />
  <img src="frontend/imgs/urz/chatbot_logo.png" alt="Chatbot logo" height="80" />
</p>

# URZ RAG Platform

This repository contains the University of Heidelberg URZ chat experience. It now includes a
platform skeleton that combines the existing Tailwind React chat UI with an Ollama-backed RAG
API, container orchestration, and space for future ingestion and worker services.

## Repository Layout

```
├── app.py                      # Legacy Flask entry point (preserved)
├── backend/                    # FastAPI + Celery platform scaffold
│   ├── app/
│   │   ├── api/                # Route modules (auth, crawl, docs, chat, admin)
│   │   ├── core/               # Config, database, security, SSE, MinIO helpers
│   │   ├── ingest/             # Crawling + ingestion pipeline placeholders
│   │   ├── models/             # SQLAlchemy ORM models
│   │   ├── rag/                # Retrieval and Ollama client helpers
│   │   ├── workers/            # Celery configuration + tasks
│   │   └── main.py             # FastAPI application entry point
│   ├── migrations/             # Alembic environment + pgvector bootstrap migration
│   └── requirements.txt        # Backend dependencies
├── docker-compose.yml          # Local orchestration for all services
├── Dockerfile.api              # Backend image (FastAPI + Celery)
├── Dockerfile.frontend         # Frontend image (Vite dev server)
├── frontend/                   # React + Tailwind chat UI
├── index_store/                # Existing FAISS index data
├── requirements.txt            # Legacy Flask requirements
└── .env.example                # Environment variable template
```

## Local Development with Docker Compose

The platform runs entirely through Docker Compose. The first run requires populating an `.env`
file from the provided template and then starting the stack.

### 1. Configure Environment Variables

Copy the example environment file and adjust values if needed:

```bash
cp .env.example .env
```

The defaults target local containers: PostgreSQL with the pgvector extension, Redis, MinIO,
and expect an Ollama runtime to be available on the Docker host.

### 2. Build Images

```bash
docker compose build
```

### 3. Launch the Stack

```bash
docker compose up
```

The command starts the following services:

| Service    | Description                            | Port |
|------------|----------------------------------------|------|
| `frontend` | React + Tailwind chat UI               | 3000 |
| `api`      | FastAPI RAG backend                    | 8000 |
| `worker`   | Celery worker for async tasks          | n/a  |
| `db`       | PostgreSQL 16 with pgvector extension  | 5432 |
| `redis`    | Redis message broker / cache           | 6379 |
| `minio`    | S3-compatible object storage           | 9000 (API), 9001 (console) |

> **Note**
> Start `ollama serve` (or ensure another Ollama daemon is listening on port 11434) on the
> host machine before launching Docker Compose. The containers reach it through
> `http://host.docker.internal:11434`. When you run the API outside Docker, set
> `OLLAMA_HOST` and `OLLAMA_FALLBACK_HOST` to the addresses that can reach your Ollama runtime.

### 4. Smoke Test

Once the containers are healthy, verify the backend health endpoint:

```bash
curl http://localhost:8000/admin/health
# {"status":"ok"}
```

You can then visit the chat UI at [http://localhost:3000](http://localhost:3000).

### 5. Run the test suite

The backend exposes a focused pytest suite. After installing the requirements from
`backend/requirements.txt`, run:

```bash
cd backend
pytest
```

## Environment Configuration

The application reads configuration from environment variables (see `backend/app/core/config.py`).
The following values are the most important when running locally:

| Variable | Purpose | Example |
|----------|---------|---------|
| `OIDC_CLIENT_ID` / `OIDC_CLIENT_SECRET` | OAuth client credentials | `rag-local` / `dev-secret` |
| `OIDC_ISSUER` | Base URL for the OpenID provider | `https://keycloak.local/realms/rag` |
| `OIDC_REDIRECT_URI` | Backend callback URL | `http://localhost:8000/auth/callback` |
| `FRONTEND_URL` | Origin used for CORS + redirects | `http://localhost:3000` |
| `OLLAMA_HOST` / `OLLAMA_FALLBACK_HOST` | Primary + fallback base URLs for the Ollama API | `http://host.docker.internal:11434` / `http://127.0.0.1:11434` |
| `SESSION_SECRET` | Cookie signing key (keep unique per deployment) | `generate-with-openssl` |
| `SESSION_COOKIE_SECURE` | Set `false` for plain HTTP dev stacks | `false` |
| `UPLOAD_MAX_BYTES` | Maximum accepted upload size | `26214400` |
| `RATE_LIMIT_CHAT_STREAM` | Per-user chat stream rate | `30/minute` |
| `RATE_LIMIT_INGESTION` / `RATE_LIMIT_CRAWL` | Upload and crawl throttles | `12/minute`, `4/hour` |

## Configuring OIDC locally

1. Register a confidential client with your provider (Keycloak, Auth0, etc.) and enable the
   authorization code flow.
2. Set the redirect URI to `http://localhost:8000/auth/callback`.
3. Copy the client ID/secret and issuer URL into `.env` using the variables listed above.
4. Restart the stack: `docker compose up -d api frontend` so the backend reloads the new settings.
5. Visit `http://localhost:3000/login` and follow the OIDC flow; upon callback the backend will
   create a session and emit `rag_session` + `csrf_token` cookies.

## Data model overview

```
 Users ───< NamespaceMembers >─── Namespaces
                     │              │
                     │              ├── Documents ───< Chunks
                     │              ├── Jobs ───────< CrawlResults
                     └── Conversations ───< Messages
```

All tenant-specific resources reference the owning namespace so retrieval and ingestion stay isolated
per organisation.

## Troubleshooting

- **CORS / mixed content** – Ensure `FRONTEND_URL` matches the origin you use in the browser. When
  running everything locally, `http://localhost:3000` is correct; update the env var and restart the
  API container if you change the port or host.
- **Session or CSRF errors** – The backend signs cookies using `SESSION_SECRET`. If you flip between
  HTTP and HTTPS locally, set `SESSION_COOKIE_SECURE=false` and restart to allow the browser to send
  the cookie over plain HTTP. Include the `X-CSRF-Token` header on JSON `POST`/`DELETE` requests.
- **MinIO connectivity** – The default credentials (`minioadmin`/`minioadmin`) match the Docker
  Compose stack. If uploads fail, confirm the bucket exists:

  ```bash
  docker compose exec minio mc ls local/rag-data
  ```

  The backend auto-creates the bucket during the first upload.
- **Metrics** – Prometheus can scrape `http://localhost:8000/admin/metrics` for request/task metrics.
  `curl -H 'Accept: text/plain' http://localhost:8000/admin/metrics | head` to inspect locally.

## Next Steps

The backend scaffold contains placeholders for authentication, ingestion pipelines, Celery tasks,
and retrieval orchestration. Future PRs will flesh out these components, wire the FastAPI backend
into the existing frontend, and migrate the legacy Flask features to the new architecture.
