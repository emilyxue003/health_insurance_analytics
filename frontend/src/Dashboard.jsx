import { useEffect, useState } from 'react'
import { Activity, ArrowUpRight, Building2, ClipboardList, Database, DollarSign, Heart, MapPin, RefreshCw, Search, Shield, Stethoscope, Table2, TrendingUp, Users } from 'lucide-react'
import { AgeChart, CoverageChart, SexChart } from './ExplorerCharts.jsx'
import TableBrowser from './TableBrowser.jsx'
import { IS_DEMO, requestData } from './api.js'
import { describeRequestError } from './requestErrors.js'
import DemoAbout from './DemoAbout.jsx'
import DemoDates from './DemoDates.jsx'
import PopulationHealth from './PopulationHealth.jsx'
import SQLShowcase from './SQLShowcase.jsx'
import QueryPerformance from './QueryPerformance.jsx'
import { claimsPeriod } from './demoDates.js'
import './Dashboard.css'

const compact = (value, currency = false) => new Intl.NumberFormat('en-US', {
  notation: 'compact', maximumFractionDigits: 1,
  ...(currency ? { style: 'currency', currency: 'USD' } : {}),
}).format(value)
const full = (value) => new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 }).format(value)

function useResource(path, revision = 0) {
  const [resource, setResource] = useState({ path: null, status: 'loading', data: null })
  useEffect(() => {
    if (!path) return
    const controller = new AbortController()
    requestData(path, { signal: controller.signal, timeout: 120000 })
      .then((data) => setResource({ path, revision, status: 'ready', data }))
      .catch((error) => {
        if (!controller.signal.aborted) setResource({ path, revision, status: 'error', data: null,
          errorMessage: describeRequestError(error, { premium: path.startsWith('/api/stats/premium-equity'), isDemo: IS_DEMO }) })
      })
    return () => controller.abort()
  }, [path, revision])
  return resource.path === path && resource.revision === revision ? resource : { status: 'loading', data: null }
}

function ResourceState({ resource, empty = false }) {
  if (resource.status === 'loading') return <div className="panel-state" role="status"><span className="loading-dot" />{IS_DEMO ? 'Loading saved results…' : 'Loading database results…'}</div>
  if (resource.status === 'error') return <div className="panel-state error-message" role="alert">{resource.errorMessage || 'Unable to load these results.'}</div>
  if (empty) return <div className="panel-state">No records returned.</div>
  return null
}

function Panel({ title, subtitle, children }) {
  return <section className="data-panel"><div className="panel-heading"><div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div><span className="panel-mark"><Database size={14} />{IS_DEMO ? 'Full dataset' : 'Database'}</span></div>{children}</section>
}

function StateChart({ resource }) {
  const rows = [...(resource.data || [])].sort((a, b) => b.count - a.count).slice(0, 10)
  const maximum = Math.max(...rows.map((row) => row.count), 1)
  return <Panel title="Top 10 states" subtitle="Members by state of residence">
    {resource.status !== 'ready' || !rows.length ? <ResourceState resource={resource} empty={!rows.length} /> : <div className="state-chart" role="img" aria-label={rows.map((row) => `${row.state || 'Unknown'}: ${full(row.count)} members`).join(', ')}>
      {rows.map((row) => <div className="bar-row" key={row.state || 'unknown'}><span className="bar-label">{row.state || 'N/A'}</span><div className="bar-track"><div className="bar-fill" style={{ width: `${row.count / maximum * 100}%` }} /></div><span className="bar-value">{compact(row.count)}</span></div>)}
      <p className="chart-footnote">Showing the largest member populations</p>
    </div>}
  </Panel>
}

