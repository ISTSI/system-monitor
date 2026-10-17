import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  build: { target: 'es2023', sourcemap: false },
  server: {
    strictPort: true,
    proxy: { '/api': { target: 'https://localhost:8443', secure: false } },
  },
});
