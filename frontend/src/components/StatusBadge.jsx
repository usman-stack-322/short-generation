const STATUS_STYLES = {
  completed: {
    label: 'Completed',
    classes: 'border-[#10B981]/30 bg-[#10B981]/10 text-[#10B981]',
    dot: 'bg-[#10B981]',
  },
  processing: {
    label: 'Processing',
    classes: 'border-[#38BDF8]/30 bg-[#38BDF8]/10 text-[#38BDF8]',
    dot: 'bg-[#38BDF8] animate-pulse',
  },
  failed: {
    label: 'Failed',
    classes: 'border-[#F43F5E]/30 bg-[#F43F5E]/10 text-[#F43F5E]',
    dot: 'bg-[#F43F5E]',
  },
  queued: {
    label: 'Queued',
    classes: 'border-[#F59E0B]/30 bg-[#F59E0B]/10 text-[#F59E0B]',
    dot: 'bg-[#F59E0B] animate-pulse',
  },
};

export default function StatusBadge({ status }) {
  const key = (status || 'queued').toLowerCase();
  const cfg = STATUS_STYLES[key] || STATUS_STYLES.queued;

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${cfg.classes}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${cfg.dot}`} />
      {cfg.label}
    </span>
  );
}
