export const IS_DEMO = import.meta.env.MODE === 'demo' || (
  import.meta.env.MODE === 'development' && new URLSearchParams(window.location.search).get('demo') === '1'
)
export const RESULT_EXPORT_URL = IS_DEMO ? null : `${import.meta.env.VITE_API_URL || 'http://127.0.0.1:8001'}/api/stats/premium-equity/export`

export const requestData = IS_DEMO
  ? async (path, options = {}) => {
    const { demoRequest } = await import('./demo.js')
    return demoRequest(path, options.signal)
  }
  : async (path, options = {}) => {
    const { default: axios } = await import('axios')
    const api = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8001'
    const { data } = await axios.get(`${api}${path}`, options)
    return data
  }
