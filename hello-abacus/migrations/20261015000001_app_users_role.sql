-- The group role every app user's Postgres role is a member of. Migrations grant to it,
-- because per-user roles do not exist when a migration runs. Who adds members is open
-- in ADR-0001.
CREATE ROLE "{{ .app_users_role }}" NOLOGIN;
