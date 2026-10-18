import { useI18n } from '../i18n';
import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { message, request, write } from '../api/client';
import type { Session, Settings, ThemeMode, User } from '../api/types';
import { ErrorNotice, Modal } from './Common';
import type { LanguagePreference } from '../i18n';

export function PasswordDialog({ onClose, onChanged, forced = false }: { onClose: () => void; onChanged: () => void; forced?: boolean }) {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = event.currentTarget; const data = new FormData(form);
    if (data.get('new_password') !== data.get('confirm_password')) { setError('New passwords do not match.'); return; }
    setBusy(true); setError('');
    try { await write('/me/password', { current_password: String(data.get('current_password')), new_password: String(data.get('new_password')) }); form.reset(); onChanged(); }
    catch (cause) { setError(message(cause)); } finally { setBusy(false); }
  }
  const contents = <><p className="muted">{forced ? t("Your Administrator requires a new password before you continue.") : t("Changing your password signs out every window. Sign in again with the new password.")}</p>{error && <ErrorNotice>{error}</ErrorNotice>}<form onSubmit={(event) => { void submit(event); }}><label>{t("Current password")}<input name="current_password" type="password" autoComplete="current-password" required maxLength={1024} autoFocus /></label><label>{t("New password")}<input name="new_password" type="password" autoComplete="new-password" minLength={12} maxLength={1024} required aria-describedby="password-help" /></label><p id="password-help" className="field-help">{t("Use at least 12 characters. Passwords are write-only.")}</p><label>{t("Confirm new password")}<input name="confirm_password" type="password" autoComplete="new-password" minLength={12} maxLength={1024} required /></label><div className="form-actions"><button type="button" onClick={onClose}>{forced ? t("Sign out") : t("Cancel")}</button><button className="primary" disabled={busy}>{busy ? t("Changing…") : t("Change password")}</button></div></form></>;
  return forced ? <section className="login-card"><p className="eyebrow">{t("ACCOUNT SECURITY")}</p><h1>{t("Change your password")}</h1>{contents}</section> : <Modal title={t("Change password")} onClose={onClose}>{contents}</Modal>;
}

export function PreferencesDialog({ appearance, appearanceBusy, appearanceError, onAppearanceChange, onAppearanceRetry, language, languageBusy, languageError, onLanguageChange, onLanguageRetry, onClose }: { appearance: ThemeMode; appearanceBusy: boolean; appearanceError: string; onAppearanceChange: (mode: ThemeMode) => void; onAppearanceRetry?: () => void; language: LanguagePreference; languageBusy: boolean; languageError: string; onLanguageChange: (language: LanguagePreference) => void; onLanguageRetry?: () => void; onClose: () => void }) {
  const { t } = useI18n();
  return <Modal title={t("Preferences")} onClose={onClose}>
    <section className="settings-section" aria-label={t("Personal appearance")}>
      <h3>{t("Appearance")}</h3><p className="muted">{t("Your appearance preference applies to every window for this account.")}</p>
      {appearanceError && <ErrorNotice retry={onAppearanceRetry}>{appearanceError}</ErrorNotice>}
      <label>{t("Appearance")}<select aria-label={t("Appearance")} value={appearance} disabled={appearanceBusy} onChange={(event) => onAppearanceChange(event.target.value as ThemeMode)}><option value="default">{t("Application default")}</option><option value="light">{t("Light · Cool Slate")}</option><option value="dark">{t("Dark · Graphite Dusk")}</option><option value="system">{t("System")}</option></select></label>
      <p className="field-help">{t("Choose a theme for your account, or follow the application default set by an Administrator.")}</p>
      <p className="field-help" role="status">{appearanceBusy ? t("Saving appearance…") : t("Changes save automatically.")}</p>
    </section>
    <section className="settings-section" aria-label={t("Personal language")}>
      <h3>{t("Language")}</h3><p className="muted">{t("Your language preference applies to every window for this account.")}</p>
      {languageError && <ErrorNotice retry={onLanguageRetry}>{languageError}</ErrorNotice>}
      <label>{t("Language")}<select aria-label={t("Language")} value={language} disabled={languageBusy} onChange={event => onLanguageChange(event.target.value as LanguagePreference)}><option value="default">{t("Application default")}</option><option value="en" lang="en">{t("English")}</option><option value="pl" lang="pl">{t("Polski")}</option></select></label>
      <p className="field-help">{t("Choose a language for your account, or follow the application default set by an Administrator.")}</p>
      <p className="field-help" role="status">{languageBusy ? t("Saving language…") : t("Changes save automatically.")}</p>
    </section>
    <div className="form-actions"><button type="button" onClick={onClose}>{t("Close")}</button></div>
  </Modal>;
}

