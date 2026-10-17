# Primary references

Original references were reviewed for v1 on 16 October 2026; the v2 MariaDB, authorization, theming and deployment references below were checked on 17 October 2026. These sources support technology capabilities and security constraints, not claims that this unimplemented application has passed tests. Most detailed algorithms, limits, API shapes and defaults in this package are explicit design decisions.

## S01
OpenAI, **Custom instructions with AGENTS.md**. Repository-level agent instructions and scope. https://developers.openai.com/codex/agent-configuration/agents-md

## S02
React Flow, **Sub Flow**, and project license information. Nested graphs/grouping and MIT core library. https://reactflow.dev/examples/grouping/sub-flows ; https://reactflow.dev/

## S03
TanStack Virtual, **Introduction**. Virtualised rendering of long lists. https://tanstack.com/virtual/latest/docs/introduction

## S04
FastAPI, **WebSockets**. WebSocket support and process-local connection-state limitation. https://fastapi.tiangolo.com/advanced/websockets/

## S05
FastAPI, **Lifespan Events**. Application startup/shutdown lifecycle. https://fastapi.tiangolo.com/advanced/events/

## S06
AsyncSSH, **API documentation** and **Asynchronous SSH for Python**. Password authentication, SFTP, known-host verification and tunnel connections. https://asyncssh.readthedocs.io/en/latest/api.html ; https://asyncssh.readthedocs.io/en/latest/

## S07
Python, **tarfile — Read and write tar archive files**. Tar members, stream reading and extraction security considerations. https://docs.python.org/3/library/tarfile.html

## S08
Python, **zipfile — Work with ZIP archives**. Member streams, supported compression and decompression pitfalls. https://docs.python.org/3/library/zipfile.html

## S09
Legacy v1 reference only; not a v2 runtime dependency. SQLite, **Appropriate Uses For SQLite**, **Write-Ahead Logging**, and **SQLite Over a Network**. Local-server database design and filesystem caveats. https://www.sqlite.org/whentouse.html ; https://www.sqlite.org/wal.html ; https://www.sqlite.org/useovernet.html

## S10
OWASP, **WebSocket Security Cheat Sheet**. Origin validation, authenticated sessions, limits and sensitive logging. https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html

## S11
OWASP, **Cross-Site Request Forgery Prevention Cheat Sheet**. CSRF tokens and request validation. https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html

## S12
OWASP, **Session Management Cheat Sheet**. Cookie/session lifecycle and server-side session controls. https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html

## S13
NGINX, **WebSocket proxying**. Proxy Upgrade/Connection handling and timeouts. https://nginx.org/en/docs/http/websocket.html

## S14
Ansible, **ansible-inventory**, **How to build your inventory**, and **Inventory plugins**. Canonical inventory output, host/group structures and executable/plugin distinction. https://docs.ansible.com/projects/ansible/latest/cli/ansible-inventory.html ; https://docs.ansible.com/projects/ansible/latest/inventory_guide/intro_inventory.html ; https://docs.ansible.com/projects/ansible/latest/plugins/inventory.html

## S15
Docker, **docker image save** and **docker image load**. Offline transport of built images. https://docs.docker.com/reference/cli/docker/image/save/ ; https://docs.docker.com/reference/cli/docker/image/load/

## S16
Podman, **podman-systemd.unit**. Declarative systemd/Quadlet lifecycle. https://docs.podman.io/en/latest/markdown/podman-systemd.unit.5.html

## S17
Node.js, **Node.js Releases** and **Node.js 24.11.0 (LTS)**. Build toolchain release/support policy. https://nodejs.org/en/about/previous-releases ; https://nodejs.org/en/blog/release/v24.11.0

