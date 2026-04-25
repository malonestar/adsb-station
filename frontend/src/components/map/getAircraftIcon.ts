import type { AircraftState } from '@/types/api'

/**
 * Pick an icon (body silhouette) for an aircraft.
 *
 * Layered selection:
 *   1. ICAO ADS-B category if readsb provides one (A1-A7, B1, B6)
 *   2. Type-code prefix match for cases where category is missing or generic
 *   3. Generic narrowbody silhouette as the last-resort fallback
 *
 * Military, interesting, and emergency are handled as OVERLAYS on top of the
 * body silhouette (see AircraftMarkers.tsx) so a USAF C-17 still reads as a
 * heavy with a military badge — not a generic "military" shape.
 */
export function pickIcon(ac: AircraftState): string {
  // Category-driven path first
  switch (ac.category) {
    case 'A1':
      return '/icons/gaprop.svg' // light <7t — Cessnas, Pipers
    case 'A2':
      return '/icons/bizjet.svg' // small 7-34t — Citations, Gulfstreams
    case 'A3':
    case 'A4':
      return '/icons/narrow.svg' // 34-300t — A320, B737, 757
    case 'A5':
      return '/icons/heavy.svg' // >300t — 777, A380, A350
    case 'A6':
      return '/icons/narrow.svg' // high-performance / fighters — narrow shape works
    case 'A7':
      return '/icons/rotor.svg'
    case 'B1':
    case 'B2':
      return '/icons/glider.svg'
    case 'B6':
      return '/icons/drone.svg'
  }

  // Type-code fallback. ICAO type designators — first 3-4 chars usually carry the family.
  const t = ac.type_code?.toUpperCase()
  if (t) {
    if (TYPE_HEAVY.has(t) || HEAVY_PREFIXES.some((p) => t.startsWith(p))) return '/icons/heavy.svg'
    if (TYPE_ROTOR.has(t) || ROTOR_PREFIXES.some((p) => t.startsWith(p))) return '/icons/rotor.svg'
    if (TYPE_BIZJET.has(t) || BIZJET_PREFIXES.some((p) => t.startsWith(p))) return '/icons/bizjet.svg'
    if (TYPE_GAPROP.has(t) || GAPROP_PREFIXES.some((p) => t.startsWith(p))) return '/icons/gaprop.svg'
    if (TYPE_NARROW.has(t) || NARROW_PREFIXES.some((p) => t.startsWith(p))) return '/icons/narrow.svg'
  }

  return '/icons/narrow.svg'
}

export function iconSizeForCategory(cat: string | null): number {
  switch (cat) {
    case 'A5':
      return 32 // heavy
    case 'A3':
    case 'A4':
      return 26 // narrow
    case 'A6':
      return 24 // fighter
    case 'A7':
      return 22 // rotor
    case 'A2':
      return 22 // bizjet
    case 'A1':
      return 20 // GA
    case 'B1':
    case 'B2':
      return 22 // glider
    default:
      return 24
  }
}

// ── Type-code lookup tables ─────────────────────────────────────────────
// Used as fallback when ADS-B `category` is missing (A0 / null). Most live
// aircraft have a category, so these only kick in for less-equipped fleets.

const HEAVY_PREFIXES = ['B74', 'B77', 'B78', 'A33', 'A34', 'A35', 'A38', 'IL96', 'AN12', 'AN24']
const TYPE_HEAVY = new Set([
  'C17', 'C5', 'C5M', 'KC10', 'KC30', 'KC46', 'K35R', 'E3CF', 'E3TF', 'E767', 'C30J', 'C130', 'P3',
])

const NARROW_PREFIXES = ['A22', 'A31', 'A32', 'B73', 'B72', 'B75', 'B76', 'E17', 'E19', 'E29', 'CRJ', 'MD8', 'MD9']
const TYPE_NARROW = new Set([
  'A220', 'A318', 'A319', 'A320', 'A321', 'B712', 'B717', 'B722', 'B732', 'B733', 'B734', 'B735',
  'B736', 'B737', 'B738', 'B739', 'B73M', 'B752', 'B753', 'B762', 'B763', 'B764',
])

const BIZJET_PREFIXES = ['CL', 'GLEX', 'GLF', 'GULF', 'F2', 'F9', 'FA', 'LJ', 'PRM', 'C2', 'C5', 'C6', 'C7', 'BE40']
const TYPE_BIZJET = new Set([
  'C25A', 'C25B', 'C25C', 'C500', 'C501', 'C510', 'C525', 'C550', 'C551', 'C560', 'C56X',
  'C650', 'C680', 'C68A', 'C700', 'C750', 'CL30', 'CL35', 'CL60', 'CL64', 'CL65',
  'GALX', 'GLEX', 'GLF2', 'GLF3', 'GLF4', 'GLF5', 'GLF6', 'GLF7', 'GULF',
  'F2TH', 'F900', 'FA10', 'FA20', 'FA50', 'FA7X', 'FA8X',
  'LJ24', 'LJ31', 'LJ35', 'LJ40', 'LJ45', 'LJ55', 'LJ60', 'LJ70', 'LJ75', 'LJ85',
  'BE40', 'PRM1', 'HDJT', 'EA50', 'PC24',
])

const GAPROP_PREFIXES = ['C1', 'PA', 'BE2', 'BE3', 'M20', 'SR2', 'DA', 'DH8', 'DHC']
const TYPE_GAPROP = new Set([
  'C150', 'C152', 'C162', 'C172', 'C175', 'C177', 'C180', 'C182', 'C185', 'C188', 'C205', 'C206',
  'C207', 'C208', 'C210', 'C336', 'C337', 'C340', 'C402', 'C414', 'C421',
  'PA18', 'PA22', 'PA23', 'PA24', 'PA28', 'PA32', 'PA34', 'PA38', 'PA44', 'PA46',
  'BE19', 'BE20', 'BE23', 'BE24', 'BE33', 'BE35', 'BE36', 'BE55', 'BE58', 'BE60', 'BE76', 'BE77',
  'BE9L', 'BE9T', 'B190', 'B350',
  'M20P', 'M20R', 'M20T',
  'SR20', 'SR22', 'SR2T',
  'DA20', 'DA40', 'DA42', 'DA62',
  'DHC2', 'DHC3', 'DHC6', 'DH8A', 'DH8B', 'DH8C', 'DH8D',
  'AT72', 'AT75', 'AT76',
])

const ROTOR_PREFIXES = ['EC', 'AS3', 'AS5', 'AS6', 'AS7', 'B06', 'B47', 'H1', 'H2', 'H6', 'R22', 'R44', 'R66', 'UH', 'AH', 'CH', 'S6', 'S7', 'S9', 'MD5', 'MD9']
const TYPE_ROTOR = new Set([
  'V22',  // V-22 Osprey — closer to rotor than fixed-wing for radar purposes
])
