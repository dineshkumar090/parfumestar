(function () {
  'use strict';


  if (!document.querySelector('script[src*="iconify"]')) {
    var iconifyScript = document.createElement('script');
    iconifyScript.src = 'https://code.iconify.design/3/3.1.0/iconify.min.js';
    document.head.appendChild(iconifyScript);
  }

  // console.log("window.location.pathname", window.location.pathname)
  console.log('[DEBUG] window.location.pathname:', window.location.pathname);

  if (!window.location.pathname.includes("/pages/contact")) {
     return;
  }

  const API_URL = 'https://py.brstdev.com:5008';
  const STORE_URL = window.location.origin;
  const shop = window.Shopify?.shop || window.location.hostname;
  //   const customer = window.ShopifyCustomer || { id: null, email: null };
  // console.log("customer::::::::::::",customer);

  var customerData = window.AlchemistCustomer || {};
  var customer = {
    id: customerData.customer_id || null,
    email: customerData.customer_email || null,
  };
  console.log("customer::::::::::::", customer);


  // ══════════════════════════════════════════════════════════════════════════
  //  UUID & DEVICE HELPERS
  // ══════════════════════════════════════════════════════════════════════════

  function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
      var r = Math.random() * 16 | 0;
      return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
    });
  }


  function renderIcon(iconName, size = 20) {
    if (!iconName) return '💬';

    // If it's already an emoji or text, return as is
    if (!iconName.startsWith('mdi:')) {
      return iconName;
    }

    // Create an Iconify icon
    var span = document.createElement('span');
    span.className = 'iconify';
    span.setAttribute('data-icon', iconName);
    span.setAttribute('data-width', String(size));
    span.setAttribute('data-height', String(size));
    span.style.display = 'inline-block';
    span.style.verticalAlign = 'middle';
    return span.outerHTML;
  }

  function getUserUUID() {
    if (customer.id) return null;
    var uid = localStorage.getItem('alchemist_user_uuid');
    if (!uid) { uid = generateUUID(); localStorage.setItem('alchemist_user_uuid', uid); }
    return uid;
  }

  function getDeviceInfo() {
    var ua = navigator.userAgent;
    var device = 'desktop';
    if (/Mobi|Android/i.test(ua)) device = 'mobile';
    else if (/Tablet|iPad/i.test(ua)) device = 'tablet';
    var browser = 'unknown';
    if (/Edg\//.test(ua)) browser = 'Edge';
    else if (/Chrome\//.test(ua) && !/Chromium/.test(ua)) browser = 'Chrome';
    else if (/Firefox\//.test(ua)) browser = 'Firefox';
    else if (/Safari\//.test(ua) && !/Chrome/.test(ua)) browser = 'Safari';
    var os = 'unknown';
    if (/Windows/.test(ua)) os = 'Windows';
    else if (/iPhone|iPad/.test(ua)) os = 'iOS';
    else if (/Android/.test(ua)) os = 'Android';
    else if (/Mac/.test(ua)) os = 'MacOS';
    else if (/Linux/.test(ua)) os = 'Linux';
    return {
      user_agent: ua, browser, os, device_type: device,
      language: navigator.language || 'unknown',
      screen_resolution: window.screen.width + 'x' + window.screen.height,
      timezone: (Intl && Intl.DateTimeFormat
        ? Intl.DateTimeFormat().resolvedOptions().timeZone : 'unknown'),
    };
  }

  var userUUID = getUserUUID();
  var currentThreadUUID = null;
  var widgetBuilt = false;

  // ══════════════════════════════════════════════════════════════════════════
  //  STORE DOMAIN FROM SHOP
  // ══════════════════════════════════════════════════════════════════════════

  function getStoreDisplayDomain() {
    var domain = shop.replace('.myshopify.com', '');
    return domain.charAt(0).toUpperCase() + domain.slice(1);
  }

  // ══════════════════════════════════════════════════════════════════════════
  //  LANGUAGE STRINGS (EN / FR)
  // ══════════════════════════════════════════════════════════════════════════

  var STRINGS = {
    fr: {
      greeting: "👋 Bonjour ! Je suis votre assistant shopping. Comment puis-je vous aider aujourd'hui ?",
      buttonText: 'Une question ?',
      placeholder: 'Posez une question sur nos produits...',
      addedToCart: function (name) { return '✓ ' + name + ' ajouté au panier'; },
      addToCartError: function (msg) { return 'Erreur : ' + msg; },
      added: '✓ Ajouté !',
      failed: 'Échec',
      genericError: 'Erreur',
      productNotIdentified: 'Erreur : produit introuvable',
      variantNotFound: 'Erreur : variante introuvable',
      rateLimited: "Vous envoyez des messages trop rapidement — merci de patienter un instant. 🙏",
      accessDenied: 'Accès refusé. Merci de rafraîchir la page ou de nous contacter.',
      genericChatError: "Désolé, une erreur s'est produite. Merci de réessayer.",
      connectionError: 'Désolé, problème de connexion. Merci de réessayer dans un instant.',
    },
    en: {
      greeting: "👋 Hi! I'm your shopping assistant. How can I help you today?",
      buttonText: 'Ask me anything!',
      placeholder: 'Ask about products...',
      addedToCart: function (name) { return '✓ Added ' + name + ' to cart'; },
      addToCartError: function (msg) { return 'Error: ' + msg; },
      added: '✓ Added!',
      failed: 'Failed',
      genericError: 'Error',
      productNotIdentified: 'Error: Could not identify product',
      variantNotFound: 'Error: Product variant not found',
      rateLimited: "You're sending messages too quickly — please wait a moment. 🙏",
      accessDenied: 'Access denied. Please refresh and try again, or contact us for help.',
      genericChatError: 'Sorry, something went wrong. Please try again.',
      connectionError: 'Sorry, having trouble connecting right now. Please try again shortly.',
    },
  };

  // Business rule: customer interactions default to French; fall back to
  // English only when the browser is explicitly English.
  var lang = (navigator.language || '').toLowerCase().indexOf('en') === 0 ? 'en' : 'fr';
  var t = STRINGS[lang];

  // ══════════════════════════════════════════════════════════════════════════
  //  CONFIG
  // ══════════════════════════════════════════════════════════════════════════

  var cfg = {
    enabled: true,
    greetingMessage: t.greeting,
    windowColor: '#008060',
    brandName: 'AI Assistant',
    headerIcon: '🤖',
    iconStyle: ['iconLabel'],
    iconSize: ['standard'],
    iconShape: ['rounded'],
    desktopPosition: 'bottomRight',
    transparentBg: false,
    buttonText: t.buttonText,
    cartIcon: 'mdi:cart',
    cartEnabled: true,
    quickChips: [

    ],
    selectedPages: ['home', 'product', 'cart', 'checkout', 'contact'],
  };

  function loadConfig() {
    console.log("start api call:::::");
    
    fetch(API_URL + '/api/chat/config?shop=' + encodeURIComponent(shop))
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (remote) {
        cfg.enabled = remote.enabled !== undefined ? remote.enabled : cfg.enabled;
        cfg.greetingMessage = remote.greeting_message || cfg.greetingMessage;
        cfg.windowColor = remote.window_color || cfg.windowColor;
        cfg.brandName = remote.brand_name || cfg.brandName;
        cfg.headerIcon = remote.header_icon || cfg.headerIcon;
        cfg.iconStyle = remote.icon_style || cfg.iconStyle;
        cfg.iconSize = remote.icon_size || cfg.iconSize;
        cfg.iconShape = remote.icon_shape || cfg.iconShape;
        cfg.desktopPosition = remote.desktop_position || cfg.desktopPosition;
        cfg.transparentBg = remote.transparent_bg !== undefined ? remote.transparent_bg : cfg.transparentBg;
        cfg.buttonText = remote.button_text || cfg.buttonText;
        cfg.cartIcon = remote.cart_icon || cfg.cartIcon;
        cfg.cartEnabled = remote.cart_enabled !== undefined ? remote.cart_enabled : cfg.cartEnabled;

        console.log('[DEBUG] Remote config received:', remote);
        console.log('[DEBUG] header_icon from remote:', remote.header_icon);

        cfg.headerIcon = remote.header_icon || cfg.headerIcon;

        console.log('[DEBUG] cfg.headerIcon after assignment:', cfg.headerIcon);

        if (remote.quick_chips && remote.quick_chips.length) {
          cfg.quickChips = remote.quick_chips;
        }

        // Store selected_pages from remote config
        cfg.selectedPages = remote.selected_pages || cfg.selectedPages || [];

        // Rebuild widget with new config if already built
        if (widgetBuilt) {
          rebuildWidget();
        } else {
          buildWidget();
        }

        // Show/hide based on page visibility
        // var container = document.getElementById('shopify-chatbot-container');
        // if (container) {
        //   var shouldShow = cfg.enabled && isPageAllowed(cfg.selectedPages);
        //   container.style.display = shouldShow ? '' : 'none';
        // }
      })
      .catch(function (err) {
        console.warn('[Chatbot] Remote config failed, using defaults.', err);
        if (!widgetBuilt) buildWidget();
      });
  }

  // ══════════════════════════════════════════════════════════════════════════
  //  STYLE HELPERS
  // ══════════════════════════════════════════════════════════════════════════

  var sizeMap = { small: ['10px 14px', 18], standard: ['12px 18px', 20], large: ['16px 22px', 24] };
  var btnSize = function () { return sizeMap[cfg.iconSize && cfg.iconSize[0]] || ['12px 18px', 20]; };
  var btnShape = function () { return cfg.iconShape && cfg.iconShape[0] === 'square' ? '8px' : '999px'; };
  var posMap = {
    bottomRight: { btn: 'bottom:20px;right:20px', win: 'bottom:90px;right:20px' },
    bottomLeft: { btn: 'bottom:20px;left:20px', win: 'bottom:90px;left:20px' },
    centerRight: { btn: 'top:50%;right:20px;transform:translateY(-50%)', win: 'top:50%;right:20px;transform:translateY(-50%)' },
  };
  var pos = function (k) { return (posMap[cfg.desktopPosition] || posMap.bottomRight)[k]; };

  function escHtml(t) {
    if (t === null || t === undefined) return '';
    var d = document.createElement('div');
    d.textContent = String(t);
    return d.innerHTML;
  }

  // ══════════════════════════════════════════════════════════════════════════
  //  INJECT CSS
  // ══════════════════════════════════════════════════════════════════════════

  if (!document.getElementById('chatbot-styles')) {
    var style = document.createElement('style');
    style.id = 'chatbot-styles';
    style.textContent = `
      #shopify-chatbot-container * { box-sizing:border-box; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
      .cb-chip { 
  font-size:12px; 
  padding:5px 12px; 
  border-radius:20px; 
  background:#fff; 
  border:1px solid #b7d4c4; 
  cursor:pointer; 
  color:#2d6a4f; 
  transition:all .15s; 
  user-select:none; 
  white-space:nowrap;
  display:inline-flex;
  align-items:center;
  gap:6px;
}
.cb-chip span:first-child {
  font-size:14px;
}
      .cb-chip:hover { background:#2d6a4f; color:#fff; border-color:#2d6a4f; }
      .cb-card { background:#fff; border:1.5px solid #d0e8da; border-radius:12px; overflow:hidden; cursor:default; transition:all .2s; box-shadow:0 1px 4px rgba(0,0,0,.06); }
      .cb-card:hover { border-color:#2d6a4f; transform:translateY(-2px); box-shadow:0 4px 14px rgba(0,0,0,.1); }
      .cb-img { width:100%; height:115px; object-fit:cover; display:block; background:#f0f7f4; }
      .cb-img-ph { width:100%; height:115px; display:flex; align-items:center; justify-content:center; background:#f0f7f4; font-size:36px; }
      .cb-row { animation:cb-slide .2s ease; }
      @keyframes cb-slide { from{opacity:0;transform:translateY(10px)} to{opacity:1;transform:none} }
      @keyframes cb-pulse { 0%,60%,100%{opacity:.3} 30%{opacity:1} }
      #chatbot-input:focus { border-color:#2d6a4f !important; box-shadow:0 0 0 2.5px rgba(45,106,79,.18) !important; }
      .cb-view-btn:hover { filter:brightness(1.1) !important; }
      .cb-ask-btn:hover  { background:#dff0e8 !important; }
      ::-webkit-scrollbar{width:5px} ::-webkit-scrollbar-thumb{background:#c0d8c8;border-radius:4px}
      #cb-history-panel { position:absolute; inset:0; background:#fff; z-index:10; display:none; flex-direction:column; border-radius:18px; overflow:hidden; }
      .cb-history-item { padding:12px 16px; border-bottom:1px solid #e8f4ed; cursor:pointer; transition:background .15s; display:flex; gap:10px; align-items:flex-start; }
      .cb-history-item:hover { background:#f0f7f4; }
      .cb-history-item:last-child { border-bottom:none; }
      .cb-new-chat-btn { background:#2d6a4f; color:#fff; border:none; border-radius:8px; padding:9px 16px; cursor:pointer; font-size:13px; font-weight:700; transition:filter .15s; width:100%; }
      .cb-new-chat-btn:hover { filter:brightness(1.1); }
      .cb-hdr-icon-btn { background:none; border:none; color:#fff; cursor:pointer; padding:5px; opacity:.8; font-size:18px; border-radius:6px; transition:all .15s; line-height:1; }
      .cb-hdr-icon-btn:hover { opacity:1; background:rgba(255,255,255,.15); }
      .cb-contact-btn { 
  display:inline-flex; align-items:center; gap:6px; margin-top:10px;
  background:#fff; color:#2d6a4f; border:1.5px solid #2d6a4f;
  font-size:12px; padding:7px 14px; border-radius:20px; cursor:pointer;
  font-weight:700; text-decoration:none; transition:all .15s;
  box-shadow:0 1px 4px rgba(0,0,0,.08);
}
.cb-contact-btn:hover { background:#2d6a4f; color:#fff; }
      @media (max-width:520px) {
        #chatbot-window { width:100% !important; height:100% !important; max-height:100svh !important; bottom:0 !important; right:0 !important; left:0 !important; top:0 !important; border-radius:0 !important; transform:none !important; }
        #chatbot-toggle { bottom:16px !important; right:16px !important; left:auto !important; top:auto !important; transform:none !important; }
        #chatbot-header { padding:12px 14px !important; }
        #chatbot-messages { padding:10px 8px !important; }
        #chatbot-input { font-size:16px !important; }
        .cb-card { border-radius:10px !important; }
      }

       .cart-bump {
        animation: cartBump 0.3s ease-in-out !important;
    }
    
    @keyframes cartBump {
        0% { transform: scale(1); }
        50% { transform: scale(1.15); }
        100% { transform: scale(1); }
    }
    `;
    document.head.appendChild(style);
  }

  // Helper function to render icon HTML (supports both emoji and mdi:)
  function renderIconHtml(iconName, size) {
    if (!iconName) return '🛍️';
    if (iconName.startsWith('mdi:')) {
      return '<span class="iconify" data-icon="' + iconName + '" data-width="' + size + '" data-height="' + size + '" style="display:inline-block;vertical-align:middle;"></span>';
    }
    // Regular emoji or text
    return '<span style="font-size:' + size + 'px;">' + iconName + '</span>';
  }


function injectDynamicStyles() {
  var old = document.getElementById('chatbot-dynamic-styles');
  if (old) old.remove();
  var s = document.createElement('style');
  s.id = 'chatbot-dynamic-styles';
  // hex to rgba helper for box-shadow
  var hex = cfg.windowColor.replace('#','');
  var r = parseInt(hex.substring(0,2),16);
  var g = parseInt(hex.substring(2,4),16);
  var b = parseInt(hex.substring(4,6),16);
  s.textContent = [
    '.cb-chip { border-color:' + cfg.windowColor + '55 !important; color:' + cfg.windowColor + ' !important; }',
    '.cb-chip:hover { background:' + cfg.windowColor + ' !important; color:#fff !important; border-color:' + cfg.windowColor + ' !important; }',
    '.cb-card:hover { border-color:' + cfg.windowColor + ' !important; box-shadow:0 4px 14px rgba('+r+','+g+','+b+',.18) !important; }',
    '#chatbot-input:focus { border-color:' + cfg.windowColor + ' !important; box-shadow:0 0 0 2.5px rgba('+r+','+g+','+b+',.2) !important; }',
    '.cb-new-chat-btn { background:' + cfg.windowColor + ' !important; }',
    '.cb-contact-btn { color:' + cfg.windowColor + ' !important; border-color:' + cfg.windowColor + ' !important; }',
    '.cb-contact-btn:hover { background:' + cfg.windowColor + ' !important; color:#fff !important; }',
  ].join('\n');
  document.head.appendChild(s);
}



  // ══════════════════════════════════════════════════════════════════════════
  //  BUILD WIDGET HTML
  // ══════════════════════════════════════════════════════════════════════════

  function buildWidget() {
    // Remove old container if exists
    var oldContainer = document.getElementById('shopify-chatbot-container');
    if (oldContainer) oldContainer.remove();

    var bpBi = btnSize();
    var bp = bpBi[0];
    var bi = bpBi[1];
    var showLabel = cfg.iconStyle && cfg.iconStyle[0] === 'iconLabel';
    var storeDomain = getStoreDisplayDomain();

    // Helper function to render icon HTML (supports both emoji and mdi:)
    function renderIconHtml(iconName, size) {
      if (!iconName) return '💬';
      if (iconName.startsWith('mdi:')) {
        return '<span class="iconify" data-icon="' + iconName + '" data-width="' + size + '" data-height="' + size + '" style="display:inline-block;vertical-align:middle;"></span>';
      }
      // Regular emoji or text
      return '<span style="font-size:' + size + 'px;">' + iconName + '</span>';
    }

    var html = `
  <div id="shopify-chatbot-container">
    <button id="chatbot-toggle" style="
      position:fixed; z-index:999998; display:flex; align-items:center; gap:8px;
      padding:${bp}; border-radius:${btnShape()};
      background:${cfg.transparentBg ? 'transparent' : cfg.windowColor};
      border:${cfg.transparentBg ? '2px solid ' + cfg.windowColor : 'none'};
      color:${cfg.transparentBg ? cfg.windowColor : '#fff'};
      cursor:pointer; transition:all .2s;
      box-shadow:0 4px 16px rgba(0,0,0,.22); font-weight:700; font-size:14px;
      ${pos('btn')};
    ">
       ${renderIconHtml(cfg.headerIcon || '🛍️', bi)}
      ${showLabel ? '<span>' + escHtml(cfg.buttonText || 'Ask me anything!') + '</span>' : ''}
    </button>

    <div id="chatbot-window" style="
      position:fixed; z-index:999999; display:none; flex-direction:column;
      width:392px; height:610px; border-radius:18px; overflow:hidden;
      background:#fff; box-shadow:0 16px 48px rgba(0,0,0,.24); border:1px solid #cce3d4;
      ${pos('win')};
    ">
      <div id="chatbot-header" style="
        background:${cfg.windowColor}; color:#fff; padding:14px 16px;
        display:flex; justify-content:space-between; align-items:center; flex-shrink:0;
        position:relative; z-index:11;
      ">
        <div style="display:flex; align-items:center; gap:10px">
          <div style="width:38px;height:38px;border-radius:50%;background:rgba(255,255,255,.2);
              display:flex;align-items:center;justify-content:center;font-size:19px"> ${renderIconHtml(cfg.headerIcon || '🛍️', 19)}</div>
          <div>
            <div style="font-weight:700;font-size:15px">${escHtml(cfg.brandName)}</div>
            <div style="font-size:11px;opacity:.75">${storeDomain}</div>
          </div>
        </div>
        <div style="display:flex;gap:4px;align-items:center">
          <button id="cb-new-thread-btn" class="cb-hdr-icon-btn" title="New conversation">✏️</button>
          <button id="cb-history-btn" class="cb-hdr-icon-btn" title="Chat history">🕐</button>
          <button id="chatbot-close" class="cb-hdr-icon-btn" style="font-size:26px">×</button>
        </div>
      </div>

      <div id="cb-history-panel" style="position:absolute; inset:0; background:#fff; z-index:10; display:none; flex-direction:column; border-radius:18px; overflow:hidden;">
        <div style="padding:23px 16px;border-bottom:1px solid #d0e8da;display:flex;justify-content:space-between;align-items:center;background:#f4faf6;">
          <span style="font-weight:700;font-size:14px;color:#1a2e1a">💬 Conversation History</span>
          <button id="cb-history-close" style="background:none;border:none;cursor:pointer;font-size:22px;color:#555;padding:0 4px;line-height:1;">×</button>
        </div>
        <div style="padding:10px 12px;background:#f4faf6;border-bottom:1px solid #d0e8da;">
          <button class="cb-new-chat-btn" id="cb-new-chat-from-history">+ Start New Conversation</button>
        </div>
        <div id="cb-history-list" style="flex:1;overflow-y:auto;"></div>
        <div id="cb-history-empty" style="display:none;flex-direction:column;align-items:center;justify-content:center;padding:30px;color:#888;font-size:13px;text-align:center;flex:1;">
          <div style="font-size:36px;margin-bottom:10px">💬</div>
          <div>No past conversations yet.</div>
          <div style="margin-top:4px;font-size:12px">Start chatting to see history here!</div>
        </div>
      </div>

      <div style="display:flex;align-items:center;background:#f4faf6;flex-shrink:0;padding:10px 4px 0;position:relative;">
        <button id="cb-chips-arrow-left" style="
          display:none;flex-shrink:0;background:#fff;border:1px solid #c8ddd0;color:#2d6a4f;
          border-radius:50%;width:26px;height:26px;cursor:pointer;font-size:14px;line-height:1;
          align-items:center;justify-content:center;box-shadow:0 1px 4px rgba(0,0,0,.1);
          margin-left:2px;margin-right:4px;padding:0;transition:all .15s;
        ">‹</button>
        <div id="cb-chips-container" style="
          display:flex;gap:6px;flex-wrap:nowrap;overflow-x:auto;
          scrollbar-width:none;-ms-overflow-style:none;flex:1;
          padding-bottom:2px;scroll-behavior:smooth;
        ">
          <style>#cb-chips-container::-webkit-scrollbar{display:none}</style>`;

    // Render chips with proper icon support
    (cfg.quickChips || []).forEach(function (chip) {
      var iconHtml = renderIconHtml(chip.icon || '💬', 14);
      html += '<span class="cb-chip" data-q="' + escHtml(chip.query) + '" style="display:inline-flex;align-items:center;gap:6px;">' +
        iconHtml +
        '<span>' + escHtml(chip.label) + '</span>' +
        '</span>';
    });

    html += `
        </div>
        <button id="cb-chips-arrow-right" style="
          display:none;flex-shrink:0;background:#fff;border:1px solid #c8ddd0;color:#2d6a4f;
          border-radius:50%;width:26px;height:26px;cursor:pointer;font-size:14px;line-height:1;
          align-items:center;justify-content:center;box-shadow:0 1px 4px rgba(0,0,0,.1);
          margin-right:2px;margin-left:4px;padding:0;transition:all .15s;
        ">›</button>
      </div>

      <div id="chatbot-messages" style="flex:1;overflow-y:auto;padding:14px 12px;display:flex;flex-direction:column;gap:10px;background:#f4faf6;"></div>

      <div style="padding:12px;border-top:1px solid #d0e8da;display:flex;gap:8px;background:#fff;flex-shrink:0;align-items:center;">
        <input id="chatbot-input" type="text" placeholder="${escHtml(t.placeholder)}" style="flex:1;padding:10px 14px;border:1.5px solid #c8ddd0;border-radius:10px;outline:none;font-size:14px;color:#1a2e1a;"/>
        ${cfg.cartEnabled ? `
  <button id="chatbot-cart-btn" style="background:${cfg.windowColor}15;color:${cfg.windowColor};border:1.5px solid ${cfg.windowColor}55;padding:8px 12px;border-radius:10px;cursor:pointer;font-size:18px;display:flex;align-items:center;justify-content:center;transition:all .15s;">
    ${renderIconHtml(cfg.cartIcon || 'mdi:cart', 20)}
  </button>
` : ''}
        <button id="chatbot-send" style="background:${cfg.windowColor};color:#fff;border:none;padding:10px 20px;border-radius:10px;cursor:pointer;font-weight:700;font-size:14px;">Send</button>
      </div>
    </div>
  </div>`;

    document.body.insertAdjacentHTML('beforeend', html);
    widgetBuilt = true;
    injectDynamicStyles();
    bindEvents();
    greeted = false;
  }

  function rebuildWidget() {
    buildWidget();
  }

  function updateChipArrows() {
    if (!$chipsContainer || !$arrowLeft || !$arrowRight) return;
    var el = $chipsContainer;
    var canScrollLeft = el.scrollLeft > 2;
    var canScrollRight = el.scrollLeft + el.clientWidth < el.scrollWidth - 2;
    var hasOverflow = el.scrollWidth > el.clientWidth + 4;
    $arrowLeft.style.display = (hasOverflow && canScrollLeft) ? 'flex' : 'none';
    $arrowRight.style.display = (hasOverflow && canScrollRight) ? 'flex' : 'none';
  }

  // ══════════════════════════════════════════════════════════════════════════
  //  EVENT BINDING
  // ══════════════════════════════════════════════════════════════════════════

  var $t, $w, $c, $s, $i, $m, $historyPanel, $historyList, $historyEmpty, $historyBtn, $historyClose, $newThreadBtn, $newChatHistory;
  var greeted = false;
  var busy = false;
  var $chipsContainer, $arrowLeft, $arrowRight;
  var chipsResizeObserver = null;

  function debounce(fn, wait) {
    var timer = null;
    return function () {
      var args = arguments;
      clearTimeout(timer);
      timer = setTimeout(function () { fn.apply(null, args); }, wait);
    };
  }
  var debouncedUpdateChipArrows = debounce(updateChipArrows, 60);

  function bindEvents() {
    $t = document.getElementById('chatbot-toggle');
    $w = document.getElementById('chatbot-window');
    $c = document.getElementById('chatbot-close');
    $s = document.getElementById('chatbot-send');
    $i = document.getElementById('chatbot-input');
    $m = document.getElementById('chatbot-messages');
    $historyPanel = document.getElementById('cb-history-panel');
    $historyList = document.getElementById('cb-history-list');
    $historyEmpty = document.getElementById('cb-history-empty');
    $historyBtn = document.getElementById('cb-history-btn');
    $historyClose = document.getElementById('cb-history-close');
    $newThreadBtn = document.getElementById('cb-new-thread-btn');
    $newChatHistory = document.getElementById('cb-new-chat-from-history');

    // Cart button
    var $cartBtn = document.getElementById('chatbot-cart-btn');
    if ($cartBtn) {
      $cartBtn.onclick = function () {
        window.location.href = '/cart';
      };
    }

    // ── Chips arrow scroll ──────────────────────────────────────────────
    $chipsContainer = document.getElementById('cb-chips-container');
    $arrowLeft = document.getElementById('cb-chips-arrow-left');
    $arrowRight = document.getElementById('cb-chips-arrow-right');

    if ($chipsContainer) {
      $chipsContainer.addEventListener('scroll', debouncedUpdateChipArrows);
      if (window.ResizeObserver) {
        if (chipsResizeObserver) chipsResizeObserver.disconnect();
        chipsResizeObserver = new ResizeObserver(debouncedUpdateChipArrows);
        chipsResizeObserver.observe($chipsContainer);
      }
      setTimeout(updateChipArrows, 120);
    }

    if ($arrowLeft) {
      $arrowLeft.addEventListener('click', function () {
        if ($chipsContainer) {
          $chipsContainer.scrollLeft -= 120;
          setTimeout(updateChipArrows, 150);
        }
      });
    }

    if ($arrowRight) {
      $arrowRight.addEventListener('click', function () {
        if ($chipsContainer) {
          $chipsContainer.scrollLeft += 120;
          setTimeout(updateChipArrows, 150);
        }
      });
    }

    if ($t) $t.onclick = toggleChat;
    if ($c) $c.onclick = closeChat;
    if ($s) $s.onclick = sendMessage;
    if ($i) $i.onkeypress = function (e) { if (e.key === 'Enter') sendMessage(); };
    if ($historyBtn) $historyBtn.onclick = showHistoryPanel;
    if ($historyClose) $historyClose.onclick = hideHistoryPanel;
    if ($newThreadBtn) $newThreadBtn.onclick = startNewThread;
    if ($newChatHistory) $newChatHistory.onclick = startNewThread;

    document.querySelectorAll('.cb-chip').forEach(function (el) {
      el.addEventListener('click', function () {
        if ($i) $i.value = el.dataset.q;
        sendMessage();
      });
    });
  }

  function toggleChat(e) {
    e.stopPropagation();
    if (!$w) return;
    var open = $w.style.display !== 'flex';
    $w.style.display = open ? 'flex' : 'none';
    if (open) {
      // Re-check arrows now that the window is visible and has real dimensions
      setTimeout(updateChipArrows, 50);
      if (!greeted) {
        addText(cfg.greetingMessage, 'bot', true);
        greeted = true;
      }
      setTimeout(function () { if ($i) $i.focus(); }, 80);
    }
  }

  function closeChat(e) {
    if (e) e.stopPropagation();
    if ($w) $w.style.display = 'none';
  }

  function startNewThread() {
    currentThreadUUID = null;
    if ($m) $m.innerHTML = '';
    greeted = false;
    hideHistoryPanel();
    addText(cfg.greetingMessage, 'bot', true);
    greeted = true;
    setTimeout(function () { if ($i) $i.focus(); }, 80);
  }

  function showHistoryPanel() {
    if ($historyPanel) $historyPanel.style.display = 'flex';
    loadHistory();
  }

  function hideHistoryPanel() {
    if ($historyPanel) $historyPanel.style.display = 'none';
  }

  function formatRelativeTime(date) {
    var diff = Math.floor((Date.now() - date.getTime()) / 1000);
    if (diff < 60) return 'just now';
    if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
    if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
    if (diff < 604800) return Math.floor(diff / 86400) + 'd ago';
    return date.toLocaleDateString();
  }

  function loadHistory() {
    if (!$historyList) return;
    $historyList.innerHTML = '';
    if ($historyEmpty) $historyEmpty.style.display = 'none';
    var params = new URLSearchParams({ shop: shop });
    if (customer.id) params.set('customer_id', customer.id);
    else if (userUUID) params.set('user_uuid', userUUID);

    fetch(API_URL + '/api/chat/threads?' + params.toString())
      .then(function (res) { if (!res.ok) throw new Error('HTTP ' + res.status); return res.json(); })
      .then(function (data) {
        var threads = data.threads || [];
        if (!threads.length) {
          if ($historyEmpty) $historyEmpty.style.display = 'flex';
          return;
        }
        threads.forEach(function (t) {
          var item = document.createElement('div');
          item.className = 'cb-history-item';
          var createdAt = t.created_at ? new Date(t.created_at) : null;
          var timeStr = createdAt ? formatRelativeTime(createdAt) : '';
          var isCurrent = t.thread_uuid === currentThreadUUID;
          item.innerHTML = '<div style="font-size:22px;flex-shrink:0;margin-top:2px">💬</div>' +
            '<div style="flex:1;min-width:0">' +
            '<div style="font-size:13px;color:#1a2e1a;font-weight:' + (isCurrent ? '700' : '500') + ';white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + escHtml(t.preview || 'New conversation') + '</div>' +
            '<div style="font-size:11px;color:#888;margin-top:3px;display:flex;gap:10px;">' + (timeStr ? '<span>' + timeStr + '</span>' : '') + '</div>' +
            '</div>' +
            (isCurrent ? '<div style="width:8px;height:8px;border-radius:50%;background:#2d6a4f;flex-shrink:0;margin-top:6px;"></div>' : '');
          item.addEventListener('click', function () { loadThreadIntoChat(t.thread_uuid); });
          if ($historyList) $historyList.appendChild(item);
        });
      })
      .catch(function (err) {
        console.error('[Chatbot] History load error:', err);
        if ($historyEmpty) $historyEmpty.style.display = 'flex';
      });
  }

  function loadThreadIntoChat(threadUUID) {
    hideHistoryPanel();
    if ($m) $m.innerHTML = '';
    currentThreadUUID = threadUUID;
    fetch(API_URL + '/api/chat/thread/' + threadUUID)
      .then(function (res) { if (!res.ok) throw new Error('HTTP ' + res.status); return res.json(); })
      .then(function (data) {
        var messages = data.messages || [];
        console.log("messages:::::::::", messages)
        if (!messages.length) { addText(cfg.greetingMessage, 'bot'); greeted = true; return; }
        messages.forEach(function (msg) {
          if (msg.role === 'user') {
            addText(msg.content, 'user', false, msg.timestamp);  // ← pass timestamp
          } else {
            if (msg.response_data && msg.response_data.message) {
              renderResponse(msg.response_data, msg.timestamp);  // ← pass timestamp
            } else {
              addText(msg.content, 'bot', false, msg.timestamp); // ← false, not true (no typing effect for history)
            }
          }
        });
        greeted = true;
      })
      .catch(function (err) {
        console.error('[Chatbot] Load thread error:', err);
        addText('Could not load this conversation.', 'bot');
      });
  }




  function typeText(element, text, speed = 30, onComplete = null) {
  var i = 0;
  element.textContent = '';
  function typeNext() {
    if (i < text.length) {
      element.textContent += text.charAt(i);
      i++;
      setTimeout(typeNext, speed);
    } else {
      if (onComplete) onComplete();
    }
  }
  typeNext();
}

  function showBotTypingIndicator() {
    if (!$m) return null;
    var row = document.createElement('div');
    row.id = 'cb-bot-typing-indicator';
    row.className = 'cb-row';
    row.style.cssText = 'display:flex; justify-content:flex-start';

    var indicatorDiv = document.createElement('div');
    indicatorDiv.style.cssText = 'background:#fff; border:1px solid #d0e8da; border-radius:4px 18px 18px 18px; padding:10px 14px; box-shadow:0 1px 3px rgba(0,0,0,.06);';
    indicatorDiv.innerHTML = '<div style="display:flex; gap:4px; align-items:center;"><span style="animation:cb-pulse 1.4s infinite;color:' + cfg.windowColor + ';font-size:12px">●</span><span style="animation:cb-pulse 1.4s infinite .2s;color:' + cfg.windowColor + ';font-size:12px">●</span><span style="animation:cb-pulse 1.4s infinite .4s;color:' + cfg.windowColor + ';font-size:12px">●</span><span style="font-size:12px;color:#888;margin-left:6px">Thinking...</span></div>';

    row.appendChild(indicatorDiv);
    $m.appendChild(row);
    scrollDn();
    return row;
  }

  function removeBotTypingIndicator(indicator) {
    if (indicator && indicator.parentNode) {
      indicator.remove();
    }
  }


  var ts = function () { return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }); };
  var scrollDn = function () { if ($m) $m.scrollTop = $m.scrollHeight; };

  function addText(text, sender, isTypingEffect = false, originalTimestamp = null) {
    if (!$m) return;
    var row = document.createElement('div');
    row.className = 'cb-row';
    row.style.cssText = 'display:flex; justify-content:' + (sender === 'user' ? 'flex-end' : 'flex-start');
    var isUser = sender === 'user';

    var messageDiv = document.createElement('div');
    messageDiv.style.cssText = 'max-width:84%; padding:10px 14px; word-break:break-word;font-size:14px; line-height:1.6; box-shadow:0 1px 3px rgba(0,0,0,.07);' +
      (isUser ? 'background:' + cfg.windowColor + '; color:#fff; border-radius:18px 4px 18px 18px;' : 'background:#fff; color:#1a2e1a; border-radius:4px 18px 18px 18px; border:1px solid #d0e8da;');

    var textSpan = document.createElement('span');
    var timeDiv = document.createElement('div');
    timeDiv.style.cssText = 'font-size:10px;margin-top:5px;opacity:.5;text-align:right';
    if (originalTimestamp) {
      var d = new Date(originalTimestamp);
      timeDiv.textContent = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } else {
      timeDiv.textContent = ts();
    }

    messageDiv.appendChild(textSpan);
    messageDiv.appendChild(timeDiv);
    row.appendChild(messageDiv);
    $m.appendChild(row);

    if (isUser || !isTypingEffect) {
      textSpan.textContent = escHtml(text);
      scrollDn();
      return Promise.resolve(); 
    } else {
     return new Promise(function(resolve) {
      typeText(textSpan, text, 30, resolve); 
    });
    }
  }

// Creates an empty bot message bubble and returns a function to append text
// to it in real time as stream chunks arrive (no fake per-character timer).
function startStreamingBotMessage() {
  if (!$m) return function () {};
  var row = document.createElement('div');
  row.className = 'cb-row';
  row.style.cssText = 'display:flex; justify-content:flex-start';

  var messageDiv = document.createElement('div');
  messageDiv.style.cssText = 'max-width:84%; padding:10px 14px; word-break:break-word;font-size:14px; line-height:1.6; box-shadow:0 1px 3px rgba(0,0,0,.07); background:#fff; color:#1a2e1a; border-radius:4px 18px 18px 18px; border:1px solid #d0e8da;';

  var textSpan = document.createElement('span');
  var timeDiv = document.createElement('div');
  timeDiv.style.cssText = 'font-size:10px;margin-top:5px;opacity:.5;text-align:right';
  timeDiv.textContent = ts();

  messageDiv.appendChild(textSpan);
  messageDiv.appendChild(timeDiv);
  row.appendChild(messageDiv);
  $m.appendChild(row);
  scrollDn();

  var buffer = '';
  return function appendDelta(piece) {
    buffer += piece;
    textSpan.textContent = buffer;
    scrollDn();
  };
}

function renderAnswerExtras(answer) {
  var products = answer.products;
  var show_products = answer.show_products;
  var type = answer.type;
  var order_data = answer.order_data;
  var show_contact = answer.show_contact;
  var escalation_note = answer.escalation_note || '';
  var contact_url = answer.contact_url || '/pages/contact';

  if (type === 'auth_required') return;
  if (show_products && products && products.length) renderProductCards(products);
  if (type === 'order' && order_data) renderOrderCard(order_data);
  if (show_contact || type === 'redirect') renderContactButton(contact_url, escalation_note);
}

function renderResponse(answer, originalTimestamp = null) {
  var message = answer.message;
  var typingDone = Promise.resolve();

  if (message) {
    // addText now returns a promise
    typingDone = addText(message || '', 'bot', !originalTimestamp, originalTimestamp);
  }

  // ← Wait for typing to finish BEFORE showing cards
  typingDone.then(function () { renderAnswerExtras(answer); });
}


  function renderProductCards(products) {
    if (!$m) return;
    var section = document.createElement('div');
    section.className = 'cb-row';
    section.style.cssText = 'display:flex; flex-direction:column; gap:8px; width:100%';
    var lbl = document.createElement('div');
    lbl.style.cssText = 'font-size:11px; color:' + cfg.windowColor + '; font-weight:700; padding-left:2px; letter-spacing:.3px; display:flex; align-items:center; gap:5px;';
    lbl.innerHTML = renderIconHtml(cfg.headerIcon || '🛍️', 14) + ' <span>RECOMMENDED PRODUCTS</span>';
    section.appendChild(lbl);
    var grid = document.createElement('div');
    grid.style.cssText = 'display:flex; flex-direction:column; gap:8px';
    products.slice(0, 5).forEach(function (p) {
      var card = document.createElement('div');
      card.className = 'cb-card';
      var imgWrap = document.createElement('div');
      if (p.image_url) {
        var img = document.createElement('img');
        img.className = 'cb-img'; img.src = p.image_url; img.alt = p.title || ''; img.loading = 'lazy';
        img.onerror = function () { this.style.display = 'none'; var ph = document.createElement('div'); ph.className = 'cb-img-ph'; ph.textContent = '🛍️'; this.parentNode.insertBefore(ph, this.nextSibling); };
        imgWrap.appendChild(img);
      } else {
        var ph = document.createElement('div'); ph.className = 'cb-img-ph'; ph.textContent = '🛍️';
        imgWrap.appendChild(ph);
      }
      card.appendChild(imgWrap);
      var body = document.createElement('div');
      body.style.cssText = 'padding:10px 13px 13px';
      var topRow = document.createElement('div');
      topRow.style.cssText = 'display:flex; justify-content:space-between; align-items:flex-start; gap:8px';

      // Price is intentionally not shown on recommendation cards. A
      // "X% similar" badge takes its place when this card came from
      // fragrance-notes matching (see notes_similarity_pct in the backend).
      var hasSimilarity = p.notes_similarity_pct !== undefined && p.notes_similarity_pct !== null;
      topRow.innerHTML = '<div style="font-weight:700;font-size:13px;color:#1a2e1a;line-height:1.3">' + escHtml(p.title) + '</div>' +
        (hasSimilarity ?
          '<div style="flex-shrink:0;text-align:right"><div style="background:' + cfg.windowColor + '18;color:' + cfg.windowColor + ';font-size:11px;font-weight:800;padding:3px 7px;border-radius:6px;white-space:nowrap">' + escHtml(String(p.notes_similarity_pct)) + '% similaire</div></div>'
          : '');
      body.appendChild(topRow);

      if (p.category) {
        var cat = document.createElement('div');
        cat.style.cssText = 'font-size:11px;color:' + cfg.windowColor + ';margin-top:3px;opacity:0.8';
        cat.textContent = '📌 ' + p.category;
        body.appendChild(cat);
      }
      if (p.description) {
        var desc = document.createElement('div');
        desc.style.cssText = 'font-size:12px;color:#555;margin-top:7px;line-height:1.45';
        desc.textContent = p.description.length > 90 ? p.description.substring(0, 90) + '…' : p.description;
        body.appendChild(desc);
      }

      // Size selector — only when there's an actual choice. Selecting a
      // size updates which variant "Add to Cart" adds and where "View
      // Product" links to, so both buttons always act on the size the
      // customer picked, not just the first/default one.
      var sizeVariants = Array.isArray(p.variants) ? p.variants.filter(function (v) { return v && v.variant_id; }) : [];
      if (sizeVariants.length > 1) {
        var sizeRow = document.createElement('div');
        sizeRow.style.cssText = 'margin-top:9px';
        var sizeLabel = document.createElement('label');
        sizeLabel.style.cssText = 'font-size:10px;color:#888;font-weight:700;letter-spacing:.3px;display:block;margin-bottom:3px';
        sizeLabel.textContent = 'TAILLE';
        sizeRow.appendChild(sizeLabel);
        var sizeSelect = document.createElement('select');
        sizeSelect.style.cssText = 'width:100%;font-size:12px;padding:6px 8px;border-radius:8px;border:1.5px solid ' + cfg.windowColor + '44;background:#fff;color:#1a2e1a;font-weight:600;cursor:pointer';
        sizeVariants.forEach(function (v, idx) {
          var opt = document.createElement('option');
          opt.value = String(idx);
          opt.textContent = v.title || 'Standard';
          sizeSelect.appendChild(opt);
        });
        sizeSelect.onchange = function () {
          var chosen = sizeVariants[sizeSelect.selectedIndex];
          p.variant_id = chosen.variant_id;
          if (chosen.product_url && viewBtn) viewBtn.href = chosen.product_url;
        };
        sizeRow.appendChild(sizeSelect);
        body.appendChild(sizeRow);
        p.variant_id = sizeVariants[0].variant_id;
      } else if (sizeVariants.length === 1) {
        p.variant_id = sizeVariants[0].variant_id;
      }

      // THREE BUTTONS ROW
      var btnRow = document.createElement('div');
      btnRow.style.cssText = 'display:flex; gap:7px; margin-top:11px';

      // View Product button
      var viewBtn = null;
      if (p.product_url) {
        viewBtn = document.createElement('a');
        viewBtn.className = 'cb-view-btn';
        viewBtn.href = p.product_url;
        viewBtn.target = '_blank';
        viewBtn.rel = 'noopener noreferrer';
        viewBtn.textContent = 'View Product';
        viewBtn.style.cssText = 'flex:1; text-align:center; background:' + cfg.windowColor + '12; color:' + cfg.windowColor + '; border:1.5px solid ' + cfg.windowColor + '44; font-size:12px; padding:8px 10px; border-radius:8px; text-decoration:none; font-weight:700; transition:all .15s; display:block;';
        btnRow.appendChild(viewBtn);
      }

      // Add to Cart button
      if (cfg.cartEnabled) {
        var addToCartBtn = document.createElement('button');
        addToCartBtn.textContent = 'Add to Cart';
        addToCartBtn.style.cssText = 'flex:1; background:' + cfg.windowColor + '; color:#fff; border:none; font-size:12px; padding:8px 10px; border-radius:8px; cursor:pointer; font-weight:700; transition:all .15s;';
        addToCartBtn.onclick = function (e) {
          e.stopPropagation();
          addToCart(p, 1, addToCartBtn);
        };
        btnRow.appendChild(addToCartBtn);
      }

      // Ask more button
      var askBtn = document.createElement('button');
      askBtn.className = 'cb-ask-btn';
      askBtn.textContent = 'Ask more ✦';
      askBtn.style.cssText = 'flex:1; background:' + cfg.windowColor + '12; color:' + cfg.windowColor + '; border:1.5px solid ' + cfg.windowColor + '44; font-size:12px; padding:8px 10px; border-radius:8px; cursor:pointer; font-weight:700; transition:all .15s;';
      askBtn.addEventListener('click', function () {
        if ($i) $i.value = 'Tell me more about ' + p.title;
        sendMessage();
      });
      btnRow.appendChild(askBtn);

      body.appendChild(btnRow);
      card.appendChild(body);
      grid.appendChild(card);
    });
    section.appendChild(grid);
    $m.appendChild(section);
    // scrollDn();
  }

  function addToCart(product, quantity, button) {
    var originalText = button.textContent;
    button.textContent = 'Adding...';
    button.disabled = true;
    button.style.opacity = '0.6';

    var variantId = null;

    if (product.variant_id) {
      variantId = product.variant_id;
    }
    else if (product.all_variant_ids && product.all_variant_ids.length > 0) {
      variantId = product.all_variant_ids[0];
    }
    else if (product.shopify_id) {
      addToCartViaHandle(product, quantity, button, originalText);
      return;
    }

    if (variantId) {
      fetch('/cart/add.js', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: variantId, quantity: quantity })
      })
        .then(function (response) {
          if (!response.ok) {
            return response.json().then(function (err) {
              throw new Error(err.description || 'Failed to add to cart');
            });
          }
          return response.json();
        })
        // Inside addToCart — replace the .then success block:
        .then(function (data) {
          button.textContent = t.added;
          button.style.background = '#27ae60';

          updateCartCountDebounced();

          showToast(t.addedToCart(product.title || 'product'), '#27ae60');

          setTimeout(function () {
            button.textContent = originalText;
            button.disabled = false;
            button.style.opacity = '1';
            button.style.background = cfg.windowColor;
          }, 2000);
        })
        .catch(function (error) {
          console.error('Add to cart error:', error);
          button.textContent = t.failed;
          button.style.background = '#e74c3c';
          setTimeout(function () {
            button.textContent = originalText;
            button.disabled = false;
            button.style.opacity = '1';
            button.style.background = cfg.windowColor;
          }, 2000);
          showToast(t.addToCartError(error.message || 'Could not add to cart'), '#e74c3c');
        });
    } else {
      console.error('No variant ID found for product:', product);
      button.textContent = t.genericError;
      button.style.background = '#e74c3c';
      setTimeout(function () {
        button.textContent = originalText;
        button.disabled = false;
        button.style.opacity = '1';
        button.style.background = '#2d6a4f';
      }, 2000);
      showToast(t.variantNotFound, '#e74c3c');
    }
  }

  function addToCartViaHandle(product, quantity, button, originalText) {
    var handle = product.handle;

    if (!handle) {
      console.error('No product handle found for:', product.title);
      button.textContent = t.genericError;
      button.style.background = '#e74c3c';
          setTimeout(function () {
            button.textContent = originalText;
            button.disabled = false;
            button.style.opacity = '1';
            button.style.background = cfg.windowColor;
          }, 2000);
      showToast(t.productNotIdentified, '#e74c3c');
      return;
    }

    fetch('/products/' + handle + '.js')
      .then(function (response) {
        if (!response.ok) {
          throw new Error('Product not found');
        }
        return response.json();
      })
      .then(function (productData) {
        if (!productData.variants || productData.variants.length === 0) {
          throw new Error('No variants found for this product');
        }
        var variantId = productData.variants[0].id;

        return fetch('/cart/add.js', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id: variantId, quantity: quantity })
        });
      })
      .then(function (response) {
        if (!response.ok) {
          return response.json().then(function (err) {
            throw new Error(err.description || 'Failed to add to cart');
          });
        }
        return response.json();
      })
      .then(function (data) {
        button.textContent = t.added;
        button.style.background = '#27ae60';

        updateCartCountDebounced();

        showToast(t.addedToCart(product.title || 'product'), '#27ae60');
        setTimeout(function () {
          button.textContent = originalText;
          button.disabled = false;
          button.style.opacity = '1';
          button.style.background = cfg.windowColor;
        }, 2000);
      })
      .catch(function (error) {
        console.error('Add to cart via handle error:', error);
        button.textContent = t.failed;
        button.style.background = '#e74c3c';
        setTimeout(function () {
          button.textContent = originalText;
          button.disabled = false;
          button.style.opacity = '1';
          button.style.background = '#2d6a4f';
        }, 2000);
        showToast(t.addToCartError(error.message || 'Could not add to cart'), '#e74c3c');
      });
  }

  function showToast(message, backgroundColor) {
    var toast = document.createElement('div');
    toast.style.cssText = `
    position: fixed;
    top: 20px;
    right: 20px;
    background: ${backgroundColor};
    color: #fff;
    padding: 12px 24px;
    border-radius: 8px;
    z-index: 1000000;
    font-size: 14px;
    box-shadow: 0 4px 12px rgba(0,0,0,.2);
    text-align: center;
    white-space: nowrap;
  `;

    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(function () {
      toast.remove();
    }, 3000);
  }
  function updateCartCount() {
    fetch('/cart.js')
      .then(function (r) { return r.json(); })
      .then(function (cart) {
        var count = cart.item_count;

        // ── Step 1: Re-render cart sections via Shopify Sections API ──
        // Only refetch sections that actually exist on this page — themes
        // vary in which of these they render, and fetching absent ones
        // wastes a full request per add-to-cart click.
        var sectionIds = [
          'cart-icon-bubble',
          'cart-notification',
          'cart-count-bubble',
          'cart-drawer',
          'header',
          'announcement-bar',
        ].filter(function (sectionId) {
          return document.getElementById(sectionId)
            || document.querySelector('[data-section-id="' + sectionId + '"]')
            || document.querySelector('.' + sectionId);
        });

        sectionIds.forEach(function (sectionId) {
          fetch('/?section_id=' + sectionId)
            .then(function (r) { return r.text(); })
            .then(function (html) {
              var parser = new DOMParser();
              var freshDoc = parser.parseFromString(html, 'text/html');

              // Find section in fresh HTML
              var freshSection = freshDoc.getElementById(sectionId)
                || freshDoc.querySelector('[data-section-id="' + sectionId + '"]')
                || freshDoc.querySelector('.' + sectionId);

              // Find section in live DOM
              var liveSection = document.getElementById(sectionId)
                || document.querySelector('[data-section-id="' + sectionId + '"]')
                || document.querySelector('.' + sectionId);

              if (freshSection && liveSection) {
                liveSection.innerHTML = freshSection.innerHTML;
              }
            })
            .catch(function () {
              // Section doesn't exist in this theme — silently skip
            });
        });

        // ── Step 2: Dispatch events that themes listen for ────────────
        var cartDetail = { cart: cart, itemCount: count, item_count: count };

        [
          'cart:updated',
          'cart:change',
          'cart:add',
          'theme:cart:add',
          'product:added',
          'ajaxCart:add',
          'on:cart:add',
          'cart-update',
        ].forEach(function (eventName) {
          document.dispatchEvent(new CustomEvent(eventName, {
            bubbles: true,
            detail: cartDetail
          }));
          window.dispatchEvent(new CustomEvent(eventName, {
            bubbles: true,
            detail: cartDetail
          }));
        });

        // ── Step 3: Shopify global callback ───────────────────────────
        if (window.Shopify && typeof window.Shopify.onCartUpdate === 'function') {
          window.Shopify.onCartUpdate(cart);
        }

        // ── Step 4: Visual bump on cart icon ──────────────────────────
        document.querySelectorAll(
          '[data-cart-toggle], [href="/cart"], .cart-link, ' +
          '.site-header__cart, .cart__link, [aria-label*="cart"], ' +
          '[aria-label*="Cart"], .header__cart, .nav-cart'
        ).forEach(function (el) {
          el.classList.add('cart-bump');
          setTimeout(function () { el.classList.remove('cart-bump'); }, 350);
        });
      })
      .catch(function (err) {
        console.error('[Chatbot] updateCartCount error:', err);
      });
  }

  // Coalesces bursts of add-to-cart clicks into a single refresh.
  var updateCartCountDebounced = debounce(updateCartCount, 250);

  function renderOrderCard(order) {
    if (!$m || !order || !order.id) return;
    var wrap = document.createElement('div'); wrap.className = 'cb-row';
    wrap.style.cssText = 'display:flex; justify-content:flex-start';
    var status = order.fulfillment_status || order.financial_status || 'Processing';
    var total = order.total_price ? ('$' + order.total_price) : 'N/A';
    var created = order.created_at ? new Date(order.created_at).toLocaleDateString() : 'N/A';
    var sColor = (status === 'fulfilled' || status === 'paid') ? '#2d6a4f' : '#b45309';
    var displayOrderNumber = order.name || order.id;
    wrap.innerHTML = '<div style="background:#fff;border:1.5px solid #d0e8da;border-radius:4px 18px 18px 18px;padding:14px 16px;max-width:310px;box-shadow:0 1px 4px rgba(0,0,0,.06)">' +
      '<div style="font-weight:700;font-size:14px;margin-bottom:10px;color:#1a2e1a">📦 Order ' + escHtml(String(displayOrderNumber)) + '</div>' +
      '<div style="display:grid;grid-template-columns:auto 1fr;gap:5px 14px;font-size:12px;color:#444">' +
      '<span style="color:#888">Status</span><span style="color:' + sColor + ';font-weight:700;text-transform:capitalize">' + escHtml(status) + '</span>' +
      '<span style="color:#888">Total</span><span style="font-weight:600">' + total + '</span>' +
      '<span style="color:#888">Date</span><span>' + created + '</span>' +
      (order.email ? '<span style="color:#888">Email</span><span>' + escHtml(order.email) + '</span>' : '') +
      '</div>' +
      (order.order_status_url ? '<a href="' + escHtml(order.order_status_url) + '" target="_blank" style="display:inline-block;margin-top:12px;background:' + cfg.windowColor + ';color:#fff;font-size:12px;padding:7px 16px;border-radius:8px;text-decoration:none;font-weight:700">Track Order →</a>' : '') +
      '</div>';
    $m.appendChild(wrap); scrollDn();
  }

  function renderContactButton(contactUrl, escalationNote) {
    if (!$m) return;
    var wrap = document.createElement('div');
    wrap.className = 'cb-row';
    wrap.style.cssText = 'display:flex; flex-direction:column; align-items:flex-start; padding-left:2px; gap:6px;';

    var btn = document.createElement('a');
    btn.className = 'cb-contact-btn';
    btn.href = contactUrl || '/pages/contact';
    btn.target = '_blank';
    btn.rel = 'noopener noreferrer';
    btn.innerHTML = '💬 Contact Us';
    wrap.appendChild(btn);

    // Show 48-hour note if present
    if (escalationNote) {
      var note = document.createElement('div');
      note.style.cssText = (
        'font-size:11px; color:#5a8a6a; line-height:1.5; max-width:270px; '
        + 'background:#f0f7f4; border-left:3px solid #2d6a4f; '
        + 'padding:6px 10px; border-radius:0 8px 8px 0;'
      );
      note.textContent = escalationNote;
      wrap.appendChild(note);
    }

    $m.appendChild(wrap);
    scrollDn();
  }


  function showTyping() {
    if (!$m) return null;
    var div = document.createElement('div'); div.id = 'cb-typing'; div.className = 'cb-row';
    div.style.cssText = 'display:flex;justify-content:flex-start';
    div.innerHTML = '<div style="background:#fff;border:1px solid #d0e8da;border-radius:4px 18px 18px 18px;padding:10px 14px;box-shadow:0 1px 3px rgba(0,0,0,.06)"><div style="display:flex;gap:5px;align-items:center"><span style="animation:cb-pulse 1.4s infinite;color:' + cfg.windowColor + ';font-size:11px">●</span><span style="animation:cb-pulse 1.4s infinite .2s;color:' + cfg.windowColor + ';font-size:11px">●</span><span style="animation:cb-pulse 1.4s infinite .4s;color:' + cfg.windowColor + ';font-size:11px">●</span><span style="font-size:11px;color:#888;margin-left:4px">Thinking…</span></div></div>';
    $m.appendChild(div);
    // scrollDn();
    return div;
  }

  function rmTyping(d) { if (d && d.parentNode) d.remove(); }

  function chatRequestBody(text) {
    return JSON.stringify({
      query: text,
      shop: shop,
      thread_uuid: currentThreadUUID,
      user_uuid: userUUID,
      customer_id: customer.id || null,
      customer_email: customer.email || null,
      page_url: window.location.href,
      device_info: getDeviceInfo(),
    });
  }

  function maybeBumpCart(answer) {
    if (answer && answer.show_products && answer.products && answer.products.length) {
      setTimeout(function () { updateCartCount(); }, 300);
    }
  }

  // Non-streaming fallback (used if the browser/proxy doesn't support
  // streaming reads, or the stream endpoint errors before any data arrives).
  function sendMessageNonStreaming(text, typingIndicator) {
    fetch(API_URL + '/api/chat/send', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: chatRequestBody(text),
    })
      .then(function (res) {
        removeBotTypingIndicator(typingIndicator);
        if (res.status === 429) {
          renderResponse({ type: 'general', message: t.rateLimited, products: [], show_products: false, show_contact: false });
          return null;
        }
        if (res.status === 403) {
          renderResponse({ type: 'redirect', message: t.accessDenied, products: [], show_products: false, show_contact: true, contact_url: '/pages/contact' });
          return null;
        }
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (data) {
        if (!data) return;
        if (data.thread_uuid) currentThreadUUID = data.thread_uuid;
        if (data.error) {
          addText(t.genericChatError, 'bot', true);
          return;
        }
        renderResponse(data.answer || {});
        maybeBumpCart(data.answer);
      })
      .catch(function (err) {
        removeBotTypingIndicator(typingIndicator);
        renderResponse({
          type: 'redirect', message: t.connectionError, products: [],
          show_products: false, show_contact: true, escalation_note: '', contact_url: '/pages/contact',
        });
        console.error('[Chatbot]', err);
      })
      .finally(function () { busy = false; });
  }

  // Streams the reply token-by-token via SSE so the user sees real text
  // arriving in real time instead of waiting for the full response.
  function sendMessageStreaming(text, typingIndicator) {
    var appendDelta = null;
    var gotAnyDelta = false;
    var finalAnswer = null;

    fetch(API_URL + '/api/chat/send-stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: chatRequestBody(text),
    })
      .then(function (res) {
        if (!res.ok || !res.body || !res.body.getReader) throw new Error('stream unsupported, HTTP ' + res.status);

        var reader = res.body.getReader();
        var decoder = new TextDecoder();
        var buf = '';

        function pump() {
          return reader.read().then(function (result) {
            if (result.done) return;
            buf += decoder.decode(result.value, { stream: true });
            var parts = buf.split('\n\n');
            buf = parts.pop(); // last part may be incomplete — keep for next chunk
            parts.forEach(function (part) {
              var line = part.trim();
              if (!line.startsWith('data:')) return;
              var payload;
              try { payload = JSON.parse(line.slice(5).trim()); } catch (e) { return; }

              if (payload.thread_uuid) currentThreadUUID = payload.thread_uuid;

              if (typeof payload.delta === 'string') {
                if (!gotAnyDelta) {
                  removeBotTypingIndicator(typingIndicator);
                  appendDelta = startStreamingBotMessage();
                  gotAnyDelta = true;
                }
                appendDelta(payload.delta);
              }
              if (payload.final) {
                finalAnswer = payload.final;
              }
            });
            return pump();
          });
        }
        return pump();
      })
      .then(function () {
        if (!gotAnyDelta) {
          // Nothing streamed at all (e.g. proxy buffered the whole response) —
          // fall back so the user still gets an answer.
          removeBotTypingIndicator(typingIndicator);
          sendMessageNonStreaming(text, null);
          return;
        }
        if (finalAnswer) renderAnswerExtras(finalAnswer);
        maybeBumpCart(finalAnswer);
        busy = false;
      })
      .catch(function (err) {
        console.warn('[Chatbot] streaming failed, falling back:', err);
        if (gotAnyDelta) {
          // Partial text already shown — don't double-send, just stop here.
          removeBotTypingIndicator(typingIndicator);
          busy = false;
          return;
        }
        removeBotTypingIndicator(typingIndicator);
        sendMessageNonStreaming(text, null);
      });
  }

  function sendMessage() {
    if (!$i) return;
    var text = $i.value.trim();
    if (!text || busy) return;
    $i.value = '';
    busy = true;
    addText(text, 'user', false);

    var typingIndicator = showBotTypingIndicator();

    if (window.fetch && window.ReadableStream && window.TextDecoder) {
      sendMessageStreaming(text, typingIndicator);
    } else {
      sendMessageNonStreaming(text, typingIndicator);
    }
  }

  // ══════════════════════════════════════════════════════════════════════════
  //  INIT
  // ══════════════════════════════════════════════════════════════════════════

  function isPageAllowed(selectedPages) {
    if (!selectedPages || selectedPages.length === 0) return false;
    var path = window.location.pathname;

    var pageTypeMap = {
      'home': path === '/' || path === '',
      'product': path.includes('/products/'),
      'collection': path.includes('/collections/'),
      'blog': path.includes('/blogs/') || path === '/blogs',
      'cart': path === '/cart' || path.startsWith('/cart/'),
      'checkout': path.includes('/checkouts') || path.includes('/checkout'),
      'contact': path === '/pages/contact' || path === '/contact' || path === '/pages/contact-us',
    };

    var standardMatch = selectedPages.some(function (pageType) {
      return pageTypeMap[pageType] === true;
    });
    if (standardMatch) return true;

    // Check dynamic page handles stored as "pages:{handle}"
    if (path.startsWith('/pages/')) {
      var parts = path.split('/pages/');
      if (parts[1]) {
        var currentHandle = parts[1].split('?')[0].split('#')[0];
        return selectedPages.some(function (p) {
          if (p.startsWith('pages:')) {
            return p === 'pages:' + currentHandle;
          }
          return false;
        });
      }
    }

    return false;
  }

  loadConfig();
})();