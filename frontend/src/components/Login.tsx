import { useState, type FormEvent } from 'react';
import { clearCsrf, message, write } from '../api/client';
import type { Bootstrap } from '../api/types';
import { ErrorNotice, Icon } from './Common';

export default function Login({ bootstrap, onLogin, notice }: { bootstrap: Bootstrap; onLogin: () => Promise<void>; notice?: string }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    setError(''); setBusy(true);
    try {
      clearCsrf();
      await write('/auth/login', { username: String(data.get('username')), password: String(data.get('password')) });
      form.reset();
      await onLogin();
    } catch (cause) { setError(message(cause)); } finally { setBusy(false); }
  }
  return <main className="login-layout"><section className="login-intro"><div className="brand-mark"><Icon /></div><p className="eyebrow">LOCAL KNOWLEDGE · CLEAR CONTEXT</p><h1>{bootstrap.branding}</h1><p className="lead">Understand your systems.<br />Keep every investigation in context.</p><div className="intro-facts"><span>Multiple systems, one place</span><span>Independent browser workspaces</span><span>Offline at runtime</span></div><p className="muted">A read-only investigation tool for documented Linux systems.</p></section><section className="login-card"><p className="eyebrow">YOUR WORKSPACE</p><h2>Sign in</h2><p className="muted">Use your local application account.</p>{notice && <p className="notice" role="status">{notice}</p>}{error && <ErrorNotice>{error}</ErrorNotice>}<form onSubmit={(event) => { void submit(event); }}><label>Username<input name="username" autoComplete="username" required maxLength={128} autoFocus /></label><label>Password<input type="password" name="password" autoComplete="current-password" required maxLength={1024} /></label><button className="primary full-width" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}<Icon kind="arrow" /></button></form><p className="login-help">Accounts are provisioned by your Administrator. There is no public registration.</p></section><footer className="login-footer"><span>{bootstrap.branding}</span><span>Local accounts · Secure sessions</span></footer></main>;
}
