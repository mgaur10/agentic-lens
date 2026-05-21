output "access_policy_name" {
  description = "Access Context Manager policy name"
  value       = google_access_context_manager_access_policy.policy.name
}

output "access_level_name" {
  description = "Access level name (allowed users for ingress/egress)"
  value       = google_access_context_manager_access_level.allowed_users.name
}

output "service_perimeter_name" {
  description = "Service perimeter name"
  value       = google_access_context_manager_service_perimeter.perimeter.name
}
