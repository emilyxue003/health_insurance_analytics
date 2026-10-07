let snapshotPromise

export function loadSnapshot() {
  if (!snapshotPromise) {
    snapshotPromise = fetch(`${import.meta.env.BASE_URL}demo/snapshot.json`)
      .then((response) => {
        if (!response.ok) throw new Error('Demo snapshot unavailable.')
        return response.json()
      })
      .catch((error) => { snapshotPromise = null; throw error })
  }
  return snapshotPromise
}

function failure(status, message) {
  const error = new Error(message)
  error.response = { status }
  return error
}

export function resolveDemo(snapshot, path) {
  const url = new URL(path, 'https://demo.local')
  if (url.pathname === '/api/demo/about') return snapshot
  if (url.pathname === '/api/stats/query-performance') {
    if (!snapshot.performance) throw failure(503, 'Saved MySQL measurement unavailable.')
    return snapshot.performance
  }
  if (url.pathname === '/api/stats/premium-equity') {
    if (!snapshot.sql_showcase || snapshot.sql_showcase.scope !== 'full') throw failure(503, 'Full-data premium results are unavailable.')
    for (const [key, value] of url.searchParams) {
      if (String(snapshot.sql_showcase.parameters[key]) !== value) throw failure(400, 'This period is not included in the saved results.')
    }
    return { sql_showcase: snapshot.sql_showcase, schema: snapshot.schema }
  }
  if (url.pathname === '/api/explorer/overview') {
    const date = url.searchParams.get('as_of')
    if (date && date !== snapshot.metadata.as_of) throw failure(400, 'This date is not included in the demo snapshot.')
    return {
      ...snapshot.overview,
      tables: snapshot.overview.tables.map((table) => ({ ...table, sample_count: snapshot.sample[table.name].length })),
    }
  }
  if (url.pathname === '/api/stats/members-by-state') return snapshot.states
  if (url.pathname === '/api/stats/claims-trend') return snapshot.claims_trend
  if (url.pathname === '/api/stats/population-health') {
    if (!snapshot.population_health) throw failure(503, 'Health measures are not included in this export.')
    return snapshot.population_health
  }
  if (url.pathname.startsWith('/members/')) {
    const id = Number(url.pathname.slice('/members/'.length))
    const row = snapshot.sample.MEMBERS.find((member) => member.member_id === id)
    if (!row) throw failure(404, 'This member is not included in the sample.')
    return row
  }
  if (url.pathname.startsWith('/api/tables/')) {
    const name = url.pathname.slice('/api/tables/'.length)
    const table = snapshot.overview.tables.find((item) => item.name === name)
    if (!table) throw failure(404, 'Unknown table.')
    const limit = Number(url.searchParams.get('limit') || 25)
    if (!Number.isInteger(limit) || limit < 1 || limit > 100) throw failure(400, 'Invalid page size.')
    const cursor = url.searchParams.get('cursor')
    const match = cursor?.match(/^([A-Z_]+):(\d+)$/)
    if (cursor && (!match || match[1] !== name)) throw failure(400, 'Invalid sample cursor.')
    const start = match ? Number(match[2]) : 0
    const records = snapshot.sample[name]
    if (!Number.isSafeInteger(start) || start > records.length) throw failure(400, 'Invalid sample position.')
    const rows = records.slice(start, start + limit)
    const hasMore = start + rows.length < records.length
    return { table: name, columns: table.columns, rows, next_cursor: hasMore ? `${name}:${start + rows.length}` : null, has_more: hasMore }
  }
  throw failure(404, 'This operation is not included in the demo.')
}

export async function demoRequest(path, signal) {
  signal?.throwIfAborted()
  const snapshot = await loadSnapshot()
  signal?.throwIfAborted()
  return resolveDemo(snapshot, path)
}
