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
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
