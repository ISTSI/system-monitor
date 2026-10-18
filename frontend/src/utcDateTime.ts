// Calendar validation uses Date; fractional seconds stay as text so existing
// investigation bounds retain their exact microseconds at the API boundary.
export function utc(value: string): string {
  const parts = /^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})(?:\.(\d{1,6}))?Z?$/.exec(value);
  if (!parts) throw new Error('Use a UTC date and time in YYYY-MM-DD HH:mm:ss format.');
  const seconds = `${parts[1]}T${parts[2]}`;
  const calendar = new Date(`${seconds}.000Z`);
  if (!Number.isFinite(calendar.getTime()) || calendar.toISOString().slice(0, 19) !== seconds) throw new Error('The UTC date or time is invalid.');
  return `${seconds}.${(parts[3] ?? '').padEnd(6, '0')}Z`;
}

// Presentation only: keep the full timestamp on the event/query for ordering,
// filtering and provenance. Never use the browser's timezone or round seconds.
export function formatUtcTimestamp(value: string): string {
  return value.replace(/^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})(?:\.\d{1,6})?Z$/, '$1 $2');
}

export function formatUtcMicroseconds(value: string): string {
  const microseconds = BigInt(value);
  // BigInt division truncates towards zero; floor negative instants so a
  // fractional second before the epoch still displays the preceding second.
  const milliseconds = microseconds / 1000n - (microseconds < 0n && microseconds % 1000n !== 0n ? 1n : 0n);
  return formatUtcTimestamp(new Date(Number(milliseconds)).toISOString());
}

export const utcInput = formatUtcTimestamp;

export function defaultTimes() {
  const end = new Date(); end.setUTCMilliseconds(0);
  return [utcInput(new Date(end.getTime() - 3600000).toISOString()), utcInput(end.toISOString())];
}
