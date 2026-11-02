const state = {
  data: null,
  selectedRoomId: "",
  level: "all",
  search: "",
  zoom: 1,
  panX: 0,
  panY: 0,
  dragging: false,
  lastPointer: null,
  dragDistance: 0,
  dragMode: "orbit",
  yawDeg: -38,
  pitchDeg: 52,
  heightScale: 0.9,
  fit: {
    centerX: 0,
    centerY: 0,
    centerZ: 0,
    modelScale: 1,
    cameraDistance: 4,
  },
};

const FOV_DEG = 45;

const COLORS = {
  room: [0, 109, 255],
  roomDark: [0, 70, 180],
  roomLight: [80, 160, 255],
  furniture: [64, 190, 255],
  furnitureDark: [0, 118, 200],
  building: [255, 255, 255],
  selected: [255, 255, 255],
  black: [5, 5, 5],
  white: [255, 255, 255],
};

const canvas = document.getElementById("mapCanvas");
const ctx = canvas.getContext("2d");
const shell = document.querySelector(".shell");
const levelFilter = document.getElementById("levelFilter");
const searchInput = document.getElementById("searchInput");
const buildingOpacity = document.getElementById("buildingOpacity");
const roomOpacity = document.getElementById("roomOpacity");
const furnitureOpacity = document.getElementById("furnitureOpacity");
const yawControl = document.getElementById("yawControl");
const pitchControl = document.getElementById("pitchControl");
const heightScale = document.getElementById("heightScale");
const buildingOpacityValue = document.getElementById("buildingOpacityValue");
const buildingLegendOpacityValue = document.getElementById("buildingLegendOpacityValue");
const roomOpacityValue = document.getElementById("roomOpacityValue");
const furnitureOpacityValue = document.getElementById("furnitureOpacityValue");
const yawValue = document.getElementById("yawValue");
const pitchValue = document.getElementById("pitchValue");
const heightScaleValue = document.getElementById("heightScaleValue");
const showBuilding = document.getElementById("showBuilding");
const showLabels = document.getElementById("showLabels");
const showFurniture = document.getElementById("showFurniture");
const showEnvelope = document.getElementById("showEnvelope");
const showAllLevels = document.getElementById("showAllLevels");
const fitButton = document.getElementById("fitButton");
const roomList = document.getElementById("roomList");
const detail = document.getElementById("detail");
const loadError = document.getElementById("loadError");
const buildingCount = document.getElementById("buildingCount");
const roomCount = document.getElementById("roomCount");
const furnitureCount = document.getElementById("furnitureCount");
const leftToggle = document.getElementById("leftToggle");
const rightToggle = document.getElementById("rightToggle");

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function rgba(rgb, alpha) {
  return `rgba(${rgb[0]}, ${rgb[1]}, ${rgb[2]}, ${alpha})`;
}

function rooms() {
  if (!state.data) return [];
  const search = state.search.toLowerCase();
  return state.data.rooms.filter((room) => {
    const levelOk = showAllLevels.checked || state.level === "all" || room.level === state.level;
    const searchText = `${room.name} ${room.id} ${room.gml_id}`.toLowerCase();
    return levelOk && (!search || searchText.includes(search));
  });
}

function buildingFallbackFromRooms(visibleRooms) {
  if (!visibleRooms.length) return [];
  const bounds = boundsForItems(visibleRooms);
  if (!bounds) return [];
  const bbox = {
    min_x: bounds.minX,
    min_y: bounds.minY,
    min_z: bounds.minZ,
    max_x: bounds.maxX,
    max_y: bounds.maxY,
    max_z: bounds.maxZ,
  };
  return [{
    id: "__visible_room_envelope_building__",
    gml_id: "derived-from-visible-rooms",
    short_id: "derived",
    type: "Building",
    name: "Derived Visible Building Envelope",
    level: "all",
    bbox,
    center: bboxCenter(bbox),
    size: bboxSize(bbox),
    area_xy: Math.max(0, bbox.max_x - bbox.min_x) * Math.max(0, bbox.max_y - bbox.min_y),
  }];
}

