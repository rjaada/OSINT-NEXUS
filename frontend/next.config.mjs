import path from "path"
import { fileURLToPath } from "url"

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  experimental: { proxyTimeout: 180000 }, // Allow local inference to finish through the API proxy.
  turbopack: {
    root: __dirname,
  },
  images: {
    unoptimized: true,
  },
  async rewrites() {
    const backend = process.env.BACKEND_INTERNAL_URL || "http://localhost:8000"
    return {
      fallback: [
        { source: "/ws/:path*", destination: `${backend}/ws/:path*` },
        {
          source: "/api/:path*",
          destination: `${backend}/api/:path*`,
        },
        {
          source: "/media/:path*",
          destination: `${backend}/media/:path*`,
        },
      ],
    }
  },
}

export default nextConfig
