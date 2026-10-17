import { useEffect, useId, useRef, useState } from 'react';

type Action = { label: string; onSelect: () => void; disabled?: boolean; dividerBefore?: boolean };

export default function ActionMenu({ label, items }: { label: string; items: Action[] }) {
  const [open, setOpen] = useState(false);
  const [availableHeight, setAvailableHeight] = useState(440);
  const container = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const popup = useRef<HTMLDivElement>(null);
  const startAtEnd = useRef(false);
  const id = useId();

  function close(restoreFocus = false) {
    setOpen(false);
    if (restoreFocus) trigger.current?.focus();
  }
  useEffect(() => {
    if (!open) return;
    const measure = () => setAvailableHeight(Math.max(80, window.innerHeight - (trigger.current?.getBoundingClientRect().bottom ?? 0) - 16));
    measure();
    const buttons = popup.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)');
    (startAtEnd.current ? buttons?.[buttons.length - 1] : buttons?.[0])?.focus();
    const outside = (event: PointerEvent) => { if (event.target instanceof Node && !container.current?.contains(event.target)) setOpen(false); };
    window.addEventListener('resize', measure);
    document.addEventListener('pointerdown', outside);
    return () => { window.removeEventListener('resize', measure); document.removeEventListener('pointerdown', outside); };
  }, [open]);

  return <div className="action-menu" ref={container} onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false); }}>
    <button ref={trigger} type="button" aria-haspopup="menu" aria-expanded={open} aria-controls={id} onClick={() => { startAtEnd.current = false; setOpen(!open); }} onKeyDown={event => {
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') { event.preventDefault(); startAtEnd.current = event.key === 'ArrowUp'; setOpen(true); }
    }}>{label}<span aria-hidden="true">⌄</span></button>
    {open && <div ref={popup} id={id} role="menu" aria-label={label} className="action-popup" style={{ maxHeight: availableHeight }} onKeyDown={event => {
      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close(true); }
      if (event.key === 'Tab') close(true);
      if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
        event.preventDefault();
        const buttons = [...event.currentTarget.querySelectorAll<HTMLButtonElement>('button:not(:disabled)')];
        const index = buttons.indexOf(document.activeElement as HTMLButtonElement);
        const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1 : (index + (event.key === 'ArrowDown' ? 1 : -1) + buttons.length) % buttons.length;
        buttons[next]?.focus();
      }
    }}>{items.map(item => <div key={item.label} role="none">{item.dividerBefore && <div role="separator" className="action-separator" />}<button type="button" role="menuitem" tabIndex={-1} disabled={item.disabled} onClick={() => { close(true); item.onSelect(); }}>{item.label}</button></div>)}</div>}
  </div>;
}
