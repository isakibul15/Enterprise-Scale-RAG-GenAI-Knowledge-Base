/**
 * API client — all communication with the FastAPI backend.
 *
 * The most critical piece here is streamQuery() which implements the
 * POST + ReadableStream pattern for SSE because native EventSource
 * only supports GET requests.
 */

const BASE = '';   // Vite proxy rewrites /health, /upload, /query → localhost:8000

// ── Health ────────────────────────────────────────────────────────────────────
export async function getHealth() {
  const res = await fetch(`${BASE}/health`);
  if (!res.ok) throw new Error(`Health check failed: ${res.status}`);
  return res.json();
}

// ── Upload ────────────────────────────────────────────────────────────────────
export async function uploadFile(file, { onProgress } = {}) {
  const form = new FormData();
  form.append('file', file);

  // Use XMLHttpRequest to track real upload progress
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();

    xhr.upload.addEventListener('progress', (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    });

    xhr.addEventListener('load', () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try { resolve(JSON.parse(xhr.responseText)); }
        catch { resolve(xhr.responseText); }
      } else {
        try {
          const err = JSON.parse(xhr.responseText);
          reject(new Error(err.detail || `Upload failed (${xhr.status})`));
        } catch {
          reject(new Error(`Upload failed (${xhr.status})`));
        }
      }
    });

    xhr.addEventListener('error',  () => reject(new Error('Network error during upload')));
    xhr.addEventListener('abort',  () => reject(new Error('Upload aborted')));
    xhr.addEventListener('timeout',() => reject(new Error('Upload timed out')));

    xhr.timeout = 120_000; // 2 min for large files
    xhr.open('POST', `${BASE}/upload`);
    xhr.send(form);
  });
}

// ── SSE Streaming Query (POST + ReadableStream) ───────────────────────────────
/**
 * Sends a question to /query/stream and delivers tokens in real time.
 *
 * Why not native EventSource?
 *   EventSource only supports GET. Our endpoint is POST (body carries the
 *   question + session_id). We replicate SSE parsing over a fetch stream.
 *
 * SSE wire format from the backend:
 *   data: {"token": "Hello"}\n\n
 *   data: {"token": " world"}\n\n
 *   data: [DONE]\n\n
 *
 * @param {object}   payload           - { question, sessionId, topK }
 * @param {object}   callbacks         - { onToken, onDone, onError }
 * @returns {AbortController}          - call .abort() to cancel mid-stream
 */
export function streamQuery(
  { question, sessionId = 'default', topK = 6 },
  { onToken, onDone, onError }
) {
  const controller = new AbortController();

  (async () => {
    try {
      const res = await fetch(`${BASE}/query/stream`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ question, session_id: sessionId, top_k: topK }),
        signal:  controller.signal,
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
        throw new Error(body.detail ?? `HTTP ${res.status}`);
      }

      const reader  = res.body.getReader();
      const decoder = new TextDecoder();
      let   buffer  = '';

      // ── Parse loop ────────────────────────────────────────────────────────
      while (true) {
        const { done, value } = await reader.read();
        if (done) { onDone(); break; }

        buffer += decoder.decode(value, { stream: true });

        // Process every complete newline-terminated SSE line
        let nl;
        while ((nl = buffer.indexOf('\n')) !== -1) {
          const line = buffer.slice(0, nl).trimEnd();
          buffer     = buffer.slice(nl + 1);

          if (!line.startsWith('data: ')) continue;

          const data = line.slice(6).trim();

          if (data === '[DONE]') { onDone(); return; }

          if (data) {
            try {
              const parsed = JSON.parse(data);
              if (parsed.token !== undefined) onToken(parsed.token);
              if (parsed.error)               onError(parsed.error);
            } catch {
              // Incomplete JSON — extremely rare with well-behaved servers
              // Put the line back and wait for the next chunk
              buffer = line + '\n' + buffer;
              break;
            }
          }
        }
      }
    } catch (err) {
      if (err.name !== 'AbortError') onError(err.message);
    }
  })();

  return controller; // Caller can call controller.abort() at any time
}

// ── Sessions ──────────────────────────────────────────────────────────────────
export async function getSessions() {
  const res = await fetch(`${BASE}/query/sessions`);
  if (!res.ok) throw new Error(`Failed to fetch sessions: ${res.status}`);
  const data = await res.json();
  return data.active_sessions ?? [];
}

export async function deleteSession(sessionId) {
  const res = await fetch(`${BASE}/query/session/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error(`Failed to delete session: ${res.status}`);
  return res.json();
}
