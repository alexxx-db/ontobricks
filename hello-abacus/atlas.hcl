# Read by the migrate job (jobs/migrate.py), which runs Atlas from this directory.
# The connection URL carries a credential, so it comes from the environment, never argv.

variable "app_users_role" {
  type = string
}

data "template_dir" "migrations" {
  path = "migrations"
  vars = {
    app_users_role = var.app_users_role
  }
}

env "lakebase" {
  url = getenv("ATLAS_URL")
  migration {
    dir = data.template_dir.migrations.url
  }
}
