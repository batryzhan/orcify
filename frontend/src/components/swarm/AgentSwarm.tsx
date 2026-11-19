import { useEffect, useMemo, useRef } from "react";

import { AGENTS, DOMAIN_LEADS, SWARM_COLORS } from "../../lib/agents";
import type { Domain, TaskStatus } from "../../types/api";
import { AgentCursorShape } from "../icons";

/** Сколько курсоров в рое (показывается и в нижней плашке). */
export const SWARM_SIZE = 16;
const LEAD_SLOTS = 3;
const TRANSIENT_BOXES = 3;

type Mode = "gather" | "build" | "work" | "drag" | "disperse";

interface AgentSpec {
  id: string;
  name: string | null;
  color: string;
  lead: boolean;
}

interface AgentState {
  x: number;
  y: number;
  vx: number;
  vy: number;
  angle: number;
  seed: number;
  scan: { x: number; y: number; el: Element | null; until: number; boxed: boolean } | null;
}

interface BoxState {
  until: number;
  el: Element | null;
}

interface Props {
  status: TaskStatus | null;
  domain: Domain | null;
  /** CSS-селектор элемента, который «строят» агенты (карточка, превью поста, отчёт). */
  focusSelector: string | null;
  /** Смена значения = рывок роя к элементу (перенос карточки, новый этап). */
  pulse: string | null;
  /** Контейнер, вокруг центра которого рой кружит, пока фокуса нет. */
  scopeSelector: string;
  onFinished: () => void;
}

function rectOf(selector: string): DOMRect | null {
  const el = document.querySelector(selector);
  return el ? el.getBoundingClientRect() : null;
}

function perimeter(r: DOMRect, u: number, offset: number): { x: number; y: number } {
  const w = r.width + offset * 2;
  const h = r.height + offset * 2;
  const total = 2 * (w + h);
  let d = (((u % 1) + 1) % 1) * total;
  const left = r.left - offset;
  const top = r.top - offset;
  if (d < w) return { x: left + d, y: top };
  d -= w;
  if (d < h) return { x: left + w, y: top + d };
  d -= h;
  if (d < w) return { x: left + w - d, y: top + h };
  d -= w;
  return { x: left, y: top + h - d };
}

function lerpAngle(a: number, b: number, t: number): number {
  let diff = ((b - a + Math.PI) % (2 * Math.PI)) - Math.PI;
  if (diff < -Math.PI) diff += 2 * Math.PI;
  return a + diff * t;
}

/**
 * Рой агентов-курсоров (как «swarm of cursors» в редакторах сайтов): пока агенты
 * думают — курсоры кружат вокруг центра окна; когда появляется элемент работы
 * (карточка Jira, превью поста, отчёт) — слетаются к нему и рисуют рамку
 * выделения с размерами; на каждом новом этапе делают рывок к элементу; в работе
 * часть роя «сканирует» окно и выделяет другие элементы. По завершении разлетаются.
 *
 * Позиции считаются в requestAnimationFrame и пишутся прямо в style.transform —
 * без ре-рендеров React на каждый кадр.
 */
