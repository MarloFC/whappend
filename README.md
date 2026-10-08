# WhAppend

Multimodal Intelligence Platform — timestamped event detection, AI chapters, and reasoning for **Videos, Audio, and Images** powered by Groq and LangChain.

## ✨ Features

- 🎥 **Full Video Intelligence**: OpenCV frame sampling, collage vision analysis, Groq Whisper transcription, and timeline alignment.
- 🎙️ **Audio Speech Intelligence**: Whisper transcription with speech chunking and speaker timestamp markers.
- 🖼️ **Image Intelligence**: Vision scene analysis, detected objects, and visible text/OCR extraction.
- 🔑 **Bring Your Own Key (BYOK)**: Optional client-side Groq API key configuration saved securely in `localStorage` without backend persistence.
- 🦜 **LangChain Ecosystem**:
  1. **Multi-Turn Conversational Memory**: Chat with the media naturally while the system retains full context across follow-up questions.
  2. **AI Video Agent with Tool Calling**: Toggle *Agent Mode* to let the model invoke tools (`search_video_events`, `get_video_statistics`, `inspect_event_details`) for complex reasoning.
  3. **Automatic Video Chapters & Structured Summary**: LangChain Pydantic structured output generates labeled video chapters with timestamps and topic tags.
  4. **Multi-Query RAG Retrieval**: Expands user questions into multiple query angles to maximize vector recall in ChromaDB.

## 📂 Project Structure

```
whappend/
├── backend/
│   ├── main.py
│   ├── config.py
│   ├── store.py
│   ├── models/schemas.py
│   ├── routers/ (upload, videos, ask)
│   └── services/
│       ├── vision_service.py
│       ├── audio_service.py
│       ├── rag_service.py
│       └── langchain_service.py   # LangChain memory, agent, chapters & multi-query
└── frontend/
    ├── src/
    │   ├── app/ (page.tsx, globals.css)
    │   ├── components/ (MediaViewer, ChaptersView, ChatPanel, ApiKeyModal, etc.)
    │   └── lib/ (api.ts, types.ts, utils.ts)
```

## 🚀 Quick Start

### 1. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows
pip install -r requirements.txt
cp .env.example .env              # Set GROQ_API_KEY (or supply it in the frontend UI)
uvicorn main:app --reload --port 8000
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev                       # http://localhost:3000
```

## 🛠️ Stack

| Layer | Tech |
|---|---|
| Frontend | Next.js 16 (App Router), TypeScript, Vanilla CSS |
| Backend | FastAPI, Python 3.11+ |
| Orchestration & Agents | **LangChain**, **LangChain-Groq**, **LangGraph** |
| LLM & Vision Inference | **Groq LPU** (`qwen/qwen-2.5-32b`, `llama-3.3-70b-versatile`) |
| Speech-to-Text | **Groq Whisper** (`whisper-large-v3-turbo`) |
| Frame Extraction | OpenCV |
| Vector Store | ChromaDB |
| Embeddings | ChromaDB default sentence embeddings |
