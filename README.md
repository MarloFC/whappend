# WhAppend

AI-powered video analysis — timestamped event timeline with LLM Q&A.

## Structure

```
whappend/
├── backend/     FastAPI + Python AI services
└── frontend/    Next.js 14
```

## Quick Start

### 1. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate       # Windows
pip install -r requirements.txt
cp .env.example .env         # Fill in OPENAI_API_KEY
uvicorn main:app --reload --port 8000
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev                  # http://localhost:3000
```

## Stack

| Layer | Tech |
|---|---|
| Frontend | Next.js 14 (App Router), TypeScript |
| Backend | FastAPI, Python 3.11+ |
| Frame extraction | OpenCV |
| Audio transcription | OpenAI Whisper |
| Vision analysis | GPT-4o (batched frames) |
| Vector store | ChromaDB |
| LLM Q&A | GPT-4o-mini + LangChain |
| Embeddings | text-embedding-3-small |
