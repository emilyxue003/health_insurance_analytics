import { demoDates } from './demoDates.js'

export default function DemoDates({ resource }) {
  const dates = resource.data ? demoDates(resource.data) : null
  const fallback = resource.status === 'error' ? 'Unavailable' : 'Loading…'
  return <section className="demo-date-panel" aria-label="Demo data dates">
    <dl><div><dt>Claims period</dt><dd>{dates?.claims || fallback}</dd></div><div><dt>Age & active coverage calculated for</dt><dd>{dates?.calculation || fallback}</dd></div><div><dt>Demo exported</dt><dd>{dates?.exported || fallback}</dd></div></dl>
    <p>Calculation and export dates do not indicate newer source records.</p>
  </section>
}
