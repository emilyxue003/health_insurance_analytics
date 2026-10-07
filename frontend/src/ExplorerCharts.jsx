const compact = (value) => new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(value)
const exact = (value) => new Intl.NumberFormat('en-US').format(value)

function ChartPanel({ title, subtitle, resource, children }) {
  return <section className="data-panel"><div className="panel-heading"><div><h2>{title}</h2><p>{subtitle}</p></div></div>
    {resource.status === 'loading' ? <div className="panel-state" role="status"><span className="loading-dot" />{IS_DEMO ? 'Loading saved summaries…' : 'Calculating database summaries…'}</div>
      : resource.status === 'error' ? <div className="panel-state error-message" role="alert">{IS_DEMO ? 'Summary unavailable. Reload this page to retry.' : 'Summary unavailable. Check the backend and refresh.'}</div> : children}
  </section>
}

export function AgeChart({ resource }) {
  const rows = (resource.data?.age_distribution || []).filter((row) => row.count || row.band !== 'Unknown / future DOB')
  const max = Math.max(...rows.map((row) => row.count), 1)
  const step = 300 / Math.max(rows.length, 1)
  return <ChartPanel title="Age distribution" subtitle={`Members · Age as of ${resource.data?.as_of || 'reporting date'}`} resource={resource}>
    <div className="age-chart"><svg viewBox="0 0 370 255" role="img" aria-label={rows.map((row) => `${row.band}: ${exact(row.count)} members`).join(', ')}>
      {[0, 0.5, 1].map((fraction) => <g key={fraction}><line x1="52" x2="355" y1={210 - fraction * 170} y2={210 - fraction * 170} stroke="#e9e9e6" strokeDasharray="3 5" /><text x="45" y={214 - fraction * 170} textAnchor="end" fill="#827f78" fontSize="11">{compact(max * fraction)}</text></g>)}
      {rows.map((row, index) => <g key={row.band}><rect x={56 + index * step} y={210 - row.count / max * 170} width={Math.max(step - 9, 1)} height={row.count / max * 170} rx="3" fill="#c66200"><title>{row.band}: {exact(row.count)} members</title></rect><text x={56 + index * step + (step - 9) / 2} y="232" textAnchor="middle" fill="#827f78" fontSize={row.band.length > 10 ? '7' : '10'}>{row.band}</text></g>)}
    </svg><p className="chart-footnote">Missing or future birth dates are counted separately.</p></div>
  </ChartPanel>
}

export function SexChart({ resource }) {
  const rows = resource.data?.sex_distribution || []
  const total = rows.reduce((sum, row) => sum + row.count, 0)
  const colors = ['#c66200', '#0083ad', '#26956d', '#b8b2aa']
  const arcs = rows.map((row, index) => {
    const length = total ? row.count / total * 100 : 0
    const offset = total ? rows.slice(0, index).reduce((sum, item) => sum + item.count, 0) / total * 100 : 0
    return <circle key={row.sex} cx="100" cy="100" r="65" fill="none" stroke={colors[index]} strokeWidth="22" pathLength="100" strokeDasharray={`${length} ${100 - length}`} strokeDashoffset={-offset} />
  })
  return <ChartPanel title="Sex distribution" subtitle="Recorded sex · All member records" resource={resource}>
    <div className="sex-chart"><svg viewBox="0 0 200 200" role="img" aria-label={rows.map((row) => `${row.sex}: ${exact(row.count)} members`).join(', ')}><circle cx="100" cy="100" r="65" fill="none" stroke="#f3f0ea" strokeWidth="22" /><g transform="rotate(-90 100 100)">{arcs}</g><text x="100" y="98" textAnchor="middle" fontSize="23" fill="#373630" fontWeight="650">{compact(total)}</text><text x="100" y="117" textAnchor="middle" fontSize="11" fill="#989088">members</text></svg>
      <div className="sex-legend">{rows.map((row, index) => <div key={row.sex}><span className="legend-label"><span style={{ background: colors[index] }} />{row.sex === 'O' ? 'Other (O)' : row.sex}</span><span title={`${exact(row.count)} members`}>{total ? `${(row.count / total * 100).toFixed(1)}%` : 'No members'}</span></div>)}</div>
    </div>
  </ChartPanel>
}

export function CoverageChart({ resource }) {
  const rows = resource.data?.coverage_tiers || []
  const max = Math.max(...rows.map((row) => row.count), 1)
  return <ChartPanel title="Coverage tiers" subtitle="Enrollment records · All coverage periods" resource={resource}>
    <div className="coverage-chart" role="img" aria-label={rows.map((row) => `${row.tier}: ${exact(row.count)} enrollment records`).join(', ')}>
      {rows.length ? rows.map((row) => <div className="coverage-row" key={row.tier}><span>{row.tier}</span><div className="bar-track"><div className="bar-fill" style={{ width: `${row.count / max * 100}%` }} /></div><span className="bar-value" title={exact(row.count)}>{compact(row.count)}</span></div>) : <p className="chart-footnote">No enrollment records.</p>}
      <p className="chart-footnote">Each enrollment is counted once, including ended coverage.</p>
    </div>
  </ChartPanel>
}
import { IS_DEMO } from './api.js'
