import { useEffect, useRef, useState } from "react";

/**
 * Fires `onReveal` once when the element enters the viewport.
 * Returns a ref to attach to the target element.
 */
export function useScrollReveal<T extends Element>(
  onReveal?: () => void,
  options: IntersectionObserverInit = { threshold: 0.15, rootMargin: "0px 0px -60px 0px" }
) {
  const ref = useRef<T>(null);
  const [revealed, setRevealed] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        setRevealed(true);
        onReveal?.();
        observer.disconnect();
      }
    }, options);

    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return { ref, revealed };
}
