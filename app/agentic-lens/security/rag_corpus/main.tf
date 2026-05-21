resource "null_resource" "vertex_rag_corpus" {
  triggers = {
    project_id   = var.project_id
    location     = var.location
    corpus_id    = var.corpus_id
    display_name = var.display_name
  }

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command     = <<EOT
${var.python_bin} "${var.setup_script_path}" \
  --project-id="${var.project_id}" \
  --location="${var.location}" \
  --corpus-id="${var.corpus_id}" \
  --display-name="${var.display_name}" \
  --description="${var.description}" \
  --skip-import
EOT
  }
}

