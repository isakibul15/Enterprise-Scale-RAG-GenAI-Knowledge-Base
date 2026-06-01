import { useState, useCallback } from 'react';
import { AlertCircle, CheckCircle2, Info, X } from 'lucide-react';

export const ToastContext = {
  current: null,
};

export function useToast() {
  const show = useCallback((message, type = 'info', duration = 4000) => {
    if (ToastContext.current) {
      ToastContext.current(message, type, duration);
    }
  }, []);

  return { show };
}

export function ToastContainer() {
  const [toasts, setToasts] = useState([]);

  // Set up context
  ToastContext.current = (message, type = 'info', duration = 4000) => {
    const id = Date.now();
    const newToast = { id, message, type };
    setToasts(prev => [...prev, newToast]);

    if (duration > 0) {
      setTimeout(() => {
        setToasts(prev => prev.filter(t => t.id !== id));
      }, duration);
    }

    return id;
  };

  const remove = (id) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  };

  return (
    <div className="fixed bottom-6 right-6 z-50 space-y-3 pointer-events-none">
      {toasts.map(toast => (
        <Toast
          key={toast.id}
          message={toast.message}
          type={toast.type}
          onClose={() => remove(toast.id)}
        />
      ))}
    </div>
  );
}

function Toast({ message, type, onClose }) {
  const config = {
    success: {
      icon: CheckCircle2,
      bg: 'bg-emerald-950/95',
      border: 'border-emerald-700/60',
      text: 'text-emerald-100',
      accent: 'text-emerald-400',
    },
    error: {
      icon: AlertCircle,
      bg: 'bg-red-950/95',
      border: 'border-red-700/60',
      text: 'text-red-100',
      accent: 'text-red-400',
    },
    info: {
      icon: Info,
      bg: 'bg-blue-950/95',
      border: 'border-blue-700/60',
      text: 'text-blue-100',
      accent: 'text-blue-400',
    },
  }[type] || config.info;

  const Icon = config.icon;

  return (
    <div
      className={`
        ${config.bg} ${config.border} ${config.text}
        border rounded-lg p-4 flex items-start gap-3 backdrop-blur-md
        pointer-events-auto animate-fade-in shadow-xl
        max-w-sm transform transition-all duration-300
      `}
    >
      <Icon size={20} className={`${config.accent} flex-shrink-0 mt-0.5`} />
      <p className="text-sm font-medium flex-1 leading-relaxed">{message}</p>
      <button
        onClick={onClose}
        className="flex-shrink-0 text-gray-500 hover:text-gray-300 transition-colors p-0.5 hover:bg-white/5 rounded"
        aria-label="Close notification"
      >
        <X size={16} />
      </button>
    </div>
  );
}
