export function ClassifiedWatermark() {
  return (
    <div
      className="pointer-events-none absolute inset-0 flex items-center justify-center overflow-hidden"
      aria-hidden="true"
    >
      <div
        className="whitespace-nowrap font-[var(--font-stencil)] text-[120px] font-bold tracking-[0.15em] text-red-official/[0.06]"
        style={{
          transform: "rotate(-32deg)",
          textShadow: "2px 2px 0 rgba(139,0,0,0.02)",
          WebkitTextStroke: "1px rgba(139,0,0,0.04)",
        }}
      >
        CLASSIFIED
      </div>
    </div>
  )
}