function ClaimsChart({ resource }) {
  const rows = resource.data || []
  const max = Math.max(...rows.map((row) => row.total), 1)
  const points = rows.map((row, i) => `${62 + i / Math.max(rows.length - 1, 1) * 548},${210 - row.total / max * 170}`).join(' ')
  return <Panel title="Monthly claims" subtitle={`Total claim amount · ${resource.status === 'ready' ? claimsPeriod(rows) : 'Loading period…'}`}>
    {resource.status !== 'ready' || !rows.length ? <ResourceState resource={resource} empty={!rows.length} /> : <div className="claims-chart">
      <svg viewBox="0 0 650 255" role="img" aria-label={`Monthly claims, ${rows[0].month} to ${rows.at(-1).month}. Detailed values below.`}>
        {[0, 0.5, 1].map((fraction) => <g key={fraction}><line x1="62" x2="610" y1={210 - fraction * 170} y2={210 - fraction * 170} stroke="#e9e9e6" strokeDasharray="3 5" /><text x="51" y={214 - fraction * 170} textAnchor="end" fill="#827f78" fontSize="12">{compact(max * fraction, true)}</text></g>)}
        <polygon points={`62,210 ${points} ${rows.length === 1 ? '62' : '610'},210`} fill="#fff2e3" />
        <polyline points={points} fill="none" stroke="#df7900" strokeWidth="3" strokeLinejoin="round" strokeLinecap="round" />
        {rows.length === 1 && <circle cx="62" cy={210 - rows[0].total / max * 170} r="4" fill="#df7900" />}
        <text x="62" y="242" fill="#827f78" fontSize="12">{rows[0].month}</text>
        <text x="610" y="242" fill="#827f78" fontSize="12" textAnchor="end">{rows.at(-1).month}</text>
      </svg>
      <details className="chart-details"><summary>View monthly values</summary><div className="small-table-wrap"><table><thead><tr><th>Month</th><th>Claim amount</th></tr></thead><tbody>{rows.map((row) => <tr key={row.month}><td>{row.month}</td><td>${full(row.total)}</td></tr>)}</tbody></table></div></details>
    </div>}
  </Panel>
}

const memberColumns = [
  ['member_id', 'Member ID'], ['DOB', 'Date of birth'], ['Sex', 'Sex'], ['State', 'State'],
  ['Primary_Care_Facility_ID', 'Care facility ID'], ['heart_rate', 'Heart rate'],
  ['blood_pressure', 'Blood pressure'], ['blood_oxygen', 'Blood oxygen'],
  ['Weight', 'Weight'], ['Height', 'Height'], ['smoker', 'Smoker'], ['drinker', 'Drinker'],
]

function MemberExplorer({ exampleIds = [] }) {
  const [input, setInput] = useState('')
  const [lookup, setLookup] = useState({ status: 'idle', data: null })
  async function search(event) {
    event.preventDefault()
    const id = Number(input)
    if (!Number.isSafeInteger(id) || id < 1) {
      setLookup({ status: 'error', data: null, message: 'Enter a positive whole-number member ID.' })
      return
    }
    setLookup({ status: 'loading', data: null })
    try {
      const data = await requestData(`/members/${id}`, { timeout: 15000 })
      setLookup({ status: 'ready', data })
    } catch (error) {
      setLookup({ status: 'error', data: null, message: error.response?.status === 404 ? (IS_DEMO ? 'This ID is outside the demo sample. Try one of the example IDs above.' : 'No member found with that ID.') : (IS_DEMO ? 'Unable to load the saved record. Reload this page to retry.' : 'Unable to retrieve this member. Check the API connection.') })
    }
  }
  return <section className="data-panel member-panel">
    <div className="panel-heading"><div><h2>Members explorer</h2><p>Look up a member record by ID</p></div><span className="table-label"><Table2 size={14} /> MEMBERS</span></div>
    <form className="member-search" onSubmit={search}><label htmlFor="member-id">Member ID</label><div className="search-field"><Search size={16} /><input id="member-id" inputMode="numeric" value={input} onChange={(event) => setInput(event.target.value)} placeholder="Enter a member ID" required disabled={lookup.status === 'loading'} /></div><button type="submit" className="primary-button" disabled={lookup.status === 'loading'}>{lookup.status === 'loading' ? 'Searching…' : 'Find member'}<ArrowUpRight size={15} /></button></form>
    {IS_DEMO && <div className="sample-id-hints"><span>Try a sample ID:</span>{exampleIds.map((id) => <button type="button" key={id} onClick={() => setInput(String(id))}>{id}</button>)}</div>}
    {lookup.status === 'idle' && <div className="member-empty"><span className="empty-icon"><Users size={25} /></span><h3>Explore your member data</h3><p>Enter an ID above to view the member’s demographics and health measures.</p></div>}
    {lookup.status === 'loading' && <ResourceState resource={lookup} />}
    {lookup.status === 'error' && <p className="lookup-error" role="alert">{lookup.message}</p>}
    {lookup.status === 'ready' && <div className="member-table-wrap"><table><thead><tr>{memberColumns.map(([key, label]) => <th key={key}>{label}</th>)}</tr></thead><tbody><tr>{memberColumns.map(([key]) => <td key={key}>{lookup.data[key] == null ? <span className="null-value">NULL</span> : typeof lookup.data[key] === 'boolean' ? (lookup.data[key] ? 'Yes' : 'No') : String(lookup.data[key])}</td>)}</tr></tbody></table></div>}
    <div className="panel-footer"><span><span className="tiny-dot" /> Individual record lookup</span><span>HealthPulse · Data Explorer</span></div>
  </section>
}

