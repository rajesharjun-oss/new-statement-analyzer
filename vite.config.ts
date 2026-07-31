import path from 'path';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(() => {
  return {
    server: {
      port: 5000,
      host: '0.0.0.0',
      allowedHosts: true as const,
      proxy: {
        '/analyze': {
          target: 'http://127.0.0.1:8000',
          changeOrigin: true,
          timeout: 1800000,
          proxyTimeout: 1800000,
        },
        '/download': {
          target: 'http://127.0.0.1:8000',
          changeOrigin: true,
          timeout: 1800000,
          proxyTimeout: 1800000,
        },
      },
    },
    plugins: [react()],

    resolve: {
      alias: {
        '@': path.resolve(__dirname, '.'),
      }
    }
  };
});
