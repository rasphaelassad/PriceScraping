
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  root: 'app/static',
  base: '',
  server: {
    host: '0.0.0.0',
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://0.0.0.0:8000',
        changeOrigin: true
      }
    },
    strictPort: true,
    allowedHosts: [
      '*.replit.dev',
      '*'
    ]
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './app/static/src')
    }
  }
});
