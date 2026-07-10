/**
 * Build a Baileys send payload for text messages, including mentions.
 *
 * @param {string} text - The message text to send.
 * @param {Object} options - Options for the message.
 * @param {string[]} [options.mentions] - Optional array of JIDs to mention.
 * @returns {Object} The Baileys message payload.
 */
export function buildTextSendPayload(text, { mentions } = {}) {
  const payload = { text };
  if (mentions && Array.isArray(mentions) && mentions.length > 0) {
    payload.contextInfo = {
      mentionedJid: mentions,
    };
  }
  return payload;
}