function buildingsForVisibleRooms() {
  if (!state.data) return [];
  const buildings = Array.isArray(state.data.buildings) ? state.data.buildings : [];
  return buildings.length ? buildings : buildingFallbackFromRooms(state.data.rooms || []);
}

function furnitureForVisibleRooms() {
  if (!state.data) return [];
  const visibleRoomIds = new Set(rooms().map((room) => room.id));
  return state.data.furniture.filter((item) => visibleRoomIds.has(item.room_id));
}

function boundsForItems(items) {
  if (!items.length) return null;
  return items.reduce((acc, item) => {
    const box = item.bbox;
    acc.minX = Math.min(acc.minX, box.min_x);
    acc.minY = Math.min(acc.minY, box.min_y);
    acc.minZ = Math.min(acc.minZ, box.min_z);
    acc.maxX = Math.max(acc.maxX, box.max_x);
    acc.maxY = Math.max(acc.maxY, box.max_y);
    acc.maxZ = Math.max(acc.maxZ, box.max_z);
    return acc;
  }, {
    minX: Infinity,
    minY: Infinity,
    minZ: Infinity,
    maxX: -Infinity,
    maxY: -Infinity,
    maxZ: -Infinity,
  });
}

function bboxCenter(bbox) {
  return {
    x: (bbox.min_x + bbox.max_x) / 2,
    y: (bbox.min_y + bbox.max_y) / 2,
    z: (bbox.min_z + bbox.max_z) / 2,
  };
}

function bboxSize(bbox) {
  return {
    x: bbox.max_x - bbox.min_x,
    y: bbox.max_y - bbox.min_y,
    z: bbox.max_z - bbox.min_z,
  };
}

function resizeCanvas() {
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, Math.floor(rect.width * dpr));
  canvas.height = Math.max(1, Math.floor(rect.height * dpr));
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  draw();
}

function bboxCorners(box) {
  return [
    { x: box.min_x, y: box.min_y, z: box.min_z },
    { x: box.max_x, y: box.min_y, z: box.min_z },
    { x: box.max_x, y: box.max_y, z: box.min_z },
    { x: box.min_x, y: box.max_y, z: box.min_z },
    { x: box.min_x, y: box.min_y, z: box.max_z },
    { x: box.max_x, y: box.min_y, z: box.max_z },
    { x: box.max_x, y: box.max_y, z: box.max_z },
    { x: box.min_x, y: box.max_y, z: box.max_z },
  ];
}

function obbCorners(item) {
  const corners = item && item.obb && Array.isArray(item.obb.corners) ? item.obb.corners : null;
  if (!corners || corners.length !== 8) return null;

  const parsed = corners.map((corner) => {
    if (!Array.isArray(corner) || corner.length < 3) return null;
    const [x, y, z] = corner.map(Number);
    if (![x, y, z].every(Number.isFinite)) return null;
    return { x, y, z };
  });
  return parsed.every((corner) => corner !== null) ? parsed : null;
}

function cuboidCorners(item) {
  return obbCorners(item) || bboxCorners(item.bbox);
}

function dot(a, b) {
  return a.x * b.x + a.y * b.y + a.z * b.z;
}

function cross(a, b) {
  return {
    x: a.y * b.z - a.z * b.y,
    y: a.z * b.x - a.x * b.z,
    z: a.x * b.y - a.y * b.x,
  };
}

function normalize(v) {
  const length = Math.hypot(v.x, v.y, v.z) || 1;
  return { x: v.x / length, y: v.y / length, z: v.z / length };
}

function modelPoint(point) {
  return {
    x: (point.x - state.fit.centerX) * state.fit.modelScale,
    y: (point.y - state.fit.centerY) * state.fit.modelScale,
    z: (point.z - state.fit.centerZ) * state.fit.modelScale * state.heightScale,
  };
}