export function AgentSwarm({ status, domain, focusSelector, pulse, scopeSelector, onFinished }: Props) {
  const specs = useMemo<AgentSpec[]>(() => {
    const leads = domain ? DOMAIN_LEADS[domain] : ["Router"];
    return Array.from({ length: SWARM_SIZE }, (_, i) => {
      const name = i < LEAD_SLOTS ? (leads[i] ?? null) : null;
      const color = name ? (AGENTS[name]?.color ?? "#1d7afc") : (SWARM_COLORS[i % SWARM_COLORS.length] ?? "#579dff");
      return { id: `a${i}`, name, color, lead: name !== null };
    });
  }, [domain]);

  const agentEls = useRef<(HTMLDivElement | null)[]>([]);
  const boxEls = useRef<(HTMLDivElement | null)[]>([]);
  const state = useRef<AgentState[]>([]);
  const boxes = useRef<BoxState[]>(Array.from({ length: TRANSIENT_BOXES }, () => ({ until: 0, el: null })));
  const mode = useRef<{ kind: Mode; since: number }>({ kind: "gather", since: performance.now() });
  const props = useRef({ focusSelector, scopeSelector, specs });
  props.current = { focusSelector, scopeSelector, specs };
  const finished = useRef(onFinished);
  finished.current = onFinished;

  // Режим роя из событий пайплайна.
  const lastPulse = useRef<string | null>(null);
  useEffect(() => {
    const now = performance.now();
    if (status === "completed" || status === "failed") {
      mode.current = { kind: "disperse", since: now };
      return;
    }
    if (pulse && lastPulse.current && pulse !== lastPulse.current) {
      mode.current = { kind: "drag", since: now };
    } else if (focusSelector && pulse && lastPulse.current === null) {
      mode.current = { kind: "build", since: now };
    } else if (!focusSelector) {
      mode.current = { kind: "gather", since: mode.current.since };
    }
    lastPulse.current = pulse;
  }, [status, focusSelector, pulse]);

  useEffect(() => {
    // Старт из кнопки «Запустить» (или из центра экрана).
    const origin = rectOf("[data-swarm-origin]");
    const ox = origin ? origin.left + origin.width / 2 : window.innerWidth / 2;
    const oy = origin ? origin.top + origin.height / 2 : window.innerHeight * 0.7;
    state.current = Array.from({ length: SWARM_SIZE }, (_, i) => ({
      x: ox + (Math.random() - 0.5) * 30,
      y: oy + (Math.random() - 0.5) * 20,
      vx: (Math.random() - 0.5) * 1.6,
      vy: -0.4 - Math.random() * 1.2,
      angle: -Math.PI / 2,
      seed: (i * 0.618034) % 1,
      scan: null,
    }));

    let raf = 0;
    let last = performance.now();
    let done = false;

    const frame = (now: number) => {
      const dt = Math.min(now - last, 34);
      last = now;
      const { focusSelector: selector, scopeSelector: scope, specs: agents } = props.current;
      let m = mode.current;
      if ((m.kind === "build" && now - m.since > 1900) || (m.kind === "drag" && now - m.since > 1400)) {
        m = mode.current = { kind: "work", since: now };
      }
      const age = now - m.since;
      const boardRect = rectOf(scope);
      const cx = boardRect ? boardRect.left + boardRect.width / 2 : window.innerWidth / 2;
      const cy = boardRect ? boardRect.top + Math.min(boardRect.height, window.innerHeight - boardRect.top) / 2 : window.innerHeight / 2;
      const focus = selector ? rectOf(selector) : null;
      const targets = m.kind === "work" ? document.querySelectorAll("[data-swarm-target]") : null;
      const fade = m.kind === "disperse" ? Math.max(0, 1 - age / 1300) : 1;

      state.current.forEach((a, i) => {
        const spec = agents[i];
        const el = agentEls.current[i];
        if (!spec || !el) return;
        let tx = cx;
        let ty = cy;
        const wobble = spec.lead ? 3 : 7;
        const nx = Math.sin(now * 0.0021 + a.seed * 40) * wobble;
        const ny = Math.cos(now * 0.0017 + a.seed * 27) * wobble;
        let stiffness = spec.lead ? 0.00016 : 0.00009;

        if (m.kind === "disperse") {
          const dir = a.seed * Math.PI * 2;
          tx = cx + Math.cos(dir) * window.innerWidth;
          ty = cy + Math.sin(dir) * window.innerHeight;
          stiffness = 0.00004;
        } else if (m.kind === "gather" || !focus) {
          const r = 46 + (i % 5) * 26 + Math.sin(now * 0.002 + i) * 10;
          const ang = a.seed * Math.PI * 2 + now * 0.0011 * (0.6 + a.seed);
          tx = cx + Math.cos(ang) * r * 1.35;
          ty = cy + Math.sin(ang) * r * 0.8;
        } else if (m.kind === "build" || m.kind === "drag") {
          const tight = m.kind === "drag" ? 4 : 14;
          if (spec.lead && i === 0) {
            tx = focus.left + 18;
            ty = focus.top + 12;
          } else if (spec.lead) {
            tx = focus.right - 8;
            ty = focus.bottom - 8;
          } else {
            const p = perimeter(focus, i / SWARM_SIZE + now * 0.00009, tight);
            tx = p.x;
            ty = p.y;
          }
          if (m.kind === "drag") stiffness *= 2.2;
        } else {
          // work: ведущие у карточки, остальные — сканируют доску.
          const scanner = !spec.lead && i % 3 !== 0;
          if (!scanner) {
            if (spec.lead) {
              tx = focus.left + focus.width * (i === 0 ? 0.3 : 0.75);
              ty = focus.top + focus.height * (i === 1 ? 0.35 : 0.7);
            } else {
              const p = perimeter(focus, i / SWARM_SIZE + now * 0.00006, 12);
              tx = p.x;
              ty = p.y;
            }
          } else {
            if ((!a.scan || now > a.scan.until) && targets && targets.length > 0) {
              const target = targets[Math.floor(Math.random() * targets.length)] ?? null;
              const r = target?.getBoundingClientRect();
              if (target && r && r.width > 0 && r.bottom > 0 && r.top < window.innerHeight) {
                a.scan = {
                  x: r.left + r.width * (0.2 + Math.random() * 0.6),
                  y: r.top + r.height * (0.2 + Math.random() * 0.6),
                  el: target,
                  until: now + 1400 + Math.random() * 1600,
                  boxed: false,
                };
              }
            }
            if (a.scan) {
              tx = a.scan.x;
              ty = a.scan.y;
              const close = Math.hypot(a.x - tx, a.y - ty) < 24;
              if (close && !a.scan.boxed) {
                a.scan.boxed = true;
                const free = boxes.current.find((b) => now > b.until);
                if (free) {
                  free.el = a.scan.el;
                  free.until = now + 900;
                }
              }
            }
          }
        }

        tx += nx;
        ty += ny;
        a.vx += (tx - a.x) * stiffness * dt - a.vx * 0.012 * dt;
        a.vy += (ty - a.y) * stiffness * dt - a.vy * 0.012 * dt;
        a.x += a.vx * dt;
        a.y += a.vy * dt;
        const speed = Math.hypot(a.vx, a.vy);
        if (speed > 0.04) a.angle = lerpAngle(a.angle, Math.atan2(a.vy, a.vx), Math.min(1, dt * 0.012));
        // Острие курсора смотрит в (-135°) — поворачиваем по направлению движения.
        const deg = (a.angle * 180) / Math.PI + 135;
        el.style.transform = `translate3d(${a.x - 2}px, ${a.y - 2}px, 0)`;
        el.style.opacity = String(fade);
        const shape = el.firstElementChild as HTMLElement | null;
        if (shape) shape.style.transform = `rotate(${deg.toFixed(1)}deg)`;
      });

      // Рамка выделения вокруг карточки, которую «строят» агенты.
      const focusBox = boxEls.current[0];
      if (focusBox) {
        if (focus && m.kind !== "disperse" && m.kind !== "gather") {
          placeBox(focusBox, focus, 1);
        } else {
          focusBox.style.opacity = "0";
        }
      }
      boxes.current.forEach((b, i) => {
        const el = boxEls.current[i + 1];
        if (!el) return;
        if (b.el && now < b.until && m.kind === "work") {
          placeBox(el, b.el.getBoundingClientRect(), 1);
        } else {
          el.style.opacity = "0";
        }
      });

      if (m.kind === "disperse" && age > 1400) {
        if (!done) {
          done = true;
          finished.current();
        }
        return;
      }
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, []);

  return (
    <div className="swarm-layer" aria-hidden>
      {Array.from({ length: TRANSIENT_BOXES + 1 }, (_, i) => (
        <div
          key={`box${i}`}
          ref={(el) => {
            boxEls.current[i] = el;
          }}
          className="swarm-box"
          style={{ opacity: 0 }}
        >
          <i />
          <i />
          <i />
          <i />
          <b />
        </div>
      ))}
      {specs.map((spec, i) => (
        <div
          key={spec.id}
          ref={(el) => {
            agentEls.current[i] = el;
          }}
          className="swarm-agent"
          style={{ opacity: 0 }}
        >
          <div style={{ transformOrigin: "2px 2px" }}>
            <AgentCursorShape color={spec.color} />
          </div>
          {spec.name && (
            <span
              className="absolute left-4 top-5 whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-semibold text-white shadow-raised"
              style={{ background: spec.color }}
            >
              {spec.name}
            </span>
          )}
        </div>
      ))}
    </div>
  );
}

function placeBox(el: HTMLDivElement, r: DOMRect, opacity: number) {
  el.style.transform = `translate3d(${r.left - 3}px, ${r.top - 3}px, 0)`;
  el.style.width = `${r.width + 6}px`;
  el.style.height = `${r.height + 6}px`;
  el.style.opacity = String(opacity);
  const label = el.lastElementChild;
  const text = `${Math.round(r.width)} × ${Math.round(r.height)}`;
  if (label && label.textContent !== text) label.textContent = text;
}
