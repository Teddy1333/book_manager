'use client';

import { useRef, useEffect } from 'react';
import { useToast } from '@/contexts/ToastContext';
import { api } from '@/lib/api';

interface HandwritingCanvasProps {
  bookId: number;
  onNoteAdded: () => void;
}

export default function HandwritingCanvas({ bookId, onNoteAdded }: HandwritingCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const drawing = useRef(false);
  const last = useRef<{ x: number; y: number } | null>(null);
  const { showToast } = useToast();

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d')!;

    const getPoint = (e: PointerEvent) => {
      const rect = canvas.getBoundingClientRect();
      return {
        x: (e.clientX - rect.left) * (canvas.width / rect.width),
        y: (e.clientY - rect.top) * (canvas.height / rect.height),
      };
    };

    const onDown = (e: PointerEvent) => {
      drawing.current = true;
      last.current = getPoint(e);
      canvas.setPointerCapture(e.pointerId);
    };

    const onMove = (e: PointerEvent) => {
      if (!drawing.current || !last.current) return;
      const current = getPoint(e);
      ctx.strokeStyle = '#f8fafc';
      ctx.lineWidth = 4;
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      ctx.beginPath();
      ctx.moveTo(last.current.x, last.current.y);
      ctx.lineTo(current.x, current.y);
      ctx.stroke();
      last.current = current;
    };

    const onUp = () => { drawing.current = false; last.current = null; };

    canvas.addEventListener('pointerdown', onDown);
    canvas.addEventListener('pointermove', onMove);
    canvas.addEventListener('pointerup', onUp);
    canvas.addEventListener('pointercancel', onUp);
    canvas.addEventListener('pointerleave', onUp);

    return () => {
      canvas.removeEventListener('pointerdown', onDown);
      canvas.removeEventListener('pointermove', onMove);
      canvas.removeEventListener('pointerup', onUp);
      canvas.removeEventListener('pointercancel', onUp);
      canvas.removeEventListener('pointerleave', onUp);
    };
  }, []);

  function clearCanvas() {
    const canvas = canvasRef.current;
    if (canvas) canvas.getContext('2d')!.clearRect(0, 0, canvas.width, canvas.height);
  }

  async function convertToText() {
    const canvas = canvasRef.current;
    if (!canvas) return;
    canvas.toBlob(async (blob) => {
      if (!blob) return;
      try {
        await api(`/books/${bookId}/notes/photo?is_handwritten=true`, {
          method: 'POST',
          headers: { 'content-type': 'application/octet-stream' },
          body: await blob.arrayBuffer(),
        });
        clearCanvas();
        showToast('✨ Handwriting converted and saved');
        onNoteAdded();
      } catch (e: unknown) {
        showToast(e instanceof Error ? e.message : 'Conversion failed', 'error');
      }
    }, 'image/png');
  }

  return (
    <div className="space-y-3">
      <canvas
        ref={canvasRef}
        width={960}
        height={420}
        className="block h-48 w-full cursor-crosshair touch-none rounded-xl border border-white/10 bg-slate-950"
      />
      <div className="flex gap-3">
        <button onClick={clearCanvas} type="button" className="btn btn-secondary flex-1">
          Clear
        </button>
        <button onClick={convertToText} type="button" className="btn btn-ai flex-1">
          ✨ Convert to Text
        </button>
      </div>
    </div>
  );
}
