class VideoGridManager {
  constructor() {
    this.videos = [];
    this.filteredVideos = [];

    this.setupEventListeners();
    this.loadVideos();
  }

  setupEventListeners() {
    // Filter and search
    document
      .getElementById("statusFilter")
      .addEventListener("change", () => this.filterVideos());
    document
      .getElementById("searchInput")
      .addEventListener("input", () => this.filterVideos());

    // Multi-upload
    const multiUpload = document.getElementById("multiVideoUpload");
    multiUpload.addEventListener("change", (e) => this.handleMultiUpload(e));

    // Delete modal
    document
      .getElementById("confirmDelete")
      .addEventListener("click", () => this.confirmDelete());
    document
      .getElementById("cancelDelete")
      .addEventListener("click", () => this.cancelDelete());

    // Download modal - with null checks
    const confirmDownload = document.getElementById("confirmDownload");
    const cancelDownload = document.getElementById("cancelDownload");

    if (confirmDownload) {
      confirmDownload.addEventListener("click", () => this.confirmDownload());
    }
    if (cancelDownload) {
      cancelDownload.addEventListener("click", () => this.cancelDownload());
    }
  }

  async loadVideos() {
    try {
      const token = localStorage.getItem("ppe_token");
      const response = await fetch("/api/videos", {
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      this.videos = await response.json();
      this.filteredVideos = [...this.videos];
      this.renderVideoDetails();
    } catch (error) {
      console.error("Error loading videos:", error);
      this.showError("Failed to load videos");
    }
  }

  filterVideos() {
    const statusFilter = document.getElementById("statusFilter").value;
    const searchTerm = document
      .getElementById("searchInput")
      .value.toLowerCase();

    this.filteredVideos = this.videos.filter((video) => {
      // Status filter
      let statusMatch = true;
      if (statusFilter === "processed") {
        statusMatch = video.processed === true;
      } else if (statusFilter === "processing") {
        statusMatch = video.processed === false;
      } else if (statusFilter === "violations") {
        statusMatch = (video.total_violations || 0) > 0;
      }

      // Search filter
      const searchMatch =
        !searchTerm ||
        video.filename.toLowerCase().includes(searchTerm) ||
        (video.summary && video.summary.toLowerCase().includes(searchTerm));

      return statusMatch && searchMatch;
    });

    this.renderVideoDetails();
  }

  showDownloadModal(videoId) {
    const modal = document.getElementById("downloadModal");
    const message = document.getElementById("downloadMessage");
    const infoDiv = document.getElementById("downloadInfo");

    this.videoToDownload = videoId;

    const video = this.videos.find((v) => (v._id || v.id) === videoId);
    if (video) {
      message.textContent = `Download "${video.filename}"?`;
      infoDiv.innerHTML = `
            <div class="download-details">
                <p><strong>Size:</strong> ${this.formatFileSize(
                  video.file_size || 0
                )}</p>
                <p><strong>Duration:</strong> ${this.formatDuration(
                  video.duration
                )}</p>
                <p><strong>Status:</strong> ${
                  this.getVideoStatus(video).text
                }</p>
            </div>
        `;
    } else {
      message.textContent = "Download this video?";
      infoDiv.innerHTML = "";
    }

    modal.style.display = "flex";
  }

  async confirmDownload() {
    if (!this.videoToDownload) return;

    const downloadBtn = document.getElementById("confirmDownload");
    const originalText = downloadBtn.textContent;

    try {
      downloadBtn.textContent = "Downloading...";
      downloadBtn.disabled = true;

      const token = localStorage.getItem("ppe_token");

      // Fetch with Authorization header
      const response = await fetch(`/api/download/${this.videoToDownload}`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || "Download failed");
      }

      // Convert to blob & trigger browser download
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${this.videoToDownload}.mp4`; // or pull filename from Content-Disposition header
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);

      this.cancelDownload();
    } catch (error) {
      console.error("Download error:", error);
      alert(`Download failed: ${error.message}`);
    } finally {
      downloadBtn.textContent = originalText;
      downloadBtn.disabled = false;
    }
  }

  cancelDownload() {
    document.getElementById("downloadModal").style.display = "none";
    this.videoToDownload = null;
  }

  async confirmDelete() {
    if (!this.videosToDelete) return;

    const deleteBtn = document.getElementById("confirmDelete");
    const originalText = deleteBtn.textContent;

    try {
      deleteBtn.textContent = "Deleting...";
      deleteBtn.disabled = true;

      const token = localStorage.getItem("ppe_token");

      // Delete each video
      for (const videoId of this.videosToDelete) {
        const response = await fetch(`/api/videos/${videoId}`, {
          method: "DELETE",
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });

        if (!response.ok) {
          const error = await response.json();
          throw new Error(error.error || "Delete failed");
        }
      }

      // Remove from local state
      this.videos = this.videos.filter(
        (v) => !this.videosToDelete.includes(v._id || v.id)
      );
      this.filteredVideos = this.filteredVideos.filter(
        (v) => !this.videosToDelete.includes(v._id || v.id)
      );

      this.renderVideoDetails();
      this.cancelDelete();
    } catch (error) {
      console.error("Delete error:", error);
      alert(`Delete failed: ${error.message}`);
    } finally {
      deleteBtn.textContent = originalText;
      deleteBtn.disabled = false;
    }
  }

  renderVideoDetails() {
    const detailsBody = document.getElementById("videoDetailsBody");

    if (this.filteredVideos.length === 0) {
      detailsBody.innerHTML = `
                <div class="loading-placeholder">
                    No videos found. Upload some videos to get started.
                </div>
            `;
      return;
    }

    detailsBody.innerHTML = this.filteredVideos
      .map((video) => this.createVideoDetailRow(video))
      .join("");

    // Re-initialize Lucide icons
    lucide.createIcons();

    this.attachDetailRowHandlers();
  }

  createVideoDetailRow(video) {
    const uploadDate = new Date(
      video.upload_time || Date.now()
    ).toLocaleDateString();
    const status = this.getVideoStatus(video);
    const fileSize = video.file_size
      ? this.formatFileSize(video.file_size)
      : "Unknown";

    return `
            <div class="details-row" data-video-id="${video._id || video.id}">
                <div class="name-column">
                    <div class="file-icon">
                        <i data-lucide="play-circle" class="video-file-icon"></i>
                    </div>
                    <div class="file-info">
                        <span class="file-name" title="${video.filename}">${
      video.filename
    }</span>
                        <span class="file-type">Video</span>
                    </div>
                </div>
                <div class="status-column">
                    <span class="status-badge ${status.class}">${
      status.text
    }</span>
                </div>
                <div class="duration-column">${this.formatDuration(
                  video.duration
                )}</div>
                <div class="violations-column">
                    <span class="violations-count ${
                      (video.total_violations || 0) > 0 ? "has-violations" : ""
                    }">
                        ${video.total_violations || 0}
                    </span>
                </div>
                <div class="date-column">${uploadDate}</div>
                <div class="size-column">${fileSize}</div>
                <div class="actions-column">
                    <button class="action-btn download-btn" data-video-id="${
                      video._id || video.id
                    }" title="Download">
                        <i data-lucide="download"></i>
                    </button>
                    <button class="action-btn delete-btn" data-video-id="${
                      video._id || video.id
                    }" title="Delete">
                        <i data-lucide="trash-2"></i>
                    </button>
                </div>
            </div>
        `;
  }

  attachDetailRowHandlers() {
    // Row click -> go to details
    document.querySelectorAll(".details-row").forEach((row) => {
      row.addEventListener("click", (e) => {
        if (e.target.closest(".action-btn")) return;
        const videoId = row.dataset.videoId;
        window.location.href = `/video-detail/${videoId}`;
      });
    });

    document.querySelectorAll(".download-btn").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        this.showDownloadModal(btn.dataset.videoId);
      });
    });

    document.querySelectorAll(".delete-btn").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        this.showDeleteModal([btn.dataset.videoId]);
      });
    });
  }

  getVideoStatus(video) {
    if (video.processed === true) {
      return { text: "Processed", class: "status-processed" };
    } else if (video.processed === false) {
      return { text: "Processing", class: "status-processing" };
    } else {
      return { text: "Pending", class: "status-pending" };
    }
  }

  formatDuration(seconds) {
    if (!seconds || seconds === 0) return "Unknown";
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.floor(seconds % 60);
    return `${minutes}:${remainingSeconds.toString().padStart(2, "0")}`;
  }

  formatFileSize(bytes) {
    if (!bytes) return "Unknown";
    const sizes = ["Bytes", "KB", "MB", "GB"];
    if (bytes === 0) return "0 Bytes";
    const i = parseInt(Math.floor(Math.log(bytes) / Math.log(1024)));
    return Math.round((bytes / Math.pow(1024, i)) * 100) / 100 + " " + sizes[i];
  }

  showDeleteModal(videoIds) {
    const modal = document.getElementById("deleteModal");
    const message = document.getElementById("deleteMessage");

    this.videosToDelete = videoIds;

    if (videoIds.length === 1) {
      const video = this.videos.find((v) => (v._id || v.id) === videoIds[0]);
      message.textContent = `Are you sure you want to delete "${
        video ? video.filename : "this video"
      }"?`;
    } else {
      message.textContent = `Are you sure you want to delete ${videoIds.length} videos?`;
    }

    modal.style.display = "flex";
  }

  cancelDelete() {
    document.getElementById("deleteModal").style.display = "none";
    this.videosToDelete = null;
  }

  async handleMultiUpload(event) {
    const files = Array.from(event.target.files);
    if (files.length === 0) return;

    const progressContainer = document.getElementById("uploadProgress");
    progressContainer.innerHTML =
      '<div class="upload-progress-title">Uploading videos...</div>';

    let completed = 0;
    const total = files.length;

    for (const file of files) {
      try {
        await this.uploadSingleVideo(file);
        completed++;

        progressContainer.innerHTML = `
                    <div class="upload-progress-title">Uploading videos... (${completed}/${total})</div>
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: ${
                          (completed / total) * 100
                        }%"></div>
                    </div>
                `;
      } catch (error) {
        console.error(`Failed to upload ${file.name}:`, error);
        progressContainer.innerHTML += `<div class="upload-error">Failed: ${file.name}</div>`;
      }
    }

    if (completed === total) {
      progressContainer.innerHTML =
        '<div class="upload-success">All videos uploaded successfully!</div>';
      setTimeout(() => {
        progressContainer.innerHTML = "";
        this.loadVideos(); // Refresh the grid
      }, 2000);
    }

    event.target.value = ""; // Reset file input
  }

  async uploadSingleVideo(file) {
    const formData = new FormData();
    formData.append("video", file);

    const token = localStorage.getItem("ppe_token");
    const response = await fetch("/api/upload", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
      },
      body: formData,
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const result = await response.json();
    if (!result.success) {
      throw new Error(result.error || "Upload failed");
    }

    return result;
  }

  showError(message) {
    const container = document.getElementById("videoDetailsBody");

    container.innerHTML = `
            <div class="loading-placeholder error">
                ${message}
                <br><br>
                <button class="btn-primary" onclick="location.reload()">Reload Page</button>
            </div>
        `;
  }
}

// Initialize when page loads
document.addEventListener("DOMContentLoaded", () => {
  new VideoGridManager();
});
