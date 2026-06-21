'use client';

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import Navbar from '@/components/Navbar';
import BookForm from '@/components/BookForm';
import { api } from '@/lib/api';
import { useToast } from '@/contexts/ToastContext';
import type { Book } from '@/types';

export default function EditBookPage() {
  const { id } = useParams<{ id: string }>();
  const { showToast } = useToast();
  const [book, setBook] = useState<Book | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api(`/books/${id}`)
      .then(setBook)
      .catch((e: unknown) => showToast(e instanceof Error ? e.message : 'Could not load book', 'error'))
      .finally(() => setLoading(false));
  }, [id, showToast]);

  return (
    <div className="min-h-screen pb-12">
      <Navbar showBack backHref={`/books/${id}`} backLabel="Details" />
      <div className="mx-auto max-w-5xl px-4 py-6 sm:py-8">
        <div className="mb-7">
          <p className="text-sm font-bold uppercase tracking-[.22em] text-ember/80">Register or rename</p>
          <h2 className="mt-2 font-display text-4xl font-bold text-white">Edit Book</h2>
        </div>
        {loading ? (
          <div className="panel rounded-xl p-5 text-slate-300">Loading…</div>
        ) : book ? (
          <BookForm book={book} />
        ) : (
          <div className="panel rounded-xl p-5 text-slate-300">Book not found.</div>
        )}
      </div>
    </div>
  );
}
