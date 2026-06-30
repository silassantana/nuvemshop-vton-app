(function () {
  if (!window.LS || !window.LS.product) return;

  var W = 'https://nuvemshop-vton-app-production.up.railway.app';

  var img = document.querySelector('.js-product-slide-img');
  var g = img ? img.src : null;
  if (!g) return;

  // Detect FASHN category from product tags
  var tags = (window.LS.product.tags || '').toLowerCase();
  var cat = 'tops';
  if (tags.includes('vestido') || tags.includes('macacão') || tags.includes('one-pieces')) cat = 'one-pieces';
  else if (tags.includes('calça') || tags.includes('short') || tags.includes('saia') || tags.includes('bottom')) cat = 'bottoms';

  var f = document.createElement('iframe');
  f.src = W + '/widget/index.html?garment_url=' + encodeURIComponent(g) + '&category=' + cat;
  f.style.cssText = 'width:100%;height:60px;border:none;border-radius:8px;display:block;margin-bottom:12px;';
  f.setAttribute('sandbox', 'allow-scripts allow-same-origin allow-forms allow-popups allow-camera');

  window.addEventListener('message', function (e) {
    if (e.data && e.data.type === 'resize') f.style.height = e.data.height + 'px';
  });

  function inject() {
    var form = document.querySelector('#product_form');
    if (form) form.parentNode.insertBefore(f, form);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', inject);
  else inject();
})();
