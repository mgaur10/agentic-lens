# Access Context Manager policy (org-level)
resource "google_access_context_manager_access_policy" "policy" {
  parent = "organizations/${var.org_id}"
  title  = var.policy_title
}

locals {
  policy_name = "accessPolicies/${google_access_context_manager_access_policy.policy.name}"
  level_id    = replace(var.access_level_title, " ", "_")
  perimeter_id = replace(var.perimeter_title, " ", "_")
}

# Access level: only these members can cross the perimeter (ingress/egress)
resource "google_access_context_manager_access_level" "allowed_users" {
  parent      = local.policy_name
  name        = "${local.policy_name}/accessLevels/${local.level_id}"
  title       = var.access_level_title
  description = "Allowed users for Agentic Prism perimeter ingress and egress"

  basic {
    conditions {
      members = var.allowed_members
    }
  }
}

# Project number for perimeter resources
data "google_project" "project" {
  project_id = var.project_id
}

# Service perimeter: protect the project; allow ingress/egress only from access level
resource "google_access_context_manager_service_perimeter" "perimeter" {
  parent         = local.policy_name
  name           = "${local.policy_name}/servicePerimeters/${local.perimeter_id}"
  title          = var.perimeter_title
  perimeter_type = "PERIMETER_TYPE_REGULAR"

  status {
    resources = ["projects/${data.google_project.project.number}"]

    # Restrict all supported VPC-SC services
    restricted_services = ["*"]

    # Ingress: allow only requests from the access level (allowed_members)
    ingress_policies {
      ingress_from {
        identity_type = "ANY_IDENTITY"
        sources {
          access_level = google_access_context_manager_access_level.allowed_users.name
        }
      }
      ingress_to {
        resources = ["*"]
        operations {
          service_name = "*"
        }
      }
    }

    # Egress: allow identities in the access level to make calls outside the perimeter
    egress_policies {
      egress_from {
        identity_type = "ANY_IDENTITY"
        identities    = [google_access_context_manager_access_level.allowed_users.name]
      }
      egress_to {
        resources = ["*"]
        operations {
          service_name = "*"
        }
      }
    }
  }
}
