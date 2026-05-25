import { Brain } from 'lucide-react';
import HealthBadge from './HealthBadge';
import UploadZone  from './UploadZone';
import SessionList from './SessionList';

export default function Sidebar({
  activeSession,
  onSelectSession,
  onNewSession,
  onUploadSuccess,
  sessionRefreshTrigger,
}) {
  return (
    <aside
      className="flex flex-col h-full w-full overflow-hidden"
      style={{ borderRight: '1px solid rgba(124,58,237,0.15)' }}
    >
      {/* ── Logo / Brand ─────────────────────────────────────────────── */}
      <div
        className="flex-shrink-0 flex items-center gap-3 px-5 py-5"
        style={{ borderBottom: '1px solid rgba(124,58,237,0.1)' }}
      >
        <div
          className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0"
          style={{
            background: 'linear-gradient(135deg, #7C3AED, #4F46E5)',
            boxShadow: '0 0 20px rgba(124,58,237,0.5), inset 0 1px 1px rgba(255,255,255,0.2)',
          }}
        >
          <Brain size={18} className="text-white" />
        </div>
        <div className="min-w-0">
          <p className="text-sm font-semibold text-gray-100 leading-tight truncate">
            Enterprise RAG
          </p>
          <p className="text-[10px] text-gray-600 leading-tight">
            GenAI Knowledge Base
          </p>
        </div>
      </div>

      {/* ── Scrollable content ───────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto scrollbar-thin px-4 py-4 space-y-5">

        {/* Health status */}
        <HealthBadge />

        {/* Upload zone */}
        <div className="glass rounded-xl p-4">
          <UploadZone onSuccess={onUploadSuccess} />
        </div>

        {/* Session management */}
        <div className="glass rounded-xl p-4">
          <SessionList
            activeSession={activeSession}
            onSelect={onSelectSession}
            onNew={onNewSession}
            refreshTrigger={sessionRefreshTrigger}
          />
        </div>

      </div>

      {/* ── Footer ───────────────────────────────────────────────────── */}
      <div
        className="flex-shrink-0 px-4 py-3"
        style={{ borderTop: '1px solid rgba(255,255,255,0.05)' }}
      >
        <p className="text-[10px] text-gray-700 text-center leading-relaxed">
          Powered by LangChain · ChromaDB · Ollama
        </p>
      </div>
    </aside>
  );
}
