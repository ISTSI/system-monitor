import { useI18n } from '../i18n';
import { useEffect, useRef, useState } from 'react';
import { csrf, message, write } from '../api/client';
import { formatUtcTimestamp } from '../utcDateTime';
import type { BundlePreview } from '../investigation';
import { ErrorNotice, Modal } from './Common';

export default function BundleTransfer({ projectId, systemName, investigationId, onOpen }: {
  projectId: string; systemName: string; investigationId?: string; onOpen: (id: string) => void;
}) {
  const { t } = useI18n();
  const base = `/projects/${encodeURIComponent(projectId)}`;
  const [mode, setMode] = useState<'export' | 'import' | null>(null);
  const [terms, setTerms] = useState(''); const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<BundlePreview | null>(null);
  const [reviewed, setReviewed] = useState(false); const [busy, setBusy] = useState(''); const [error, setError] = useState('');
  const alive = useRef(true); const version = useRef(0);
  const heldPreview = useRef<BundlePreview | null>(null); const cancelling = useRef<Promise<unknown>>(Promise.resolve());
  useEffect(() => { alive.current = true; return () => {
    alive.current = false; version.current += 1;
    const pending = heldPreview.current; heldPreview.current = null;
    if (pending) void write(`${base}/bundles/previews/${encodeURIComponent(pending.preview_id)}/cancel`).catch(() => {});
  }; }, [base]);
  function releasePreview() {
    const pending = heldPreview.current; heldPreview.current = null;
    if (pending) cancelling.current = cancelling.current.then(() => write(`${base}/bundles/previews/${encodeURIComponent(pending.preview_id)}/cancel`)).catch(() => {});
    return cancelling.current;
  }
  function invalidate() { version.current += 1; void releasePreview(); setPreview(null); setReviewed(false); }
  function open(next: 'export' | 'import') { invalidate(); setMode(next); setError(''); }
  async function prepare() {
    const current = ++version.current; setBusy('Preparing preview'); setError(''); setPreview(null); setReviewed(false);
    try {
      await releasePreview();
      if (!alive.current || current !== version.current) return;
      let result: BundlePreview;
      if (mode === 'export' && investigationId) {
        result = await write<BundlePreview>(`${base}/bundles/export/preview`, { investigation_id: investigationId, redact_terms: terms.split('\n').filter(term => term !== '') });
      } else {
        if (!file) throw new Error('Choose an investigation ZIP bundle.');
        if (file.size > 512 * 1024 * 1024) throw new Error('The bundle exceeds the 512 MiB upload limit.');
        const token = await csrf();
        const response = await fetch(`/api/v1${base}/bundles/import/preview`, { method: 'POST', credentials: 'same-origin', cache: 'no-store', headers: { 'Content-Type': 'application/zip', 'X-CSRF-Token': token }, body: file, signal: AbortSignal.timeout(120000) });
        const body = await response.json() as BundlePreview & { error?: { message?: string } };
        if (!response.ok) throw new Error(body.error?.message ?? 'The bundle was rejected. No investigation was imported.');
        result = body;
      }
      if (alive.current && current === version.current && result.project_id === projectId) { heldPreview.current = result; setPreview(result); }
      else if (result.project_id === projectId) void write(`${base}/bundles/previews/${encodeURIComponent(result.preview_id)}/cancel`).catch(() => {});
    } catch (cause) { if (alive.current && current === version.current) setError(message(cause)); }
    finally { if (alive.current && current === version.current) setBusy(''); }
  }
  async function confirm() {
    if (!preview || !reviewed) return;
    const current = version.current; setBusy(mode === 'export' ? 'Preparing download' : 'Importing offline copy'); setError('');
    try {
      if (mode === 'export') {
        const value = await write<{ project_id: string; url: string }>(`${base}/bundles/export`, { preview_id: preview.preview_id });
        if (!alive.current || current !== version.current || value.project_id !== projectId || !value.url.startsWith(`/api/v1${base}/bundle-downloads/`)) return;
        const link = document.createElement('a'); link.href = value.url; link.download = 'investigation.zip'; link.click();
        // The browser owns the streaming download now. Cancelling this preview
        // would revoke its grant before that download can finish.
        heldPreview.current = null; setPreview(null);
        setMode(null);
      } else {
        const value = await write<{ project_id: string; investigation_id: string; offline: boolean }>(`${base}/bundles/import`, { preview_id: preview.preview_id });
        if (alive.current && current === version.current && value.project_id === projectId && value.offline) { heldPreview.current = null; setPreview(null); setMode(null); onOpen(value.investigation_id); }
      }
    } catch (cause) { if (alive.current && current === version.current) setError(message(cause)); }
    finally { if (alive.current && current === version.current) setBusy(''); }
  }
  return <><div className="bundle-actions"><button title={t("Prepare a redacted offline bundle of this investigation.")} disabled={!investigationId} onClick={() => open('export')}>{t("Export investigation bundle")}</button><button title={t("Preview an offline bundle before importing a private copy.")} onClick={() => open('import')}>{t("Import offline bundle")}</button></div>{mode && <Modal title={mode === 'export' ? t("Preview redacted investigation bundle") : t("Preview offline investigation import")} onClose={() => { if (!busy) { invalidate(); setMode(null); } }}>
    <p className="target-system">{t("Selected system:")} <strong>{systemName}</strong><code>{projectId}</code></p>
    {error && <ErrorNotice>{t(error)}</ErrorNotice>}
    {mode === 'export' ? <><p>{t("Save your workspace and annotations first. Redaction changes the exported copy. Credentials, SSH trust and active connection profiles are always excluded.")}</p><label>{t("Redact literal values (one per line)")}<textarea aria-label={t("Redact literal values (one per line)")} value={terms} rows={4} maxLength={10240} disabled={!!busy} onChange={event => { setTerms(event.target.value); invalidate(); }} placeholder={t("Sensitive IDs, labels, paths or note text")} /></label><p className="muted">{t("Review all metadata, source names, context, notes and topology text. Automatic redaction cannot identify every sensitive value.")}</p></> : <><p>{t("This creates your private offline investigation in the selected system, preserving origin provenance. Import starts no host connection.")}</p><label>{t("Investigation bundle ZIP")}<input type="file" disabled={!!busy} accept=".zip,application/zip" onChange={event => { setFile(event.target.files?.[0] ?? null); invalidate(); }} /></label></>}
    <button title={mode === 'export' ? t("Generate a preview with the requested redactions.") : t("Validate the selected ZIP and preview its investigation data.")} disabled={!!busy} onClick={() => { void prepare(); }}>{mode === 'export' ? t("Preview redacted bundle") : t("Validate and preview bundle")}</button>
    <span role="status">{t(busy)}</span>
    {preview && <section className="bundle-preview" aria-label={t("Bundle content preview")}><p>{t("SHA-256")} <code>{preview.digest}</code></p><p>{t("Preview expires")} {formatUtcTimestamp(preview.expires_at)} UTC</p>{preview.warnings.map((warning, index) => <p className="history-warning" key={index}>{warning}</p>)}<pre data-testid="bundle-preview-document">{JSON.stringify(preview.document, null, 2)}</pre><label className="checkbox-label"><input type="checkbox" checked={reviewed} onChange={event => setReviewed(event.target.checked)} />{t("I reviewed this exact preview")}</label><p className="target-system">{t("Selected system:")} <strong>{systemName}</strong><code>{projectId}</code></p><button title={mode === 'export' ? t("Download the exact redacted bundle you reviewed.") : t("Create a private offline investigation from this preview.")} className="primary" disabled={!!busy || !reviewed} onClick={() => { void confirm(); }}>{mode === 'export' ? t("Download previewed bundle") : t("Import private offline copy")}</button></section>}
  </Modal>}</>;
}