export function SettingsDialog({ onClose, onSaved }: { onClose: () => void; onSaved: (settings: Settings) => void }) {
  const { t } = useI18n();
  const [settings, setSettings] = useState<Settings | null>(null); const [error, setError] = useState(''); const [busy, setBusy] = useState(false); const [saved, setSaved] = useState(false); const [diagnostics, setDiagnostics] = useState<Record<string, unknown> | null>(null);
  const load = useCallback(async () => { setError(''); try { const [current, status] = await Promise.all([request<Settings>('/admin/settings'), request<Record<string, unknown>>('/admin/database/status')]); setSettings(current); setDiagnostics(status); } catch (cause) { setError(message(cause)); } }, []);
  useEffect(() => { void load(); }, [load]);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!settings) return; const data = new FormData(event.currentTarget); setBusy(true); setError(''); setSaved(false);
    try { const result = await write<Settings>('/admin/settings', { branding: String(data.get('branding')), default_theme_mode: String(data.get('default_theme_mode')), default_language: String(data.get('default_language')), additional_security_measures: data.has('additional_security_measures'), expected_revision: settings.revision }, 'PATCH'); setSettings(result); setSaved(true); onSaved(result); }
    catch (cause) { setError(message(cause)); } finally { setBusy(false); }
  }
  return <Modal title={t("Settings")} onClose={onClose}>
    <section className="settings-section" aria-label={t("Shared application settings")}>
      <h3>{t("Application settings")}</h3><p className="muted">{t("Administrator changes apply to the deployment. Explicit personal appearance and language choices stay unchanged.")}</p>
      {error && <ErrorNotice retry={() => { void load(); }}>{error}</ErrorNotice>}
      {saved && <p className="notice success" role="status">{t("Application settings saved.")}</p>}
      {settings ? <form onSubmit={(event) => { void submit(event); }}>
        <label>{t("Product name")}<input name="branding" required maxLength={128} defaultValue={settings.branding} /></label>
        <label>{t("Application default appearance")}<select name="default_theme_mode" defaultValue={settings.default_theme_mode}><option value="dark">{t("Dark · Graphite Dusk")}</option><option value="light">{t("Light · Cool Slate")}</option><option value="system">{t("Follow browser system preference")}</option></select></label>
        <p className="field-help">{t("This theme is used on the signed-out screen and for new accounts. People using “Application default” also follow this choice. Change your own theme in Preferences under your user menu.")}</p>
        <label>{t("Application default language")}<select name="default_language" defaultValue={settings.default_language}><option value="en" lang="en">{t("English")}</option><option value="pl" lang="pl">{t("Polski")}</option></select></label>
        <p className="field-help">{t("This language is used on the signed-out screen and for accounts using “Application default”. Change your own language in Preferences under your user menu.")}</p>
        <label className="checkbox-label"><input type="checkbox" name="additional_security_measures" checked={settings.additional_security_measures} onChange={event => { const checked = event.target.checked; setSettings(current => current ? { ...current, additional_security_measures: checked } : current); setSaved(false); }} aria-describedby="additional-security-help" disabled={busy} />{t("Additional security measures")}</label>
        <p id="additional-security-help" className="field-help">{t("Require Administrator confirmation of the target and log roots after configuration changes, including paths and parsers. When unchecked, saved changes apply automatically. SSH host keys always require explicit verification.")}</p>
        <div className="read-only-settings"><h3>{t("Database · server managed")}</h3><p>{t("The database endpoint and secret files are set in deployment configuration. Changing them requires an operator-managed restart.")}</p>{diagnostics && <dl>{Object.entries(diagnostics).filter(([, value]) => ['string', 'number', 'boolean'].includes(typeof value)).map(([key, value]) => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{String(value)}</dd></div>)}</dl>}</div>
        <div className="form-actions"><span className="muted">{t("Revision ")}{settings.revision}</span><button className="primary" disabled={busy}>{busy ? t("Saving…") : t("Save application settings")}</button></div>
      </form> : !error && <p role="status">{t("Loading application settings…")}</p>}
    </section>
    <div className="form-actions"><button type="button" onClick={onClose}>{t("Close")}</button></div>
  </Modal>;
}

