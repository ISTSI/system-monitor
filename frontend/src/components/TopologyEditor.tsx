import { useI18n } from '../i18n';
import { useRef, useState, type FormEvent } from 'react';
import { message } from '../api/client';
import { ancestors, defaultGeometry, entityList, newId, type Config, type Connection, type EditEntity, type EntityKind, type Flow, type Parser, type Process, type Server, type View } from '../topology';
import { ErrorNotice, Modal } from './Common';
import ParserTestPanel from './ParserTestPanel';

type Props = { kind: EntityKind; item?: EditEntity; config: Config; currentView?: View; defaults?: Partial<Flow>; onClose: () => void; onSave: (kind: EntityKind, item: EditEntity, connection?: Connection) => Promise<void> };
const entityNames: Record<EntityKind, string> = { subsystem: 'Subsystem', server: 'Server', process: 'Process', flow: 'Flow', connection: 'Connection', parser: 'Parser', view: 'View' };
const editorActions: Record<EntityKind, { add: string; edit: string; save: string }> = Object.fromEntries(Object.keys(entityNames).map(kind => [kind, { add: `Add ${kind}`, edit: `Edit ${kind}`, save: `Save ${kind}` }])) as Record<EntityKind, { add: string; edit: string; save: string }>;
const rootChangeHelp = 'Keep the current roots and add the new root on another line, save, then update the affected processes before removing an old root.';
function configuredLogPaths(config: Config, connectionId: string) {
  return config.processes.flatMap(process => {
    const server = config.servers.find(server => server.id === process.server_id && server.connection_id === connectionId);
    const source = process.log_source;
    if (!server || !source) return [];
    return [
      { kind: 'Active log', path: source.active_path },
      ...source.rotated_patterns.map(path => ({ kind: 'Rotated files', path })),
      ...source.archives.map(archive => ({ kind: 'Archive', path: archive.path_pattern })),
    ].map(path => ({ ...path, processId: process.id, processName: process.name, serverName: server.name }));
  });
}
function belowLogRoots(path: string, roots: string[]) {
  return roots.some(root => path.startsWith(root.replace(/\/+$/, '') + '/'));
}

