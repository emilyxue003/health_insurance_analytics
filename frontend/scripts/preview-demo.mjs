import { preview } from 'vite'

const server = await preview({ preview: { host: '127.0.0.1', port: 5174, strictPort: true } })
server.printUrls()
