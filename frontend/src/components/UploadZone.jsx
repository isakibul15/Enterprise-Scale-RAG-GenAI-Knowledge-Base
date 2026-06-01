import { useState, useRef, useCallback } from 'react';
import { Upload, FileText, CheckCircle2, AlertCircle, X, Loader2 } from 'lucide-react';
import { uploadFile } from '../api/client';
import { useToast } from './Toast';

const ACCEPTED = ['.pdf','.docx','.doc','.txt','.md','.html','.htm','.csv'];
const MAX_MB   = 50;

function formatBytes(bytes) {
  if (bytes < 1024)        return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function UploadZone({ onSuccess }) {
  const [dragging,  setDragging]  = useState(false);
  const [file,      setFile]      = useState(null);
  const [progress,  setProgress]  = useState(0);
  const [uploading, setUploading] = useState(false);
  const [result,    setResult]    = useState(null);   // { ok, message }
  const { show: toast } = useToast();
  const inputRef = useRef(null);

  const validate = (f) => {
    if (!f) return 'No file selected.';
    const ext = '.' + f.name.split('.').pop().toLowerCase();
    if (!ACCEPTED.includes(ext)) return `Type "${ext}" not supported.`;
    if (f.size > MAX_MB * 1024 * 1024) return `File exceeds ${MAX_MB} MB limit.`;
    return null;
  };

  const pick = useCallback((f) => {
    setResult(null);
    const err = validate(f);
    if (err) { setResult({ ok: false, message: err }); return; }
    setFile(f);
  }, []);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files?.[0];
    if (f) pick(f);
  }, [pick]);

  const handleDragOver = (e) => { e.preventDefault(); setDragging(true);  };
  const handleDragLeave= ()  => setDragging(false);
  const handleInput    = (e) => pick(e.target.files?.[0]);

  const handleUpload = async () => {
    if (!file || uploading) return;
    setUploading(true);
    setProgress(0);
    setResult(null);

    try {
      const data = await uploadFile(file, { onProgress: setProgress });
      const successMsg = `✓ ${data.total_child_chunks} chunks ingested in ${data.duration_seconds}s`;
      setResult({
        ok: true,
        message: successMsg,
      });
      toast(successMsg, 'success', 4000);
      onSuccess?.(data);
      setFile(null);
      if (inputRef.current) inputRef.current.value = '';
    } catch (err) {
      const errorMsg = err.message || 'Upload failed';
      setResult({ ok: false, message: errorMsg });
      toast(errorMsg, 'error', 4000);
    } finally {
      setUploading(false);
      setProgress(0);
    }
  };

  const clear = () => {
    setFile(null);
    setResult(null);
    if (inputRef.current) inputRef.current.value = '';
  };

  return (
    <div className="space-y-2.5">
      <p className="text-xs font-semibold uppercase tracking-widest text-gray-500">
        Knowledge Base
      </p>

      {/* Drop zone */}
      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={() => !file && inputRef.current?.click()}
        className={`
          relative cursor-pointer rounded-xl border-2 border-dashed p-5 text-center
          transition-all duration-200 group
          ${dragging
            ? 'border-violet-500 bg-violet-900/10 scale-[1.01]'
            : file
            ? 'border-emerald-600/40 bg-emerald-950/10 cursor-default'
            : 'border-white/10 hover:border-white/20 hover:bg-white/[0.02]'
          }
        `}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED.join(',')}
          onChange={handleInput}
          className="hidden"
        />

        {file ? (
          /* Selected file preview */
          <div className="flex items-center gap-3 text-left">
            <div className="flex-shrink-0 w-9 h-9 rounded-lg bg-emerald-900/30 border border-emerald-700/30 flex items-center justify-center">
              <FileText size={16} className="text-emerald-400" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-gray-200 truncate">{file.name}</p>
              <p className="text-xs text-gray-500">{formatBytes(file.size)}</p>
            </div>
            <button
              onClick={(e) => { e.stopPropagation(); clear(); }}
              className="text-gray-600 hover:text-gray-400 transition-colors"
            >
              <X size={15} />
            </button>
          </div>
        ) : (
          /* Empty state */
          <div className="py-1">
            <div
              className={`
                mx-auto mb-3 w-10 h-10 rounded-xl flex items-center justify-center
                transition-all duration-200
                ${dragging ? 'bg-violet-600/30 scale-110' : 'bg-white/5 group-hover:bg-white/8'}
              `}
            >
              <Upload size={18} className={dragging ? 'text-violet-400' : 'text-gray-500'} />
            </div>
            <p className="text-sm text-gray-400 font-medium">
              {dragging ? 'Drop to upload' : 'Drag & drop or click'}
            </p>
            <p className="text-xs text-gray-600 mt-1">
              PDF · DOCX · TXT · MD · HTML · CSV
            </p>
          </div>
        )}
      </div>

      {/* Progress bar */}
      {uploading && (
        <div className="space-y-2">
          <div className="flex justify-between items-center text-xs">
            <span className="flex items-center gap-1.5 text-gray-300 font-medium">
              <Loader2 size={12} className="animate-spin text-violet-400" />
              Ingesting…
            </span>
            <span className="text-gray-500">{progress}%</span>
          </div>
          <div className="h-2 bg-white/5 rounded-full overflow-hidden border border-white/5">
            <div
              className="h-full bg-gradient-to-r from-violet-600 to-indigo-500 rounded-full transition-all duration-300 shadow-lg"
              style={{ width: `${progress}%`, boxShadow: '0 0 8px rgba(124,58,237,0.5)' }}
            />
          </div>
        </div>
      )}

      {/* Result toast */}
      {result && (
        <div
          className={`
            flex items-start gap-2 text-xs px-3 py-2.5 rounded-lg animate-fade-in
            ${result.ok
              ? 'bg-emerald-950/40 border border-emerald-800/40 text-emerald-300'
              : 'bg-red-950/40 border border-red-800/40 text-red-300'
            }
          `}
        >
          {result.ok
            ? <CheckCircle2 size={13} className="mt-0.5 flex-shrink-0" />
            : <AlertCircle  size={13} className="mt-0.5 flex-shrink-0" />
          }
          <span>{result.message}</span>
        </div>
      )}

      {/* Upload button */}
      {file && !uploading && (
        <button
          onClick={handleUpload}
          className="btn-send w-full flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-semibold text-white animate-fade-in"
        >
          <Upload size={14} />
          Ingest Document
        </button>
      )}
    </div>
  );
}
