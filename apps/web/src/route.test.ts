import { describe, it, expect } from 'vitest'
import { parse, format, uidToSlug, slugToUid, parentOf, type Loc } from './route'

describe('uid <-> slug', () => {
  it('swaps the colon for a dash and back', () => {
    expect(uidToSlug('XNAS:AAPL')).toBe('XNAS-AAPL')
    expect(slugToUid('XNAS-AAPL')).toBe('XNAS:AAPL')
  })
  it('round-trips a uid through a slug', () => {
    for (const uid of ['XNYS:GE', 'XETR:IU2', 'XNSE:TCS']) {
      expect(slugToUid(uidToSlug(uid))).toBe(uid)
    }
  })
})

describe('format then parse is the identity', () => {
  const cases: Loc[] = [
    { surface: 'live', route: { k: 'home' } },
    { surface: 'stories', route: { k: 'home' } },
    { surface: 'live', route: { k: 'globe' } },
    { surface: 'signals', route: { k: 'event' } },
    { surface: 'live', route: { k: 'country', iso2: 'US' } },
    { surface: 'news', route: { k: 'country', iso2: 'IN' } },
    { surface: 'live', route: { k: 'sector', iso2: 'US', sectorCode: 'tech' } },
    { surface: 'live', route: { k: 'company', uid: 'XNAS:NVDA' } },
  ]
  for (const loc of cases) {
    it(`${loc.surface} / ${loc.route.k}`, () => {
      expect(parse(format(loc))).toEqual(loc)
    })
  }
})

describe('parse', () => {
  it('reads the surface prefix and upper-cases the country', () => {
    expect(parse('#/signals/country/us')).toEqual({
      surface: 'signals', route: { k: 'country', iso2: 'US' },
    })
  })
  it('falls back to the live home for an unknown hash', () => {
    expect(parse('#/nonsense/path')).toEqual({ surface: 'live', route: { k: 'home' } })
    expect(parse('')).toEqual({ surface: 'live', route: { k: 'home' } })
  })
  it('turns a company slug back into a uid', () => {
    expect(parse('#/company/XNAS-AAPL').route).toEqual({ k: 'company', uid: 'XNAS:AAPL' })
  })
})

describe('parentOf', () => {
  it('climbs sector -> country -> globe -> home', () => {
    expect(parentOf({ k: 'sector', iso2: 'US', sectorCode: 'tech' })).toEqual({ k: 'country', iso2: 'US' })
    expect(parentOf({ k: 'country', iso2: 'US' })).toEqual({ k: 'globe' })
    expect(parentOf({ k: 'company', uid: 'XNAS:AAPL' })).toEqual({ k: 'home' })
  })
})
