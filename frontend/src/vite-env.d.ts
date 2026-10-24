/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** CARTO basemaps key (free, carto.com/basemaps/apikey). Build-time; set in frontend/.env.local. */
  readonly VITE_CARTO_KEY?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
