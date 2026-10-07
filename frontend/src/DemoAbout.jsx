import DatabaseSchema from './DatabaseSchema.jsx'

const monthlySQL = `SELECT DATE_FORMAT(date, '%Y-%m') AS month,
       SUM(amount) AS total
FROM CLAIMS
GROUP BY month
ORDER BY month;`

const ageSQL = `SELECT COUNT(*) AS members_18_to_34
FROM MEMBERS
WHERE DOB <= :as_of
  AND TIMESTAMPDIFF(YEAR, DOB, :as_of) >= 18
  AND TIMESTAMPDIFF(YEAR, DOB, :as_of) < 35;`

export default function DemoAbout({ resource }) {
  const snapshot = resource.data
  const records = snapshot?.overview.tables.reduce((sum, table) => sum + table.row_count, 0)
  return <details className="data-panel project-about" id="about-project">
    <summary>About this project <span>Architecture, schema & SQL</span></summary>
    {resource.status !== 'ready' ? <p className="panel-state">{resource.status === 'error' ? 'Project details unavailable. Reload this page to retry.' : 'Loading project details…'}</p> : <div className="about-content">
      <p className="project-intro">HealthPulse brings together synthetic data for {new Intl.NumberFormat('en-US', { notation: 'compact' }).format(snapshot.overview.total_members)} members: {new Intl.NumberFormat('en-US').format(records)} records across eight MySQL tables covering demographics, coverage, and claim spending.</p>
      <div className="architecture-flow" aria-label="Local application architecture"><span>React interface</span><b aria-hidden="true">→</b><span>FastAPI endpoints</span><b aria-hidden="true">→</b><span>MySQL database</span></div>
      <div className="about-grid"><div><h3>The full application</h3><p>SQL aggregates power population charts, claims trends, and premium analyses. The API caches summary results for five minutes in each running process and browses tables using the complete primary key, including composite keys.</p></div><div><h3>How this demo works</h3><p>The published site reads saved full-source aggregates and a connected sample in your browser. Premium Equity &amp; SQL uses full-source results; only record browsing is limited to 200 members. The regular dashboard runs those same queries against MySQL.</p></div></div>
      <p className="sample-method"><strong>Sample method:</strong> {snapshot.metadata.sample_method} Age and active coverage use the calculation date shown above. Claim and coverage charts include all recorded periods. Population Health source: {snapshot.population_health?.source || 'Unavailable'}.{snapshot.population_health?.verified_sample_members && ` The source member count and health measures for ${snapshot.population_health.verified_sample_members} exported members were reconciled against this database export.`}</p>
      <h3>Database schema</h3><DatabaseSchema schema={snapshot.schema} counts={Object.fromEntries(snapshot.overview.tables.map((table) => [table.name, table.row_count]))} sample={snapshot.sample} />
      <div className="about-grid sql-examples"><div><h3>Monthly claims aggregation</h3><pre><code>{monthlySQL}</code></pre></div><div><h3>Age at a reporting date</h3><pre><code>{ageSQL}</code></pre></div></div>
      <a className="project-link" href={snapshot.metadata.source_repository} target="_blank" rel="noreferrer">View the project repository ↗</a>
    </div>}
  </details>
}
