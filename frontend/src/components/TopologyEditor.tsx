import { useState, type FormEvent } from 'react';
import { message } from '../api/client';
import { ancestors, defaultGeometry, entityList, newId, type Config, type Connection, type EditEntity, type EntityKind, type Flow, type Parser, type Process, type Server, type View } from '../topology';
import { ErrorNotice, Modal } from './Common';

type Props = { kind: EntityKind; item?: EditEntity; config: Config; currentView?: View; defaults?: Partial<Flow>; onClose: () => void; onSave: (kind: EntityKind, item: EditEntity, connection?: Connection) => Promise<void> };
export default function TopologyEditor({ kind, item, config, currentView, defaults, onClose, onSave }: Props) {
  const [id] = useState(() => item?.id ?? newId(kind));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const process = kind === 'process' ? item as Process | undefined : undefined;
  const server = kind === 'server' ? item as Server | undefined : undefined;
  const connection = kind === 'connection' ? item as Connection | undefined : undefined;
  const [connectionId, setConnectionId] = useState(server?.connection_id ?? config.connections?.[0]?.id ?? '');
  const [newConnectionId] = useState(() => newId('connection'));
  const selectedConnection = config.connections?.find(item => item.id === connectionId);
  const parser = kind === 'parser' ? item as Parser | undefined : undefined;
  const flow = kind === 'flow' ? (item ?? defaults) as Flow | undefined : undefined;
  const view = kind === 'view' ? item as View | undefined : undefined;
  const [timestampKind, setTimestampKind] = useState(parser?.timestamp.kind ?? 'iso8601_prefix');
  const [visibleIds, setVisibleIds] = useState(() => (view ?? currentView)?.nodes.map(node => node.element_id) ?? defaultGeometry(config).map(node => node.element_id));
  const [visibleFlows, setVisibleFlows] = useState(() => (view ?? currentView)?.flow_ids ?? config.flows.map(flow => flow.id));
  const entities = [...config.subsystems, ...config.servers, ...config.processes];
  const text = (data: FormData, name: string) => String(data.get(name) ?? '').trim();
  const list = (data: FormData, name: string) => text(data, name).split('\n').map(value => value.trim()).filter(Boolean);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const data = new FormData(event.currentTarget); setBusy(true); setError('');
    try {
      const base = { id: text(data, 'id') || id, name: text(data, 'name') };
      if (!item && ['subsystem', 'server', 'process', 'connection', 'parser', 'flow', 'view'].some(kind => entityList(config, kind as EntityKind).some(existing => existing.id === base.id))) throw new Error('This stable ID already belongs to an element in this system. Choose a new ID.');
      const documented = { ...base, description: String(data.get('description') ?? ''), tags: text(data, 'tags').split(',').map(tag => tag.trim()).filter(Boolean) };
      const connectionFields = () => ({ host: text(data, 'host'), port: Number(data.get('port')), username: text(data, 'username'), credential_ref: text(data, 'credential_ref'), jump_connection_id: text(data, 'jump_connection_id') || null, allowed_log_roots: list(data, 'allowed_log_roots') });
      const addedConnection = kind === 'server' && !connectionId ? { id: newConnectionId, name: text(data, 'ssh_profile_name') || `${[...base.name].slice(0, 252).join('')} SSH`, ...connectionFields() } : undefined;
      let value: EditEntity;
      switch (kind) {
        case 'subsystem': value = documented; break;
        case 'server': value = { ...documented, subsystem_id: server?.subsystem_id ?? text(data, 'subsystem_id'), connection_id: addedConnection?.id ?? connectionId }; break;
        case 'process': value = { ...documented, server_id: process?.server_id ?? text(data, 'server_id'), pcs_resource_name: text(data, 'pcs_resource_name') || null,
          log_source: { active_path: text(data, 'active_path'), rotated_patterns: list(data, 'rotated_patterns'), archives: JSON.parse(text(data, 'archives') || '[]') as NonNullable<Process['log_source']>['archives'], parser_id: text(data, 'parser_id'), encoding: text(data, 'encoding'), allow_symlink: data.has('allow_symlink') } }; break;
        case 'connection': value = { ...base, ...connectionFields() }; break;
        case 'parser': value = { ...base, timestamp: timestampKind === 'iso8601_prefix' ? { kind: 'iso8601_prefix', naive_timezone: 'UTC' } : { kind: 'fixed_width', width: Number(data.get('width')), format: text(data, 'format'), naive_timezone: 'UTC' }, correlation_markers: JSON.parse(text(data, 'correlation_markers') || '[]') as Parser['correlation_markers'] }; break;
        case 'flow': value = { ...base, source_process_id: text(data, 'source_process_id'), target_process_id: text(data, 'target_process_id'), protocol: text(data, 'protocol'), description: String(data.get('description') ?? '') }; break;
        case 'view': {
          const include = new Set(visibleIds.flatMap(elementId => [...ancestors(config, elementId), elementId]));
          const geometries = defaultGeometry(config);
          value = { ...base, nodes: [...include].map(elementId => structuredClone((view ?? currentView)?.nodes.find(node => node.element_id === elementId) ?? geometries.find(node => node.element_id === elementId)!)), flow_ids: config.flows.filter(flow => visibleFlows.includes(flow.id) && include.has(flow.source_process_id) && include.has(flow.target_process_id)).map(flow => flow.id) };
          break;
        }
      }
      await onSave(kind, value, addedConnection); onClose();
    } catch (cause) { setError(cause instanceof SyntaxError ? 'Enter valid JSON in the advanced fields. No changes were saved.' : message(cause)); } finally { setBusy(false); }
  }

  return <Modal title={`${item ? 'Edit' : 'Add'} ${kind}`} onClose={onClose}><p className="target-system">Target system: <strong>{config.project.name}</strong><code>{config.project.id}</code></p>{error && <ErrorNotice>{error}</ErrorNotice>}<form onSubmit={event => { void submit(event); }}>
    <div className="form-grid"><label>Name<input name="name" defaultValue={item?.name ?? ''} maxLength={256} required autoFocus /></label><label>Stable ID<input name="id" defaultValue={id} readOnly={!!item} pattern="[A-Za-z0-9][A-Za-z0-9_.:\-]{0,127}" required maxLength={128} /></label></div>
    {!item && <p className="field-help">The ID is permanent. Renaming an element preserves its relationships.</p>}
    {['subsystem', 'server', 'process'].includes(kind) && <><label>Documentation (Markdown)<textarea name="description" rows={5} defaultValue={item && 'description' in item ? item.description : ''} /></label><label>Tags (comma separated)<input name="tags" defaultValue={item && 'tags' in item ? item.tags.join(', ') : ''} /></label></>}
    {kind === 'server' && <><label>Subsystem<select name="subsystem_id" defaultValue={server?.subsystem_id} disabled={!!server} required>{config.subsystems.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>{server && <p className="field-help">Use Move to subsystem to explicitly change ownership.</p>}<fieldset className="ssh-connection"><legend>SSH connection</legend><label>Connection profile<select name="connection_id" value={connectionId} onChange={event => setConnectionId(event.target.value)}><option value="">Create a new SSH profile</option>{config.connections?.map(item => <option key={item.id} value={item.id}>{item.name} · {item.host} · port {item.port}</option>)}</select></label>{selectedConnection ? <><div className="form-grid"><label>SSH host<input readOnly value={selectedConnection.host} /></label><label>SSH port<input readOnly value={selectedConnection.port} /></label></div><p className="field-help">This server uses the selected profile. Change its settings through Connections, or choose Create a new SSH profile for a different endpoint.</p></> : <><p className="field-help">Enter an IP address or hostname for the Linux host. Leave the profile name empty to use the server name.</p><label>SSH profile name (optional)<input name="ssh_profile_name" maxLength={256} placeholder="Server name + SSH" /></label><ConnectionFields config={config} /></>}</fieldset></>}
    {kind === 'process' && <>
      <label>Server<select name="server_id" defaultValue={process?.server_id} disabled={!!process} required>{config.servers.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>{process && <p className="field-help">Use Move to server to explicitly change ownership.</p>}
      <label>PCS resource name (optional)<input name="pcs_resource_name" defaultValue={process?.pcs_resource_name ?? ''} /></label>
      <label>Active log path<input name="active_path" defaultValue={process?.log_source?.active_path ?? '/var/log/application/app.log'} required /></label>
      <label>Rotated file patterns (one per line)<textarea name="rotated_patterns" defaultValue={process?.log_source?.rotated_patterns.join('\n') ?? ''} rows={2} /></label>
      <label>Archive definitions (JSON)<textarea className="config-text" name="archives" defaultValue={JSON.stringify(process?.log_source?.archives ?? [], null, 2)} rows={4} /></label><p className="field-help">Example: [{'{'}"path_pattern":"/var/log/application/*.zip","member_patterns":["logs/*.log"]{'}'}]</p>
      <div className="form-grid"><label>Parser profile<select name="parser_id" defaultValue={process?.log_source?.parser_id} required>{config.parsers?.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Encoding<input name="encoding" defaultValue={process?.log_source?.encoding ?? 'utf-8'} required /></label></div>
      <label className="checkbox-label"><input type="checkbox" name="allow_symlink" defaultChecked={process?.log_source?.allow_symlink ?? false} />Allow resolved regular-file symlinks within approved roots</label>
    </>}
    {kind === 'connection' && <ConnectionFields config={config} connection={connection} />}
    {['server', 'connection'].includes(kind) && <p className="notice">After saving, use Password & connection test to store the SSH password and verify access. Historical log collection still uses the synthetic local demo.</p>}
    {kind === 'parser' && <>
      <label>Timestamp strategy<select name="timestamp_kind" value={timestampKind} onChange={event => setTimestampKind(event.target.value as Parser['timestamp']['kind'])}><option value="iso8601_prefix">ISO 8601 prefix (UTC)</option><option value="fixed_width">Fixed width (UTC)</option></select></label>
      {timestampKind === 'fixed_width' && <div className="form-grid"><label>Timestamp width<input type="number" name="width" defaultValue={parser?.timestamp.kind === 'fixed_width' ? parser.timestamp.width : 23} min={1} max={64} required /></label><label>Timestamp format<input name="format" defaultValue={parser?.timestamp.kind === 'fixed_width' ? parser.timestamp.format : '%Y-%m-%d %H:%M:%S,%f'} required /></label></div>}
      <label>Correlation markers (JSON)<textarea name="correlation_markers" className="config-text" defaultValue={JSON.stringify(parser?.correlation_markers ?? [], null, 2)} rows={5} /></label><p className="field-help">Example: [{'{'}"key":"request_id","prefix":"request_id=","terminators":" "{'}'}]</p>
    </>}
    {kind === 'flow' && <>
      <div className="form-grid"><label>Source process<select name="source_process_id" defaultValue={flow?.source_process_id} required>{config.processes.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Target process<select name="target_process_id" defaultValue={flow?.target_process_id ?? config.processes[1]?.id} required>{config.processes.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label></div>
      <label>Protocol<input name="protocol" defaultValue={flow?.protocol ?? ''} /></label><label>Documentation (Markdown)<textarea name="description" rows={4} defaultValue={flow?.description ?? ''} /></label><p className="field-help">This describes a possible transfer; it does not establish observed causality.</p>
    </>}
    {kind === 'view' && <><p className="muted">Choose existing elements. Ancestors are included automatically; shared documentation and IDs stay unchanged.</p><fieldset className="view-elements"><legend>Visible elements</legend>{entities.map(item => <label className="checkbox-label" key={item.id}><input type="checkbox" checked={visibleIds.includes(item.id)} onChange={event => setVisibleIds(current => event.target.checked ? [...current, item.id] : current.filter(id => id !== item.id))} />{item.name}<code>{item.id}</code></label>)}</fieldset><fieldset className="view-elements"><legend>Visible flows</legend>{config.flows.map(flow => <label className="checkbox-label" key={flow.id}><input type="checkbox" checked={visibleFlows.includes(flow.id)} onChange={event => setVisibleFlows(current => event.target.checked ? [...current, flow.id] : current.filter(id => id !== flow.id))} />{flow.name}<code>{flow.id}</code></label>)}</fieldset><p className="field-help">A flow appears only when both endpoint processes are included.</p></>}
    <div className="form-actions"><button type="button" onClick={onClose}>Cancel</button><button className="primary" disabled={busy}>{busy ? 'Saving…' : `Save ${kind}`}</button></div>
  </form></Modal>;
}

function ConnectionFields({ config, connection }: { config: Config; connection?: Connection }) {
  const [credentialReference] = useState(() => `credential-${crypto.randomUUID()}`);
  return <>
    <div className="form-grid"><label>SSH host<input name="host" defaultValue={connection?.host ?? ''} placeholder="IP address or hostname" required maxLength={253} /></label><label>SSH port<input type="number" name="port" defaultValue={connection?.port ?? 22} min={1} max={65535} step={1} required /></label></div>
    <div className="form-grid"><label>Username<input name="username" defaultValue={connection?.username ?? 'logreader'} required /></label><label>Credential reference<input name="credential_ref" defaultValue={connection?.credential_ref ?? credentialReference} required /></label></div>
    <p className="field-help">This reference is a label for a separately stored SSH password. Save the profile, then use Password & connection test to set the password and approve the host key.</p>
    {connection && <p className="field-help">Changes apply to every server using this profile ({config.servers.filter(server => server.connection_id === connection.id).length} in this system).</p>}
    <label>Jump connection<select name="jump_connection_id" defaultValue={connection?.jump_connection_id ?? ''}><option value="">Direct connection</option>{config.connections?.filter(item => item.id !== connection?.id && !item.jump_connection_id).map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
    <label>Proposed log roots (one absolute Linux path per line)<textarea name="allowed_log_roots" defaultValue={connection?.allowed_log_roots.join('\n') ?? '/var/log/application'} rows={3} /></label>
  </>;
}

export function MoveDialog({ config, selection, onClose, onMove }: { config: Config; selection: { kind: 'server' | 'process'; id: string }; onClose: () => void; onMove: (parent: string) => Promise<void> }) {
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const current = entityList(config, selection.kind).find(item => item.id === selection.id)!;
  const parentKind = selection.kind === 'server' ? 'subsystem' : 'server';
  const original = selection.kind === 'server' ? (current as Server).subsystem_id : (current as Process).server_id;
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError('');
    try { await onMove(String(new FormData(event.currentTarget).get('parent'))); onClose(); } catch (cause) { setError(message(cause)); } finally { setBusy(false); }
  }
  return <Modal title={`Move to ${parentKind}`} onClose={onClose}><p className="target-system">Target system: <strong>{config.project.name}</strong><code>{config.project.id}</code></p><p>Move <strong>{current.name}</strong> and retain its permanent ID and relationships. This explicitly changes its parent within this system.</p>{error && <ErrorNotice>{error}</ErrorNotice>}<form onSubmit={event => { void submit(event); }}><label>New {parentKind}<select name="parent" required defaultValue=""><option value="" disabled>Choose a different parent</option>{entityList(config, parentKind).filter(item => item.id !== original).map(item => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label><div className="form-actions"><button type="button" onClick={onClose}>Cancel</button><button disabled={busy} className="primary">Confirm move</button></div></form></Modal>;
}
