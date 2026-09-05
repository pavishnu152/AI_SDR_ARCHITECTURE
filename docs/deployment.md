# Deployment Guide

## Why Render, not Railway

Both were considered as deployment options for the project.

For this portfolio project, **Render** is the selected deployment platform because it supports the required Docker-based FastAPI backend, static React frontend, and PostgreSQL deployment workflow in a single platform.

The deployment architecture is:

```text
GitHub
   │
   ▼
Render Blueprint
   │
   ├── ai-sdr-api
   │      └── FastAPI + Docker
   │
   ├── ai-sdr-dashboard
   │      └── React + Vite static site
   │
   └── ai-sdr-db
          └── PostgreSQL
```

The application uses **Google Gemini** for its LLM functionality.

The current model is:

```text
gemini-2.5-flash
```

Gemini is accessed through its OpenAI-compatible API endpoint, allowing the existing agent implementation to use the OpenAI Python SDK while keeping the provider configuration isolated.

Provider-specific pricing is intentionally not hard-coded into this deployment guide because current Gemini pricing should be verified separately before making cost claims.

## What's already done

`render.yaml` at the repository root is a Render Blueprint that defines the application's deployment resources:

1. `ai-sdr-api` — the FastAPI backend, built from `docker/Dockerfile`.

2. `ai-sdr-dashboard` — the React frontend, built as a static site from `frontend/` and served from `frontend/dist`.

3. `ai-sdr-db` — the PostgreSQL database used by the backend.

The backend Docker image uses the existing application Dockerfile and startup process.

The database schema is managed through Alembic migrations.

The deployment configuration uses Render environment variables for secrets and environment-specific configuration.

The Gemini API key is supplied through:

```text
GEMINI_API_KEY
```

The key is not committed to the repository.

## What you need to do

This part requires your own Render account and GitHub connection.

### 1. Push the repository to GitHub

Make sure the latest project changes are committed and pushed before deploying.

Verify the repository contains:

```text
render.yaml
docker/
frontend/
src/
alembic/
pyproject.toml
```

Do not commit:

```text
.env
```

or any file containing real credentials.

### 2. Create a Render account

Open:

https://dashboard.render.com/register

Sign in or create your Render account.

### 3. Create a Blueprint

From the Render dashboard:

```text
New
  ↓
Blueprint
  ↓
Connect GitHub repository
```

Select the repository containing the AI SDR project.

Render should detect:

```text
render.yaml
```

automatically.

The Blueprint should define the backend, frontend, and database resources.

### 4. Configure the Gemini API key

Render will prompt for environment variables marked for manual configuration.

Set:

```text
GEMINI_API_KEY
```

Use your real Google Gemini API key.

Do not paste the key into:

* GitHub
* `render.yaml`
* source code
* README files
* frontend source
* screenshots
* public documentation

The key should remain a server-side environment variable.

### 5. Apply the Blueprint

Click:

```text
Apply
```

Render will provision the configured services.

The backend deployment includes:

```text
Docker build
     ↓
Container startup
     ↓
Alembic migration
     ↓
FastAPI application
```

The frontend deployment includes:

```text
npm install
     ↓
npm run build
     ↓
frontend/dist
     ↓
Static hosting
```

The initial deployment can take several minutes.

## Environment variables

The backend requires the following production configuration.

### Gemini

```text
GEMINI_API_KEY
```

This is the credential used to access Google Gemini.

The current model is configured in the application configuration:

```text
gemini-2.5-flash
```

### Database

```text
DATABASE_URL
```

Render provides the PostgreSQL connection information through the Blueprint configuration.

### Authentication

```text
JWT_SECRET_KEY
```

This must be a strong production secret.

Never reuse a development secret in production.

### CORS

```text
CORS_ALLOWED_ORIGINS
```

This must contain the actual deployed frontend URL.

Example:

```text
https://your-dashboard.onrender.com
```

### Frontend API URL

The React application uses:

```text
VITE_API_BASE_URL
```

This must point to the deployed FastAPI backend.

Example:

```text
https://your-api.onrender.com
```

## The two-pass deployment step

The API needs to know the dashboard URL for CORS.

The dashboard needs to know the API URL for API requests.

However, Render assigns the final service URLs when the services are created.

