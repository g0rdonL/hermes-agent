import test from 'node:test';
import assert from 'node:assert/strict';
import { buildTextSendPayload } from './bridge_helpers.js';

test('buildTextSendPayload creates a simple text payload', () => {
  const payload = buildTextSendPayload('Hello');
  assert.deepEqual(payload, { text: 'Hello' });
});

test('buildTextSendPayload adds mentions to contextInfo', () => {
  const mentions = ['123@s.whatsapp.net', '456@s.whatsapp.net'];
  const payload = buildTextSendPayload('Hello', { mentions });
  assert.deepEqual(payload, {
    text: 'Hello',
    contextInfo: {
      mentionedJid: mentions
    }
  });
});

test('buildTextSendPayload handles empty mentions array', () => {
  const payload = buildTextSendPayload('Hello', { mentions: [] });
  assert.deepEqual(payload, { text: 'Hello' });
});

test('buildTextSendPayload handles null/undefined mentions', () => {
  assert.deepEqual(buildTextSendPayload('Hello', { mentions: null }), { text: 'Hello' });
  assert.deepEqual(buildTextSendPayload('Hello', { mentions: undefined }), { text: 'Hello' });
});
