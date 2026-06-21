'use client';

import { createContext, useCallback, useContext, useRef, useState } from 'react';

interface ToastContextValue {
  showToast: (message: string, type?: 'info' | 'error') => void;
}

const ToastContext = createContext<ToastContextValue>({ showToast: () => {} });

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [message, setMessage] = useState('');
  const [visible, setVisible] = useState(false);
  const [isError, setIsError] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showToast = useCallback((msg: string, type: 'info' | 'error' = 'info') => {
    if (timerRef.current) clearTimeout(timerRef.current);
    setMessage(msg);
    setIsError(type === 'error');
    setVisible(true);
    timerRef.current = setTimeout(() => setVisible(false), 3600);
  }, []);

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      {visible && (
        <div
          className={`fixed bottom-5 left-1/2 z-50 w-[calc(100%-2rem)] max-w-md -translate-x-1/2 rounded-xl border px-4 py-3 text-sm font-bold text-white shadow-lift sm:bottom-8 ${
            isError ? 'border-red-400/30 bg-red-950/95' : 'border-teal-300/25 bg-slate-950/95'
          }`}
        >
          {message}
        </div>
      )}
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);