export default function TopologyEditor({ kind, item, config, currentView, defaults, onClose, onSave }: Props) {
  const { t } = useI18n();
  const [id] = useState(() => item?.id ?? newId(kind));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [excludedRootCount, setExcludedRootCount] = useState(0);
  const formRef = useRef<HTMLFormElement>(null);
  const [parserDraftVersion, setParserDraftVersion] = useState(0);
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

  function parserDraft(data: FormData): Parser {
    return { id: text(data, 'id') || id, name: text(data, 'name') || 'Parser preview', timestamp: timestampKind === 'iso8601_prefix' ? { kind: 'iso8601_prefix', naive_timezone: 'UTC' } : { kind: 'fixed_width', width: Number(data.get('width')), format: text(data, 'format'), naive_timezone: 'UTC' }, correlation_markers: JSON.parse(text(data, 'correlation_markers') || '[]') as Parser['correlation_markers'] };
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const data = new FormData(event.currentTarget); setBusy(true); setError(''); setExcludedRootCount(0);
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
        case 'connection': {
          const fields = connectionFields();
          const excluded = configuredLogPaths(config, base.id).filter(source => !belowLogRoots(source.path, fields.allowed_log_roots));
          if (excluded.length) { setExcludedRootCount(excluded.length); throw new Error('These log roots exclude configured log paths.'); }
          value = { ...base, ...fields }; break;
        }
        case 'parser': value = { ...parserDraft(data), ...base }; break;
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

  return <Modal title={t(editorActions[kind][item ? 'edit' : 'add'])} onClose={onClose}><p className="target-system">{t("Target system:")} <strong>{config.project.name}</strong><code>{config.project.id}</code></p>{error && <ErrorNotice>{excludedRootCount ? t("These log roots exclude {count} configured log paths. {help}", { count: excludedRootCount, help: t(rootChangeHelp) }) : t(error)}</ErrorNotice>}<form ref={formRef} onChange={event => { if (kind === 'parser' && !event.target.closest('.parser-test')) setParserDraftVersion(value => value + 1); }} onSubmit={event => { void submit(event); }}>
    <div className="form-grid"><label>{t("Name")}<input name="name" defaultValue={item?.name ?? ''} maxLength={256} required autoFocus /></label><label>{t("Stable ID")}<input name="id" defaultValue={id} readOnly={!!item} pattern="[A-Za-z0-9][A-Za-z0-9_.:\-]{0,127}" required maxLength={128} /></label></div>
    {!item && <p className="field-help">{t("The ID is permanent. Renaming an element preserves its relationships.")}</p>}
    {['subsystem', 'server', 'process'].includes(kind) && <><label>{t("Documentation (Markdown)")}<textarea name="description" rows={5} defaultValue={item && 'description' in item ? item.description : ''} /></label><label>{t("Tags (comma separated)")}<input name="tags" defaultValue={item && 'tags' in item ? item.tags.join(', ') : ''} /></label></>}
    {kind === 'server' && <><label>{t("Subsystem")}<select name="subsystem_id" defaultValue={server?.subsystem_id} disabled={!!server} required>{config.subsystems.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>{server && <p className="field-help">{t("Use Move to subsystem to explicitly change ownership.")}</p>}<fieldset className="ssh-connection"><legend>{t("SSH connection")}</legend><label>{t("Connection profile")}<select name="connection_id" value={connectionId} onChange={event => setConnectionId(event.target.value)}><option value="">{t("Create a new SSH profile")}</option>{config.connections?.map(item => <option key={item.id} value={item.id}>{item.name} · {item.host} {t("· port")} {item.port}</option>)}</select></label>{selectedConnection ? <><div className="form-grid"><label>{t("SSH host")}<input readOnly value={selectedConnection.host} /></label><label>{t("SSH port")}<input readOnly value={selectedConnection.port} /></label></div><p className="field-help">{t("This server uses the selected profile. Change its settings through Connections, or choose Create a new SSH profile for a different endpoint.")}</p></> : <><p className="field-help">{t("Enter an IP address or hostname for the Linux host. Leave the profile name empty to use the server name.")}</p><label>{t("SSH profile name (optional)")}<input name="ssh_profile_name" maxLength={256} placeholder={t("Server name + SSH")} /></label><ConnectionFields config={config} /></>}</fieldset></>}
    {kind === 'process' && <>
      <label>{t("Server")}<select name="server_id" defaultValue={process?.server_id} disabled={!!process} required>{config.servers.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>{process && <p className="field-help">{t("Use Move to server to explicitly change ownership.")}</p>}
      <label>{t("PCS resource name (optional)")}<input name="pcs_resource_name" defaultValue={process?.pcs_resource_name ?? ''} /></label>
      <label>{t("Active log path")}<input name="active_path" defaultValue={process?.log_source?.active_path ?? '/var/log/application/app.log'} required /></label>
      <label>{t("Rotated file patterns (one per line)")}<textarea name="rotated_patterns" defaultValue={process?.log_source?.rotated_patterns.join('\n') ?? ''} rows={2} /></label>
      <label>{t("Archive definitions (JSON)")}<textarea className="config-text" name="archives" defaultValue={JSON.stringify(process?.log_source?.archives ?? [], null, 2)} rows={4} /></label><p className="field-help">{t("Example: [")}{'{'}"path_pattern":"/var/log/application/*.zip","member_patterns":["logs/*.log"]{'}'}]</p>
      <div className="form-grid"><label>{t("Parser profile")}<select name="parser_id" defaultValue={process?.log_source?.parser_id} required>{config.parsers?.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>{t("Encoding")}<input name="encoding" defaultValue={process?.log_source?.encoding ?? 'utf-8'} required /></label></div>
      <label className="checkbox-label"><input type="checkbox" name="allow_symlink" defaultChecked={process?.log_source?.allow_symlink ?? false} />{t("Allow resolved regular-file symlinks within approved roots")}</label>
    </>}
    {kind === 'connection' && <ConnectionFields config={config} connection={connection} />}
    {['server', 'connection'].includes(kind) && <p className="notice">{t("After saving, use Password & connection test to store the SSH password and verify the host key. Confirm the target and log roots when Additional security measures is enabled in Settings.")}</p>}
    {kind === 'parser' && <>
      <label>{t("Timestamp strategy")}<select name="timestamp_kind" value={timestampKind} onChange={event => setTimestampKind(event.target.value as Parser['timestamp']['kind'])}><option value="iso8601_prefix">{t("ISO 8601 prefix (UTC)")}</option><option value="fixed_width">{t("Fixed width (UTC)")}</option></select></label>
      {timestampKind === 'fixed_width' && <div className="form-grid"><label>{t("Timestamp width")}<input type="number" name="width" defaultValue={parser?.timestamp.kind === 'fixed_width' ? parser.timestamp.width : 23} min={1} max={64} required /></label><label>{t("Timestamp format")}<input name="format" defaultValue={parser?.timestamp.kind === 'fixed_width' ? parser.timestamp.format : '%Y-%m-%d %H:%M:%S,%f'} required /></label></div>}
      <label>{t("Correlation markers (JSON)")}<textarea name="correlation_markers" className="config-text" defaultValue={JSON.stringify(parser?.correlation_markers ?? [], null, 2)} rows={5} /></label><p className="field-help">{t("Example: [")}{'{'}"key":"request_id","prefix":"request_id=","terminators":" "{'}'}]</p>
    </>}
    {kind === 'parser' && <ParserTestPanel config={config} draftVersion={parserDraftVersion} getParser={() => parserDraft(new FormData(formRef.current!))} />}
    {kind === 'flow' && <>
      <div className="form-grid"><label>{t("Source process")}<select name="source_process_id" defaultValue={flow?.source_process_id} required>{config.processes.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>{t("Target process")}<select name="target_process_id" defaultValue={flow?.target_process_id ?? config.processes[1]?.id} required>{config.processes.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label></div>
      <label>{t("Protocol")}<input name="protocol" defaultValue={flow?.protocol ?? ''} /></label><label>{t("Documentation (Markdown)")}<textarea name="description" rows={4} defaultValue={flow?.description ?? ''} /></label><p className="field-help">{t("This describes a possible transfer; it does not establish observed causality.")}</p>
    </>}
    {kind === 'view' && <><p className="muted">{t("Choose existing elements. Ancestors are included automatically; shared documentation and IDs stay unchanged.")}</p><fieldset className="view-elements"><legend>{t("Visible elements")}</legend>{entities.map(item => <label className="checkbox-label" key={item.id}><input type="checkbox" checked={visibleIds.includes(item.id)} onChange={event => setVisibleIds(current => event.target.checked ? [...current, item.id] : current.filter(id => id !== item.id))} />{item.name}<code>{item.id}</code></label>)}</fieldset><fieldset className="view-elements"><legend>{t("Visible flows")}</legend>{config.flows.map(flow => <label className="checkbox-label" key={flow.id}><input type="checkbox" checked={visibleFlows.includes(flow.id)} onChange={event => setVisibleFlows(current => event.target.checked ? [...current, flow.id] : current.filter(id => id !== flow.id))} />{flow.name}<code>{flow.id}</code></label>)}</fieldset><p className="field-help">{t("A flow appears only when both endpoint processes are included.")}</p></>}
    <div className="form-actions"><button type="button" onClick={onClose}>{t("Cancel")}</button><button className="primary" disabled={busy}>{busy ? t("Saving…") : t(editorActions[kind].save)}</button></div>
  </form></Modal>;
}

function ConnectionFields({ config, connection }: { config: Config; connection?: Connection }) {
  const { t } = useI18n();
  const [credentialReference] = useState(() => `credential-${crypto.randomUUID()}`);
  const [logRoots, setLogRoots] = useState(connection?.allowed_log_roots.join('\n') ?? '/var/log/application');
  const roots = logRoots.split('\n').map(root => root.trim()).filter(Boolean);
  const paths = connection ? configuredLogPaths(config, connection.id) : [];
  const excludedCount = paths.filter(source => !belowLogRoots(source.path, roots)).length;
  return <>
    <div className="form-grid"><label>{t("SSH host")}<input name="host" defaultValue={connection?.host ?? ''} placeholder={t("IP address or hostname")} required maxLength={253} /></label><label>{t("SSH port")}<input type="number" name="port" defaultValue={connection?.port ?? 22} min={1} max={65535} step={1} required /></label></div>
    <div className="form-grid"><label>{t("Username")}<input name="username" defaultValue={connection?.username ?? 'logreader'} required /></label><label>{t("Credential reference")}<input name="credential_ref" defaultValue={connection?.credential_ref ?? credentialReference} required /></label></div>
    <p className="field-help">{t("This reference is a label for a separately stored SSH password. Save the profile, then use Password & connection test to set the password and approve the host key.")}</p>
    {connection && <p className="field-help">{t("Changes apply to every server using this profile ({count} in this system).", { count: config.servers.filter(server => server.connection_id === connection.id).length })}</p>}
    <label>{t("Jump connection")}<select name="jump_connection_id" defaultValue={connection?.jump_connection_id ?? ''}><option value="">{t("Direct connection")}</option>{config.connections?.filter(item => item.id !== connection?.id && !item.jump_connection_id).map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
    <label>{t("Proposed log roots (one absolute Linux path per line)")}<textarea name="allowed_log_roots" value={logRoots} onChange={event => setLogRoots(event.target.value)} aria-invalid={excludedCount > 0} aria-describedby="log-roots-help" rows={3} /></label>
    <p id="log-roots-help" className="field-help">{t("Every active log, rotated file pattern and archive path on servers using this profile must be below a proposed root.")} {t(rootChangeHelp)}</p>
    {paths.length > 0 && <section className="connection-log-paths" aria-label={t("Configured log paths using this profile")}><h3>{t("Configured log paths using this profile")}</h3><p className={excludedCount ? 'log-root-warning' : 'muted'} aria-live="polite">{excludedCount ? t("{count} configured log paths are outside the proposed roots. Review the marked paths below.", { count: excludedCount }) : t("All configured log paths are within the proposed roots.")}</p><ul>{paths.map((source, index) => {
      const outside = !belowLogRoots(source.path, roots);
      return <li key={`${source.processId}:${index}`}><strong>{t("{process} on {server}", { process: source.processName, server: source.serverName })}</strong><span>{t(source.kind)}</span><code>{source.path}</code>{outside && <span className="log-root-warning">{t("Outside proposed roots")}</span>}</li>;
    })}</ul></section>}
  </>;
}

export function MoveDialog({ config, selection, onClose, onMove }: { config: Config; selection: { kind: 'server' | 'process'; id: string }; onClose: () => void; onMove: (parent: string) => Promise<void> }) {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const current = entityList(config, selection.kind).find(item => item.id === selection.id)!;
  const parentKind = selection.kind === 'server' ? 'subsystem' : 'server';
  const original = selection.kind === 'server' ? (current as Server).subsystem_id : (current as Process).server_id;
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError('');
    try { await onMove(String(new FormData(event.currentTarget).get('parent'))); onClose(); } catch (cause) { setError(message(cause)); } finally { setBusy(false); }
  }
  return <Modal title={parentKind === 'server' ? t("Move to server") : t("Move to subsystem")} onClose={onClose}><p className="target-system">{t("Target system:")} <strong>{config.project.name}</strong><code>{config.project.id}</code></p><p>{t("Move")} <strong>{current.name}</strong> {t("and retain its permanent ID and relationships. This explicitly changes its parent within this system.")}</p>{error && <ErrorNotice>{t(error)}</ErrorNotice>}<form onSubmit={event => { void submit(event); }}><label>{parentKind === 'server' ? t("New server") : t("New subsystem")}<select name="parent" required defaultValue=""><option value="" disabled>{t("Choose a different parent")}</option>{entityList(config, parentKind).filter(item => item.id !== original).map(item => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label><div className="form-actions"><button type="button" onClick={onClose}>{t("Cancel")}</button><button disabled={busy} className="primary">{t("Confirm move")}</button></div></form></Modal>;
}
