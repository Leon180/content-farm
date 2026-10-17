/*
 * Deterministic entrance animations for explainer slides (v2).
 *
 * Nothing moves on its own: the page stays in its final state until the
 * capturer calls window.__anim.seek(t) with an explicit time in seconds.
 * Every frame is a pure function of t, so frame N always looks the same
 * no matter how slow the screenshot was (no wall-clock recording).
 *
 * After `duration` seconds every element sits at its final state, which is
 * exactly the static slide PNG; the capturer holds that frame to the end.
 */
(function () {
  const clamp = (x) => Math.min(Math.max(x, 0), 1);
  const ease = (x) => 1 - Math.pow(1 - clamp(x), 3);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));
  const kind = document.body.dataset.animation || 'fade_in';
  const STAGGER = 0.28;
  const ITEM = 0.55;

  const parseNumber = (text) => {
    const m = text.match(/^(\D*?)(-?[\d,]*\.?\d+)(.*)$/);
    if (!m) return null;
    const raw = m[2].replace(/,/g, '');
    const decimals = raw.includes('.') ? raw.split('.')[1].length : 0;
    return { prefix: m[1], value: parseFloat(raw), decimals, suffix: m[3], comma: m[2].includes(',') };
  };
  const formatNumber = (n, spec) => {
    let s = n.toFixed(spec.decimals);
    if (spec.comma) s = Number(s).toLocaleString('en-US', { minimumFractionDigits: spec.decimals });
    return spec.prefix + s + spec.suffix;
  };

  // ---- effects: each returns {duration, apply(t)} -------------------------
  const fadeUp = (els, start, opts = {}) => {
    const dy = opts.dy ?? 36;
    return {
      duration: start + Math.max(0, els.length - 1) * STAGGER + ITEM,
      apply(t) {
        els.forEach((el, i) => {
          const p = ease((t - start - i * STAGGER) / ITEM);
          el.style.opacity = String(p);
          el.style.transform = `translateY(${(1 - p) * dy}px)`;
        });
      },
    };
  };

  const grow = (els, start, axis) => {
    els.forEach((el) => { el.style.transformOrigin = axis === 'x' ? 'left center' : 'center bottom'; });
    return {
      duration: start + Math.max(0, els.length - 1) * STAGGER + 0.8,
      apply(t) {
        els.forEach((el, i) => {
          const p = ease((t - start - i * STAGGER) / 0.8);
          el.style.transform = axis === 'x' ? `scaleX(${p})` : `scaleY(${p})`;
          el.style.opacity = String(clamp(p * 3));
        });
      },
    };
  };

  const countUp = (el, start, length) => {
    const spec = el && parseNumber(el.textContent.trim());
    if (!spec) return { duration: 0, apply() {} };
    return {
      duration: start + length,
      apply(t) { el.textContent = formatNumber(spec.value * ease((t - start) / length), spec); },
    };
  };

  const heading = () => fadeUp($$('.heading, .title-main'), 0, { dy: 24 });

  // ---- per-layout recipes --------------------------------------------------
  const recipes = {
    count_up() {
      const value = document.querySelector('.bignum .value');
      return [heading(), countUp(value, 0.2, 1.6), fadeUp($$('.bignum .unit, .bignum .caption'), 1.2)];
    },
    grow_bars() {
      const layout = document.body.className;
      if (layout.includes('layout-compare')) {
        return [heading(), grow($$('.compare .side'), 0.25, 'y'), fadeUp($$('.compare li, .compare .vs'), 0.9)];
      }
      if (layout.includes('layout-bullets')) {
        $$('.bullets li').forEach((li) => li.classList.add('anim-bar'));
        return [heading(), grow($$('.bullets li'), 0.25, 'x')];
      }
      // big_number: a meter under the value fills to the percentage (or full).
      const bignum = document.querySelector('.bignum');
      const spec = parseNumber((document.querySelector('.bignum .value') || {}).textContent || '');
      const unit = ((document.querySelector('.bignum .unit') || {}).textContent || '').trim();
      const pct = spec && unit === '%' ? Math.min(Math.max(spec.value, 0), 100) : 100;
      const meter = document.createElement('div');
      meter.className = 'anim-meter';
      meter.innerHTML = `<div class="anim-meter-fill" style="width:${pct}%"></div>`;
      bignum.querySelector('.value-row').after(meter);
      return [heading(), countUp(document.querySelector('.bignum .value'), 0.2, 1.6),
              grow($$('.anim-meter-fill'), 0.2, 'x'), fadeUp($$('.bignum .caption'), 1.2)];
    },
    reveal_list() {
      const items = $$('.bullets li, .compare .side, .timeline .event');
      return [heading(), fadeUp(items, 0.35)];
    },
    draw_line() {
      const timeline = document.querySelector('.timeline');
      timeline.classList.add('anim-draw');
      const line = document.createElement('div');
      line.className = 'anim-line';
      timeline.prepend(line);
      const events = $$('.timeline .event');
      const drawStart = 0.3, drawLen = 1.8;
      const lineFx = grow([line], drawStart, 'x');
      lineFx.duration = drawStart + drawLen;
      lineFx.apply = (t) => {
        const p = clamp((t - drawStart) / drawLen);
        line.style.transform = `scaleX(${p})`;
        line.style.opacity = '1';
      };
      const tlBox = timeline.getBoundingClientRect();
      const eventFx = {
        duration: drawStart + drawLen + ITEM,
        apply(t) {
          const head = clamp((t - drawStart) / drawLen);
          events.forEach((ev) => {
            const r = ev.getBoundingClientRect();
            const at = (r.left + 30 - tlBox.left) / tlBox.width;  // dot position
            const reached = drawStart + at * drawLen;
            const p = head >= at ? ease((t - reached) / ITEM) : 0;
            ev.style.opacity = String(p);
            ev.style.transform = `translateY(${(1 - p) * 24}px)`;
          });
        },
      };
      return [heading(), lineFx, eventFx];
    },
    fade_in() {
      const quoteParts = $$('.quote > *');
      return [fadeUp(quoteParts.length ? quoteParts : $$('.content > *'), 0.1, { dy: 40 })];
    },
    title_card() {
      const card = $$('.news-card');
      const rule = $$('.news-rule');
      return [fadeUp(card, 0, { dy: 60 }), grow(rule, 0.5, 'x'), fadeUp($$('.news-summary, .news-foot'), 0.8)];
    },
  };

  // ---- narration-cued staging (v3): body[data-cues] = reveal second per unit,
  //      body[data-pulses] = [[second, unit index | -1], ...] emphasis while a picture would hold
  const readJSON = (key) => {
    try { return JSON.parse(document.body.dataset[key] || 'null'); } catch (e) { return null; }
  };
  const cues = readJSON('cues');
  const pulseList = readJSON('pulses') || [];
  const unitEls = () => {
    const layout = document.body.className;
    if (layout.includes('layout-bullets')) return $$('.bullets li');
    if (layout.includes('layout-compare')) return $$('.compare .side');
    if (layout.includes('layout-timeline')) return $$('.timeline .event');
    return [];
  };
  const PULSE = 0.9;
  const pulseTarget = (idx, units) => {
    if (idx >= 0 && units[idx]) return units[idx];
    // the one thing worth pointing at — never the whole page (v3 eval: a full-page glow read as a render error)
    // in priority order (a comma list would return the first match in document order: the heading)
    const order = ['.bignum .value', '.quote .text', '.news-headline', '.timeline', '.content', '.title-main', '.heading'];
    for (const sel of order) {
      const el = document.querySelector(sel);
      if (el) return el;
    }
    return null;
  };
  const pulseFx = (list, units) => {
    const items = list.map(([t, idx]) => ({ t, el: pulseTarget(idx, units), tint: idx >= 0 })).filter((p) => p.el);
    items.forEach((p) => { p.el.style.transformOrigin = p.el.style.transformOrigin || 'center center'; });
    return {
      duration: items.length ? Math.max(...items.map((p) => p.t + PULSE)) : 0,
      windows: items.map((p) => [p.t, p.t + PULSE]),
      apply(t) {
        const bump = new Map();
        const tinted = new Set(items.filter((p) => p.tint).map((p) => p.el));
        items.forEach((p) => {
          const x = (t - p.t) / PULSE;
          if (x >= 0 && x <= 1) bump.set(p.el, Math.max(bump.get(p.el) || 0, Math.sin(Math.PI * x)));
          else if (!bump.has(p.el)) bump.set(p.el, 0);
        });
        bump.forEach((b, el) => {
          // strong enough to read as "something happened" on a phone (v3: 0.05 scale alone was invisible);
          // a list item gets a tint, a headline / big number only scales with a tight glow
          el.style.scale = String(1 + 0.08 * b);
          el.style.filter = b > 0 ? `drop-shadow(0 0 ${Math.round(14 * b)}px var(--accent, #f5a524))` : '';
          el.style.backgroundColor = b > 0 && tinted.has(el) ? `rgba(245, 165, 36, ${(0.22 * b).toFixed(3)})` : '';
        });
      },
    };
  };
  const cuedReveal = (units) => {
    const times = units.map((_, i) => (cues[i] ?? cues[cues.length - 1] ?? 0.4));
    return {
      duration: Math.max(0, ...times) + ITEM,
      windows: times.map((t) => [t, t + ITEM + 0.45]),
      apply(t) {
        const shown = times.filter((c) => t >= c).length;
        units.forEach((el, i) => {
          const p = ease((t - times[i]) / ITEM);
          // the unit being talked about is full strength; earlier ones step back a little
          const later = times[i + 1] !== undefined ? ease((t - times[i + 1]) / 0.45) : 0;
          const focus = i < shown - 1 ? 1 - 0.32 * later : 1;
          el.style.opacity = String(p * focus);
          el.style.transform = `translateY(${(1 - p) * 30}px)`;
        });
      },
    };
  };

  const baseEffects = (recipes[kind] || recipes.fade_in)();
  const units = cues ? unitEls() : [];
  const staged = cues && units.length ? [heading(), cuedReveal(units)] : null;
  const effects = [...(staged || baseEffects), ...(pulseList.length ? [pulseFx(pulseList, units)] : [])];
  if (staged && kind === 'draw_line') effects.push(baseEffects[1]);  // keep the timeline rule drawing
  const duration = Math.max(...effects.map((e) => e.duration));
  const entrance = Math.max(...(staged || baseEffects).map((e) => (e.windows ? 0 : e.duration)), 0);
  const windows = [[0, entrance], ...effects.flatMap((e) => e.windows || [])];

  window.__anim = {
    kind,
    duration,
    windows,      // [start, end] spans where something moves; the capturer holds frames between them
    seek(t) { effects.forEach((e) => e.apply(Math.min(t, duration + 1))); return true; },
  };
})();
