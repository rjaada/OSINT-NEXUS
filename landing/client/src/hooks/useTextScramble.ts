import { useEffect, useState, useRef } from "react";

const CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789#@!%&*";

/**
 * Military text scramble effect.
 * Characters cycle through random glyphs, then resolve left-to-right.
 * @param finalText - The text to resolve to
 * @param start     - Trigger to begin. Every time this changes to true, animation replays.
 * @param speed     - Interval ms between frames (default 35ms)
 */
export function useTextScramble(
  finalText: string,
  start: boolean,
  speed = 35
): string {
  const [display, setDisplay] = useState("");
  // Track the current animation run to cancel stale ones
  const runRef = useRef(0);

  useEffect(() => {
    if (!start) return;

    runRef.current += 1;
    const currentRun = runRef.current;

    let frame = 0;
    const framesPerChar = 3;
    const totalFrames = finalText.replace(/ /g, "").length * framesPerChar + 8;

    const id = setInterval(() => {
      // Cancel if a newer run started
      if (runRef.current !== currentRun) {
        clearInterval(id);
        return;
      }

      const resolved = Math.floor(frame / framesPerChar);
      const text = finalText
        .split("")
        .map((char, i) => {
          if (char === " ") return " ";
          if (i < resolved) return char;
          return CHARS[Math.floor(Math.random() * CHARS.length)];
        })
        .join("");

      setDisplay(text);
      frame++;

      if (frame > totalFrames) {
        clearInterval(id);
        setDisplay(finalText);
      }
    }, speed);

    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [start]);   // only re-run when `start` changes identity (toggle trick)

  return display;
}