function DashboardContent({ revision }) {
  const [section, setSection] = useState('explorer')
  const [reportingDate, setReportingDate] = useState(() => new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Chicago', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date()))
  const summary = useResource(IS_DEMO ? '/api/explorer/overview' : `/api/explorer/overview?as_of=${reportingDate}`, revision)
  const about = useResource(IS_DEMO ? '/api/demo/about' : null, revision)
  const states = useResource('/api/stats/members-by-state', revision)
  const performance = useResource('/api/stats/query-performance', revision)
  const claims = useResource(section === 'claims' ? '/api/stats/claims-trend' : null, revision)
  const health = useResource(section === 'population' ? '/api/stats/population-health' : null, revision)
  const [equityPeriod, setEquityPeriod] = useState({ as_of: '2025-11-30', claims_start: '2024-11-01', claims_end: '2025-12-01' })
  const equity = useResource(section === 'sql' ? `/api/stats/premium-equity?${new URLSearchParams(equityPeriod)}` : null, revision)
  const resources = section === 'sql' ? [equity] : section === 'claims' ? [summary, states, claims] : section === 'population' ? [summary, health] : [summary, states]
  const status = resources.some((r) => r.status === 'error') ? 'Some data unavailable' : resources.some((r) => r.status === 'loading') ? 'Loading data' : IS_DEMO ? 'Saved demo' : 'Data loaded'
  const asOf = IS_DEMO ? summary.data?.as_of : reportingDate
  const exampleIds = about.data ? [about.data.sample.MEMBERS[0], about.data.sample.MEMBERS[41], about.data.sample.MEMBERS.at(-1)].filter(Boolean).map((member) => member.member_id) : []
  const populationMetrics = [
    { label: 'Total members', icon: Users, tone: 'amber', value: summary.data ? compact(summary.data.total_members) : null, detail: summary.data ? `${full(summary.data.total_members)} member records` : 'Member population', resource: summary },
    { label: 'Total claims value', icon: DollarSign, tone: 'orange', value: summary.data ? compact(summary.data.total_claims_value, true) : null, detail: summary.data ? `$${full(summary.data.total_claims_value)} in claims` : 'Sum of claim amounts', resource: summary },
    { label: 'Average heart rate', icon: Activity, tone: 'rose', value: summary.data?.average_heart_rate ?? null, suffix: 'bpm', detail: 'Across recorded member heart rates', resource: summary },
    { label: 'States represented', icon: MapPin, tone: 'mint', value: states.data ? states.data.filter((row) => row.state).length : null, detail: 'Distinct recorded state codes', resource: states },
  ]
  const tableCount = (name) => summary.data?.tables.find((table) => table.name === name)?.row_count ?? null
  const countMetric = (name, label, icon, tone) => ({ label, icon, tone, value: tableCount(name) == null ? null : compact(tableCount(name)), detail: IS_DEMO ? 'Full-dataset records' : 'Database records', resource: summary })
  const metrics = section === 'explorer' ? [
    populationMetrics[0],
    countMetric('CLAIMS', 'Claims', ClipboardList, 'orange'),
    countMetric('FACILITY', 'Facilities', Building2, 'mint'),
    countMetric('CONDITION', 'Conditions', Stethoscope, 'rose'),
    countMetric('INSURANCE', 'Insurers', Shield, 'neutral'),
    countMetric('PLAN', 'Plans', ClipboardList, 'neutral'),
    { label: 'Active enrollments', icon: Users, tone: 'mint', value: summary.data ? compact(summary.data.active_enrollments) : null, detail: `Calculated for ${asOf || 'reference date'}`, resource: summary },
    populationMetrics[1],
  ] : populationMetrics
  const headings = { explorer: ['Data Explorer', 'Browse demographics, coverage, and relational tables'], population: ['Population Health', 'Explore recorded health measures, sleep, exercise, and lifestyle'], claims: ['Claims Overview', 'Explore claim spending across time'], sql: ['Premium Equity & SQL', 'Explore full-data pricing comparisons and inspect the SQL behind them'] }
  return <div className="healthpulse">
    <header className="app-header"><a href="#" className="brand" onClick={(event) => { event.preventDefault(); setSection('explorer') }}><span className="brand-icon"><Heart size={25} /></span><span><strong>HealthPulse</strong><small>ANALYTICS PLATFORM</small></span></a>
      <nav aria-label="Dashboard sections">{[['explorer', Database, 'Data Explorer'], ['population', Heart, 'Population Health'], ['claims', TrendingUp, 'Claims Overview'], ['sql', Shield, 'Premium Equity & SQL']].map(([key, icon, label]) => {
        const Icon = icon
        return <button key={key} aria-current={section === key ? 'page' : undefined} className={section === key ? 'nav-item selected' : 'nav-item'} onClick={() => setSection(key)}><Icon size={16} /><span>{label}</span></button>
      })}</nav>
      <span className={`connection-badge ${resources.some((r) => r.status === 'error') ? 'unavailable' : ''}`} role="status"><span className="tiny-dot" />{status}</span>
    </header>
    <main className="dashboard-main">
      {IS_DEMO && <div className="demo-banner"><div><strong>{summary.data ? `Synthetic data for ${compact(summary.data.total_members)} members` : 'Synthetic data demo'}</strong><p>All analytical charts use full-source aggregates. The table browser contains a connected sample of 200 members and related records.</p></div><a href="https://github.com/emilyxue003/health_insurance_analytics" target="_blank" rel="noreferrer">View project code<ArrowUpRight size={15} /></a></div>}
      <div className="page-heading"><div><h1>{headings[section][0]}</h1><p>{headings[section][1]}</p></div>{!IS_DEMO && section === 'explorer' && <form className="reporting-date" onSubmit={(event) => { event.preventDefault(); setReportingDate(new FormData(event.currentTarget).get('as_of')) }}><label htmlFor="reporting-date">Age & active coverage as of</label><input id="reporting-date" name="as_of" type="date" defaultValue={reportingDate} required /><button type="submit">Apply date</button></form>}</div>
      {IS_DEMO && section !== 'sql' && <DemoDates resource={about} />}
      {section !== 'population' && section !== 'sql' && <section className={`metric-grid ${section === 'explorer' ? 'explorer-metrics' : ''}`} aria-label="Summary metrics">{metrics.map((metric) => {
        const { label, icon: Icon, tone, value, suffix, detail, resource } = metric
        return <article className="metric-card" key={label}><div><p className="metric-label">{label}</p><p className="metric-value">{value == null ? (resource.status === 'error' ? 'Unavailable' : resource.status === 'ready' ? 'No readings' : 'Loading…') : value}{value != null && suffix && <span className="metric-unit"> {suffix}</span>}</p><p className="metric-detail">{detail}</p></div><span className={`metric-icon ${tone}`}><Icon size={22} /></span></article>
      })}</section>}
      {section === 'sql' ? <SQLShowcase resource={equity} isDemo={IS_DEMO} period={equityPeriod} onPeriodChange={setEquityPeriod} /> : section === 'population' ? <PopulationHealth resource={health} /> : section === 'claims' ? <div className="charts-grid single-chart"><ClaimsChart resource={claims} /></div> : <div className="charts-grid demographic-grid"><AgeChart resource={summary} /><SexChart resource={summary} /><CoverageChart resource={summary} /><StateChart resource={states} /></div>}
      {section === 'explorer' && <><TableBrowser tables={summary.data?.tables || []} status={summary.status} revision={revision} /><details className="member-lookup"><summary>Find an individual member by ID</summary><MemberExplorer exampleIds={exampleIds} /></details></>}
      {(section === 'explorer' || section === 'sql') && <QueryPerformance resource={performance} isDemo={IS_DEMO} />}
      {IS_DEMO && <DemoAbout resource={about} />}
      <footer className="dashboard-footer"><span>HealthPulse Analytics <span className="footer-separator">/</span>{IS_DEMO ? 'Portfolio demo' : 'Local workspace'}</span><span>{IS_DEMO ? 'Synthetic data · Saved results · No live database connection' : 'Counts include all records · Summaries cached up to 5 minutes'}</span></footer>
    </main>
  </div>
}

export default function Dashboard() {
  const [revision, setRevision] = useState(0)
  return <><DashboardContent key={IS_DEMO ? revision : 'live'} revision={revision} /><button className="refresh-button" aria-label={IS_DEMO ? 'Reset demo view' : 'Refresh dashboard data'} onClick={() => setRevision((value) => value + 1)}><RefreshCw size={15} />{IS_DEMO ? 'Reset view' : 'Refresh data'}</button></>
}
