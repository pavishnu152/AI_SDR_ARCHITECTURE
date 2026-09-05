# Demo Walkthrough

No screen recording is included in this repo — this sandbox has no browser to record one. This is the script to follow to demo it live or record your own, in order, with what each step is meant to show.

## 1. Setup (once)

```bash
pip install -e ".[dev]"

cp .env.example .env
# Fill in a real GEMINI_API_KEY

alembic upgrade head

uvicorn src.main:app --reload
```

```bash
cd frontend

npm install

cp .env.example .env
# Default already points at localhost:8000

npm run dev
```

Open `http://localhost:5173`.

The backend uses Google Gemini through its OpenAI-compatible API endpoint with the `gemini-2.5-flash` model.

## 2. Register and log in

Use the Register tab on the login screen.

The frontend calls:

```text
POST /auth/register
POST /auth/token
```

This demonstrates:

* JWT authentication working end to end
* Password hashing
* Protected API access
* User-specific data access
* Passwords never being logged or stored in plaintext

## 3. Research a lead

On the Leads page, enter a real company name. A company with genuine, findable AI-related signals works best for a good demo — for example, an AI-native startup you know of.

Click **Research**.

### What's happening under the hood

Worth narrating live:

1. **Research Agent**

   The Research Agent performs an agentic research process using the available web tools.

   It can decide which:

   ```text
   web_search
   fetch_page
   ```

   calls are useful rather than following only a fixed research script.

2. **Scoring Agent**

   The Scoring Agent evaluates the research against the configurable ICP defined in:

   ```text
   configs/icp_ai_native_b2b.yaml
   ```

   The lead receives a score from 0–100 along with the reasoning and confidence.

3. **Reject-Early Gate**

   If the score clears the configured rejection threshold, the pipeline continues to drafting.

   If the score is below the threshold, the pipeline stops early.

   This avoids generating outreach for poor-fit leads and reduces unnecessary downstream LLM usage.

4. **Drafting Agent**

   Qualified leads are passed to the Drafting Agent.

   The agent generates personalized outreach using the researched company information and scoring context.

5. **Guardrail Agent**

   The Guardrail Agent independently checks the generated outreach against the available research.

   It checks for issues such as:

   * Unsupported company claims
   * Incorrect personalization
   * Factual inconsistencies
   * Poor outreach quality
   * Other validation failures

6. **Self-Correction**

   If the guardrail rejects the draft, the system provides the guardrail feedback to the drafting stage for one correction pass.

   The corrected draft is then checked again.

   The system does not allow unlimited recursive correction.

The current LLM provider is **Google Gemini**, using:

```text
Model:
gemini-2.5-flash

Endpoint:
https://generativelanguage.googleapis.com/v1beta/openai/
```

The call can take several seconds because the workflow performs multiple agent and tool operations. The UI displays **"Running pipeline..."** while the run is in progress.

## 4. Lead detail page

Click into the researched lead.

The lead detail page shows the results of the complete pipeline.

### Research

Shows:

* Research summary
* Individual company signals
* Evidence gathered by the Research Agent
* Source URLs where available

### Score

Shows:

* 0–100 ICP score
* Confidence
* Scoring Agent reasoning
* Qualification/rejection result

### Outreach draft

Shows:

* Generated subject
* Outreach message
* Personalization
* Guardrail-approved or guardrail-flagged status

### Agent trace

Shows the execution history associated with the lead.

The trace is intended to make the workflow observable rather than treating the multi-agent system as a black box.

Where available, it includes information such as:

* Agent invocation
* Execution status
* Failed attempts
* Retries/correction attempts
* Per-call latency
* Token/usage information

The `AgentLog` audit table provides a persistent record of the pipeline's execution and decisions.

## 5. Optional — Demonstrate the fail-closed guardrail

This is difficult to force organically during a normal demo, but it is worth explaining even if it is not shown live.

If the Guardrail Agent's LLM call fails because of an API error, rate limit, outage, or another provider-side failure, the system does **not** automatically mark the outreach as approved.

Instead, the guardrail fails closed.

Conceptually:

