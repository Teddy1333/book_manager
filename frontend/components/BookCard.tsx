import Link from 'next/link';
import type { Book } from '@/types';

function getProgress(book: Book) {
  const latest = book.latest_progress;
  const total = Number(latest?.total_pages || book.pages || 0);
  const current = Number(latest?.current_page || 0);
  const percent = latest?.percentage ?? (total ? Math.round((current / total) * 100) : 0);
  return { current, total, percent: Math.min(100, Math.max(0, Number(percent) || 0)) };
}

interface BookCardProps {
  book: Book;
  onDelete: (id: number) => void;
}

export default function BookCard({ book, onDelete }: BookCardProps) {
  const progress = getProgress(book);

  return (
    <article className="panel group rounded-2xl p-4 shadow-lift transition hover:border-teal-300/45 hover:bg-slate-950/60">
      <div className="grid grid-cols-[5.25rem_minmax(0,1fr)] gap-4">
        <div className="grid aspect-[3/4] place-items-center overflow-hidden rounded-xl border border-white/10 bg-teal-300/10">
          {book.cover_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img className="h-full w-full object-cover" src={book.cover_url} alt={`${book.title} cover`} />
          ) : (
            <span className="text-3xl">📖</span>
          )}
        </div>
        <div className="min-w-0">
          <h4 className="line-clamp-2 text-lg font-extrabold text-white">{book.title}</h4>
          <p className="mt-1 truncate text-sm font-semibold text-slate-400">{book.author || 'Unknown author'}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {(book.tags ?? []).map((tag) => (
              <span key={tag} className="rounded-full bg-teal-300/10 px-2.5 py-1 text-xs font-bold text-teal-100">
                {tag}
              </span>
            ))}
          </div>
        </div>
      </div>
      <div className="mt-4">
        <div className="h-2 overflow-hidden rounded-full bg-slate-800">
          <div
            className="h-full rounded-full bg-gradient-to-r from-teal-300 to-ember transition-all"
            style={{ width: `${progress.percent}%` }}
          />
        </div>
        <p className="mt-2 text-xs font-bold text-slate-400">
          {progress.current} / {progress.total || '?'} pages · {progress.percent}%
        </p>
      </div>
      <div className="mt-4 grid grid-cols-3 gap-2">
        <Link href={`/books/${book.id}/edit`} className="btn btn-secondary min-h-10 px-2 py-2 text-xs">
          Edit
        </Link>
        <button
          className="btn btn-danger min-h-10 px-2 py-2 text-xs"
          type="button"
          onClick={() => onDelete(book.id)}
        >
          Delete
        </button>
        <Link href={`/books/${book.id}`} className="btn btn-primary min-h-10 px-2 py-2 text-xs">
          Details
        </Link>
      </div>
    </article>
  );
}
