// Карточка белгілерінің түстері (трекерлердегі «лозенждер» сияқты): белгі -> тұрақты түс.
const KNOWN: Record<string, string> = {
  LEGAL: "bg-[#dfd8fd] text-[#5e4db2]",
  FINANCE: "bg-[#baf3db] text-[#216e4e]",
  "AWESOME POSTS": "bg-[#fedec8] text-[#a54800]",
  HR: "bg-[#c6edfb] text-[#206a83]",
  AUTOMATION: "bg-[#e9f2ff] text-[#0055cc]",
  FRONTEND: "bg-[#fdd0ec] text-[#943d73]",
  PRIVACY: "bg-[#dcfff1] text-[#216e4e]",
  RESEARCH: "bg-[#f8e6a0] text-[#7f5f01]",
  "LOCAL MCP": "bg-[#e9f2ff] text-[#0055cc]",
  "NEEDS INPUT": "bg-[#fff7d6] text-[#a54800]",
  ERROR: "bg-[#ffd5d2] text-[#ae2e24]",
};

const PALETTE = [
  "bg-[#f8e6a0] text-[#7f5f01]",
  "bg-[#fedec8] text-[#a54800]",
  "bg-[#dfd8fd] text-[#5e4db2]",
  "bg-[#c6edfb] text-[#206a83]",
  "bg-[#baf3db] text-[#216e4e]",
  "bg-[#fdd0ec] text-[#943d73]",
];

export function labelClass(label: string): string {
  const known = KNOWN[label.toUpperCase()];
  if (known) return known;
  let hash = 0;
  for (const ch of label) hash = (hash * 33 + ch.charCodeAt(0)) >>> 0;
  return PALETTE[hash % PALETTE.length] ?? PALETTE[0]!;
}
