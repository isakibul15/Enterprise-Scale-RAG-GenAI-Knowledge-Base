import { useEffect, useState, useCallback } from 'react';
import { MessageSquare, Trash2, Plus, Loader2, Edit2, Check, X } from 'lucide-react';
import { getSessions, deleteSession } from '../api/client';
import { useConfirm } from './ConfirmDialog';
import { useToast } from './Toast';

export default function SessionList({ activeSession, onSelect, onNew, refreshTrigger }) {
  const [sessions,  setSessions]  = useState([]);
  const [loading,   setLoading]   = useState(false);
  const [deletingId, setDeletingId] = useState(null);
  const [editingId, setEditingId] = useState(null);
  const [editName, setEditName] = useState('');
  const [sessionNames, setSessionNames] = useState(() => {
    const saved = localStorage.getItem('sessionNames');
    return saved ? JSON.parse(saved) : {};
  });
  const { show: confirm } = useConfirm();
  const { show: toast } = useToast();

  const saveNames = (names) => {
    localStorage.setItem('sessionNames', JSON.stringify(names));
    setSessionNames(names);
  };

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
    
    confirm(
      'Delete Session?',
      'This action cannot be undone. All messages in this session will be permanently deleted.',
      async () => {
        setDeletingId(id);
        try {
          await deleteSession(id);
          setSessions(prev => prev.filter(s => s !== id));
          const newNames = { ...sessionNames };
          delete newNames[id];
          saveNames(newNames);
          toast('Session deleted', 'info', 3000);
          if (activeSession === id) onNew();
        } catch (err) {
          toast(err.message || 'Failed to delete session', 'error', 4000);
        } finally {
          setDeletingId(null);
        }
      }
    );
  };

  const handleStartEdit = (e, id) => {
    e.stopPropagation();
    setEditingId(id);
    setEditName(sessionNames[id] || label(id));
  };

  const handleSaveName = (e, id) => {
    e.stopPropagation();
    const trimmed = editName.trim();
    if (trimmed) {
      const newNames = { ...sessionNames, [id]: trimmed };
      saveNames(newNames);
      toast('Session renamed', 'success', 2000);
    }
    setEditingId(null);
  };

  const handleCancelEdit = (e) => {
    e.stopPropagation();
    setEditingId(null);
  };

  const label = (id) => {
    // Return custom name if exists, otherwise generate default
    if (sessionNames[id]) return sessionNames[id];
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
            const isEditing = editingId === id;

            if (isEditing) {
              return (
                <div
                  key={id}
                  onClick={(e) => e.stopPropagation()}
                  className="flex items-center gap-2 px-2.5 py-2 rounded-lg bg-white/[0.04] border border-white/[0.08]"
                >
                  <input
                    type="text"
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') handleSaveName(e, id);
                      if (e.key === 'Escape') handleCancelEdit(e);
                    }}
                    autoFocus
                    maxLength={50}
                    className="flex-1 bg-transparent text-xs text-gray-200 outline-none"
                  />
                  <button
                    onClick={(e) => handleSaveName(e, id)}
                    className="text-gray-600 hover:text-emerald-400 transition-colors"
                    title="Save"
                  >
                    <Check size={11} />
                  </button>
                  <button
                    onClick={(e) => handleCancelEdit(e)}
                    className="text-gray-600 hover:text-red-400 transition-colors"
                    title="Cancel"
                  >
                    <X size={11} />
                  </button>
                </div>
              );
            }

            return (
              <button
                key={id}
                onClick={() => onSelect(id)}
                className={`
                  w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-left
                  transition-all duration-150 group
                  ${isActive
                    ? 'bg-violet-600/20 border border-violet-600/40 text-violet-200'
                    : 'hover:bg-white/[0.06] border border-transparent text-gray-400 hover:text-gray-200'
                  }
                `}
              >
                <MessageSquare
                  size={13}
                  className={isActive ? 'text-violet-400 flex-shrink-0' : 'text-gray-600 group-hover:text-gray-500 flex-shrink-0 transition-colors'}
                />
                <span className="flex-1 min-w-0 truncate text-xs font-medium">
                  {label(id)}
                </span>
                <div className="flex items-center gap-1 opacity-60 group-hover:opacity-100 transition-opacity">
                  <button
                    onClick={(e) => handleStartEdit(e, id)}
                    className="text-gray-600 hover:text-violet-400 transition-colors flex-shrink-0 p-0.5"
                    title="Rename session"
                  >
                    <Edit2 size={11} />
                  </button>
                  <button
                    onClick={(e) => handleDelete(e, id)}
                    className={`
                      text-gray-600 hover:text-red-400 transition-colors flex-shrink-0 p-0.5
                      ${deletingId === id ? 'opacity-100' : ''}
                    `}
                    title="Delete session"
                  >
                    {deletingId === id
                      ? <Loader2 size={11} className="animate-spin" />
                      : <Trash2 size={11} />
                    }
                  </button>
                </div>
              </button>
            );
          })
        )}
      </div>
    </div>
  );
}
