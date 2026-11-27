// XS247: tài khoản người dùng, tỉnh và bộ số yêu thích (dùng chung cho các trang công khai).
(function () {
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var esc = function (s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]; }); };
  function api(method, path, body) {
    return fetch('/v1/user' + path, {method: method, credentials: 'same-origin',
      headers: Object.assign({'X-LV-CSRF': '1'}, body ? {'Content-Type': 'application/json'} : {}), body: body ? JSON.stringify(body) : undefined})
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (d) {
        if (!r.ok) { var e = new Error((d.error && d.error.message) || ('Lỗi ' + r.status)); e.status = r.status; e.body = d; throw e; } return d; }); });
  }
  // Helpers dùng chung có thể thiếu (vd. trang không nạp lv-loading.js): luôn có phương án dự phòng.
  function toast(msg, kind, opt) { if (window.lvToast) window.lvToast(msg, kind, opt); else if (kind === 'err') alert(msg); }
  function busy(btn, label) { return window.lvBusy ? window.lvBusy(btn, label) : (btn ? function () {} : null); }
  function friendly(er) { return window.lvErr ? window.lvErr(er, er && er.status, er && er.body) : ((er && er.message) || 'Có lỗi, hãy thử lại.'); }
  var meP = null;
  function whenMe() { return ME ? Promise.resolve(ME) : (meP || Promise.resolve(ME)); }
  function toLogin() { location.href = '/dang-nhap?next=' + encodeURIComponent(location.pathname + location.search); }
  function nextUrl() { var n = new URLSearchParams(location.search).get('next'); return n && n.charAt(0) === '/' && n.charAt(1) !== '/' ? n : '/tai-khoan'; }
  var ME = null;

  function paintHeader() {
    var a = $('#acct'); if (!a) return;
    if (ME && ME.user) { a.textContent = ME.user.display_name + ' ▾'; a.href = '/tai-khoan'; a.classList.add('signed-in'); acctMenu(a); }
    document.querySelectorAll('[data-fav-province]').forEach(function (b) {
      var on = !!(ME && ME.favorites && ME.favorites.provinces.some(function (p) { return p.code === b.dataset.favProvince; }));
      paintFav(b, on);
    });
  }
  function favLabel(b) {
    if (!b.dataset.label) {
      var t = b.textContent.replace(/^\s*[★☆]\s*/, '').trim();
      if (/^Đang |^Đã /.test(t)) t = b.dataset.favName || 'Theo dõi';
      b.dataset.label = t;
    }
    return b.dataset.label;
  }
  function paintFav(b, on) {
    var l = favLabel(b), onTxt = /^Theo dõi/i.test(l) ? 'Đang theo dõi' + l.slice(8) : 'Đã ' + l.charAt(0).toLowerCase() + l.slice(1);
    b.dataset.on = on ? '1' : ''; b.textContent = on ? '★ ' + onTxt : '☆ ' + l;
    b.setAttribute('aria-pressed', String(on));
  }
  function favName(b) { return b.dataset.name || favLabel(b).replace(/^(Theo dõi|Lưu đài)\s*/i, '').trim() || b.dataset.favProvince; }
  // Menu tài khoản trên thanh đầu trang: bấm tên để mở (Trang của tôi, Vé chơi thử, Đăng xuất)
  function acctMenu(a) {
    if (a.dataset.menu) return; a.dataset.menu = '1';
    a.setAttribute('aria-haspopup', 'menu'); a.setAttribute('aria-expanded', 'false');
    if (!document.getElementById('lvAcctCss')) {
      var st = document.createElement('style'); st.id = 'lvAcctCss';
      st.textContent = '.lv-acct-menu{position:absolute;z-index:2500;min-width:200px;padding:6px;border-radius:14px;background:#fff;color:#141B2D;' +
        'box-shadow:0 12px 32px rgba(26,20,70,.25);border:1px solid #E3E1EE;font:600 .92rem "Be Vietnam Pro",system-ui,sans-serif}' +
        '.lv-acct-menu[hidden]{display:none}.lv-acct-menu a,.lv-acct-menu button{display:block;width:100%;text-align:left;padding:10px 12px;border:0;' +
        'border-radius:10px;background:none;color:inherit;font:inherit;text-decoration:none;cursor:pointer}' +
        '.lv-acct-menu a:hover,.lv-acct-menu button:hover,.lv-acct-menu a:focus-visible,.lv-acct-menu button:focus-visible{background:#F1F0F8;outline:none}' +
        '.lv-acct-menu .who{padding:8px 12px 10px;border-bottom:1px solid #E3E1EE;margin-bottom:4px;font-size:.8rem;color:#5B6578;font-weight:500}' +
        '.lv-acct-menu .out{color:#C0392B}';
      document.head.appendChild(st);
    }
    var m = document.createElement('div'); m.className = 'lv-acct-menu'; m.setAttribute('role', 'menu'); m.hidden = true;
    m.innerHTML = '<div class="who">Đang đăng nhập: <b>' + esc(ME.user.display_name) + '</b></div>' +
      '<a role="menuitem" href="/tai-khoan">Trang của tôi</a><a role="menuitem" href="/choi-thu.html">Vé chơi thử</a>' +
      '<button role="menuitem" type="button" class="out">Đăng xuất</button>';
    document.body.appendChild(m);
    function place() { var r = a.getBoundingClientRect(); m.style.top = (r.bottom + window.scrollY + 6) + 'px';
      m.style.left = Math.max(8, Math.min(r.right - m.offsetWidth, document.documentElement.clientWidth - m.offsetWidth - 8)) + window.scrollX + 'px'; }
    function close() { m.hidden = true; a.setAttribute('aria-expanded', 'false'); }
    a.addEventListener('click', function (e) { e.preventDefault(); m.hidden = !m.hidden; a.setAttribute('aria-expanded', String(!m.hidden)); if (!m.hidden) { place(); m.querySelector('a').focus(); } });
    document.addEventListener('click', function (e) { if (!m.hidden && !m.contains(e.target) && e.target !== a) close(); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !m.hidden) { close(); a.focus(); } });
    window.addEventListener('resize', close);
    m.querySelector('.out').addEventListener('click', function () {
      api('POST', '/logout').catch(function () {}).then(function () { location.reload(); });
    });
  }
  function loadMe() { return api('GET', '/me').then(function (d) { ME = d; paintHeader(); return d; }).catch(function () { ME = {user: null}; }); }

  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-fav-province]');
    if (b) {
      if (b.dataset.lvBusy) return;
      favLabel(b);
      var rel = busy(b, 'Đang lưu…'); if (!rel && window.lvBusy) return;
      var restore = rel || function () {};
      whenMe().then(function () {
        if (!ME || !ME.user) { restore(); return toLogin(); }
        var on = b.dataset.on === '1', nm = favName(b);
        return api(on ? 'DELETE' : 'PUT', '/favorites/provinces/' + encodeURIComponent(b.dataset.favProvince)).then(loadMe).then(function () {
          restore(); paintFav(b, !on);
          var game = /^Theo dõi/i.test(favLabel(b));
          toast(on ? (game ? 'Đã bỏ theo dõi ' : 'Đã bỏ lưu đài ') + nm : (game ? 'Đang theo dõi ' : 'Đã lưu đài ') + nm + ' trong Trang của tôi', on ? 'info' : 'ok', on ? undefined : {action: {label: 'Xem', href: '/tai-khoan'}});
        });
      }).catch(function (er) { restore(); if (er && er.status === 401) return toLogin(); toast(friendly(er), 'err'); });
      return;
    }
    var s = e.target.closest('[data-save-set]');
    if (s) {
      if (s.dataset.lvBusy) return;
      var rel2 = busy(s, 'Đang lưu…'); if (!rel2 && window.lvBusy) return;
      var restore2 = rel2 || function () {};
      whenMe().then(function () {
        if (!ME || !ME.user) { restore2(); return toLogin(); }
        return api('POST', '/favorites/sets', {kind: s.dataset.kind, scope: s.dataset.scope, numbers: s.dataset.numbers.split(','), label: ''})
          .then(function () { restore2(); s.textContent = '★ Đã lưu vào Trang của tôi'; s.disabled = true; toast('Đã lưu bộ số vào trang cá nhân', 'ok', {action: {label: 'Xem', href: '/tai-khoan'}}); });
      }).catch(function (er) { restore2(); if (er && er.status === 401) return toLogin(); toast(friendly(er), 'err'); });
    }
  });

  // Đăng nhập, đăng ký
  function bindForm(id, path) {
    var f = $(id); if (!f) return;
    f.addEventListener('submit', function (e) {
      e.preventDefault();
      var data = {}; new FormData(f).forEach(function (v, k) { data[k] = v; });
      var m = $('.msg', f), btn = $('button[type=submit]', f);
      var restore = busy(btn, path === '/login' ? 'Đang đăng nhập…' : 'Đang tạo tài khoản…'); if (!restore && window.lvBusy) return;
      m.textContent = ''; m.className = 'msg';
      api('POST', path, data).then(function () { location.href = nextUrl(); })
        .catch(function (er) { if (restore) restore(); m.textContent = friendly(er); m.className = 'msg bad'; });
    });
  }
  bindForm('#loginForm', '/login');
  bindForm('#registerForm', '/register');

  // Trang của tôi
  var app = $('#accountApp');
  function scopeOptions(kind) {
    var provs = JSON.parse(app.dataset.provinces), games = JSON.parse(app.dataset.games);
    if (kind === 'pick') return games.map(function (g) { var p = provs.find(function (x) { return x.code === g; }); return [g, p ? p.name : g]; });
    var out = [['mb', 'Miền Bắc'], ['mn', 'Miền Nam (mọi đài)'], ['mt', 'Miền Trung (mọi đài)']];
    provs.filter(function (p) { return p.region_code === 'mn' || p.region_code === 'mt'; }).forEach(function (p) { out.push([p.code, p.name]); });
    return out;
  }
  var KIND = {lo: 'Số lô', pick: 'Bộ số', ticket: 'Số vé'};
  function renderAccount() {
    api('GET', '/dashboard').then(function (d) {
      $('#accHello').textContent = 'Xin chào ' + ME.user.display_name + ' (' + ME.user.email + ').';
      if ($('#mustChange')) $('#mustChange').hidden = !ME.user.must_change_password;
      $('#favProvs').innerHTML = d.provinces.length ? d.provinces.map(function (p) {
        return '<div class="fav"><div class="fav-h"><a href="' + (p.draw && p.draw.url ? esc(p.draw.url) : '#') + '"><b>' + esc(p.name) + '</b></a>' +
          '<button class="linkx" data-rm-prov="' + esc(p.code) + '" aria-label="Bỏ ' + esc(p.name) + '">Bỏ</button></div>' +
          (p.draw ? '<p class="hint">' + esc(p.draw.date.split('-').reverse().join('/')) + '</p>' + (p.draw.numbers && p.draw.numbers.length ? '<div class="rk-nums">' + p.draw.numbers.map(function (x) { return '<span class="rk-n' + (x.sp ? ' sp' : '') + '">' + esc(x.n) + '</span>'; }).join('') + '</div>' : '<p class="mono">' + esc(p.draw.summary) + '</p>') : '<p class="hint">Chưa có kết quả.</p>') + '</div>';
      }).join('') : '<p class="hint">Chưa có đài nào. Thêm ở bên dưới, hoặc bấm “☆ Lưu đài này” trên trang của đài.</p>';
      $('#favSets').innerHTML = d.sets.length ? '<div class="tablewrap"><table class="list"><thead><tr><th>Loại</th><th>Phạm vi</th><th>Các số</th><th>Kỳ mới nhất</th><th></th></tr></thead><tbody>' +
        d.sets.map(function (s) {
          return '<tr><td>' + KIND[s.kind] + (s.label ? '<br><small>' + esc(s.label) + '</small>' : '') + '</td><td>' + esc(scopeName(s.kind, s.scope)) + '</td><td><div class="rk-nums">' +
            s.numbers.map(function (n) { var h = s.check && (s.check.hit_numbers || s.check.hits); return '<span class="rk-n' + (s.kind === 'ticket' ? ' w3' : '') + (h && h.indexOf(n) >= 0 ? ' hi hitnum' : '') + '">' + esc(n) + '</span>'; }).join('') + '</div></td><td>' +
            (s.check ? esc(s.check.text) : '<span class="hint">Chưa có kết quả</span>') + '</td><td><button class="linkx" data-rm-set="' + s.id + '">Xóa</button> ' +
            (s.kind !== 'ticket' ? '<a class="linkx" href="/so-sanh?so=' + s.numbers.join(',') + '&pham-vi=' + encodeURIComponent(s.scope) + '">So sánh</a>' : '') + '</td></tr>';
        }).join('') + '</tbody></table></div>' : '<p class="hint">Chưa có bộ số nào.</p>';
    }).catch(function (er) { if (er.status === 401) toLogin(); else $('#accHello').textContent = er.message; });
  }
  function scopeName(kind, code) { var o = scopeOptions(kind).find(function (x) { return x[0] === code; }); return o ? o[1] : code; }
  function fillScope() { $('#setScope').innerHTML = scopeOptions($('#setKind').value).map(function (o) { return '<option value="' + esc(o[0]) + '">' + esc(o[1]) + '</option>'; }).join(''); }
  if (app) {
    loadMe().then(function () {
      if (!ME || !ME.user) return toLogin();
      var provs = JSON.parse(app.dataset.provinces);
      $('#addProv').innerHTML = provs.map(function (p) { return '<option value="' + esc(p.code) + '">' + esc(p.name) + '</option>'; }).join('');
      fillScope(); renderAccount();
    });
    $('#setKind').addEventListener('change', fillScope);
    function failToast(er) { if (er && er.status === 401) return toLogin(); toast(friendly(er), 'err'); }
    $('#addProvBtn').addEventListener('click', function () {
      var sel = $('#addProv'), code = sel.value, nm = sel.options[sel.selectedIndex] ? sel.options[sel.selectedIndex].text : code;
      if (!code) return;
      if ($('#favProvs').querySelector('[data-rm-prov="' + code.replace(/"/g, '') + '"]')) {
        toast('Đài này đã có trong danh sách', 'info'); return;
      }
      var restore = busy(this, 'Đang thêm…'); if (!restore && window.lvBusy) return;
      api('PUT', '/favorites/provinces/' + encodeURIComponent(code)).then(function () { return loadMe(); }).then(function () { renderAccount(); toast('Đã thêm ' + nm, 'ok'); })
        .catch(failToast).then(function () { if (restore) restore(); });
    });
    $('#addSetBtn').addEventListener('click', function () {
      var nums = ($('#setNums').value.match(/\d+/g) || []); var m = $('#setMsg');
      var restore = busy(this, 'Đang lưu…'); if (!restore && window.lvBusy) return;
      m.textContent = ''; m.className = 'msg';
      api('POST', '/favorites/sets', {kind: $('#setKind').value, scope: $('#setScope').value, numbers: nums, label: $('#setLabel').value})
        .then(function () { $('#setNums').value = ''; $('#setLabel').value = ''; m.textContent = 'Đã lưu.'; m.className = 'msg good'; toast('Đã lưu bộ số', 'ok'); renderAccount(); })
        .catch(function (er) { if (er && er.status === 401) return toLogin(); m.textContent = friendly(er); m.className = 'msg bad'; })
        .then(function () { if (restore) restore(); });
    });
    app.addEventListener('click', function (e) {
      var a = e.target.closest('[data-rm-prov]');
      if (a) { var ra = busy(a, '…'); if (!ra && window.lvBusy) return;
        api('DELETE', '/favorites/provinces/' + encodeURIComponent(a.dataset.rmProv)).then(function () { return loadMe(); }).then(function () { renderAccount(); toast('Đã bỏ đài', 'info'); })
          .catch(function (er) { if (ra) ra(); failToast(er); }); return; }
      var b = e.target.closest('[data-rm-set]');
      if (b) {
        var row = b.closest('tr'), nums = row ? Array.prototype.map.call(row.querySelectorAll('.rk-n'), function (x) { return x.textContent; }).join(' ') : '';
        if (!confirm('Xóa bộ số ' + (nums ? nums + ' ' : '') + '?')) return;
        var rb = busy(b, '…'); if (!rb && window.lvBusy) return;
        api('DELETE', '/favorites/sets/' + encodeURIComponent(b.dataset.rmSet)).then(function () { renderAccount(); toast('Đã xóa', 'ok'); })
          .catch(function (er) { if (rb) rb(); failToast(er); });
      }
    });
    $('#pwBtn').addEventListener('click', function () {
      var m = $('#pwMsg');
      var restore = busy(this, 'Đang đổi…'); if (!restore && window.lvBusy) return;
      m.textContent = ''; m.className = 'msg';
      api('POST', '/password', {current_password: $('#curPw').value, new_password: $('#newPw').value})
        .then(function () { m.textContent = 'Đã đổi mật khẩu.'; m.className = 'msg good'; toast('Đã đổi mật khẩu', 'ok'); $('#curPw').value = $('#newPw').value = ''; if ($('#mustChange')) $('#mustChange').hidden = true; })
        .catch(function (er) { if (er && er.status === 401 && !(er.body && er.body.error && er.body.error.message)) return toLogin(); m.textContent = friendly(er); m.className = 'msg bad'; })
        .then(function () { if (restore) restore(); });
    });
    $('#logoutBtn').addEventListener('click', function () {
      var restore = busy(this, 'Đang thoát…');
      api('POST', '/logout').catch(function () {}).then(function () { location.href = '/'; });
    });
    $('#delBtn').addEventListener('click', openDelete);
  } else {
    meP = loadMe();
  }

  // Hộp xác nhận xóa tài khoản (thay cho prompt() hiện mật khẩu rõ chữ)
  function openDelete() {
    var opener = document.activeElement;
    if (!document.getElementById('lvDelCss')) {
      var st = document.createElement('style'); st.id = 'lvDelCss';
      st.textContent = '.lv-del{border:0;border-radius:16px;padding:22px;max-width:min(420px,92vw);width:100%;box-shadow:0 16px 48px rgba(26,20,70,.35);color:#141B2D;font-family:inherit}' +
        '.lv-del::backdrop{background:rgba(20,27,45,.55)}.lv-del h2{margin:0 0 8px;font-size:1.15rem}.lv-del p{margin:0 0 12px;font-size:.92rem;line-height:1.45}' +
        '.lv-del label{display:block;font-weight:600;font-size:.88rem}.lv-del input{display:block;width:100%;box-sizing:border-box;margin-top:6px;padding:10px 12px;font-size:1rem;border:1px solid #C9C6DC;border-radius:10px}' +
        '.lv-del .acts{display:flex;gap:10px;justify-content:flex-end;margin-top:16px}.lv-del .err{color:#C0392B;font-size:.88rem;min-height:1.2em;margin:8px 0 0}';
      document.head.appendChild(st);
    }
    var d = document.createElement('dialog'); d.className = 'lv-del'; d.setAttribute('aria-labelledby', 'lvDelT');
    d.innerHTML = '<form method="dialog" autocomplete="off"><h2 id="lvDelT">Xóa tài khoản?</h2>' +
      '<p>Việc này sẽ xóa luôn các đài và bộ số bạn đã lưu, và không khôi phục được. Nhập mật khẩu để xác nhận.</p>' +
      '<label>Mật khẩu<input type="password" name="pw" autocomplete="current-password" required></label>' +
      '<p class="err" role="alert"></p><div class="acts"><button type="button" class="btn ghost" data-cancel>Hủy</button>' +
      '<button type="submit" class="btn ghost danger">Xác nhận xóa</button></div></form>';
    document.body.appendChild(d);
    var f = d.firstChild, pw = f.pw, err = $('.err', d), go = $('button[type=submit]', d);
    function close() { if (d.open) d.close(); d.remove(); if (opener && opener.focus) opener.focus(); }
    $('[data-cancel]', d).addEventListener('click', close);
    d.addEventListener('cancel', function (e) { e.preventDefault(); close(); });
    f.addEventListener('submit', function (e) {
      e.preventDefault(); if (!pw.value) { err.textContent = 'Hãy nhập mật khẩu.'; pw.focus(); return; }
      var restore = busy(go, 'Đang xóa…'); if (!restore && window.lvBusy) return;
      err.textContent = '';
      api('POST', '/delete', {password: pw.value}).then(function () { location.href = '/?deleted=1'; })
        .catch(function (er) { if (restore) restore(); err.textContent = friendly(er); pw.select(); });
    });
    if (d.showModal) d.showModal(); else d.setAttribute('open', '');
    pw.focus();
  }

  // Sau khi xóa tài khoản: báo một lần rồi bỏ tham số khỏi địa chỉ
  (function () {
    var q = new URLSearchParams(location.search);
    if (q.get('deleted') !== '1') return;
    toast('Đã xóa tài khoản. Hẹn gặp lại!', 'info');
    q.delete('deleted'); var qs = q.toString();
    history.replaceState(null, '', location.pathname + (qs ? '?' + qs : '') + location.hash);
  })();
})();