## S18
MariaDB Foundation, **Maintenance policy**; MariaDB's official container repository, **docker-entrypoint.sh** and **healthcheck.sh**; image environment-variable guide. Maintained release baseline, initialization, password-file variables and readiness hooks. Use the community `mariadb` image, not an enterprise subscription image shown in some documentation examples. https://mariadb.org/about/#maintenance-policy ; https://github.com/MariaDB/mariadb-docker/blob/master/docker-entrypoint.sh ; https://github.com/MariaDB/mariadb-docker/blob/master/healthcheck.sh ; https://mariadb.com/docs/server/server-management/automated-mariadb-deployment-and-administration/docker-and-mariadb/mariadb-server-docker-official-image-environment-variables

## S19
SQLAlchemy, **MySQL and MariaDB — asyncmy**. AsyncEngine integration and database dialect. https://docs.sqlalchemy.org/en/20/dialects/mysql.html#module-sqlalchemy.dialects.mysql.asyncmy

## S20
React Flow, **Theming**. Light/dark/system colour modes and CSS variable customization. https://reactflow.dev/learn/customization/theming

## S21
OWASP, **Authorization Cheat Sheet**. Deny-by-default and per-request authorization; application-specific ownership and role choices are explicitly defined in document 13. https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html

## S22
W3C, **Understanding WCAG 2.2 Contrast (Minimum)** and **Non-text Contrast**. Text/control contrast criteria; full implemented accessibility still requires browser testing. https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html ; https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html

## S23
Docker, **Manage secrets securely in Docker Compose**. Service-specific file-backed secret mounts; verify local implementation permissions rather than assuming Swarm behaviour. https://docs.docker.com/compose/how-tos/use-secrets/ ; https://docs.docker.com/reference/compose-file/services/#secrets

## S24
Docker, **Control startup and shutdown order in Compose**. Healthy service and successful one-shot dependency conditions. https://docs.docker.com/compose/how-tos/startup-order/

## S25
MariaDB, **GET_LOCK**. Connection-lifetime advisory locks; application failover/locking strategy is a design choice. https://mariadb.com/docs/server/reference/sql-functions/secondary-functions/miscellaneous-functions/get_lock

## S26
Alembic, **Using asyncio with Alembic**. Async migration connection workflow. https://alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic

## S27
MariaDB, **mariadb-dump**. Consistent transactional dump options and client compatibility. Filesystem-cache coordination and recovery gates are application requirements. https://mariadb.com/docs/server/clients-and-utilities/backup-restore-and-import-clients/mariadb-dump

## S28
React Flow, **Performance**. Avoiding unnecessary renders and excessively expensive node styling. https://reactflow.dev/learn/advanced-use/performance

## S29
Caddy, **tls directive**. Explicit local certificate/key configuration rather than Internet certificate issuance. https://caddyserver.com/docs/caddyfile/directives/tls

## S30
Compose Specification, **JSON Schema**. Optional validation input for the template checker when this schema is supplied locally. The package did not execute this optional schema check or Docker Compose itself. https://github.com/compose-spec/compose-spec/blob/main/schema/compose-spec.json

No paid example implementation or font files have been copied into this package. Preserve license notices for the dependencies actually selected at implementation time.


## Version 3 source review — 17 October 2026

S14 was reread for direct static inventory formats, relative `group_vars`/`host_vars`, aliases and documented merge precedence. The CLI documentation distinguishes `--list` from `--export`. The safe subset/conflict policy, ZIP workflow, source IDs and import limits here are application design choices, not a claim of full Ansible equivalence.

## S28
MDN, **Window: sessionStorage property**. Page-session scope, reload persistence and copying from an opener. Supports the warning that copied storage is not a unique live-workspace identity. https://developer.mozilla.org/en-US/docs/Web/API/Window/sessionStorage

## S29
SQLAlchemy 2.0, **Defining Constraints and Indexes**. Use `ForeignKeyConstraint` for composite foreign keys; independent single-column constraints do not express the paired relationship. https://docs.sqlalchemy.org/en/20/core/constraints.html

S01 was checked again during this iteration (the official URL currently redirects to the ChatGPT Learn Codex documentation). The staged prompts, workspace scheme, capacity defaults and scope invariants are package decisions, not capabilities claimed to have been tested in Codex or a production browser.
