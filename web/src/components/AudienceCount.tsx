/** "12 listening", while live. */

export default function AudienceCount({ listeners }: { listeners: number | null }) {
  if (listeners === null) return null;
  return (
    <p className="audience" role="status" aria-live="polite">
      {listeners === 1 ? "1 listening" : `${listeners} listening`}
    </p>
  );
}
