
// ===================== BO CHON NGAY KIEU VIET NAM (ngày/tháng/năm) =====================
// Thay mọi ô <input type="date"> bằng nút hiển thị dd/mm/yyyy và lịch bắt đầu từ thứ Hai.
// Ô gốc vẫn giữ giá trị ISO (yyyy-mm-dd) nên mã cũ đọc và gán .value như bình thường.
(function () {
  const WD = ['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN'];
  const WDFULL = ['Chủ nhật', 'Thứ Hai', 'Thứ Ba', 'Thứ Tư', 'Thứ Năm', 'Thứ Sáu', 'Thứ Bảy'];
  const p2 = n => String(n).padStart(2, '0');
  const toISO = (y, m, d) => y + '-' + p2(m) + '-' + p2(d);
  const parseISO = s => { const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s || ''); return m ? {y: +m[1], m: +m[2], d: +m[3]} : null; };
  const fmt = s => { const p = parseISO(s); return p ? p2(p.d) + '/' + p2(p.m) + '/' + p.y : ''; };
  const dow = s => { const p = parseISO(s); return p ? new Date(Date.UTC(p.y, p.m - 1, p.d)).getUTCDay() : 0; };
  const today = () => { const d = new Date(Date.now() + 7 * 3600e3); return {y: d.getUTCFullYear(), m: d.getUTCMonth() + 1, d: d.getUTCDate()}; };
  const addDays = (iso, k) => { const p = parseISO(iso); const d = new Date(Date.UTC(p.y, p.m - 1, p.d + k)); return toISO(d.getUTCFullYear(), d.getUTCMonth() + 1, d.getUTCDate()); };
  function parseDMY(t) {
    const m = /^\s*(\d{1,2})\s*[\/\-.\s]\s*(\d{1,2})\s*[\/\-.\s]\s*(\d{2,4})\s*$/.exec(t || '');
    if (!m) return null;
    let y = +m[3]; if (y < 100) y += 2000;
    const d = +m[1], mo = +m[2], dt = new Date(Date.UTC(y, mo - 1, d));
    return dt.getUTCMonth() === mo - 1 && dt.getUTCDate() === d ? toISO(y, mo, d) : null;
  }
  const ICON = '<svg class="lvd-ico" viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5" width="18" height="16" rx="3" fill="none" stroke="currentColor" stroke-width="2"/><path d="M3 10h18M8 3v4M16 3v4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><circle cx="8.5" cy="14.5" r="1.4" fill="currentColor"/></svg>';
  let open = null;

  function setVal(inp, iso) {
    inp.value = iso;
    inp.dispatchEvent(new Event('input', {bubbles: true}));
    inp.dispatchEvent(new Event('change', {bubbles: true}));
  }
  function close() { if (open) { open.pop.remove(); if (open.back) open.back.remove(); open.btn.setAttribute('aria-expanded', 'false'); open = null; } }

  function enhance(inp) {
    if (inp.dataset.lvd) return;
    inp.dataset.lvd = '1';
    const wrap = document.createElement('span'); wrap.className = 'lvd';
    const btn = document.createElement('button'); btn.type = 'button'; btn.className = 'lvd-btn';
    btn.setAttribute('aria-haspopup', 'dialog'); btn.setAttribute('aria-expanded', 'false');
    const lab = inp.id && document.querySelector('label[for="' + inp.id + '"]');
    if (lab) { btn.id = inp.id + '-lvd'; lab.htmlFor = btn.id; }
    inp.parentNode.insertBefore(wrap, inp); wrap.appendChild(btn); wrap.appendChild(inp);
    inp.hidden = true; inp.tabIndex = -1;
    const desc = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
    Object.defineProperty(inp, 'value', {configurable: true, get() { return desc.get.call(inp); }, set(v) { desc.set.call(inp, v); paint(); }});
    function paint() {
      const v = inp.value;
      btn.innerHTML = ICON + '<span class="lvd-txt">' + (v ? '<b>' + fmt(v) + '</b><small>' + WDFULL[dow(v)] + '</small>' : '<b class="lvd-ph">dd/mm/yyyy</b><small>Chọn ngày</small>') + '</span>';
      btn.setAttribute('aria-label', (lab ? lab.textContent.trim() + ': ' : '') + (v ? fmt(v) + ', ' + WDFULL[dow(v)] : 'chưa chọn ngày') + '. Bấm để chọn ngày');
    }
    paint();
    btn.addEventListener('click', e => { e.stopPropagation(); if (open && open.inp === inp) { close(); return; } openCal(inp, btn, wrap); });
  }

  function openCal(inp, btn, wrap) {
    close();
    const cur = parseISO(inp.value) || today();
    let vy = cur.y, vm = cur.m, focusIso = inp.value || toISO(cur.y, cur.m, cur.d);
    const pop = document.createElement('div');
    pop.className = 'lvd-pop'; pop.setAttribute('role', 'dialog'); pop.setAttribute('aria-label', 'Chọn ngày');
    // Trên điện thoại: lịch trượt lên từ đáy màn hình, gắn vào body để không bị khung cha giới hạn
    const sheet = window.matchMedia('(max-width: 600px)').matches;
    let back = null;
    if (sheet) { back = document.createElement('div'); back.className = 'lvd-back'; document.body.appendChild(back); document.body.appendChild(pop); pop.classList.add('sheet'); }
    else wrap.appendChild(pop);
    open = {inp, pop, btn, back}; btn.setAttribute('aria-expanded', 'true');
    function render(focus) {
      const start = (new Date(Date.UTC(vy, vm - 1, 1)).getUTCDay() + 6) % 7, days = new Date(Date.UTC(vy, vm, 0)).getUTCDate();
      const marks = window.lvDateMarks ? window.lvDateMarks(inp, vy, vm) : null;
      const t = today(), ti = toISO(t.y, t.m, t.d), sel = inp.value;
      let cells = ''; for (let i = 0; i < start; i++) cells += '<span></span>';
      for (let d = 1; d <= days; d++) {
        const iso = toISO(vy, vm, d), c = ['lvd-day'];
        if (iso === sel) c.push('sel'); if (iso === ti) c.push('today'); if (marks && marks.has(iso)) c.push('has');
        cells += '<button type="button" class="' + c.join(' ') + '" data-iso="' + iso + '" tabindex="' + (iso === focusIso ? 0 : -1) + '" aria-label="' + WDFULL[dow(iso)] + ' ' + p2(d) + '/' + p2(vm) + '/' + vy +
          (marks && marks.has(iso) ? ', có kết quả' : '') + '"' + (iso === sel ? ' aria-pressed="true"' : '') + '>' + d + '</button>';
      }
      pop.innerHTML = '<div class="lvd-head"><button type="button" class="lvd-nav" data-m="-1" aria-label="Tháng trước">‹</button><b>Tháng ' + vm + ', ' + vy + '</b>' +
        '<button type="button" class="lvd-nav" data-m="1" aria-label="Tháng sau">›</button></div>' +
        '<div class="lvd-wd">' + WD.map(w => '<span>' + w + '</span>').join('') + '</div><div class="lvd-grid">' + cells + '</div>' +
        '<div class="lvd-foot"><input type="text" class="lvd-type" inputmode="numeric" maxlength="10" placeholder="dd/mm/yyyy" aria-label="Gõ ngày theo ngày/tháng/năm" value="' + fmt(sel) + '">' +
        '<button type="button" class="lvd-today">Hôm nay</button></div>' + (marks ? '<div class="lvd-legend"><i></i>Ngày có kết quả</div>' : '');
      if (focus) { const b = pop.querySelector('[data-iso="' + focusIso + '"]') || pop.querySelector('.lvd-day'); if (b) b.focus(); }
    }
    function go(iso) { const p = parseISO(iso); focusIso = iso; if (p.y !== vy || p.m !== vm) { vy = p.y; vm = p.m; } render(true); }
    render(true);
    pop.addEventListener('click', e => {
      e.stopPropagation();
      const n = e.target.closest('[data-m]');
      if (n) { vm += +n.dataset.m; if (vm < 1) { vm = 12; vy--; } if (vm > 12) { vm = 1; vy++; } focusIso = toISO(vy, vm, 1); render(false); return; }
      const d = e.target.closest('[data-iso]');
      if (d) { setVal(inp, d.dataset.iso); close(); btn.focus(); return; }
      if (e.target.closest('.lvd-today')) { const t = today(); setVal(inp, toISO(t.y, t.m, t.d)); close(); btn.focus(); }
    });
    pop.addEventListener('keydown', e => {
      if (e.key === 'Escape') { e.preventDefault(); close(); btn.focus(); return; }
      if (e.target.classList.contains('lvd-type')) {
        if (e.key === 'Enter') { const iso = parseDMY(e.target.value); if (iso) { setVal(inp, iso); close(); btn.focus(); } else e.target.classList.add('bad'); }
        return;
      }
      const d = e.target.closest('[data-iso]'); if (!d) return;
      const k = {ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7}[e.key];
      if (k) { e.preventDefault(); go(addDays(d.dataset.iso, k)); }
      if (e.key === 'PageUp' || e.key === 'PageDown') { e.preventDefault(); const p = parseISO(d.dataset.iso); const mm = p.m + (e.key === 'PageUp' ? -1 : 1);
        const y = mm < 1 ? p.y - 1 : mm > 12 ? p.y + 1 : p.y, m = (mm + 11) % 12 + 1; go(toISO(y, m, Math.min(p.d, new Date(Date.UTC(y, m, 0)).getUTCDate()))); }
    });
    pop.addEventListener('input', e => {
      if (!e.target.classList.contains('lvd-type')) return;
      let v = e.target.value.replace(/\D/g, '').slice(0, 8);
      if (v.length > 4) v = v.slice(0, 2) + '/' + v.slice(2, 4) + '/' + v.slice(4); else if (v.length > 2) v = v.slice(0, 2) + '/' + v.slice(2);
      e.target.value = v; e.target.classList.remove('bad');
      const iso = v.length === 10 && parseDMY(v);
      if (iso) { const p = parseISO(iso); vy = p.y; vm = p.m; focusIso = iso; render(false); const t = pop.querySelector('.lvd-type'); t.value = v; t.focus(); }
    });
  }
  document.addEventListener('click', e => { if (open && !open.pop.contains(e.target) && !open.btn.contains(e.target)) close(); });
  function scan(root) { (root || document).querySelectorAll('input[type="date"]').forEach(enhance); }
  window.lvDateEnhance = scan;
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => scan()); else scan();
  new MutationObserver(ms => { for (const m of ms) for (const n of m.addedNodes) if (n.nodeType === 1) { if (n.matches && n.matches('input[type="date"]')) enhance(n); else if (n.querySelectorAll) scan(n); } })
    .observe(document.documentElement, {childList: true, subtree: true});
})();
