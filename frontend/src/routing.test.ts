import { describe, expect, it } from 'vitest'
import { buildPath, parseRoute, type Route } from './routing'

describe('parseRoute', () => {
  it('maps the root path to the default dashboard', () => {
    expect(parseRoute('/')).toEqual({ screen: 'dashboard' })
    expect(parseRoute('')).toEqual({ screen: 'dashboard' })
  })

  it('maps /p/:slug to a named project worklist', () => {
    expect(parseRoute('/p/docs-search-api')).toEqual({
      screen: 'dashboard',
      slug: 'docs-search-api',
    })
  })

  it('maps /p/:slug/topics/:topicId to a topic page', () => {
    expect(parseRoute('/p/docs-search-api/topics/tenant-cache-isolation')).toEqual({
      screen: 'topic',
      slug: 'docs-search-api',
      topicId: 'tenant-cache-isolation',
    })
  })

  it('tolerates trailing slashes', () => {
    expect(parseRoute('/p/docs-search-api/topics/abc/')).toEqual({
      screen: 'topic',
      slug: 'docs-search-api',
      topicId: 'abc',
    })
  })

  it('decodes percent-encoded segments', () => {
    expect(parseRoute('/p/my%20repo/topics/a%2Fb')).toEqual({
      screen: 'topic',
      slug: 'my repo',
      topicId: 'a/b',
    })
  })

  it('falls back to the dashboard for unknown paths', () => {
    expect(parseRoute('/anything/else')).toEqual({ screen: 'dashboard' })
    expect(parseRoute('/p')).toEqual({ screen: 'dashboard' })
  })
})

describe('buildPath', () => {
  it('builds the root path when no slug is given', () => {
    expect(buildPath({ screen: 'dashboard' })).toBe('/')
  })

  it('builds the worklist path for a named project', () => {
    expect(buildPath({ screen: 'dashboard', slug: 'docs-search-api' })).toBe('/p/docs-search-api')
  })

  it('builds the topic path', () => {
    expect(
      buildPath({ screen: 'topic', slug: 'docs-search-api', topicId: 'tenant-cache-isolation' }),
    ).toBe('/p/docs-search-api/topics/tenant-cache-isolation')
  })

  it('round-trips with parseRoute', () => {
    const routes: Route[] = [
      { screen: 'dashboard' },
      { screen: 'dashboard', slug: 'docs-search-api' },
      { screen: 'topic', slug: 'docs-search-api', topicId: 'tenant-cache-isolation' },
    ]
    for (const route of routes) {
      expect(parseRoute(buildPath(route))).toEqual(route)
    }
  })
})
