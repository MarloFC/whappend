"""
RAG service.
Embeddings: local sentence-transformers (free) or OpenAI.
LLM Q&A: Groq (free) or OpenAI.
"""

import os
os.environ["ANONYMIZED_TELEMETRY"] = "False"
try:
    from chromadb.telemetry.product.posthog import Posthog
    Posthog.capture = lambda self, event: None
except Exception:
    pass

import json
from typing import Optional
import chromadb
from chromadb import Documents, EmbeddingFunction, Embeddings

from config import settings
from models.schemas import TimelineEvent, QuestionResponse, ChatMessage
from services.langchain_service import (
    answer_with_conversational_memory,
    generate_multi_query,
    run_video_agent,
)

# ─── Embedding functions ───────────────────────────────────────────────────────

class LocalEmbeddingFunction(EmbeddingFunction):
    """Uses sentence-transformers locally — completely free, no API key."""

    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer
        print(f"[RAGService] Loading local embedding model '{model_name}'…")
        self._model = SentenceTransformer(model_name)
        print("[RAGService] Embedding model loaded.")

    def __call__(self, input: Documents) -> Embeddings:
        embeddings = self._model.encode(list(input), convert_to_numpy=True)
        return embeddings.tolist()


def _get_embedding_function():
    if settings.embedding_provider == "openai":
        from chromadb.utils import embedding_functions
        return embedding_functions.OpenAIEmbeddingFunction(
            api_key=settings.openai_api_key,
            model_name=settings.openai_embedding_model,
        )
    # Default: local sentence-transformers
    return LocalEmbeddingFunction(settings.local_embedding_model)


# ─── ChromaDB client (singleton) ──────────────────────────────────────────────

_chroma_client = None
_embedding_fn = None


def _get_chroma():
    global _chroma_client, _embedding_fn
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(
            path=str(settings.chroma_dir),
            settings=chromadb.config.Settings(anonymized_telemetry=False)
        )
        _embedding_fn = _get_embedding_function()
    return _chroma_client, _embedding_fn


def _collection_name(video_id: str) -> str:
    return f"video_{video_id.replace('-', '_')}"


# ─── Indexing ──────────────────────────────────────────────────────────────────

def index_events(video_id: str, events: list[TimelineEvent]) -> None:
    """Embed and store all timeline events for a video into ChromaDB."""
    if not events:
        return

    client, ef = _get_chroma()
    col_name = _collection_name(video_id)

    try:
        client.delete_collection(col_name)
    except Exception:
        pass

    collection = client.create_collection(name=col_name, embedding_function=ef)

    documents, metadatas, ids = [], [], []
    for event in events:
        doc = f"[{event.timestamp:.1f}s] {event.event_type.value}: {event.description}"
        documents.append(doc)
        metadatas.append({
            "event_id": event.id,
            "timestamp": event.timestamp,
            "modality": event.modality,
            "event_type": event.event_type.value,
            "confidence": event.confidence,
        })
        ids.append(event.id)

    collection.add(documents=documents, metadatas=metadatas, ids=ids)
    print(f"[RAGService] Indexed {len(documents)} events for video {video_id}.")


# ─── LLM answer (Gemini, OpenAI, Groq, or Local Summary) ────────────────────

