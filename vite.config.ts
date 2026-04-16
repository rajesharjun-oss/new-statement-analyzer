import path from 'path';
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '');
  return {
    server: {
      port: 5000,
      host: '0.0.0.0',
      allowedHosts: true,
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
    define: {
      'process.env.API_KEY': JSON.stringify(env.API_KEY),
      'process.env.GEMINI_API_KEY': JSON.stringify(env.API_KEY)
    },
    resolve: {
      alias: {
        '@': path.resolve(__dirname, '.'),
      }
    }
  };
});
