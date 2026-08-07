# AI SDR — Multi-Agent Sales Lead Research & Qualification System

Status: **in development (Milestone 2 of 14)** — scaffolding stage. Full README (setup, usage, screenshots, results) will be written at the deployment milestone.

See [`docs/architecture.md`](docs/architecture.md) for the full problem definition, agent architecture, tech stack rationale, and milestone plan.

## What this is

A multi-agent system that, given a lead (company), autonomously:
1. Researches the company (Research Agent)
2. Scores it against an Ideal Customer Profile — AI-native B2B companies (Scoring Agent)
3. Drafts personalized outreach (Drafting Agent)
4. Fact-checks the draft against the research before anything is marked ready to send (Guardrail Agent)

Every agent decision is logged for full traceability — this is not a black-box chatbot wrapper.

## Local development (once dependencies land in later milestones)

```bash
pip install -e ".[dev]"
cp .env.example .env  # fill in your Anthropic API key
uvicorn src.main:app --reload
```
