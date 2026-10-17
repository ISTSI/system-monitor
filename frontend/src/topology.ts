import type { components } from './api/schema';

export type EntityKind = 'subsystem' | 'server' | 'process' | 'flow' | 'connection' | 'parser' | 'view';
export type Documented = { id: string; name: string; description: string; tags: string[] };
export type Subsystem = Documented;
export type Server = Documented & { subsystem_id: string; connection_id?: string };
export type LogSource = { active_path: string; rotated_patterns: string[]; archives: { path_pattern: string; member_patterns: string[] }[]; parser_id: string; encoding: string; allow_symlink: boolean };
export type Process = Documented & { server_id: string; pcs_resource_name: string | null; log_source?: LogSource };
export type Connection = { id: string; name: string; host: string; port: number; username: string; credential_ref: string; jump_connection_id: string | null; allowed_log_roots: string[] };
export type Parser = { id: string; name: string; timestamp: { kind: 'iso8601_prefix'; naive_timezone: 'UTC' } | { kind: 'fixed_width'; width: number; format: string; naive_timezone: 'UTC' }; correlation_markers: { key: string; prefix: string; terminators: string }[] };
export type Flow = { id: string; name: string; source_process_id: string; target_process_id: string; protocol: string; description: string };
export type Geometry = { element_id: string; x: number; y: number; width: number; height: number; collapsed: boolean };
export type View = { id: string; name: string; nodes: Geometry[]; flow_ids: string[] };
export type Config = {
  schema_version: '2.0'; project: { id: string; name: string; description: string; revision: number; display_timezone: 'UTC' };
  subsystems: Subsystem[]; servers: Server[]; processes: Process[]; flows: Flow[]; views: View[];
  connections?: Connection[]; parsers?: Parser[]; settings?: { ui: { product_name: string; locale: 'en' }; live: { poll_interval_ms: number; reorder_buffer_ms: number; record_by_default: boolean } };
};
export type Topology = Omit<components['schemas']['TopologyResponse'], 'config'> & { config: Config };
export type Selection = { kind: EntityKind; id: string };
export type SearchResult = Selection & { name: string; view_id: string | null };
export type DeleteImpact = { entities: { kind: EntityKind; id: string; name: string }[]; flows: string[]; views: string[]; investigations: unknown[]; active_sessions: unknown[] };
export type EditEntity = Subsystem | Server | Process | Connection | Parser | Flow | View;

export function entityList(config: Config, kind: EntityKind): EditEntity[] {
  switch (kind) {
    case 'subsystem': return config.subsystems;
    case 'server': return config.servers;
    case 'process': return config.processes;
    case 'connection': return config.connections ?? [];
    case 'parser': return config.parsers ?? [];
    case 'flow': return config.flows;
    case 'view': return config.views;
  }
}

export function entity(config: Config, selection: Selection | null): EditEntity | undefined {
  return selection ? entityList(config, selection.kind).find(item => item.id === selection.id) : undefined;
}

export function kindOf(config: Config, id: string): EntityKind {
  if (config.subsystems.some(item => item.id === id)) return 'subsystem';
  if (config.servers.some(item => item.id === id)) return 'server';
  return 'process';
}

export function parentId(config: Config, id: string): string | undefined {
  return config.servers.find(item => item.id === id)?.subsystem_id ?? config.processes.find(item => item.id === id)?.server_id;
}

export function ancestors(config: Config, id: string): string[] {
  const parent = parentId(config, id);
  return parent ? [...ancestors(config, parent), parent] : [];
}

export function newId(kind: EntityKind): string { return `${kind}-${crypto.randomUUID()}`; }

// A new view references existing model IDs; geometry is local to that view.
export function defaultGeometry(config: Config): Geometry[] {
  const nodes: Geometry[] = [];
  config.subsystems.forEach((subsystem, index) => {
    const outer = { element_id: subsystem.id, x: index * 570, y: 0, width: 540, height: 320, collapsed: false };
    nodes.push(outer); let serverY = 65;
    for (const server of config.servers.filter(item => item.subsystem_id === subsystem.id)) {
      const processes = config.processes.filter(item => item.server_id === server.id);
      const height = Math.max(240, 55 + processes.length * 88 + 10);
      nodes.push({ element_id: server.id, x: 20, y: serverY, width: 490, height, collapsed: false });
      processes.forEach((process, index) => nodes.push({ element_id: process.id, x: 20, y: 55 + index * 88, width: 440, height: 72, collapsed: false }));
      serverY += height + 20;
    }
    outer.height = Math.max(outer.height, serverY);
  });
  return nodes;
}

export function withEntity(config: Config, kind: EntityKind, value: EditEntity): Config {
  const next = structuredClone(config);
  const collection = entityList(next, kind);
  const found = collection.findIndex(item => item.id === value.id);
  if (found >= 0) collection[found] = value;
  else collection.push(value);
  if (kind === 'connection') next.connections = collection as Connection[];
  if (kind === 'parser') next.parsers = collection as Parser[];
  if (found < 0 && ['subsystem', 'server', 'process'].includes(kind)) {
    if (!next.views.length) next.views.push({ id: newId('view'), name: 'System overview', nodes: defaultGeometry(next), flow_ids: [] });
    const geometry = defaultGeometry(next).find(item => item.element_id === value.id)!;
    for (const view of next.views) {
      const ids = [...ancestors(next, value.id), value.id];
      for (const id of ids) if (!view.nodes.some(node => node.element_id === id)) view.nodes.push(id === value.id ? geometry : defaultGeometry(next).find(node => node.element_id === id)!);
      // Expand groups to fit the newly added node without changing model ownership.
      for (const id of ancestors(next, value.id).reverse()) {
        const parent = view.nodes.find(node => node.element_id === id)!;
        const children = view.nodes.filter(node => parentId(next, node.element_id) === id);
        parent.width = Math.max(parent.width, ...children.map(child => child.x + child.width + 20));
        parent.height = Math.max(parent.height, ...children.map(child => child.y + child.height + 20));
      }
    }
  }
  if (kind === 'flow' && found < 0) for (const view of next.views) {
    const flow = value as Flow;
    if ([flow.source_process_id, flow.target_process_id].every(id => view.nodes.some(node => node.element_id === id))) view.flow_ids.push(value.id);
  }
  return next;
}
