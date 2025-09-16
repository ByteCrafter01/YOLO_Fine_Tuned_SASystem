class LiveStreamManager {
  constructor() {
    const token = localStorage.getItem("ppe_token");
    this.socket = io({
      auth: {
        token: token,
      },
    });
    this.canvas = document.getElementById("videoCanvas");
    this.ctx = this.canvas.getContext("2d");
    this.isStreaming = false;
    this.sessionId = null;
    this.frameCount = 0;

    this.setupSocketListeners();
    this.setupUI();
    this.loadVideoSources();
    this.checkAutoStart(); // Add this line
  }

  // Add this new method
  checkAutoStart() {
    const urlParams = new URLSearchParams(window.location.search);
    const autoStart = urlParams.get("autostart");

    if (autoStart === "webcam") {
      // Wait a moment for video sources to load, then auto-start webcam
      setTimeout(() => {
        this.autoStartWebcam();
      }, 1000);
    }
  }

  // Add this new method
  async autoStartWebcam() {
    try {
      // Check if webcam is available
      const devices = await navigator.mediaDevices.enumerateDevices();
      const hasWebcam = devices.some((device) => device.kind === "videoinput");

      if (!hasWebcam) {
        alert("No webcam detected. Please connect a webcam and try again.");
        return;
      }

      // Set webcam as selected source
      const videoSourceSelect = document.getElementById("videoSource");
      videoSourceSelect.value = "webcam";

      // Show loading message
      this.updateStreamStatus("Initializing webcam...");

      // Start the stream
      this.startStream();
    } catch (error) {
      console.error("Error accessing webcam:", error);
      alert("Could not access webcam. Please check permissions and try again.");
    }
  }

  setupSocketListeners() {
    this.socket.on("connect", () => {
      console.log("Connected to server");
      this.updateStreamStatus("Connected");
    });

    this.socket.on("disconnect", () => {
      console.log("Disconnected from server");
      this.updateStreamStatus("Disconnected");
      this.isStreaming = false;
    });

    this.socket.on("live_session_started", (data) => {
      this.sessionId = data.session_id;
      this.isStreaming = true;
      this.updateStreamStatus("Streaming");
      console.log("Live session started:", this.sessionId);
    });

    this.socket.on("live_frame", (data) => {
      this.displayFrame(data);
      this.updateAnalysis(data.analysis);
      this.frameCount = data.frame_count;
      document.getElementById(
        "frameCounter"
      ).textContent = `Frame: ${this.frameCount}`;
    });

    this.socket.on("violation_alert", (data) => {
      this.showViolationAlert(data.violations);
    });

    this.socket.on("query_response", (data) => {
      this.addQueryToHistory(data.query, data.response);
    });

    this.socket.on("live_session_stopped", () => {
      this.isStreaming = false;
      this.sessionId = null;
      this.updateStreamStatus("Stopped");
      this.clearCanvas();
    });
  }

  setupUI() {
    const startBtn = document.getElementById("startStream");
    const stopBtn = document.getElementById("stopStream");
    const sendQueryBtn = document.getElementById("sendQuery");
    const queryInput = document.getElementById("queryInput");

    startBtn.addEventListener("click", () => this.startStream());
    stopBtn.addEventListener("click", () => this.stopStream());
    sendQueryBtn.addEventListener("click", () => this.sendQuery());

    queryInput.addEventListener("keypress", (e) => {
      if (e.key === "Enter") {
        this.sendQuery();
      }
    });

    // Query suggestion buttons
    document.querySelectorAll(".query-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const query = btn.getAttribute("data-query");
        document.getElementById("queryInput").value = query;
        this.sendQuery();
      });
    });
  }

  async loadVideoSources() {
    try {
      const token = localStorage.getItem("ppe_token");
      const response = await fetch("/api/videos", {
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const videos = await response.json();

      const select = document.getElementById("videoSource");
      select.innerHTML = '<option value="">Select video source</option>';

      // Add webcam option
      select.innerHTML += '<option value="webcam">Webcam (Live)</option>';

      // Add uploaded videos
      videos.forEach((video) => {
        select.innerHTML += `<option value="${video.file_path}">${video.filename}</option>`;
      });
    } catch (error) {
      console.error("Error loading video sources:", error);
    }
  }

  startStream() {
    const videoSource = document.getElementById("videoSource").value;
    if (!videoSource) {
      alert("Please select a video source");
      return;
    }

    const startBtn = document.getElementById("startStream");
    const stopBtn = document.getElementById("stopStream");

    startBtn.disabled = true;
    stopBtn.disabled = false;

    const token = localStorage.getItem("ppe_token");

    this.socket.emit("start_live_stream", {
      video_source: videoSource,
      auth: { token: token },
    });

    console.log("Emitted start_live_stream with:", {
      video_source: videoSource,
      auth: { token },
    });

    this.updateStreamStatus("Starting...");
  }

  stopStream() {
    const startBtn = document.getElementById("startStream");
    const stopBtn = document.getElementById("stopStream");

    startBtn.disabled = false;
    stopBtn.disabled = true;

    this.socket.emit("stop_live_stream", {
      session_id: this.sessionId,
    });
  }

  displayFrame(data) {
    if (!data.frame) return;

    const img = new Image();
    img.onload = () => {
      this.canvas.width = img.width;
      this.canvas.height = img.height;
      this.ctx.drawImage(img, 0, 0);
    };
    img.src = "data:image/jpeg;base64," + data.frame;
  }

  updateAnalysis(analysis) {
    if (!analysis) return;

    document.getElementById("peopleCount").textContent =
      analysis.people_count || "-";
    document.getElementById("complianceStatus").textContent =
      analysis.compliance_status || "-";
    document.getElementById("violationCount").textContent = analysis.violations
      ? analysis.violations.length
      : "0";

    // Update compliance status styling
    const statusEl = document.getElementById("complianceStatus");
    statusEl.className =
      analysis.compliance_status === "compliant" ? "status-good" : "status-bad";
  }

  showViolationAlert(violations) {
    const alertsContainer = document.getElementById("violationAlerts");

    violations.forEach((violation) => {
      const alertDiv = document.createElement("div");
      alertDiv.className = "violation-alert";
      alertDiv.innerHTML = `
                <div class="alert-header">⚠️ ${violation.type}</div>
                <div class="alert-time">${new Date().toLocaleTimeString()}</div>
            `;

      alertsContainer.insertBefore(alertDiv, alertsContainer.firstChild);

      while (alertsContainer.children.length > 15) {
        alertsContainer.removeChild(alertsContainer.lastChild);
      }

      alertsContainer.scrollTop = 0;

      // Auto remove after 10 seconds
      setTimeout(() => {
        if (alertDiv.parentNode) {
          alertDiv.remove();
        }
      }, 30000);
    });
  }

  sendQuery() {
    const queryInput = document.getElementById("queryInput");
    const query = queryInput.value.trim();

    if (!query || !this.sessionId) {
      if (!this.sessionId) {
        alert("Please start a live stream first");
      }
      return;
    }

    this.socket.emit("query_live_stream", {
      session_id: this.sessionId,
      query: query,
    });

    queryInput.value = "";
  }

  addQueryToHistory(query, response) {
    const historyContainer = document.getElementById("queryHistory");

    const historyItem = document.createElement("div");
    historyItem.className = "history-item";
    historyItem.innerHTML = `
            <div class="query">${query}</div>
            <div class="response">${response}</div>
        `;

    historyContainer.insertBefore(historyItem, historyContainer.firstChild);

    // Keep only last 10 queries
    while (historyContainer.children.length > 10) {
      historyContainer.removeChild(historyContainer.lastChild);
    }
  }

  updateStreamStatus(status) {
    const statusEl = document.getElementById("streamStatus");
    statusEl.textContent = status;
    statusEl.className = `stream-status status-${status.toLowerCase()}`;
  }

  clearCanvas() {
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    this.ctx.fillStyle = "#333";
    this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
    this.ctx.fillStyle = "#fff";
    this.ctx.font = "20px Arial";
    this.ctx.textAlign = "center";
    this.ctx.fillText(
      "Stream Stopped",
      this.canvas.width / 2,
      this.canvas.height / 2
    );
  }
}

// Initialize when page loads
document.addEventListener("DOMContentLoaded", () => {
  new LiveStreamManager();
});
