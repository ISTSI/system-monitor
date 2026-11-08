#!/bin/sh
# Fixed operations only. Never pass passwords through argv or enable tracing.
set -eu
umask 077
client_file="$(mktemp /tmp/inspector-client.XXXXXXXX)"
trap 'rm -f "$client_file"' EXIT HUP INT TERM
password_file=/run/secrets/inspector_db_migration_password
bytes="$(wc -c < "$password_file")"
without_nul="$(tr -d '\000' < "$password_file" | wc -c)"
[ "$bytes" -le 4096 ] && [ "$bytes" -eq "$without_nul" ] || { echo 'Invalid protected password file' >&2; exit 1; }
iconv -f UTF-8 -t UTF-8 "$password_file" >/dev/null 2>&1 || { echo 'Invalid protected password encoding' >&2; exit 1; }
# An appended sentinel prevents command substitution stripping *all* trailing
# newlines. Remove at most one LF/CRLF, preserving spaces and reserved symbols.
password="$(cat "$password_file"; printf x)"
password="${password%x}"
line_feed='
'
carriage_return="$(printf '\r')"
case "$password" in
  *"$carriage_return$line_feed") password="${password%"$carriage_return$line_feed"}";;
  *"$line_feed") password="${password%"$line_feed"}";;
esac
case "$password" in ''|*"$line_feed"*|*"$carriage_return"*) echo 'Invalid protected password value' >&2; exit 1;; esac
escaped_password="$(printf '%s' "$password" | sed 's/\\/\\\\/g; s/"/\\"/g')"
db_name="${SI_DB_NAME:-system_inspector}"
db_user="${SI_DB_USER:-inspector_migrator}"
db_host="${SI_DB_HOST:-127.0.0.1}"
db_port="${SI_DB_PORT:-3306}"
case "$db_name" in ''|*[!a-z0-9_]*) exit 1;; esac
case "$db_user" in ''|*[!a-z0-9_]*) exit 1;; esac
case "$db_host" in ''|*[!a-zA-Z0-9_.:-]*) exit 1;; esac
case "$db_port" in ''|*[!0-9]*) exit 1;; esac
printf '[client]\nuser=%s\npassword="%s"\nhost=%s\nport=%s\nprotocol=tcp\n' "$db_user" "$escaped_password" "$db_host" "$db_port" > "$client_file"
unset password escaped_password
if [ "${SI_DB_TLS:-disabled}" = verify_identity ]; then
  printf 'ssl\nssl-verify-server-cert\nssl-ca=/run/tls/database-ca.crt\n' >> "$client_file"
elif [ "${SI_DB_TLS:-disabled}" != disabled ]; then exit 1; fi
case "${1:-}" in
  dump) mariadb-dump --defaults-extra-file="$client_file" --single-transaction --quick --hex-blob --no-tablespaces --skip-comments "$db_name";;
  restore) mariadb --defaults-extra-file="$client_file" --binary-mode "$db_name";;
  inspect) mariadb --defaults-extra-file="$client_file" --batch --skip-column-names "$db_name" <<'SQL'
SELECT version_num FROM alembic_version;
SELECT 'projects',COUNT(*) FROM projects;
SELECT 'users',COUNT(*) FROM users;
SELECT 'history_events',COUNT(*) FROM history_events;
SELECT 'saved_investigations',COUNT(*) FROM saved_investigations;
SELECT 'user_preferences',COUNT(*) FROM user_preferences;
SQL
  ;;
  revoke) mariadb --defaults-extra-file="$client_file" --batch "$db_name" <<'SQL'
START TRANSACTION;
DELETE FROM auth_sessions;
UPDATE workspaces SET state='detached',revision=revision+1;
UPDATE live_sessions SET status='interrupted' WHERE status NOT IN ('stopped','interrupted','failed');
UPDATE history_jobs SET status='interrupted' WHERE status NOT IN ('completed','partial','cancelled','failed','interrupted');
COMMIT;
SQL
  ;;
  *) echo 'Choose dump, restore, inspect or revoke' >&2; exit 2;;
esac
