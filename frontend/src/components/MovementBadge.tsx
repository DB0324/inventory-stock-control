import type { MovementKind } from "../types/api";

// Colour plus glyph plus text, never any one alone. A colour-blind user, a
// printed page and a screen reader all need the same information.
//
// Adjustment is amber rather than neutral on purpose: it is the only kind
// that admits the records were wrong, and it should look slightly
// uncomfortable.
const STYLES: Record<MovementKind, { glyph: string; className: string }> = {
  RECEIPT: { glyph: "↑", className: "bg-green-50 text-green-700" },
  ISSUE: { glyph: "↓", className: "bg-blue-50 text-blue-700" },
  TRANSFER: { glyph: "⇄", className: "bg-accent-50 text-accent-700" },
  ADJUSTMENT: { glyph: "⚠", className: "bg-amber-50 text-amber-700" },
};

export default function MovementBadge({ kind }: { kind: MovementKind }) {
  const { glyph, className } = STYLES[kind];
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 text-xs font-medium ${className}`}
    >
      <span aria-hidden>{glyph}</span>
      {kind.charAt(0) + kind.slice(1).toLowerCase()}
    </span>
  );
}