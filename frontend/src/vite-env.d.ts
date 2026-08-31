/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_PRIVACY_CONTACT_EMAIL?: string;
  readonly VITE_ICP_NUMBER?: string;
  readonly VITE_ICP_LINK?: string;
  readonly VITE_PUBLIC_SECURITY_NUMBER?: string;
  readonly VITE_PUBLIC_SECURITY_LINK?: string;
  readonly VITE_USER_CONTENT_RETENTION_DAYS?: string;
  readonly VITE_AI_PROVIDER_NAME?: string;
  readonly VITE_APP_VERSION?: string;
  readonly VITE_BUILD_COMMIT?: string;
  readonly VITE_BUILD_TIME?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

declare const __APP_VERSION__: string;
declare const __BUILD_COMMIT__: string;
declare const __BUILD_TIME__: string;
