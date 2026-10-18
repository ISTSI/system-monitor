import { useI18n } from '../i18n';
import { useState } from 'react';
import { message, request, write } from '../api/client';
import { type Config } from '../topology';
import { ErrorNotice, Modal } from './Common';

type Preview = { preview_id: string; project_id: string; expected_revision: number; warnings: string[]; source_project_id: string; target_project_id: string; changes: Record<string, unknown>; requires_delete_confirmation: boolean; requires_reparent_confirmation: boolean };
export async function exportConfig(projectId: string, format: 'json' | 'yaml') {
  const result = await request<{ content: string; format: string }>(`/projects/${encodeURIComponent(projectId)}/config/export?format=${format}`);
  const url = URL.createObjectURL(new Blob([result.content], { type: format === 'json' ? 'application/json' : 'application/yaml' }));
  const link = document.createElement('a'); link.href = url; link.download = `${projectId}.project.${format}`; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function ConfigImport({ config, revision, onClose, onCommitted }: { config: Config; revision: number; onClose: () => void; onCommitted: () => Promise<void> }) {
  const { t } = useI18n();
  const [format, setFormat] = useState<'json' | 'yaml'>('json');
  const [content, setContent] = useState('');
  const [preview, setPreview] = useState<Preview | null>(null);
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const [deletions, setDeletions] = useState(false); const [reparent, setReparent] = useState(false); const [remap, setRemap] = useState(false);
  const base = `/projects/${encodeURIComponent(config.project.id)}/config`;
  function reset() { setPreview(null); setDeletions(false); setReparent(false); setRemap(false); setError(''); }
  async function read(file?: File) {
    reset(); if (!file) return;
    if (file.size > 10 * 1024 * 1024) { setError('Configuration exceeds the 10 MiB upload limit.'); return; }
    setContent(await file.text()); setFormat(/\.ya?ml$/i.test(file.name) ? 'yaml' : 'json');
  }
  async function createPreview() {
    setBusy(true); setError('');
    try { setPreview(await write<Preview>(`${base}/preview`, { expected_revision: revision, content, format })); } catch (cause) { setError(message(cause)); } finally { setBusy(false); }
  }
  async function commit() {
    if (!preview) return; setBusy(true); setError('');
    try { await write(`${base}/commit`, { preview_id: preview.preview_id, expected_revision: revision, confirmed_deletions: deletions, reparent, confirm_project_remap: remap }); await onCommitted(); onClose(); } catch (cause) { setError(message(cause)); } finally { setBusy(false); }
  }
  return <Modal title={t("Import configuration")} onClose={onClose}><p className="target-system">{t("Target system:")} <strong>{config.project.name}</strong><code>{config.project.id} {t("· revision")} {revision}</code></p><p>{t("Import version 2 YAML/JSON or visibly convert a version 1 configuration. Connections remain unapproved; credential references do not import passwords.")}</p>{error && <ErrorNotice>{t(error)}</ErrorNotice>}<div className="import-fields"><div className="form-grid"><label>{t("Configuration file")}<input type="file" accept=".json,.yaml,.yml,application/json,application/yaml" onChange={event => { void read(event.target.files?.[0]); }} /></label><label>{t("Configuration format")}<select value={format} onChange={event => { setFormat(event.target.value as 'json' | 'yaml'); reset(); }}><option value="json">JSON</option><option value="yaml">YAML</option></select></label></div><label>{t("Configuration content")}<textarea className="config-text" rows={10} value={content} onChange={event => { setContent(event.target.value); reset(); }} placeholder={t("Paste an editable project configuration…")} /></label></div>
    {preview && <section className="import-preview" aria-label={t("Configuration preview")}><h3>{t("Validated import preview")}</h3><p>{t("Source")} <code>{preview.source_project_id}</code> {t("→ target")} <code>{preview.target_project_id}</code></p><pre>{JSON.stringify(preview.changes, null, 2)}</pre>{preview.warnings?.length > 0 && <ul>{preview.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul>}{preview.requires_delete_confirmation && <label className="checkbox-label"><input type="checkbox" checked={deletions} onChange={event => setDeletions(event.target.checked)} />{t("Confirm the listed deletions and dependent view/flow changes")}</label>}{preview.requires_reparent_confirmation && <label className="checkbox-label"><input type="checkbox" checked={reparent} onChange={event => setReparent(event.target.checked)} />{t("Confirm explicit parent changes inside this target system")}</label>}{preview.source_project_id !== preview.target_project_id && <label className="checkbox-label"><input type="checkbox" checked={remap} onChange={event => setRemap(event.target.checked)} />{t("Map the source project identity to this explicitly selected target system")}</label>}</section>}
    <div className="form-actions"><button title={t("Close without importing configuration.")} onClick={onClose}>{t("Cancel")}</button>{preview ? <button title={t("Apply the reviewed changes to this system configuration.")} className="primary" disabled={busy || (preview.requires_delete_confirmation && !deletions) || (preview.requires_reparent_confirmation && !reparent) || (preview.source_project_id !== preview.target_project_id && !remap)} onClick={() => { void commit(); }}>{busy ? t("Committing…") : t("Commit configuration")}</button> : <button title={t("Validate this configuration and review the proposed changes.")} className="primary" disabled={busy || !content.trim()} onClick={() => { void createPreview(); }}>{busy ? t("Validating…") : t("Preview configuration")}</button>}</div>
  </Modal>;
}
