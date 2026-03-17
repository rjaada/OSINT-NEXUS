/**
 * Radar/Targeting Circle Visualization
 * Design: Anduril Behance reference — concentric ellipses, orbital track, aircraft markers
 * Colors: Black on cream (#F5F4EF), static — no animations
 */

// Aircraft marker data: [x, y, orbitAngle, labelX, labelY, labelAnchor, id]
// Orbit angles computed for CCW motion: tangent = (cy-y, x-cx) normalized → atan2
// Center of orbit ≈ (250, 252)
const MARKERS = [
  { x: 142, y: 162, angle: -52, lx: 158, ly: 150, anchor: "start",  id: "BC-4R312" },
  { x: 365, y: 180, angle:  58, lx: 323, ly: 173, anchor: "end",    id: "AA-9M312" },
  { x: 210, y: 348, angle: 214, lx: 218, ly: 362, anchor: "start",  id: "OE-L5711" },
  { x: 430, y: 358, angle: 116, lx: 388, ly: 373, anchor: "end",    id: "BA-31278" },
  { x:  72, y: 432, angle:-140, lx:  34, ly: 447, anchor: "start",  id: "BA-17534" },
];

export default function RadarVisualization() {
  return (
    <svg
      viewBox="0 0 500 500"
      style={{ width: "100%", maxWidth: "460px" }}
      xmlns="http://www.w3.org/2000/svg"
    >
      {/* ── Background ── */}
      <rect x="0" y="0" width="500" height="500" fill="#F5F4EF" stroke="rgba(0,0,0,0.18)" strokeWidth="1" />

      {/* ── Crosshair lines ── */}
      <line x1="0"   y1="250" x2="500" y2="250" stroke="rgba(0,0,0,0.10)" strokeWidth="0.8" />
      <line x1="250" y1="0"   x2="250" y2="500" stroke="rgba(0,0,0,0.10)" strokeWidth="0.8" />
      <line x1="0"   y1="0"   x2="500" y2="500" stroke="rgba(0,0,0,0.06)" strokeWidth="0.8" />
      <line x1="500" y1="0"   x2="0"   y2="500" stroke="rgba(0,0,0,0.06)" strokeWidth="0.8" />

      {/* ── Concentric ellipses — slightly imperfect for organic feel ── */}
      <ellipse cx="250" cy="250" rx="228" ry="225" stroke="rgba(0,0,0,0.18)" strokeWidth="1.2" fill="none" transform="rotate(-2,250,250)" />
      <ellipse cx="250" cy="250" rx="185" ry="182" stroke="rgba(0,0,0,0.16)" strokeWidth="1"   fill="none" transform="rotate(1,250,250)"  />
      <ellipse cx="250" cy="250" rx="143" ry="140" stroke="rgba(0,0,0,0.15)" strokeWidth="1"   fill="none" transform="rotate(-1.5,250,250)" />
      <ellipse cx="250" cy="250" rx="100" ry="98"  stroke="rgba(0,0,0,0.14)" strokeWidth="0.9" fill="none" transform="rotate(2,250,250)"  />
      <ellipse cx="250" cy="250" rx="58"  ry="56"  stroke="rgba(0,0,0,0.13)" strokeWidth="0.9" fill="none" transform="rotate(-1,250,250)" />

      {/* ── Orbital track — the KEY element, thicker and darker than rings ── */}
      <ellipse cx="250" cy="258" rx="212" ry="196" stroke="rgba(0,0,0,0.56)" strokeWidth="2" fill="none" transform="rotate(12,250,250)" className="orbit-rotate" />

      {/* ── Dotted lines from each marker toward center ── */}
      {MARKERS.map((m) => {
        // Calculate tangent vector to terminate the line exactly at the radius (R=26)
        const dx = 250 - m.x;
        const dy = 250 - m.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        const radius = 26; // Center dot radius + padding
        
        // Stop the line short by `radius`
        const stopX = 250 - (dx / dist) * radius;
        const stopY = 250 - (dy / dist) * radius;

        return (
          <line
            key={`dot-${m.id}`}
            x1={m.x} y1={m.y}
            x2={stopX} y2={stopY}
            stroke="rgba(0,0,0,0.15)"
            strokeWidth="0.8"
            strokeDasharray="3,5"
          />
        );
      })}

      {/* ── Center point: large filled circle + shield icon ── */}
      <circle cx="250" cy="250" r="22" fill="#000000" className="radar-pulse" />
      {/* Shield shape inside center circle */}
      <path
        d="M250,239 L261,243.5 L261,254 Q261,263 250,267 Q239,263 239,254 L239,243.5 Z"
        fill="none"
        stroke="#F5F4EF"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />

      {/* ── Aircraft markers ── */}
      {MARKERS.map((m) => (
        <g key={m.id} transform={`translate(${m.x},${m.y}) rotate(${m.angle})`}>
          {/*
            Airplane silhouette pointing right (+x direction) when angle=0.
            Size ≈ 22px nose-to-tail, 18px wingspan.
          */}
          <path
            d={[
              "M 13,0",          // nose
              "L 4,-2.5",        // upper-right fuselage
              "L 2,-2.5",
              "L -1,-9",         // right wingtip
              "L -5,-8",
              "L -3.5,-2.5",     // right wing root
              "L -8,-3",         // right tail leading
              "L -9,-5",
              "L -11,-5",        // right tail fin
              "L -11,0",
              "L -11,5",         // left tail fin
              "L -9,5",
              "L -8,3",          // left tail trailing
              "L -3.5,2.5",      // left wing root
              "L -5,8",
              "L -1,9",          // left wingtip
              "L 2,2.5",
              "L 4,2.5",         // lower-right fuselage
              "Z",
            ].join(" ")}
            fill="#000000"
          />
        </g>
      ))}

      {/* ── Labels ── */}
      {MARKERS.map((m) => (
        <text
          key={`lbl-${m.id}`}
          x={m.lx}
          y={m.ly}
          fontFamily="'Geist Mono', monospace"
          fontSize="8.5"
          fill="rgba(0,0,0,0.50)"
          letterSpacing="0.6"
          textAnchor={m.anchor as "start" | "end" | "middle" | "inherit"}
        >
          {m.id}
        </text>
      ))}
    </svg>
  );
}
