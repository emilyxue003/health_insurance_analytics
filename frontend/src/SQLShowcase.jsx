import { useState } from 'react'
import { RESULT_EXPORT_URL } from './api.js'
import DatabaseSchema from './DatabaseSchema.jsx'

const number = (value) => new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 }).format(value)
const compact = (value) => new Intl.NumberFormat('en-US', { notation: 'compact' }).format(value)
const dollars = (value) => value == null ? 'Unavailable' : new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(value)
const readableDate = (value) => new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' }).format(new Date(`${value}T00:00:00Z`))
const methods = {
  regional_premiums: {
    title: 'Regional premiums within comparable coverage',
    definition: 'For each enrollment, divide its premium by the mean for its plan and coverage tier, then average those ratios by state. Index 100 equals the peer mean. Each peer group includes the enrollment itself and at least two records.',
    caveat: 'State counts are shown beside each value. This controls only plan and coverage tier, not age, health, insurer rating rules, or coverage duration. Differences are descriptive.',
  },
  housing_premiums: {
    title: 'Housing insecurity and linked premiums',
    definition: 'Keep plan and coverage cells with both recorded housing statuses. Calculate each group’s mean premium within each cell, then give both groups the same cell weight: the smaller group count.',
    caveat: 'Only members in overlapping cells contribute. Linked enrollment premiums are member-weighted and may cover a household. Housing insecurity is not income; this is not an affordability or causal fairness estimate.',
  },
  conditions_costs: {
    title: 'Recorded conditions, premiums, and claim spending',
    definition: 'Count distinct conditions recorded by the cutoff and sum claims per member before joining. Keep members with no recorded diagnoses or claims, then group by condition count.',
    caveat: 'Premiums come from the linked enrollment, not historical coverage for each claim. Claims span a separate fixed period. Premium billing frequency is undocumented, so no loss ratio is calculated. This comparison is not risk-adjusted.',
  },
}

function ResultTable({ rows }) {
  if (!rows.length) return <p className="sql-empty">No records meet this selection.</p>
  const columns = Object.keys(rows[0])
  return <div className="sql-result-table"><table><thead><tr>{columns.map((column) => <th key={column}>{column.replaceAll('_', ' ')}</th>)}</tr></thead><tbody>{rows.map((row, i) => <tr key={i}>{columns.map((column) => <td key={column}>{row[column] == null ? 'NULL' : typeof row[column] === 'number' ? number(row[column]) : row[column]}</td>)}</tr>)}</tbody></table></div>
}

function MoneyBars({ rows, field, label }) {
  const maximum = Math.max(...rows.map((row) => row[field] || 0), 1)
  return <section className="sql-money-chart"><h3>{label}</h3><p className="sql-axis-note">USD · bars start at zero</p>{rows.map((row) => <div className="sql-money-row" key={row.label}><span>{row.label}</span><div className="bar-track"><div className="bar-fill" style={{ width: `${Math.max(row[field] || 0, 0) / maximum * 100}%` }} /></div><strong>{dollars(row[field])}</strong></div>)}</section>
}

function CaseChart({ selected, rows }) {
  if (selected.id === 'regional_premiums') {
    const maximum = Math.max(...rows.map((row) => row.premium_index), 100) * 1.1
    return <div className="sql-region-chart"><p className="sql-axis-note">Premium index · 100 = same-plan, same-tier mean · axis starts at zero</p>{rows.map((row) => <div className="sql-index-row" key={row.state}><span>{row.state}<small>n = {number(row.enrollments)}</small></span><div className="sql-index-track"><div className="bar-fill" style={{ width: `${row.premium_index / maximum * 100}%` }} /><span className="sql-reference" style={{ left: `${100 / maximum * 100}%` }} /></div><strong>{number(row.premium_index)}</strong></div>)}</div>
  }
  if (selected.id === 'housing_premiums') {
    const row = rows[0]
    if (!row?.matched_cells) return <p className="sql-empty">No plan and coverage cells contain both recorded housing groups. A comparable gap cannot be calculated.</p>
    return <><p className="sql-result-scope">{number(row.matched_cells)} matched cells · {number(row.yes_members)} housing-insecure members · {number(row.no_members)} members recorded without housing insecurity</p><MoneyBars rows={[{ label: 'Recorded yes', value: row.yes_premium }, { label: 'Recorded no', value: row.no_premium }]} field="value" label="Premium with common plan and coverage weights" /><p className="sql-gap">Recorded yes minus recorded no: <strong>{dollars(row.premium_difference)} ({row.difference_pct == null ? 'Unavailable' : `${number(row.difference_pct)}%`})</strong></p></>
  }
  const chartRows = rows.map((row) => ({ ...row, label: `${row.conditions} conditions` }))
  return <><p className="sql-result-scope">{number(rows.reduce((sum, row) => sum + row.members, 0))} members · {number(rows.reduce((sum, row) => sum + row.members_with_claims, 0))} with claims · Zero-claim members remain in the denominator</p><div className="sql-paired-charts"><MoneyBars rows={chartRows} field="average_premium" label="Mean linked enrollment premium" /><MoneyBars rows={chartRows} field="average_claim_amount" label="Mean claim spending per member" /></div></>
}

function DownloadResults({ selected, data, minimum, isDemo }) {
  const threshold = selected.id === 'regional_premiums' ? minimum : 0
  const parameters = new URLSearchParams({ ...data.parameters, case_id: selected.id, minimum_state_count: String(threshold) })
  const href = isDemo ? `sql/results/${selected.id}-${threshold}.json` : `${RESULT_EXPORT_URL}?${parameters}`
  return <a href={href} download={`healthpulse-${selected.id}-results.json`}>Download these results</a>
}

