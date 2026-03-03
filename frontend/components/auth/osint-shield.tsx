"use client"

export function OsintShield({ className = "", size = 40 }: { className?: string; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-hidden="true"
    >
      <path
        d="M32 4L8 16V32C8 46.4 18.4 59.2 32 62C45.6 59.2 56 46.4 56 32V16L32 4Z"
        fill="none"
        stroke="#00b4d8"
        strokeWidth="1.5"
        opacity="0.6"
      />
      <path
        d="M32 8L12 18V32C12 44.2 21 55.4 32 58C43 55.4 52 44.2 52 32V18L32 8Z"
        fill="#0a0a12"
        stroke="#00b4d8"
        strokeWidth="0.6"
        opacity="0.85"
      />
      <circle cx="32" cy="32" r="12" fill="none" stroke="#00b4d8" strokeWidth="1" opacity="0.5" />
      <circle cx="32" cy="32" r="8" fill="none" stroke="#00b4d8" strokeWidth="0.5" opacity="0.3" />
      <line x1="32" y1="18" x2="32" y2="26" stroke="#00b4d8" strokeWidth="1" opacity="0.6" />
      <line x1="32" y1="38" x2="32" y2="46" stroke="#00b4d8" strokeWidth="1" opacity="0.6" />
      <line x1="18" y1="32" x2="26" y2="32" stroke="#00b4d8" strokeWidth="1" opacity="0.6" />
      <line x1="38" y1="32" x2="46" y2="32" stroke="#00b4d8" strokeWidth="1" opacity="0.6" />
      <circle cx="32" cy="32" r="2.4" fill="#00b4d8" opacity="0.9" />
    </svg>
  )
}
