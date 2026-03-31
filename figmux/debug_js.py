from __future__ import annotations

DOM_EVENT_DEBUG_JS = r"""
(function () {
  if (window.__figmuxInputDebugInstalled) {
    return;
  }
  window.__figmuxInputDebugInstalled = true;

  function summarizeTransfer(dataTransfer) {
    if (!dataTransfer) {
      return { hasDataTransfer: false };
    }
    var fileCount = dataTransfer.files ? dataTransfer.files.length : 0;
    var itemKinds = [];
    if (dataTransfer.items) {
      for (var i = 0; i < dataTransfer.items.length; i += 1) {
        var item = dataTransfer.items[i];
        itemKinds.push({ kind: item.kind, type: item.type });
      }
    }
    return {
      hasDataTransfer: true,
      fileCount: fileCount,
      itemKinds: itemKinds
    };
  }

  function log(name, payload) {
    try {
      console.info("[figmux-input-debug]", JSON.stringify({ event: name, payload: payload }));
    } catch (error) {
      console.info("[figmux-input-debug]", name);
    }
  }

  ["dragenter", "dragover", "drop"].forEach(function (eventName) {
    window.addEventListener(eventName, function (event) {
      log(eventName, summarizeTransfer(event.dataTransfer));
    }, true);
  });

  window.addEventListener("paste", function (event) {
    log("paste", summarizeTransfer(event.clipboardData));
  }, true);
})();
"""

CURSOR_SCALE_DEBUG_JS = r"""
(function () {
  function describeVisualViewport() {
    if (!window.visualViewport) {
      return null;
    }
    return {
      width: window.visualViewport.width,
      height: window.visualViewport.height,
      scale: window.visualViewport.scale,
      offsetLeft: window.visualViewport.offsetLeft,
      offsetTop: window.visualViewport.offsetTop
    };
  }

  function safeCursor(selector) {
    var node = selector === "body" ? document.body : document.documentElement;
    if (!node) {
      return null;
    }
    try {
      return window.getComputedStyle(node).cursor;
    } catch (_error) {
      return null;
    }
  }

  function logSnapshot(reason) {
    var canvas = document.querySelector("canvas");
    var payload = {
      reason: reason,
      href: window.location.href,
      devicePixelRatio: window.devicePixelRatio,
      innerWidth: window.innerWidth,
      innerHeight: window.innerHeight,
      outerWidth: window.outerWidth,
      outerHeight: window.outerHeight,
      visualViewport: describeVisualViewport(),
      bodyCursor: safeCursor("body"),
      documentCursor: safeCursor("document"),
      canvasWidth: canvas ? canvas.width : null,
      canvasHeight: canvas ? canvas.height : null,
      canvasClientWidth: canvas ? canvas.clientWidth : null,
      canvasClientHeight: canvas ? canvas.clientHeight : null
    };
    try {
      console.info("[figmux-input-debug]", JSON.stringify({ event: "cursor_scale_snapshot", payload: payload }));
    } catch (_error) {
      console.info("[figmux-input-debug]", "cursor_scale_snapshot");
    }
  }

  if (!window.__figmuxCursorScaleDebugInstalled) {
    window.__figmuxCursorScaleDebugInstalled = true;
    window.addEventListener("resize", function () {
      logSnapshot("resize");
    });
  }

  logSnapshot("load");
})();
"""
