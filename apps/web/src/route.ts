/** The address bar as the single source of truth for where you are.
 *
 *  Every view in this app used to live in React state alone. Clicking a
 *  company moved you to its page and left the URL on the landing page, which
 *  broke three things at once: you could not send anyone a company, you could
 *  not bookmark one, and the browser's back button left the site altogether
 *  instead of stepping back to the sector you came from.
 *
 *  Hashes rather than paths, because the site is served as static files.
 *  A path like /company/XNAS:AMD would need the host to rewrite unknown paths
 *  onto index.html; a hash never reaches the server, so a deep link works on
 *  any static host, including an offline copy opened from disk.
 *
 *  Company uids contain a colon (XNAS:AMD). Colons are legal in a fragment but
 *  are mangled by enough chat clients and mail readers that a shared link
 *  arrives broken, so the wire form uses a dash and converts back on read.
 */
export type Surface = 'live' | 'signals' | 'news' | 'replay' | 'simulate'

export type Route =
  | { k: 'home' }
  | { k: 'globe' }
  | { k: 'country'; iso2: string }
  | { k: 'sector'; iso2: string; sectorCode: string }
  | { k: 'company'; uid: string }
  | { k: 'event' }

export type Loc = { surface: Surface; route: Route }

const SURFACES: Surface[] = ['live', 'signals', 'news', 'replay', 'simulate']

/** XNAS:AMD <-> XNAS-AMD. Only the first dash is a colon: tickers such as
 *  BRK-B carry their own, and turning those back into colons would ask the
 *  API for a company that does not exist. */
export const uidToSlug = (uid: string) => uid.replace(':', '-')
export const slugToUid = (slug: string) => slug.replace('-', ':')

export function format({ surface, route }: Loc): string {
  const head = surface === 'live' ? '' : `/${surface}`
  switch (route.k) {
    case 'home':    return `#${head || '/'}`
    case 'globe':   return `#${head}/globe`
    case 'event':   return `#${head}/event`
    case 'country': return `#${head}/country/${route.iso2}`
    case 'sector':  return `#${head}/country/${route.iso2}/${route.sectorCode}`
    case 'company': return `#${head}/company/${uidToSlug(route.uid)}`
  }
}

export function parse(hash: string): Loc {
  const parts = hash.replace(/^#\/?/, '').split('/').filter(Boolean)
  let surface: Surface = 'live'
  if (parts.length && SURFACES.includes(parts[0] as Surface)) {
    surface = parts.shift() as Surface
  }
  const [head, a, b] = parts
  if (head === 'company' && a) return { surface, route: { k: 'company', uid: slugToUid(a) } }
  if (head === 'country' && a) {
    return b
      ? { surface, route: { k: 'sector', iso2: a.toUpperCase(), sectorCode: b } }
      : { surface, route: { k: 'country', iso2: a.toUpperCase() } }
  }
  if (head === 'globe') return { surface, route: { k: 'globe' } }
  if (head === 'event') return { surface, route: { k: 'event' } }
  return { surface, route: { k: 'home' } }
}

/** Where "back" should go, so the crumb and the browser agree.
 *
 *  Derived from the route rather than remembered, because a view reached by a
 *  pasted link has no history to remember: arriving straight at a company
 *  should still offer its sector, not a dead button. */
export function parentOf(route: Route): Route {
  switch (route.k) {
    case 'sector':  return { k: 'country', iso2: route.iso2 }
    case 'country': return { k: 'globe' }
    default:        return { k: 'home' }
  }
}
