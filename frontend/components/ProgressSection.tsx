'use client';

import { useState, useEffect } from 'react';
import { useToast } from '@/contexts/ToastContext';
import { api } from '@/lib/api';
import type { Book } from '@/types';

interface ProgressSectionProps {
  book: Book;
  onRefresh: () => void;
}

export default function ProgressSection({ book, onRefresh }: ProgressSectionProps) {
  const { showToast } = useToast();
  const latest = book.latest_progress;
  const percent = Math.min(100, Math.max(0, latest?.percentage ?? 0));

  const [currentPage, setCurrentPage] = useState(String(latest?.current_page ?? ''));
  const [totalPages, setTotalPages] = useState(String(latest?.total_pages ?? book.pages ?? ''));
  const [processing, setProcessing] = useState(false);

  useEffect(() => {
    setCurrentPage(String(book.latest_progress?.current_page ?? ''));
    setTotalPages(String(book.latest_progress?.total_pages ?? book.pages ?? ''));
  }, [book.latest_progress?.current_page, book.latest_progress?.total_pages, book.pages]);

  async function saveProgress() {
    const cp = Number(currentPage || 0);
    const tp = Number(totalPages || 0) || null;
    try {
      await api(`/books/${book.id}/progress`, {
        method: 'POST',
        body: JSON.stringify({ current_page: cp, total_pages: tp, source: 'manual' }),
      });
      showToast('Progress saved');
      onRefresh();
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : 'Could not save progress', 'error');
    }
  }

  async function uploadPhoto(file: File) {
    setProcessing(true);
    showToast('🔄 Processing page photo…');
    try {
      await api(`/books/${book.id}/progress/photo`, {
        method: 'POST',
        headers: { 'content-type': 'application/octet-stream' },
        body: await file.arrayBuffer(),
      });
      showToast('✨ Progress tracked from page photo');
      onRefresh();
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : 'Photo processing failed', 'error');
    } finally {
      setProcessing(false);
    }
  }

  return (
    <section className="panel rounded-2xl p-4 shadow-lift sm:p-5">
      <div className="mb-4 flex items-center justify-between gap-4">
        <div>
          <p className="text-sm font-bold uppercase tracking-[.2em] text-teal-200/70">Progress Tracker</p>
          <h3 className="mt-1 text-2xl font-extrabold text-white">Reading progress</h3>
        </div>
        <span className="rounded-full border border-teal-300/30 bg-teal-300/10 px-3 py-1 text-sm font-extrabold text-teal-100">
          {Math.round(percent)}%
        </span>
      </div>
      <div className="mb-4 h-3 overflow-hidden rounded-full bg-slate-800">
        <div
          className="h-full rounded-full bg-gradient-to-r from-teal-300 to-ember transition-all"
          style={{ width: `${percent}%` }}
        />
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <input
          className="field"
          type="number"
          min={0}
          placeholder="Current page"
          value={currentPage}
          onChange={(e) => setCurrentPage(e.target.value)}
        />
        <input
          className="field"
          type="number"
          min={1}
          placeholder="Total pages"
          value={totalPages}
          onChange={(e) => setTotalPages(e.target.value)}
        />
        <button className="btn btn-secondary sm:col-span-2" type="button" onClick={saveProgress}>
          Save Progress
        </button>
      </div>
      <label className={`mt-4 grid cursor-pointer place-items-center rounded-2xl border border-dashed border-teal-300/35 bg-teal-300/5 p-6 text-center transition hover:border-teal-200 hover:bg-teal-300/10 ${processing ? 'pointer-events-none opacity-60' : ''}`}>
        <input
          className="sr-only"
          type="file"
          accept="image/*"
          capture="environment"
          disabled={processing}
          onChange={(e) => e.target.files?.[0] && uploadPhoto(e.target.files[0])}
        />
        <span className="text-3xl">{processing ? '🔄' : '✨'}</span>
        <span className="mt-2 block font-extrabold text-white">{processing ? 'Processing…' : 'Track Progress by Page Photo'}</span>
        <span className="mt-1 block text-sm text-slate-400">Upload a page photo to detect page number.</span>
      </label>
    </section>
  );
}