function cameraBasis() {
  const yaw = (state.yawDeg * Math.PI) / 180;
  const pitch = (state.pitchDeg * Math.PI) / 180;
  const distance = Math.max(0.4, state.fit.cameraDistance / state.zoom);
  const cosPitch = Math.cos(pitch);
  const camera = {
    x: distance * cosPitch * Math.sin(yaw),
    y: distance * cosPitch * Math.cos(yaw),
    z: distance * Math.sin(pitch),
  };
  const forward = normalize({ x: -camera.x, y: -camera.y, z: -camera.z });
  const worldUp = { x: 0, y: 0, z: 1 };
  let right = normalize(cross(worldUp, forward));
  if (Math.hypot(right.x, right.y, right.z) < 0.001) {
    right = { x: 1, y: 0, z: 0 };
  }
  const up = normalize(cross(forward, right));
  return { camera, forward, right, up };
}

function rawProject(point) {
  const p = modelPoint(point);
  const basis = cameraBasis();
  const fromCamera = {
    x: p.x - basis.camera.x,
    y: p.y - basis.camera.y,
    z: p.z - basis.camera.z,
  };
  const depth = dot(fromCamera, basis.forward);
  return {
    x: dot(fromCamera, basis.right),
    y: dot(fromCamera, basis.up),
    depth,
    visible: depth > 0.05,
  };
}

function project(point) {
  const rect = canvas.getBoundingClientRect();
  const raw = rawProject(point);
  const fov = (FOV_DEG * Math.PI) / 180;
  const focal = Math.min(rect.width, rect.height) / (2 * Math.tan(fov / 2));
  const depth = Math.max(0.05, raw.depth);
  return {
    x: rect.width / 2 + state.panX + (raw.x * focal) / depth,
    y: rect.height / 2 + state.panY - (raw.y * focal) / depth,
    depth: raw.depth,
    visible: raw.visible,
  };
}

function visibleItemsForFit() {
  const visibleRooms = rooms();
  const visibleFurniture = furnitureForVisibleRooms();
  const visibleBuildings = showBuilding.checked ? buildingsForVisibleRooms() : [];
  return visibleRooms.length
    ? [...visibleBuildings, ...visibleRooms, ...visibleFurniture]
    : [...visibleBuildings, ...state.data.rooms];
}

function computeFit() {
  if (!state.data) return;
  const items = visibleItemsForFit();
  if (!items.length) return;

  const bounds = boundsForItems(items);
  if (!bounds) return;

  state.fit.centerX = (bounds.minX + bounds.maxX) / 2;
  state.fit.centerY = (bounds.minY + bounds.maxY) / 2;
  state.fit.centerZ = (bounds.minZ + bounds.maxZ) / 2;

  const spanX = Math.max(1, bounds.maxX - bounds.minX);
  const spanY = Math.max(1, bounds.maxY - bounds.minY);
  const spanZ = Math.max(1, bounds.maxZ - bounds.minZ) * state.heightScale;
  const maxSpan = Math.max(spanX, spanY, spanZ);
  state.fit.modelScale = 2 / maxSpan;

  let radius = 1;
  items.forEach((item) => {
    bboxCorners(item.bbox).forEach((corner) => {
      const p = modelPoint(corner);
      radius = Math.max(radius, Math.hypot(p.x, p.y, p.z));
    });
  });
  const fov = (FOV_DEG * Math.PI) / 180;
  state.fit.cameraDistance = Math.max(2.8, (radius / Math.sin(fov / 2)) * 1.25);
  state.zoom = 1;
  state.panX = 0;
  state.panY = 0;
}

function facePath(points) {
  ctx.beginPath();
  points.forEach((point, index) => {
    if (index === 0) {
      ctx.moveTo(point.x, point.y);
    } else {
      ctx.lineTo(point.x, point.y);
    }
  });
  ctx.closePath();
}

function drawFace(points, fill, stroke, lineWidth = 1) {
  if (points.some((point) => !point.visible)) return;
  ctx.save();
  facePath(points);
  ctx.fillStyle = fill;
  ctx.strokeStyle = stroke;
  ctx.lineWidth = lineWidth;
  ctx.fill();
  ctx.stroke();
  ctx.restore();
}

