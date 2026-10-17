# 07 — Security requirements and trust boundaries

## Threat model

The application stores operational topology and potentially sensitive logs, connects to internal machines and holds passwords. No Internet access does not make it trusted by default. Protect against an unauthenticated LAN client, cross-site browser requests, malicious/compromised log contents, unsafe archives/inventories and accidental secret disclosure. A fully compromised application host or an authorised service administrator can access data the application legitimately reads; encryption of stored SSH secrets does not eliminate that risk.

The browser, imported files and remote log content are untrusted. The backend is privileged to read only operator-approved targets/paths. Never run production tests against a supplied address automatically.

## Web authentication and sessions

Bootstrap the first Administrator through a server-side interactive command at deployment, never through public self-registration/setup or a default password. Further accounts are provisioned by an authenticated Administrator. Hash all account passwords using a maintained Argon2 library with suitable parameters. Enforce document 13 roles/object ownership on the backend, including uploads, downloads, previews and live sockets. Rate-limit login and sensitive credential tests; return nonrevealing authentication errors.

Use random opaque session cookies, Secure, HttpOnly and SameSite=Strict in production, with a restricted path/domain. Store session verifier hashes server-side, not passwords or bearer tokens in browser storage. Suggested policy: 30-minute idle timeout and eight-hour absolute lifetime, configurable. Define whether deliberate user activity renews idle timeout; heartbeats alone must not defeat absolute expiry. Logout/revocation terminates streams and pending authenticated downloads.

Use exact Origin/Host validation, CSRF tokens for state-changing HTTP requests and authenticated WebSocket initial frames. Reject unexpected origins and oversized frames. No wildcard CORS. Protect login itself against login CSRF. Distinguish health endpoints from authenticated operational diagnostics. See OWASP session, CSRF and WebSocket guidance [S10–S12].

Use HTTPS with an internal-CA/provisioned certificate; the release must not contact ACME/Let's Encrypt. HSTS only after certificate/domain deployment is correct. Configure reverse-proxy WebSocket upgrade and timeouts [S13]. Trust forwarded headers only from the known proxy.

Render log strings through text nodes, not HTML. Disable raw HTML, remote images, remote includes and dangerous URL schemes in Markdown. Export log text with safe content types/download disposition. A recommended CSP permits self-hosted scripts/connects only, blocks objects and frames, and explicitly accounts for framework-required style handling without enabling unsafe script evaluation.

## SSH and secrets

Use an application-owned known-host store. Check target **and jump-host** keys. Unknown keys block authentication; an inspect operation may retrieve a fingerprint without sending credentials, but does not establish trust. An Administrator confirms it against an independent trusted source before approval. Inspectors cannot approve keys or activate targets. A changed key is a hard stop, not an automatic replacement. The trust identity includes hostname/address, port and configured alias/routing context. Never disable verification to make a test pass. AsyncSSH's known-host and tunnel behaviour must be explicitly tested [S06].

Keep a separate password record for each credential reference. Encrypt with authenticated encryption and random nonces using `cryptography`; bind ciphertext to credential ID/key version. Load the master key from a protected mounted file or supported secret facility, not the project config, source repository, container image, access logs or a command-line argument. Restrict its ownership/permissions. Document key rotation and recovery; a database backup without its separate key cannot decrypt secrets. An attacker with both runtime privileges and key access can still decrypt them.

SSH connection profiles reference secrets. Ordinary GET, config export, diagnostic output, application logs and investigation bundles never return plaintext or ciphertext. Explicit password replacement is write-only. Version credential changes and invalidate old pooled connections. Do not forward an SSH agent or expose a SOCKS/port-forward endpoint to browsers. Jump forwarding is used only internally for the approved target.

The initial transport uses direct read permissions, without sudo. Read permission must cover active logs, archived logs and directory traversal, including future rotated files. Permission tests report the failing source without trying to escalate privileges. Do not grant access to all of `/` for convenience.

## Path, archive, inventory and network boundaries

Approved targets and log roots are local Administrator approvals. Importing a config proposes them but cannot automatically activate a connection. Reject loopback/link-local/metadata targets by default unless a deployment administrator explicitly authorises a legitimate local test target; private LAN addresses are expected and are not categorically blocked. Resolve/validate destinations on connect and after changes, with explicit jump-target routing rather than arbitrary URL fetching.

The explicit 17 October 2026 user request makes the separate per-revision
target/root confirmation conditional on the global Administrator setting
**Additional security measures** (`additional_security_measures`, default true).
When true, the existing verified, expiring source approval is required. When
false, saved configuration changes, including paths and parsers, are eligible
for requested operations without that manual checkbox. This overrides the
unconditional manual-source-approval rule above; imports still start no network
operation, create no credential binding and grant no host-key trust. In either
mode enforce valid bound credentials, credential expiry, explicit target/jump
host-key trust, destination checks, configured-root/path validation, source
limits, RBAC, ownership and CSRF. Never create a synthetic approval when the
setting is off. Turning it back on requires a valid current approval. Include
the effective setting in guarded remote-operation snapshots so a policy change
cancels pending work rather than continuing under an outdated decision.

Use SFTP path operations, not a shell string. Reject traversal/control characters and revalidate canonical paths/symlinks against approved roots. Symlinks are disabled by default; an explicit profile option may permit a resolved regular file only within approved roots, with race/continuity limitations exposed. A target account's filesystem permissions remain an essential boundary.

