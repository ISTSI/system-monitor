#!/usr/bin/env bash
# Keep this file non-executable: the pinned official image sources init .sh files.
# It uses the image's docker_process_sql helper; verify against the pinned image.
# This script runs only for a fresh database directory, never as a password rotator.
(
  set +x
  set -euo pipefail
  : "${MARIADB_DATABASE:?Database name is required}"
  : "${MARIADB_USER:?Migration account name is required}"
  : "${INSPECTOR_DB_APP_USER:?Runtime account name is required}"
  [[ "$MARIADB_DATABASE" =~ ^[a-z][a-z0-9_]{0,47}$ ]] || { echo 'Invalid database name' >&2; exit 1; }
  [[ "$MARIADB_USER" =~ ^[a-z][a-z0-9_]{0,31}$ ]] || { echo 'Invalid migration username' >&2; exit 1; }
  [[ "$INSPECTOR_DB_APP_USER" =~ ^[a-z][a-z0-9_]{0,31}$ ]] || { echo 'Invalid runtime username' >&2; exit 1; }
  [[ "$INSPECTOR_DB_APP_USER" != "$MARIADB_USER" && "$INSPECTOR_DB_APP_USER" != root ]] || { echo 'Runtime account must be separate' >&2; exit 1; }
  declare -F docker_process_sql >/dev/null || { echo 'Unsupported image initialization context' >&2; exit 1; }
  runtime_password_file="${INSPECTOR_DB_APP_PASSWORD_FILE:-/run/secrets/inspector_db_password}"
  [[ -r "$runtime_password_file" ]] || { echo 'Runtime password file is not readable' >&2; exit 1; }
  runtime_password="$(cat "$runtime_password_file")"
  # The supplied local generator writes 64 random hexadecimal characters. This
  # deliberately restricted bootstrap representation avoids SQL quoting hazards.
  [[ "$runtime_password" =~ ^[0-9a-f]{64}$ ]] || { echo 'Invalid bootstrap password format' >&2; exit 1; }
  docker_process_sql <<EOSQL
CREATE USER '${INSPECTOR_DB_APP_USER}'@'%' IDENTIFIED BY '${runtime_password}';
GRANT SELECT, INSERT, UPDATE, DELETE ON \`${MARIADB_DATABASE}\`.* TO '${INSPECTOR_DB_APP_USER}'@'%';
EOSQL
  unset runtime_password runtime_password_file
)
