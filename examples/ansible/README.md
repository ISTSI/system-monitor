# Ansible file-import examples

`hosts` and `inventory.hosts.ini` are direct **host-only** static imports. `inventory.static.yaml` and `inventory.canonical.json` additionally contain the optional `inspector_processes` extension. `bundle/hosts.ini` plus its `group_vars/` and `host_vars/` demonstrates reading inventory-relative companion data; `inventory-with-vars.zip` contains exactly those files at its root. It is a deterministic ordinary ZIP, not executable code.

All examples are synthetic. The same inventory can be imported separately into System Alpha and System Beta without merging their definitions. Select a stable inventory-source ID within the target system on reimport; do not identify the source by filename/IP alone. `import-mapping.example.json` is a mapping reference, not a credential/trust grant. The typed preview request example is in `contracts/inventory-import.example.json`.

The package's bounded sample reader checks these examples but does not implement the web upload wizard, full supported variable resolution, transactional commit or authorization. Production implementation and tests are Codex work. For full rules/unsupported formats, read document 10.
