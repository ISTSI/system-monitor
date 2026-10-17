import { useId, useState } from 'react';
import { utc, utcInput } from '../utcDateTime';
import { Modal } from './Common';

export default function UtcDateTimeInput({ bound, value, onChange }: {
  bound: 'From' | 'To'; value: string; onChange: (value: string) => void;
}) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const [date, setDate] = useState(''); const [time, setTime] = useState('');
  const [error, setError] = useState('');
  const label = `${bound} UTC (${bound === 'From' ? 'inclusive' : 'exclusive'})`;
  const pickerLabel = `Choose ${bound} UTC date and time`;

  function choose() {
    let current: string;
    try { current = utc(value); } catch { current = new Date().toISOString(); }
    setDate(current.slice(0, 10)); setTime(current.slice(11, 19)); setError(''); setOpen(true);
  }

  function apply() {
    const selected = `${date} ${time.length === 5 ? `${time}:00` : time}`;
    try { utc(selected); } catch { setError('Choose a valid UTC date and time, including seconds.'); return; }
    onChange(selected); setOpen(false);
  }

  return <div className="utc-date-time">
    <label htmlFor={id}>{label}</label>
    <div className="utc-date-time-control">
      <input id={id} aria-label={label} value={utcInput(value)} onChange={event => onChange(event.target.value)} spellCheck={false} placeholder="YYYY-MM-DD HH:mm:ss" title={/\.[0-9]*[1-9][0-9]*Z$/.test(value) ? `Exact UTC bound: ${value}` : undefined} />
      <button type="button" aria-label={pickerLabel} title={pickerLabel} aria-haspopup="dialog" onClick={choose}>
        <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M16 3v4M8 3v4M3 11h18M8 15h.01M12 15h.01M16 15h.01M8 18h.01M12 18h.01" /></svg>
      </button>
    </div>
    {open && <Modal title={pickerLabel} onClose={() => setOpen(false)}>
      <form className="utc-date-time-picker" onSubmit={event => { event.preventDefault(); apply(); }}>
        <p className="muted">All values are in UTC.</p>
        <div className="form-grid">
          <label>{bound} UTC date<input type="date" aria-label={`${bound} UTC date`} value={date} min="0001-01-01" max="9999-12-31" required onChange={event => { setDate(event.target.value); setError(''); }} /></label>
          <label>{bound} UTC time<input type="time" aria-label={`${bound} UTC time`} value={time} step="1" required onChange={event => { setTime(event.target.value); setError(''); }} /></label>
        </div>
        {error && <p className="notice error" role="alert">{error}</p>}
        <div className="form-actions"><button type="button" onClick={() => setOpen(false)}>Cancel</button><button className="primary" type="submit">Use date and time</button></div>
      </form>
    </Modal>}
  </div>;
}
