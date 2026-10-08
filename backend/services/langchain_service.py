"""
WhAppend LangChain Service.
Implements 4 core LangChain features:
1. Conversational Memory (LCEL + ChatPromptTemplate with MessagesPlaceholder)
2. Multi-Query RAG generation (expands user prompt to maximize retrieval recall)
3. Automatic Video Chapters & Structured Summary (Structured Outputs)
4. AI Video Agent with Custom Tools (Tool Calling with ChatGroq)
"""

import json
from typing import Optional
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.tools import tool
from langchain_groq import ChatGroq

from config import settings
from models.schemas import (
    TimelineEvent,
    ChatMessage,
    Chapter,
    ChaptersResponse,
)


def _get_llm(groq_api_key: Optional[str] = None, temperature: float = 0.2) -> Optional[ChatGroq]:
    """Instantiates ChatGroq with user-provided key or server default."""
    effective_key = groq_api_key or settings.groq_api_key
    if not effective_key:
        return None
    return ChatGroq(
        model=settings.groq_llm_model,
        api_key=effective_key,
        temperature=temperature,
        max_tokens=600,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 1: Conversational Memory (Multi-Turn Chat)
# ═══════════════════════════════════════════════════════════════════════════════

def answer_with_conversational_memory(
    context: str,
    question: str,
    history: Optional[list[ChatMessage]] = None,
    groq_api_key: Optional[str] = None,
) -> str:
    """
    Answers user questions using LangChain's LCEL chain with historical context.
    Allows natural follow-ups ('What happened after that?', 'What was in his hand?').
    """
    llm = _get_llm(groq_api_key=groq_api_key, temperature=0.2)
    if not llm:
        return f"Based on the timeline:\n\n{context}"

    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            "You are WhAppend, an expert AI video and media analyst assistant.\n"
            "Answer the user's questions strictly and factually based on the provided event timeline.\n"
            "Reference exact timestamps (e.g., [02.4s]) whenever relevant.\n"
            "If the information is not present in the timeline, state so clearly.\n\n"
            "Video Event Timeline Excerpts:\n{context}"
        ),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{question}"),
    ])

    chain = prompt | llm | StrOutputParser()

    # Convert incoming ChatMessage schemas to LangChain message objects
    formatted_history = []
    if history:
        for msg in history[-8:]:  # keep the last 8 messages for token budget
            if msg.role.lower() == "user":
                formatted_history.append(HumanMessage(content=msg.content))
            else:
                formatted_history.append(AIMessage(content=msg.content))

    try:
        response = chain.invoke({
            "context": context,
            "chat_history": formatted_history,
            "question": question,
        })
        return response.strip()
    except Exception as e:
        print(f"[LangChainService] Conversational memory error: {e}")
        # Fallback to direct prompt
        return f"Based on the timeline:\n\n{context}\n\n(Note: {e})"


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 4: Multi-Query RAG (Retrieval Augmentation)
# ═══════════════════════════════════════════════════════════════════════════════

def generate_multi_query(
    question: str,
    groq_api_key: Optional[str] = None,
) -> list[str]:
    """
    Expands a single user question into 3 semantic perspectives (e.g. actions,
    dialogue, visual objects) to increase vector database recall.
    """
    llm = _get_llm(groq_api_key=groq_api_key, temperature=0.4)
    if not llm:
        return [question]

    multi_prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            "You are an AI assistant designed to optimize search queries for video timeline events.\n"
            "Given a user query, output 3 different search versions from different angles:\n"
            "1. Physical actions and visual scene changes\n"
            "2. Spoken dialogue and sound cues\n"
            "3. Objects, people, and locations\n"
            "Return ONLY the 3 queries, one per line. Do not number them or add bullet points."
        ),
        ("human", "{question}"),
    ])

    chain = multi_prompt | llm | StrOutputParser()

    try:
        raw = chain.invoke({"question": question})
        lines = [line.strip().lstrip("123456789.-* ") for line in raw.split("\n") if line.strip()]
        unique_queries = [question]
        for l in lines:
            if l and l not in unique_queries:
                unique_queries.append(l)
        return unique_queries[:3]
    except Exception as e:
        print(f"[LangChainService] Multi-query generation fallback: {e}")
        return [question]


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 3: Automatic Video Chapters & Structured Summary
# ═══════════════════════════════════════════════════════════════════════════════

