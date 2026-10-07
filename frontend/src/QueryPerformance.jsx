import { RESULT_EXPORT_URL } from './api.js'

const labels = {
  member_demographics: 'Member demographics', coverage_summary: 'Coverage summary',
  population_health: 'Population health', monthly_claims: 'Monthly claims',
  members_by_state: 'Members by state', member_lookup: 'Member lookup by ID',
  members_first_page: 'First member table page', regional_premiums: 'Regional premiums',
  housing_premiums: 'Housing insecurity & premiums', conditions_costs: 'Conditions & costs',
}
const duration = (ms) => ms < 1000 ? `${ms.toFixed(2)} ms` : `${(ms / 1000).toFixed(2)} s`

export default function QueryPerformance({ resource, isDemo }) {
  if (resource.status !== 'ready') return <details className="data-panel query-performance"><summary>Measured MySQL performance</summary><p>{resource.status === 'error' ? 'The saved measurement is unavailable.' : 'Loading saved measurement…'}</p></details>
  const report = resource.data
  const comparison = report.optimization
  const regional = comparison?.results.find((row) => row.candidate_name === 'regional_grouped')
  const covering = report.covering_trial
  const activation = report.covering_activation
  const candidateLabels = { regional_grouped: 'Group regional records before window calculations', conditions_primary_diagnoses: 'Change diagnosis scan', conditions_primary_scans: 'Change diagnosis & claims scans' }
  const count = Object.values(report.table_counts).reduce((sum, n) => sum + n, 0)
  const date = new Intl.DateTimeFormat('en-US', { timeZone: 'America/Chicago', dateStyle: 'medium' }).format(new Date(report.measured_at))
  return <details className="data-panel query-performance">
    <summary>Measured MySQL performance <span>Full dataset · {date}</span></summary>
    <div className="performance-content">
      <p>MySQL {report.mysql_version} · {report.connection === 'local' ? 'Local database' : 'Remote database'} · {new Intl.NumberFormat('en-US').format(count)} records across eight tables.</p>
      {comparison && <section className="performance-comparison" aria-label="Measured query optimization">
        <h3>Regional query: {duration(regional.baseline.median_repeated_ms)} → {duration(regional.candidate.median_repeated_ms)}</h3>
        <p>{Math.abs(regional.change_pct).toFixed(1)}% less query time · {regional.speedup.toFixed(2)}× speedup · Identical full-data results. {report.adopted_candidates?.includes('regional_grouped') ? 'Applied to the regular dashboard and downloadable SQL.' : 'Candidate measured; not applied.'}</p>
        <p>Grouping reduces window-calculation inputs from about 3.15 million enrollment records to 8,000 coverage cells in the measured plan. Three repeated paired reads per candidate; execution order alternates. Local MySQL, fixed saved period.</p>
        <div className="small-table-wrap"><table><caption>Query rewrites tested before the covering index</caption><thead><tr><th>Change</th><th>Before</th><th>After</th><th>Decision</th></tr></thead><tbody>{comparison.results.map((row) => <tr key={row.candidate_name}><td>{candidateLabels[row.candidate_name]}</td><td>{duration(row.baseline.median_repeated_ms)}</td><td>{duration(row.candidate.median_repeated_ms)}</td><td>{report.adopted_candidates?.includes(row.candidate_name) ? 'Applied' : row.change_pct > 0 ? 'Not applied: slower' : 'Not applied: within trial variation'}</td></tr>)}</tbody></table></div>
      </section>}
      {covering && <section className="performance-comparison" aria-label="Conditions query covering index">
        <h3>Conditions query: {duration(covering.baseline.median_repeated_ms)} → {duration(covering.candidate.median_repeated_ms)}</h3>
        <p>{Math.abs(covering.change_pct).toFixed(1)}% less query time · {covering.speedup.toFixed(2)}× speedup · Identical full-data results. Three paired reads comparing the existing claims index with a covering index on member, date, and amount.</p>
        {activation ? <p><strong>Applied and verified: {duration(activation.median_repeated_ms)}</strong> median for the normal dashboard query. MySQL chose the visible covering index automatically. This later check is separate from the paired comparison above.</p> : <p>Candidate measured; activation has not been verified.</p>}
        <p>The index supplies claim amounts without fetching each claims table row. It adds storage and index maintenance work; write performance was not measured.</p>
      </section>}
      <p>Original baseline before either improvement: record access took about 1 ms; premium analyses took 16–36 seconds. All timings are saved database measurements for the fixed period, independent of dashboard filters.</p>
      <div className="small-table-wrap"><table><caption>Original baseline: median of {report.repeats} direct database reads per query</caption><thead><tr><th>Query</th><th>First read</th><th>Median repeat</th><th>Repeat range</th><th>Output rows</th></tr></thead><tbody>{report.results.map((row) => <tr key={row.query}><td>{labels[row.query]}</td><td>{duration(row.first_read_ms)}</td><td>{duration(row.median_repeated_ms)}</td><td>{duration(row.min_repeated_ms)} to {duration(row.max_repeated_ms)}</td><td>{row.returned_rows}</td></tr>)}</tbody></table></div>
      <p className="performance-method">Includes fetching results. Excludes connection setup, application caching, HTTP, and browser rendering. Database buffers were not flushed; this is not a cold-disk test or a Cloud SQL benchmark. One client; background load was not controlled. The table page fetches 25 records plus one lookahead.</p>
      <a href={isDemo ? `${import.meta.env.BASE_URL}benchmarks/mysql-performance.json` : RESULT_EXPORT_URL.replace('/premium-equity/export', '/query-performance')} download="healthpulse-mysql-performance.json">Download timings, SQL & query plans</a>
      <details className="performance-plans"><summary>Inspect measured query plans</summary>{report.results.map((row) => <details key={row.query}><summary>{labels[row.query]}</summary><pre>{row.plan}</pre></details>)}</details>
      {comparison && <details className="performance-plans"><summary>Inspect before-and-after query plans</summary>{comparison.results.map((row) => <details key={row.candidate_name}><summary>{candidateLabels[row.candidate_name]}</summary><h4>Before</h4><pre>{row.baseline.plan}</pre><h4>After</h4><pre>{row.candidate.plan}</pre></details>)}</details>}
      {covering && <details className="performance-plans"><summary>Inspect covering index query plans</summary><h4>Existing claims index</h4><pre>{covering.baseline.plan}</pre><h4>Covering claims index trial</h4><pre>{covering.candidate.plan}</pre>{activation && <><h4>Normal dashboard query after activation</h4><pre>{activation.plan}</pre></>}</details>}
    </div>
  </details>
}
