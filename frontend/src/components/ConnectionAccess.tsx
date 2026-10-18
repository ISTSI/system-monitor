import { useI18n } from '../i18n';
import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { message, request, write } from '../api/client';
import type { components } from '../api/schema';
import { formatUtcMicroseconds } from '../utcDateTime';
import type { Config, Connection } from '../topology';
import { ErrorNotice, Modal } from './Common';

type Access = components['schemas']['AccessResponse'];
type Inspection = components['schemas']['InspectResponse'];
type SourceAccess = components['schemas']['SourceAccessResponse'];
type PathTest = components['schemas']['SourcePathTestResponse'];

export default function ConnectionAccess({ config, connection, onClose, onJump }: {
  config: Config; connection: Connection; onClose: () => void; onJump: (id: string) => void;
}) {
  const { t } = useI18n();
  const [access, setAccess] = useState<Access | null>(null);
  const [inspection, setInspection] = useState<Inspection | null>(null);
  const [verified, setVerified] = useState(false);
  const [sourceAccess, setSourceAccess] = useState<SourceAccess | null>(null);
  const [rootsVerified, setRootsVerified] = useState(false);
  const [pathTest, setPathTest] = useState<PathTest | null>(null);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const base = `/projects/${encodeURIComponent(config.project.id)}/connections/${encodeURIComponent(connection.id)}`;
  const load = useCallback(async () => {
    setAccess(null); setInspection(null); setVerified(false); setSourceAccess(null); setRootsVerified(false); setPathTest(null); setError('');
    try {
      const [current, sources] = await Promise.all([request<Access>(`${base}/access`), request<SourceAccess>(`${base}/source-access`)]);
      if (current.config_revision !== config.project.revision || sources.config_revision !== config.project.revision) throw new Error('System configuration changed. Close this dialog and reload the system before testing.');
      setAccess(current); setSourceAccess(sources);
    }
    catch (cause) { setError(message(cause)); }
  }, [base, config.project.revision]);
  useEffect(() => { void load(); }, [load]);

  async function refreshSources() {
    setRootsVerified(false); setPathTest(null);
    setSourceAccess(await request<SourceAccess>(`${base}/source-access`));
  }

  async function savePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!access) return;
    const form = event.currentTarget;
    const password = String(new FormData(form).get('ssh_password') ?? '');
    form.reset();
    setBusy('password'); setError(''); setNotice('');
    try {
      setAccess(await write<Access>(`${base}/password`, {
        expected_config_revision: access.config_revision,
        expected_credential_revision: access.credential.revision, password,
      }, 'PUT'));
      setInspection(null); setVerified(false);
      await refreshSources();
      setNotice('SSH password saved. The password field has been cleared.');
    } catch (cause) { setError(message(cause)); }
    finally { setBusy(''); }
  }

  async function action(kind: 'inspect' | 'approve' | 'test' | 'revoke') {
    if (!access) return;
    setBusy(kind); setError(''); setNotice('');
    try {
      const revision = { expected_config_revision: access.config_revision };
      if (kind === 'inspect') {
        setInspection(null); setVerified(false);
        await refreshSources();
        setInspection(await request<Inspection>(`${base}/host-key/inspect`, { method: 'POST', body: JSON.stringify(revision), signal: AbortSignal.timeout(35000) }));
      } else if (kind === 'approve') {
        if (!inspection || !verified) return;
        setAccess(await write<Access>(`${base}/host-key/approve`, {
          ...revision, expected_trust_revision: access.host_key.revision,
          inspection_token: inspection.inspection_token, verified: true,
        }));
        setInspection(null); setVerified(false);
        await refreshSources();
        setNotice('Host key approved for this saved connection.');
      } else if (kind === 'revoke') {
        setAccess(await write<Access>(`${base}/revoke`, {
          ...revision, expected_trust_revision: access.host_key.revision,
        }));
        setInspection(null); setVerified(false);
        await refreshSources();
        setNotice('Host-key approval revoked. Connection tests are blocked until a key is approved.');
      } else {
        const result = await request<components['schemas']['TestResponse']>(`${base}/test`, { method: 'POST', body: JSON.stringify(revision), signal: AbortSignal.timeout(35000) });
        if (result.ssh && result.sftp) setNotice('Connection test passed: SSH authentication and SFTP are available. Configured log paths have not been checked.');
      }
    } catch (cause) { setError(message(cause)); }
    finally { setBusy(''); }
  }

  async function sourceAction(kind: 'approve' | 'revoke' | 'test') {
    if (!sourceAccess || (kind === 'approve' && !rootsVerified)) return;
    setBusy(`source-${kind}`); setError(''); setNotice(''); setPathTest(null);
    try {
      const revision = { expected_config_revision: sourceAccess.config_revision };
      if (kind === 'test') {
        setPathTest(await request<PathTest>(`${base}/source-access/test`, { method: 'POST', body: JSON.stringify(revision), signal: AbortSignal.timeout(65000) }));
      } else {
        setSourceAccess(await write<SourceAccess>(`${base}/source-access/${kind}`, {
          ...revision, expected_approval_revision: sourceAccess.approval.revision,
          ...(kind === 'approve' ? { verified: true } : {}),
        }));
        setRootsVerified(false);
        setNotice(kind === 'approve' ? 'Configured target and log roots approved for collection in this system.' : 'Source approval revoked. New remote collection is blocked for this connection.');
      }
    } catch (cause) { setError(message(cause)); }
    finally { setBusy(''); }
  }

  const jump = config.connections?.find(item => item.id === connection.jump_connection_id);
  return <Modal title={t("SSH password & connection test")} onClose={() => { if (!busy) onClose(); }}>
    <p className="target-system">{t("Target system:")} <strong>{config.project.name}</strong><code>{config.project.id}</code></p>
    <div className="connection-target"><strong>{connection.name}</strong><code>{connection.username}@{connection.host} {t("· port")} {connection.port}</code></div>
    {jump && <p className="notice">{t("Via jump host")} {jump.name}{t(". Configure its password and approve its key first.")}<button title={t("Open password and host-key settings for the jump host.")} disabled={!!busy} onClick={() => onJump(jump.id)}>{t("Configure jump host")}</button></p>}
    {error && <ErrorNotice retry={() => { void load(); }}>{t(error)}</ErrorNotice>}
    {notice && <p className="notice success" role="status">{t(notice)}</p>}
    {!access ? !error && <p role="status">{t("Loading saved connection access…")}</p> : <div className="connection-access">
      <section aria-label={t("SSH password storage")}>
        <h3>{t("SSH password")}</h3>
        <p>{t("Stored encrypted in the server database. Its encryption key is held separately on the server. Passwords are excluded from configuration exports and are never displayed again.")}</p>
        <p data-testid="ssh-password-status">{access.credential.configured ? t("A password is stored for this credential reference.") : t("No password is stored for this credential reference.")} <code>{connection.credential_ref}</code></p>
        {(config.connections?.filter(item => item.credential_ref === connection.credential_ref).length ?? 0) > 1 && <p>{t("Replacing this password affects every connection using this reference in this system.")}</p>}
        {!access.vault_available && <p className="notice error">{t("SSH password storage is unavailable. The deployment administrator must configure the server vault key.")}</p>}
        <form onSubmit={event => { void savePassword(event); }}>
          <label>{access.credential.configured ? t("Replacement SSH password") : t("SSH password")}<input type="password" name="ssh_password" autoComplete="new-password" required maxLength={1024} disabled={!!busy || !access.vault_available} /></label>
          <button title={t("Store this SSH password securely for the saved credential reference.")} className="primary" disabled={!!busy || !access.vault_available}>{busy === 'password' ? t("Saving password…") : t("Save SSH password")}</button>
        </form>
      </section>
      <section aria-label={t("SSH host key")}>
        <h3>{t("Host-key verification")}</h3>
        <p>{t("Inspect the server key, compare its fingerprint with a trusted source, then approve it. Inspection sends no password to the target.")}</p>
        <p>{access.host_key.approved ? t("Approved key") : t("No key approved for this saved connection")}</p>
        {access.host_key.approved && <code className="ssh-fingerprint">{access.host_key.algorithm} {access.host_key.fingerprint}</code>}
        <div className="connection-actions"><button title={t("Read the target SSH key fingerprint for independent verification.")} disabled={!!busy} onClick={() => { void action('inspect'); }}>{busy === 'inspect' ? t("Inspecting host key…") : t("Inspect host key")}</button>{access.host_key.approved && <button title={t("Remove trust in this saved SSH host key.")} disabled={!!busy} onClick={() => { void action('revoke'); }}>{t("Revoke host-key approval")}</button>}</div>
        {inspection && <div className="host-key-preview"><strong>{t("Observed key ·")} {inspection.algorithm}</strong><code className="ssh-fingerprint">{inspection.fingerprint}</code><label className="checkbox-label"><input type="checkbox" checked={verified} disabled={!!busy} onChange={event => setVerified(event.target.checked)} />{t("I verified this fingerprint against an independent trusted source and approve connection tests to this target.")}</label><button title={t("Trust the independently verified SSH key for this target.")} disabled={!verified || !!busy} onClick={() => { void action('approve'); }}>{busy === 'approve' ? t("Approving…") : t("Approve host key")}</button></div>}
      </section>
      <section aria-label={t("SSH connection test")}>
        <h3>{t("Test saved connection")}</h3>
        <p>{t("The application server connects to the saved host and checks SSH authentication and SFTP availability.")}</p>
        <button title={t("Check SSH authentication and SFTP access using saved credentials.")} className="primary" disabled={!!busy || !access.vault_available || !access.credential.configured || !access.host_key.approved} onClick={() => { void action('test'); }}>{busy === 'test' ? t("Testing connection…") : t("Test connection")}</button>
        {(!access.credential.configured || !access.host_key.approved) && <p className="field-help">{t("Save an SSH password and approve the host key to enable the test.")}</p>}
      </section>
      {sourceAccess && <section aria-label={t("Configured source approval")}>
        <h3>{sourceAccess.manual_confirmation_required ? t("Approve target and log roots") : t("Configured target and log roots")}</h3>
        {sourceAccess.manual_confirmation_required ? <p>{t("Review the configured target and roots for")} <strong>{config.project.name}</strong>{t(". Approval applies only to this system and saved configuration. Changing credentials, trust, routing or source definitions requires a new approval.")}</p> : <p>{t("Additional security measures are disabled. Saved changes to paths and parsers apply automatically. SSH host keys still require explicit verification.")}</p>}
        <p className="source-approval-state" data-testid="source-approval-status">{sourceAccess.manual_confirmation_required ? sourceAccess.approval.approved ? t("Approved for remote collection.") : t("Remote collection is blocked until this target and its roots are approved.") : sourceAccess.approval.approved ? t("Ready for remote collection. Manual source confirmation is disabled.") : t("Remote collection requires stored credentials and explicitly verified SSH host keys.")}</p>
        {sourceAccess.approval.approved && sourceAccess.approval.expires_us && <p>{t("Approval expires")} {formatUtcMicroseconds(sourceAccess.approval.expires_us)} UTC.</p>}
        <dl className="source-approval-details"><dt>{t("Target")}</dt><dd><code>{connection.host}:{connection.port}</code>{jump && <span> {t("via")} {jump.name}</span>}</dd><dt>{t("Configured log roots")}</dt><dd>{sourceAccess.roots.length ? <ul>{sourceAccess.roots.map(root => <li key={root}><code>{root}</code></li>)}</ul> : t("No log roots configured.")}</dd><dt>{t("Configured sources")}</dt><dd>{sourceAccess.process_ids.length ? <ul>{sourceAccess.process_ids.map(id => { const process = config.processes.find(item => item.id === id); return <li key={id}>{process?.name ?? id}<code>{process?.log_source?.active_path ?? id}</code></li>; })}</ul> : t("This connection has no configured log sources.")}</dd></dl>
        {sourceAccess.roots.length > 0 && sourceAccess.process_ids.length > 0 && <>
          {sourceAccess.manual_confirmation_required && !sourceAccess.approval.approved && <label className="checkbox-label"><input type="checkbox" checked={rootsVerified} disabled={!!busy} onChange={event => setRootsVerified(event.target.checked)} />{t("I verified this target and these configured log roots and authorize read-only collection for this system.")}</label>}
          <div className="connection-actions">{sourceAccess.manual_confirmation_required && (sourceAccess.approval.approved ? <button title={t("Withdraw permission to collect logs from this configured target.")} disabled={!!busy} onClick={() => { void sourceAction('revoke'); }}>{t("Revoke source approval")}</button> : <button title={t("Authorize read-only collection from this target and its log roots.")} disabled={!!busy || !rootsVerified || !access.credential.configured || !access.host_key.approved} onClick={() => { void sourceAction('approve'); }}>{busy === 'source-approve' ? t("Approving sources…") : t("Approve target and log roots")}</button>)}<button title={t("Check read access to the configured log files and archives.")} className="primary" disabled={!!busy || !sourceAccess.approval.approved} onClick={() => { void sourceAction('test'); }}>{busy === 'source-test' ? t("Checking configured paths…") : t("Test configured log paths")}</button></div>
          {(!access.credential.configured || !access.host_key.approved) && <p className="field-help">{t("Save the password and approve the host key before testing configured log paths.")}</p>}
        </>}
        {pathTest && <div className="source-path-results" role="status"><strong>{t("Configured path checks ·")} {config.project.name}</strong>{pathTest.processes.map(result => <div key={result.process_id}><strong>{config.processes.find(item => item.id === result.process_id)?.name ?? result.process_id}</strong><span>{result.accessible ? t("Accessible") : t("Access failed")} · {result.candidate_count} {t("candidates ·")} {result.estimated_bytes} {t("estimated bytes")}</span>{result.warning && <p className={result.accessible ? 'field-help' : 'history-warning'}>{result.warning}</p>}</div>)}</div>}
      </section>}
    </div>}
    <div className="form-actions"><button title={t("Close connection access settings.")} disabled={!!busy} onClick={onClose}>{t("Close")}</button></div>
  </Modal>;
}
