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

export async function exportChatAsPdf(messages, sessionId) {
  try {
    const { jsPDF } = await import('jspdf');
    const pdf = new jsPDF({
      orientation: 'portrait',
      unit: 'mm',
      format: 'a4',
    });

    const pageWidth = pdf.internal.pageSize.getWidth();
    const pageHeight = pdf.internal.pageSize.getHeight();
    const margin = 10;
    const maxWidth = pageWidth - 2 * margin;
    let y = margin;

    // Header
    pdf.setFillColor(124, 58, 237);
    pdf.rect(margin, y, maxWidth, 25, 'F');
    pdf.setTextColor(255, 255, 255);
    pdf.setFontSize(16);
    pdf.text('Chat Export', margin + 5, y + 10);

    pdf.setFontSize(9);
    y += 7;
    pdf.text(`Session: ${sessionId}`, margin + 5, y + 10);
    pdf.text(`Exported: ${new Date().toLocaleString()}`, margin + 5, y + 15);
    pdf.text(`Messages: ${messages.length}`, margin + 5, y + 20);

    y += 30;
    pdf.setTextColor(0, 0, 0);

    // Messages
    for (const msg of messages) {
      const isUser = msg.role === 'user';

      // Check if we need a new page
      if (y > pageHeight - margin - 10) {
        pdf.addPage();
        y = margin;
      }

      // Message role
      pdf.setFontSize(10);
      pdf.setFont(undefined, 'bold');
      pdf.setTextColor(isUser ? 124 : 79, isUser ? 58 : 46, 237);
      pdf.text(`${msg.role.toUpperCase()}:`, margin, y);

      y += 6;

      // Message content (wrapped)
      pdf.setFontSize(9);
      pdf.setFont(undefined, 'normal');
      pdf.setTextColor(0, 0, 0);

      const wrappedText = pdf.splitTextToSize(msg.content, maxWidth - 4);
      for (const line of wrappedText) {
        if (y > pageHeight - margin - 10) {
          pdf.addPage();
          y = margin;
        }
        pdf.text(line, margin + 2, y);
        y += 5;
      }

      y += 3;
    }

    pdf.save(`chat-${sessionId}-${Date.now()}.pdf`);
  } catch (err) {
    // Fallback if jsPDF not available
    throw new Error(`PDF export failed: ${err.message}`);
  }
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