Archive validation/streaming limits are in the engine contract. Generate local cache filenames independently of remote/member names. No `extractall`, `pickle`, `eval`, uploaded scripts, executable plugins or Jinja/lookup evaluation. The inventory importer accepts safe static data or canonical JSON output generated externally. Uploaded `ansible.cfg`, inventory plugins and executable inventory scripts are not run.

## Storage, redaction and auditing

State/cache directories are writable only by the service account. MariaDB is never exposed to browser clients and logs are never exposed as static web files. No default browser service-worker cache or persistent browser storage of raw logs. Cache settings, deletion and retained coverage are visible. Backend application logs must not contain source raw text, filter/correlation values, SSH passwords or auth tokens by default.

Audit authentication, trust/credential metadata changes, target approval, config commits, collection start/stop and exports using IDs, counts and safe summaries. This operational audit is not advertised as tamper-proof. A raw log export requires explicit operator action. Redacted exports include a preview and note remaining limitations; do not claim automatic anonymisation is complete. All export paths exclude secrets regardless of a redaction toggle.

Bundle import validates every member path/type/size/checksum before commit, creates a new offline investigation, and does not enable network sources, copy encrypted credentials or replace live topology without a separate explicit operation. Notes/Markdown and filenames are untrusted as well as raw logs.

## Limits and failure behaviour

Initial administrator policy: 10 MiB config/inventory uploads; 512 MiB per bundle upload/collection download budget; 128 MiB per expanded archive member; 1 GiB expanded bytes per collection; 10,000 members; compression ratio 500; 256 KiB per physical line; 120 seconds per bounded archive task; two concurrent archive tasks. Values are conservative initial defaults and must be configurable with validation. Exceeding a cap returns a visible partial/rejected status, not silent truncation. An explicit budget increase is bounded by administrator policy.

Max term counts/lengths, frame sizes, result page sizes and queue/buffer limits must be tested. Repeated malformed input must not crash the worker. An oversized line is flagged and optionally represented by an escaped preview with a clear truncation marker; never claim its preview is the full line or use it to establish a negative text match.

## Release security gate

Review dependency licenses/advisories on the connected build machine; pin security-patched versions and record the review date. This is not a claim that a release remains vulnerability-free forever. Supply an offline update mechanism, checksums and rollback. Run security acceptance cases before accepting a build. No external telemetry or background update checking is enabled.

## Role and database boundaries

See document 13 and the machine-readable permission matrix. Every protected service operation re-evaluates the current account's role/enabled/auth-version state and resource ownership. Client-side hiding and trusted owner IDs in a request are insufficient. Use explicit allowlists for preference and settings fields; reject mass assignment of role, owner, limits or connection information. Administrators cannot remove/disable/demote the last enabled Administrator, including concurrent requests. Serialize that invariant in a DB transaction.

A web Administrator is not the MariaDB root user and does not gain host terminal/Docker access. The serving app uses the scoped `inspector_app` DML account; schema migration credentials are mounted only into the migration tool; root credentials only into DB provisioning/authorized recovery. Do not mount the Docker socket. Secrets loaded from files must be sanitized from validation errors, exceptions, SQLAlchemy URLs, logs and export files. External DB connections require certificate and hostname verification; a verified private container-network exception is explicit in deployment config.

MariaDB outages prevent auth/ownership checks: return sanitized 503, stop protected streams and do not continue using cached session grants. Never fall back to a second database or treat a password/role present in the browser as authority. Password changes/resets, account disablement or role changes revoke existing sessions and user jobs/streams; inspect permissions at the next dispatch and interrupt existing streams within the documented two-second revocation ceiling.


## Version 3 isolation and non-executing inventory inputs

Separate authenticated user ownership from explicit project membership and live workspace control. All three must pass where applicable; a user entitled to inspect both A and B is still forbidden to attach an A event/source/preview to a B investigation or pass a B resource under A's route. No project inference from auth cookies/global current-state is allowed. Scope query cursors, download grants, idempotency keys, source/cache paths, pool keys and every WS frame. Use compound MariaDB foreign keys as defense in depth; document 16 defines the relationships and active-controller rules.

Roles remain application-global, with no new per-system ACL claim. Inspectors may inspect each system but cannot edit/import any. Administrators do not gain implicit read access to other owners' investigations. Reused vault secrets need an explicit binding to the target project; SSH trust/root approvals are not inherited just because another system uses the same address.

Inventory uploads are bounded data only. Never run `ansible-inventory`, scripts, playbooks/plugins/Jinja/lookup/ProxyCommand, nor read uploaded ansible.cfg. Companion variables come only from explicitly uploaded validated relative files. Reject unsafe ZIP/YAML before mutation; omit embedded credentials without printing values, stage raw content restrictively and delete it on commit/cancel/expiry. A canonical JSON import is not approval to execute instructions embedded in a variable. Document 10 specifies supported semantics and limits.

Global session logout/revocation intentionally affects both windows; ordinary page close/system selection/filter changes never do. A cloned sessionStorage entry is not an authenticated live-control lease. Test same-origin shared storage/account conditions, forged cross-system IDs, expired controller leases and stale frames independently of the UI controls. No cross-project raw-source deduplication in this first implementation.
