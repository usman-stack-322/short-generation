import { useEffect, useRef } from 'react';
import { X } from 'lucide-react';

export default function ModalDialog({ open, onClose, title, subtitle, children }) {
  const dialogRef = useRef(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      dialog.showModal();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  if (!open) return null;

  return (
    <dialog
      ref={dialogRef}
      onClose={onClose}
      onClick={(e) => {
        if (e.target === dialogRef.current) onClose();
      }}
      className="m-auto w-full max-w-lg rounded-xl border border-[#22283A] bg-[#131722] p-0 text-[#F8FAFC] shadow-2xl"
    >
      <div className="flex items-start justify-between border-b border-[#22283A] px-6 py-4">
        <div>
          <h3 className="text-base font-semibold text-[#F8FAFC]">{title}</h3>
          {subtitle && <p className="mt-0.5 text-xs text-[#94A3B8]">{subtitle}</p>}
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close modal"
          className="rounded-lg p-1.5 text-[#94A3B8] transition hover:bg-[#1E2434] hover:text-[#F8FAFC]"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="p-6">{children}</div>
    </dialog>
  );
}