The actual URLs may therefore differ from the names initially expected in the Blueprint.

For example:

```text
https://ai-sdr-api.onrender.com
https://ai-sdr-dashboard.onrender.com
```

or Render may assign a suffixed service name if the preferred name is already unavailable.

### After the first deployment

Open the Render dashboard and note the actual URLs for:

```text
ai-sdr-api
ai-sdr-dashboard
```

### Update the backend

Open:

```text
ai-sdr-api
  ↓
Environment
```

Set:

```text
CORS_ALLOWED_ORIGINS
```

to the actual dashboard URL.

Example:

```text
https://ai-sdr-dashboard.onrender.com
```

Save the environment change and redeploy if Render requires it.

### Update the frontend

Open:

```text
ai-sdr-dashboard
  ↓
Environment
```

Set:

```text
VITE_API_BASE_URL
```

to the actual backend URL.

Example:

```text
https://ai-sdr-api.onrender.com
```

Then trigger a **manual redeploy**.

This step is important because Vite environment variables are injected during the frontend build.

Changing:

```text
VITE_API_BASE_URL
```

does not modify an already-built JavaScript bundle.

The frontend must be rebuilt.

## Production verification

After both services have deployed, first verify the backend health endpoint.

```bash
curl https://<your-api>.onrender.com/health
```

Expected response:

```json
{
  "status": "ok",
  "env": "production"
}
```

If the health endpoint works, open the deployed dashboard.

Example:

```text
https://<your-dashboard>.onrender.com
```

Then verify the complete application flow.

## End-to-end production smoke test

Run the following sequence.

### 1. Open dashboard

Confirm the React application loads.

### 2. Register

Create a new test account.

Verify registration succeeds.

### 3. Login

Log in with the newly created account.

Verify the JWT-authenticated session works.

### 4. Create a lead

Enter a real company.

### 5. Run research

Click:

```text
Research
```

The UI should show:

```text
Running pipeline...
```

### 6. Verify research

Confirm that the Research Agent returns company information and source URLs.

### 7. Verify scoring

Confirm that the lead receives:

```text
Score
Confidence
Reasoning
```

### 8. Verify reject-early behavior

For a low-fit company, verify that the pipeline can stop after scoring rather than continuing to drafting.

### 9. Verify outreach

For a qualified company, confirm that the Drafting Agent generates personalized outreach.

### 10. Verify guardrail

Confirm that the Guardrail Agent evaluates the generated draft.

### 11. Verify agent trace

Open the lead detail page and verify that execution information is visible.

This confirms the major production path:

```text
Frontend
   ↓
FastAPI
   ↓
JWT
   ↓
LangGraph
   ↓
Research
   ↓
Scoring
   ↓
ICP Gate
   ↓
Drafting
   ↓
Guardrail
   ↓
PostgreSQL
   ↓
Gemini
```

## Gemini-specific deployment verification

The most important provider-specific check is that the production backend can actually communicate with Google Gemini.

The backend should have:

```text
GEMINI_API_KEY
```

configured in Render.

The application configuration should resolve to:

```text
Google Gemini
gemini-2.5-flash
```

and the Gemini OpenAI-compatible endpoint:

```text
https://generativelanguage.googleapis.com/v1beta/openai/
```

Do not expose the Gemini key in frontend environment variables.

In particular, do not put:

```text
GEMINI_API_KEY
```

inside the Vite frontend.

Only server-side backend code should access the Gemini credential.

## Database migrations

The production database schema is managed through Alembic.

The deployment startup process runs:

```bash
alembic upgrade head
```

This ensures the database schema is brought to the latest migration before the application begins serving requests.

If a migration fails, investigate the migration/database error rather than manually modifying production tables.

To inspect migration status locally:

```bash
alembic current
```

To inspect available migrations:

```bash
alembic history
```

## Keeping the demo alive

The availability and pricing of hosted free tiers can change over time.

For a portfolio deployment, monitor the selected Render services and database lifecycle rather than assuming that a particular free-tier configuration will remain unchanged indefinitely.

The main considerations are:

* Web-service sleep/cold-start behavior
* Database storage limits
* Database retention/lifecycle policies
* API usage limits
* Gemini API quotas
* Render service limits

