'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import dynamic from 'next/dynamic';
import { useToast } from '@/contexts/ToastContext';
import { api } from '@/lib/api';
import type { Note } from '@/types';

const HandwritingCanvas = dynamic(() => import('./HandwritingCanvas'), { ssr: false });

export default function NotesSection({ bookId }: { bookId: number }) {
  const { showToast } = useToast();
  const [notes, setNotes] = useState<Note[]>([]);
  const [text, setText] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editText, setEditText] = useState('');
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const loadNotes = useCallback(async () => {
    try {
      const data = await api(`/books/${bookId}/notes`);
      setNotes(Array.isArray(data) ? data : []);
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : 'Could not load notes', 'error');
    }
  }, [bookId, showToast]);

  useEffect(() => { loadNotes(); }, [loadNotes]);

  async function saveTypedNote() {
    if (!text.trim()) return showToast('Write a note first', 'error');
    try {
      await api(`/books/${bookId}/notes`, {
        method: 'POST',
        body: JSON.stringify({ text: text.trim(), note_type: 'manual' }),
      });
      setText('');
      showToast('Note saved');
      loadNotes();
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : 'Could not save note', 'error');
    }
  }

  async function deleteNote(noteId: number) {
    if (!confirm('Delete this note?')) return;
    try {
      await api(`/books/${bookId}/notes/${noteId}`, { method: 'DELETE' });
      showToast('Note deleted');
      loadNotes();
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : 'Could not delete note', 'error');
    }
  }

  function startEditing(note: Note) {
    setEditingId(note.id);
    setEditText(note.text);
  }

  function cancelEditing() {
    setEditingId(null);
    setEditText('');
  }

  async function saveEdit(noteId: number) {
    if (!editText.trim()) return showToast('Note cannot be empty', 'error');
    try {
      await api(`/books/${bookId}/notes/${noteId}`, {
        method: 'PATCH',
        body: JSON.stringify({ text: editText.trim() }),
      });
      showToast('Note updated');
      setEditingId(null);
      setEditText('');
      loadNotes();
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : 'Could not update note', 'error');
    }
  }

  async function toggleVoiceNote() {
    if (isRecording && recorderRef.current) {
      recorderRef.current.stop();
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      chunksRef.current = [];
      const rec = new MediaRecorder(stream);
      recorderRef.current = rec;
      rec.ondataavailable = (e) => chunksRef.current.push(e.data);
      rec.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        setIsRecording(false);
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
        try {
          await api(`/books/${bookId}/notes/voice?audio_format=webm`, {
            method: 'POST',
            headers: { 'content-type': 'application/octet-stream' },
            body: await blob.arrayBuffer(),
          });
          showToast('✨ Voice note saved');
          loadNotes();
        } catch (e: unknown) {
          showToast(e instanceof Error ? e.message : 'Voice note failed', 'error');
        }
      };
      rec.start();
      setIsRecording(true);
      showToast('Recording… tap again to stop');
    } catch {
      showToast('Microphone access denied', 'error');
    }
  }

  return (
    <section className="panel rounded-2xl p-4 shadow-lift sm:p-5">
      <p className="text-sm font-bold uppercase tracking-[.2em] text-teal-200/70">Notes Section</p>
      <h3 className="mt-1 text-2xl font-extrabold text-white">Typed, voice &amp; handwritten</h3>
      <div className="mt-4 grid gap-4">
        <textarea
          className="field min-h-36"
          placeholder="Type a note for this book…"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <div className="grid gap-3 sm:grid-cols-2">
          <button className="btn btn-primary" type="button" onClick={saveTypedNote}>
            Save Typed Note
          </button>
          <button className="btn btn-ai" type="button" onClick={toggleVoiceNote}>
            {isRecording ? '⏹ Stop Recording' : '✨ Voice Note'}
          </button>
        </div>

        <div className="rounded-2xl border border-teal-300/20 bg-slate-950/55 p-3">
          <p className="mb-3 font-extrabold text-white">Handwritten Notes</p>
          <HandwritingCanvas bookId={bookId} onNoteAdded={loadNotes} />
        </div>

        {notes.length === 0 ? (
          <div className="rounded-xl border border-white/10 bg-slate-950/40 p-3 text-sm font-bold text-slate-400">
            No notes yet.
          </div>
        ) : (
          <div className="grid gap-3">
            {notes.map((note) => (
              <article key={note.id} className="rounded-xl border border-white/10 bg-slate-950/55 p-3">
                {editingId === note.id ? (
                  <>
                    <textarea
                      className="field min-h-24"
                      value={editText}
                      onChange={(e) => setEditText(e.target.value)}
                      autoFocus
                    />
                    <div className="mt-2 flex gap-2">
                      <button
                        className="btn btn-primary min-h-9 px-3 py-1 text-xs"
                        type="button"
                        onClick={() => saveEdit(note.id)}
                      >
                        Save
                      </button>
                      <button
                        className="btn btn-secondary min-h-9 px-3 py-1 text-xs"
                        type="button"
                        onClick={cancelEditing}
                      >
                        Cancel
                      </button>
                    </div>
                  </>
                ) : (
                  <>
                    <p className="text-sm leading-6 text-slate-200">{note.text}</p>
                    <p className="mt-2 text-xs font-bold uppercase tracking-[.16em] text-teal-200/60">
                      {note.note_type}
                      {note.page != null ? ` · Page ${note.page}` : ''}
                    </p>
                    <div className="mt-2 flex gap-2">
                      <button
                        className="btn btn-secondary min-h-9 px-3 py-1 text-xs"
                        type="button"
                        onClick={() => startEditing(note)}
                      >
                        Edit
                      </button>
                      <button
                        className="btn btn-danger min-h-9 px-3 py-1 text-xs"
                        type="button"
                        onClick={() => deleteNote(note.id)}
                      >
                        Delete
                      </button>
                    </div>
                  </>
                )}
              </article>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
