export function describeRequestError(error, { premium = false, isDemo = false } = {}) {
  if (isDemo) return 'Unable to load the demo snapshot. Reload this page to retry.'
  if (error.code === 'ECONNABORTED' || error.code === 'ETIMEDOUT') {
    return 'The request timed out after two minutes. The backend may still be calculating; check its Terminal before retrying.'
  }
  const status = error.response?.status
  if (!status) return 'Could not reach the backend. Check that the server is running and leave its Terminal open.'
  if (premium && (status === 400 || status === 422)) {
    return 'The selected period is invalid. Claims end must follow the start and be no later than the day after the coverage cutoff. Check that all three dates are valid.'
  }
  if (status === 503) return 'The backend could not retrieve the results. Check its Terminal for the database or service error.'
  if (status >= 500) return 'The backend encountered an error while preparing the results. Check its Terminal for the error.'
  return 'The request could not be completed. Check the backend Terminal for details.'
}
