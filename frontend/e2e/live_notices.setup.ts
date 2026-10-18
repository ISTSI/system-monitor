// TEST-ONLY: explicit in-process Vite lifecycle avoids Windows child-tree teardown.
import { createServer } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'node:path';

export default async function setup() {
  const server = await createServer({
    configFile: false,
    root: resolve('.'),
    plugins: [react()],
    server: { host: '127.0.0.1', port: 5189, strictPort: true },
  });
  await server.listen();
  return async () => { await server.close(); };
}
