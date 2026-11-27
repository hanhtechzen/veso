/* XS247: loading dùng chung cho mọi trang.
   1) Thanh tiến trình mảnh trên đầu trang: chạy khi trang đang tải, khi bấm sang trang khác trong site
      và khi trang đang gọi API (fetch).
   2) Khung chờ (skeleton): mọi phần tử chỉ chứa chữ "Đang tải…" được thay bằng các vạch mờ chuyển động,
      tự trở lại bình thường khi nội dung thật được điền vào. */
(function () {
  if (window.__lvLoading) return; window.__lvLoading = true;

  var css = '' +
    '#lvBar{position:fixed;top:0;left:0;height:3px;width:0;z-index:3000;pointer-events:none;opacity:0;' +
    'background:linear-gradient(90deg,#FFC233,#FF7A00,#FF2D55);box-shadow:0 0 8px rgba(255,122,0,.6);' +
    'transition:width .3s ease,opacity .25s ease}' +
    '#lvBar.on{opacity:1}' +
    '.lv-skel-host{position:relative;color:transparent!important;min-height:3.2em}' +
    '.lv-skel-host>*{visibility:hidden}' +
    '.lv-skel-host::before{content:"";position:absolute;inset:4px 0;border-radius:8px;' +
    'background:repeating-linear-gradient(180deg,transparent 0 6px,var(--surface,#fff) 6px 18px),' +
    'linear-gradient(90deg,var(--line,#E3E1EE) 25%,color-mix(in srgb,var(--line,#E3E1EE) 40%,#fff) 50%,var(--line,#E3E1EE) 75%);' +
    'background-size:100% 100%,200% 100%;animation:lvSkel 1.2s linear infinite}' +
    '@keyframes lvSkel{from{background-position:0 0,100% 0}to{background-position:0 0,-100% 0}}' +
    '@media (prefers-reduced-motion:reduce){.lv-skel-host::before{animation:none}#lvBar{transition:none}}';
  var st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);

  // ---------- thanh tiến trình ----------
  var bar, pending = 0, timer = null, w = 0;
  function el() { if (!bar) { bar = document.createElement('div'); bar.id = 'lvBar'; bar.setAttribute('aria-hidden', 'true'); (document.body || document.documentElement).appendChild(bar); } return bar; }
  function start() {
    var b = el(); clearInterval(timer); if (!b.classList.contains('on')) { w = 8; b.style.width = w + '%'; b.classList.add('on'); }
    timer = setInterval(function () { w += (90 - w) * 0.08; b.style.width = w + '%'; }, 200);  // tiến dần tới 90%, không bao giờ "đứng"
  }
  function done() {
    var b = el(); clearInterval(timer); b.style.width = '100%';
    setTimeout(function () { b.classList.remove('on'); setTimeout(function () { b.style.width = '0'; }, 250); }, 200);
  }
  function inc() { if (pending++ === 0) start(); }
  function dec() { if (pending > 0 && --pending === 0) done(); }

  // Trang đang tải lần đầu
  if (document.readyState !== 'complete') { inc(); window.addEventListener('load', dec, {once: true}); }

  // Bấm link sang trang khác trong site (không tính link mở tab mới, link neo #, tải file)
  document.addEventListener('click', function (e) {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var a = e.target.closest && e.target.closest('a[href]'); if (!a || a.target === '_blank' || a.hasAttribute('download')) return;
    var u; try { u = new URL(a.href, location.href); } catch (er) { return; }
    if (u.origin !== location.origin) return;
    if (u.pathname === location.pathname && u.search === location.search && u.hash) return;  // chỉ đổi #: không tải trang
    start();
  }, true);
  window.addEventListener('pageshow', function (e) { if (e.persisted) { pending = 0; done(); } });  // quay lại bằng nút Back

  // Đang gọi API: bọc fetch (bỏ qua luồng trực tiếp SSE và gói thống kê truy cập)
  if (window.fetch) {
    var of = window.fetch;
    window.fetch = function (input, init) {
      var url = typeof input === 'string' ? input : (input && input.url) || '';
      if (/\/v1\/(live\/stream|t)(\?|$)/.test(url)) return of.apply(this, arguments);
      inc();
      return of.apply(this, arguments).then(function (r) { dec(); return r; }, function (er) { dec(); throw er; });
    };
  }

  // ---------- khung chờ ----------
  var WAIT = /^Đang tải(…|\.\.\.)?$/;
  function mark(node) {
    if (!node || node.nodeType !== 1 || node.classList.contains('lv-skel-host')) return;
    if (!WAIT.test((node.textContent || '').trim()) || node.children.length > 1) return;
    node.classList.add('lv-skel-host'); node.setAttribute('aria-busy', 'true');
    var mo = new MutationObserver(function () {
      if (!WAIT.test((node.textContent || '').trim())) { node.classList.remove('lv-skel-host'); node.removeAttribute('aria-busy'); mo.disconnect(); }
    });
    mo.observe(node, {childList: true, characterData: true, subtree: true});
  }
  function scan(root) {
    (root.querySelectorAll ? root.querySelectorAll('p,div,span,td,section') : []).forEach(function (n) {
      if (n.childElementCount <= 1 && WAIT.test((n.textContent || '').trim())) mark(n.childElementCount === 1 && WAIT.test(n.firstElementChild.textContent.trim()) ? n.firstElementChild : n);
    });
  }
  function boot() {
    scan(document);
    new MutationObserver(function (ms) { ms.forEach(function (m) { m.addedNodes.forEach(function (n) { if (n.nodeType === 1) { mark(n); scan(n); } }); }); })
      .observe(document.body, {childList: true, subtree: true});
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();

  // ---------- thông báo nổi (toast) dùng chung ----------
  // lvToast('Đã tạo vé thử', 'ok' | 'err' | 'info', {action: {label, href}}) — hiện góc dưới, tự ẩn sau 4,5 giây (lỗi: 7 giây).
  var tcss = '#lvToasts{position:fixed;left:50%;bottom:max(18px,env(safe-area-inset-bottom));transform:translateX(-50%);z-index:3100;' +
    'display:flex;flex-direction:column;gap:8px;width:min(440px,calc(100vw - 32px));pointer-events:none}' +
    '.lv-toast{pointer-events:auto;display:flex;align-items:center;gap:10px;padding:12px 14px;border-radius:14px;color:#fff;' +
    'font:600 .95rem/1.35 "Be Vietnam Pro",system-ui,sans-serif;box-shadow:0 10px 30px rgba(0,0,0,.25);background:#1F7A4D;' +
    'animation:lvTin .25s ease both}' +
    '.lv-toast.err{background:#B42318}.lv-toast.info{background:#2B3553}' +
    '.lv-toast .ic{font-size:1.15rem}.lv-toast .tx{flex:1}' +
    '.lv-toast a{color:#fff;font-weight:800;text-decoration:underline;white-space:nowrap}' +
    '.lv-toast button{background:none;border:0;color:#fff;font-size:1.1rem;cursor:pointer;padding:0 2px;opacity:.85}' +
    '.lv-toast.out{animation:lvTout .25s ease both}' +
    '@keyframes lvTin{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:none}}' +
    '@keyframes lvTout{to{opacity:0;transform:translateY(12px)}}' +
    '@media (max-width:600px){#lvToasts{bottom:calc(78px + env(safe-area-inset-bottom))}}' +  // trên nút nổi "Dò vé"
    '@media (prefers-reduced-motion:reduce){.lv-toast,.lv-toast.out{animation:none}}';
  var ts = document.createElement('style'); ts.textContent = tcss; document.head.appendChild(ts);
  var ICON = {ok: '✅', err: '⚠️', info: 'ℹ️'};
  window.lvToast = function (msg, kind, opt) {
    kind = kind || 'ok'; opt = opt || {};
    var box = document.getElementById('lvToasts');
    if (!box) { box = document.createElement('div'); box.id = 'lvToasts'; box.setAttribute('role', 'status'); box.setAttribute('aria-live', 'polite'); document.body.appendChild(box); }
    var t = document.createElement('div'); t.className = 'lv-toast ' + kind;
    var ic = document.createElement('span'); ic.className = 'ic'; ic.setAttribute('aria-hidden', 'true'); ic.textContent = ICON[kind] || '';
    var tx = document.createElement('span'); tx.className = 'tx'; tx.textContent = msg;
    t.appendChild(ic); t.appendChild(tx);
    if (opt.action && opt.action.label) {
      var a = document.createElement('a'); a.textContent = opt.action.label; a.href = opt.action.href || '#';
      if (opt.action.onClick) a.addEventListener('click', function (e) { e.preventDefault(); opt.action.onClick(); close(); });
      t.appendChild(a);
    }
    var x = document.createElement('button'); x.type = 'button'; x.setAttribute('aria-label', 'Đóng'); x.textContent = '×'; t.appendChild(x);
    function close() { if (!t.parentNode) return; t.classList.add('out'); setTimeout(function () { t.remove(); }, 250); }
    x.addEventListener('click', close);
    box.appendChild(t); while (box.children.length > 3) box.firstElementChild.remove();
    setTimeout(close, opt.ms || (kind === 'err' ? 7000 : 4500));
    return t;
  };

  // lvBusy(nút, 'Đang tạo…'): khóa nút, đổi chữ, trả về hàm khôi phục. Gọi lại khi nút đang bận -> trả null (chặn bấm 2 lần).
  window.lvBusy = function (btn, label) {
    if (!btn || btn.dataset.lvBusy) return null;
    var old = btn.innerHTML; btn.dataset.lvBusy = '1'; btn.disabled = true; btn.setAttribute('aria-busy', 'true');
    if (label) btn.textContent = label;
    return function () { btn.innerHTML = old; btn.disabled = false; btn.removeAttribute('aria-busy'); delete btn.dataset.lvBusy; };
  };

  // lvErr(lỗi, mã HTTP?, body JSON?): câu báo lỗi tiếng Việt dễ hiểu. Chấp nhận Error của fetch (TypeError = mất mạng),
  // đối tượng có .status/.code/.msg/.message, hoặc body dạng {error:{code,message}} của API.
  window.lvErr = function (e, status, body) {
    e = e || {}; status = status || e.status || 0;
    var err = (body && body.error) || (e.body && e.body.error) || {};
    var code = err.code || e.code || '', msg = err.message || e.msg || '';
    if (e instanceof TypeError || /Failed to fetch|NetworkError|Load failed/i.test(e.message || '')) return 'Không kết nối được máy chủ. Kiểm tra mạng rồi thử lại.';
    if (status === 401 || code === 'unauthorized') return 'Phiên đăng nhập đã hết. Hãy đăng nhập lại.';
    if (status === 429 || code === 'rate_limited') return msg || 'Bạn thao tác hơi nhanh, thử lại sau ít phút.';
    if (status >= 500 || e instanceof SyntaxError) return 'Máy chủ đang bận, thử lại sau ít phút.';
    if (code === 'invalid_param') return 'Thông tin chưa hợp lệ, kiểm tra lại rồi thử lại.';
    return msg || (e.message && !/^(HTTP|Lỗi) ?\d|Unexpected token|JSON/.test(e.message) ? e.message : 'Có lỗi xảy ra, thử lại sau.');
  };
})();
