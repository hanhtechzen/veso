// XS247: đếm lượt xem trang. Không cookie, không lưu IP; tôn trọng "Do Not Track".
(function () {
  if (navigator.doNotTrack === '1' || window.doNotTrack === '1' || navigator.globalPrivacyControl) return;
  var last = '';
  function send() {
    var p = location.pathname + (location.pathname.indexOf('/cong-cu') === 0 && location.hash ? location.hash : '');
    if (p === last) return;
    var ref = last ? '' : document.referrer;  // chỉ tính nguồn ở trang đầu tiên
    last = p;
    var body = JSON.stringify({p: p, r: ref || ''});
    try {
      if (navigator.sendBeacon) navigator.sendBeacon('/v1/t', new Blob([body], {type: 'text/plain'}));
      else fetch('/v1/t', {method: 'POST', body: body, keepalive: true, headers: {'Content-Type': 'text/plain'}});
    } catch (e) {}
  }
  send();
  addEventListener('hashchange', send);
})();
