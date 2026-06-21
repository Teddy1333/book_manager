'use client';

import { useState, FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import { useToast } from '@/contexts/ToastContext';

export default function LoginPage() {
  const router = useRouter();
  const { showToast } = useToast();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleLogin(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    try {
      const form = new URLSearchParams();
      form.set('username', username);
      form.set('password', password);
      const res = await fetch('/api/proxy/token', {
        method: 'POST',
        headers: { 'content-type': 'application/x-www-form-urlencoded' },
        body: form.toString(),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(String(err.detail || 'Login failed'));
      }
      router.push('/dashboard');
      router.refresh();
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : 'Login failed', 'error');
    } finally {
      setLoading(false);
    }
  }

  async function handleSignup() {
    if (!username || !password) return showToast('Enter a username and password first', 'error');
    setLoading(true);
    try {
      const query = new URLSearchParams({ username, password });
      const res = await fetch(`/api/proxy/signup?${query}`, { method: 'POST' });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(String(err.detail || 'Signup failed'));
      }
      showToast('Account created — logging in…');
      // Auto-login after signup
      const form = new URLSearchParams();
      form.set('username', username);
      form.set('password', password);
      const loginRes = await fetch('/api/proxy/token', {
        method: 'POST',
        headers: { 'content-type': 'application/x-www-form-urlencoded' },
        body: form.toString(),
      });
      if (loginRes.ok) {
        router.push('/dashboard');
        router.refresh();
      }
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : 'Signup failed', 'error');
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen px-4 py-8">
      <div className="mx-auto flex min-h-[calc(100vh-4rem)] w-full max-w-md items-center">
        <div className="glass w-full rounded-2xl border border-teal-300/15 p-6 shadow-lift sm:p-8">
          <div className="mb-8">
            <div className="mb-5 grid h-14 w-14 place-items-center rounded-2xl bg-teal-300 text-2xl font-black text-teal-950 shadow-glow">
              B
            </div>
            <p className="mb-2 text-sm font-bold uppercase tracking-[.22em] text-teal-200/80">Premium library</p>
            <h1 className="font-display text-4xl font-bold text-white">Book Manager</h1>
            <p className="mt-3 text-sm leading-6 text-slate-300">
              Sign in to manage books, reading progress, notes, and shareable reading cards.
            </p>
          </div>
          <form onSubmit={handleLogin} className="space-y-4">
            <label className="block">
              <span className="mb-2 block text-sm font-bold text-slate-200">Username</span>
              <input
                className="field"
                type="text"
                autoComplete="username"
                placeholder="Enter your username"
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </label>
            <label className="block">
              <span className="mb-2 block text-sm font-bold text-slate-200">Password</span>
              <input
                className="field"
                type="password"
                autoComplete="current-password"
                placeholder="Enter your password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
            <button className="btn btn-primary w-full" type="submit" disabled={loading}>
              {loading ? 'Please wait…' : 'Login'}
            </button>
            <button className="btn btn-secondary w-full" type="button" onClick={handleSignup} disabled={loading}>
              Create Account
            </button>
          </form>
        </div>
      </div>
    </main>
  );
}
