import { useEffect, useRef, useState } from 'react';
import { csrf, message, request, write } from '../api/client';
import { emptyInventoryMapping, type InventoryDiagnostic, type InventoryFormat, type InventoryMapping, type InventoryParsed, type InventoryPreview, type InventorySource, type InventoryUpload } from '../inventory';
import type { Config } from '../topology';
import { ErrorNotice, Modal } from './Common';
import './inventory.css';

const formatNames: Record<InventoryFormat, string> = { ini: 'Static INI / extensionless hosts', yaml: 'Static YAML / YML', canonical_json: 'Canonical inventory JSON', static_zip: 'ZIP with static sources and companion variables' };
function display(value: unknown): string { return value === undefined ? 'Not set' : typeof value === 'string' ? value : JSON.stringify(value, null, 2); }

export default function InventoryImport({ config, revision, onClose, onCommitted }: { config: Config; revision: number; onClose: () => void; onCommitted: () => Promise<void> }) {
  const projectId = config.project.id; const base = `/projects/${encodeURIComponent(projectId)}/inventory`;
  const [sources, setSources] = useState<InventorySource[]>([]); const [sourceId, setSourceId] = useState(''); const [sourceName, setSourceName] = useState('');
  const [credentialRefs, setCredentialRefs] = useState<string[]>([]); const [jumpIds, setJumpIds] = useState<string[]>([]);
  const [file, setFile] = useState<File | null>(null); const [upload, setUpload] = useState<InventoryUpload | null>(null);
  const [format, setFormat] = useState<InventoryFormat>('ini'); const [sourceFiles, setSourceFiles] = useState<string[]>([]);
  const [parsed, setParsed] = useState<InventoryParsed | null>(null); const [mapping, setMapping] = useState<InventoryMapping>(emptyInventoryMapping);
  const [preview, setPreview] = useState<InventoryPreview | null>(null); const [reviewed, setReviewed] = useState(false);
  const [busy, setBusy] = useState('Loading inventory sources'); const [error, setError] = useState(''); const [step, setStep] = useState(1);
  const alive = useRef(true); const generation = useRef(0); const heldUpload = useRef<InventoryUpload | null>(null); const heldPreview = useRef<InventoryPreview | null>(null); const abort = useRef<AbortController | null>(null);
  const commitStarted = useRef(false);
  const pendingCancel = useRef<Promise<unknown>>(Promise.resolve());
  useEffect(() => {
    alive.current = true;
    void Promise.all([
      request<{ project_id: string; items: InventorySource[] }>(`${base}/sources`),
      Promise.allSettled((config.connections ?? []).map(async connection => {
        const access = await request<{ project_id: string; connection_id: string; config_revision: number; credential: { configured: boolean }; host_key: { approved: boolean } }>(`/projects/${encodeURIComponent(projectId)}/connections/${encodeURIComponent(connection.id)}/access`);
        return { connection, access };
      })),
    ]).then(([value, access]) => {
      if (!alive.current || value.project_id !== projectId) return;
      setSources(value.items);
      const available = access.flatMap(result => result.status === 'fulfilled' && result.value.access.project_id === projectId && result.value.access.config_revision === revision && result.value.access.credential.configured ? [result.value] : []);
      setCredentialRefs([...new Set(available.map(item => item.connection.credential_ref))]);
      setJumpIds(available.filter(item => item.access.host_key.approved && !item.connection.jump_connection_id).map(item => item.connection.id));
    }).catch((cause: unknown) => { if (alive.current) setError(message(cause)); }).finally(() => { if (alive.current) setBusy(''); });
    return () => { alive.current = false; generation.current += 1; abort.current?.abort(); const currentPreview = heldPreview.current; const currentUpload = heldUpload.current; heldPreview.current = null; heldUpload.current = null; if (currentPreview) void write(`${base}/previews/${encodeURIComponent(currentPreview.preview_id)}/cancel`).catch(() => {}); if (currentUpload) void write(`${base}/uploads/${encodeURIComponent(currentUpload.upload_id)}/cancel`).catch(() => {}); };
  }, [base, projectId, config.connections, revision]);
  function releasePreview() {
    const previous = heldPreview.current; heldPreview.current = null;
    if (previous) pendingCancel.current = pendingCancel.current.then(() => write(`${base}/previews/${encodeURIComponent(previous.preview_id)}/cancel`)).catch(() => {});
    setPreview(null); setReviewed(false); return pendingCancel.current;
  }
  function invalidateParse() { generation.current += 1; void releasePreview(); setParsed(null); setMapping(emptyInventoryMapping()); setError(''); }
  function invalidateUpload() {
    invalidateParse(); const previous = heldUpload.current; heldUpload.current = null;
    if (previous) pendingCancel.current = pendingCancel.current.then(() => write(`${base}/uploads/${encodeURIComponent(previous.upload_id)}/cancel`)).catch(() => {});
    setUpload(null); setSourceFiles([]);
  }
  function close() { if (!commitStarted.current) onClose(); }
  async function createSource() {
    setBusy('Creating source identity'); setError(''); const current = generation.current; const controller = new AbortController(); abort.current = controller;
    try { const source = await request<InventorySource>(`${base}/sources`, { method: 'POST', body: JSON.stringify({ name: sourceName.trim() }), signal: AbortSignal.any([controller.signal, AbortSignal.timeout(15000)]) }); if (alive.current && current === generation.current && source.project_id === projectId) { invalidateUpload(); setFile(null); setSources(values => [...values, source]); setSourceId(source.id); setSourceName(''); setStep(2); } }
    catch (cause) { if (alive.current) setError(message(cause)); } finally { if (alive.current) setBusy(''); if (abort.current === controller) abort.current = null; }
  }
  async function uploadFile() {
    if (!file || !sourceId) return;
    invalidateUpload(); const current = generation.current; setBusy('Validating uploaded files'); setError(''); const controller = new AbortController(); abort.current = controller;
    try {
      if (file.size > 10 * 1024 * 1024) throw new Error('Inventory exceeds the 10 MiB upload limit.');
      if (!file.size) throw new Error('Choose a non-empty inventory file.');
      await pendingCancel.current;
      if (!alive.current || current !== generation.current) return;
      const token = await csrf();
      const response = await fetch(`/api/v1${base}/uploads?inventory_source_id=${encodeURIComponent(sourceId)}&expected_revision=${revision}`, { method: 'POST', credentials: 'same-origin', cache: 'no-store', headers: { 'Content-Type': 'application/octet-stream', 'X-CSRF-Token': token, 'X-Inventory-Filename': encodeURIComponent(file.name) }, body: file, signal: AbortSignal.any([controller.signal, AbortSignal.timeout(60000)]) });
      const value = await response.json() as InventoryUpload & { error?: { message?: string } };
      if (!response.ok) throw new Error(value.error?.message ?? 'The inventory upload was rejected.');
      if (value.project_id !== projectId || value.inventory_source_id !== sourceId || value.expected_revision !== revision) throw new Error('The uploaded inventory does not match this system, source and revision.');
      if (alive.current && current === generation.current) { heldUpload.current = value; setUpload(value); setFormat(value.format ?? 'ini'); setSourceFiles(value.source_candidates.length === 1 ? value.source_candidates : []); }
      else void write(`${base}/uploads/${encodeURIComponent(value.upload_id)}/cancel`).catch(() => {});
    } catch (cause) { if (alive.current && current === generation.current) setError(message(cause)); }
    finally { if (alive.current && current === generation.current) setBusy(''); if (abort.current === controller) abort.current = null; }
  }
  async function parse() {
    if (!upload || !sourceFiles.length) return;
    invalidateParse(); const current = generation.current; setBusy('Parsing static inventory'); const controller = new AbortController(); abort.current = controller;
    try {
      const value = await request<InventoryParsed>(`${base}/parse`, { method: 'POST', body: JSON.stringify({ inventory_source_id: sourceId, upload_id: upload.upload_id, expected_revision: revision, format, source_files: sourceFiles }), signal: AbortSignal.any([controller.signal, AbortSignal.timeout(15000)]) });
      if (alive.current && current === generation.current && value.project_id === projectId) { setParsed(value); setMapping({ ...emptyInventoryMapping(), tag_only_groups: value.groups.map(group => group.name).filter(name => name !== 'all' && name !== 'ungrouped') }); setStep(3); }
    } catch (cause) { if (alive.current && current === generation.current) setError(message(cause)); }
    finally { if (alive.current && current === generation.current) setBusy(''); if (abort.current === controller) abort.current = null; }
  }
  function mapField(field: 'group_to_subsystem' | 'host_to_subsystem' | 'credential_mapping' | 'parser_mapping', key: string, value: string) {
    void releasePreview(); setError(''); setMapping(previous => { const values = { ...previous[field] }; if (value.trim()) values[key] = value.trim(); else delete values[key]; return { ...previous, [field]: values }; });
  }
  async function preparePreview() {
    if (!upload || !parsed) return;
    const current = ++generation.current; setBusy('Preparing exact changes'); setError(''); const controller = new AbortController(); abort.current = controller;
    try {
      await releasePreview();
      if (!alive.current || current !== generation.current) return;
      const value = await request<InventoryPreview>(`${base}/preview`, { method: 'POST', body: JSON.stringify({ project_id: projectId, inventory_source_id: sourceId, upload_id: upload.upload_id, expected_revision: revision, format, source_files: sourceFiles, mapping }), signal: AbortSignal.any([controller.signal, AbortSignal.timeout(15000)]) });
      if (value.project_id !== projectId || value.inventory_source_id !== sourceId || value.expected_revision !== revision) throw new Error('The preview does not match this system, source and revision.');
      if (alive.current && current === generation.current) { heldPreview.current = value; setPreview(value); setReviewed(false); setStep(4); }
      else void write(`${base}/previews/${encodeURIComponent(value.preview_id)}/cancel`).catch(() => {});
    } catch (cause) { if (alive.current && current === generation.current) setError(message(cause)); }
    finally { if (alive.current && current === generation.current) setBusy(''); if (abort.current === controller) abort.current = null; }
  }
  async function commit() {
    if (!preview || !reviewed || !preview.can_commit || commitStarted.current) return;
    commitStarted.current = true;
    setBusy('Committing reviewed inventory'); setError('');
    try { await write(`${base}/commit`, { preview_id: preview.preview_id, expected_revision: preview.expected_revision }); heldPreview.current = null; heldUpload.current = null; await onCommitted(); onClose(); }
    catch (cause) { if (alive.current) setError(message(cause)); } finally { commitStarted.current = false; if (alive.current) setBusy(''); }
  }
  function order(path: string, delta: number) { invalidateParse(); setSourceFiles(previous => { const next = [...previous]; const index = next.indexOf(path); const target = index + delta; if (index >= 0 && target >= 0 && target < next.length) [next[index], next[target]] = [next[target], next[index]]; return next; }); }
  const source = sources.find(value => value.id === sourceId);
  const parserIds = [...new Set(parsed?.hosts.flatMap(host => host.processes.map(process => process.log_source.parser_id)) ?? [])];
  const ignored = upload?.files.filter(entry => !sourceFiles.includes(entry.path) && entry.role !== 'companion') ?? [];
  return <Modal title="Import Ansible inventory files" onClose={close}><div className="inventory-wizard">
    <div className="inventory-target" aria-label="Inventory import target"><strong>{config.project.name}</strong><code>{projectId} · revision {revision}</code><span>Inventory source: <strong>{source?.name ?? 'Choose a source'}</strong></span>{sourceId && <code data-testid="inventory-source-id">{sourceId}</code>}</div>
    <ol className="inventory-steps" aria-label="Inventory import steps">{['Source identity', 'Upload and select', 'Map inventory', 'Review and commit'].map((name, index) => <li key={name} aria-current={step === index + 1 ? 'step' : undefined}><span>{index + 1}</span>{name}</li>)}</ol>
    {upload && parsed && step > 2 && <details className="inventory-help"><summary>Selected files and provenance: {upload.filename}</summary><p>Format: {formatNames[format]}. Source read order: {sourceFiles.join(' → ')}.</p><p>Companion files ({parsed.provenance.companion_files.length}): {parsed.provenance.companion_files.join(', ') || 'none supplied'}.</p><p>Ignored files ({parsed.provenance.ignored_files.length}): {parsed.provenance.ignored_files.join(', ') || 'none'}.</p></details>}
    {error && <ErrorNotice>{error}</ErrorNotice>}<p className="inventory-status" role="status">{busy}</p>
    {step === 1 && <section aria-label="Inventory source identity"><h3>Keep reimports attached to one source</h3><p>Choose the source used for earlier imports even if the filename changed. Different inventories can have the same filename.</p><label>Existing inventory source<select aria-label="Existing inventory source" value={sourceId} disabled={!!busy} onChange={event => { invalidateUpload(); setFile(null); setSourceId(event.target.value); }}><option value="">Choose a source or create one</option>{sources.map(value => <option key={value.id} value={value.id}>{value.name} · {value.id}</option>)}</select></label><div className="inventory-new-source"><label>New inventory source name<input maxLength={128} value={sourceName} disabled={!!busy} onChange={event => setSourceName(event.target.value)} placeholder="For example, production static hosts" /></label><button disabled={!!busy || !sourceName.trim()} onClick={() => { void createSource(); }}>Create inventory source</button></div><p className="muted">The target system comes from this page URL. Select another system before opening this wizard to import there.</p></section>}
    {step === 2 && <section aria-label="Inventory file selection"><h3>Upload a static file or companion ZIP</h3><p>Static INI, extensionless hosts, YAML and canonical JSON are supported directly. ZIP companion variables stay relative to the selected inventory root. Upload limit: up to 10 MiB; deployment limits may be lower.</p><label>Inventory file or ZIP<input type="file" disabled={!!busy} onChange={event => { invalidateUpload(); setFile(event.target.files?.[0] ?? null); }} /></label><button disabled={!!busy || !file} onClick={() => { void uploadFile(); }}>Upload and inspect files</button>
      {upload && <><label>Inventory format<select value={format} disabled={!!busy} onChange={event => { invalidateParse(); setFormat(event.target.value as InventoryFormat); }}>{Object.entries(formatNames).map(([value, name]) => <option value={value} key={value}>{name}</option>)}</select></label><p>Detected: <strong>{upload.format ? formatNames[upload.format] : 'ambiguous; choose a format'}</strong> · {upload.files.length} uploaded files · {sourceFiles.length} selected sources · {ignored.length} ignored files</p><Warnings warnings={upload.warnings} />{upload.source_candidates.length === 0 && <p className="inventory-warning" role="alert">No supported static source files were found. Scripts, plugins and unsupported files cannot be selected. Upload a static INI, YAML or canonical JSON inventory.</p>}
        <fieldset className="inventory-manifest"><legend>Choose static source files in read order</legend>{upload.files.map(entry => { const index = sourceFiles.indexOf(entry.path); const candidate = upload.source_candidates.includes(entry.path); return <div className="inventory-file" key={entry.path}><label className="checkbox-label"><input type="checkbox" checked={index >= 0} disabled={!!busy || !candidate} onChange={event => { invalidateParse(); setSourceFiles(previous => event.target.checked ? [...previous, entry.path] : previous.filter(path => path !== entry.path)); }} /><span><code>{entry.path}</code><small>{entry.size} bytes · {entry.format ?? entry.role}{!candidate ? entry.role === 'companion' ? ' · companion variables' : ' · ignored' : index < 0 ? ' · ignored until selected' : ` · source ${index + 1}`}</small></span></label>{index >= 0 && <span className="inventory-order"><button aria-label={`Read ${entry.path} earlier`} disabled={!!busy || index === 0} onClick={() => order(entry.path, -1)}>↑</button><button aria-label={`Read ${entry.path} later`} disabled={!!busy || index === sourceFiles.length - 1} onClick={() => order(entry.path, 1)}>↓</button></span>}</div>; })}</fieldset><p className="muted">Selected read order: {sourceFiles.length ? sourceFiles.join(' → ') : 'none'}. Unselected source files and unsupported extras are ignored.</p></>}
      <details className="inventory-help"><summary>Supported static subset and complex inventories</summary><p>Uploaded scripts, plugins, playbooks, Jinja, Vault and shell arguments never run. Resolve unsupported trusted inventories outside this application with <code>ansible-inventory -i ./trusted-inventory --list &gt; inventory.resolved.json</code>, inspect for secrets, then upload canonical JSON.</p></details>
    </section>}
    {step === 3 && parsed && <section aria-label="Inventory mappings"><h3>Assign each host to exactly one subsystem</h3><p><strong>{parsed.hosts.length} hosts</strong> · <strong>{parsed.groups.length} groups</strong> · <strong>{parsed.process_count} process definitions found</strong>. {parsed.process_count === 0 && 'Host-only import is supported; add processes afterwards.'}</p><Warnings warnings={parsed.warnings} /><Warnings warnings={parsed.conflicts} />{parsed.omitted_variables.length > 0 && <div className="inventory-warning" role="note">Secret fields omitted: {parsed.omitted_variables.map(item => `${item.name} (${item.count})`).join(', ')}. Their values are never shown or activated.</div>}
      <datalist id="inventory-subsystems">{config.subsystems.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</datalist><p className="muted">Choose an existing subsystem ID or enter a new ID to create it. Group assignments can conflict; an explicit host assignment resolves membership for that host. Unmapped groups may be kept as tags.</p>
      <fieldset className="inventory-group-mapping"><legend>Groups to subsystems</legend>{parsed.groups.map(group => <div key={group.name}><label>{group.name} subsystem<input aria-label={`Subsystem for group ${group.name}`} list="inventory-subsystems" value={mapping.group_to_subsystem[group.name] ?? ''} disabled={!!busy} onChange={event => mapField('group_to_subsystem', group.name, event.target.value)} placeholder="No subsystem assignment" /></label><label className="checkbox-label"><input type="checkbox" checked={mapping.tag_only_groups.includes(group.name)} disabled={!!busy} onChange={event => { void releasePreview(); setMapping(previous => ({ ...previous, tag_only_groups: event.target.checked ? [...previous.tag_only_groups, group.name] : previous.tag_only_groups.filter(name => name !== group.name) })); }} />Keep {group.name} as a tag</label><small>{group.hosts.length} direct hosts · children: {group.children.join(', ') || 'none'}</small></div>)}</fieldset>
      <div className="inventory-hosts">{parsed.hosts.map(host => <article className="inventory-host" key={host.alias}><div className="inventory-host-heading"><h4>{host.alias}</h4><code>{host.address}:{host.port}</code><span>{host.user || 'SSH user not supplied'}</span></div><p className="muted">Groups: {host.groups.join(', ') || 'ungrouped'} · {host.processes.length} process definitions</p><div className="form-grid"><label>Host subsystem override<input aria-label={`Subsystem for host ${host.alias}`} list="inventory-subsystems" value={mapping.host_to_subsystem[host.alias] ?? ''} disabled={!!busy} onChange={event => mapField('host_to_subsystem', host.alias, event.target.value)} placeholder={typeof host.vars.inspector_subsystem === 'string' ? `Proposed: ${host.vars.inspector_subsystem}` : 'Use group mapping'} /></label><label>Approved credential reference<select aria-label={`Credential for host ${host.alias}`} value={mapping.credential_mapping[host.alias] ?? ''} disabled={!!busy} onChange={event => mapField('credential_mapping', host.alias, event.target.value)}><option value="">Unresolved — configure separately</option>{credentialRefs.map(ref => <option key={ref} value={ref}>{ref}</option>)}</select></label><label>Jump connection<select aria-label={`Jump connection for host ${host.alias}`} value={mapping.jump_mapping[host.alias] ?? ''} disabled={!!busy} onChange={event => { void releasePreview(); setMapping(previous => ({ ...previous, jump_mapping: { ...previous.jump_mapping, [host.alias]: event.target.value || null } })); }}><option value="">Direct connection</option>{config.connections?.filter(connection => jumpIds.includes(connection.id)).map(connection => <option key={connection.id} value={connection.id}>{connection.name} · {connection.id}</option>)}</select></label></div>{host.processes.map(process => <div className="inventory-process" key={process.id}><strong>{process.name}</strong><code>{process.id}</code>{process.pcs_resource_name && <span>PCS: {process.pcs_resource_name}</span>}<code>{process.log_source.active_path}</code><span>Parser: {process.log_source.parser_id} · {process.log_source.encoding}</span><details><summary>Log rotations and archive selectors</summary><pre>{display(process.log_source)}</pre></details></div>)}<Warnings warnings={host.warnings} /><details><summary>Field provenance for {host.alias}</summary><pre>{display(host.provenance)}</pre></details></article>)}</div>
      {parserIds.length > 0 && <fieldset className="inventory-parsers"><legend>Resolve parser references inside this system</legend>{parserIds.map(id => <label key={id}>Imported parser {id}<select aria-label={`Map inventory parser ${id}`} value={mapping.parser_mapping[id] ?? ''} disabled={!!busy} onChange={event => mapField('parser_mapping', id, event.target.value)}><option value="">Use matching parser ID if present</option>{config.parsers?.map(parser => <option key={parser.id} value={parser.id}>{parser.name} · {parser.id}</option>)}</select></label>)}</fieldset>}
      <p className="inventory-warning">Imported SSH profiles remain unapproved. Dedicated log-read credentials, host-key trust and target/root approval must be configured separately. Ansible become/sudo and shell routing arguments never grant access.</p>
    </section>}
    {step === 4 && preview && <section aria-label="Exact inventory change preview"><h3>Review the stored changes</h3><p>Preview <code data-testid="inventory-preview-id">{preview.preview_id}</code> · revision {preview.expected_revision} · expires {new Date(Number(BigInt(preview.expires_us) / 1000n)).toISOString()}</p><p>Descriptions, diagram positions, flows and unrelated processes are preserved. Missing records remain in the system and require a separate lifecycle action.</p><Warnings warnings={preview.warnings} /><Warnings warnings={preview.conflicts} /><p className="inventory-counts">{['added', 'changed', 'unchanged', 'conflicting', 'unassigned', 'absent'].map(status => <span key={status}>{preview.records.filter(record => record.status === status).length} {status}</span>)}</p><div className="inventory-diff" data-testid="inventory-diff">{preview.records.map((record, index) => <article key={`${record.kind}:${record.alias}:${record.local_id ?? index}`}><div><strong>{record.alias}{record.local_id ? ` / ${record.local_id}` : ''}</strong><span className={`inventory-record-state ${record.status}`}>{record.status}</span></div><p>{record.kind} → <code>{record.target_id}</code></p>{record.message && <p className="inventory-warning">{record.message}</p>}{record.changes.map(change => <div className="inventory-field-diff" key={change.field}><strong>{change.field}</strong><div><span>Current</span><pre>{display(change.before)}</pre></div><div><span>Proposed</span><pre>{display(change.after)}</pre></div></div>)}</article>)}</div>{!preview.can_commit && <p className="inventory-warning" role="alert">Resolve the listed conflicts or unassigned hosts, then create a fresh preview.</p>}<label className="checkbox-label inventory-confirm"><input type="checkbox" disabled={!!busy || !preview.can_commit} checked={reviewed} onChange={event => setReviewed(event.target.checked)} />I reviewed these exact changes for {config.project.name} ({projectId}), revision {preview.expected_revision}</label></section>}
    <div className="inventory-actions"><button disabled={commitStarted.current} onClick={close}>Cancel inventory import</button>{step > 1 && <button disabled={!!busy} onClick={() => { if (step === 4) { void releasePreview(); setStep(3); } else setStep(step - 1); }}>Back</button>}{step === 1 && <button className="primary" disabled={!!busy || !sourceId} onClick={() => setStep(2)}>Continue to upload</button>}{step === 2 && <button className="primary" disabled={!!busy || !upload || !sourceFiles.length} onClick={() => { void parse(); }}>Parse selected sources</button>}{step === 3 && <button className="primary" disabled={!!busy || !parsed} onClick={() => { void preparePreview(); }}>Preview exact changes</button>}{step === 4 && <button className="primary" disabled={!!busy || !preview?.can_commit || !reviewed} onClick={() => { void commit(); }}>Commit reviewed inventory</button>}</div>
  </div></Modal>;
}

function Warnings({ warnings }: { warnings: InventoryDiagnostic[] }) { return warnings?.length ? <ul className="inventory-warnings">{warnings.map((warning, index) => <li key={index}>{warning.message ?? warning.code ?? 'Inventory diagnostic'}{Object.keys(warning).some(key => key !== 'message' && key !== 'code') && <details><summary>Diagnostic details</summary><pre>{display(warning)}</pre></details>}</li>)}</ul> : null; }
