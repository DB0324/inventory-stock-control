import { useState } from "react";

import type { WeeklyVolume } from "../types/api";

/** Receipts and issues per week (goal 8).
 *
 * Grouped bars rather than lines: eight weekly buckets are discrete periods,
 * not a continuous signal, and a line implies you could read a value between
 * two Mondays.
 *
 * Two series on ONE scale. Both are quantities of stock in the same units, so
 * a second axis would be inventing a comparison that is not there -- and a
 * dual-axis chart can be made to show any relationship you like by choosing
 * the scales, which is why it is never the right answer.
 *
 * Hand-drawn SVG rather than a charting library: one chart does not justify
 * 90kB of bundle, and the whole thing is fifty lines.
 */

// Slots 1 and 2 of the validated categorical order. Blue/orange separate for
// every common form of colour blindness (worst-case CVD dE 24.7), which a
// green/red pair -- the obvious choice for in/out -- would not.
const RECEIPTS = "#2a78d6";
const ISSUES = "#eb6834";

export default function WeeklyVolumeChart({ data }: { data: WeeklyVolume[] }) {
  const [hovered, setHovered] = useState<number | null>(null);

  const peak = Math.max(1, ...data.flatMap((w) => [w.receipts, w.issues]));
  const width = 640;
  const height = 200;
  const padding = { top: 8, right: 8, bottom: 28, left: 40 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;

  const slot = plotWidth / data.length;
  const barWidth = Math.min(14, (slot - 6) / 2);

  const y = (value: number) => plotHeight - (value / peak) * plotHeight;

  function label(week: string) {
    const date = new Date(week);
    return `${date.getDate()}/${date.getMonth() + 1}`;
  }

  return (
    <div>
      {/* A legend is always present for two or more series -- identity must
          never rest on colour alone. */}
      <div className="mb-2 flex gap-4 text-xs text-zinc-600">
        <span className="flex items-center gap-1.5">
          <span
            className="inline-block h-2.5 w-2.5 rounded-sm"
            style={{ background: RECEIPTS }}
          />
          Received
        </span>
        <span className="flex items-center gap-1.5">
          <span
            className="inline-block h-2.5 w-2.5 rounded-sm"
            style={{ background: ISSUES }}
          />
          Issued
        </span>
      </div>

      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="w-full min-w-[32rem]"
          role="img"
          aria-label="Stock received and issued per week over the last eight weeks"
        >
          <g transform={`translate(${padding.left},${padding.top})`}>
            {/* Recessive gridlines: present enough to read a value against,
                quiet enough not to compete with the bars. */}
            {[0, 0.5, 1].map((fraction) => (
              <g key={fraction}>
                <line
                  x1={0}
                  x2={plotWidth}
                  y1={y(peak * fraction)}
                  y2={y(peak * fraction)}
                  stroke="#e4e4e7"
                  strokeWidth={1}
                />
                <text
                  x={-8}
                  y={y(peak * fraction) + 4}
                  textAnchor="end"
                  className="fill-zinc-400 text-[10px] tabular-nums"
                >
                  {Math.round(peak * fraction)}
                </text>
              </g>
            ))}

            {data.map((week, index) => {
              const x = index * slot;
              const active = hovered === index;
              return (
                <g key={week.week}>
                  {/* One wide hit target per week rather than per bar: the
                      bars are 14px and a pointer should not have to be
                      precise to read a tooltip. */}
                  <rect
                    x={x}
                    y={0}
                    width={slot}
                    height={plotHeight}
                    fill={active ? "#00000008" : "transparent"}
                    onMouseEnter={() => setHovered(index)}
                    onMouseLeave={() => setHovered(null)}
                  />
                  <rect
                    x={x + slot / 2 - barWidth - 1}
                    y={y(week.receipts)}
                    width={barWidth}
                    height={plotHeight - y(week.receipts)}
                    fill={RECEIPTS}
                    rx={2}
                    pointerEvents="none"
                  />
                  <rect
                    x={x + slot / 2 + 1}
                    y={y(week.issues)}
                    width={barWidth}
                    height={plotHeight - y(week.issues)}
                    fill={ISSUES}
                    rx={2}
                    pointerEvents="none"
                  />
                  <text
                    x={x + slot / 2}
                    y={plotHeight + 16}
                    textAnchor="middle"
                    className="fill-zinc-400 text-[10px] tabular-nums"
                  >
                    {label(week.week)}
                  </text>
                </g>
              );
            })}
          </g>
        </svg>
      </div>

      {/* Values on hover, not printed on every bar -- sixteen numbers on the
          chart would bury the shape they are meant to explain. */}
      <div className="mt-1 h-5 text-xs text-zinc-600">
        {hovered !== null && (
          <span className="tabular-nums">
            Week of {new Date(data[hovered].week).toLocaleDateString()} —{" "}
            received {data[hovered].receipts}, issued {data[hovered].issues},{" "}
            {data[hovered].movements} movements
          </span>
        )}
      </div>
    </div>
  );
}
