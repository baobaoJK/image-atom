import { defineConfig } from '@vben/vite-config';

export default defineConfig(async () => {
  return {
    application: {},
    vite: {
      server: {
        proxy: {
          '/api': {
            changeOrigin: true,
            // 本地 Flask 后端（image-atom-server），接口本身带 /api 前缀，无需 rewrite
            target: 'http://localhost:5000',
          },
        },
      },
    },
  };
});
