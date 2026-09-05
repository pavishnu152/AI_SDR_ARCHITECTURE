# AI SDR — System Architecture

## 1. System Overview

The AI SDR is a production-oriented, multi-agent sales development system designed to research companies, evaluate them against a configurable Ideal Customer Profile (ICP), generate personalized outreach, and independently verify the generated content before it is marked ready to send.

The system follows a gated agent workflow:

Research → Score → Reject Early → Draft → Guardrail → Self-Correction → Ready

The architecture separates:

- API and authentication
- Agent orchestration
- Individual agent responsibilities
- External tools
- Database persistence
- LLM provider configuration
- Evaluation
- Deployment infrastructure

The goal is to demonstrate production-style AI engineering rather than a simple LLM wrapper.

---

## 2. High-Level Architecture

```text
                         ┌──────────────────────────┐
                         │        React UI           │
                         │     Vite + TypeScript     │
                         └────────────┬─────────────┘
                                      │
                                      │ HTTP / JWT
                                      ▼
                         ┌──────────────────────────┐
                         │       FastAPI API         │
                         │                          │
                         │ Authentication           │
                         │ Lead Management          │
                         │ Run Management           │
                         │ Health Checks            │
                         └────────────┬─────────────┘
                                      │
                                      ▼
                         ┌──────────────────────────┐
                         │       LangGraph           │
                         │    Agent Orchestrator     │
                         └────────────┬─────────────┘
                                      │
                 ┌────────────────────┼────────────────────┐
                 │                    │                    │
                 ▼                    ▼                    ▼
        ┌────────────────┐   ┌────────────────┐   ┌────────────────┐
        │ Research Agent │   │ Scoring Agent  │   │ Drafting Agent │
        └───────┬────────┘   └────────────────┘   └───────┬────────┘
                │                                          │
                ▼                                          ▼
        ┌────────────────┐                         ┌────────────────┐
        │ Search / Fetch │                         │ Guardrail Agent│
        │    Tools       │                         └────────────────┘
        └────────────────┘                                  │
                                                            ▼
                                                  ┌──────────────────┐
                                                  │ Self-Correction  │
                                                  │      Loop        │
                                                  └──────────────────┘

                                      │
                                      ▼
                         ┌──────────────────────────┐
                         │       PostgreSQL          │
                         │                          │
                         │ Users                    │
                         │ Leads                    │
                         │ Runs                     │
                         │ Agent Results             │
                         └──────────────────────────┘

                                      │
                                      ▼
                         ┌──────────────────────────┐
                         │       Google Gemini       │
                         │      gemini-2.5-flash     │
                         │                          │
                         │ OpenAI-compatible API     │
                         └──────────────────────────┘
3. Core Workflow

Each lead moves through a controlled multi-agent workflow.

START
  │
  ▼
Research
  │
  ▼
Score
  │
  ▼
ICP Gate
  │
  ├──────────────► REJECT
  │
  ▼
Draft
  │
  ▼
Guardrail
  │
  ├──────────────► FAIL
  │                    │
  │                    ▼
  │              Self-Correction
  │                    │
  │                    ▼
  │              Guardrail Again
  │
  ▼
READY

The workflow intentionally rejects unsuitable leads before spending additional LLM usage on drafting and validation.

4. Technology Stack
Layer	Technology	Purpose
Frontend	React	Dashboard UI
Frontend Build	Vite	Frontend development/build
Frontend Language	TypeScript	Type-safe frontend development
Styling	Tailwind CSS	UI styling
Backend	FastAPI	REST API
Agent Orchestration	LangGraph	Stateful multi-agent workflow
LLM	Google Gemini API	Research, scoring, drafting and guardrail reasoning
LLM Model	gemini-2.5-flash	Current production model
LLM SDK	OpenAI Python SDK	Access Gemini through its OpenAI-compatible endpoint
Database	PostgreSQL	Persistent application data
ORM	SQLAlchemy	Database abstraction
Migrations	Alembic	Database schema migrations
Authentication	JWT	Stateless API authentication
Containerization	Docker	Reproducible deployment
CI	GitHub Actions	Automated validation
Testing	Pytest	Automated testing
Linting	Ruff	Code quality
Evaluation	Synthetic evaluation harness	Agent quality measurement
Deployment	Render	Backend deployment
Frontend Deployment	Vercel	Frontend hosting
5. Backend Architecture

The backend is structured around clear separation of concerns.

src/
├── agents/
│   ├── research_agent.py
│   ├── scoring_agent.py
│   ├── drafting_agent.py
│   └── guardrail_agent.py
│
├── api/
│   ├── auth.py
│   ├── leads.py
│   ├── runs.py
│   └── health.py
│
├── core/
│   ├── config.py
│   ├── database.py
│   ├── security.py
│   └── pricing.py
│
├── db/
│   ├── models.py
│   └── repositories.py
│
├── graph/
│   └── workflow.py
│
├── schemas/
│   ├── auth.py
│   ├── leads.py
│   └── runs.py
│
├── tools/
│   ├── web_search.py
│   └── page_fetch.py
│
├── eval/
│   └── run_eval.py
│
└── main.py

The architecture keeps business logic out of the API routes wherever possible.

6. Agent Responsibilities
6.1 Research Agent

The Research Agent gathers factual information about the target company.

Responsibilities:

Search for company information
Retrieve relevant web pages
Extract useful company facts
Identify company size and industry
Identify products or services
Identify relevant business signals
Produce structured research output
Preserve source URLs where applicable

The Research Agent should focus on evidence gathering rather than deciding whether the company is a good prospect.

Inputs
Company name
Company domain
Optional lead metadata
Outputs
Company overview
Industry
Employee/company-size signals
Products/services
Business signals
Evidence
Source URLs
Research confidence
7. Scoring Agent

The Scoring Agent evaluates the researched company against the configured ICP.

The scoring process is configurable rather than hard-coded to a single company.

Example ICP dimensions:

Industry
Company size
Geography
Technology signals
Business model
Funding/growth signals
Relevant pain points

The agent produces a structured score and explanation.

Example:

{
  "score": 82,
  "fit": "strong",
  "reasons": [
    "Matches target industry",
    "Company size is within ICP range",
    "Strong technology adoption signals"
  ]
}

The scoring stage is intentionally separated from research so that evidence collection and business qualification remain independent responsibilities.

8. Reject-Early Gate

After scoring, the workflow evaluates whether the lead should continue.

Score >= threshold
        │
        ├── YES ──► Draft
        │
        └── NO ───► Reject

The threshold is configurable.

Example:

Minimum ICP score = 60

A lead scoring below the threshold is rejected before drafting.

This prevents unnecessary downstream LLM usage and avoids generating outreach for poor-fit companies.

9. Drafting Agent

The Drafting Agent generates personalized outreach only for qualified leads.

Inputs include:

Company research
ICP score
ICP reasoning
Relevant company signals
Target persona
Outreach configuration

The draft should:

Reference verified company information
Explain a relevant business problem
Avoid generic personalization
Maintain professional tone
Include a clear call to action
Avoid unsupported claims

Example output structure:

{
  "subject": "...",
  "body": "...",
  "personalization_points": [
    "..."
  ]
}
10. Guardrail Agent

The Guardrail Agent independently reviews the generated outreach.

It should not simply trust the Drafting Agent.

The guardrail checks for:

Factual accuracy

Are company claims supported by research?

Unsupported claims

Does the message invent:

products
customers
funding
partnerships
metrics
executives
business initiatives
Personalization quality

Does the message use actual company-specific evidence?

Sales quality

Does the message contain:

a clear value proposition
relevant context
appropriate CTA
professional language
Safety and policy

The message should not contain inappropriate or deceptive claims.

The Guardrail Agent returns a structured validation result.

Example:

{
  "passed": false,
  "issues": [
    {
      "type": "unsupported_claim",
      "severity": "high",
      "text": "..."
    }
  ]
}
11. Self-Correction Loop

The system contains one controlled self-correction loop.

Draft
  │
  ▼
Guardrail
  │
  ├── PASS ──► READY
  │
  └── FAIL
        │
        ▼
   Self-Correction
        │
        ▼
      Draft
        │
        ▼
    Guardrail
        │
        ├── PASS ──► READY
        │
        └── FAIL ──► FAILED

The loop is deliberately limited to one correction cycle.

This prevents uncontrolled agent recursion and makes execution behavior predictable.

12. LangGraph State

The workflow uses a shared state object.

Conceptually:

class SDRState:
    lead_id: str
    company_name: str
    company_domain: str

    research: dict | None
    score: dict | None

    rejected: bool
    rejection_reason: str | None

    draft: dict | None
    guardrail: dict | None

    correction_count: int

    status: str
    error: str | None

LangGraph nodes update this state as the workflow progresses.

The state makes the workflow explicit and observable.

13. LLM Provider Architecture

The application uses Google Gemini through its OpenAI-compatible API endpoint.

The provider configuration is isolated inside the application configuration layer.

Application
     │
     ▼
Agent
     │
     ▼
OpenAI-compatible SDK
     │
     ▼
Google Gemini OpenAI-compatible endpoint
     │
     ▼
gemini-2.5-flash

Current configuration:

Provider:
Google Gemini

Model:
gemini-2.5-flash

Endpoint:
https://generativelanguage.googleapis.com/v1beta/openai/

The application does not hard-code provider configuration inside individual business workflows.

This makes future provider/model changes easier without redesigning the agent architecture.

14. Configuration Management

Environment variables are used for secrets and deployment-specific configuration.

Example:

GEMINI_API_KEY=
DATABASE_URL=
JWT_SECRET_KEY=

Application code reads these values through the configuration layer.

Secrets are never committed to Git.

The real .env file remains local and is excluded through .gitignore.

A safe .env.example contains placeholders only.

Example:

GEMINI_API_KEY=your_gemini_api_key_here
DATABASE_URL=postgresql://user:password@localhost:5432/ai_sdr
JWT_SECRET_KEY=replace_with_a_secure_secret
15. Authentication Architecture

The API uses JWT-based authentication.

User
 │
 ▼
Login
 │
 ▼
FastAPI
 │
 ▼
Credential Validation
 │
 ▼
JWT Token
 │
 ▼
Protected API Requests

Protected endpoints validate the JWT before accessing user-specific resources.

Authentication responsibilities include:

User registration
Login
Password hashing
JWT generation
JWT validation
Protected routes
User ownership checks

Passwords are never stored in plaintext.

16. Database Architecture

PostgreSQL is the production database.

Core entities include:

User
 │
 ├── Leads
 │
 └── Runs
       │
       ├── Research result
       ├── Scoring result
       ├── Draft result
       └── Guardrail result

The database stores persistent application state rather than temporary workflow-only state.

SQLAlchemy provides ORM functionality.

Alembic manages schema migrations.

17. API Architecture

The FastAPI layer exposes REST endpoints.

Typical endpoint groups:

/auth
/leads
/runs
/health

Example flow:

POST /auth/register
POST /auth/login

POST /leads
GET  /leads

POST /runs
GET  /runs/{run_id}

GET /health

The API layer is responsible for:

Request validation
Authentication
Authorization
Calling application services/workflows
Returning structured responses
Error handling

The API should not contain complex agent orchestration logic directly.

18. Tool Architecture

Agents can access bounded external tools.

Current tools include:

Web Search
Page Fetch
Web Search

Used to discover relevant public information.

Responsibilities:

Search public web sources
Return search results
Preserve URLs
Bound the amount of retrieved information
Page Fetch

Used to retrieve content from selected URLs.

Responsibilities:

Fetch public pages
Extract useful text
Limit content size
Handle request failures
Avoid uncontrolled content retrieval

Tools are kept separate from agents so they can be tested independently.

19. Tool Safety

External web content is treated as untrusted input.

The system should:

Limit request sizes
Limit fetched content
Apply timeouts
Handle failures
Avoid executing arbitrary page content
Keep retrieved content separate from system instructions
Preserve source URLs for traceability

The research process should prefer evidence-backed claims rather than blindly trusting generated text.

20. Error Handling

Errors are represented explicitly throughout the system.

Typical failure categories:

AuthenticationError
ValidationError
DatabaseError
ToolError
LLMError
WorkflowError

The API returns appropriate HTTP responses rather than exposing internal stack traces.

LLM/API failures should be captured and converted into controlled workflow failures.

Example:

LLM request fails
       │
       ▼
Agent captures error
       │
       ▼
Workflow records failure
       │
       ▼
API returns controlled response
21. Observability

Each lead run should have a traceable lifecycle.

Example:

run_id
lead_id
status
current_stage
started_at
completed_at
error

Agent outputs should be persisted sufficiently to diagnose failures and evaluate system quality.

Important metrics include:

Research success rate
Scoring success rate
Reject rate
Draft success rate
Guardrail pass rate
Self-correction rate
Final ready rate
Workflow failure rate
LLM usage per lead run
Average execution time
22. Evaluation Strategy

The project includes a synthetic evaluation harness.

The evaluation dataset contains representative companies and expected outcomes.

Evaluation dimensions include:

Research quality
Relevant facts retrieved
Source quality
Missing information
Hallucination rate
Scoring quality
ICP alignment
Score consistency
Explanation quality
Draft quality
Personalization
Relevance
Clarity
CTA quality
Unsupported claims
Guardrail quality
Correctly detects unsupported claims
Correctly accepts valid drafts
Produces useful failure reasons
Workflow quality
Correct routing
Correct rejection behavior
Correct self-correction behavior
No uncontrolled recursion
23. Evaluation Dataset

The synthetic evaluation harness should contain cases such as:

Strong ICP fit
Medium ICP fit
Poor ICP fit
Insufficient research
Conflicting evidence
Unsupported personalization
Valid personalized draft
Guardrail failure
Self-correction success
Self-correction failure

This allows the system to be tested beyond simple unit tests.

24. Testing Strategy

The project uses multiple testing layers.

Unit Tests

Test individual functions and components.

Examples:

Configuration
Pricing/usage handling
Authentication
Repositories
Tools
Agents
Schemas
Integration Tests

Test interactions between:

API
Database
Workflow
Agents
Workflow Tests

Validate:

Research → Score
Score → Reject
Score → Draft
Draft → Guardrail
Guardrail → Self-Correction
Guardrail → Ready
End-to-End Tests

Validate the complete application flow.

25. Code Quality

Ruff is used for linting and code quality checks.

The CI pipeline should run:

ruff check src tests
pytest

A successful CI run should provide confidence that the repository is syntactically valid, lint-clean, and passing automated tests.

26. CI/CD Architecture

GitHub Actions provides automated validation.

Developer
   │
   ▼
Git Push
   │
   ▼
GitHub
   │
   ▼
GitHub Actions
   │
   ├── Install dependencies
   │
   ├── Ruff
   │
   ├── Pytest
   │
   └── Build/validation

Deployment should only proceed after required checks pass.

27. Docker Architecture

Docker provides a reproducible backend runtime.

Conceptually:

Docker Image
    │
    ├── Python runtime
    ├── Application dependencies
    ├── Backend source
    └── Startup configuration

The application is configured through environment variables at runtime.

Secrets are not baked into the Docker image.

28. Deployment Architecture

Production deployment is split between frontend and backend.

                         Internet
                            │
             ┌──────────────┴──────────────┐
             │                             │
             ▼                             ▼
        Vercel                         Render
      React Frontend                 FastAPI Backend
                                           │
                                           ▼
                                      PostgreSQL
                                           │
                                           ▼
                                     Google Gemini

The frontend communicates with the backend API.

The backend communicates with PostgreSQL and Google Gemini.

Database credentials and Gemini credentials remain server-side.

29. Environment Separation

The system should distinguish between local development and production configuration.

Local
localhost
local PostgreSQL
local environment variables
development frontend
Production
Render
managed PostgreSQL
production environment variables
Vercel frontend
Google Gemini API

Production secrets are configured through the deployment platform rather than committed to the repository.

30. Security Model

Security controls include:

Secrets
Never commit .env
Never expose API keys in frontend code
Never hard-code secrets
Use deployment environment variables
Authentication
Hash passwords
Use signed JWT tokens
Validate authentication on protected routes
Authorization

Users should only access resources they own.

External tools
Apply request timeouts
Bound content
Treat external content as untrusted
LLM output

Generated content is validated before being considered ready.

31. Data Flow

A complete lead run looks like this:

1. User creates lead
        │
        ▼
2. API validates request
        │
        ▼
3. Lead stored in PostgreSQL
        │
        ▼
4. LangGraph run starts
        │
        ▼
5. Research Agent
        │
        ├── Web Search
        └── Page Fetch
        │
        ▼
6. Research result stored
        │
        ▼
7. Scoring Agent
        │
        ▼
8. ICP Gate
        │
        ├── Reject → END
        │
        ▼
9. Drafting Agent
        │
        ▼
10. Guardrail Agent
        │
        ├── PASS → READY
        │
        └── FAIL
              │
              ▼
        11. Self-Correction
              │
              ▼
        12. Guardrail
              │
              ├── PASS → READY
              │
              └── FAIL → FAILED
32. Failure Strategy

The system is designed to fail safely.

Research failure
Research unavailable
       │
       ▼
Run marked failed
Scoring failure
Research exists
       │
       ▼
Scoring fails
       │
       ▼
Run marked failed
Low ICP score
Score below threshold
       │
       ▼
Reject lead
       │
       ▼
No drafting
Guardrail failure
Draft fails validation
       │
       ▼
One self-correction attempt
       │
       ├── Pass → Ready
       │
       └── Fail → Failed

This provides deterministic limits around agent behavior.

33. Cost and Usage Control

The system reduces unnecessary LLM usage through workflow gating.

The primary optimization is:

Research
   ↓
Score
   ↓
Reject bad leads early
   ↓
Draft only qualified leads
   ↓
Guardrail
   ↓
One correction maximum

This prevents every lead from automatically reaching every agent.

The project intentionally avoids hard-coding unverified provider pricing into the architecture documentation.

Actual usage/cost reporting should be based on verified provider pricing and the application's measured token usage.

34. Scalability Considerations

The initial architecture is designed for a small production workload.

Potential future improvements include:

Async job processing

Move long-running agent runs into a worker queue.

Possible architecture:

FastAPI
   │
   ▼
Job Queue
   │
   ▼
Worker
   │
   ▼
LangGraph
Caching

Cache:

Company research
Search results
Page content
Rate limiting

Control:

API requests
Web requests
LLM requests
Horizontal scaling

Multiple backend/worker instances can process independent lead runs.

35. Reliability Considerations

The architecture avoids uncontrolled autonomous behavior.

Reliability mechanisms include:

Explicit LangGraph transitions
Typed state
Early rejection
Bounded tool access
One self-correction loop
Persistent run state
Controlled errors
Automated testing
CI validation

The system therefore behaves more like a controlled workflow engine than an unconstrained autonomous agent.

36. Design Principles
Separation of concerns

Each component has a clear responsibility.

Explicit orchestration

The workflow is represented explicitly through LangGraph.

Evidence before generation

Research occurs before scoring and drafting.

Independent verification

The Guardrail Agent independently validates generated outreach.

Fail fast

Poor-fit leads are rejected before expensive downstream processing.

Bounded autonomy

The self-correction mechanism has a fixed limit.

Configuration over hard-coding

ICP thresholds, provider configuration, and environment-specific settings are configurable.

Production readiness

Authentication, persistence, migrations, testing, CI/CD, Docker, deployment, and security are part of the architecture rather than afterthoughts.

37. Current Architecture Decision

The current production architecture uses:

Frontend:
React + Vite + TypeScript + Tailwind CSS

Backend:
FastAPI

Agent Orchestration:
LangGraph

Database:
PostgreSQL

ORM:
SQLAlchemy

Migrations:
Alembic

Authentication:
JWT

LLM Provider:
Google Gemini

LLM Model:
gemini-2.5-flash

LLM Access:
OpenAI-compatible Gemini API endpoint

Tools:
Web Search + Page Fetch

Testing:
Pytest

Linting:
Ruff

Containerization:
Docker

CI:
GitHub Actions

Backend Deployment:
Render

Frontend Deployment:
Vercel

The overall architecture is intentionally provider-isolated so the LLM provider or model can be changed later without redesigning the agent workflow.

38. Final Architecture Summary

The AI SDR is a controlled, evidence-driven multi-agent system.

The complete architecture is:

                         USER
                          │
                          ▼
                 ┌─────────────────┐
                 │   React/Vite UI │
                 └────────┬────────┘
                          │
                          ▼
                 ┌─────────────────┐
                 │     FastAPI     │
                 │   JWT Auth      │
                 └────────┬────────┘
                          │
                          ▼
                 ┌─────────────────┐
                 │    LangGraph    │
                 │   Orchestrator  │
                 └────────┬────────┘
                          │
             ┌────────────┼─────────────┐
             │            │             │
             ▼            ▼             ▼
        Research       Scoring        Drafting
          Agent         Agent          Agent
             │            │             │
             ▼            ▼             ▼
        Web Search    ICP Evaluation   Guardrail
        Page Fetch          │             │
                            │             ▼
                            │       Self-Correction
                            │             │
                            └─────────────┘
                                  │
                                  ▼
                                READY
                                  │
                                  ▼
                            PostgreSQL

                                  │
                                  ▼
                         Google Gemini API
                         gemini-2.5-flash

The system demonstrates the core capabilities expected from a production-oriented AI engineering project:

Multi-agent orchestration
Structured state management
LLM integration
Tool calling
Evidence-based research
Configurable ICP scoring
Early rejection
Personalized generation
Independent guardrails
Controlled self-correction
Authentication
PostgreSQL persistence
API design
Docker
CI/CD
Automated testing
Evaluation
Production deployment
Security-conscious configuration

The architecture is designed to be understandable, testable, observable, and extensible while keeping the autonomous behavior bounded and predictable.