(function () {
  "use strict";

  var script = document.currentScript;
  var responseId = script.getAttribute("data-response-id");

  var statusEl = document.getElementById("wait-status");
  var errorEl = document.getElementById("wait-error");
  var spinnerEl = document.getElementById("spinner");
  var titleEl = document.getElementById("wait-title");

  var POLL_INTERVAL = 3000;
  var TIMEOUT = 180000;
  var startTime = Date.now();
  var timerId = null;

  var STATUS_MESSAGES = {
    pending: "요청을 접수했습니다...",
    processing: "교통편을 검색하고 있습니다..."
  };

  function pollUrl() {
    if (responseId) {
      return "/api/status/" + encodeURIComponent(responseId);
    }
    return "/api/status/latest";
  }

  function showError(message) {
    if (spinnerEl) spinnerEl.style.display = "none";
    if (titleEl) titleEl.textContent = "오류 발생";
    if (statusEl) statusEl.textContent = "";
    if (errorEl) {
      errorEl.textContent = message;
      errorEl.classList.add("visible");
    }
  }

  function poll() {
    if (Date.now() - startTime > TIMEOUT) {
      stopPolling();
      showError("시간이 초과되었습니다. 나중에 다시 시도해 주세요.");
      return;
    }

    fetch(pollUrl())
      .then(function (res) {
        if (res.status === 404) {
          if (statusEl) statusEl.textContent = "요청을 기다리고 있습니다...";
          return null;
        }
        if (!res.ok) throw new Error("서버 오류 (" + res.status + ")");
        return res.json();
      })
      .then(function (data) {
        if (!data) return;

        // Auto-discover response_id from latest endpoint
        if (!responseId && data.response_id) {
          responseId = data.response_id;
        }

        if (data.status === "done" && data.result_id) {
          stopPolling();
          if (statusEl) statusEl.textContent = "완료! 결과 페이지로 이동합니다...";
          window.location.href = "/r/" + data.result_id;
          return;
        }

        if (data.status === "error") {
          stopPolling();
          showError(data.error_message || "처리 중 오류가 발생했습니다.");
          return;
        }

        if (statusEl) {
          statusEl.textContent = STATUS_MESSAGES[data.status] || STATUS_MESSAGES.processing;
        }
      })
      .catch(function (err) {
        console.error("Polling error:", err);
      });
  }

  function stopPolling() {
    if (timerId !== null) {
      clearInterval(timerId);
      timerId = null;
    }
  }

  poll();
  timerId = setInterval(poll, POLL_INTERVAL);
})();
