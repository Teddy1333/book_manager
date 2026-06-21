'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import Navbar from '@/components/Navbar';
import BookCard from '@/components/BookCard';
import { api } from '@/lib/api';
import { useToast } from '@/contexts/ToastContext';
import type { Book, UserStats } from '@/types';

export default function DashboardPage() {
  const { showToast } = useToast();
  const [books, setBooks] = useState<Book[]>([]);
  const [stats, setStats] = useState<UserStats | null>(null);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [booksData, statsData] = await Promise.all([
        api('/books'),
        api('/user/stats').catch(() => null),
      ]);
      setBooks(Array.isArray(booksData) ? booksData : []);
      setStats(statsData);
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : 'Could not load books', 'error');
    } finally {
      setLoading(false);
    }
  }, [showToast]);

  useEffect(() => { loadData(); }, [loadData]);

  async function deleteBook(bookId: number) {
    if (!confirm('Delete this book and all its notes?')) return;
    try {
      await api(`/books/${bookId}`, { method: 'DELETE' });
      showToast('Book deleted');
      loadData();
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : 'Could not delete book', 'error');
    }
  }

  const filtered = books.filter((book) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return [book.title, book.author, ...(book.tags ?? [])].join(' ').toLowerCase().includes(q);
  });

  const totalPages = books.reduce((sum, b) => sum + (b.latest_progress?.current_page ?? 0), 0);

  return (
    <div className="min-h-screen pb-28">
      <Navbar
        rightAction={
          <button className="btn btn-secondary hidden sm:inline-flex" type="button" onClick={loadData}>
            Refresh
          </button>
        }
      />
      <div className="mx-auto max-w-7xl px-4 py-6 sm:py-8">
        <div className="mb-6">
          <p className="text-sm font-bold uppercase tracking-[.22em] text-ember/80">Reading command center</p>
          <h2 className="mt-2 font-display text-4xl font-bold text-white sm:text-5xl">Your Library</h2>
        </div>

        {/* Stats */}
        <div className="mb-7 grid grid-cols-2 gap-3 sm:grid-cols-4 sm:gap-4">
          <article className="panel rounded-xl p-4 shadow-glow sm:p-5">
            <p className="text-sm font-semibold text-slate-400">Books</p>
            <strong className="mt-2 block text-3xl font-black text-white">
              {stats?.books_count ?? books.length}
            </strong>
          </article>
          <article className="panel rounded-xl p-4 shadow-glow sm:p-5">
            <p className="text-sm font-semibold text-slate-400">Notes</p>
            <strong className="mt-2 block text-3xl font-black text-white">{stats?.notes_count ?? '—'}</strong>
          </article>
          <article className="panel rounded-xl p-4 shadow-glow sm:p-5">
            <p className="text-sm font-semibold text-slate-400">Pages Read</p>
            <strong className="mt-2 block text-3xl font-black text-white">
              {stats?.total_read_pages ?? totalPages}
            </strong>
          </article>
          <article className="panel rounded-xl p-4 shadow-glow sm:p-5">
            <p className="text-sm font-semibold text-slate-400">Top Genre</p>
            <strong className="mt-2 block truncate text-xl font-black text-white">
              {stats?.top_genres?.[0]?.tag ?? '—'}
            </strong>
          </article>
        </div>

        {/* Filter */}
        <div className="mb-4 flex items-end justify-between gap-4">
          <div>
            <p className="text-sm font-bold uppercase tracking-[.2em] text-teal-200/70">Library</p>
            <h3 className="mt-1 text-2xl font-extrabold text-white">Book shelf</h3>
          </div>
          <input
            className="field max-w-xs"
            type="search"
            placeholder="Search books…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        {/* Grid */}
        {loading ? (
          <div className="panel rounded-xl p-5 text-slate-300">Loading your library…</div>
        ) : filtered.length === 0 ? (
          <div className="panel rounded-xl p-5 text-slate-300">
            {books.length === 0
              ? 'No books yet. Use the + button to add your first book.'
              : 'No books match your search.'}
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {filtered.map((book) => (
              <BookCard key={book.id} book={book} onDelete={deleteBook} />
            ))}
          </div>
        )}
      </div>

      <Link
        href="/books/new"
        className="btn btn-primary fixed bottom-5 right-5 z-40 h-16 rounded-full px-6 text-base sm:bottom-8 sm:right-8"
      >
        <span className="text-2xl leading-none">+</span>
        Add New Book
      </Link>
    </div>
  );
}
