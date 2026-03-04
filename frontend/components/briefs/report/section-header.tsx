interface SectionHeaderProps {
  number: number
  title: string
}

export function SectionHeader({ number, title }: SectionHeaderProps) {
  return (
    <div className="mb-4 flex items-center gap-0">
      <div className="w-1 self-stretch bg-red-official" />
      <h2 className="bg-ink/[0.03] px-4 py-2 font-[var(--font-stencil)] text-base tracking-wide text-ink">
        SECTION {number} — {title}
      </h2>
    </div>
  )
}
