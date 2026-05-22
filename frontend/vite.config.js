import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    // Proxy all API requests to the FastAPI backend — avoids CORS in dev
    proxy: {
      '/health':  { target: 'http://localhost:8000', changeOrigin: true },
      '/upload':  { target: 'http://localhost:8000', changeOrigin: true },
      '/query':   { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
});