function cuboidFaces(item) {
  const corners = cuboidCorners(item).map(project);
  const faces = [
    { name: "bottom", indexes: [0, 1, 2, 3], shade: 0.22 },
    { name: "front", indexes: [0, 1, 5, 4], shade: 0.54 },
    { name: "right", indexes: [1, 2, 6, 5], shade: 0.4 },
    { name: "back", indexes: [2, 3, 7, 6], shade: 0.32 },
    { name: "left", indexes: [3, 0, 4, 7], shade: 0.48 },
    { name: "top", indexes: [4, 5, 6, 7], shade: 0.78 },
  ];
  return faces.map((face) => {
    const points = face.indexes.map((index) => corners[index]);
    const depth = points.reduce((total, point) => total + point.depth, 0) / points.length;
    return { ...face, points, depth };
  });
}

function drawCuboid(item, options) {
  const base = options.rgb;
  const alpha = options.alpha;
  const selected = options.selected;
  const strokeBase = options.strokeRgb || COLORS.white;
  const stroke = selected ? rgba(COLORS.white, 1) : rgba(strokeBase, 0.72);
  const faces = cuboidFaces(item).sort((a, b) => b.depth - a.depth);

  faces.forEach((face) => {
    const shadeAlpha = clamp(alpha * face.shade, 0.03, 1);
    const lineWidth = options.lineWidth || (selected ? 2.4 : 1.1);
    drawFace(face.points, rgba(base, shadeAlpha), stroke, lineWidth);
  });
}

function polygonPointToModelPoint(point) {
  if (!Array.isArray(point) || point.length < 3) return null;
  const [x, y, z] = point;
  if (![x, y, z].every((value) => Number.isFinite(Number(value)))) return null;
  return { x: Number(x), y: Number(y), z: Number(z) };
}

function itemPolygonFaces(item) {
  const polygons = Array.isArray(item.polygons) ? item.polygons : [];
  return polygons.map((polygon, index) => {
    const rings = Array.isArray(polygon.rings) ? polygon.rings : [];
    const outerRing = Array.isArray(rings[0]) ? rings[0] : [];
    const modelPoints = outerRing
      .map(polygonPointToModelPoint)
      .filter((point) => point !== null);
    if (modelPoints.length < 3) return null;

    const points = modelPoints.map(project);
    const depth = points.reduce((total, point) => total + point.depth, 0) / points.length;
    return { index, points, depth };
  }).filter((face) => face !== null);
}

function drawPolygonItem(item, options) {
  const faces = itemPolygonFaces(item).sort((a, b) => b.depth - a.depth);
  if (!faces.length) {
    drawCuboid(item, options);
    return;
  }

  const base = options.rgb;
  const selected = options.selected;
  const stroke = selected ? rgba(COLORS.white, 1) : rgba(COLORS.white, 0.58);
  const lineWidth = selected ? 1.8 : 0.85;

  faces.forEach((face) => {
    drawFace(face.points, rgba(base, clamp(options.alpha * 0.5, 0.03, 0.82)), stroke, lineWidth);
  });

  if (selected) {
    drawCuboid(item, {
      rgb: COLORS.selected,
      alpha: 0.08,
      selected: true,
      strokeRgb: COLORS.white,
      lineWidth: 2,
    });
  }
}

function drawProjectedPolyline(points, stroke, lineWidth, close = false) {
  const visiblePoints = points.filter((point) => point.visible);
  if (visiblePoints.length < 2) return;

  ctx.save();
  ctx.strokeStyle = stroke;
  ctx.lineWidth = lineWidth;
  ctx.beginPath();
  points.forEach((point, index) => {
    if (!point.visible) return;
    if (index === 0) {
      ctx.moveTo(point.x, point.y);
    } else {
      ctx.lineTo(point.x, point.y);
    }
  });
  if (close) ctx.closePath();
  ctx.stroke();
  ctx.restore();
}

function outlineFootprintPoint(point, z) {
  if (!Array.isArray(point) || point.length < 2) return null;
  const [x, y] = point.map(Number);
  if (![x, y, z].every(Number.isFinite)) return null;
  return { x, y, z };
}

