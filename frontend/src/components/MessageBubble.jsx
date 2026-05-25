import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { User, Cpu, Copy, Check } from 'lucide-react';
import { useState } from 'react';

/* ── Copy button for code blocks ────────────────────────────────────────── */
function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch { /* ignore */ }
  };

  return (
    <button
      onClick={handleCopy}
      className="flex items-center gap-1 text-[10px] text-gray-500 hover:text-gray-300 transition-colors"
    >
      {copied ? <Check size={11} className="text-emerald-400" /> : <Copy size={11} />}
      {copied ? 'Copied' : 'Copy'}
    </button>
  );
}

/* ── Markdown component map ─────────────────────────────────────────────── */
const components = {
  code({ inline, className, children, ...props }) {
    const match = /language-(\w+)/.exec(className || '');
    const lang   = match ? match[1] : '';
    const code   = String(children).replace(/\n$/, '');

    if (inline) {
      return (
        <code
          className="px-1.5 py-0.5 rounded-md text-[0.82em] font-mono"
          style={{
            background: 'rgba(124,58,237,0.15)',
            border: '1px solid rgba(124,58,237,0.2)',
            color: '#C4B5FD',
          }}
          {...props}
        >
          {children}
        </code>
      );
    }

    return (
      <div className="group relative my-4">
        {/* Language + copy header */}
        <div
          className="flex items-center justify-between px-4 py-2 rounded-t-lg font-medium"
          style={{ background: '#0A0E1A', borderBottom: '1px solid rgba(124,58,237,0.2)' }}
        >
          <span className="text-[10px] font-semibold uppercase tracking-widest text-violet-400">
            {lang || 'code'}
          </span>
          <CopyButton text={code} />
        </div>
        <SyntaxHighlighter
          style={oneDark}
          language={lang || 'text'}
          PreTag="div"
          customStyle={{
            margin: 0,
            borderRadius: '0 0 8px 8px',
            background: '#070B14',
            border: '1px solid rgba(124,58,237,0.15)',
            borderTop: 'none',
            fontSize: '0.85em',
            padding: '1rem 1rem',
          }}
          {...props}
        >
          {code}
        </SyntaxHighlighter>
      </div>
    );
  },
};

/* ── Main component ─────────────────────────────────────────────────────── */
export default function MessageBubble({ role, content, isStreaming = false }) {
  const isUser = role === 'user';

  return (
    <div className={`flex gap-3 animate-fade-in ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
      {/* Avatar */}
      <div
        className={`
          flex-shrink-0 w-7 h-7 rounded-lg flex items-center justify-center mt-0.5
          ${isUser
            ? 'bg-violet-600/20 border border-violet-600/30'
            : 'bg-indigo-900/30 border border-indigo-700/30'
          }
        `}
      >
        {isUser
          ? <User size={13} className="text-violet-400" />
          : <Cpu  size={13} className="text-indigo-400" />
        }
      </div>

      {/* Bubble */}
      <div
        className={`
          max-w-[82%] rounded-2xl px-5 py-3.5
          ${isUser
            ? 'bg-violet-600/12 border border-violet-600/25 text-gray-100 rounded-tr-sm'
            : 'bg-white/[0.04] border border-white/[0.08] rounded-tl-sm'
          }
          ${isStreaming ? 'cursor-blink' : ''}
        `}
        style={isUser 
          ? { boxShadow: '0 4px 16px rgba(124,58,237,0.12), inset 0 1px 0 rgba(255,255,255,0.05)' } 
          : { boxShadow: '0 2px 8px rgba(0,0,0,0.2), inset 0 1px 0 rgba(255,255,255,0.03)' }
        }
      >
        {isUser ? (
          <p className="text-sm leading-relaxed whitespace-pre-wrap">{content}</p>
        ) : (
          <div className="prose-dark text-sm text-gray-300">
            {content ? (
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
                {content}
              </ReactMarkdown>
            ) : (
              // Shimmer placeholder while waiting for first token
              <span className="shimmer-text text-sm">Thinking…</span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
