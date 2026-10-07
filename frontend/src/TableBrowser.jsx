import { useEffect, useState } from 'react'
import { ChevronLeft, ChevronRight, Table2 } from 'lucide-react'
import { IS_DEMO, requestData } from './api.js'

const exact = (value) => new Intl.NumberFormat('en-US').format(value)

function TablePage({ name, limit, rowCount }) {
  const [history, setHistory] = useState([null])
  const [page, setPage] = useState(0)
  const [resource, setResource] = useState({ path: null, status: 'loading', data: null })
  const params = new URLSearchParams({ limit: String(limit) })
  if (history[page]) params.set('cursor', history[page])
  const path = `/api/tables/${name}?${params}`
  const current = resource.path === path ? resource : { status: 'loading', data: null }

  useEffect(() => {
    const controller = new AbortController()
    requestData(path, { signal: controller.signal, timeout: 20000 })
      .then((data) => setResource({ path, status: 'ready', data }))
      .catch(() => { if (!controller.signal.aborted) setResource({ path, status: 'error', data: null }) })
    return () => controller.abort()
  }, [path])

  function next() {
    setHistory([...history.slice(0, page + 1), current.data.next_cursor])
    setPage(page + 1)
  }

  return <>
    {current.status === 'loading' && <div className="panel-state" role="status"><span className="loading-dot" />Loading table records…</div>}
    {current.status === 'error' && <div className="panel-state error-message" role="alert">Unable to load this table. Refresh the dashboard to retry.</div>}
    {current.status === 'ready' && <div className="member-table-wrap browsed-table" tabIndex="0" role="region" aria-label={`${name} records`}><table><thead><tr>{current.data.columns.map((column) => <th key={column}>{column.replaceAll('_', ' ')}</th>)}</tr></thead><tbody>{current.data.rows.map((row, index) => <tr key={index}>{current.data.columns.map((column) => <td key={column}>{row[column] == null ? <span className="null-value">NULL</span> : typeof row[column] === 'object' ? JSON.stringify(row[column]) : String(row[column])}</td>)}</tr>)}</tbody></table>{!current.data.rows.length && <p className="empty-table">No records in this table.</p>}</div>}
    <div className="table-pagination"><span>{current.status === 'ready' ? (current.data.rows.length ? `Rows ${exact(page * limit + 1)}–${exact(page * limit + current.data.rows.length)}` : '0 rows') : current.status === 'error' ? 'Records unavailable' : 'Loading records'}{rowCount != null && ` · ${exact(rowCount)} ${IS_DEMO ? 'sample records' : 'total'}`}</span><div><button onClick={() => setPage(page - 1)} disabled={page === 0 || current.status === 'loading'} aria-label="Previous table page"><ChevronLeft size={14} />Previous</button><span>Page {page + 1}</span><button onClick={next} disabled={current.status !== 'ready' || !current.data?.has_more} aria-label="Next table page">Next<ChevronRight size={14} /></button></div></div>
  </>
}

export default function TableBrowser({ tables, status, revision }) {
  const [name, setName] = useState('MEMBERS')
  const [limit, setLimit] = useState(25)
  const selected = tables.find((table) => table.name === name)
  const names = ['MEMBERS', 'CLAIMS', 'ENROLLMENT', 'FACILITY', 'CONDITION', 'INSURANCE', 'PLAN', 'MEMBER_CONDITION']
  return <div className="explorer-grid table-explorer">
    <aside className="data-panel source-panel"><div className="panel-heading"><div><h2><Table2 size={17} /> Tables</h2>{IS_DEMO && <p>Counts below refer to the full database</p>}</div></div><nav className="table-list" aria-label="Database tables">{names.map((table) => <button key={table} className={name === table ? 'table-choice active' : 'table-choice'} aria-pressed={name === table} onClick={() => setName(table)}><span>{table}</span><span>{tables.find((item) => item.name === table)?.row_count != null ? exact(tables.find((item) => item.name === table).row_count) : status === 'error' ? 'Unavailable' : 'Loading…'}</span></button>)}</nav></aside>
    <section className="data-panel"><div className="panel-heading"><div><h2>{name} table</h2><p>{selected ? (IS_DEMO ? `${exact(selected.sample_count)} sample records · ${exact(selected.row_count)} in full database` : `${exact(selected.row_count)} records · Ordered by primary key`) : 'Read-only records'}</p></div><div className="page-size"><label htmlFor="table-page-size">Rows per page</label><select id="table-page-size" value={limit} onChange={(event) => setLimit(Number(event.target.value))}>{[25, 50, 100].map((size) => <option key={size} value={size}>{size}</option>)}</select></div></div><TablePage key={`${name}-${limit}-${revision}`} name={name} limit={limit} rowCount={IS_DEMO ? selected?.sample_count : selected?.row_count} /></section>
  </div>
}
