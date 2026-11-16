CREATE SCHEMA app_data;
CREATE TABLE app_data.items (
  id         BIGSERIAL PRIMARY KEY,
  name       TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 200),
  created_by TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT USAGE ON SCHEMA app_data TO "{{ .app_users_role }}";
GRANT SELECT, INSERT ON app_data.items TO "{{ .app_users_role }}";
GRANT USAGE ON SEQUENCE app_data.items_id_seq TO "{{ .app_users_role }}";
