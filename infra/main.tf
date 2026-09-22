resource "random_id" "this" {
  byte_length = 4

  keepers = {
    seed_input = try(var.aws_app_code, terraform.workspace)
  }
}

resource "random_pet" "this" {
  length    = 3
  separator = "-"

  keepers = {
    seed_input = try(var.aws_app_code, terraform.workspace)
  }
}

# Signing key for the API's access tokens, shared by every backend service so a
# token issued at login verifies everywhere. Held in Terraform state rather
# than in the repository, and stable across applies via keepers: regenerating
# it would sign out every user.
resource "random_password" "jwt_secret" {
  length  = 48
  special = false

  keepers = {
    seed_input = try(var.aws_app_code, terraform.workspace)
  }
}
