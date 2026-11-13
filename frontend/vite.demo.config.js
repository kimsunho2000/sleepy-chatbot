import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// 데모 빌드: 백엔드 없이 동작하는 미리보기를 JS 1개 + CSS 1개로 묶는다 (outDir: dist-demo)
export default defineConfig({
  plugins: [react()],
  base: './',
  // 환경변수 없이 어느 OS에서나 데모 모드가 켜지도록 설정에서 직접 지정한다
  define: { 'import.meta.env.VITE_DEMO': JSON.stringify('true') },
  build: {
    outDir: 'dist-demo',
    cssCodeSplit: false,
    rollupOptions: { output: { inlineDynamicImports: true } },
  },
});
