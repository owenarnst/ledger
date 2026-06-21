// Issue #10 — hand-rolled routing for the two deep-linkable surfaces the Ledger
// SessionStart nudge emits: the project worklist and a single topic page. Only
// these two URL shapes exist, so there is no router dependency — parseRoute reads
// a pathname into a Route, and buildPath is its inverse. The topic route lands on
// the topic page (where difficulty is chosen); it never creates a check.

export type Route =
  | { screen: 'dashboard'; slug?: string }
  | { screen: 'topic'; slug: string; topicId: string }

// /                          → dashboard (default project)
// /p/:slug                   → dashboard (named project's worklist)
// /p/:slug/topics/:topicId   → topic page
export function parseRoute(pathname: string): Route {
  const parts = pathname.split('/').filter(Boolean)
  if (parts[0] === 'p' && parts[1]) {
    const slug = decodeURIComponent(parts[1])
    if (parts[2] === 'topics' && parts[3]) {
      return { screen: 'topic', slug, topicId: decodeURIComponent(parts[3]) }
    }
    return { screen: 'dashboard', slug }
  }
  return { screen: 'dashboard' }
}

export function buildPath(route: Route): string {
  if (route.screen === 'topic') {
    return `/p/${encodeURIComponent(route.slug)}/topics/${encodeURIComponent(route.topicId)}`
  }
  return route.slug ? `/p/${encodeURIComponent(route.slug)}` : '/'
}
