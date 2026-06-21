// Issue #23 — Worklist dashboard. Renders the analyst-proposed, verified worklist
// (ADR-0002 / #22) as compact rows in the analyst's supplied order. Each row shows
// exactly four fields — Topic title, ownership status, verified evidence summary,
// and categorical impact — and the whole row is the only interaction: it opens the
// Topic page. No Open button, no Start check, no signal chips, no numeric score.
import { Card } from '../adapt'
import { badge, impactChip } from '../theme'

const mono = "'JetBrains Mono', monospace"

interface DashboardProps {
  topics: Card[]
  onOpen: (card: Card) => void
}

export default function Dashboard({ topics, onOpen }: DashboardProps) {
  return (
    <div className="lg-scroll" style={{ flex: 1, overflow: 'auto' }}>
      <div style={{ maxWidth: 980, margin: '0 auto', padding: '40px 44px 80px' }}>
        <div style={{ marginBottom: 26 }}>
          <h1 style={{ fontSize: 23, fontWeight: 600, letterSpacing: '-0.02em', margin: '0 0 7px' }}>
            Ownership worklist
          </h1>
          <div style={{ color: 'var(--mut)', fontSize: 14, maxWidth: 620 }}>
            Load-bearing decisions your coding agents shipped, ordered by how much they matter and how thinly you own
            them. Ledger recommends checks — it never asserts the gap.
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {topics.map((t) => {
            const open = () => onOpen(t)
            return (
              <div
                key={t.id}
                className="lg-hover-row"
                role="button"
                tabIndex={0}
                aria-label={`Open ${t.title}`}
                onClick={open}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    open()
                  }
                }}
                style={{
                  border: '1px solid var(--bd)',
                  background: 'var(--panel)',
                  borderRadius: 11,
                  padding: '16px 18px',
                  cursor: 'pointer',
                }}
              >
                {/* Field 1 (title) + Field 2 (ownership status) */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                  <span style={{ fontSize: 15, fontWeight: 550, letterSpacing: '-0.01em' }}>{t.title}</span>
                  <span style={{ ...badge(t.badge), ...(t.faint ? { opacity: 0.85 } : null) }}>{t.badgeLabel}</span>
                </div>
                {/* Field 3 (evidence summary) + Field 4 (impact level) */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 11 }}>
                  <span style={{ flex: 1, minWidth: 0, fontFamily: mono, fontSize: 12, color: 'var(--mut)' }}>
                    {t.evidenceSummary}
                  </span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 7, flex: 'none' }}>
                    <span
                      style={{
                        fontFamily: mono,
                        fontSize: 10,
                        letterSpacing: '0.06em',
                        textTransform: 'uppercase',
                        color: 'var(--faint)',
                      }}
                    >
                      Impact
                    </span>
                    <span style={impactChip(t.impact)}>{t.impact}</span>
                  </span>
                </div>
              </div>
            )
          })}
        </div>

        <div
          style={{
            marginTop: 22,
            fontSize: 12,
            color: 'var(--faint)',
            fontFamily: mono,
            display: 'flex',
            alignItems: 'center',
            gap: 7,
          }}
        >
          <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
            <circle cx="8" cy="8" r="6.2" stroke="currentColor" strokeWidth="1.2" />
            <path d="M8 5.2v3.4M8 10.6h.01" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
          </svg>
          One real repo. Only the tenant-isolation topic is grounded in real evidence for this demo.
        </div>
      </div>
    </div>
  )
}
