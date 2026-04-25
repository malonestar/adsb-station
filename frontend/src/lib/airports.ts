/**
 * Static metadata for the airports we surveil with the /airports board.
 *
 * elev_ft = field elevation above MSL. Used to compute altitude AGL from
 * `alt_baro` so the "low altitude" filter is consistent across airports
 * (KAPA at 5,885 MSL would otherwise look like commercial cruise alt).
 */

export interface Airport {
  icao: string
  iata: string | null
  name: string
  short: string // short label for the tab
  lat: number
  lon: number
  elev_ft: number
}

export const AIRPORTS: Airport[] = [
  {
    icao: 'KDEN',
    iata: 'DEN',
    name: 'Denver International',
    short: 'DEN',
    lat: 39.8617,
    lon: -104.6731,
    elev_ft: 5434,
  },
  {
    icao: 'KAPA',
    iata: 'APA',
    name: 'Centennial',
    short: 'APA',
    lat: 39.5701,
    lon: -104.8493,
    elev_ft: 5885,
  },
  {
    icao: 'KBKF',
    iata: null,
    name: 'Buckley Space Force Base',
    short: 'BKF',
    lat: 39.7017,
    lon: -104.7517,
    elev_ft: 5662,
  },
  {
    icao: 'KFTG',
    iata: null,
    name: 'Front Range',
    short: 'FTG',
    lat: 39.7853,
    lon: -104.5436,
    elev_ft: 5512,
  },
]

/**
 * Great-circle distance in nautical miles between two lat/lon points.
 * Same haversine as the backend, kept here so the airports board can
 * filter without a round-trip.
 */
export function haversineNm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 3440.065 // earth radius nm
  const toRad = (d: number) => (d * Math.PI) / 180
  const phi1 = toRad(lat1)
  const phi2 = toRad(lat2)
  const dphi = toRad(lat2 - lat1)
  const dlam = toRad(lon2 - lon1)
  const a =
    Math.sin(dphi / 2) ** 2 + Math.cos(phi1) * Math.cos(phi2) * Math.sin(dlam / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(a))
}
