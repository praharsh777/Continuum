# Continuum — Institutional Memory Agent for Autonomous Incident Response

Continuum is an AI-powered site reliability engineering (SRE) and incident diagnosis agent. It acts as an persistent institutional memory layer for software engineering teams by integrating **Hindsight Cloud** for memory recall/retention, **Groq** for high-speed LLM inference (`openai/gpt-oss-120b` with fallback), **SQLite** for local state persistence, and **Streamlit** for real-time SRE control dashboards.

---

## 🏛️ System Architecture

```
                                  +-----------------------+
                                  |   Streamlit Dashboard |
                                  |    (dashboard/app.py) |
                                  +-----------+-----------+
                                              |
                                              v
                                  +-----------------------+
                                  |   Diagnosis Service   |
                                  |   (agent/diagnosis.py)|
                                  +-----+-----------+-----+
                                        |           |
            +---------------------------+           +--------------------------+
            |                                                                  |
            v                                                                  v
+-----------------------+                                          +-----------------------+
|  Hindsight Memory     |                                          |   Groq LLM Engine     |
|  (agent/memory.py)    |                                          | (gpt-oss-120b/llama3) |
+-----------+-----------+                                          +-----------------------+
            |
            +-------------------+
            |                   |
            v                   v
 +-------------------+   +--------------------+
 | Hindsight Cloud   |   | Confidence Scorer  |
 | (TEMPR Search)    |   | (agent/confidence) |
 +-------------------+   +---------+----------+
                                   |
                                   v
                         +--------------------+
                         |  SQLite DB Store   |
                         |   (agent/db.py)    |
                         +--------------------+
```

---

## 💡 Key Features & Memory Mechanics

1. **Persistent Memory Retention & Recall (FR-1 to FR-3):**
   - Retains postmortems with rich context and metadata bound to `document_id`.
   - Recalls past postmortems using Hindsight TEMPR search (`budget="low"` for sub-second recall).
   - Zero-hallucination citation enforcement: only cites historical incident IDs explicitly returned by Hindsight recall.

2. **Structured LLM Diagnosis & Fallback (FR-4, NFR-1):**
   - Primary model: `openai/gpt-oss-120b`.
   - Fallback model: `llama3-70b-8192`.
   - Structured JSON output with strict error bounds.

3. **Memory-Driven Confidence Scoring (FR-5):**
   - Calculates candidate fix reliability: `Confidence = (Successful Resolutions) / (Total Resolution Attempts)`.
   - Handles novel incidents gracefully without artificial confidence inflation.

4. **Resolution & Postmortem Loop (FR-6):**
   - Generates structured postmortems upon incident resolution and automatically retains them live in Hindsight to influence future diagnoses.

5. **50-Incident Synthetic Dataset & A/B/C Arc (FR-7, FR-8):**
   - Pre-populated synthetic dataset spanning 10 fictional microservices.
   - Built-in reproducible Incident A / Incident B / Incident C demonstration arc.

---

## 🚀 Setup & Installation

### Prerequisites
- **Python 3.12+** (`py -3.12`)
- Hindsight Cloud API Key (`HINDSIGHT_API_KEY`)
- Groq API Key (`GROQ_API_KEY`)

### Environment Setup

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Configure your environment variables in `.env`:
   ```env
   HINDSIGHT_API_KEY=your_hindsight_api_key
   HINDSIGHT_BASE_URL=https://api.hindsight.vectorize.io
   HINDSIGHT_BANK_ID=continuum-demo
   GROQ_API_KEY=your_groq_api_key
   GROQ_PRIMARY_MODEL=openai/gpt-oss-120b
   GROQ_FALLBACK_MODEL=llama3-70b-8192
   ```

3. Install dependencies:
   ```bash
   py -3.12 -m pip install -r requirements.txt
   ```

---

## 🛠️ Usage & Operations

### 1. Resetting Demo State & Seeding Data
Resets the SQLite database and deletes/recreates the Hindsight memory bank, then seeds the 50-incident synthetic dataset:
```bash
py -3.12 scripts/reset_demo_state.py
```

### 2. Launching the Streamlit Dashboard
```bash
py -3.12 -m streamlit run dashboard/app.py
```
Open [http://localhost:8501](http://localhost:8501) in your browser.

### 3. Running Automated Test Suite
Run unit, integration, and latency tests:
```bash
py -3.12 -m unittest discover tests
```

---

## 🎬 Incident A / B / C Demonstration Walkthrough

Continuum's institutional memory loop can be demonstrated using the built-in demo arc:

1. **Incident A (Novel Incident — `INC-DEMO-A`):**
   - Select `INC-DEMO-A` ("Kafka consumer group offset lag spiking") in the dashboard feed.
   - Diagnose: Returns zero recalled memories. Explains that no historical incident exists.
   - Resolve: Enter fix details ("Increased partition count to 16 and rebalanced consumer group").
   - Postmortem: Retained live to Hindsight Cloud.

2. **Incident B (Repeat Incident — `INC-DEMO-B`):**
   - Select `INC-DEMO-B` ("Event stream processing delay and partition imbalance").
   - Diagnose: Hindsight recalls `INC-DEMO-A`. The diagnosis cites `INC-DEMO-A` and leverages its past resolution.

3. **Incident C (False Match Avoidance — `INC-DEMO-C`):**
   - Select `INC-DEMO-C` ("Message queue processing timeout on auth topic").
   - Diagnose: Superficially resembles consumer lag, but root cause is authentication service failure. Continuum explicitly avoids false-matching to `INC-DEMO-A`.

---

## ⚡ Performance & Benchmarks (NFR-2)

- **Hindsight Recall Latency:** ~0.6s–0.8s (using `budget="low"` + connection pooling)
- **Groq Inference Latency:** ~1.2s–2.0s
- **End-to-End Pipeline Latency:** ~3.6s–4.0s (under target thresholds for real-time cloud API integration)

---

## 🛡️ License & Acknowledgments
Built for HackwithHyderabad 3.0. Powered by **Hindsight Cloud** and **Groq**.
