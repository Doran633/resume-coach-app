import fs from 'node:fs';
import path from 'node:path';
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const version = env.VITE_APP_VERSION || fs.readFileSync(path.resolve(process.cwd(), '../VERSION'), 'utf8').trim();
  const commit = (env.VITE_BUILD_COMMIT || 'unknown').slice(0, 8);
  const buildTime = env.VITE_BUILD_TIME || new Date().toISOString();
  return {
    plugins: [
      react(),
      {
        name: 'release-metadata',
        transformIndexHtml(html) {
          return html.replace('</head>', `    <meta name="resume-coach-version" content="${version}" />\n    <meta name="resume-coach-commit" content="${commit}" />\n    <meta name="resume-coach-build-time" content="${buildTime}" />\n  </head>`);
        }
      }
    ],
    define: {
      __APP_VERSION__: JSON.stringify(version),
      __BUILD_COMMIT__: JSON.stringify(commit),
      __BUILD_TIME__: JSON.stringify(buildTime)
    },
    server: {
      host: '127.0.0.1',
      port: 5173,
      proxy: {
        '/api': {
          target: 'http://127.0.0.1:8000',
          changeOrigin: true,
        },
      },
    },
  };
});
