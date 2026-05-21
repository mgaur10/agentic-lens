variable "project_id" {
  type        = string
  description = "GCP Project ID where the RagCorpus is created"
}

variable "location" {
  type        = string
  description = "RAG location (e.g. us-west1)"
}

variable "corpus_id" {
  type        = string
  description = "RagCorpus ID (ragCorpora/{corpus_id})"
}

variable "display_name" {
  type        = string
  description = "RagCorpus display name"
}

variable "description" {
  type        = string
  description = "RagCorpus description"
}

variable "python_bin" {
  type        = string
  description = "Python binary to use for the bootstrap script (should include vertexai/preview.rag deps)"
}

variable "setup_script_path" {
  type        = string
  description = "Path to backend/setup_vertex_rag_corpus.py"
}

