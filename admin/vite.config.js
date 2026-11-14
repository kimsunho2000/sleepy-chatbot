import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// npm run mock / build:mock (--mode mock): 백엔드 없이 명세 모양의 가짜 데이터로 동작한다.
// .env 파일 없이 어느 OS에서나 켜지도록 설정에서 직접 지정한다
export default defineConfig(({ mode }) => ({
  plugins: [react()],
  define: mode === 'mock' ? { 'import.meta.env.VITE_MOCK': JSON.stringify('true') } : {},
  // 챗봇 프론트(5173)와 동시에 띄울 수 있도록 포트를 나눈다
  server: { port: 5175 },
}));
