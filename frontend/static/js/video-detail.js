class VideoDetailManager {
  constructor() {
    this.videoId = this.getVideoIdFromUrl();
    this.videoData = null;
    this.violations = [];
    this.currentImageIndex = 0;
    this.imageCache = new Map(); // Cache for blob URLs

    if (this.videoId) {
      this.loadVideoDetails();
      this.initializeModal();
    } else {
      this.showError("No video ID provided");
    }
  }

  getVideoIdFromUrl() {
    const pathParts = window.location.pathname.split("/");
    return pathParts[pathParts.length - 1];
  }

  async loadVideoDetails() {
    try {
      const token = localStorage.getItem("ppe_token");
      const response = await fetch(`/api/video/${this.videoId}`, {
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      this.videoData = data.video;
      this.violations = data.violations || [];

      this.renderVideoInfo();
      this.renderAnalysisSummary();
      await this.renderScreenshots(); // Now async
    } catch (error) {
      console.error("Error loading video details:", error);
      this.showError("Failed to load video details");
    }
  }

  // New method to fetch image as blob with authentication
  async fetchImageAsBlob(imagePath) {
    // Check cache first
    if (this.imageCache.has(imagePath)) {
      return this.imageCache.get(imagePath);
    }

    try {
      const token = localStorage.getItem("ppe_token");
      const response = await fetch(`/api/violations/${imagePath}`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        throw new Error(`Failed to load image: ${response.status}`);
      }

      const blob = await response.blob();
      const objectURL = URL.createObjectURL(blob);

      // Cache the object URL
      this.imageCache.set(imagePath, objectURL);

      return objectURL;
    } catch (error) {
      console.error("Error fetching image:", error);
      return null; // Return null so we can show a placeholder
    }
  }

  renderVideoInfo() {
    const section = document.getElementById("videoInfoSection");

    if (!this.videoData) {
      section.innerHTML = '<div class="loading">Video not found</div>';
      return;
    }

    const uploadDate = new Date(this.videoData.upload_time).toLocaleString();
    const processedDate = this.videoData.processed_at
      ? new Date(this.videoData.processed_at).toLocaleString()
      : "Not processed yet";

    section.innerHTML = `
            <h2>${this.videoData.filename}</h2>
            <div class="video-meta-grid">
                <div class="meta-item">
                    <strong>Upload Date:</strong>
                    <span>${uploadDate}</span>
                </div>
                <div class="meta-item">
                    <strong>Processing Status:</strong>
                    <span class="${
                      this.videoData.processed
                        ? "status-processed"
                        : "status-processing"
                    }">
                        ${
                          this.videoData.processed
                            ? "Completed"
                            : "Processing..."
                        }
                    </span>
                </div>
                <div class="meta-item">
                    <strong>Duration:</strong>
                    <span>${this.formatDuration(this.videoData.duration)}</span>
                </div>
                <div class="meta-item">
                    <strong>Total Frames:</strong>
                    <span>${this.videoData.frame_count || "Unknown"}</span>
                </div>
                <div class="meta-item">
                    <strong>Total Violations:</strong>
                    <span class="violation-count">${
                      this.videoData.total_violations || 0
                    }</span>
                </div>
                <div class="meta-item">
                    <strong>Processed Date:</strong>
                    <span>${processedDate}</span>
                </div>
            </div>
        `;
  }

  renderAnalysisSummary() {
    const section = document.getElementById("analysisSummary");

    if (!this.videoData.processed) {
      section.style.display = "none";
      return;
    }

    section.style.display = "block";

    const summary = this.videoData.summary || "No summary available";
    const violationStats = this.generateViolationStats();

    document.getElementById("summaryContent").innerHTML = `
            <div class="summary-text">
                ${summary
                  .split("\n")
                  .map((line) => `<p>${line}</p>`)
                  .join("")}
            </div>
            <div class="violation-breakdown">
                <h3>Violation Breakdown</h3>
                ${violationStats}
            </div>
            <div class="compliance-score">
                <h3>Compliance Score</h3>
                <div class="score-display">
                    ${this.calculateComplianceScore()}%
                </div>
            </div>
        `;
  }

  async renderScreenshots() {
    const section = document.getElementById("screenshotsSection");
    const screenshotsWithImages = this.violations.filter(
      (v) => v.screenshot_path
    );

    if (screenshotsWithImages.length === 0) {
      section.style.display = "none";
      return;
    }

    section.style.display = "block";
    const grid = document.getElementById("screenshotsGrid");

    // Show loading state
    grid.innerHTML =
      '<div class="loading-screenshots">Loading screenshots...</div>';

    // Create screenshot items with loading placeholders
    const screenshotItems = await Promise.all(
      screenshotsWithImages.map(async (violation, index) => {
        const imagePath = this.getRelativeScreenshotPath(
          violation.screenshot_path
        );
        const imageUrl = await this.fetchImageAsBlob(imagePath);

        return `
          <div class="screenshot-item" data-index="${index}">
            ${
              imageUrl
                ? `<img src="${imageUrl}" alt="Violation screenshot" onclick="videoDetailManager.openImageModal(${index})" />`
                : `<div class="screenshot-placeholder" onclick="videoDetailManager.openImageModal(${index})">
                   <span>Image not available</span>
                 </div>`
            }
            <div class="screenshot-info">
              <div class="screenshot-time">${this.formatTimestamp(
                violation.timestamp
              )}</div>
              <div class="screenshot-violation">${
                violation.violation_type
              }</div>
            </div>
          </div>
        `;
      })
    );

    grid.innerHTML = screenshotItems.join("");
  }

  // Initialize the modal HTML
  initializeModal() {
    const modalHTML = `
            <div id="imageModal" class="image-modal">
                <div class="modal-content">
                    <span class="modal-close" onclick="videoDetailManager.closeImageModal()">&times;</span>
                    <button class="modal-nav modal-prev" onclick="videoDetailManager.previousImage()">&#10094;</button>
                    <button class="modal-nav modal-next" onclick="videoDetailManager.nextImage()">&#10095;</button>
                    <div class="modal-image-container">
                        <img id="modalImage" src="" alt="Violation screenshot">
                        <div id="modalImageLoading" class="modal-loading">Loading...</div>
                    </div>
                    <div class="modal-info">
                        <div class="modal-timestamp" id="modalTimestamp"></div>
                        <div class="modal-violation-type" id="modalViolationType"></div>
                        <div class="modal-counter" id="modalCounter"></div>
                    </div>
                </div>
            </div>
        `;

    document.body.insertAdjacentHTML("beforeend", modalHTML);

    // Add keyboard event listeners
    document.addEventListener("keydown", (e) => {
      const modal = document.getElementById("imageModal");
      if (modal.style.display === "flex") {
        if (e.key === "Escape") this.closeImageModal();
        if (e.key === "ArrowLeft") this.previousImage();
        if (e.key === "ArrowRight") this.nextImage();
      }
    });
  }

  // Open the image modal
  async openImageModal(index) {
    const screenshotsWithImages = this.violations.filter(
      (v) => v.screenshot_path
    );
    if (index < 0 || index >= screenshotsWithImages.length) return;

    this.currentImageIndex = index;
    const violation = screenshotsWithImages[index];

    const modal = document.getElementById("imageModal");
    const modalImage = document.getElementById("modalImage");
    const modalImageLoading = document.getElementById("modalImageLoading");
    const modalTimestamp = document.getElementById("modalTimestamp");
    const modalViolationType = document.getElementById("modalViolationType");
    const modalCounter = document.getElementById("modalCounter");

    // Show modal first
    modal.style.display = "flex";
    document.body.style.overflow = "hidden";

    // Show loading state
    modalImageLoading.style.display = "block";
    modalImage.style.display = "none";

    // Set text content
    modalTimestamp.textContent = `Time: ${this.formatTimestamp(
      violation.timestamp
    )}`;
    modalViolationType.textContent = violation.violation_type;
    modalCounter.textContent = `${index + 1} of ${
      screenshotsWithImages.length
    }`;

    // Load image
    const imagePath = this.getRelativeScreenshotPath(violation.screenshot_path);
    const imageUrl = await this.fetchImageAsBlob(imagePath);

    // Hide loading, show image
    modalImageLoading.style.display = "none";

    if (imageUrl) {
      modalImage.src = imageUrl;
      modalImage.style.display = "block";
    } else {
      modalImage.alt = "Image not available";
      modalImage.style.display = "block";
    }
  }

  // Close the image modal
  closeImageModal() {
    const modal = document.getElementById("imageModal");
    modal.style.display = "none";
    document.body.style.overflow = "auto";
  }

  // Navigate to previous image
  previousImage() {
    const screenshotsWithImages = this.violations.filter(
      (v) => v.screenshot_path
    );
    if (this.currentImageIndex > 0) {
      this.openImageModal(this.currentImageIndex - 1);
    } else {
      this.openImageModal(screenshotsWithImages.length - 1);
    }
  }

  // Navigate to next image
  nextImage() {
    const screenshotsWithImages = this.violations.filter(
      (v) => v.screenshot_path
    );
    if (this.currentImageIndex < screenshotsWithImages.length - 1) {
      this.openImageModal(this.currentImageIndex + 1);
    } else {
      this.openImageModal(0);
    }
  }

  // Convert full file path to relative path for API
  getRelativeScreenshotPath(fullPath) {
    return fullPath.replace(/^uploads\/violations\//, "");
  }

  generateViolationStats() {
    if (this.violations.length === 0) {
      return "<p>No violations detected</p>";
    }

    const violationTypes = {};
    this.violations.forEach((violation) => {
      const type = violation.violation_type;
      violationTypes[type] = (violationTypes[type] || 0) + 1;
    });

    const stats = Object.entries(violationTypes)
      .sort(([, a], [, b]) => b - a)
      .map(
        ([type, count]) => `
                <div class="violation-stat">
                    <span class="violation-type">${type}</span>
                    <span class="violation-count">${count} instance${
          count > 1 ? "s" : ""
        }</span>
                </div>
            `
      )
      .join("");

    return `<div class="violation-stats">${stats}</div>`;
  }

  calculateComplianceScore() {
    if (!this.videoData.frame_count || this.videoData.frame_count === 0) {
      return 0;
    }

    const violationFrames = this.violations.length;
    const totalFrames = this.videoData.frame_count;
    const sampleFrames = Math.ceil(totalFrames / 30);

    const complianceScore = Math.max(
      0,
      Math.round(((sampleFrames - violationFrames) / sampleFrames) * 100)
    );
    return complianceScore;
  }

  formatDuration(seconds) {
    if (!seconds || seconds === 0) return "Unknown";

    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const remainingSeconds = Math.floor(seconds % 60);

    if (hours > 0) {
      return `${hours}:${minutes.toString().padStart(2, "0")}:${remainingSeconds
        .toString()
        .padStart(2, "0")}`;
    }
    return `${minutes}:${remainingSeconds.toString().padStart(2, "0")}`;
  }

  formatTimestamp(seconds) {
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.floor(seconds % 60);
    return `${minutes}:${remainingSeconds.toString().padStart(2, "0")}`;
  }

  showError(message) {
    const section = document.getElementById("videoInfoSection");
    section.innerHTML = `
            <div class="error-message">
                <h2>Error</h2>
                <p>${message}</p>
                <button onclick="window.history.back()" class="btn-secondary">Go Back</button>
            </div>
        `;
  }

  // Cleanup method to revoke object URLs when needed
  cleanup() {
    this.imageCache.forEach((objectURL) => {
      URL.revokeObjectURL(objectURL);
    });
    this.imageCache.clear();
  }
}

// Global variable to access from onclick handlers
let videoDetailManager;

// Initialize when page loads
document.addEventListener("DOMContentLoaded", () => {
  videoDetailManager = new VideoDetailManager();
});

// Cleanup when page unloads to prevent memory leaks
window.addEventListener("beforeunload", () => {
  if (videoDetailManager) {
    videoDetailManager.cleanup();
  }
});
