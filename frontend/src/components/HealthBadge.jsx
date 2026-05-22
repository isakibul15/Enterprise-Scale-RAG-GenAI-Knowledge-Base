import { useEffect, useState, useCallback } from 'react';
import { Activity, AlertCircle, Loader2 } from 'lucide-react';
import { getHealth } from '../api/client';

const STATUS_CONFIG = {
  ok:       { color: '#10B981', label: 'Systems Operational',  ring: 'rgba(16,185,129,0.3)' },
  degraded: { color: '#F59E0B', label: 'Degraded Performance', ring: 'rgba(245,158,11,0.3)' },
  error:    { color: '#EF4444', label: 'API Unreachable',      ring: 'rgba(239,68,68,0.3)'  },
  loading:  { color: '#6B7280', label: 'Checking…',            ring: 'rgba(107,114,128,0.2)' },
};

export default function HealthBadge() {
  const [health, setHealth]   = useState(null);
  const [status, setStatus]   = useState('loading');

  const check = useCallback(async () => {
    try {
      const data = await getHealth();
      setHealth(data);
      setStatus(data.status === 'ok' ? 'ok' : 'degraded');
    } catch {
      setStatus('error');
      setHealth(null);
    }
  }, []);

  // Check on mount, then every 30 s
  useEffect(() => {
    check();
    const id = setInterval(check, 30_000);
    return () => clearInterval(id);
  }, [check]);

  const cfg = STATUS_CONFIG[status];

  return (
    <div className="glass rounded-xl p-3.5 animate-fade-in">
      <div className="flex items-center justify-between mb-2.5">
        <span className="text-xs font-semibold uppercase tracking-widest text-gray-500 flex items-center gap-1.5">
          <Activity size={11} />
          System Status
        </span>
        <button
          onClick={check}
          className="text-gray-600 hover:text-gray-400 transition-colors"
          title="Refresh health"
        >
          <Loader2
            size={11}
            className={status === 'loading' ? 'animate-spin' : ''}
          />
        </button>
      </div>

      {/* Main status row */}
      <div className="flex items-center gap-2.5">
        {/* Pulsing dot */}
        <div className="relative flex-shrink-0">
          <div
            className="w-2.5 h-2.5 rounded-full"
            style={{ backgroundColor: cfg.color }}
          />
          {status === 'ok' && (
            <div
              className="absolute inset-0 rounded-full animate-ping"
              style={{ backgroundColor: cfg.color, opacity: 0.4 }}
            />
          )}
        </div>
        <span className="text-sm font-medium text-gray-200">{cfg.label}</span>
      </div>

      {/* Detail pills */}
      {health && status !== 'error' && (
        <div className="mt-2.5 flex flex-wrap gap-1.5">
          <Pill label="Vector DB" value={health.chromadb} ok={health.chromadb === 'connected'} />
          <Pill label="Embed"     value="ready"           ok />
          <Pill label="LLM"       value={health.llm_provider} ok />
        </div>
      )}
    </div>
  );
}

function Pill({ label, value, ok }) {
  return (
    <div
      className="flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium"
      style={{
        background: ok ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)',
        border:     `1px solid ${ok ? 'rgba(16,185,129,0.25)' : 'rgba(239,68,68,0.25)'}`,
        color:      ok ? '#34D399' : '#FCA5A5',
      }}
    >
      <span className="text-gray-500">{label}</span>
      <span>{value}</span>
    </div>
  );
}
