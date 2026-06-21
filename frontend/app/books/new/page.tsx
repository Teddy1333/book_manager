import Navbar from '@/components/Navbar';
import BookForm from '@/components/BookForm';

export default function NewBookPage() {
  return (
    <div className="min-h-screen pb-12">
      <Navbar showBack backHref="/dashboard" backLabel="Dashboard" />
      <div className="mx-auto max-w-5xl px-4 py-6 sm:py-8">
        <div className="mb-7">
          <p className="text-sm font-bold uppercase tracking-[.22em] text-ember/80">Register or rename</p>
          <h2 className="mt-2 font-display text-4xl font-bold text-white">Add a New Book</h2>
        </div>
        <BookForm />
      </div>
    </div>
  );
}
