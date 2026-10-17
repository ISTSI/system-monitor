import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { message, request, write } from '../api/client';
import type { components } from '../api/schema';
import type { Config, Connection } from '../topology';
import { ErrorNotice, Modal } from './Common';

type Access = components['schemas']['AccessResponse'];
type Inspection = components['schemas']['InspectResponse'];

export default function ConnectionAccess({ config, connection, onClose, onJump }: {
  config: Config; connection: Connection; onClose: () => void; onJump: (id: string) => void;
}) {
  const [access, setAccess] = useState<Access | null>(null);
  const [inspection, setInspection] = useState<Inspection | null>(null);
  const [verified, setVerified] = useState(false);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const base = `/projects/${encodeURIComponent(config.project.id)}/connections/${encodeURIComponent(connection.id)}`;
  const load = useCallback(async () => {
    setAccess(null); setInspection(null); setVerified(false); setError('');
    try {
      const current = await request<Access>(`${base}/access`);
      if (current.config_revision !== config.project.revision) throw new Error('System configuration changed. Close this dialog and reload the system before testing.');
      setAccess(current);
    }
    catch (cause) { setError(message(cause)); }
  }, [base, config.project.revision]);
  useEffect(() => { void load(); }, [load]);

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
        setInspection(await request<Inspection>(`${base}/host-key/inspect`, { method: 'POST', body: JSON.stringify(revision), signal: AbortSignal.timeout(35000) }));
      } else if (kind === 'approve') {
        if (!inspection || !verified) return;
        setAccess(await write<Access>(`${base}/host-key/approve`, {
          ...revision, expected_trust_revision: access.host_key.revision,
          inspection_token: inspection.inspection_token, verified: true,
        }));
        setInspection(null); setVerified(false);
        setNotice('Host key approved for this saved connection.');
      } else if (kind === 'revoke') {
        setAccess(await write<Access>(`${base}/revoke`, {
          ...revision, expected_trust_revision: access.host_key.revision,
        }));
        setInspection(null); setVerified(false);
        setNotice('Host-key approval revoked. Connection tests are blocked until a key is approved.');
      } else {
        const result = await request<components['schemas']['TestResponse']>(`${base}/test`, { method: 'POST', body: JSON.stringify(revision), signal: AbortSignal.timeout(35000) });
        if (result.ssh && result.sftp) setNotice('Connection test passed: SSH authentication and SFTP are available. Configured log paths have not been checked.');
      }
    } catch (cause) { setError(message(cause)); }
    finally { setBusy(''); }
  }

  const jump = config.connections?.find(item => item.id === connection.jump_connection_id);
  return <Modal title="SSH password & connection test" onClose={() => { if (!busy) onClose(); }}>
    <p className="target-system">Target system: <strong>{config.project.name}</strong><code>{config.project.id}</code></p>
    <div className="connection-target"><strong>{connection.name}</strong><code>{connection.username}@{connection.host} · port {connection.port}</code></div>
    {jump && <p className="notice">Via jump host {jump.name}. Configure its password and approve its key first.<button disabled={!!busy} onClick={() => onJump(jump.id)}>Configure jump host</button></p>}
    {error && <ErrorNotice retry={() => { void load(); }}>{error}</ErrorNotice>}
    {notice && <p className="notice success" role="status">{notice}</p>}
    {!access ? !error && <p role="status">Loading saved connection access…</p> : <div className="connection-access">
      <section aria-label="SSH password storage">
        <h3>SSH password</h3>
        <p>Stored encrypted in the server database. Its encryption key is held separately on the server. Passwords are excluded from configuration exports and are never displayed again.</p>
        <p data-testid="ssh-password-status">{access.credential.configured ? 'A password is stored for this credential reference.' : 'No password is stored for this credential reference.'} <code>{connection.credential_ref}</code></p>
        {(config.connections?.filter(item => item.credential_ref === connection.credential_ref).length ?? 0) > 1 && <p>Replacing this password affects every connection using this reference in this system.</p>}
        {!access.vault_available && <p className="notice error">SSH password storage is unavailable. The deployment administrator must configure the server vault key.</p>}
        <form onSubmit={event => { void savePassword(event); }}>
          <label>{access.credential.configured ? 'Replacement SSH password' : 'SSH password'}<input type="password" name="ssh_password" autoComplete="new-password" required maxLength={1024} disabled={!!busy || !access.vault_available} /></label>
          <button className="primary" disabled={!!busy || !access.vault_available}>{busy === 'password' ? 'Saving password…' : 'Save SSH password'}</button>
        </form>
      </section>
      <section aria-label="SSH host key">
        <h3>Host-key verification</h3>
        <p>Inspect the server key, compare its fingerprint with a trusted source, then approve it. Inspection sends no password to the target.</p>
        <p>{access.host_key.approved ? 'Approved key' : 'No key approved for this saved connection'}</p>
        {access.host_key.approved && <code className="ssh-fingerprint">{access.host_key.algorithm} {access.host_key.fingerprint}</code>}
        <div className="connection-actions"><button disabled={!!busy} onClick={() => { void action('inspect'); }}>{busy === 'inspect' ? 'Inspecting host key…' : 'Inspect host key'}</button>{access.host_key.approved && <button disabled={!!busy} onClick={() => { void action('revoke'); }}>Revoke host-key approval</button>}</div>
        {inspection && <div className="host-key-preview"><strong>Observed key · {inspection.algorithm}</strong><code className="ssh-fingerprint">{inspection.fingerprint}</code><label className="checkbox-label"><input type="checkbox" checked={verified} disabled={!!busy} onChange={event => setVerified(event.target.checked)} />I verified this fingerprint against an independent trusted source and approve connection tests to this target.</label><button disabled={!verified || !!busy} onClick={() => { void action('approve'); }}>{busy === 'approve' ? 'Approving…' : 'Approve host key'}</button></div>}
      </section>
      <section aria-label="SSH connection test">
        <h3>Test saved connection</h3>
        <p>The application server connects to the saved host and checks SSH authentication and SFTP availability.</p>
        <button className="primary" disabled={!!busy || !access.vault_available || !access.credential.configured || !access.host_key.approved} onClick={() => { void action('test'); }}>{busy === 'test' ? 'Testing connection…' : 'Test connection'}</button>
        {(!access.credential.configured || !access.host_key.approved) && <p className="field-help">Save an SSH password and approve the host key to enable the test.</p>}
      </section>
    </div>}
    <div className="form-actions"><button disabled={!!busy} onClick={onClose}>Close</button></div>
  </Modal>;
}
