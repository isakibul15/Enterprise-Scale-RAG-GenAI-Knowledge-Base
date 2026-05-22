import { useState, useCallback, useRef } from 'react';
import { Menu, X } from 'lucide-react';
import Sidebar   from './components/Sidebar';
import ChatPanel from './components/ChatPanel';

function generateSessionId() {
  return `session-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export default function App() {
  /* ── Session state ───────────────────────────────────────────────────── */
  const [sessionId, setSessionId] = useState(() => generateSessionId());
  const [sessions,  setSessions]  = useState(new Map()); // sessionId → Message[]
  const [sessionRefresh, setSessionRefresh] = useState(0);

  /* ── Sidebar mobile toggle ───────────────────────────────────────────── */
  const [sidebarOpen, setSidebarOpen] = useState(false);

  /* ── Current messages (derived from sessions map) ───────────────────── */
  const messages = sessions.get(sessionId) ?? [];

  /* ── Message updater — accepts either a new message or an updater fn ── */
  const onMessage = useCallback((msgOrUpdater) => {
    setSessions(prev => {
      const current = prev.get(sessionId) ?? [];
      const next = typeof msgOrUpdater === 'function'
        ? msgOrUpdater(current)
        : [...current, msgOrUpdater];
      return new Map(prev).set(sessionId, next);
    });
  }, [sessionId]);

  /* ── New session ─────────────────────────────────────────────────────── */
  const handleNewSession = useCallback(() => {
    const id = generateSessionId();
    setSessionId(id);
    setSidebarOpen(false);
  }, []);

  /* ── Select existing session ─────────────────────────────────────────── */
  const handleSelectSession = useCallback((id) => {
    setSessionId(id);
    setSidebarOpen(false);
  }, []);

  /* ── After a stream completes, refresh the session list ─────────────── */
  const handleStreamDone = useCallback(() => {
    setSessionRefresh(n => n + 1);
  }, []);

  /* ── After a successful upload, trigger a session refresh too ────────── */
  const handleUploadSuccess = useCallback(() => {
    setSessionRefresh(n => n + 1);
  }, []);

  return (
    <div className="flex h-full w-full overflow-hidden" style={{ position: 'relative', zIndex: 1 }}>

      {/* ── Mobile sidebar overlay ──────────────────────────────────────── */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-20 bg-black/60 backdrop-blur-sm lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* ── Sidebar ─────────────────────────────────────────────────────── */}
      <div
        className={`
          fixed lg:relative inset-y-0 left-0 z-30
          w-72 flex-shrink-0
          glass
          transform transition-transform duration-300 ease-in-out
          ${sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
        `}
      >
        <Sidebar
          activeSession={sessionId}
          onSelectSession={handleSelectSession}
          onNewSession={handleNewSession}
          onUploadSuccess={handleUploadSuccess}
          sessionRefreshTrigger={sessionRefresh}
        />
      </div>

      {/* ── Main chat area ──────────────────────────────────────────────── */}
      <main className="flex-1 flex flex-col min-w-0 h-full">

        {/* Top bar (mobile hamburger + session label) */}
        <header
          className="flex-shrink-0 flex items-center gap-3 px-4 py-3 lg:px-6"
          style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}
        >
          {/* Mobile menu button */}
          <button
            onClick={() => setSidebarOpen(s => !s)}
            className="lg:hidden text-gray-500 hover:text-gray-300 transition-colors"
          >
            {sidebarOpen ? <X size={18} /> : <Menu size={18} />}
          </button>

          <div className="flex-1 min-w-0">
            <h1 className="text-sm font-semibold text-gray-300 truncate">
              {sessionId.startsWith('session-')
                ? `Session · ${sessionId.split('-').pop().toUpperCase()}`
                : sessionId}
            </h1>
            <p className="text-[10px] text-gray-600">
              {messages.length === 0
                ? 'No messages yet'
                : `${messages.length} message${messages.length !== 1 ? 's' : ''}`}
            </p>
          </div>

          {/* Gradient accent line under header */}
          <div
            className="absolute left-0 bottom-0 h-[1px] w-full pointer-events-none"
            style={{
              background: 'linear-gradient(90deg, transparent, rgba(124,58,237,0.3), rgba(79,70,229,0.2), transparent)',
            }}
          />
        </header>

        {/* Chat panel (fills remaining space) */}
        <div className="flex-1 min-h-0">
          <ChatPanel
            key={sessionId}          /* remount when session changes */
            sessionId={sessionId}
            messages={messages}
            onMessage={onMessage}
            onStreamDone={handleStreamDone}
          />
        </div>

      </main>
    </div>
  );
}
