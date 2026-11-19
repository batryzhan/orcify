import { useEffect, useRef, useState } from "react";

function commonPrefix(a: string, b: string): number {
  let i = 0;
  while (i < a.length && i < b.length && a[i] === b[i]) i += 1;
  return i;
}

/** Жаңа мәтінді таңбалап басады (оны агент теріп жатқандай), ортақ префиксінен бастап. */
export function useTypewriter(text: string, active: boolean, msPerChar = 28): { shown: string; typing: boolean } {
  const [shown, setShown] = useState(text);
  const shownRef = useRef(text);

  useEffect(() => {
    if (!active || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      shownRef.current = text;
      setShown(text);
      return;
    }
    let index = commonPrefix(shownRef.current, text);
    const id = window.setInterval(() => {
      index += 1;
      shownRef.current = text.slice(0, index);
      setShown(shownRef.current);
      if (index >= text.length) window.clearInterval(id);
    }, msPerChar);
    return () => window.clearInterval(id);
  }, [text, active, msPerChar]);

  return { shown, typing: shown !== text };
}
