import { describe, expect, it } from 'vitest';
import {
  TERMINAL_JOB_STATUSES,
  isTerminalStatus,
  shouldApplyPolledDetail,
} from './jobStateHelpers';

describe('TERMINAL_JOB_STATUSES', () => {
  it('contains the three job terminal states', () => {
    expect(TERMINAL_JOB_STATUSES.has('succeeded')).toBe(true);
    expect(TERMINAL_JOB_STATUSES.has('failed')).toBe(true);
    expect(TERMINAL_JOB_STATUSES.has('cancelled')).toBe(true);
    expect(TERMINAL_JOB_STATUSES.has('running')).toBe(false);
    expect(TERMINAL_JOB_STATUSES.has('queued')).toBe(false);
  });
});

describe('isTerminalStatus', () => {
  it('returns true for terminal statuses', () => {
    expect(isTerminalStatus('succeeded')).toBe(true);
    expect(isTerminalStatus('failed')).toBe(true);
    expect(isTerminalStatus('cancelled')).toBe(true);
  });

  it('returns false for non-terminal statuses', () => {
    expect(isTerminalStatus('queued')).toBe(false);
    expect(isTerminalStatus('running')).toBe(false);
  });

  it('returns false for null / undefined / empty', () => {
    expect(isTerminalStatus(null)).toBe(false);
    expect(isTerminalStatus(undefined)).toBe(false);
    expect(isTerminalStatus('')).toBe(false);
  });
});

describe('shouldApplyPolledDetail', () => {
  it('applies when current is non-terminal and next is non-terminal', () => {
    expect(shouldApplyPolledDetail('queued', 'running')).toBe(true);
    expect(shouldApplyPolledDetail('running', 'running')).toBe(true);
  });

  it('applies when current is null / undefined', () => {
    expect(shouldApplyPolledDetail(null, 'running')).toBe(true);
    expect(shouldApplyPolledDetail(undefined, 'queued')).toBe(true);
  });

  it('applies when both transition into terminal', () => {
    expect(shouldApplyPolledDetail('running', 'failed')).toBe(true);
    expect(shouldApplyPolledDetail('running', 'succeeded')).toBe(true);
    expect(shouldApplyPolledDetail('queued', 'cancelled')).toBe(true);
  });

  it('rejects stale polling that flips terminal back to in-progress', () => {
    expect(shouldApplyPolledDetail('failed', 'running')).toBe(false);
    expect(shouldApplyPolledDetail('failed', 'queued')).toBe(false);
    expect(shouldApplyPolledDetail('cancelled', 'running')).toBe(false);
    expect(shouldApplyPolledDetail('succeeded', 'running')).toBe(false);
  });

  it('still applies when both are terminal (data confirms terminal status)', () => {
    expect(shouldApplyPolledDetail('failed', 'failed')).toBe(true);
    expect(shouldApplyPolledDetail('failed', 'succeeded')).toBe(true);
    expect(shouldApplyPolledDetail('cancelled', 'failed')).toBe(true);
  });
});
