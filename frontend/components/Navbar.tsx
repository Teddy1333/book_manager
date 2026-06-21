'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';

interface NavbarProps {
  showBack?: boolean;
  backHref?: string;
  backLabel?: string;
  rightAction?: React.ReactNode;
}

export default function Navbar({
  showBack = false,
  backHref = '/dashboard',
  backLabel = 'Back',
  rightAction,
}: NavbarProps) {
  const router = useRouter();

  async function logout() {
    await fetch('/api/auth/logout', { method: 'POST' });
    router.push('/');
    router.refresh();
  }

  return (
    <nav className="sticky top-0 z-30 border-b border-white/10 bg-night/[0.86] px-4 py-3 backdrop-blur-xl">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-3">
        {showBack ? (
          <Link href={backHref} className="btn btn-secondary">
            ← {backLabel}
          </Link>
        ) : (
          <Link href="/dashboard" className="flex items-center gap-3 text-left">
            <span className="grid h-11 w-11 place-items-center rounded-xl bg-teal-300 font-black text-teal-950">B</span>
            <span>
              <span className="block font-display text-xl font-bold text-white">Book Manager</span>
              <span className="block text-xs font-bold uppercase tracking-[.18em] text-teal-200/70">Dashboard</span>
            </span>
          </Link>
        )}
        <div className="flex items-center gap-2">
          {rightAction}
          {!showBack && (
            <button className="btn btn-secondary" type="button" onClick={logout}>
              Logout
            </button>
          )}
        </div>
      </div>
    </nav>
  );
}
