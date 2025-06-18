import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import fs from 'fs';

export default defineConfig({
  plugins: [react()],
  build: {
    lib: {
      entry: path.resolve(__dirname, 'src/index.js'),
      name: 'YubaWidget',
      fileName: (format) => `yuba-widget.${format}.js`,
    },
    rollupOptions: {
      external: ['react', 'react-dom', 'axios'],
      output: {
        globals: {
          react: 'React',
          'react-dom': 'ReactDOM',
          axios: 'axios',
        },
      },
    },
  },
  // This will run after build and copy widget.css to dist/
  closeBundle: () => {
    const srcPath = path.resolve(__dirname, 'src/components/widget.css');
    const distPath = path.resolve(__dirname, 'dist/yuba-widget.css');

    try {
      fs.copyFileSync(srcPath, distPath);
      console.log('✅ widget.css copied to dist/');
    } catch (err) {
      console.error('❌ Failed to copy CSS file:', err);
    }
  },
});
