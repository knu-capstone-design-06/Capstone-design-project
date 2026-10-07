import { createBackendApi } from './client.ts';

/** Vite 또는 Nginx의 같은 출처 프록시를 통해 backend에 연결합니다. */
export const backendApi = createBackendApi('/backend');