function PeriodControl({ period, onPeriodChange }) {
  return <form className="sql-period" key={JSON.stringify(period)} onSubmit={(event) => {
    event.preventDefault()
    const values = Object.fromEntries(new FormData(event.currentTarget))
    onPeriodChange(values)
  }}><label>Coverage cutoff<input name="as_of" type="date" defaultValue={period.as_of} required /></label><label>Claims start<input name="claims_start" type="date" defaultValue={period.claims_start} required /></label><label>Claims end (exclusive)<input name="claims_end" type="date" defaultValue={period.claims_end} required /></label><button type="submit">Apply period</button></form>
}

export default function SQLShowcase({ resource, isDemo, period, onPeriodChange }) {
  const [caseId, setCaseId] = useState('regional_premiums')
  const [minimum, setMinimum] = useState(0)
  const snapshot = resource.data
  const data = snapshot?.sql_showcase
  const controls = !isDemo && <PeriodControl period={period} onPeriodChange={onPeriodChange} />
  if (resource.status !== 'ready' || !data) return <>{controls}<div className="panel-state" role={resource.status === 'error' ? 'alert' : 'status'}>{resource.status === 'error' ? resource.errorMessage || 'Premium results could not be loaded. Check the backend Terminal for the error.' : resource.status === 'ready' ? 'Full-data SQL evidence is unavailable.' : 'Calculating full-data premium results…'}</div></>
  const selected = data.cases.find((item) => item.id === caseId)
  const rows = selected.id === 'regional_premiums' ? selected.rows.filter((row) => row.enrollments >= minimum) : selected.rows
  const method = methods[selected.id]
  return <div className="sql-showcase">
    {controls}
    <section className="sql-scope"><strong>Synthetic data for {compact(data.total_members)} members · Full-data premium analysis</strong><p>Source: {data.source}. {number(data.eligible_members)} members and {number(data.eligible_enrollments)} enrollment records meet the coverage and premium rules at {readableDate(data.parameters.as_of)}. {isDemo ? 'The public demo displays saved full-data results; record browsing remains a 200-member sample.' : 'The regular dashboard queries the full MySQL database for the selected period.'}</p><p>Premium values are shown as recorded in USD; billing frequency is undocumented. These comparisons explore disparities, not discrimination or algorithmic fairness.</p></section>
    <nav className="sql-case-nav" aria-label="SQL case studies">{data.cases.map((item) => <button type="button" key={item.id} aria-pressed={item.id === caseId} onClick={() => setCaseId(item.id)}>{methods[item.id].title}</button>)}</nav>
    <section className="data-panel sql-case" key={selected.id} id={selected.id}>
      <div className="panel-heading"><div><h2>{selected.question}</h2><p>{selected.grain} grain · Coverage active {readableDate(data.parameters.as_of)}{selected.id === 'conditions_costs' ? ` · Claims ${readableDate(data.parameters.claims_start)} through ${readableDate(new Date(new Date(`${data.parameters.claims_end}T00:00:00Z`).getTime() - 86400000).toISOString().slice(0, 10))}` : ''}</p></div></div>
      <div className="sql-case-body"><div className="sql-techniques">{selected.techniques.map((technique) => <span key={technique}>{technique}</span>)}</div><p className="sql-definition">{method.definition}</p>
        {selected.id === 'regional_premiums' && <label className="sql-filter">Minimum enrollment count per displayed state <select value={minimum} onChange={(event) => setMinimum(Number(event.target.value))}>{[0, 10000, 50000, 100000, 1000000].map((value) => <option key={value} value={value}>{value === 0 ? 'All states' : number(value)}</option>)}</select><span>{rows.length} of {selected.rows.length} states displayed</span></label>}
        <p className="sql-caveat">{method.caveat}</p>
        {rows.length ? <CaseChart selected={selected} rows={rows} /> : <p className="sql-empty">No states meet this minimum. Lower the displayed-state threshold to inspect the results.</p>}
        <div className="sql-actions"><a href={`sql/${selected.id}.sql`} download>Download SQL</a><DownloadResults selected={selected} data={data} minimum={minimum} isDemo={isDemo} /></div>
        <details className="sql-code"><summary>View SQL for this result</summary><p>{isDemo ? 'SQL behind these saved full-source results.' : 'SQL used for this database result.'} <a href="sql/README.md" download>Methods and source details</a></p><pre><code>{selected.sql}</code></pre><p>Parameters: {JSON.stringify(data.parameters)}</p></details>
        <details className="sql-values"><summary>View exact results and counts</summary><ResultTable rows={rows} /></details>
        <details className="sql-evidence"><summary>Validation and interpretation</summary><p>{data.validation} Tests also cover repeated diagnoses, multiple claims, no claims, excluded future dates, coverage end-date boundaries, zero premiums, empty results, and missing comparison groups.</p><p>No income or pricing-algorithm output is available. Age, geography, health, and plan selection can confound these comparisons. Diagnosis count means recorded distinct conditions by the cutoff, not clinical severity.</p></details>
      </div>
    </section>
    {!isDemo && <details className="data-panel project-about"><summary>Database schema</summary><div className="about-content"><DatabaseSchema schema={snapshot.schema} /></div></details>}
  </div>
}
