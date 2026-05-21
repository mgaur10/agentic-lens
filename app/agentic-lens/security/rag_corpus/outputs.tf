output "rag_corpus_name" {
  value       = "projects/${var.project_id}/locations/${var.location}/ragCorpora/${var.corpus_id}"
  description = "Full RagCorpus resource name"
}

