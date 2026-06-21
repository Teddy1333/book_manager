import type { Metadata } from 'next';
import { Fraunces, Manrope } from 'next/font/google';
import './globals.css';
import { ToastProvider } from '@/contexts/ToastContext';

const manrope = Manrope({
  subsets: ['latin'],
  variable: '--font-manrope',
  display: 'swap',
});

const fraunces = Fraunces({
  subsets: ['latin'],
  variable: '--font-fraunces',
  display: 'swap',
  weight: ['600', '700'],
});

export const metadata: Metadata = {
  title: 'Book Manager',
  description: 'Manage your personal library, reading progress, notes, and sharing.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="scroll-smooth">
      <body
        className={`${manrope.variable} ${fraunces.variable} min-h-screen overflow-x-hidden bg-night font-sans text-slate-100 antialiased`}
      >
        {/* Background gradients */}
        <div className="fixed inset-0 -z-10 bg-[radial-gradient(circle_at_top_left,rgba(20,184,166,.22),transparent_32%),linear-gradient(135deg,#06120f_0%,#0f172a_48%,#10110d_100%)]" />
        <div className="fixed inset-0 -z-10 opacity-[.08] [background-image:linear-gradient(rgba(255,255,255,.9)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,.9)_1px,transparent_1px)] [background-size:36px_36px]" />
        <ToastProvider>{children}</ToastProvider>
      </body>
    </html>
  );
}
