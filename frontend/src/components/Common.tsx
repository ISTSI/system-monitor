import { useI18n } from '../i18n';
import { useEffect, useId, useRef, type ReactNode } from 'react';

export function Icon({ kind = 'system', className = '' }: { kind?: 'system' | 'server' | 'process' | 'arrow'; className?: string }) {
  return <svg aria-hidden="true" className={`icon ${className}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
    {kind === 'system' && <><path d="m12 2 9 5v10l-9 5-9-5V7Z" /><path d="m12 7 5 3v5l-5 3-5-3v-5Z" /><path d="m3 7 9 5 9-5M12 12v10" /></>}
    {kind === 'server' && <><rect x="4" y="3" width="16" height="18" rx="2" /><path d="M4 9h16M4 15h16M8 6h.01M8 12h.01M8 18h.01M12 6h5M12 12h5M12 18h5" /></>}
    {kind === 'process' && <><rect x="6" y="6" width="12" height="12" rx="3" /><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4" /><circle cx="12" cy="12" r="2" /></>}
    {kind === 'arrow' && <path d="M4 12h16m-6-6 6 6-6 6" />}
  </svg>;
}

export function ErrorNotice({ children, retry }: { children: ReactNode; retry?: () => void }) {
  const { t } = useI18n();
  return <div className="notice error" role="alert"><span>{typeof children === 'string' ? t(children) : children}</span>{retry && <button type="button" onClick={retry}>{t("Retry")}</button>}</div>;
}

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const { t } = useI18n();
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const element = ref.current;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    element?.showModal();
    return () => { element?.close(); previous?.focus(); };
  }, []);
  return <dialog ref={ref} onCancel={event => { event.preventDefault(); onClose(); }} aria-labelledby={titleId}><div className="dialog-head"><h2 id={titleId}>{title}</h2><button type="button" aria-label={t("Close dialog")} onClick={onClose}>×</button></div>{children}</dialog>;
}

export function EmptyState({ title, children }: { title: string; children: ReactNode }) {
  return <div className="empty-state"><Icon /><h3>{title}</h3><p>{children}</p></div>;
}
