import type { LogSource } from './topology';

export type InventoryFormat = 'ini' | 'yaml' | 'canonical_json' | 'static_zip';
export type InventoryDiagnostic = { code?: string; message?: string; [key: string]: unknown };
export type InventorySource = { project_id?: string; id: string; name: string; created_us: string };
export type InventoryUpload = {
  project_id: string; inventory_source_id: string; upload_id: string; expected_revision: number; expires_us: string;
  filename: string; format: InventoryFormat | null; files: { path: string; size: number; role: string; format: string | null }[];
  source_candidates: string[]; ignored_files: string[]; warnings: InventoryDiagnostic[];
};
export type InventoryProcess = { id: string; name: string; pcs_resource_name?: string | null; log_source: LogSource };
export type InventoryHost = {
  alias: string; address: string; port: number; user: string | null; groups: string[];
  vars: Record<string, unknown>; processes: InventoryProcess[]; provenance: unknown; warnings: InventoryDiagnostic[];
};
export type InventoryParsed = {
  project_id: string; inventory_source_id: string; upload_id: string; expected_revision: number;
  hosts: InventoryHost[]; groups: { name: string; children: string[]; hosts: string[]; vars: Record<string, unknown>; provenance: unknown }[];
  process_count: number; warnings: InventoryDiagnostic[]; conflicts: InventoryDiagnostic[]; omitted_variables: { name: string; count: number }[];
  provenance: { source_files: string[]; companion_files: string[]; ignored_files: string[] };
};
export type InventoryMapping = {
  group_to_subsystem: Record<string, string>; host_to_subsystem: Record<string, string>; tag_only_groups: string[];
  credential_mapping: Record<string, string>; jump_mapping: Record<string, string | null>; parser_mapping: Record<string, string>;
  preserve_existing_documentation: true; preserve_existing_layout: true; delete_missing_hosts: false;
};
export type InventoryPreview = {
  project_id: string; inventory_source_id: string; preview_id: string; expected_revision: number; expires_us: string;
  can_commit: boolean; process_count: number; warnings: InventoryDiagnostic[]; conflicts: InventoryDiagnostic[];
  records: { kind: 'host' | 'process'; alias: string; local_id?: string; target_id: string; status: 'added' | 'changed' | 'unchanged' | 'conflicting' | 'unassigned' | 'absent'; changes: { field: string; before: unknown; after: unknown }[]; message?: string }[];
};

export function emptyInventoryMapping(): InventoryMapping {
  return { group_to_subsystem: {}, host_to_subsystem: {}, tag_only_groups: [], credential_mapping: {}, jump_mapping: {}, parser_mapping: {}, preserve_existing_documentation: true, preserve_existing_layout: true, delete_missing_hosts: false };
}
