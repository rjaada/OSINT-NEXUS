import type { Metadata, Viewport } from 'next'
import { JetBrains_Mono, IBM_Plex_Serif, IBM_Plex_Mono, Black_Ops_One } from 'next/font/google'
import { FirstOpenOverlay } from '@/components/system/first-open-overlay'
import { Toaster } from '@/components/ui/sonner'
import { AuthProvider } from '@/lib/auth-context'
import './globals.css'

const jetbrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  variable: '--font-jetbrains',
})

const ibmSerif = IBM_Plex_Serif({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  variable: '--font-serif',
})

const ibmMono = IBM_Plex_Mono({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  variable: '--font-ibm-mono',
})

const blackOps = Black_Ops_One({
  subsets: ['latin'],
  weight: ['400'],
  variable: '--font-stencil',
})

export const metadata: Metadata = {
  title: 'OSINT NEXUS - Intelligence Dashboard',
  description: 'Real-time military OSINT intelligence monitoring and analysis dashboard',
  icons: {
    icon: [
      {
        url: '/icon-light-32x32.png',
        media: '(prefers-color-scheme: light)',
      },
      {
        url: '/icon-dark-32x32.png',
        media: '(prefers-color-scheme: dark)',
      },
      {
        url: '/icon.svg',
        type: 'image/svg+xml',
      },
    ],
    apple: '/apple-icon.png',
  },
}

export const viewport: Viewport = {
  themeColor: '#050507',
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en">
      <body className={`${jetbrainsMono.variable} ${ibmSerif.variable} ${ibmMono.variable} ${blackOps.variable} font-mono antialiased`}>
        <AuthProvider>
          <FirstOpenOverlay />
          {children}
          <Toaster richColors closeButton />
        </AuthProvider>
      </body>
    </html>
  )
}
