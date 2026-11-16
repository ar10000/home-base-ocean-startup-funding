/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_OIDC_AUTHORITY?: string;
  readonly VITE_OIDC_CLIENT_ID?: string;
  /** "1" builds the public demo: a recorded snapshot, no API and no sign-in (D-79). */
  readonly VITE_DEMO?: string;
}
