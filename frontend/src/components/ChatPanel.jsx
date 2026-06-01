import { useRef, useEffect, useState, useCallback } from 'react';
import { Send, Square, Sparkles, ChevronDown } from 'lucide-react';
import MessageBubble from './MessageBubble';
import { streamQuery } from '../api/client';
import { useToast } from './Toast';

/* ── Empty / welcome state ──────────────────────────────────────────────── */
function EmptyState({ onSuggestion }) {
  const suggestions = [
    'Summarize the key findings in the uploaded documents.',
    'What are the main topics covered in the knowledge base?',
    'Find information about [your topic] and cite the sources.',
    'Compare and contrast the different sections of the documents.',
  ];

  return (
    <div className="flex flex-col items-center justify-center h-full px-6 text-center select-none">
      {/* Glow orb */}
      <div className="relative mb-12">
        <div
          className="w-20 h-20 rounded-3xl flex items-center justify-center"
          style={{
            background: 'linear-gradient(135deg, rgba(124,58,237,0.3), rgba(79,70,229,0.15))',
            border: '1.5px solid rgba(124,58,237,0.4)',
            boxShadow: '0 0 60px rgba(124,58,237,0.25), inset 0 1px 20px rgba(255,255,255,0.1)',
          }}
        >
          <Sparkles size={32} className="text-violet-300" />
        </div>
        <div
          className="absolute inset-0 rounded-3xl animate-pulse"
          style={{ background: 'rgba(124,58,237,0.1)', filter: 'blur(20px)' }}
        />
      </div>

      <h2 className="text-2xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-violet-400 to-indigo-400 mb-3">
        Enterprise Knowledge Base
      </h2>
      <p className="text-sm text-gray-300 mb-3 max-w-sm leading-relaxed font-medium">
        Upload documents using the sidebar, then ask anything.
      </p>
      <p className="text-xs text-gray-500 mb-12 max-w-sm leading-relaxed">
        Every answer is grounded in your data with source citations.
      </p>

      {/* Suggestion chips */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-lg">
        {suggestions.map((s, i) => (
          <button
            key={i}
            onClick={() => onSuggestion(s)}
            className="text-left text-xs text-gray-400 hover:text-gray-100 px-4 py-3 rounded-lg transition-all duration-200 transform hover:scale-105"
            style={{
              background: 'rgba(255,255,255,0.04)',
              border: '1px solid rgba(255,255,255,0.08)',
            }}
            onMouseEnter={e => {
              e.currentTarget.style.background = 'rgba(124,58,237,0.12)';
              e.currentTarget.style.borderColor = 'rgba(124,58,237,0.25)';
            }}
            onMouseLeave={e => {
              e.currentTarget.style.background = 'rgba(255,255,255,0.04)';
              e.currentTarget.style.borderColor = 'rgba(255,255,255,0.08)';
            }}
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}

/* ── Scroll-to-bottom button ────────────────────────────────────────────── */
function ScrollButton({ onClick }) {
  return (
    <button
      onClick={onClick}
      className="absolute bottom-24 right-6 z-10 p-2.5 rounded-full animate-fade-in hover:scale-110 transition-transform duration-200"
      style={{
        background: 'rgba(124,58,237,0.2)',
        border: '1px solid rgba(124,58,237,0.3)',
        backdropFilter: 'blur(8px)',
        boxShadow: '0 4px 16px rgba(124,58,237,0.15)',
      }}
    >
      <ChevronDown size={16} className="text-violet-300" />
    </button>
  );
}

/* ── Main ChatPanel ─────────────────────────────────────────────────────── */
export default function ChatPanel({ sessionId, messages, onMessage, onStreamDone }) {
  const [input,      setInput]      = useState('');
  const [streaming,  setStreaming]   = useState(false);
  const [showScroll, setShowScroll] = useState(false);
  const { show: toast } = useToast();
  const abortRef   = useRef(null);
  const bottomRef  = useRef(null);
  const scrollRef  = useRef(null);
  const textareaRef = useRef(null);

  /* Auto-scroll to bottom on new messages */
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  /* Show scroll-to-bottom button when not at bottom */
  const handleScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    setShowScroll(!atBottom);
  };

  /* Auto-resize textarea */
  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 160) + 'px';
  }, [input]);

  const scrollToBottom = () => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const stopStreaming = () => {
    abortRef.current?.abort();
    setStreaming(false);
  };

  const send = useCallback(async (text) => {
    const q = (text || input).trim();
    if (!q || streaming) return;

    setInput('');
    setStreaming(true);

    // Add user message
    onMessage({ role: 'user', content: q, id: Date.now() });

    // Placeholder AI message (content fills in via tokens)
    const aiId = Date.now() + 1;
    onMessage({ role: 'assistant', content: '', id: aiId, streaming: true });

    abortRef.current = streamQuery(
      { question: q, sessionId, topK: 6 },
      {
        onToken: (token) => {
          onMessage((prev) =>
            prev.map((m) =>
              m.id === aiId ? { ...m, content: m.content + token } : m
            )
          );
        },
        onDone: () => {
          onMessage((prev) =>
            prev.map((m) =>
              m.id === aiId ? { ...m, streaming: false } : m
            )
          );
          setStreaming(false);
          onStreamDone?.();
        },
        onError: (err) => {
          const errorMsg = typeof err === 'string' ? err : err?.message || 'Failed to get response';
          onMessage((prev) =>
            prev.map((m) =>
              m.id === aiId
                ? { ...m, content: `⚠️ Error: ${errorMsg}`, streaming: false }
                : m
            )
          );
          toast(errorMsg, 'error', 5000);
          setStreaming(false);
        },
      }
    );
  }, [input, streaming, sessionId, onMessage, onStreamDone, toast]);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  return (
    <div className="flex flex-col h-full relative">

      {/* ── Message list ───────────────────────────────────────────────── */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto scrollbar-thin px-6 py-6 space-y-5"
      >
        {messages.length === 0 ? (
          <EmptyState onSuggestion={(s) => send(s)} />
        ) : (
          messages.map((msg) => (
            <MessageBubble
              key={msg.id}
              role={msg.role}
              content={msg.content}
              isStreaming={msg.streaming ?? false}
            />
          ))
        )}
        <div ref={bottomRef} />
      </div>

      {showScroll && <ScrollButton onClick={scrollToBottom} />}

      {/* ── Input area ─────────────────────────────────────────────────── */}
      <div
        className="flex-shrink-0 px-4 py-4"
        style={{ borderTop: '1px solid rgba(255,255,255,0.05)' }}
      >
        <div
          className="flex items-end gap-3 rounded-2xl px-4 py-3 transition-all duration-200 chat-input-area"
          style={{
            background: 'rgba(13,19,33,0.8)',
            border: '1px solid rgba(255,255,255,0.08)',
            boxShadow: '0 0 0 0 rgba(124,58,237,0)',
          }}
          onFocusCapture={e => {
            e.currentTarget.style.borderColor = 'rgba(124,58,237,0.35)';
            e.currentTarget.style.boxShadow = '0 0 0 3px rgba(124,58,237,0.08)';
          }}
          onBlurCapture={e => {
            e.currentTarget.style.borderColor = 'rgba(255,255,255,0.08)';
            e.currentTarget.style.boxShadow = 'none';
          }}
        >
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask anything about your documents… (Enter to send, Shift+Enter for newline)"
            rows={1}
            disabled={streaming}
            className="
              flex-1 resize-none bg-transparent text-sm text-gray-200
              placeholder-gray-600 outline-none leading-relaxed
              disabled:opacity-50 disabled:cursor-not-allowed
            "
            style={{ maxHeight: '160px' }}
          />

          {/* Send / Stop button */}
          {streaming ? (
            <button
              onClick={stopStreaming}
              className="
                flex-shrink-0 w-8 h-8 rounded-xl flex items-center justify-center
                bg-red-600/20 border border-red-600/30 text-red-400
                hover:bg-red-600/30 transition-all duration-150
              "
              title="Stop generation"
            >
              <Square size={13} />
            </button>
          ) : (
            <button
              onClick={() => send()}
              disabled={!input.trim()}
              className="
                flex-shrink-0 w-8 h-8 rounded-xl flex items-center justify-center
                btn-send disabled:opacity-30 disabled:cursor-not-allowed
                disabled:transform-none disabled:shadow-none
              "
              title="Send (Enter)"
            >
              <Send size={13} className="text-white" />
            </button>
          )}
        </div>

        <p className="text-[10px] text-gray-700 text-center mt-2">
          Answers are grounded in your uploaded documents · Not a substitute for professional advice
        </p>
      </div>
    </div>
  );
}
