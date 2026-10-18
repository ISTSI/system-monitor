import assert from 'node:assert/strict';
import { test } from 'node:test';
import { formatUtcMicroseconds, formatUtcTimestamp, utc, utcInput } from '../src/utcDateTime.ts';

test('UTC metadata uses second precision without rounding or mutating exact query bounds', () => {
  const exact = '2026-10-18T12:34:56.999999Z';
  assert.equal(formatUtcTimestamp(exact), '2026-10-18 12:34:56');
  assert.equal(formatUtcTimestamp('2026-10-18T12:34:56Z'), '2026-10-18 12:34:56');
  assert.equal(utc(exact), exact);
  assert.equal(utcInput(exact), formatUtcTimestamp(exact));
  assert.equal(utc('2026-10-18 12:34:56'), '2026-10-18T12:34:56.000000Z');
});

test('UTC timestamp formatting never converts to the client timezone or invents unknown times', () => {
  const previous = process.env.TZ;
  try {
    process.env.TZ = 'Pacific/Honolulu';
    assert.equal(formatUtcTimestamp('2026-01-01T00:00:00.123456Z'), '2026-01-01 00:00:00');
    assert.equal(formatUtcTimestamp('unparsed source value'), 'unparsed source value');
    assert.equal(formatUtcTimestamp(''), '');
  } finally {
    if (previous === undefined) delete process.env.TZ;
    else process.env.TZ = previous;
  }
});

test('integer epoch microseconds display the owning UTC second, including before the epoch', () => {
  assert.equal(formatUtcMicroseconds('0'), '1970-01-01 00:00:00');
  assert.equal(formatUtcMicroseconds('999999'), '1970-01-01 00:00:00');
  assert.equal(formatUtcMicroseconds('-1'), '1969-12-31 23:59:59');
  assert.equal(formatUtcMicroseconds('-1000001'), '1969-12-31 23:59:58');
  assert.equal(formatUtcMicroseconds('1792326896999999'), '2026-10-18 12:34:56');
});
