const exact = (value) => new Intl.NumberFormat('en-US').format(value)
const compact = (value) => new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(value)

function Distribution({ title, subtitle, rows, total, color }) {
  const maximum = Math.max(...rows.map((row) => row.count), 1)
  return <section className="data-panel health-distribution"><div className="panel-heading"><div><h2>{title}</h2><p>{subtitle}</p></div></div>
    <div className="health-bars" role="img" aria-label={rows.map((row) => `${row.label}: ${exact(row.count)} members`).join(', ')}>{rows.map((row) => <div className="health-bar-row" key={row.label}><span>{row.label}</span><div className="bar-track"><div className="bar-fill" style={{ width: `${row.count / maximum * 100}%`, background: row.label === 'Missing / invalid' ? '#b7afa4' : color }} /></div><span title={`${exact(row.count)} members`}>{compact(row.count)} <small>{total ? (row.count / total * 100).toFixed(1) : '0'}%</small></span></div>)}</div>
  </section>
}

export default function PopulationHealth({ resource }) {
  if (resource.status !== 'ready') return <section className="data-panel"><p className="panel-state" role={resource.status === 'error' ? 'alert' : 'status'}>{resource.status === 'error' ? 'Health measures unavailable. Reload this page to retry.' : 'Loading recorded health measures…'}</p></section>
  const profile = resource.data
  const smoker = profile.behaviors.find((row) => row.key === 'smoker')
  const knownSmoker = smoker.yes + smoker.no
  const metrics = [
    ['Average heart rate', profile.averages.heart_rate.value, 'bpm', `${exact(profile.averages.heart_rate.count)} recorded values`],
    ['Recorded smokers', knownSmoker ? (smoker.yes / knownSmoker * 100).toFixed(1) : null, '%', `${exact(smoker.yes)} of ${exact(knownSmoker)} known statuses`],
    ['Average sleep', profile.averages.sleep.value, 'hours / night', `${exact(profile.averages.sleep.count)} recorded values`],
    ['Average exercise', profile.averages.exercise.value, 'min / week', `${exact(profile.averages.exercise.count)} recorded values`],
  ]
  return <>
    <div className="health-scope"><strong>Synthetic data for {compact(profile.total_members)} members</strong><span>Source: {profile.source}</span></div>
    <section className="metric-grid" aria-label="Recorded health metrics">{metrics.map(([label, value, unit, detail]) => <article className="metric-card" key={label}><div><p className="metric-label">{label}</p><p className="metric-value">{value ?? 'No readings'}{value != null && <span className="metric-unit">{unit}</span>}</p><p className="metric-detail">{detail}</p></div></article>)}</section>
    <div className="charts-grid demographic-grid">
      <Distribution title="Recorded heart rate" subtitle="Beats per minute · Member counts" rows={profile.distributions.heart_rate} total={profile.total_members} color="#c66200" />
      <Distribution title="Recorded sleep" subtitle="Hours per night · Member counts" rows={profile.distributions.sleep} total={profile.total_members} color="#0083ad" />
      <Distribution title="Weekly exercise" subtitle="Minutes per week · Member counts" rows={profile.distributions.exercise} total={profile.total_members} color="#048743" />
      <section className="data-panel health-distribution"><div className="panel-heading"><div><h2>Smoking & drinking</h2><p>Recorded statuses · All member records</p></div></div><div className="behavior-chart">{profile.behaviors.map((row) => <div className="behavior-row" key={row.key}><h3>{row.label}</h3><div className="behavior-track" role="img" aria-label={`${row.label}: yes ${exact(row.yes)}, no ${exact(row.no)}, unknown ${exact(row.unknown)}`}>{[['yes', '#c66200'], ['no', '#b8dcd0'], ['unknown', '#b7afa4']].map(([key, color]) => <span key={key} style={{ width: `${profile.total_members ? row[key] / profile.total_members * 100 : 0}%`, background: color }} />)}</div><div className="behavior-legend"><span>Yes {exact(row.yes)}</span><span>No {exact(row.no)}</span><span>Unknown {exact(row.unknown)}</span></div></div>)}</div></section>
    </div>
    <p className="health-method">Averages exclude missing or invalid values. Smoking percentage uses known statuses; chart percentages use all members. These recorded health fields have no measurement dates.</p>
  </>
}
