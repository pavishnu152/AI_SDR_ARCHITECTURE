// All content sourced from the resume and the AI SDR project's own docs —
// nothing fabricated. Update here once, reflected everywhere.

export const profile = {
  name: "Pavishnu S",
  title: "AI/ML Engineer",
  subtitle: "Building production multi-agent systems, RAG pipelines, and applied deep learning",
  location: "Bangalore, Karnataka, India",
  email: "sspavishnu16@gmail.com",
  phone: "+91 81442 81008",
  github: "https://github.com/pavishnu152",
  linkedin: "https://linkedin.com/in/pavishnu152",
  resumeFile: "/Pavishnu_Resume.pdf",
  summary:
    "B.Tech IT graduate (2026) who ships working AI systems, not notebooks. Four end-to-end projects spanning agentic pipelines, RAG, and applied deep learning — including a multi-agent system with a fail-closed guardrail and full per-call audit logging, and a CNN+BiGRU model at 96.39% accuracy.",
};

export const featuredProject = {
  name: "AI SDR",
  tagline: "A 4-agent lead research and qualification pipeline with full decision traceability",
  description:
    "Given a company name, four coordinated agents autonomously research it, score it against a configurable Ideal Customer Profile, draft personalized outreach, and independently fact-check that draft before anything is marked ready to send. Every agent call — including failures and retries — is logged to an append-only audit table. Not a chatbot wrapper: a pipeline with a fail-closed guardrail and a real evaluation harness.",
  stack: [
    "FastAPI",
    "LangGraph",
    "Anthropic Claude (Haiku 4.5 + Sonnet 5)",
    "PostgreSQL",
    "SQLAlchemy 2.0",
    "React",
    "TypeScript",
    "Docker",
    "GitHub Actions",
  ],
  highlights: [
    {
      label: "Tiered model use",
      detail: "Haiku 4.5 for high-volume research/scoring, Sonnet 5 for higher-stakes drafting/guardrail — not one expensive model for everything.",
    },
    {
      label: "Fail-closed guardrail",
      detail: "An LLM outage during the fact-check step results in a flagged lead for human review, never a silently-approved one.",
    },
    {
      label: "Two orchestrators, compared",
      detail: "Built as a hand-rolled state machine first, then refactored onto LangGraph — with the honest finding that the LangGraph version is more lines of code, documented and tested side by side.",
    },
    {
      label: "Real bug found via live testing",
      detail: "A missing API key raised a client-side error that unit tests couldn't reach (they mock the client). A live smoke test caught it; fixed with a regression test, not just a patch.",
    },
  ],
  stats: [
    { value: "102", label: "tests passing" },
    { value: "97%", label: "test coverage" },
    { value: "4", label: "coordinated agents" },
    { value: "1", label: "audit-logged decision at every step" },
  ],
  demoUrl: "", // filled in once deployed — see docs/deployment.md
  githubUrl: "", // filled in once pushed to GitHub
  diagramSrc: "/ai-sdr-architecture.svg",
};

export const otherProjects = [
  {
    name: "AI-Powered Enterprise Document Insight System",
    metric: "92% answer relevance",
    description:
      "RAG pipeline over enterprise documents with citation-grounded responses (85%+ accuracy) and zero external API dependency — local Ollama inference cut response latency 35%. Modular FastAPI backend for ingestion, indexing, and real-time query handling.",
    stack: ["Python", "FastAPI", "LangChain", "ChromaDB", "FAISS", "Ollama"],
    githubUrl: "https://github.com/pavishnu152/Enterprise-Doc-Insight",
  },
  {
    name: "AI Resume Analyzer",
    metric: "95.5% skill detection accuracy",
    description:
      "Transformer-embedding semantic relevance scoring for ATS-style resume evaluation — 40% higher keyword recall than standard ATS keyword filtering. FastAPI backend, React frontend, structured skill-gap output.",
    stack: ["Python", "FastAPI", "React.js"],
    githubUrl: "https://github.com/pavishnu152/AIRESUMEANALYZER",
  },
  {
    name: "Parkinson's Disease Detection System",
    metric: "96.39% accuracy",
    description:
      "Hybrid CNN+BiGRU deep learning model detecting Parkinson's from MRI scans — CNN extracts spatial features, BiGRU learns forward/backward feature relationships. Deployed as a Gradio app with automated PDF medical report generation.",
    stack: ["Python", "TensorFlow", "Keras", "Gradio"],
    githubUrl: "https://github.com/pavishnu152/Parkinson-Disease-Prediction-System",
  },
  {
    name: "ConvoLens AI",
    metric: "Real-time multi-speaker transcription",
    description:
      "Audio-to-text meeting assistant with real-time transcription, LLM-based summarization, and key-point extraction — eliminates manual meeting notes entirely, no technical setup required to use it.",
    stack: ["Python", "Streamlit", "AssemblyAI", "LM Studio"],
    githubUrl: "https://github.com/pavishnu152/ConvoLens-AI",
  },
];

export const skills = {
  "Generative AI": ["RAG", "LangChain", "LangGraph", "ChromaDB", "FAISS", "Ollama", "Prompt Engineering", "Embeddings", "Semantic Search"],
  "Machine Learning": ["Scikit-learn", "TensorFlow", "Keras", "CNN", "BiGRU", "Pandas", "NumPy", "Model Evaluation"],
  "Backend / Systems": ["Python", "FastAPI", "SQL", "PostgreSQL", "SQLAlchemy", "REST APIs", "Docker", "CI/CD"],
  "Frontend": ["React", "TypeScript", "Streamlit"],
};

export const certifications = [
  "Machine Learning with Python — Coursera",
  "Python for Data Science and AI — Udemy",
  "Claude Code Certification",
];
