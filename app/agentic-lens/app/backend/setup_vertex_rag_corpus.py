"""
Vertex AI RAG corpus bootstrap (Managed RAG Corpus).

Creates a `ragCorpora/{corpus_id}` resource and imports documents from a GCS
bucket/prefix (e.g. PDFs, DOCX, PPTX, etc.).

This is intended for the Events concierge, but it’s reusable.
"""

from __future__ import annotations

import argparse
import os
from typing import Optional

import vertexai
from dotenv import load_dotenv
from vertexai.preview import rag

load_dotenv()


def _env(name: str, default: Optional[str] = None) -> str:
    val = (os.getenv(name) or default or "").strip()
    return val


def _build_corpus_name(*, project_id: str, location: str, corpus_id: str) -> str:
    if not project_id or not location or not corpus_id:
        raise ValueError(
            "Missing required values to build RagCorpus name: "
            f"project_id={project_id!r}, location={location!r}, corpus_id={corpus_id!r}"
        )
    return f"projects/{project_id}/locations/{location}/ragCorpora/{corpus_id}"


def _get_existing_corpus(corpus_name: str) -> bool:
    try:
        _ = rag.get_corpus(corpus_name)
        return True
    except Exception:
        return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", default=_env("VERTEX_RAG_PROJECT_ID", _env("GCP_PROJECT_ID")))
    parser.add_argument("--location", default=_env("VERTEX_RAG_LOCATION", _env("GCP_LOCATION", "us-west1")))
    parser.add_argument("--corpus-id", default=_env("VERTEX_RAG_CORPUS_ID"))
    parser.add_argument("--display-name", default=_env("VERTEX_RAG_DISPLAY_NAME", "agentic-lens-events-rag"))
    parser.add_argument("--description", default=_env("VERTEX_RAG_DESCRIPTION", "Managed RAG corpus for Concierge Events"))
    parser.add_argument(
        "--gcs-uri",
        default=_env("VERTEX_RAG_GCS_PATH"),
        help="GCS URI to import from, e.g. gs://my-bucket/events-docs/ (directory/prefix).",
    )
    parser.add_argument("--chunk-size", type=int, default=int(_env("VERTEX_RAG_CHUNK_SIZE", "1024")))
    parser.add_argument("--chunk-overlap", type=int, default=int(_env("VERTEX_RAG_CHUNK_OVERLAP", "200")))
    parser.add_argument("--use-advanced-pdf-parsing", action="store_true", default=_env("VERTEX_RAG_USE_ADVANCED_PDF_PARSING", "false").lower() == "true")
    parser.add_argument("--timeout", type=int, default=int(_env("VERTEX_RAG_IMPORT_TIMEOUT", "600")))
    parser.add_argument("--recreate", action="store_true", default=_env("VERTEX_RAG_RECREATE", "false").lower() == "true")
    parser.add_argument(
        "--skip-import",
        action="store_true",
        default=_env("VERTEX_RAG_SKIP_IMPORT", "false").lower() == "true",
        help="Create the RagCorpus but do not import/index any files.",
    )
    args = parser.parse_args()

    if not args.project_id:
        raise SystemExit("Missing --project-id or env VERTEX_RAG_PROJECT_ID / GCP_PROJECT_ID")
    if not args.corpus_id and not _env("VERTEX_RAG_CORPUS_NAME"):
        raise SystemExit(
            "Missing --corpus-id or env VERTEX_RAG_CORPUS_ID "
            "(or set VERTEX_RAG_CORPUS_NAME to the full ragCorpora resource name)."
        )
    if not args.skip_import and not args.gcs_uri:
        raise SystemExit(
            "Missing --gcs-uri or env VERTEX_RAG_GCS_PATH (e.g. gs://bucket/prefix). "
            "Or set --skip-import to only create the RagCorpus."
        )

    # Prefer full resource name from env when set (Console / API use numeric ragCorpora IDs).
    corpus_name = _env("VERTEX_RAG_CORPUS_NAME")
    if not corpus_name:
        corpus_name = _build_corpus_name(
            project_id=args.project_id,
            location=args.location,
            corpus_id=args.corpus_id,
        )

    print("=" * 80)
    print("Vertex AI RAG bootstrap")
    print(f"Project:     {args.project_id}")
    print(f"Location:    {args.location}")
    print(f"Corpus ID:   {args.corpus_id}")
    print(f"Corpus name: {corpus_name}")
    print(f"GCS URI:     {args.gcs_uri if args.gcs_uri else '<not set>'}")
    print(f"Skip import: {args.skip_import}")
    print("=" * 80)

    vertexai.init(project=args.project_id, location=args.location)

    exists = _get_existing_corpus(corpus_name)
    if exists and args.recreate:
        print("RagCorpus already exists; recreating (--recreate enabled).")
        rag.delete_corpus(corpus_name)
        exists = False

    if not exists:
        print("Creating RagCorpus...")
        # DocumentCorpus is the appropriate type for PDFs/docs.
        rag_corpus = rag.create_corpus(
            display_name=args.display_name,
            description=args.description,
            corpus_type_config=rag.RagCorpusTypeConfig(
                corpus_type_config=rag.DocumentCorpus()
            ),
        )
        # Use returned name (SDK may normalize ID formatting).
        corpus_name = rag_corpus.name or corpus_name
        print(f"Created: {corpus_name}")
    else:
        print("RagCorpus already exists; will import files into it.")

    if args.skip_import:
        print("Skipping import/index step (--skip-import enabled).")
        resp = None
    else:
        transformation_config = rag.TransformationConfig(
            chunking_config=rag.ChunkingConfig(
                chunk_size=args.chunk_size,
                chunk_overlap=args.chunk_overlap,
            )
        )

        print("Importing files into RagCorpus...")
        resp = rag.import_files(
            corpus_name=corpus_name,
            paths=[args.gcs_uri],
            transformation_config=transformation_config,
            use_advanced_pdf_parsing=args.use_advanced_pdf_parsing,
            timeout=args.timeout,
        )

    # `resp` is ImportRagFilesResponse; print a couple useful fields if present.
    imported_count = getattr(resp, "imported_rag_files_count", None) if resp is not None else None
    print("Import completed.")
    if imported_count is not None:
        print(f"Imported RagFiles count: {imported_count}")
    print(f"Vertex RAG corpus ready: {corpus_name}")
    print("=" * 80)


if __name__ == "__main__":
    main()

