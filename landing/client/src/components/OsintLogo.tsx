/**
 * OSINT NEXUS Logo Component
 * Hexagon outline with 4-pointed star (diamond) inside
 * Accepts className, fill, and style props for flexible usage incl. intro animation
 */
import type { CSSProperties } from "react";

interface OsintLogoProps {
  className?: string;
  fill?: string;
  style?: CSSProperties;
}

export default function OsintLogo({ className = "", fill = "currentColor", style }: OsintLogoProps) {
  return (
    <svg
      viewBox="0 0 120 138"
      className={className}
      style={style}
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
    >
      {/* Hexagon outline */}
      <path
        d="M60 4 L108 31 L108 107 L60 134 L12 107 L12 31 Z"
        stroke={fill}
        strokeWidth="7"
        fill="none"
        strokeLinejoin="miter"
      />
      {/* 4-pointed star / sparkle inside */}
      <path
        d="M60 22 C60 22 52 54 20 69 C52 84 60 116 60 116 C60 116 68 84 100 69 C68 54 60 22 60 22 Z"
        fill={fill}
      />
    </svg>
  );
}
