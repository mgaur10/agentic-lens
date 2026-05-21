# VPC Service Controls (VPC-SC) and Access Context Manager
# Requires an organization; policy is created at org level.

variable "project_id" {
  type        = string
  description = "GCP Project ID to protect with the perimeter"
}

variable "org_id" {
  type        = string
  description = "Google Cloud Organization ID (parent of the project)"
}

variable "allowed_members" {
  type        = list(string)
  description = "Identities allowed to ingress/egress the perimeter (e.g. [\"user:dev@example.com\"]). Used in both ingress and egress rules."
}

variable "policy_title" {
  type        = string
  default     = "Agentic Prism VPC-SC Policy"
  description = "Title for the Access Context Manager policy"
}

variable "access_level_title" {
  type        = string
  default     = "prism_allowed_users"
  description = "Title for the access level (allowed users)"
}

variable "perimeter_title" {
  type        = string
  default     = "prism_perimeter"
  description = "Title for the service perimeter"
}
