'use client';

import { useState } from 'react';
import { useToast } from '@/contexts/ToastContext';
import { api } from '@/lib/api';
import type { Book, ShareInfo } from '@/types';

export default function ShareSection({ book }: { book: Book }) {
  const { showToast } = useToast();
  const [shareInfo, setShareInfo] = useState<ShareInfo | null>(null);

  async function createShareLink() {
    try {
      const info = await api(`/books/${book.id}/share`, { method: 'POST' });
      setShareInfo(info);
      showToast('Share link created');
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : 'Could not create share link', 'error');
    }
  }

  async function copyLink() {
    if (!shareInfo?.share_url) return showToast('Create a share link first', 'error');
    await navigator.clipboard.writeText(shareInfo.share_url);
    showToast('Link copied');
  }

  async function nativeShare() {
    const url = shareInfo?.share_url ?? window.location.href;
    if (navigator.share) {
      await navigator.share({ title: book.title, text: 'Shared from Book Manager', url });
    } else {
      await navigator.clipboard.writeText(url);
      showToast('Link copied (native share unavailable)');
    }
  }

  return (
    <aside className="panel h-max rounded-2xl p-4 shadow-lift sm:p-5">
      <p className="text-sm font-bold uppercase tracking-[.2em] text-teal-200/70">Share Section</p>
      <h3 className="mt-1 text-2xl font-extrabold text-white">Dynamic share</h3>
      <div className="mt-5">
        {shareInfo?.qr_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img className="w-full rounded-2xl bg-white p-4" src={shareInfo.qr_url} alt="QR code" />
        ) : (
          <div className="grid aspect-square place-items-center rounded-2xl border border-dashed border-teal-300/35 bg-slate-950/60 p-6 text-center">
            <div>
              <div className="mx-auto grid h-28 w-28 place-items-center rounded-xl bg-white text-5xl text-slate-950">
                ▦
              </div>
              <p className="mt-4 text-sm font-semibold text-slate-400">Dynamic QR Code placeholder</p>
            </div>
          </div>
        )}
      </div>
      <input
        className="field mt-4"
        readOnly
        placeholder="Share link appears here"
        value={shareInfo?.share_url ?? ''}
      />
      <div className="mt-3 grid gap-3">
        <button className="btn btn-secondary" type="button" onClick={createShareLink}>
          Create QR Link
        </button>
        <button className="btn btn-primary" type="button" onClick={copyLink}>
          Copy Link
        </button>
        <button className="btn btn-ai" type="button" onClick={nativeShare}>
          ✨ Native Share
        </button>
      </div>
    </aside>
  );
}