function drawFurnitureOutline(item, options) {
  const outline = item && item.outline ? item.outline : null;
  const footprint = outline && Array.isArray(outline.footprint) ? outline.footprint : [];
  const minZ = Number(outline && outline.min_z);
  const maxZ = Number(outline && outline.max_z);
  if (footprint.length < 3 || !Number.isFinite(minZ) || !Number.isFinite(maxZ)) {
    drawCuboid(item, options);
    return;
  }

  const bottom = footprint
    .map((point) => outlineFootprintPoint(point, minZ))
    .filter((point) => point !== null)
    .map(project);
  const top = footprint
    .map((point) => outlineFootprintPoint(point, maxZ))
    .filter((point) => point !== null)
    .map(project);
  if (bottom.length < 3 || top.length < 3) {
    drawCuboid(item, options);
    return;
  }

  const stroke = rgba(options.rgb, clamp(options.alpha, 0.2, 1));
  const faintStroke = rgba(options.rgb, clamp(options.alpha * 0.44, 0.12, 0.65));
  drawProjectedPolyline(bottom, faintStroke, 1, true);
  drawProjectedPolyline(top, stroke, 1.5, true);
  for (let index = 0; index < Math.min(bottom.length, top.length); index += 1) {
    drawProjectedPolyline([bottom[index], top[index]], faintStroke, 1, false);
  }
}

function drawEnvelope(items) {
  if (!showEnvelope.checked || !items.length) return;
  const bounds = items.reduce((acc, item) => {
    const box = item.bbox;
    acc.min_x = Math.min(acc.min_x, box.min_x);
    acc.min_y = Math.min(acc.min_y, box.min_y);
    acc.min_z = Math.min(acc.min_z, box.min_z);
    acc.max_x = Math.max(acc.max_x, box.max_x);
    acc.max_y = Math.max(acc.max_y, box.max_y);
    acc.max_z = Math.max(acc.max_z, box.max_z);
    return acc;
  }, {
    min_x: Infinity,
    min_y: Infinity,
    min_z: Infinity,
    max_x: -Infinity,
    max_y: -Infinity,
    max_z: -Infinity,
  });
  const corners = bboxCorners(bounds).map(project);
  const lines = [
    [0, 1], [1, 2], [2, 3], [3, 0],
    [4, 5], [5, 6], [6, 7], [7, 4],
    [0, 4], [1, 5], [2, 6], [3, 7],
  ];

  ctx.save();
  ctx.strokeStyle = rgba(COLORS.white, 0.88);
  ctx.lineWidth = 2;
  ctx.setLineDash([8, 6]);
  lines.forEach(([a, b]) => {
    ctx.beginPath();
    ctx.moveTo(corners[a].x, corners[a].y);
    ctx.lineTo(corners[b].x, corners[b].y);
    ctx.stroke();
  });
  ctx.setLineDash([]);
  const top = corners.slice(4).reduce((best, point) => (point.y < best.y ? point : best), corners[4]);
  ctx.fillStyle = rgba(COLORS.white, 0.92);
  ctx.font = "800 12px Aptos, Segoe UI, sans-serif";
  ctx.fillText("visible room envelope", top.x + 10, top.y - 10);
  ctx.restore();
}

function drawLabels(visibleRooms) {
  if (!showLabels.checked) return;
  ctx.save();
  ctx.textBaseline = "middle";
  ctx.textAlign = "center";
  visibleRooms.forEach((room) => {
    const p = project({ x: room.center.x, y: room.center.y, z: room.bbox.max_z });
    const label = `${room.name}\n${room.short_id}`;
    const lines = label.split("\n");
    ctx.font = "800 13px Aptos, Segoe UI, sans-serif";
    const width = Math.max(...lines.map((line) => ctx.measureText(line).width)) + 14;
    const height = 36;
    roundedRect(ctx, p.x - width / 2, p.y - height - 10, width, height, 8);
    ctx.fillStyle = rgba(COLORS.black, 1);
    ctx.fillText(lines[0], p.x, p.y - height - 10 + 12);
    ctx.fillStyle = rgba(COLORS.room, 1);
    ctx.font = "700 10px Cascadia Mono, Consolas, monospace";
    ctx.fillText(lines[1], p.x, p.y - height - 10 + 27);
  });
  ctx.restore();
}

