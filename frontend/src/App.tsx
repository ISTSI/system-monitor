import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, clearCsrf, message, request, write } from './api/client';
import type { Bootstrap, Preferences, Session, ThemeMode } from './api/types';
import { ErrorNotice, Icon } from './components/Common';
import Login from './components/Login';
import Catalogue from './components/Catalogue';
import SystemWorkspace from './components/SystemWorkspace';
import { PasswordDialog, PreferencesDialog, SettingsDialog, UsersDialog } from './components/Management';
import { useAppearance } from './theme/useAppearance';
import { I18nProvider, resolveLanguage, useTranslator, type LanguagePreference } from './i18n';

type AccountEvent = 'appearance' | 'authentication';

export default function App() {
  const [bootstrap, setBootstrap] = useState<Bootstrap | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [preferences, setPreferences] = useState<Preferences | null>(null);
  const [ready, setReady] = useState(false);
  const [startupError, setStartupError] = useState('');
  const [sessionError, setSessionError] = useState('');
  const [notice, setNotice] = useState('');
  const [path, setPath] = useState(window.location.pathname);
  const [dialog, setDialog] = useState<'password' | 'preferences' | 'settings' | 'users' | null>(null);
  const [appearanceError, setAppearanceError] = useState('');
  const [appearanceBusy, setAppearanceBusy] = useState(false);
  const authEpoch = useRef(0);
  const failedMode = useRef<ThemeMode | null>(null);
  const [languageError, setLanguageError] = useState('');
  const [languageBusy, setLanguageBusy] = useState(false);
  const failedLanguage = useRef<LanguagePreference | null>(null);
  const preferenceWrite = useRef<number | null>(null);
  const channel = useRef<BroadcastChannel | null>(null);
  const accountMenu = useRef<HTMLDetailsElement | null>(null);
  const hasAccountPreferences = Boolean(session && !session.must_change_password);
  useAppearance(bootstrap, preferences);
  const language = resolveLanguage(bootstrap?.default_language, preferences?.language);
  const t = useTranslator(language);

  const clearProtected = useCallback((text = 'Your session ended. Sign in to continue.') => {
    authEpoch.current += 1;
    setSession(null); setPreferences(null); setDialog(null); clearCsrf(); setNotice(text);
    setAppearanceError(''); setAppearanceBusy(false); failedMode.current = null;
    setLanguageError(''); setLanguageBusy(false); failedLanguage.current = null;
    preferenceWrite.current = null;
    setSessionError('');
    void request<Bootstrap>('/ui/bootstrap').then(setBootstrap).catch(() => { /* Retain the last known public default while offline. */ });
  }, []);
  const loadAccount = useCallback(async () => {
    const epoch = authEpoch.current;
    const account = await request<Session>('/auth/session');
    if (epoch !== authEpoch.current) return;
    const prefs = account.must_change_password ? null : await request<Preferences>('/me/preferences');
    if (epoch !== authEpoch.current) return;
    setSession(account); setPreferences(prefs); setNotice('');
  }, []);
  const initialize = useCallback(async () => {
    setStartupError('');
    try {
      const publicInfo = await request<Bootstrap>('/ui/bootstrap');
      setBootstrap(publicInfo);
      try { await loadAccount(); } catch (cause) {
        if (!(cause instanceof ApiError && cause.status === 401)) throw cause;
        setNotice('');
      }
      setReady(true);
    } catch (cause) { setStartupError(message(cause)); }
  }, [loadAccount]);

  useEffect(() => { void initialize(); }, [initialize]);
  useEffect(() => {
    const pop = () => setPath(window.location.pathname);
    const expired = () => clearProtected();
    window.addEventListener('popstate', pop);
    window.addEventListener('si-session-ended', expired);
    return () => { window.removeEventListener('popstate', pop); window.removeEventListener('si-session-ended', expired); };
  }, [clearProtected]);
  useEffect(() => {
    if (!('BroadcastChannel' in window)) return;
    const broadcast = new BroadcastChannel('system-inspector-account');
    channel.current = broadcast;
    broadcast.onmessage = (event: MessageEvent<unknown>) => {
      if (event.data === 'authentication') { clearProtected(); }
      if (event.data === 'appearance') {
        const epoch = authEpoch.current;
        void request<Bootstrap>('/ui/bootstrap').then(setBootstrap)
          .catch(() => { /* Retain the last known public default while offline. */ });
        if (hasAccountPreferences) {
          void request<Preferences>('/me/preferences')
            .then(prefs => { if (epoch === authEpoch.current) setPreferences(prefs); })
            .catch(() => { /* The next protected action displays a connection/authentication error. */ });
        }
      }
    };
    return () => { channel.current = null; broadcast.close(); };
  }, [clearProtected, hasAccountPreferences]);
  useEffect(() => {
    if (!session?.user_id) return;
    const epoch = authEpoch.current;
    let pending = false;
    let stopped = false;
    const recheck = () => {
      if (pending) return;
      pending = true;
      void request<Session>('/auth/session').then((current) => {
      if (stopped || epoch !== authEpoch.current) return;
      if (current.user_id !== session.user_id) { clearProtected('The account changed in another window.'); window.location.reload(); return; }
      setSession(current); setSessionError('');
    }).catch((cause: unknown) => {
      if (stopped || epoch !== authEpoch.current) return;
      if (cause instanceof ApiError && cause.status === 401) clearProtected();
      else setSessionError(message(cause));
    }).finally(() => { pending = false; }); };
    window.addEventListener('focus', recheck);
    const timer = window.setInterval(recheck, 1000);
    return () => { stopped = true; window.removeEventListener('focus', recheck); window.clearInterval(timer); };
  }, [session?.user_id, clearProtected]);

  function broadcast(kind: AccountEvent) { channel.current?.postMessage(kind); }
  function navigate(target: string) { window.history.pushState({}, '', target); setPath(target); }
  function openAccountDialog(target: 'preferences' | 'password') {
    if (accountMenu.current) {
      accountMenu.current.open = false;
      accountMenu.current.querySelector('summary')?.focus();
    }
    setDialog(target);
  }
  async function logout() {
    try {
      await write('/auth/logout');
      clearProtected('You signed out. This ends the account session in every window.');
      broadcast('authentication');
    } catch (cause) { setAppearanceError(message(cause)); }
  }
  async function saveAppearance(mode: ThemeMode, refresh = false) {
    if (!preferences || preferenceWrite.current !== null) return;
    const epoch = authEpoch.current;
    preferenceWrite.current = epoch;
    setAppearanceBusy(true); setAppearanceError(''); failedMode.current = mode;
    try {
      const current = refresh ? await request<Preferences>('/me/preferences') : preferences;
      if (epoch !== authEpoch.current) return;
      const saved = await write<Preferences>('/me/preferences', { theme_mode: mode, expected_revision: current.revision }, 'PATCH');
      if (epoch !== authEpoch.current) return;
      setPreferences(saved); failedMode.current = null; broadcast('appearance');
    } catch (cause) { if (epoch === authEpoch.current) setAppearanceError(message(cause)); } finally { if (preferenceWrite.current === epoch) preferenceWrite.current = null; if (epoch === authEpoch.current) setAppearanceBusy(false); }
  }

  async function saveLanguage(mode: LanguagePreference, refresh = false) {
    if (!preferences || preferenceWrite.current !== null) return;
    const epoch = authEpoch.current;
    preferenceWrite.current = epoch;
    setLanguageBusy(true); setLanguageError(''); failedLanguage.current = mode;
    try {
      const current = refresh ? await request<Preferences>('/me/preferences') : preferences;
      if (epoch !== authEpoch.current) return;
      const saved = await write<Preferences>('/me/preferences', { language: mode, expected_revision: current.revision }, 'PATCH');
      if (epoch !== authEpoch.current) return;
      setPreferences(saved); failedLanguage.current = null; broadcast('appearance');
    } catch (cause) { if (epoch === authEpoch.current) setLanguageError(message(cause)); }
    finally { if (preferenceWrite.current === epoch) preferenceWrite.current = null; if (epoch === authEpoch.current) setLanguageBusy(false); }
  }

  if (!ready || !bootstrap) return <I18nProvider language={language}><main className="startup" aria-busy={!startupError}><div className="brand-mark"><Icon /></div><h1>{t("System Inspector")}</h1>{startupError ? <ErrorNotice retry={() => { void initialize(); }}>{startupError}</ErrorNotice> : <p role="status">{t("Preparing your workspace…")}</p>}</main></I18nProvider>;
  if (!session) return <I18nProvider language={language}><Login bootstrap={bootstrap} notice={notice} onLogin={loadAccount} /></I18nProvider>;
  if (session.must_change_password) return <I18nProvider language={language}><main className="forced-password"><div className="brand-line"><Icon /><strong>{bootstrap.branding}</strong></div><PasswordDialog forced onClose={() => { void logout(); }} onChanged={() => { clearProtected('Password changed. Sign in with your new password.'); broadcast('authentication'); }} /></main></I18nProvider>;

  const systemRoute = /^\/systems\/([^/]+)(?:\/(topology|logs|investigations)(?:\/([^/]+))?)?\/?$/.exec(path);
  const projectId = systemRoute?.[1];
  const section = systemRoute?.[2] === 'logs' || systemRoute?.[2] === 'investigations' ? 'logs' : 'topology';
  const investigationId = systemRoute?.[2] === 'investigations' ? systemRoute[3] : undefined;
  const adminView = /^\/admin\/?$/.test(path);
  const administrator = session.role === 'administrator';
  const retryAppearance = failedMode.current ? () => { if (failedMode.current) void saveAppearance(failedMode.current, true); } : undefined;
  const retryLanguage = failedLanguage.current ? () => { if (failedLanguage.current) void saveLanguage(failedLanguage.current, true); } : undefined;
  return <I18nProvider language={language}><div className="application">
    <header className="topbar">
      <a className="brand-line" href="/" onClick={(event) => { if (event.button === 0 && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey) { event.preventDefault(); navigate('/'); } }}><span className="brand-symbol"><Icon /></span><strong>{bootstrap.branding}</strong></a>
      <nav aria-label={t("Application")}>
        <a href="/" className={!projectId && !adminView ? 'active' : ''} onClick={(event) => { if (event.button === 0 && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey) { event.preventDefault(); navigate('/'); } }}>{t("Systems")}</a>
        {administrator && <button onClick={() => setDialog('users')}>{t("Accounts")}</button>}
        {administrator && <button onClick={() => setDialog('settings')}>{t("Settings")}</button>}
        {administrator && <a href="/admin" className={adminView ? 'active' : ''} onClick={(event) => { if (event.button === 0 && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey) { event.preventDefault(); navigate('/admin'); } }}>{t("Admin")}</a>}
      </nav>
      <div className="account-controls">
        {bootstrap.demo_mode && <span className="demo-label">{t("SYNTHETIC DEMO DATA")}</span>}
        <details ref={accountMenu} className="account-menu" onKeyDown={event => { if (event.key === 'Escape' && accountMenu.current?.open) { accountMenu.current.open = false; accountMenu.current.querySelector('summary')?.focus(); } }}><summary><span className="avatar">{(session.display_name || session.username).slice(0, 1).toUpperCase()}</span><span className="account-summary"><strong>{session.display_name || session.username}</strong><small>{administrator ? t("Administrator") : t("Inspector")}</small></span><span aria-hidden="true">⌄</span></summary><div className="account-popup"><p>{session.username}</p><button onClick={() => openAccountDialog('preferences')}>{t("Preferences")}</button><button onClick={() => openAccountDialog('password')}>{t("Change password")}</button><button onClick={() => { void logout(); }}>{t("Sign out all windows")}</button></div></details>
      </div>
    </header>
    {appearanceError && dialog !== 'preferences' && <div className="page-notice"><ErrorNotice retry={retryAppearance}>{appearanceError}</ErrorNotice></div>}
    <div className="session-boundary">{sessionError && <div className="page-notice"><ErrorNotice>{sessionError}{t(" Protected requests require a ready server. Retrying automatically.")}</ErrorNotice></div>}</div>
    {projectId ? <SystemWorkspace key={projectId} projectId={projectId} session={session} navigate={navigate} branding={bootstrap.branding} historicalDemoEnabled={bootstrap.historical_demo_enabled} section={section} investigationId={investigationId} />
      : adminView && !administrator ? <main className="catalogue-page"><ErrorNotice>{t("Administrator access is required to manage systems.")}</ErrorNotice><a href="/" onClick={(event) => { event.preventDefault(); navigate('/'); }}>{t("Back to systems")}</a></main>
        : <Catalogue key={adminView ? 'admin' : 'systems'} session={session} navigate={navigate} branding={bootstrap.branding} manage={adminView} />}
    <footer className="app-footer"><span>{bootstrap.branding}{t(" · Topology and log investigation")}</span><span>{t("All times UTC · Offline at runtime")}</span></footer>
    {dialog === 'password' && <PasswordDialog onClose={() => setDialog(null)} onChanged={() => { clearProtected('Password changed. Sign in with your new password.'); broadcast('authentication'); }} />}
    {dialog === 'preferences' && <PreferencesDialog appearance={preferences?.theme_mode ?? 'default'} appearanceBusy={appearanceBusy || languageBusy} appearanceError={appearanceError} onAppearanceChange={(mode) => { void saveAppearance(mode); }} onAppearanceRetry={retryAppearance} language={preferences?.language ?? 'default'} languageBusy={languageBusy || appearanceBusy} languageError={languageError} onLanguageChange={mode => { void saveLanguage(mode); }} onLanguageRetry={retryLanguage} onClose={() => setDialog(null)} />}
    {dialog === 'settings' && administrator && <SettingsDialog onClose={() => setDialog(null)} onSaved={(settings) => { setBootstrap((current) => current ? { ...current, branding: settings.branding, default_theme_mode: settings.default_theme_mode, default_language: settings.default_language } : current); broadcast('appearance'); }} />}
    {dialog === 'users' && <UsersDialog session={session} onClose={() => setDialog(null)} onSelfRevoked={() => { clearProtected('Your account changed. Sign in again to continue.'); broadcast('authentication'); }} />}
  </div></I18nProvider>;
}
