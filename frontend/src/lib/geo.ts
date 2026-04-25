// Geo helpers mirroring the backend parser.

const EARTH_NM = 3440.065

export function haversineNm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const toRad = (d: number) => (d * Math.PI) / 180
  const p1 = toRad(lat1)
  const p2 = toRad(lat2)
  const dp = toRad(lat2 - lat1)
  const dl = toRad(lon2 - lon1)
  const a =
    Math.sin(dp / 2) ** 2 +
    Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2
  return 2 * EARTH_NM * Math.asin(Math.sqrt(a))
}

export function bearingDeg(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const toRad = (d: number) => (d * Math.PI) / 180
  const toDeg = (r: number) => (r * 180) / Math.PI
  const p1 = toRad(lat1)
  const p2 = toRad(lat2)
  const dl = toRad(lon2 - lon1)
  const y = Math.sin(dl) * Math.cos(p2)
  const x = Math.cos(p1) * Math.sin(p2) - Math.sin(p1) * Math.cos(p2) * Math.cos(dl)
  return (toDeg(Math.atan2(y, x)) + 360) % 360
}

/** 50/100/150/200 nm ring polygons (as GeoJSON-ish lon/lat arrays) */
export function ringPolygon(centerLat: number, centerLon: number, rangeNm: number, steps = 128): [number, number][] {
  const d = rangeNm / EARTH_NM // angular distance radians
  const lat1 = (centerLat * Math.PI) / 180
  const lon1 = (centerLon * Math.PI) / 180
  const pts: [number, number][] = []
  for (let i = 0; i <= steps; i++) {
    const brg = (i / steps) * 2 * Math.PI
    const lat2 = Math.asin(Math.sin(lat1) * Math.cos(d) + Math.cos(lat1) * Math.sin(d) * Math.cos(brg))
    const lon2 =
      lon1 +
      Math.atan2(
        Math.sin(brg) * Math.sin(d) * Math.cos(lat1),
        Math.cos(d) - Math.sin(lat1) * Math.sin(lat2),
      )
    pts.push([(lon2 * 180) / Math.PI, (lat2 * 180) / Math.PI])
  }
  return pts
}