function roundedRect(context, x, y, width, height, radius) {
  context.save();
  context.beginPath();
  if (typeof context.roundRect === "function") {
    context.roundRect(x, y, width, height, radius);
  } else {
    const r = Math.min(radius, width / 2, height / 2);
    context.moveTo(x + r, y);
    context.lineTo(x + width - r, y);
    context.quadraticCurveTo(x + width, y, x + width, y + r);
    context.lineTo(x + width, y + height - r);
    context.quadraticCurveTo(x + width, y + height, x + width - r, y + height);
    context.lineTo(x + r, y + height);
    context.quadraticCurveTo(x, y + height, x, y + height - r);
    context.lineTo(x, y + r);
    context.quadraticCurveTo(x, y, x + r, y);
  }
  context.fillStyle = rgba(COLORS.white, 0.92);
  context.strokeStyle = rgba(COLORS.room, 0.78);
  context.lineWidth = 1;
  context.fill();
  context.stroke();
  context.restore();
}

function clearCanvas() {
  const rect = canvas.getBoundingClientRect();
  ctx.clearRect(0, 0, rect.width, rect.height);
}

function draw() {
  clearCanvas();
  if (!state.data) return;

  const visibleRooms = rooms();
  const visibleBuildings = showBuilding.checked ? buildingsForVisibleRooms() : [];
  const visibleFurniture = showFurniture.checked ? furnitureForVisibleRooms() : [];
  const buildingAlpha = Number(buildingOpacity.value);
  const roomAlpha = Number(roomOpacity.value);
  const furnitureAlpha = Number(furnitureOpacity.value);

  drawEnvelope(visibleRooms);

  visibleBuildings.forEach((item) => {
    drawCuboid(item, {
      rgb: COLORS.building,
      alpha: buildingAlpha,
      selected: false,
      strokeRgb: COLORS.room,
      lineWidth: 1.5,
    });
  });

  const drawItems = [
    ...visibleRooms.map((item) => ({ item, kind: "room" })),
    ...visibleFurniture.map((item) => ({ item, kind: "furniture" })),
  ].sort((a, b) => {
    const pa = rawProject(a.item.center);
    const pb = rawProject(b.item.center);
    return pb.depth - pa.depth;
  });

  drawItems.forEach(({ item, kind }) => {
    if (kind === "room") {
      drawPolygonItem(item, {
        rgb: item.id === state.selectedRoomId ? COLORS.selected : COLORS.room,
        alpha: item.id === state.selectedRoomId ? clamp(roomAlpha + 0.18, 0, 1) : roomAlpha,
        selected: item.id === state.selectedRoomId,
      });
    } else {
      drawFurnitureOutline(item, {
        rgb: COLORS.furniture,
        alpha: furnitureAlpha,
        selected: false,
      });
    }
  });

  drawLabels(visibleRooms);
}

function renderList() {
  const visibleRooms = rooms();
  roomList.innerHTML = "";
  visibleRooms.forEach((room) => {
    const row = document.createElement("button");
    row.className = `room-row ${room.id === state.selectedRoomId ? "active" : ""}`;
    row.innerHTML = `
      <strong>${escapeHtml(room.name)}</strong>
      <code>${escapeHtml(room.gml_id)}</code>
      <span>${escapeHtml(room.level)} / furniture ${room.furniture_ids.length}</span>
    `;
    row.addEventListener("click", () => selectRoom(room.id));
    roomList.appendChild(row);
  });
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatNumber(value) {
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: 3 });
}

function selectRoom(roomId) {
  state.selectedRoomId = roomId;
  renderList();
  renderDetail();
  draw();
}

