// Issue #6 — Ranked ownership worklist (curated order). Rank #1 expanded into
// the authored "why selected". Provider-labeled chips per row.
import React from 'react'
import { badge, chipForKind } from '../theme.js'

const mono = "'JetBrains Mono', monospace"

export default function Dashboard({ topics, onOpen }) {
  return (
    <div className="lg-scroll" style={{ flex: 1, overflow: 'auto' }}>
      <div style={{ maxWidth: 980, margin: '0 auto', padding: '40px 44px 80px' }}>
        <div style={{ marginBottom: 26 }}>
          <h1 style={{ fontSize: 23, fontWeight: 600, letterSpacing: '-0.02em', margin: '0 0 7px' }}>
            Ownership worklist
          </h1>
          <div style={{ color: 'var(--mut)', fontSize: 14, maxWidth: 620 }}>
            Load-bearing decisions your coding agents shipped, ranked by how much they matter and how thinly you own
            them. Ledger recommends checks — it never asserts the gap.
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {topics.map((t, i) => (
            <div
              key={t.id}
              className="lg-hover-row"
              onClick={t.isHero ? () => onOpen(t) : undefined}
              style={{
                border: '1px solid var(--bd)',
                background: 'var(--panel)',
                borderRadius: 11,
                padding: '16px 18px',
                cursor: t.isHero ? 'pointer' : 'default',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 16 }}>
                <div
                  style={{
                    fontFamily: mono,
                    fontSize: 13,
                    color: 'var(--faint)',
                    width: 20,
                    flex: 'none',
                    paddingTop: 1,
                  }}
                >
                  {String(i + 1).padStart(2, '0')}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                    <span style={{ fontSize: 15, fontWeight: 550, letterSpacing: '-0.01em' }}>{t.title}</span>
                    <span style={{ ...badge(t.badge), ...(t.faint ? { opacity: 0.85 } : null) }}>{t.badgeLabel}</span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 7, flexWrap: 'wrap', marginTop: 11 }}>
                    {t.chips.map((c, ci) => (
                      <span key={ci} style={chipForKind(c.k)}>
                        {c.label}
                      </span>
                    ))}
                  </div>
                </div>
                {t.isHero && (
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                      color: 'var(--accent)',
                      fontSize: 13,
                      fontWeight: 500,
                      flex: 'none',
                      paddingTop: 2,
                    }}
                  >
                    Open <span style={{ fontSize: 15 }}>→</span>
                  </div>
                )}
              </div>
              {t.expanded && (
                <div
                  style={{
                    marginTop: 14,
                    paddingTop: 13,
                    borderTop: '1px solid var(--bd)',
                    display: 'flex',
                    gap: 10,
                  }}
                >
                  <div
                    style={{
                      width: 6,
                      height: 6,
                      borderRadius: '50%',
                      background: 'var(--accent)',
                      marginTop: 7,
                      flex: 'none',
                    }}
                  />
                  <div style={{ fontSize: 13, color: 'var(--mut)', lineHeight: 1.6 }}>
                    <span style={{ color: 'var(--tx)', fontWeight: 500 }}>Why it's #1.</span> {t.why}
                  </div>
                </div>
              )}
            </div>
          ))}
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
