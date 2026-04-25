// Mirrors backend Pydantic schemas. Keep in sync with app/readsb/schema.py.

export interface AircraftState {
  hex: string
  flight: string | null
  registration: string | null
  type_code: string | null
  category: string | null

  lat: number | null
  lon: number | null
  alt_baro: number | null
  alt_geom: number | null
  gs: number | null
  tas: number | null
  mach: number | null
  track: number | null
  true_heading: number | null
  mag_heading: number | null
  baro_rate: number | null
  geom_rate: number | null

  squawk: string | null
  emergency: string | null

  messages: number
  seen: number
  seen_pos: number | null
  rssi: number | null

  db_flags: number

  distance_nm: number | null
  bearing_deg: number | null
  is_military: boolean
  is_interesting: boolean
  is_pia: boolean
  is_emergency: boolean

  updated_at: string
}

export interface ReceiverInfo {
  lat: number
  lon: number
  alt_m: number
  name: string
  tz?: string
}

export interface AircraftEnrichment {
  hex: string
  registration?: string | null
  type_code?: string | null
  operator?: string | null
  type_name?: string | null
  manufacturer?: string | null
  photo_url?: string | null
  photo_thumb_url?: string | null
  photo_photographer?: string | null
  photo_link?: string | null
  callsign?: string | null
  route?: RouteInfo | null
}

export interface RouteAirport {
  icao: string
  iata: string | null
  name: string
  city: string | null
}

export type RouteSource =
  | 'adsbdb'
  | 'hexdb'
  | 'aeroapi'
  | 'not_found'
  | 'no_callsign'
  | 'unavailable'

export interface RouteInfo {
  callsign: string | null
  origin: RouteAirport | null
  destination: RouteAirport | null
  airline: string | null
  source: RouteSource
}

export interface CatalogRow {
  hex: string
  registration: string | null
  type_code: string | null
  operator: string | null
  category: string | null
  first_seen: string | null
  last_seen: string | null
  seen_count: number
  max_alt_ft: number | null
  max_speed_kt: number | null
  min_distance_nm: number | null
  is_military: boolean
  is_interesting: boolean
  photo_url: string | null
  photo_thumb_url: string | null
}

export type CatalogCategory =
  | 'all'
  | 'military'
  | 'interesting'
  | 'has_photo'
  | 'seen_last_hour'
  | 'watchlist'
  | 'emergency_recent'

export type CatalogSort =
  | 'last_seen'
  | 'first_seen'
  | 'seen_count'
  | 'max_alt_ft'
  | 'max_speed_kt'
  | 'min_distance_nm'
  | 'registration'

export interface CatalogResponse {
  total: number
  limit: number
  offset: number
  sort: CatalogSort
  sort_dir: 'asc' | 'desc'
  category: CatalogCategory
  rows: CatalogRow[]
}

export interface Alert {
  id: number
  hex: string
  kind: string
  triggered_at: string
  cleared_at: string | null
  payload: Record<string, unknown>
}

export interface WatchlistEntry {
  id: number
  kind: 'hex' | 'reg' | 'type' | 'operator'
  value: string
  label: string | null
  created_at?: string
}

export interface WatchlistDetailItem {
  id: number
  kind: 'hex' | 'reg' | 'type' | 'operator'
  value: string
  label: string | null
  created_at: string
  live: boolean
  catalog: {
    registration: string | null
    type_code: string | null
    operator: string | null
    photo_url: string | null
    photo_thumb_url: string | null
    photo_link: string | null
    is_military: boolean
    is_interesting: boolean
    first_seen: string | null
    last_seen: string | null
    seen_count: number
    max_alt_ft: number | null
    max_speed_kt: number | null
    min_distance_nm: number | null
  } | null
}

export interface SignalBucket {
  bucket: number
  count: number
}

export interface LiveStats {
  ts: string
  messages_per_sec: number
  aircraft_total: number
  aircraft_with_position: number
  max_range_nm_today: number
  signal_histogram: SignalBucket[]
}

export interface FeedHealthEntry {
  name: string
  state: 'ok' | 'warn' | 'down' | 'absent' | 'unknown'
  docker_status?: string
  docker_health?: string
  started_at?: string | null
  last_error?: string | null
  updated_at?: string
  message_rate?: number | null
}

export interface DailyAggregateRow {
  date: string
  msgs_total: number
  aircraft_unique: number
  max_range_nm: number
  top_aircraft: { top: { hex: string; count: number }[] }
}

export interface HeatmapBin {
  lat: number
  lon: number
  count: number
}

export interface ReplayPoint {
  hex: string
  ts: string
  lat: number
  lon: number
  alt_baro: number | null
  gs: number | null
  track: number | null
}

export interface TrailPoint {
  ts: string
  lat: number
  lon: number
  alt_baro: number | null
}

export interface AircraftTrail {
  hex: string
  points: TrailPoint[]
}

export interface AircraftTrailsResponse {
  seconds: number
  aircraft: AircraftTrail[]
}

export interface AircraftLiveResponse {
  ts: string
  aircraft: AircraftState[]
  receiver: ReceiverInfo
  tick_count: number
  last_tick: string | null
}

export interface AircraftDelta {
  added: AircraftState[]
  updated: AircraftState[]
  removed: string[]
}

// Discriminated union for WebSocket messages
export type WsMessage =
  | { type: 'aircraft.delta'; data: AircraftDelta }
  | { type: 'aircraft.enriched'; data: AircraftEnrichment }
  | { type: 'alert.new'; data: Alert }
  | { type: 'alert.cleared'; data: { id: number; hex: string; kind: string; cleared_at: string } }
  | { type: 'stats.tick'; data: LiveStats }
  | { type: 'feed.status'; data: { feeds: FeedHealthEntry[] } }