function renderDetail() {
  if (!state.data) {
    detail.innerHTML = "<p>No data loaded.</p>";
    return;
  }
  const room = state.data.rooms.find((item) => item.id === state.selectedRoomId);
  if (!room) {
    detail.innerHTML = "<p>Select a room from the 3D view or list.</p>";
    return;
  }
  const roomFurniture = state.data.furniture.filter((item) => item.room_id === room.id);
  detail.innerHTML = `
    <h3>${escapeHtml(room.name)}</h3>
    <div class="kv">
      <div><span>GML ID</span><code>${escapeHtml(room.gml_id)}</code></div>
      <div><span>Node ID</span><code>${escapeHtml(room.id)}</code></div>
      <div><span>Level</span><strong>${escapeHtml(room.level)}</strong></div>
      <div><span>XY bbox area</span><strong>${formatNumber(room.area_xy)}</strong></div>
      <div><span>Polygon faces</span><strong>${formatNumber(room.polygon_count || 0)}</strong></div>
      <div><span>Center</span><code>x=${formatNumber(room.center.x)}, y=${formatNumber(room.center.y)}, z=${formatNumber(room.center.z)}</code></div>
      <div><span>Size</span><code>x=${formatNumber(room.size.x)}, y=${formatNumber(room.size.y)}, z=${formatNumber(room.size.z)}</code></div>
    </div>
    <h3 style="margin-top: 18px;">Furniture in room (${roomFurniture.length})</h3>
    <div class="furniture-list">
      ${roomFurniture.map((item) => `
        <div class="furniture-card">
          <strong>${escapeHtml(item.name)}</strong><br />
          <code>${escapeHtml(item.gml_id)}</code>
        </div>
      `).join("") || "<p>No furniture linked to this room.</p>"}
    </div>
  `;
}

function populateControls() {
  const levels = state.data.summary.levels || [];
  levelFilter.innerHTML = `<option value="all">All levels</option>` +
    levels.map((level) => `<option value="${escapeHtml(level)}">${escapeHtml(level)}</option>`).join("");
  if (levels.length && state.level === "all") {
    state.level = levels[0];
    levelFilter.value = state.level;
  }
  buildingCount.textContent = state.data.summary.building_count || (state.data.buildings || []).length || 0;
  roomCount.textContent = state.data.summary.room_count;
  furnitureCount.textContent = state.data.summary.furniture_count;
}

function updateControlLabels() {
  const buildingOpacityText = Number(buildingOpacity.value).toFixed(2);
  buildingOpacityValue.textContent = buildingOpacityText;
  buildingLegendOpacityValue.textContent = buildingOpacityText;
  roomOpacityValue.textContent = Number(roomOpacity.value).toFixed(2);
  furnitureOpacityValue.textContent = Number(furnitureOpacity.value).toFixed(2);
  yawValue.textContent = `${state.yawDeg}deg`;
  pitchValue.textContent = `${state.pitchDeg}deg`;
  heightScaleValue.textContent = Number(state.heightScale).toFixed(2);
}

function pointInPolygon(point, polygon) {
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const pi = polygon[i];
    const pj = polygon[j];
    const intersects = ((pi.y > point.y) !== (pj.y > point.y)) &&
      (point.x < ((pj.x - pi.x) * (point.y - pi.y)) / (pj.y - pi.y + Number.EPSILON) + pi.x);
    if (intersects) inside = !inside;
  }
  return inside;
}

function roomHitFaces(room) {
  const polygonFaces = itemPolygonFaces(room);
  if (polygonFaces.length) return polygonFaces;
  const topFace = cuboidFaces(room).find((face) => face.name === "top");
  return topFace ? [topFace] : [];
}

function roomAtCanvasPoint(x, y) {
  const candidates = rooms().filter((room) => {
    return roomHitFaces(room).some((face) => pointInPolygon({ x, y }, face.points));
  });
  candidates.sort((a, b) => {
    const pa = project(a.center);
    const pb = project(b.center);
    const da = Math.hypot(pa.x - x, pa.y - y);
    const db = Math.hypot(pb.x - x, pb.y - y);
    return da - db;
  });
  return candidates[0] || null;
}

canvas.addEventListener("pointerdown", (event) => {
  state.dragging = true;
  state.lastPointer = { x: event.clientX, y: event.clientY };
  state.dragDistance = 0;
  state.dragMode = event.shiftKey || event.button === 1 ? "pan" : "orbit";
  canvas.setPointerCapture(event.pointerId);
});

