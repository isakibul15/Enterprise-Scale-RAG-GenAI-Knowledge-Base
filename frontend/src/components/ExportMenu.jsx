import { Download, FileText, Code2, File } from 'lucide-react';
import { useState, useRef } from 'react';
import { exportChatAsTxt, exportChatAsJson, exportChatAsHtml } from '../utils/exportChat';
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
        className="p-2 text-gray-500 hover:text-gray-300 rounded-lg transition-colors hover:bg-white/5"
        title="Export chat"
        aria-label="Export chat"
      >
        <Download size={16} />
      </button>

      {open && (
        <div
          className="absolute right-0 mt-2 w-48 rounded-lg shadow-lg z-50 animate-fade-in"
          style={{
            background: 'rgba(30, 27, 50, 0.95)',
            border: '1px solid rgba(124, 58, 237, 0.2)',
            backdropFilter: 'blur(12px)',
          }}
        >
          <button
            onClick={() => handleExport('txt')}
            className="w-full text-left px-4 py-3 hover:bg-white/5 transition-colors flex items-center gap-2 text-sm text-gray-300 hover:text-gray-100 border-b border-white/5"
          >
            <FileText size={14} className="text-violet-400" />
            <span>Export as TXT</span>
          </button>
          <button
            onClick={() => handleExport('json')}
            className="w-full text-left px-4 py-3 hover:bg-white/5 transition-colors flex items-center gap-2 text-sm text-gray-300 hover:text-gray-100 border-b border-white/5"
          >
            <Code2 size={14} className="text-blue-400" />
            <span>Export as JSON</span>
          </button>
          <button
            onClick={() => handleExport('html')}
            className="w-full text-left px-4 py-3 hover:bg-white/5 transition-colors flex items-center gap-2 text-sm text-gray-300 hover:text-gray-100"
          >
            <File size={14} className="text-green-400" />
            <span>Export as HTML</span>
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
