import assert from 'node:assert/strict'
import { describeRequestError } from '../src/requestErrors.js'

for (const code of ['ECONNABORTED', 'ETIMEDOUT']) {
  const message = describeRequestError({ code }, { premium: true })
  assert.match(message, /timed out/)
  assert.doesNotMatch(message, /period is invalid/)
}
for (const status of [400, 422]) {
  assert.match(describeRequestError({ response: { status } }, { premium: true }), /period is invalid/)
}
for (const status of [500, 503]) {
  const message = describeRequestError({ response: { status, data: { detail: 'private SQL and credentials' } } }, { premium: true })
  assert.match(message, /backend|Terminal/)
  assert.doesNotMatch(message, /period is invalid|private SQL|credentials/)
}
assert.match(describeRequestError({ code: 'ERR_NETWORK' }), /Could not reach/)
assert.match(describeRequestError({ response: { status: 503 } }, { isDemo: true }), /demo snapshot/)
console.log('Request errors distinguish timeouts, invalid periods, network failures, and backend errors without exposing raw details.')