If the database plan has a lifecycle or expiration limitation, plan a migration or upgrade before production data becomes unavailable.

For a portfolio demo, the application data is generally less important than keeping the application itself reproducible.

The repository should therefore remain capable of recreating the system from:

```text
GitHub
+
render.yaml
+
Alembic migrations
+
environment variables
```

## Cold-start behavior

If the deployed web service is running on a plan that sleeps after inactivity, the first request after a period of inactivity may take longer than subsequent requests.

This is normal for a sleeping service.

For a live portfolio demonstration, open the dashboard a few minutes before the demonstration and perform a health check so the service is awake.

If the first request is slow, explain that it is a deployment-platform cold start rather than an application failure.

## Troubleshooting

### Backend does not start

Check the Render service logs.

Look for:

```text
Docker build failure
Dependency installation failure
Alembic migration failure
Environment variable errors
Application startup errors
```

### Gemini requests fail

Verify:

```text
GEMINI_API_KEY
```

is configured correctly in the backend Render service.

Also verify that the configured model is:

```text
gemini-2.5-flash
```

and that the application is using the expected Gemini OpenAI-compatible endpoint.

Do not troubleshoot by exposing the API key in logs or source code.

### CORS error in browser

Verify:

```text
CORS_ALLOWED_ORIGINS
```

matches the exact deployed frontend origin.

For example:

```text
https://ai-sdr-dashboard.onrender.com
```

Do not add an unnecessary trailing path.

### Frontend cannot reach backend

Verify:

```text
VITE_API_BASE_URL
```

points to the actual deployed backend URL.

Then redeploy the frontend because Vite embeds environment variables during the build.

### Database connection failure

Check:

```text
DATABASE_URL
```

and verify that the database service is available.

Then inspect the backend logs for SQLAlchemy/PostgreSQL connection errors.

### Authentication fails

Check:

```text
JWT_SECRET_KEY
```

and backend authentication logs.

Do not rotate the JWT secret unnecessarily while active sessions are being tested unless you understand the resulting session invalidation.

## Production security checklist

Before sharing the public demo:

```text
[ ] .env is not committed
[ ] GEMINI_API_KEY is not exposed
[ ] JWT_SECRET_KEY is not exposed
[ ] Database credentials are not exposed
[ ] Frontend contains no server-side secrets
[ ] CORS is restricted to the deployed frontend
[ ] Production database is connected
[ ] Alembic migrations completed
[ ] /health endpoint works
[ ] Registration works
[ ] Login works
[ ] Lead creation works
[ ] Research works
[ ] Scoring works
[ ] Drafting works
[ ] Guardrail works
[ ] Agent trace works
```

## Verifying a deploy

The fastest backend sanity check is:

```bash
curl https://<your-api>.onrender.com/health
```

Expected:

```json
{
  "status": "ok",
  "env": "production"
}
```

Then verify the frontend:

```text
https://<your-dashboard>.onrender.com
```

Finally perform one complete lead run.

The strongest deployment verification is therefore:

```text
Health
  ↓
Register
  ↓
Login
  ↓
Create Lead
  ↓
Research
  ↓
Score
  ↓
Draft
  ↓
Guardrail
  ↓
Agent Trace
```

## Final deployment architecture

The deployed system is:

```text
                         GitHub
                           │
                           ▼
                    Render Blueprint
                           │
             ┌─────────────┼─────────────┐
             │             │             │
             ▼             ▼             ▼
        FastAPI API    React Dashboard  PostgreSQL
        Docker         Static Site
             │             │
             │             │
             │             ▼
             │        VITE_API_BASE_URL
             │
             ▼
        LangGraph
             │
       ┌─────┼─────┐
       │     │     │
       ▼     ▼     ▼
   Research Score Draft
       │     │     │
       └─────┼─────┘
             ▼
        Guardrail
             │
             ▼
       Self-Correction
             │
             ▼
           Ready
             │
             ▼
       Google Gemini
       gemini-2.5-flash
```

The production deployment keeps the same application architecture used locally while separating frontend hosting, backend execution, database persistence, and LLM access.

The Gemini API key remains server-side, the database schema is managed through Alembic, the backend is containerized with Docker, and the frontend communicates with the backend through the configured production API URL.
