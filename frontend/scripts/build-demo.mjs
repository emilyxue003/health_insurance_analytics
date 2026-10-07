import { build } from 'vite'
import { readFile, mkdir, writeFile } from 'node:fs/promises'

const snapshot = JSON.parse(await readFile(new URL('../public/demo/snapshot.json', import.meta.url), 'utf8'))
const data = snapshot.sql_showcase
if (data?.scope !== 'full') throw new Error('Full-data premium results are required for publication.')
const directory = new URL('../public/sql/results/', import.meta.url)
await mkdir(directory, { recursive: true })
for (const selected of data.cases) {
  for (const minimum of selected.id === 'regional_premiums' ? [0, 10000, 50000, 100000, 1000000] : [0]) {
    const rows = selected.id === 'regional_premiums' ? selected.rows.filter((row) => row.enrollments >= minimum) : selected.rows
    const payload = { question: selected.question, source: data.source, scope: data.scope, total_members: data.total_members,
      parameters: data.parameters, grain: selected.grain, execution_engine: data.engine, mysql_verified: data.mysql_verified,
      mysql_verification: data.mysql_verification || null,
      generated_at: data.generated_at, state_minimum_count: selected.id === 'regional_premiums' ? minimum : null,
      sql_sha256: selected.sha256, methods_document: 'https://healthpulse-analytics.netlify.app/sql/README.md',
      caveat: 'Synthetic descriptive comparison. Premium billing frequency is undocumented. This is not an income, affordability, causal fairness, or discrimination estimate.', rows }
    await writeFile(new URL(`${selected.id}-${minimum}.json`, directory), JSON.stringify(payload, null, 2))
  }
}

await build({ mode: 'demo' })