export function UsersDialog({ session, onClose, onSelfRevoked }: { session: Session; onClose: () => void; onSelfRevoked: () => void }) {
  const { t } = useI18n();
  const [items, setItems] = useState<User[]>([]); const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [editing, setEditing] = useState<User | null>(null); const [creating, setCreating] = useState(false); const [resetting, setResetting] = useState<User | null>(null); const [notice, setNotice] = useState('');
  const load = useCallback(async () => { setError(''); try { setItems((await request<{ items: User[] }>('/admin/users')).items); } catch (cause) { setError(message(cause)); } }, []);
  useEffect(() => { void load(); }, [load]);
  async function mutate(user: User, action: string, body: Record<string, unknown>) { setBusy(true); setError(''); setNotice(''); try { const updated = await write<User>(`/admin/users/${encodeURIComponent(user.user_id)}${action}`, { expected_auth_version: user.auth_version, ...body }, action ? 'POST' : 'PATCH'); if (user.user_id === session.user_id && updated.auth_version !== user.auth_version) { onSelfRevoked(); return; } setEditing(null); setResetting(null); setNotice(updated.auth_version === user.auth_version ? 'Account unchanged.' : 'Account updated. Its existing sessions have ended.'); await load(); } catch (cause) { setError(message(cause)); } finally { setBusy(false); } }
  async function create(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const form = event.currentTarget; const data = new FormData(form); setBusy(true); setError(''); try { await write('/admin/users', { username: String(data.get('username')), display_name: String(data.get('display_name')), role: String(data.get('role')), password: String(data.get('password')), must_change_password: data.get('must_change_password') === 'on' }); form.reset(); setCreating(false); setNotice('Local account created. Share the initial password through your approved channel.'); await load(); } catch (cause) { setError(message(cause)); } finally { setBusy(false); } }
  function edit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); if (!editing) return; const data = new FormData(event.currentTarget); void mutate(editing, '', { role: String(data.get('role')), enabled: data.get('enabled') === 'on' }); }
  function reset(event: FormEvent<HTMLFormElement>) { event.preventDefault(); if (!resetting) return; const form = event.currentTarget; const data = new FormData(form); void mutate(resetting, '/reset-password', { password: String(data.get('password')), must_change_password: data.get('must_change_password') === 'on' }).then(() => form.reset()); }
  return <Modal title={t("Local accounts")} onClose={onClose}><p className="muted">{t("Roles apply to every configured system. Disabling an account preserves its owned history.")}</p>{error && <ErrorNotice retry={() => { void load(); }}>{error}</ErrorNotice>}{notice && <p className="notice success" role="status">{t(notice)}</p>}{creating ? <form onSubmit={(event) => { void create(event); }}><h3>{t("Create local account")}</h3><div className="form-grid"><label>{t("Username")}<input name="username" required maxLength={128} autoComplete="off" /></label><label>{t("Display name")}<input name="display_name" required maxLength={128} /></label></div><label>{t("Account role")}<select name="role" defaultValue="inspector"><option value="inspector">{t("Inspector · read shared configuration")}</option><option value="administrator">{t("Administrator · manage shared configuration")}</option></select></label><label>{t("Initial password")}<input name="password" type="password" required minLength={12} maxLength={1024} autoComplete="new-password" /></label><label className="checkbox-label"><input name="must_change_password" type="checkbox" defaultChecked />{t("Require password change at first sign in")}</label><div className="form-actions"><button type="button" onClick={() => setCreating(false)}>{t("Cancel")}</button><button className="primary" disabled={busy}>{t("Create local account")}</button></div></form> : editing ? <form onSubmit={edit}><h3>{t("Edit ")}{editing.display_name || editing.username}</h3><p className="target-system">{editing.username}<code>{editing.user_id}</code></p><label>{t("Account role")}<select name="role" defaultValue={editing.role}><option value="inspector">{t("Inspector")}</option><option value="administrator">{t("Administrator")}</option></select></label><label className="checkbox-label"><input name="enabled" type="checkbox" defaultChecked={editing.enabled} />{t("Account enabled")}</label><p className="field-help">{t("Saving a change revokes this account’s sessions. The last enabled Administrator is protected.")}</p><div className="form-actions"><button type="button" onClick={() => setEditing(null)}>{t("Cancel")}</button><button className="primary" disabled={busy}>{t("Save account")}</button></div></form> : resetting ? <form onSubmit={reset}><h3>{t("Reset password for ")}{resetting.display_name || resetting.username}</h3><p>{resetting.username}</p><label>{t("Temporary password")}<input name="password" type="password" autoComplete="new-password" required minLength={12} maxLength={1024} /></label><label className="checkbox-label"><input name="must_change_password" type="checkbox" defaultChecked />{t("Require password change at next sign in")}</label><div className="form-actions"><button type="button" onClick={() => setResetting(null)}>{t("Cancel")}</button><button className="primary" disabled={busy}>{t("Reset password")}</button></div></form> : <><div className="accounts-toolbar"><span>{t('Local accounts: {count}', { count: items.length })}</span><button className="primary" onClick={() => { setNotice(''); setCreating(true); }}>{t("+ Create account")}</button></div><div className="account-list">{items.map((user) => <article className="account-row" key={user.user_id}><div className="avatar">{(user.display_name || user.username).slice(0, 1).toUpperCase()}</div><div className="account-info"><strong>{user.display_name || user.username}{user.user_id === session.user_id ? t(' (you)') : ''}</strong><span>{user.username} · {user.role === 'administrator' ? t("Administrator") : t("Inspector")}</span><small>{user.enabled ? t("Enabled") : t("Disabled")}{user.must_change_password ? t(" · Password change required") : ''}</small></div><div className="account-actions"><button onClick={() => { setError(''); setEditing(user); }}>{t("Edit")}</button><button onClick={() => { setError(''); setResetting(user); }}>{t("Reset password")}</button><button disabled={busy} onClick={() => { void mutate(user, '/revoke-sessions', {}); }}>{t("Revoke sessions")}</button></div></article>)}</div></>}</Modal>;
}
