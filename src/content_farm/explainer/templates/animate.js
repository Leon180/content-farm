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

  const effects = (recipes[kind] || recipes.fade_in)();
  const duration = Math.max(...effects.map((e) => e.duration));

  window.__anim = {
    kind,
    duration,
    seek(t) { effects.forEach((e) => e.apply(Math.min(t, duration + 1))); return true; },
  };
})();