```text
Guardrail LLM call
       │
       ├── Successful validation
       │       │
       │       ├── PASS → READY
       │       └── FAIL → correction/review
       │
       └── LLM/API failure
               │
               ▼
          Fail closed
```

This is an important safety property because an infrastructure failure should not silently become an approval decision.

The behavior is covered by:

```text
tests/agents/test_guardrail_agent.py
```

Point to the relevant test if asked about this during an interview.

## 6. Optional — Show the audit trail surviving a real failure

The research-agent test suite contains regression coverage for client-side failures as well as normal API failures.

For example:

```text
tests/agents/test_research_agent.py
```

The test coverage demonstrates that failures during the provider/client interaction are handled by the application's error path rather than being allowed to escape as uncontrolled exceptions.

This is useful to mention during an interview because mocked unit tests can verify application logic, while real provider testing can reveal failures associated with actual credential resolution and SDK behavior.

The important production principle is:

```text
External provider failure
        │
        ▼
Controlled application error
        │
        ▼
Audit information preserved
        │
        ▼
No silent approval
```

## 7. Eval harness (terminal, not the UI)

Run:

```bash
python -m src.eval.run_eval
```

The evaluation harness runs the Scoring Agent against the project's labeled synthetic-company evaluation dataset.

The evaluation reports quantitative scoring-quality metrics such as:

* Precision
* Recall
* F1
* Agreement rate
* LLM/token usage information where available

The purpose is to make agent-quality changes measurable rather than relying only on subjective inspection.

For example, after changing a prompt or model configuration, the same evaluation harness can be run again to compare the results.

The evaluation should therefore be presented as:

```text
Prompt/model change
        │
        ▼
Run evaluation
        │
        ▼
Compare metrics
        │
        ▼
Determine whether quality improved
```

No unverified Gemini dollar pricing is assumed in the demo documentation. Provider pricing should only be reported when it has been explicitly verified and implemented in the project's pricing configuration.

## 8. Recommended live demo order

For a short interview or portfolio demonstration, use this sequence:

```text
1. Open application
       │
       ▼
2. Register / Login
       │
       ▼
3. Create or select a lead
       │
       ▼
4. Run Research
       │
       ▼
5. Show Research results
       │
       ▼
6. Show ICP score
       │
       ▼
7. Explain Reject-Early Gate
       │
       ▼
8. Show personalized outreach
       │
       ▼
9. Show Guardrail result
       │
       ▼
10. Show Agent Trace
       │
       ▼
11. Explain fail-closed behavior
       │
       ▼
12. Run evaluation harness
```

The key story to communicate is:

> This is not simply an LLM chatbot. It is a controlled multi-agent workflow where research produces evidence, scoring determines qualification, poor-fit leads are rejected early, qualified leads receive personalized outreach, and an independent guardrail validates the result before it is considered ready.

## 9. Key points to emphasize during the demo

### Multi-agent architecture

Each agent has a specific responsibility:

```text
Research
   ↓
Score
   ↓
Reject Early
   ↓
Draft
   ↓
Guardrail
   ↓
Self-Correction
   ↓
Ready
```

### Evidence-based generation

The drafting stage receives researched company information rather than generating personalization from an empty prompt.

### Independent validation

The Guardrail Agent separately evaluates the generated outreach instead of trusting the Drafting Agent's output.

### Bounded autonomy

The self-correction mechanism is limited to one correction cycle.

### Production engineering

The project includes:

* FastAPI
* React
* LangGraph
* PostgreSQL
* SQLAlchemy
* Alembic
* JWT authentication
* Docker
* GitHub Actions
* Automated tests
* Ruff
* Evaluation harness
* Render deployment
* Vercel deployment

### Provider isolation

The application accesses Google Gemini through a provider configuration layer.

Current model:

```text
gemini-2.5-flash
```

This keeps the provider/model configuration separate from the core workflow and makes future model changes easier.

### Observability

The system records workflow execution information so that agent behavior and failures can be inspected rather than hidden behind a single final response.

### Fail-closed behavior

A guardrail infrastructure failure does not result in automatic approval.

That is an important distinction between a production-oriented agent workflow and an uncontrolled LLM generation pipeline.