canvas.addEventListener("pointermove", (event) => {
  if (!state.dragging || !state.lastPointer) return;
  const dx = event.clientX - state.lastPointer.x;
  const dy = event.clientY - state.lastPointer.y;
  if (Math.abs(dx) + Math.abs(dy) > 1) {
    if (state.dragMode === "pan") {
      state.panX += dx;
      state.panY += dy;
    } else {
      state.yawDeg = ((state.yawDeg + dx * 0.35 + 540) % 360) - 180;
      state.pitchDeg = clamp(state.pitchDeg - dy * 0.25, -5, 82);
      yawControl.value = String(Math.round(state.yawDeg));
      pitchControl.value = String(Math.round(state.pitchDeg));
      updateControlLabels();
    }
    state.dragDistance += Math.abs(dx) + Math.abs(dy);
    state.lastPointer = { x: event.clientX, y: event.clientY };
    draw();
  }
});

canvas.addEventListener("contextmenu", (event) => {
  event.preventDefault();
});

canvas.addEventListener("pointerup", (event) => {
  state.dragging = false;
  state.lastPointer = null;
  canvas.releasePointerCapture(event.pointerId);
  if (state.dragDistance > 4) return;
  const rect = canvas.getBoundingClientRect();
  const room = roomAtCanvasPoint(event.clientX - rect.left, event.clientY - rect.top);
  if (room) selectRoom(room.id);
});

canvas.addEventListener("wheel", (event) => {
  event.preventDefault();
  const zoomFactor = event.deltaY < 0 ? 1.12 : 0.89;
  state.zoom = clamp(state.zoom * zoomFactor, 0.1, 24);
  draw();
}, { passive: false });

levelFilter.addEventListener("change", () => {
  state.level = levelFilter.value;
  computeFit();
  renderList();
  draw();
});

searchInput.addEventListener("input", () => {
  state.search = searchInput.value.trim();
  computeFit();
  renderList();
  draw();
});

[buildingOpacity, roomOpacity, furnitureOpacity].forEach((input) => input.addEventListener("input", () => {
  updateControlLabels();
  draw();
}));

yawControl.addEventListener("input", () => {
  state.yawDeg = Number(yawControl.value);
  updateControlLabels();
  draw();
});

pitchControl.addEventListener("input", () => {
  state.pitchDeg = Number(pitchControl.value);
  updateControlLabels();
  draw();
});

heightScale.addEventListener("input", () => {
  state.heightScale = Number(heightScale.value);
  updateControlLabels();
  computeFit();
  draw();
});

[showLabels, showFurniture, showEnvelope].forEach((input) => {
  input.addEventListener("change", draw);
});

showBuilding.addEventListener("change", () => {
  computeFit();
  draw();
});

showAllLevels.addEventListener("change", () => {
  levelFilter.disabled = showAllLevels.checked;
  computeFit();
  renderList();
  draw();
});

leftToggle.addEventListener("click", () => {
  shell.classList.toggle("left-collapsed");
  window.setTimeout(() => {
    resizeCanvas();
    computeFit();
    draw();
  }, 0);
});

rightToggle.addEventListener("click", () => {
  shell.classList.toggle("right-collapsed");
  window.setTimeout(() => {
    resizeCanvas();
    computeFit();
    draw();
  }, 0);
});

fitButton.addEventListener("click", () => {
  computeFit();
  draw();
});

window.addEventListener("resize", () => {
  resizeCanvas();
  computeFit();
  draw();
});

async function load() {
  state.yawDeg = Number(yawControl.value);
  state.pitchDeg = Number(pitchControl.value);
  state.heightScale = Number(heightScale.value);
  updateControlLabels();
  try {
    const response = await fetch("etype_room_dashboard_data.json", { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    state.data = await response.json();
    populateControls();
    resizeCanvas();
    computeFit();
    const visibleRooms = rooms();
    if (visibleRooms[0]) {
      state.selectedRoomId = visibleRooms[0].id;
    } else if (state.data.rooms[0]) {
      state.selectedRoomId = state.data.rooms[0].id;
    }
    renderList();
    renderDetail();
    draw();
  } catch (error) {
    loadError.hidden = false;
    loadError.innerHTML = `
      Dashboard data was not found. Generate it first, then serve this directory over localhost.<br />
      <code>python scripts/world_graph/build_etype_room_dashboard_data.py --input data/output/e_type_import.json --output web/etype_room_dashboard/etype_room_dashboard_data.json</code>
    `;
    detail.innerHTML = "<p>Waiting for dashboard data.</p>";
  }
}

load();
