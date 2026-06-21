'use client';

import { useState, useRef, FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import { useToast } from '@/contexts/ToastContext';
import { api } from '@/lib/api';
import type { Book, BookSearchResult } from '@/types';

interface BookFormProps {
  book?: Book;
}

export default function BookForm({ book }: BookFormProps) {
  const router = useRouter();
  const { showToast } = useToast();
  const isEdit = Boolean(book);

  const [title, setTitle] = useState(book?.title ?? '');
  const [author, setAuthor] = useState(book?.author ?? '');
  const [pages, setPages] = useState(book?.pages ?? '');
  const [tags, setTags] = useState((book?.tags ?? []).join(', '));
  const [isbn, setIsbn] = useState(book?.isbn ?? '');
  const [publisher, setPublisher] = useState(book?.publisher ?? '');
  const [coverUrl, setCoverUrl] = useState(book?.cover_url ?? '');
  const [description, setDescription] = useState(book?.description ?? '');

  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<BookSearchResult[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [shareImportUrl, setShareImportUrl] = useState('');
  const [saving, setSaving] = useState(false);
  const [processing, setProcessing] = useState(false);

  const photoInputRef = useRef<HTMLInputElement>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const [isRecording, setIsRecording] = useState(false);

  function fillFromResult(result: BookSearchResult) {
    setTitle(result.title ?? '');
    setAuthor(result.author ?? '');
    setPages(result.pages ?? '');
    setTags((result.tags ?? []).join(', '));
    setIsbn(result.isbn ?? '');
    setPublisher(result.publisher ?? '');
    setCoverUrl(result.cover_url ?? '');
    setDescription(result.description ?? '');
    setSearchResults([]);
    showToast('Book details filled from search');
  }

  async function runSearch(query: string) {
    const normalizedIsbn = query.toUpperCase().replace(/[^0-9X]/g, '');
    const isIsbn = normalizedIsbn.length === 10 || normalizedIsbn.length === 13;
    setSearchLoading(true);
    try {
      if (isIsbn) {
        const result = await api(`/lookup/isbn/${encodeURIComponent(normalizedIsbn)}`);
        const matches = result.matches ?? [];
        setSearchResults(matches);
        if (result.errors?.length) showToast(result.errors.join(' | '), 'error');
        if (matches.length === 0) showToast('No ISBN matches found');
      } else {
        const results = await api(`/lookup/google?q=${encodeURIComponent(query)}&limit=5`);
        const matches = Array.isArray(results) ? results : [];
        setSearchResults(matches);
        if (matches.length === 0) showToast('No matches found');
      }
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : 'Search failed', 'error');
    } finally {
      setSearchLoading(false);
    }
  }

  async function handleSearchKey(e: React.KeyboardEvent) {
    if (e.key === 'Enter') { e.preventDefault(); runSearch(searchQuery); }
  }

  async function recognizePhoto(file: File) {
    setProcessing(true);
    showToast('🔄 Recognizing book from photo…');
    try {
      const data = await api('/books/photo/recognize', {
        method: 'POST',
        headers: { 'content-type': 'application/octet-stream' },
        body: await file.arrayBuffer(),
      });
      if (data.matches?.length) {
        setSearchResults(data.matches);
        fillFromResult(data.matches[0]);
        showToast('Photo processed — book details filled');
      } else {
        showToast('No matching books found from photo', 'error');
      }
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : 'Photo recognition failed', 'error');
    } finally {
      setProcessing(false);
      if (photoInputRef.current) photoInputRef.current.value = '';
    }
  }

  async function toggleVoiceSearch() {
    if (isRecording && recorderRef.current) {
      recorderRef.current.stop();
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      chunksRef.current = [];
      const rec = new MediaRecorder(stream);
      recorderRef.current = rec;
      setIsRecording(true);

      rec.ondataavailable = (e) => chunksRef.current.push(e.data);
      rec.onstop = async () => {
        setIsRecording(false);
        stream.getTracks().forEach((t) => t.stop());
        recorderRef.current = null;

        const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
        showToast('🔄 Transcribing…');
        try {
          const data = await api('/books/voice/recognize?audio_format=webm', {
            method: 'POST',
            headers: { 'content-type': 'application/octet-stream' },
            body: await blob.arrayBuffer(),
          });
          const transcript = data.transcript || '';
          setSearchQuery(transcript);
          if (data.matches?.length) {
            setSearchResults(data.matches);
            fillFromResult(data.matches[0]);
            showToast('Voice recognized — book details filled');
          } else if (transcript) {
            await runSearch(transcript);
          } else {
            showToast('Could not recognize speech', 'error');
          }
        } catch (e: unknown) {
          showToast(e instanceof Error ? e.message : 'Voice search failed', 'error');
        }
      };

      rec.start();
      showToast('🎙️ Recording… tap again to stop');
    } catch {
      showToast('Microphone access denied', 'error');
    }
  }

  async function importFromShare() {
    if (!shareImportUrl.trim()) return showToast('Enter a share URL', 'error');
    try {
      const imported = await api('/books/import/share', {
        method: 'POST',
        body: JSON.stringify({ url: shareImportUrl }),
      });
      showToast(`Imported "${imported.title}"`);
      router.push('/dashboard');
      router.refresh();
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : 'Import failed', 'error');
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!title.trim()) return showToast('Title is required', 'error');
    setSaving(true);
    const payload = {
      title: title.trim(),
      author: author.trim() || null,
      isbn: isbn.trim() || null,
      publisher: publisher.trim() || null,
      pages: pages.trim() || null,
      description: description.trim() || null,
      cover_url: coverUrl.trim() || null,
      source: 'manual',
      tags: tags.split(',').map((t) => t.trim().toLowerCase()).filter(Boolean),
    };
    try {
      if (isEdit && book) {
        await api(`/books/${book.id}`, { method: 'PATCH', body: JSON.stringify(payload) });
        showToast('Book updated');
        router.push(`/books/${book.id}`);
      } else {
        const created = await api('/books', { method: 'POST', body: JSON.stringify(payload) });
        showToast('Book saved');
        router.push(`/books/${created.id}`);
      }
      router.refresh();
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : 'Could not save book', 'error');
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="panel space-y-5 rounded-2xl p-4 shadow-lift sm:p-6">
      {!isEdit && (
        <div className="space-y-4">
          {/* Google Books / ISBN Search */}
          <div className="rounded-xl border border-teal-300/15 bg-slate-950/45 p-4">
            <span className="mb-2 block text-sm font-bold text-slate-200">Search Google Books API</span>
            <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto]">
              <input
                className="field"
                type="search"
                placeholder="Title, author, or ISBN"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={handleSearchKey}
              />
              <button
                className="btn btn-secondary"
                type="button"
                onClick={() => runSearch(searchQuery)}
                disabled={searchLoading}
              >
                {searchLoading ? '…' : 'Search'}
              </button>
            </div>
            {searchResults.length > 0 && (
              <div className="mt-4 grid gap-3">
                {searchResults.map((result, i) => (
                  <button
                    key={i}
                    className="grid rounded-xl border border-white/10 bg-slate-950/60 p-3 text-left transition hover:border-teal-300/50 hover:bg-teal-300/10"
                    type="button"
                    onClick={() => fillFromResult(result)}
                  >
                    <span className="font-extrabold text-white">{result.title || 'Untitled'}</span>
                    <span className="text-sm text-slate-400">{result.author || 'Unknown author'}</span>
                    <span className="text-xs font-bold text-slate-500">
                      ISBN: {result.isbn || 'unknown'} · Pages: {result.pages || 'unknown'}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* AI Tools */}
          <div className="grid gap-3 sm:grid-cols-2">
            <button className="btn btn-ai" type="button" disabled={processing} onClick={() => photoInputRef.current?.click()}>
              {processing ? '🔄 Processing…' : '✨ Add by Photo'}
            </button>
            <button className="btn btn-ai" type="button" disabled={processing} onClick={toggleVoiceSearch}>
              {isRecording ? '⏹ Stop Recording' : '✨ Add by Voice'}
            </button>
            <input
              ref={photoInputRef}
              type="file"
              accept="image/*"
              capture="environment"
              hidden
              onChange={(e) => e.target.files?.[0] && recognizePhoto(e.target.files[0])}
            />
          </div>

          {/* Share Import */}
          <div className="rounded-xl border border-teal-300/15 bg-slate-950/45 p-4">
            <span className="mb-2 block text-sm font-bold text-slate-200">Import from shared link</span>
            <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto]">
              <input
                className="field"
                type="url"
                placeholder="http://…/share/token"
                value={shareImportUrl}
                onChange={(e) => setShareImportUrl(e.target.value)}
              />
              <button className="btn btn-secondary" type="button" onClick={importFromShare}>
                Import
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Manual fields */}
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block">
          <span className="mb-2 block text-sm font-bold text-slate-200">Title *</span>
          <input className="field" required value={title} onChange={(e) => setTitle(e.target.value)} />
        </label>
        <label className="block">
          <span className="mb-2 block text-sm font-bold text-slate-200">Author</span>
          <input className="field" value={author} onChange={(e) => setAuthor(e.target.value)} />
        </label>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block">
          <span className="mb-2 block text-sm font-bold text-slate-200">Tags</span>
          <input
            className="field"
            placeholder="fiction, design, research"
            value={tags}
            onChange={(e) => setTags(e.target.value)}
          />
        </label>
        <label className="block">
          <span className="mb-2 block text-sm font-bold text-slate-200">Pages</span>
          <input
            className="field"
            inputMode="numeric"
            placeholder="320"
            value={pages}
            onChange={(e) => setPages(e.target.value)}
          />
        </label>
      </div>

      {/* Hidden fields populated by search */}
      <input type="hidden" value={isbn} readOnly />
      <input type="hidden" value={publisher} readOnly />
      <input type="hidden" value={coverUrl} readOnly />

      <div className="grid gap-3 pt-2 sm:grid-cols-2">
        <button className="btn btn-primary" type="submit" disabled={saving}>
          {saving ? 'Saving…' : 'Save'}
        </button>
        <button className="btn btn-secondary" type="button" onClick={() => router.back()}>
          Cancel
        </button>
      </div>
    </form>
  );
}
