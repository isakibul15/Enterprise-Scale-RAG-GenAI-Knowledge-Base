"""
Prompt templates for the RAG pipeline.

Two prompts work in tandem:
  1. CONDENSE_PROMPT  — rewrites a follow-up question into a standalone question
                        using chat history so the retriever always gets a
                        self-contained query.

  2. QA_PROMPT        — the anti-hallucination answer prompt. It instructs the
                        model to answer ONLY from the supplied context, cite
                        sources, and admit ignorance rather than fabricate.

Design notes
------------
• temperature=0 on the LLM is not sufficient on its own — the prompt must
  explicitly forbid fabrication and define an "I don't know" escape hatch.
• Sources are formatted inline (filename + page) so the model can reference
  them naturally in its answer.
• The QA system prompt intentionally separates RULES from CONTEXT so that
  the model cannot easily confuse instructions with document content.
"""

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.documents import Document
from typing import List

# ---------------------------------------------------------------------------
# 1. Condense / history-aware retrieval prompt
# ---------------------------------------------------------------------------

_CONDENSE_SYSTEM = """\
You are a query reformulation assistant.

Given the conversation history and the user's latest message, rewrite the \
message into a single, self-contained search query that captures all relevant \
context from the history.

Rules:
- Output ONLY the reformulated query — no explanation, no preamble.
- If the latest message is already self-contained, output it unchanged.
- Preserve technical terms, proper nouns, and acronyms exactly.
- Do not answer the question; only reformulate it.\
"""

CONDENSE_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", _CONDENSE_SYSTEM),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
    ]
)

# ---------------------------------------------------------------------------
# 2. Anti-hallucination QA prompt
# ---------------------------------------------------------------------------

_QA_SYSTEM = """\
You are a precise, trustworthy assistant for an enterprise knowledge base. \
Your answers are grounded exclusively in the document excerpts supplied in \
the CONTEXT block below.

━━━━━━━━━━━━━━━━━━━━━━  RULES  ━━━━━━━━━━━━━━━━━━━━━━
1. USE ONLY THE PROVIDED CONTEXT. Do not draw on prior training knowledge, \
general world knowledge, or information not present in the excerpts.

2. IF THE CONTEXT IS INSUFFICIENT, respond with exactly:
   "I don't have enough information in the provided documents to answer \
this question."
   Do not speculate, extrapolate, or guess.

3. NEVER fabricate facts, statistics, dates, names, URLs, or citations \
that do not appear verbatim in the context.

4. CITE YOUR SOURCES inline using the format [Source: <filename>, p.<page>] \
immediately after each factual claim. If no page number is available, \
omit the page part.

5. CONFLICTING INFORMATION: if excerpts contradict each other, note the \
conflict and present both viewpoints with their respective sources.

6. Be concise. Prefer bullet points for lists of facts. Avoid padding.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CONTEXT:
{context}
"""

QA_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", _QA_SYSTEM),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
    ]
)


# ---------------------------------------------------------------------------
# Context formatter — converts retrieved Documents into the {context} string
# ---------------------------------------------------------------------------

def format_retrieved_docs(docs: List[Document]) -> str:
    """
    Render a list of LangChain Documents into a numbered context block.

    Each excerpt carries its source path and page number so the model can
    produce accurate citations. An empty list renders a sentinel string that
    triggers the "insufficient context" path in the QA prompt.

    Args:
        docs: List of retrieved Document objects with metadata

    Returns:
        Formatted context string with numbered entries and source citations
    """
    if not docs:
        return "[No relevant documents were retrieved for this query.]"

    parts: list[str] = []
    for i, doc in enumerate(docs, start=1):
        meta = doc.metadata
        file_name = meta.get("file_name", meta.get("source", "unknown"))
        page = meta.get("page", meta.get("chunk_index", ""))
        page_str = f", p.{page}" if page != "" else ""
        header = f"[{i}] Source: {file_name}{page_str}"
        parts.append(f"{header}\n{doc.page_content.strip()}")

    return "\n\n---\n\n".join(parts)
