import { Download, FileText, FileJson, File } from 'lucide-react';
import { useState, useRef } from 'react';
import { exportChatAsTxt, exportChatAsJson, exportChatAsHtml, exportChatAsPdf } from '../utils/exportChat';
import { useToast } from './Toast';

export function ExportMenu({ messages, sessionId }) {
  const [open, setOpen] = useState(false);
  const menuRef = useRef(null);
  const { show: toast } = useToast();

  const handleExport = async (format) => {
    try {
      if (!messages || messages.length === 0) {
        toast('No messages to export', 'info', 3000);
        return;
      }

      switch (format) {
        case 'txt':
          exportChatAsTxt(messages, sessionId);
          toast('Chat exported as TXT', 'success', 3000);
          break;
        case 'json':
          exportChatAsJson(messages, sessionId);
          toast('Chat exported as JSON', 'success', 3000);
          break;
        case 'html':
          exportChatAsHtml(messages, sessionId);
          toast('Chat exported as HTML', 'success', 3000);
          break;
        case 'pdf':
          await exportChatAsPdf(messages, sessionId);
          toast('Chat exported as PDF', 'success', 3000);
          break;
      }
      setOpen(false);
    } catch (err) {
      toast(err.message || 'Export failed', 'error', 4000);
    }
  };

  return (
    <div className="relative" ref={menuRef}>
      <button
        onClick={() => setOpen(!open)}
        className="p-2.5 text-gray-500 hover:text-gray-300 rounded-lg transition-all duration-200 hover:bg-white/[0.08] group"
        title="Export chat"
        aria-label="Export chat"
      >
        <Download size={18} className="group-hover:scale-110 transition-transform" />
      </button>

      {open && (
        <div
          className="absolute right-0 mt-2 w-52 rounded-lg shadow-xl z-50 animate-fade-in overflow-hidden"
          style={{
            background: 'var(--menu-bg)',
            border: '1px solid var(--menu-border)',
            backdropFilter: 'blur(12px)',
            color: 'var(--menu-text)',
          }}
        >
          <button
            onClick={() => handleExport('txt')}
            className="w-full text-left px-4 py-3 transition-all duration-150 flex items-center gap-3 text-sm font-medium border-b"
            style={{
              color: 'var(--menu-text)',
              borderColor: 'rgba(255, 255, 255, 0.05)',
            }}
            onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--menu-hover-bg)')}
            onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
          >
            <FileText size={16} className="text-violet-400 flex-shrink-0" />
            <span>Export as TXT</span>
          </button>
          <button
            onClick={() => handleExport('json')}
            className="w-full text-left px-4 py-3 transition-all duration-150 flex items-center gap-3 text-sm font-medium border-b"
            style={{
              color: 'var(--menu-text)',
              borderColor: 'rgba(255, 255, 255, 0.05)',
            }}
            onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--menu-hover-bg)')}
            onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
          >
            <FileJson size={16} className="text-blue-400 flex-shrink-0" />
            <span>Export as JSON</span>
          </button>
          <button
            onClick={() => handleExport('html')}
            className="w-full text-left px-4 py-3 transition-all duration-150 flex items-center gap-3 text-sm font-medium border-b"
            style={{
              color: 'var(--menu-text)',
              borderColor: 'rgba(255, 255, 255, 0.05)',
            }}
            onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--menu-hover-bg)')}
            onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
          >
            <File size={16} className="text-green-400 flex-shrink-0" />
            <span>Export as HTML</span>
          </button>
          <button
            onClick={() => handleExport('pdf')}
            className="w-full text-left px-4 py-3 transition-all duration-150 flex items-center gap-3 text-sm font-medium"
            style={{
              color: 'var(--menu-text)',
            }}
            onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--menu-hover-bg)')}
            onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
          >
            <File size={16} className="text-red-400 flex-shrink-0" />
            <span>Export as PDF</span>
          </button>
        </div>
      )}

      {open && (
        <div
          className="fixed inset-0 z-40"
          onClick={() => setOpen(false)}
        />
      )}
    </div>
  );
}
