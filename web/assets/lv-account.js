// LuckyVision: tài khoản người dùng, tỉnh và bộ số yêu thích (dùng chung cho các trang công khai).
(function () {
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var esc = function (s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]; }); };
  function api(method, path, body) {
    return fetch('/v1/user' + path, {method: method, credentials: 'same-origin',
      headers: Object.assign({'X-LV-CSRF': '1'}, body ? {'Content-Type': 'application/json'} : {}), body: body ? JSON.stringify(body) : undefined})
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (d) {
        if (!r.ok) { var e = new Error((d.error && d.error.message) || ('Lỗi ' + r.status)); e.status = r.status; throw e; } return d; }); });
  }
  function toLogin() { location.href = '/dang-nhap?next=' + encodeURIComponent(location.pathname + location.search); }
  function nextUrl() { var n = new URLSearchParams(location.search).get('next'); return n && n.charAt(0) === '/' && n.charAt(1) !== '/' ? n : '/tai-khoan'; }
  var ME = null;

  function paintHeader() {
    var a = $('#acct'); if (!a) return;
    if (ME && ME.user) { a.textContent = ME.user.display_name; a.href = '/tai-khoan'; a.classList.add('in'); }
    document.querySelectorAll('[data-fav-province]').forEach(function (b) {
      var on = !!(ME && ME.favorites && ME.favorites.provinces.some(function (p) { return p.code === b.dataset.favProvince; }));
      b.dataset.on = on ? '1' : ''; b.textContent = on ? '★ Đã lưu' : b.textContent.replace('★ Đã lưu', '☆ Lưu');
      b.setAttribute('aria-pressed', String(on));
    });
  }
  function loadMe() { return api('GET', '/me').then(function (d) { ME = d; paintHeader(); return d; }).catch(function () { ME = {user: null}; }); }

  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-fav-province]');
    if (b) {
      if (!ME || !ME.user) return toLogin();
      var on = b.dataset.on === '1';
      api(on ? 'DELETE' : 'PUT', '/favorites/provinces/' + encodeURIComponent(b.dataset.favProvince)).then(loadMe).catch(function (er) { alert(er.message); });
      return;
    }
    var s = e.target.closest('[data-save-set]');
    if (s) {
      if (!ME || !ME.user) return toLogin();
      api('POST', '/favorites/sets', {kind: s.dataset.kind, scope: s.dataset.scope, numbers: s.dataset.numbers.split(','), label: ''})
        .then(function () { s.textContent = '★ Đã lưu vào Trang của tôi'; s.disabled = true; }).catch(function (er) { alert(er.message); });
    }
  });

  // Đăng nhập, đăng ký
  function bindForm(id, path) {
    var f = $(id); if (!f) return;
    f.addEventListener('submit', function (e) {
      e.preventDefault();
      var data = {}; new FormData(f).forEach(function (v, k) { data[k] = v; });
      var m = $('.msg', f); m.textContent = 'Đang xử lý…'; m.className = 'msg';
      api('POST', path, data).then(function () { location.href = nextUrl(); }).catch(function (er) { m.textContent = er.message; m.className = 'msg bad'; });
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
          (p.draw ? '<p class="hint">' + esc(p.draw.date.split('-').reverse().join('/')) + '</p><p class="mono">' + esc(p.draw.summary) + '</p>' : '<p class="hint">Chưa có kết quả.</p>') + '</div>';
      }).join('') : '<p class="hint">Chưa có đài nào. Thêm ở bên dưới, hoặc bấm “☆ Lưu đài này” trên trang của đài.</p>';
      $('#favSets').innerHTML = d.sets.length ? '<div class="tablewrap"><table class="list"><thead><tr><th>Loại</th><th>Phạm vi</th><th>Các số</th><th>Kỳ mới nhất</th><th></th></tr></thead><tbody>' +
        d.sets.map(function (s) {
          return '<tr><td>' + KIND[s.kind] + (s.label ? '<br><small>' + esc(s.label) + '</small>' : '') + '</td><td>' + esc(scopeName(s.kind, s.scope)) + '</td><td class="mono">' +
            s.numbers.map(function (n) { return '<b' + (s.check && s.check.hits && s.check.hits.indexOf(n) >= 0 ? ' class="hitnum"' : '') + '>' + esc(n) + '</b>'; }).join(' ') + '</td><td>' +
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
    $('#addProvBtn').addEventListener('click', function () { api('PUT', '/favorites/provinces/' + $('#addProv').value).then(renderAccount).catch(function (er) { alert(er.message); }); });
    $('#addSetBtn').addEventListener('click', function () {
      var nums = ($('#setNums').value.match(/\d+/g) || []); var m = $('#setMsg');
      api('POST', '/favorites/sets', {kind: $('#setKind').value, scope: $('#setScope').value, numbers: nums, label: $('#setLabel').value})
        .then(function () { $('#setNums').value = ''; $('#setLabel').value = ''; m.textContent = 'Đã lưu.'; m.className = 'msg good'; renderAccount(); })
        .catch(function (er) { m.textContent = er.message; m.className = 'msg bad'; });
    });
    app.addEventListener('click', function (e) {
      var a = e.target.closest('[data-rm-prov]'); if (a) api('DELETE', '/favorites/provinces/' + a.dataset.rmProv).then(renderAccount);
      var b = e.target.closest('[data-rm-set]'); if (b) api('DELETE', '/favorites/sets/' + b.dataset.rmSet).then(renderAccount);
    });
    $('#pwBtn').addEventListener('click', function () {
      var m = $('#pwMsg');
      api('POST', '/password', {current_password: $('#curPw').value, new_password: $('#newPw').value})
        .then(function () { m.textContent = 'Đã đổi mật khẩu.'; m.className = 'msg good'; $('#curPw').value = $('#newPw').value = ''; if ($('#mustChange')) $('#mustChange').hidden = true; })
        .catch(function (er) { m.textContent = er.message; m.className = 'msg bad'; });
    });
    $('#logoutBtn').addEventListener('click', function () { api('POST', '/logout').then(function () { location.href = '/'; }); });
    $('#delBtn').addEventListener('click', function () {
      var pw = prompt('Xóa tài khoản sẽ xóa luôn tỉnh và bộ số đã lưu. Nhập mật khẩu để xác nhận:'); if (!pw) return;
      api('POST', '/delete', {password: pw}).then(function () { location.href = '/'; }).catch(function (er) { alert(er.message); });
    });
  } else {
    loadMe();
  }
})();