def _call_llm(context: str, question: str, groq_api_key: Optional[str] = None) -> str:
    system = (
        "You are a helpful video analysis assistant. "
        "Answer questions about the video using ONLY the provided event timeline. "
        "Be concise and reference timestamps when relevant."
    )
    user = f"Video event timeline (relevant excerpts):\n{context}\n\nQuestion: {question}"

    effective_groq = groq_api_key or settings.groq_api_key
    provider = (settings.llm_provider or "").lower()

    if (provider == "groq" or effective_groq) and effective_groq:
        try:
            from groq import Groq
            client = Groq(api_key=effective_groq)
            resp = client.chat.completions.create(
                model=settings.groq_llm_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=500,
                temperature=0.2,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            print(f"[RAGService] Groq call notice with {settings.groq_llm_model}: {e}")
            try:
                resp = client.chat.completions.create(
                    model="qwen/qwen3.8-27b",
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    max_tokens=400,
                    temperature=0.2,
                )
                return resp.choices[0].message.content.strip()
            except Exception as e2:
                print(f"[RAGService] Groq fallback notice: {e2}")

    gemini_key = getattr(settings, "gemini_api_key", "")
    if (provider == "gemini" or gemini_key) and gemini_key:
        try:
            from google import genai
            client = genai.Client(api_key=gemini_key)
            resp = client.models.generate_content(
                model=getattr(settings, "gemini_llm_model", "gemini-2.0-flash"),
                contents=f"{system}\n\n{user}"
            )
            if resp.text:
                return resp.text.strip()
        except Exception as e:
            print(f"[RAGService] Gemini call notice: {e}")

    # Fallback to direct event timeline extract when no cloud LLM API key is present
    return f"Based on the video event timeline:\n\n{context}"



# ─── Mock Q&A ─────────────────────────────────────────────────────────────────

def _mock_answer(question: str, events: list[TimelineEvent]) -> str:
    sample = events[:3]
    lines = [f"At {e.timestamp:.1f}s: {e.description}" for e in sample]
    return (
        f"[MOCK MODE] Based on the timeline, here's what happened:\n"
        + "\n".join(lines)
        + f"\n\nYour question was: \"{question}\""
    )


# ─── Public API ───────────────────────────────────────────────────────────────

def answer_question(
    video_id: str,
    question: str,
    all_events: list[TimelineEvent],
    top_k: int = 6,
    groq_api_key: Optional[str] = None,
    history: Optional[list[ChatMessage]] = None,
    use_agent: bool = False,
) -> QuestionResponse:
    if settings.mock_mode:
        relevant = sorted(all_events, key=lambda e: e.timestamp)[:top_k]
        return QuestionResponse(
            answer=_mock_answer(question, relevant),
            relevant_events=relevant,
            video_id=video_id,
            used_agent=use_agent,
        )

    # ── Option A: AI Agent Mode with Tool Calling ─────────────────────────────
    if use_agent:
        agent_answer, agent_events = run_video_agent(
            video_id=video_id,
            question=question,
            events=all_events,
            history=history,
            groq_api_key=groq_api_key,
        )
        return QuestionResponse(
            answer=agent_answer,
            relevant_events=agent_events or all_events[:4],
            video_id=video_id,
            used_agent=True,
        )

    # ── Option B: LangChain Multi-Query + Conversational Memory RAG ───────────
    client, ef = _get_chroma()
    col_name = _collection_name(video_id)
    collection = client.get_collection(name=col_name, embedding_function=ef)

    total_count = collection.count()
    if total_count == 0:
        return QuestionResponse(
            answer="No events found to answer from.",
            relevant_events=[],
            video_id=video_id,
            used_agent=False,
        )

    # Generate 3 multi-query perspectives to boost recall
    queries = generate_multi_query(question, groq_api_key=groq_api_key)

    retrieved_ids = set()
    per_query_n = max(2, min(4, total_count))
    for q in queries:
        try:
            res = collection.query(query_texts=[q], n_results=per_query_n)
            for doc_id in res["ids"][0]:
                retrieved_ids.add(doc_id)
        except Exception:
            pass

    if not retrieved_ids:
        # Fallback to single original query
        res = collection.query(query_texts=[question], n_results=min(top_k, total_count))
        retrieved_ids = set(res["ids"][0])

    relevant_events = [e for e in all_events if e.id in retrieved_ids]
    relevant_events.sort(key=lambda e: e.timestamp)

    context = "\n".join(
        f"[{e.timestamp:.1f}s] ({e.event_type.value}) {e.description}"
        for e in relevant_events
    )

    # Answer using LangChain Conversational Memory Chain
    answer = answer_with_conversational_memory(
        context=context,
        question=question,
        history=history,
        groq_api_key=groq_api_key,
    )

    return QuestionResponse(
        answer=answer,
        relevant_events=relevant_events,
        video_id=video_id,
        used_agent=False,
    )
