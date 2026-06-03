const state = {
  project: null,
  analysis: null,
  selectedObservationId: null,
  map: null,
  mapLayer: null,
};

const palette = ["#5d7cff", "#00c2a8", "#ff8a3d", "#c76bff", "#f95d8e"];

const fileInput = document.getElementById("file-input");
const uploadForm = document.getElementById("upload-form");
const observationList = document.getElementById("observation-list");
const metadataForm = document.getElementById("metadata-form");
const selectedImage = document.getElementById("selected-image");
const imageStage = document.getElementById("image-stage");
const imageMarker = document.getElementById("image-marker");
const reloadButton = document.getElementById("reload-button");
const issuesPanel = document.getElementById("issues");
const resultPanel = document.getElementById("result-panel");

function initMap() {
  if (state.map) return;
  state.map = L.map("map", { worldCopyJump: true }).setView([37.7749, -122.4194], 10);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(state.map);
  state.mapLayer = L.layerGroup().addTo(state.map);
}

function getSelectedObservation() {
  if (!state.project) return null;
  return state.project.observations.find(
    (observation) => observation.observation_id === state.selectedObservationId,
  ) || null;
}

function updateObservationField(field, value) {
  const observation = getSelectedObservation();
  if (!observation) return;

  if (["captured_at", "filename"].includes(field)) {
    observation[field] = value || null;
  } else {
    observation[field] = value === "" ? null : Number(value);
    if (!Number.isFinite(observation[field])) {
      observation[field] = null;
    }
  }
}

function renderObservationList() {
  observationList.innerHTML = "";
  if (!state.project) return;

  const solvedById = new Map(
    (state.analysis?.observations || []).map((observation) => [observation.observation_id, observation]),
  );

  state.project.observations.forEach((observation, index) => {
    const solved = solvedById.get(observation.observation_id);
    const button = document.createElement("button");
    button.type = "button";
    button.className = `observation-button ${observation.observation_id === state.selectedObservationId ? "active" : ""}`;
    button.innerHTML = `
      <strong>${index + 1}. ${observation.filename}</strong>
      <div class="observation-meta">
        <span>${observation.width}×${observation.height}</span>
        <span>${solved?.status || "pending"}</span>
      </div>
    `;
    button.addEventListener("click", () => {
      state.selectedObservationId = observation.observation_id;
      renderSelectedObservation();
      renderObservationList();
    });
    observationList.appendChild(button);
  });
}

function renderSelectedObservation() {
  const observation = getSelectedObservation();
  imageStage.classList.toggle("empty", !observation);
  if (!observation) {
    selectedImage.removeAttribute("src");
    imageMarker.hidden = true;
    metadataForm.reset();
    return;
  }

  selectedImage.src = observation.image_url;
  selectedImage.onload = renderImageMarker;

  for (const element of metadataForm.elements) {
    if (!element.name) continue;
    element.value = observation[element.name] ?? "";
  }
  renderImageMarker();
}

function renderImageMarker() {
  const observation = getSelectedObservation();
  if (!observation || !selectedImage.complete || observation.pixel_row == null || observation.pixel_col == null) {
    imageMarker.hidden = true;
    return;
  }

  const rect = selectedImage.getBoundingClientRect();
  const x = (observation.pixel_col / observation.width) * rect.width;
  const y = (observation.pixel_row / observation.height) * rect.height;
  imageMarker.hidden = false;
  imageMarker.style.left = `${selectedImage.offsetLeft + x}px`;
  imageMarker.style.top = `${selectedImage.offsetTop + y}px`;
}

function renderIssues() {
  issuesPanel.innerHTML = "";
  const issues = state.analysis?.issues || [];
  issues.forEach((issue) => {
    const line = document.createElement("div");
    line.textContent = issue;
    issuesPanel.appendChild(line);
  });
}

function renderResultPanel() {
  const result = state.analysis?.result;
  if (!result) {
    resultPanel.textContent = "Need at least two ready observations to triangulate a result.";
    return;
  }

  resultPanel.textContent = JSON.stringify(result, null, 2);
}

function renderMap() {
  initMap();
  state.mapLayer.clearLayers();

  const bounds = [];
  (state.analysis?.observations || []).forEach((observation, index) => {
    if (!observation.camera_point) return;
    const color = palette[index % palette.length];
    const cameraLatLng = [
      observation.camera_point.latitude,
      observation.camera_point.longitude,
    ];
    bounds.push(cameraLatLng);
    L.circleMarker(cameraLatLng, { radius: 6, color }).addTo(state.mapLayer)
      .bindPopup(`${observation.filename}<br>camera`);

    const sightline = (observation.sightline || []).map((point) => [
      point.latitude,
      point.longitude,
    ]);
    if (sightline.length > 1) {
      sightline.forEach((point) => bounds.push(point));
      L.polyline(sightline, { color, weight: 3, opacity: 0.8 }).addTo(state.mapLayer)
        .bindPopup(`${observation.filename}<br>sight line`);
    }
  });

  const triangulatedLocation = state.analysis?.result?.triangulated_location;
  if (triangulatedLocation) {
    const latLng = [triangulatedLocation.latitude, triangulatedLocation.longitude];
    bounds.push(latLng);
    L.marker(latLng).addTo(state.mapLayer).bindPopup("Triangulated result");
  }

  if (bounds.length) {
    state.map.fitBounds(bounds, { padding: [30, 30] });
  }
}

async function reloadAnalysis() {
  if (!state.project) return;

  const response = await fetch("/api/solve", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      project_id: state.project.project_id,
      observations: state.project.observations,
    }),
  });
  state.analysis = await response.json();
  renderObservationList();
  renderIssues();
  renderResultPanel();
  renderMap();
}

uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!fileInput.files.length) return;

  const formData = new FormData();
  [...fileInput.files].forEach((file) => formData.append("files", file));

  const response = await fetch("/api/projects/upload", {
    method: "POST",
    body: formData,
  });
  state.project = await response.json();
  state.analysis = state.project.analysis;
  state.selectedObservationId = state.project.observations[0]?.observation_id || null;
  reloadButton.disabled = !state.project.observations.length;
  renderObservationList();
  renderSelectedObservation();
  renderIssues();
  renderResultPanel();
  renderMap();
});

metadataForm.addEventListener("input", (event) => {
  if (!event.target.name) return;
  updateObservationField(event.target.name, event.target.value);
  renderImageMarker();
});

reloadButton.addEventListener("click", () => {
  reloadAnalysis();
});

selectedImage.addEventListener("click", (event) => {
  const observation = getSelectedObservation();
  if (!observation) return;

  const rect = selectedImage.getBoundingClientRect();
  const scaleX = observation.width / rect.width;
  const scaleY = observation.height / rect.height;
  const pixelCol = (event.clientX - rect.left) * scaleX;
  const pixelRow = (event.clientY - rect.top) * scaleY;
  observation.pixel_col = Number(pixelCol.toFixed(2));
  observation.pixel_row = Number(pixelRow.toFixed(2));
  renderSelectedObservation();
});

window.addEventListener("resize", renderImageMarker);
initMap();
