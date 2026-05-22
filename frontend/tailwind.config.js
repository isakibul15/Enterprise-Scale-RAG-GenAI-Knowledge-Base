/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // Deep cosmic background palette
        cosmic: {
          950: '#070B14',
          900: '#0B0F19',
          800: '#0D1321',
          700: '#111827',
          600: '#161f32',
          500: '#1e2d45',
          400: '#2a3f5f',
        },
        // Violet accent chain
        violet: {
          950: '#1e0050',
          900: '#2e0080',
          DEFAULT: '#7C3AED',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      animation: {
        'pulse-slow':    'pulse 3s ease-in-out infinite',
        'blink':         'blink 1s step-end infinite',
        'fade-in':       'fadeIn 0.25s ease-out',
        'slide-up':      'slideUp 0.3s ease-out',
        'slide-in-left': 'slideInLeft 0.3s ease-out',
        'shimmer':       'shimmer 1.8s linear infinite',
        'glow-pulse':    'glowPulse 2s ease-in-out infinite',
      },
      keyframes: {
        blink: {
          '0%, 100%': { opacity: '1' },
          '50%':      { opacity: '0' },
        },
        fadeIn: {
          from: { opacity: '0' },
          to:   { opacity: '1' },
        },
        slideUp: {
          from: { transform: 'translateY(10px)', opacity: '0' },
          to:   { transform: 'translateY(0)',    opacity: '1' },
        },
        slideInLeft: {
          from: { transform: 'translateX(-10px)', opacity: '0' },
          to:   { transform: 'translateX(0)',     opacity: '1' },
        },
        shimmer: {
          '0%':   { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition:  '200% 0' },
        },
        glowPulse: {
          '0%, 100%': { boxShadow: '0 0 8px rgba(124,58,237,0.4)' },
          '50%':      { boxShadow: '0 0 20px rgba(124,58,237,0.8)' },
        },
      },
      backdropBlur: { xs: '2px' },
      boxShadow: {
        'glass':         '0 4px 24px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.05)',
        'glow-violet':   '0 0 20px rgba(124,58,237,0.35)',
        'glow-emerald':  '0 0 20px rgba(16,185,129,0.35)',
        'message-user':  '0 2px 16px rgba(124,58,237,0.25)',
        'message-ai':    '0 2px 16px rgba(0,0,0,0.4)',
      },
    },
  },
  plugins: [],
};
