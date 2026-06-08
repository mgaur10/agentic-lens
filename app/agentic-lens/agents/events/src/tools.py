"""Vertex RAG tool for the Events agent — retrieve context from the Managed RAG Corpus."""

from vertexai.preview import rag

# Managed RAG Corpus (events) — us-west1
_CORPUS_NAME = "projects/agentic-prism/locations/us-west1/ragCorpora/2305843009213693952"
_RAG_PROJECT = "agentic-prism"
_RAG_LOCATION = "us-west1"


def retrieve_event_info(query: str) -> str:
    """Retrieve relevant event information from the Managed RAG Corpus.

    Args:
        query: Natural language question or topic to look up in the corpus.

    Returns:
        Concatenated text from the top retrieved contexts, or a fallback message
        if retrieval fails or returns no contexts.
    """
    try:
        try:
            import vertexai
            from vertexai.preview import rag
            vertexai.init(project=_RAG_PROJECT, location=_RAG_LOCATION)
        except Exception as e:
            print(f"ERROR: RAG Init failed: {e}")
            return f"No relevant information found. (System Error: Init failed: {e})"

        try:
            resource = rag.RagResource(rag_corpus=_CORPUS_NAME)
            response = rag.retrieval_query(
                text=query,
                rag_resources=[resource],
                similarity_top_k=5,
                vector_distance_threshold=0.5,
            )
        except Exception as e:
            print(f"ERROR: RAG Retrieval failed: {e}")
            return f"No relevant information found. (System Error: Retrieval failed: {e})"

        if not response or not response.contexts or not response.contexts.contexts:
            return "No relevant information found in the corpus."

        parts = [ctx.text for ctx in response.contexts.contexts if ctx.text]
        if not parts:
            return "No relevant information found in the corpus."

        return "\n\n".join(parts)
        
    except Exception as e:
        print(f"CRITICAL ERROR in retrieve_event_info: {e}")
        return f"No relevant information found. (Critical Error: {e})"
