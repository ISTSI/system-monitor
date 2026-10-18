import { useI18n } from '../i18n';
import { useState, type FormEvent } from 'react';
import { clearCsrf, message, write } from '../api/client';
import type { Bootstrap } from '../api/types';
import { ErrorNotice, Icon } from './Common';

export default function Login({ bootstrap, onLogin, notice }: { bootstrap: Bootstrap; onLogin: () => Promise<void>; notice?: string }) {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    setError(''); setBusy(true);
    try {
      clearCsrf();
      await write('/auth/login', { username: String(data.get('username')), password: String(data.get('password')), remember_me: data.get('remember_me') === 'on' });
      form.reset();
      await onLogin();
    } catch (cause) { setError(message(cause)); } finally { setBusy(false); }
  }
  return <main className="login-layout"><section className="login-intro"><div className="brand-mark"><Icon /></div><p className="eyebrow">{t("LOCAL KNOWLEDGE · CLEAR CONTEXT")}</p><h1>{bootstrap.branding}</h1><p className="lead">{t("Understand your systems.")}<br />{t("Keep every investigation in context.")}</p><div className="intro-facts"><span>{t("Multiple systems, one place")}</span><span>{t("Independent browser workspaces")}</span><span>{t("Offline at runtime")}</span></div><p className="muted">{t("A read-only investigation tool for documented Linux systems.")}</p></section><section className="login-card"><p className="eyebrow">{t("YOUR WORKSPACE")}</p><h2>{t("Sign in")}</h2><p className="muted">{t("Use your local application account.")}</p>{notice && <p className="notice" role="status">{t(notice)}</p>}{error && <ErrorNotice>{error}</ErrorNotice>}<form onSubmit={(event) => { void submit(event); }}><label>{t("Username")}<input name="username" autoComplete="username" required maxLength={128} autoFocus /></label><label>{t("Password")}<input type="password" name="password" autoComplete="current-password" required maxLength={1024} /></label><label className="checkbox-label"><input type="checkbox" name="remember_me" aria-describedby="remember-help" />{t("Remember me")}</label><p id="remember-help" className="muted">{t("Stay signed in for 30 days.")}</p><button title={t("Open your workspace using your local account.")} className="primary full-width" disabled={busy}>{busy ? t("Signing in…") : t("Sign in")}<Icon kind="arrow" /></button></form><p className="login-help">{t("Accounts are provisioned by your Administrator. There is no public registration.")}</p></section><footer className="login-footer"><span>{bootstrap.branding}</span><span>{t("Local accounts · Secure sessions")}</span></footer></main>;
}
