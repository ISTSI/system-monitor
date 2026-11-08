#!/usr/bin/env bash
# Must remain non-executable: official entrypoint sources its SQL helper.
(
  set +x
  # The sourced official docker_process_sql helper accepts an empty argv.
  # Enabling nounset would break its own optional positional-argument handling.
  set -eo pipefail
  [[ "${MARIADB_DATABASE:-}" =~ ^[a-z][a-z0-9_]{0,47}$ ]] || exit 1
  [[ "${MARIADB_USER:-}" =~ ^[a-z][a-z0-9_]{0,31}$ ]] || exit 1
  [[ "${INSPECTOR_DB_APP_USER:-}" =~ ^[a-z][a-z0-9_]{0,31}$ ]] || exit 1
  [[ "$INSPECTOR_DB_APP_USER" != "$MARIADB_USER" && "$INSPECTOR_DB_APP_USER" != root ]] || exit 1
  declare -F docker_process_sql >/dev/null || exit 1
  runtime_password="$(cat /run/secrets/inspector_db_password)"
  [[ "$runtime_password" =~ ^[0-9a-f]{64}$ ]] || exit 1
  # Database GRANT patterns treat '_' as a wildcard, even inside backticks.
  database_scope="${MARIADB_DATABASE//_/\\_}"
  docker_process_sql <<EOSQL
CREATE USER '${INSPECTOR_DB_APP_USER}'@'%' IDENTIFIED BY '${runtime_password}';
GRANT SELECT, INSERT, UPDATE, DELETE ON \`${database_scope}\`.* TO '${INSPECTOR_DB_APP_USER}'@'%';
EOSQL
  unset runtime_password database_scope
)
