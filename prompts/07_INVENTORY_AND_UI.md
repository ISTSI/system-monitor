# Stage 07 — Finish safe Ansible import and UI acceptance

Read AGENTS.md and the relevant references below. Implement this stage only unless a higher-level user prompt explicitly authorises another stage.

## References

- `docs/06_UI_UX.md`
- `docs/10_ANSIBLE_IMPORT.md`
- `examples/ansible/inventory.canonical.json`
- `examples/ansible/inventory.static.yaml`
- `examples/ansible/inventory.hosts.ini`

## Task

Implement canonical ansible-inventory JSON and the specified safe static YAML/INI subsets, mapping preview, one-subsystem conflicts, stable reimport identities and the optional inspector_processes extension. Omit secret fields without echoing them. Never run Ansible/plugins/ProxyCommand/Jinja from uploaded data. Finish parser/path test panels, shortcuts, accessibility and UI states for all completed features.

Preserve existing descriptions, layouts and manually configured processes on reimport. Display unknown/unsupported inventory semantics clearly and direct complex cases to canonical JSON. Complete visuals from the supplied reference without using the image as a page background or copying branding. Inspect screens at 1280×720 and 1920×1080 and verify all primary actions through browser tests.

## Version 2 gate

Inventory/parser/connection diagnostics and shared settings are Administrator-only. Complete visual matrix of both roles and both themes across every page, dialog, menu and error/empty/loading state. Test actual contrast, focus, local icons, measured row seeding, no false green health labels, and durable user/default/system appearance behaviour.

## Version 3 gate

Complete the direct-file Ansible setup wizard, not only canonical JSON: INI/extensionless hosts, YAML and ZIP companion variables. Bind source/upload/preview/mapping/commit to the explicitly selected system. Test malicious/static-unsupported inputs, secret omission, project-scoped idempotency, preserved manual fields and Inspector denials at every endpoint. Capture both themes with two distinct system window titles.

## Completion gate

All three supplied inventory formats produce the expected host mapping; canonical/YAML optional process definitions work and the host-only INI never invents processes. Reimports are idempotent, conflicting memberships are blocked, unsafe inputs do not execute. Complete the required screenshot and keyboard/zoom evidence. Stop before production release.

Acceptance targets: AT55, AT56, AT57, AT58, AT59, AT60, AT61, AT70, AT88, AT102, AT103, AT104, AT105, AT106, AT107, AT108, AT109, AT110, AT111, AT112, AT113, AT114, AT119. Run the tests that actually exist or implement the missing tests for this scope. Do not interpret an acceptance-test name as proof of a passing test. Update progress/STATUS.md with exact commands, results, blocked checks and the next stage.
