const monthFormat = new Intl.DateTimeFormat('en-US', { month: 'short', year: 'numeric', timeZone: 'UTC' })
const dayFormat = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' })
const exportFormat = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'America/Chicago' })

export function claimsPeriod(rows = []) {
  const months = rows.map((row) => row.month).filter((month) => /^\d{4}-(0[1-9]|1[0-2])$/.test(month)).sort()
  if (!months.length) return 'No dated claims'
  const first = monthFormat.format(new Date(`${months[0]}-01T00:00:00Z`))
  const last = monthFormat.format(new Date(`${months.at(-1)}-01T00:00:00Z`))
  return first === last ? first : `${first}–${last}`
}

export function demoDates(snapshot) {
  const date = snapshot?.overview.as_of
  const exported = snapshot?.metadata.exported_at
  return {
    claims: claimsPeriod(snapshot?.claims_trend),
    calculation: date ? dayFormat.format(new Date(`${date}T00:00:00Z`)) : 'Unavailable',
    exported: exported ? exportFormat.format(new Date(exported)) : 'Unavailable',
  }
}
