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
