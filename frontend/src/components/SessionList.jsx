import { useEffect, useState, useCallback } from 'react';
import { MessageSquare, Trash2, Plus, Loader2 } from 'lucide-react';
import { getSessions, deleteSession } from '../api/client';

export default function SessionList({ activeSession, onSelect, onNew, refreshTrigger }) {
  const [sessions,  setSessions]  = useState([]);
  const [loading,   setLoading]   = useState(false);
  const [deletingId, setDeletingId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getSessions();
      setSessions(data);
    } catch {
      // silently fail — backend may be starting up
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load, refreshTrigger]);

  const handleDelete = async (e, id) => {
    e.stopPropagation();
    setDeletingId(id);
    try {
      await deleteSession(id);
      setSessions(prev => prev.filter(s => s !== id));
      if (activeSession === id) onNew();
    } catch {
      // ignore
    } finally {
      setDeletingId(null);
    }
  };

  const label = (id) => {
    // Convert UUID-ish IDs into short human labels
    if (!id || id === 'default') return 'Default Session';
    const parts = id.split('-');
    return `Session ${parts[parts.length - 1].slice(0, 6).toUpperCase()}`;
  };

  return (
    <div className="space-y-2">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-widest text-gray-500">
          Sessions
        </p>
        <button
          onClick={onNew}
          title="New session"
          className="flex items-center gap-1 text-xs text-gray-500 hover:text-violet-400 transition-colors"
        >
          <Plus size={12} />
          New
        </button>
      </div>

      {/* List */}
      <div className="space-y-1">
        {loading && sessions.length === 0 ? (
          <div className="flex items-center gap-2 py-2 px-2.5 text-xs text-gray-600">
            <Loader2 size={10} className="animate-spin" />
            Loading…
          </div>
        ) : sessions.length === 0 ? (
          <p className="text-xs text-gray-700 px-2 py-1.5 italic">No saved sessions yet.</p>
        ) : (
          sessions.map((id) => {
            const isActive = id === activeSession;
            return (
              <button
                key={id}
                onClick={() => onSelect(id)}
                className={`
                  w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-left
                  transition-all duration-150 group
                  ${isActive
                    ? 'bg-violet-600/15 border border-violet-600/30 text-violet-300'
                    : 'hover:bg-white/[0.04] border border-transparent text-gray-400 hover:text-gray-200'
                  }
                `}
              >
                <MessageSquare
                  size={13}
                  className={isActive ? 'text-violet-400 flex-shrink-0' : 'text-gray-600 flex-shrink-0'}
                />
                <span className="flex-1 min-w-0 truncate text-xs font-medium">
                  {label(id)}
                </span>
                <button
                  onClick={(e) => handleDelete(e, id)}
                  className={`
                    flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity
                    text-gray-600 hover:text-red-400
                    ${deletingId === id ? 'opacity-100' : ''}
                  `}
                  title="Delete session"
                >
                  {deletingId === id
                    ? <Loader2 size={11} className="animate-spin" />
                    : <Trash2 size={11} />
                  }
                </button>
              </button>
            );
          })
        )}
      </div>
    </div>
  );
}
