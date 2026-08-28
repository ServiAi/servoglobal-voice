(function () {
  'use strict';

  if (window.VoiceEmbed) return;

  var RESIZE_MESSAGE_TYPE = 'voice-embed:resize';
  var Z_INDEX = 2147483000;

  function createIframe(src) {
    var iframe = document.createElement('iframe');
    iframe.src = src;
    iframe.setAttribute('allow', 'microphone; autoplay');
    iframe.setAttribute('title', 'Voice assistant');
    iframe.style.border = '0';
    iframe.style.width = '100%';
    iframe.style.display = 'block';
    return iframe;
  }

  function resolveTarget(target) {
    if (!target) return null;
    if (typeof target === 'string') return document.querySelector(target);
    return target;
  }

  function waitForElement(selector, callback) {
    var existing = document.querySelector(selector);
    if (existing) {
      callback(existing);
      return;
    }
    var observer = new MutationObserver(function () {
      var el = document.querySelector(selector);
      if (el) {
        observer.disconnect();
        callback(el);
      }
    });
    observer.observe(document.documentElement, { childList: true, subtree: true });
  }

  function clampPanelSize(panel) {
    var isSmall = window.innerWidth < 480;
    panel.style.width = isSmall ? 'calc(100vw - 24px)' : '380px';
    panel.style.maxWidth = 'calc(100vw - 24px)';
    panel.style.maxHeight = '80vh';
  }

  function mountInline(target, opts) {
    var container = resolveTarget(target);
    if (!container || !opts || !opts.src) return null;
    var iframe = createIframe(opts.src);
    iframe.style.height = (opts.height || 640) + 'px';
    container.appendChild(iframe);
    return { iframe: iframe, destroy: function () { iframe.remove(); } };
  }

  function mountFloating(opts) {
    if (!opts || !opts.src) return null;
    var position = opts.position === 'bottom-left' ? 'bottom-left' : 'bottom-right';
    var button = document.createElement('button');
    button.type = 'button';
    button.textContent = opts.text || 'Habla con nosotros';
    button.style.position = 'fixed';
    button.style.bottom = '20px';
    button.style[position === 'bottom-left' ? 'left' : 'right'] = '20px';
    button.style.zIndex = String(Z_INDEX);
    button.style.borderRadius = '999px';
    button.style.border = '0';
    button.style.padding = '12px 20px';
    button.style.fontSize = '14px';
    button.style.fontWeight = '600';
    button.style.color = '#ffffff';
    button.style.backgroundColor = '#0f766e';
    button.style.boxShadow = '0 12px 30px -10px rgba(15,23,42,0.45)';
    button.style.cursor = 'pointer';
    document.body.appendChild(button);

    var panel = null;
    var iframe = null;
    var open = false;

    function ensurePanel() {
      if (panel) return;
      panel = document.createElement('div');
      panel.style.position = 'fixed';
      panel.style.bottom = '84px';
      panel.style[position === 'bottom-left' ? 'left' : 'right'] = '20px';
      panel.style.zIndex = String(Z_INDEX - 1);
      panel.style.overflow = 'hidden';
      panel.style.borderRadius = '16px';
      panel.style.boxShadow = '0 24px 60px -20px rgba(15,23,42,0.55)';
      panel.style.display = 'none';
      clampPanelSize(panel);
      iframe = createIframe(opts.src);
      iframe.style.height = '480px';
      iframe.style.maxHeight = '80vh';
      panel.appendChild(iframe);
      document.body.appendChild(panel);
      window.addEventListener('resize', function () {
        if (panel) clampPanelSize(panel);
      });
    }

    button.addEventListener('click', function () {
      ensurePanel();
      open = !open;
      panel.style.display = open ? 'block' : 'none';
      button.textContent = open ? '✕' : (opts.text || 'Habla con nosotros');
    });

    return {
      button: button,
      destroy: function () {
        button.remove();
        if (panel) panel.remove();
      },
    };
  }

  function mountModal(opts) {
    if (!opts || !opts.src || !opts.trigger) return null;
    var overlay = null;
    var iframe = null;

    function ensureOverlay() {
      if (overlay) return;
      overlay = document.createElement('div');
      overlay.style.position = 'fixed';
      overlay.style.inset = '0';
      overlay.style.backgroundColor = 'rgba(0,0,0,0.5)';
      overlay.style.zIndex = String(Z_INDEX);
      overlay.style.display = 'none';
      overlay.style.alignItems = 'center';
      overlay.style.justifyContent = 'center';

      var panel = document.createElement('div');
      panel.style.position = 'relative';
      panel.style.width = 'min(560px, calc(100vw - 32px))';
      panel.style.maxHeight = '85vh';
      panel.style.overflow = 'hidden';
      panel.style.borderRadius = '16px';
      panel.style.boxShadow = '0 30px 80px -20px rgba(0,0,0,0.6)';

      var closeButton = document.createElement('button');
      closeButton.type = 'button';
      closeButton.setAttribute('aria-label', 'Cerrar');
      closeButton.textContent = '✕';
      closeButton.style.position = 'absolute';
      closeButton.style.top = '8px';
      closeButton.style.right = '8px';
      closeButton.style.zIndex = '1';
      closeButton.style.border = '0';
      closeButton.style.background = 'rgba(255,255,255,0.9)';
      closeButton.style.borderRadius = '999px';
      closeButton.style.width = '32px';
      closeButton.style.height = '32px';
      closeButton.style.cursor = 'pointer';
      closeButton.addEventListener('click', close);

      iframe = createIframe(opts.src);
      iframe.style.height = '70vh';
      iframe.style.maxHeight = '85vh';

      panel.appendChild(closeButton);
      panel.appendChild(iframe);
      overlay.appendChild(panel);
      overlay.addEventListener('click', function (event) {
        if (event.target === overlay) close();
      });
      document.body.appendChild(overlay);
    }

    function open() {
      ensureOverlay();
      overlay.style.display = 'flex';
      document.addEventListener('keydown', onKeyDown);
    }

    function close() {
      if (overlay) overlay.style.display = 'none';
      document.removeEventListener('keydown', onKeyDown);
    }

    function onKeyDown(event) {
      if (event.key === 'Escape') close();
    }

    function attach(el) {
      el.addEventListener('click', function (event) {
        event.preventDefault();
        open();
      });
    }

    if (typeof opts.trigger === 'string') {
      waitForElement(opts.trigger, attach);
    } else {
      attach(opts.trigger);
    }

    return {
      open: open,
      close: close,
      destroy: function () {
        if (overlay) overlay.remove();
      },
    };
  }

  window.addEventListener('message', function (event) {
    var data = event.data;
    if (!data || data.type !== RESIZE_MESSAGE_TYPE || typeof data.height !== 'number') return;
    var iframes = document.querySelectorAll('iframe');
    for (var i = 0; i < iframes.length; i += 1) {
      if (iframes[i].contentWindow === event.source) {
        iframes[i].style.height = data.height + 'px';
        break;
      }
    }
  });

  window.VoiceEmbed = {
    mountInline: mountInline,
    mountFloating: mountFloating,
    mountModal: mountModal,
    destroy: function (handle) {
      if (handle && typeof handle.destroy === 'function') handle.destroy();
    },
  };

  function autoInit() {
    // Inline containers self-declare via their own [data-voice-embed="inline"]
    // attribute, independent of whichever script tag happens to load the SDK.
    var containers = document.querySelectorAll('[data-voice-embed="inline"]');
    for (var i = 0; i < containers.length; i += 1) {
      var src = containers[i].getAttribute('data-voice-embed-src');
      if (src) mountInline(containers[i], { src: src });
    }

    var script = document.currentScript;
    if (!script) return;
    var mode = script.getAttribute('data-voice-embed');
    var scriptSrc = script.getAttribute('data-voice-embed-src');
    if (mode === 'floating') {
      mountFloating({
        src: scriptSrc,
        text: script.getAttribute('data-voice-embed-text'),
        position: script.getAttribute('data-voice-embed-position'),
      });
    } else if (mode === 'modal') {
      mountModal({
        src: scriptSrc,
        trigger: script.getAttribute('data-voice-embed-trigger'),
      });
    }
  }

  autoInit();
})();
