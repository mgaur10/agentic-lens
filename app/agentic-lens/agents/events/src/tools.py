"""Vertex RAG tool for the Events agent — retrieve context from the Managed RAG Corpus."""
import os
from vertexai.preview import rag

# Use PRD RAG corpus cross-project (no QA corpus exists)
_CORPUS_NAME = os.environ.get(
    "RAG_CORPUS_NAME",
    "projects/agentic-prism/locations/us-west1/ragCorpora/2305843009213693952"
)
_RAG_PROJECT = os.environ.get("RAG_PROJECT", "agentic-prism")
_RAG_LOCATION = os.environ.get("RAG_LOCATION", "us-west1")


def retrieve_event_info(query: str) -> str:
    """
    Retrieve event information from the Managed RAG Corpus.

    Args:
        query: The question about the event (schedule, venue, speakers, etc.)

    Returns:
        str: Retrieved context from the RAG corpus.
    """
    try:
        rag_resource = rag.RagResource(rag_corpus=_CORPUS_NAME)
        response = rag.retrieval_query(
            rag_resources=[rag_resource],
            text=query,
            similarity_top_k=5,
            vector_distance_threshold=0.5,
        )
        contexts = []
        for ctx in response.contexts.contexts:
            contexts.append(ctx.text)
        if contexts:
            return "\n\n".join(contexts)
        return "No relevant event information found for your query."
    except Exception as e:
        return f"Unable to retrieve event information: {e}"
