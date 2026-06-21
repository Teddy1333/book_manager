'use client';

import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import Navbar from '@/components/Navbar';
import ProgressSection from '@/components/ProgressSection';
import NotesSection from '@/components/NotesSection';
import ShareSection from '@/components/ShareSection';
import { api } from '@/lib/api';
import { useToast } from '@/contexts/ToastContext';
import type { Book } from '@/types';

export default function BookDetailsPage() {
  const { id } = useParams<{ id: string }>();
  const { showToast } = useToast();
  const [book, setBook] = useState<Book | null>(null);
  const [loading, setLoading] = useState(true);

  const loadBook = useCallback(async () => {
    try {
      const data = await api(`/books/${id}`);
      setBook(data);
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : 'Could not load book', 'error');
    } finally {
      setLoading(false);
    }
  }, [id, showToast]);

  useEffect(() => { loadBook(); }, [loadBook]);

  if (loading) {
    return (
      <div className="min-h-screen">
        <Navbar showBack backHref="/dashboard" />
        <div className="mx-auto max-w-6xl px-4 py-8">
          <div className="panel rounded-xl p-5 text-slate-300">Loading book…</div>
        </div>
      </div>
    );
  }

  if (!book) {
    return (
      <div className="min-h-screen">
        <Navbar showBack backHref="/dashboard" />
        <div className="mx-auto max-w-6xl px-4 py-8">
          <div className="panel rounded-xl p-5 text-slate-300">Book not found.</div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen pb-12">
      <Navbar
        showBack
        backHref="/dashboard"
        rightAction={
          <Link href={`/books/${id}/edit`} className="btn btn-primary">
            Edit Book
          </Link>
        }
      />
      <div className="mx-auto max-w-6xl px-4 py-6 sm:py-8">
        {/* Header */}
        <header className="mb-7 grid gap-4 sm:grid-cols-[auto_minmax(0,1fr)] sm:items-end">
          <div className="grid h-36 w-28 place-items-center overflow-hidden rounded-xl border border-teal-300/20 bg-teal-300/10 text-4xl shadow-glow">
            {book.cover_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img className="h-full w-full object-cover" src={book.cover_url} alt={`${book.title} cover`} />
            ) : (
              '📖'
            )}
          </div>
          <div>
            <p className="text-sm font-bold uppercase tracking-[.22em] text-ember/80">Book Details &amp; Notes</p>
            <h2 className="mt-2 font-display text-4xl font-bold text-white">{book.title}</h2>
            <p className="mt-2 text-slate-300">{book.author || 'Unknown author'}</p>
            {book.tags?.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {book.tags.map((tag) => (
                  <span key={tag} className="rounded-full bg-teal-300/10 px-2.5 py-1 text-xs font-bold text-teal-100">
                    {tag}
                  </span>
                ))}
              </div>
            )}
          </div>
        </header>

        {/* Content grid */}
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
          <div className="space-y-5">
            <ProgressSection book={book} onRefresh={loadBook} />
            <NotesSection bookId={book.id} />
          </div>
          <ShareSection book={book} />
        </div>
      </div>
    </div>
  );
}
