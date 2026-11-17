#!/usr/bin/env bash
# Discover host-side log files for running Docker containers and export
# a System Inspector server-import JSON document.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${1:-$SCRIPT_DIR/.env}"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
info() { printf '%s\n' "$*" >&2; }

[[ -f "$ENV_FILE" ]] || fail "Configuration not found: $ENV_FILE"
# The .env file is Bash-sourced; use only a file you trust.
# shellcheck source=/dev/null
source "$ENV_FILE"

for variable in SERVER_ID SERVER_NAME SERVER_ADDRESS SERVER_PORT SERVER_USER SUBSYSTEM_ID; do
  [[ -n "${!variable:-}" ]] || fail "Missing $variable in $ENV_FILE"
done
[[ "$SERVER_PORT" =~ ^[0-9]+$ ]] || fail 'SERVER_PORT must be an integer'
(( 10#$SERVER_PORT >= 1 && 10#$SERVER_PORT <= 65535 )) || fail 'SERVER_PORT out of range'

PARSER_ID="${PARSER_ID:-parser-iso-utc}"
LOG_ENCODING="${LOG_ENCODING:-utf-8}"
MAX_LOG_DEPTH="${MAX_LOG_DEPTH:-4}"
LOG_FILE_PATTERNS="${LOG_FILE_PATTERNS:-*.log}"
OUTPUT_FILE="${OUTPUT_FILE:-system-inspector-server.json}"
SCAN_ALL_MOUNTS="${SCAN_ALL_MOUNTS:-false}"

[[ "$MAX_LOG_DEPTH" =~ ^[1-9][0-9]?$ ]] || fail 'MAX_LOG_DEPTH must be an integer from 1 to 99'
[[ "$SCAN_ALL_MOUNTS" == true || "$SCAN_ALL_MOUNTS" == false ]] || fail 'SCAN_ALL_MOUNTS must be true or false'
[[ -n "$OUTPUT_FILE" ]] || fail 'OUTPUT_FILE must not be empty'
[[ "$OUTPUT_FILE" == /* ]] || OUTPUT_FILE="$SCRIPT_DIR/$OUTPUT_FILE"

command -v docker >/dev/null 2>&1 || fail 'docker command not found'
command -v jq >/dev/null 2>&1 || fail 'jq command not found (install: dnf install jq)'
command -v sha256sum >/dev/null 2>&1 || fail 'sha256sum command not found'

IFS=';' read -r -a PATTERNS <<< "$LOG_FILE_PATTERNS"
(( ${#PATTERNS[@]} > 0 )) || fail 'LOG_FILE_PATTERNS must contain at least one glob'
find_predicates=()
for pattern in "${PATTERNS[@]}"; do
  [[ -n "$pattern" ]] || continue
  (( ${#find_predicates[@]} == 0 )) || find_predicates+=( -o )
  find_predicates+=( -iname "$pattern" )
done
(( ${#find_predicates[@]} > 0 )) || fail 'LOG_FILE_PATTERNS contains no valid glob'

mkdir -p -- "$(dirname -- "$OUTPUT_FILE")"
records_file="$(mktemp)"
output_tmp="$(mktemp "${OUTPUT_FILE}.tmp.XXXXXX")"
trap 'rm -f -- "$records_file" "$output_tmp"' EXIT

# Only inspect mounts likely to contain application logs.
log_mount() {
  local src="${1,,}" dst="${2,,}"
  [[ "$SCAN_ALL_MOUNTS" == true ]] && return 0
  [[ "$src" =~ (^|/)(log|logs|logfiles)(/|$) ]] && return 0
  [[ "$dst" =~ (^|/)(log|logs|logfiles)(/|$) ]] && return 0
  [[ "$src" == *.log || "$dst" == *.log ]] && return 0
  [[ "$src" == *-logs/* || "$src" == *-logs || "$dst" == *-logs/* || "$dst" == *-logs ]] && return 0
  return 1
}

add_record() {
  local container="$1" filepath="$2" digest
  digest="$(printf '%s' "$filepath" | sha256sum | cut -c1-8)"
  jq -nc --arg container "$container" --arg active_path "$filepath" --arg digest "$digest" \
    '{container:$container,active_path:$active_path,digest:$digest}' >> "$records_file"
}

container_count=0
containers_without_logs=0
# Enumerate only currently running containers. Inspect each for host mounts.
while IFS= read -r container_id; do
  [[ -n "$container_id" ]] || continue
  ((container_count += 1))
  if ! inspection="$(docker inspect "$container_id" 2>/dev/null)"; then
    info "WARN: Container $container_id disappeared before inspection; skipped"
    continue
  fi
  container_name="$(jq -r '.[0].Name // "" | ltrimstr("/")' <<< "$inspection")"
  [[ -n "$container_name" ]] || { info "WARN: Container $container_id has no name; skipped"; continue; }

  discovered=0
  # Null-separated fields allow spaces, tabs, and newlines in mount paths.
  while IFS= read -r -d '' source && IFS= read -r -d '' destination; do
    [[ -n "$source" && -n "$destination" ]] || continue
    log_mount "$source" "$destination" || continue
    [[ ! -L "$source" ]] || { info "WARN: $container_name: symlinked mount source $source skipped"; continue; }

    # Broad shared mounts cannot safely be attributed to one container.
    # A matching per-container subdirectory is safe to scan instead.
    scan_target="$source"
    if [[ "$source" == /var/log || "$source" == /var/log/mc ]]; then
      if [[ -d "$source/$container_name" && ! -L "$source/$container_name" ]]; then
        scan_target="$source/$container_name"
      else
        info "WARN: $container_name: shared mount $source skipped (no $container_name subdirectory)"
        continue
      fi
    fi

    if [[ -f "$scan_target" && ! -L "$scan_target" ]]; then
      # Directly mounted file; accept it only if it matches a configured glob.
      filename="${scan_target##*/}"
      for pattern in "${PATTERNS[@]}"; do
        [[ -n "$pattern" ]] || continue
        if [[ "${filename,,}" == ${pattern,,} ]]; then
          add_record "$container_name" "$scan_target"
          ((discovered += 1))
          break
        fi
      done
    elif [[ -d "$scan_target" ]]; then
      while IFS= read -r -d '' logfile; do
        add_record "$container_name" "$logfile"
        ((discovered += 1))
      done < <(find -P "$scan_target" -maxdepth "$MAX_LOG_DEPTH" -type f \
                    \( "${find_predicates[@]}" \) -print0)
    fi
  done < <(jq -j '.[0].Mounts[]? |
                    select(.Type == "bind" or .Type == "volume") |
                    select((.Source | type) == "string" and (.Destination | type) == "string") |
                    .Source, "\u0000", .Destination, "\u0000"' <<< "$inspection")

  if (( discovered == 0 )); then
    ((containers_without_logs += 1))
    info "NO FILE LOG FOUND: $container_name (may log to Docker stdout/stderr)"
  fi
done < <(docker ps --format '{{.ID}}')

# Build one service for each discovered log file. If a container has just one
# file, its service id is <container>.service. With multiple files, append a
# filename and a stable hash so ids remain distinct across subdirectories.
jq -n \
  --slurpfile records "$records_file" \
  --arg server_id "$SERVER_ID" \
  --arg server_name "$SERVER_NAME" \
  --arg server_address "$SERVER_ADDRESS" \
  --argjson server_port "$((10#$SERVER_PORT))" \
  --arg server_user "$SERVER_USER" \
  --arg subsystem_id "$SUBSYSTEM_ID" \
  --arg parser_id "$PARSER_ID" \
  --arg encoding "$LOG_ENCODING" '
  def safe_id: gsub("[^a-zA-Z0-9_.-]"; "_");
  def basename: split("/") | last;
  {
    format: "system-inspector-server",
    schema_version: "1.0",
    server: {
      id: $server_id,
      name: $server_name,
      address: $server_address,
      port: $server_port,
      user: $server_user,
      subsystem_id: $subsystem_id
    },
    services: (
      $records
      | unique_by(.container, .active_path)
      | group_by(.container)
      | map(
          . as $group
          | ($group | length) as $number_of_logs
          | $group | map(
              . as $entry
              | {
                  id: (
                    ($entry.container | safe_id)
                    + (if $number_of_logs > 1
                       then "__" + ($entry.active_path | basename | sub("\\.(log|out)$"; "") | safe_id) + "_" + $entry.digest
                       else "" end)
                    + ".service"
                  ),
                  name: (
                    $server_id + ": " + $entry.container
                    + (if $number_of_logs > 1 then " (" + ($entry.active_path | basename) + ")" else "" end)
                  ),
                  log_source: {
                    active_path: $entry.active_path,
                    rotated_patterns: [],
                    archives: [],
                    parser_id: $parser_id,
                    encoding: $encoding,
                    allow_symlink: false
                  }
                }
            )
        )
      | add // []
    )
  }
' > "$output_tmp"

chmod 0644 "$output_tmp"
mv -f -- "$output_tmp" "$OUTPUT_FILE"
service_count="$(jq '.services | length' "$OUTPUT_FILE")"
info "Scanned $container_count running container(s); found $service_count log file(s)."
info "Containers without discovered file logs: $containers_without_logs"
info "Output: $OUTPUT_FILE"
