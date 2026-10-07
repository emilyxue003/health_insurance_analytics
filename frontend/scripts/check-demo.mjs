import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import { resolveDemo } from '../src/demo.js'
import { demoDates } from '../src/demoDates.js'

const snapshot = JSON.parse(await readFile(new URL('../public/demo/snapshot.json', import.meta.url), 'utf8'))
assert.equal(snapshot.metadata.synthetic, true)
const overview = resolveDemo(snapshot, '/api/explorer/overview')
assert.equal(snapshot.states.reduce((sum, row) => sum + row.count, 0), overview.total_members)
for (const key of ['age_distribution', 'sex_distribution']) {
  assert.equal(overview[key].reduce((sum, row) => sum + row.count, 0), overview.total_members)
}
assert.ok(Math.abs(snapshot.claims_trend.reduce((sum, row) => sum + row.total, 0) - overview.total_claims_value) < 0.01)
assert.equal(overview.coverage_tiers.reduce((sum, row) => sum + row.count, 0), overview.tables.find((table) => table.name === 'ENROLLMENT').row_count)
const dates = demoDates(snapshot)
assert.notEqual(dates.claims, 'No dated claims')
assert.deepEqual(demoDates({ overview: { as_of: '2026-10-05' }, metadata: { exported_at: '2026-10-06T02:00:00Z' }, claims_trend: [{ month: '2025-01' }, { month: '2024-12' }] }), { claims: 'Dec 2024–Jan 2025', calculation: 'Oct 5, 2026', exported: 'Oct 5, 2026' })
const health = resolveDemo(snapshot, '/api/stats/population-health')
assert.equal(health.total_members, overview.total_members)
for (const rows of Object.values(health.distributions)) assert.equal(rows.reduce((sum, row) => sum + row.count, 0), health.total_members)
for (const average of Object.values(health.averages)) assert.equal(average.count + average.missing, health.total_members)
for (const row of health.behaviors) assert.equal(row.yes + row.no + row.unknown, health.total_members)
const sqlShowcase = resolveDemo(snapshot, '/api/stats/premium-equity').sql_showcase
const performance = resolveDemo(snapshot, '/api/stats/query-performance')
assert.equal(performance.scope, 'full')
assert.equal(performance.results.length, 10)
assert.deepEqual(performance.table_counts, Object.fromEntries(overview.tables.map((row) => [row.name, row.row_count])))
assert.deepEqual(performance, JSON.parse(await readFile(new URL('../public/benchmarks/mysql-performance.json', import.meta.url), 'utf8')))
assert.deepEqual(performance.adopted_candidates, ['regional_grouped'])
assert.deepEqual(performance.optimization, JSON.parse(await readFile(new URL('../public/benchmarks/mysql-optimization.json', import.meta.url), 'utf8')))
for (const row of performance.optimization.results) {
  assert.equal(row.results_equal, true)
  for (const side of [row.baseline, row.candidate]) {
    assert.equal(createHash('sha256').update(side.sql).digest('hex'), side.sql_sha256)
    const sorted = [...side.repeated_uncached_ms].sort((a, b) => a - b)
    assert.equal(sorted[Math.floor(sorted.length / 2)], side.median_repeated_ms)
  }
}
const regionalComparison = performance.optimization.results.find((row) => row.candidate_name === 'regional_grouped')
assert.equal(sqlShowcase.cases.find((row) => row.id === 'regional_premiums').sql, regionalComparison.candidate.sql)
assert.deepEqual(performance.covering_trial, JSON.parse(await readFile(new URL('../public/benchmarks/mysql-covering-index.json', import.meta.url), 'utf8')))
assert.deepEqual(performance.covering_activation, JSON.parse(await readFile(new URL('../public/benchmarks/mysql-covering-index-applied.json', import.meta.url), 'utf8')))
const activation = performance.covering_activation
assert.equal(activation.applied, true)
assert.deepEqual(activation.table_counts, performance.table_counts)
assert.deepEqual(activation.parameters, sqlShowcase.parameters)
assert.equal(activation.sql, sqlShowcase.cases.find((row) => row.id === 'conditions_costs').sql)
assert.equal(createHash('sha256').update(activation.sql).digest('hex'), activation.sql_sha256)
assert.equal(activation.result_sha256, performance.results.find((row) => row.query === 'conditions_costs').result_sha256)
assert.ok(activation.plan.includes(`Covering index scan on CLAIMS using ${activation.index_name}`))
assert.equal([...activation.repeated_uncached_ms].sort((a, b) => a - b)[1], activation.median_repeated_ms)
assert.equal(sqlShowcase.mysql_verification.queries.conditions_costs.report, 'benchmarks/mysql-covering-index-applied.json')
for (const row of performance.results) {
  assert.equal(createHash('sha256').update(row.sql).digest('hex'), row.sql_sha256)
  const sorted = [...row.repeated_uncached_ms].sort((a, b) => a - b)
  assert.ok(Math.abs(sorted[Math.floor(sorted.length / 2)] - row.median_repeated_ms) < 0.002)
}
assert.equal(sqlShowcase.mysql_verified, true)
assert.equal(sqlShowcase.scope, 'full')
assert.equal(sqlShowcase.total_members, overview.total_members)
assert.equal(typeof sqlShowcase.mysql_verified, 'boolean')
for (const [table, count] of Object.entries(sqlShowcase.table_counts)) assert.equal(count, overview.tables.find((row) => row.name === table).row_count)
for (const item of sqlShowcase.cases) {
  const sql = await readFile(new URL(`../public/sql/${item.id}.sql`, import.meta.url), 'utf8')
  assert.equal(sql, item.sql)
  assert.equal(createHash('sha256').update(sql).digest('hex'), item.sha256)
}
const conditionRows = sqlShowcase.cases.find((item) => item.id === 'conditions_costs').rows
assert.equal(conditionRows.reduce((sum, row) => sum + row.members, 0), sqlShowcase.eligible_members)
assert.ok(conditionRows.every((row) => row.members_with_claims <= row.members))

for (const table of snapshot.schema) {
  for (const size of [25, 50, 100]) {
    const rows = []
    let cursor = null
    do {
      const params = new URLSearchParams({ limit: String(size) })
      if (cursor) params.set('cursor', cursor)
      const page = resolveDemo(snapshot, `/api/tables/${table.name}?${params}`)
      rows.push(...page.rows)
      assert.equal(page.has_more, page.next_cursor !== null)
      cursor = page.next_cursor
    } while (cursor)
    assert.deepEqual(rows, snapshot.sample[table.name])
    assert.equal(new Set(rows.map((row) => JSON.stringify(table.primary_key.map((key) => row[key])))).size, rows.length)
  }
  for (const key of table.foreign_keys) {
    const ids = new Set(snapshot.sample[key.table].map((row) => row[key.target_column]))
    assert.ok(snapshot.sample[table.name].every((row) => row[key.column] == null || ids.has(row[key.column])))
  }
}
for (const member of snapshot.sample.MEMBERS) assert.deepEqual(resolveDemo(snapshot, `/members/${member.member_id}`), member)
for (const path of ['/members/999999999', '/api/tables/SECRET', '/api/tables/MEMBERS?cursor=CLAIMS:25', '/api/tables/MEMBERS?cursor=garbage', '/api/tables/MEMBERS?limit=101', '/api/explorer/overview?as_of=2000-01-01', '/api/stats/premium-equity?as_of=2000-01-01']) {
  assert.throws(() => resolveDemo(snapshot, path), (error) => error.response.status >= 400)
}
console.log('Demo validated: full-dataset totals, all sample relationships, 24 complete pagination walks, member lookups, and invalid requests.')
