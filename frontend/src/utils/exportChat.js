export async function exportChatAsTxt(messages, sessionId) {
  const lines = [
    `Session: ${sessionId}`,
    `Exported: ${new Date().toISOString()}`,
    '',
    '---',
    '',
  ];

  for (const msg of messages) {
    lines.push(`${msg.role.toUpperCase()}`);
    lines.push(msg.content);
    lines.push('');
  }

  const text = lines.join('\n');
  const blob = new Blob([text], { type: 'text/plain' });
  downloadBlob(blob, `chat-${sessionId}-${Date.now()}.txt`);
}

export async function exportChatAsJson(messages, sessionId) {
  const data = {
    sessionId,
    exportedAt: new Date().toISOString(),
    messageCount: messages.length,
    messages,
  };

  const json = JSON.stringify(data, null, 2);
  const blob = new Blob([json], { type: 'application/json' });
  downloadBlob(blob, `chat-${sessionId}-${Date.now()}.json`);
}

export async function exportChatAsHtml(messages, sessionId) {
  const html = `
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Chat Export - ${sessionId}</title>
  <style>
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      max-width: 900px;
      margin: 0 auto;
      padding: 2rem;
      background: #f5f5f5;
      color: #333;
    }
    .header {
      background: linear-gradient(135deg, #7C3AED, #4F46E5);
      color: white;
      padding: 2rem;
      border-radius: 8px;
      margin-bottom: 2rem;
    }
    .message {
      margin-bottom: 1.5rem;
      padding: 1rem;
      border-radius: 8px;
      background: white;
      border-left: 4px solid;
    }
    .message.user {
      border-left-color: #7C3AED;
      background: #f3e8ff;
    }
    .message.assistant {
      border-left-color: #4F46E5;
      background: #eef2ff;
    }
    .message-role {
      font-weight: 600;
      color: #666;
      margin-bottom: 0.5rem;
      text-transform: uppercase;
      font-size: 0.85em;
    }
    .message-content {
      line-height: 1.6;
      white-space: pre-wrap;
      word-wrap: break-word;
    }
    code {
      background: #f0f0f0;
      padding: 2px 6px;
      border-radius: 3px;
      font-family: monospace;
      font-size: 0.9em;
    }
  </style>
</head>
<body>
  <div class="header">
    <h1>Chat Export</h1>
    <p><strong>Session:</strong> ${escapeHtml(sessionId)}</p>
    <p><strong>Exported:</strong> ${new Date().toLocaleString()}</p>
    <p><strong>Messages:</strong> ${messages.length}</p>
  </div>
  
  ${messages.map(msg => `
    <div class="message ${msg.role}">
      <div class="message-role">${msg.role}</div>
      <div class="message-content">${escapeHtml(msg.content)}</div>
    </div>
  `).join('')}
</body>
</html>
  `.trim();

  const blob = new Blob([html], { type: 'text/html' });
  downloadBlob(blob, `chat-${sessionId}-${Date.now()}.html`);
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}
