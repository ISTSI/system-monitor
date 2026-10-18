import { useEffect, useLayoutEffect, useRef } from 'react';
import { useI18n } from '../i18n';

type ProcessVisibilityMenuProps = {
  processOptions: { id: string; name: string; host: string }[];
  visibleProcessIds: string[];
  disabled: boolean;
  onChange: (ids: string[]) => void;
};

export default function ProcessVisibilityMenu({ processOptions, visibleProcessIds, disabled, onChange }: ProcessVisibilityMenuProps) {
  const { t } = useI18n();
  const menu = useRef<HTMLDetailsElement>(null);
  const pendingChange = useRef<HTMLInputElement | null>(null);
  const currentlyDisabled = useRef(disabled);
  const selected = new Set(visibleProcessIds);
  const visibleCount = processOptions.filter(process => selected.has(process.id)).length;
  const all = processOptions.length > 0 && visibleCount === processOptions.length;

  useLayoutEffect(() => {
    currentlyDisabled.current = disabled;
    if (disabled) return;
    const input = pendingChange.current;
    pendingChange.current = null;
    const focused = document.activeElement;
    if (input?.isConnected && menu.current?.open && (!focused || focused === document.body || menu.current.contains(focused))) {
      input.focus({ preventScroll: true });
    }
  }, [disabled]);

  function change(input: HTMLInputElement, ids: string[]) {
    pendingChange.current = input;
    onChange(ids);
    // Split-pane visibility updates synchronously without a loading cycle.
    // Only an actual disabled interval needs to retain the focus anchor.
    queueMicrotask(() => {
      if (!currentlyDisabled.current && pendingChange.current === input) pendingChange.current = null;
    });
  }

  useEffect(() => {
    const dismiss = (event: PointerEvent) => {
      if (menu.current?.open && event.target instanceof Node && !menu.current.contains(event.target)) {
        menu.current.open = false;
        pendingChange.current = null;
      }
    };
    document.addEventListener('pointerdown', dismiss, true);
    return () => document.removeEventListener('pointerdown', dismiss, true);
  }, []);

  return <details className="log-process-menu" ref={menu} onBlur={event => {
    if (event.relatedTarget === null && (disabled || pendingChange.current)) return;
    // A real focus move, including Tab, must keep the user's chosen target.
    pendingChange.current = null;
    if (!event.currentTarget.contains(event.relatedTarget)) event.currentTarget.open = false;
  }} onKeyDown={event => {
    if (event.key === 'Escape' && event.currentTarget.open) {
      event.preventDefault(); event.stopPropagation(); event.currentTarget.open = false;
      pendingChange.current = null;
      event.currentTarget.querySelector('summary')?.focus({ preventScroll: true });
    }
  }}>
    <summary aria-label={t('Show process')}>{t('Show process')} <span aria-hidden="true">({visibleCount}/{processOptions.length})</span></summary>
    <fieldset><legend>{t('Visible processes')}</legend>
      {processOptions.length > 0 ? <>
        <label className="checkbox-label"><input type="checkbox" checked={all} disabled={disabled} ref={element => { if (element) element.indeterminate = visibleCount > 0 && !all; }} onChange={event => {
          change(event.currentTarget, event.target.checked ? processOptions.map(process => process.id) : []);
        }} />{t('All processes')}</label>
        {processOptions.map(process => <label className="checkbox-label" key={process.id} title={process.id}>
          <input type="checkbox" data-process-id={process.id} aria-label={`${process.host}: ${process.name}`} title={process.id} checked={selected.has(process.id)} disabled={disabled} onChange={event => {
            change(event.currentTarget, processOptions.filter(option => option.id === process.id ? event.target.checked : selected.has(option.id)).map(option => option.id));
          }} />
          <span title={process.id}>{process.host}: {process.name}</span>
        </label>)}
      </> : <p className="muted">{t('Apply a query to choose visible processes.')}</p>}
    </fieldset>
  </details>;
}
