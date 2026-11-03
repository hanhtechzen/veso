// LuckyVision: tô màu bóng số theo hàng chục và đổi tông màu theo miền đang xem.
(function () {
  function setD(b) {
    if (!b || !b.classList || !b.classList.contains('ball') || b.classList.contains('sp') || b.classList.contains('wait')) return;
    var t = (b.textContent || '').trim();
    if (/^\d{2}$/.test(t)) b.dataset.d = t[0]; else delete b.dataset.d;
  }
  function scan(root) { if (root.querySelectorAll) root.querySelectorAll('.ball').forEach(setD); }
  new MutationObserver(function (ms) {
    ms.forEach(function (m) {
      m.addedNodes.forEach(function (n) {
        if (n.nodeType === 1) { setD(n); scan(n); } else if (n.nodeType === 3 && n.parentElement) setD(n.parentElement);
      });
    });
  }).observe(document.body, {childList: true, subtree: true});
  scan(document);
  var map = {mb: 'mb', mn: 'mn', mt: 'mt', vl: 'power', mega: 'mega'};
  function setRegion(r) { document.body.dataset.region = map[r] || r || 'power'; }
  var sel = document.getElementById('region');
  if (sel) { setRegion(sel.value); sel.addEventListener('change', function () { setRegion(sel.value); }); }
  else if (document.querySelector('.side')) setRegion('admin');
  else { var d = new URLSearchParams(location.search).get('draw'); setRegion(d ? d.split('-')[0] : 'power'); }
})();
