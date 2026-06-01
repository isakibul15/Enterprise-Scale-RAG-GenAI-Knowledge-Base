import { Moon, Sun } from 'lucide-react';
import { useTheme } from '../hooks/useTheme';

export function ThemeToggle() {
  const { theme, toggle } = useTheme();

  return (
    <button
      onClick={toggle}
      className="p-2.5 text-gray-500 hover:text-gray-300 rounded-lg transition-all duration-200 hover:bg-white/[0.08] group"
      title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
      aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
    >
      {theme === 'dark' ? (
        <Sun size={18} className="text-yellow-400 group-hover:scale-110 transition-transform" />
      ) : (
        <Moon size={18} className="text-blue-400 group-hover:scale-110 transition-transform" />
      )}
    </button>
  );
}
