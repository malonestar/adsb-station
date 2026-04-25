import type { AircraftState } from '@/types/api'

export function pickIcon(ac: AircraftState): string {
  if (ac.is_military) return '/icons/military.svg'
  switch (ac.category) {
    case 'A1':
      return '/icons/light.svg'
    case 'A2':
      return '/icons/small.svg'
    case 'A3':
    case 'A4':
      return '/icons/narrow.svg'
    case 'A5':
    case 'A6':
      return '/icons/heavy.svg'
    case 'A7':
      return '/icons/rotor.svg'
    case 'B1':
      return '/icons/glider.svg'
    case 'B2':
      return '/icons/glider.svg'
    case 'B6':
      return '/icons/drone.svg'
    default:
      return '/icons/narrow.svg'
  }
}

export function iconSizeForCategory(cat: string | null): number {
  switch (cat) {
    case 'A5':
    case 'A6':
      return 32
    case 'A3':
    case 'A4':
      return 26
    case 'A7':
      return 22
    case 'A1':
    case 'A2':
      return 20
    default:
      return 24
  }
}
