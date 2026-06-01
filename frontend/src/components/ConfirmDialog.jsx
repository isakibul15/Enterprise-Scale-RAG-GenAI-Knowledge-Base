import { useState } from 'react';

const ConfirmContext = { current: null };

export const useConfirm = () => {
  return {
    show: (title, message, onConfirm, onCancel) => {
      if (ConfirmContext.current) {
        ConfirmContext.current({ title, message, onConfirm, onCancel });
      }
    },
  };
};

export function ConfirmDialog() {
  const [dialog, setDialog] = useState(null);

  ConfirmContext.current = ({ title, message, onConfirm, onCancel }) => {
    setDialog({ title, message, onConfirm, onCancel });
  };

  if (!dialog) return null;

  const handleConfirm = async () => {
    await dialog.onConfirm?.();
    setDialog(null);
  };

  const handleCancel = () => {
    dialog.onCancel?.();
    setDialog(null);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/60 backdrop-blur-sm"
        onClick={handleCancel}
      />

      {/* Dialog */}
      <div
        className="relative rounded-xl p-6 max-w-sm w-full shadow-2xl animate-fade-in"
        style={{
          background: 'rgba(30, 27, 50, 0.95)',
          border: '1px solid rgba(124, 58, 237, 0.2)',
          backdropFilter: 'blur(12px)',
        }}
      >
        <h2 className="text-lg font-bold text-gray-100 mb-3">
          {dialog.title}
        </h2>
        <p className="text-sm text-gray-400 mb-6 leading-relaxed">
          {dialog.message}
        </p>

        {/* Buttons */}
        <div className="flex gap-3 justify-end pt-2">
          <button
            onClick={handleCancel}
            className="px-4 py-2 rounded-lg text-sm font-semibold text-gray-300 hover:bg-white/[0.08] transition-all duration-200"
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            className="px-4 py-2 rounded-lg text-sm font-semibold text-white transition-all duration-200 shadow-lg hover:shadow-xl hover:scale-105"
            style={{
              background: 'linear-gradient(135deg, #EF4444, #DC2626)',
            }}
          >
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}
