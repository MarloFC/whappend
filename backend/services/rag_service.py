"""
RAG service.
Embeddings: local sentence-transformers (free) or OpenAI.
LLM Q&A: Groq (free) or OpenAI.
"""

import os
os.environ["ANONYMIZED_TELEMETRY"] = "False"

import json
import math
import re
from collections import Counter
from typing import Optional

from config import settings
from models.schemas import TimelineEvent, QuestionResponse, ChatMessage
from services.langchain_service import (
    answer_with_conversational_memory,
    generate_multi_query,
    run_video_agent,
)


# ─── Lightweight In-Memory Hybrid BM25 + Token-Overlap Ranker (<1 MB RAM) ─────

_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "in", "on", "at", "to", "for",
    "of", "and", "or", "what", "when", "where", "who", "how", "why", "did", "do",
    "does", "happened", "happens", "video", "audio", "image", "show", "tell",
}


def _tokenize(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if w not in _STOPWORDS and len(w) > 1]


def _rank_events_lightweight(
    queries: list[str],
    all_events: list[TimelineEvent],
    top_k: int = 6,
) -> list[TimelineEvent]:
    """
    Ranks timeline events against multi-query expansions using BM25-style IDF +
    exact substring match boosting. Uses <1 MB RAM (fits easily on Render 512MB tier)
    and needs no persistent disk state across restarts.
    """
    if not all_events:
        return []
    if len(all_events) <= top_k:
        return sorted(all_events, key=lambda e: e.timestamp)

    n_docs = len(all_events)
    doc_tokens: list[list[str]] = []
    df: Counter = Counter()

    for ev in all_events:
        toks = _tokenize(f"{ev.event_type.value} {ev.description}")
        doc_tokens.append(toks)
        for unique_tok in set(toks):
            df[unique_tok] += 1

    avg_dl = max(1.0, sum(len(t) for t in doc_tokens) / n_docs)
    k1, b = 1.5, 0.75

    query_tok_sets = [_tokenize(q) for q in queries if q]
    all_query_tokens = [tok for qset in query_tok_sets for tok in qset]

    scores: list[tuple[float, int]] = []
    for idx, ev in enumerate(all_events):
        toks = doc_tokens[idx]
        tf = Counter(toks)
        dl = len(toks)
        score = 0.0
        for qtok in all_query_tokens:
            if qtok in tf:
                idf = math.log(1.0 + (n_docs - df[qtok] + 0.5) / (df[qtok] + 0.5))
                freq = tf[qtok]
                score += idf * (freq * (k1 + 1.0)) / (freq + k1 * (1.0 - b + b * dl / avg_dl))
        scores.append((score, idx))

    scores.sort(key=lambda item: item[0], reverse=True)
    best_indices = [idx for sc, idx in scores[:top_k] if sc > 0]

    if not best_indices:
        # Evenly sample across the timeline if query is broad (e.g. "summarize the video")
        step = max(1, len(all_events) // top_k)
        best_indices = list(range(0, len(all_events), step))[:top_k]

    selected = [all_events[i] for i in best_indices]
    selected.sort(key=lambda e: e.timestamp)
    return selected


# ─── Indexing ──────────────────────────────────────────────────────────────────

def index_events(video_id: str, events: list[TimelineEvent], user_id: Optional[str] = None) -> None:
    """
    Events are persisted in Postgres/SQLite JSONB via `store.save_events`.
    If `EMBEDDING_PROVIDER=chromadb` is explicitly set (for high-RAM machines), also indexes into ChromaDB.
    """
    if not events:
        return
    if settings.embedding_provider != "chromadb":
        print(f"[RAGService] Ready {len(events)} events for video {video_id} (lightweight hybrid ranker).")
        return

    import chromadb
    from chromadb.utils import embedding_functions

    client = chromadb.PersistentClient(path=str(settings.chroma_dir))
    ef = embedding_functions.DefaultEmbeddingFunction()
    col_name = f"video_{video_id.replace('-', '_')}"
    try:
        client.delete_collection(col_name)
    except Exception:
        pass
    collection = client.create_collection(name=col_name, embedding_function=ef)
    documents, metadatas, ids = [], [], []
    for event in events:
        documents.append(f"[{event.timestamp:.1f}s] {event.event_type.value}: {event.description}")
        meta = {
            "event_id": event.id,
            "timestamp": event.timestamp,
            "modality": event.modality,
            "event_type": event.event_type.value,
            "confidence": event.confidence,
        }
        if user_id:
            meta["user_id"] = user_id
        metadatas.append(meta)
        ids.append(event.id)
    collection.add(documents=documents, metadatas=metadatas, ids=ids)
    print(f"[RAGService] Indexed {len(documents)} events in ChromaDB for video {video_id}.")


# ─── LLM answer (Gemini, OpenAI, Groq, or Local Summary) ────────────────────

def _call_llm(context: str, question: str, groq_api_key: Optional[str] = None) -> str:
    system = (
        "You are a helpful video analysis assistant. "
        "Answer questions about the video using ONLY the provided event timeline. "
        "Be concise and reference timestamps when relevant."
    )
    user = f"Video event timeline (relevant excerpts):\n{context}\n\nQuestion: {question}"

    effective_groq = (groq_api_key or "").strip()
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
    if not all_events:
        return QuestionResponse(
            answer="No events found to answer from.",
            relevant_events=[],
            video_id=video_id,
            used_agent=False,
        )

    # Generate 3 multi-query perspectives to boost recall
    queries = generate_multi_query(question, groq_api_key=groq_api_key)
    if question not in queries:
        queries = [question] + list(queries)

    relevant_events = _rank_events_lightweight(queries=queries, all_events=all_events, top_k=top_k)

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