def generate_video_chapters(
    video_id: str,
    events: list[TimelineEvent],
    duration_seconds: Optional[float] = None,
    groq_api_key: Optional[str] = None,
) -> ChaptersResponse:
    """
    Synthesizes the entire media timeline into structured chapters with
    titles, summaries, and key topics using LangChain structured output.
    """
    if not events:
        return ChaptersResponse(
            video_id=video_id,
            overview="No timeline events available to generate chapters.",
            chapters=[],
        )

    llm = _get_llm(groq_api_key=groq_api_key, temperature=0.1)
    if not llm:
        # Simple rule-based chapters fallback
        return _fallback_chapters(video_id, events, duration_seconds)

    # Format event excerpts (capped to prevent token explosion)
    sampled = events if len(events) <= 40 else events[:: len(events) // 30]
    timeline_text = "\n".join(
        f"[{e.timestamp:.1f}s] ({e.event_type.value}) {e.description}"
        for e in sampled
    )

    try:
        structured_llm = llm.with_structured_output(ChaptersResponse)
        prompt = (
            f"Media Duration: {duration_seconds or events[-1].timestamp:.1f}s\n"
            f"Here is the chronological event timeline of the media:\n\n{timeline_text}\n\n"
            "Organize this media into 3 to 6 chronological chapters. "
            "For each chapter, provide start_time, end_time, an engaging title, a concise summary, and 2-3 key topics."
        )
        result: ChaptersResponse = structured_llm.invoke(prompt)
        result.video_id = video_id
        return result
    except Exception as e:
        print(f"[LangChainService] Structured chapters failed ({e}), using fallback.")
        return _fallback_chapters(video_id, events, duration_seconds)


def _fallback_chapters(
    video_id: str,
    events: list[TimelineEvent],
    duration_seconds: Optional[float],
) -> ChaptersResponse:
    """Heuristic chapter grouping fallback."""
    if not events:
        return ChaptersResponse(video_id=video_id, overview="Empty media.", chapters=[])

    total_duration = duration_seconds or events[-1].timestamp or 1.0
    num_chapters = min(4, max(1, len(events) // 4))
    chunk_size = total_duration / num_chapters

    chapters = []
    for i in range(num_chapters):
        start = round(i * chunk_size, 1)
        end = round(min(total_duration, (i + 1) * chunk_size), 1)
        sub_events = [e for e in events if start <= e.timestamp <= end]
        desc = "; ".join(e.description[:50] for e in sub_events[:2]) or "Media segment"
        chapters.append(Chapter(
            start_time=start,
            end_time=end,
            title=f"Segment {i + 1}: {start}s - {end}s",
            summary=desc,
            key_topics=["events", "analysis"],
        ))

    return ChaptersResponse(
        video_id=video_id,
        overview="Generated automatic chronological chapter overview.",
        chapters=chapters,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 2: AI Video Agent with Custom Tools
# ═══════════════════════════════════════════════════════════════════════════════

def run_video_agent(
    video_id: str,
    question: str,
    events: list[TimelineEvent],
    history: Optional[list[ChatMessage]] = None,
    groq_api_key: Optional[str] = None,
) -> tuple[str, list[TimelineEvent]]:
    """
    Executes a LangChain Tool-Calling Agent. The agent inspects the question,
    calls targeted inspection tools (visual search, audio search, timeline stats),
    and aggregates multi-hop evidence to answer complex queries.
    """
    llm = _get_llm(groq_api_key=groq_api_key, temperature=0.1)
    if not llm or not events:
        return (
            "Agent mode requires an active Groq API key and processed events.",
            events[:3] if events else [],
        )

    # ── Define Agent Tools bound to this video's events ───────────────────────
    collected_events: list[TimelineEvent] = []

    @tool
    def search_visual_events(query: str) -> str:
        """Search the video for visual actions, scene changes, people, and detected objects."""
        matches = [e for e in events if e.modality in ["visual", "merged"] and any(
            word.lower() in e.description.lower() for word in query.split()
        )]
        selected = matches[:6] if matches else events[:3]
        collected_events.extend(selected)
        return "\n".join(f"[{e.timestamp:.1f}s] {e.description}" for e in selected) or "No visual matches."

    @tool
    def search_spoken_dialogue(query: str) -> str:
        """Search spoken speech and dialogue transcribed by Groq Whisper."""
        matches = [e for e in events if e.modality in ["audio", "merged"] and any(
            word.lower() in e.description.lower() for word in query.split()
        )]
        selected = matches[:6] if matches else [e for e in events if e.modality in ["audio", "merged"]][:3]
        collected_events.extend(selected)
        return "\n".join(f"[{e.timestamp:.1f}s] {e.description}" for e in selected) or "No dialogue matches."

    @tool
    def get_media_statistics() -> str:
        """Returns metadata stats about the video: total event counts, visual count, speech count, duration."""
        visual_count = sum(1 for e in events if e.modality in ["visual", "merged"])
        audio_count = sum(1 for e in events if e.modality in ["audio", "merged"])
        max_time = max((e.timestamp for e in events), default=0.0)
        return (
            f"Total events: {len(events)}, Visual events: {visual_count}, "
            f"Spoken segments: {audio_count}, Latest timestamp: {max_time:.1f}s"
        )

    tools = [search_visual_events, search_spoken_dialogue, get_media_statistics]
    tool_map = {t.name: t for t in tools}

    # Bind tools to the model
    llm_with_tools = llm.bind_tools(tools)

    system_instruction = (
        "You are WhAppend AI Agent, an autonomous video and media investigator.\n"
        "You have access to tools to search visual actions, spoken dialogue, and video statistics.\n"
        "Use your tools to find exact facts before answering. Cite timestamps in square brackets [00.0s].\n"
        "If the tools provide the answer, synthesize a clear final response."
    )

    messages = [SystemMessage(content=system_instruction)]
    if history:
        for m in history[-4:]:
            if m.role.lower() == "user":
                messages.append(HumanMessage(content=m.content))
            else:
                messages.append(AIMessage(content=m.content))
    messages.append(HumanMessage(content=question))

    # Tool calling loop (max 3 turns)
    for _ in range(3):
        try:
            ai_msg = llm_with_tools.invoke(messages)
            messages.append(ai_msg)

            if not ai_msg.tool_calls:
                # Finished reasoning
                deduped_events = []
                seen_ids = set()
                for e in collected_events:
                    if e.id not in seen_ids:
                        seen_ids.add(e.id)
                        deduped_events.append(e)
                return str(ai_msg.content), deduped_events

            # Execute tool calls
            for tc in ai_msg.tool_calls:
                selected_tool = tool_map.get(tc["name"])
                if selected_tool:
                    tool_output = selected_tool.invoke(tc["args"])
                else:
                    tool_output = f"Tool {tc['name']} not found."
                messages.append(ToolMessage(content=str(tool_output), tool_call_id=tc["id"]))
        except Exception as e:
            print(f"[LangChainService] Agent tool calling step error: {e}")
            break

    # Final fallback synthesis if loop ends with tool messages
    try:
        final_response = llm.invoke(messages)
        return str(final_response.content), collected_events
    except Exception as e:
        return f"Agent analysis completed. Found relevant events.", collected_events
