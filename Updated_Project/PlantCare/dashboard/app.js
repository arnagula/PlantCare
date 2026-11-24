'use strict';

const byId = id => document.getElementById(id);
// The four plant measurements; soil moisture and light are the main ones.
// scale: bar range (light above 3000 lux, i.e. direct sun, shows as a full bar).
// below/above: status pill text when a reading is outside its ideal range.
const metrics = [
  { key: 'soil_pct', icon: '🪴', name: 'Soil moisture', unit: '%', scale: [0, 100], below: 'Needs water', above: 'Overwatered' },
  { key: 'light_lux', icon: '☀️', name: 'Light', unit: 'lux', note: ' (daytime only)', scale: [0, 3000], below: 'Needs light', above: 'Very bright' },
  { key: 'temperature_c', icon: '🌡️', name: 'Temperature', unit: '°C', scale: [0, 40], below: 'Too cold', above: 'Too warm' },
  { key: 'humidity_pct', icon: '💦', name: 'Humidity', unit: '% RH', scale: [0, 100], below: 'Low', above: 'High' },
];
const metricByKey = new Map(metrics.map(metric => [metric.key, metric]));
const HISTORY_MS = 30 * 60 * 1000;
const SVG = 'http://www.w3.org/2000/svg';
// Plant condition from the backend -> [emoji, title, recommended action].
const conditions = new Map([
  ['happy', ['😊', 'Healthy', 'All readings are within the ideal range. No action needed.']],
  ['thirsty', ['💧', 'Needs water', 'Soil moisture is below the ideal range. Water until the soil is evenly moist.']],
  ['too_wet', ['🌊', 'Overwatered', 'Soil moisture is above the ideal range. Let the soil dry out and check that the pot drains.']],
  ['too_hot', ['🔥', 'Too warm', 'Temperature is above the ideal range. Move the plant away from heat sources.']],
  ['too_cold', ['❄️', 'Too cold', 'Temperature is below the ideal range. Move the plant away from cold drafts and windows.']],
  ['low_light', ['🌥️', 'Needs more light', 'Light is below the ideal range. Move the plant to brighter, indirect light.']],
  ['low_humidity', ['🏜️', 'Low humidity', 'Humidity is below the ideal range. Mist the leaves or place a humidifier nearby.']],
]);
const unknownCondition = ['❔', 'Status unavailable', 'Waiting for fresh readings from the sensor.'];
const modes = new Map([
  ['live', { banner: 'Live plant', ok: 'Receiving live measurements' }],
  ['simulated', { banner: 'Simulated plant', ok: 'Receiving simulated measurements' }],
]);
// API status -> badge kind. Uncalibrated soil is shown on the soil card, so the plant still counts as online.
const statuses = new Map([
  ['ok', 'ok'],
  ['uncalibrated', 'ok'],
  ['invalid', 'partial'],
]);
// Badge kind -> [short label, longer hover text]. Colours live in style.css.
const badges = {
  ok: ['Online', null],
  partial: ['Partial data', 'Some measurements are unavailable'],
  stale: ['Offline', 'No fresh measurements'],
  error: ['Connection error', 'Telemetry connection unavailable'],
  waiting: ['Connecting…', 'Waiting for telemetry'],
};
let mode = 'live';
let generation = 0;
let inFlight = null;
let expiresAt = 0;
let thresholds = null; // last thresholds received for the current mode
// Readings seen since the page opened (or the mode last changed): key -> [{t, v}].
let history = new Map();
let lastSampleTime = null;

let selected = 'soil_pct'; // metric shown in the detail panel
let lastReadings = null;

function recordSample(sampleTime, readings) {
  const t = sampleTime.getTime();
  if (t === lastSampleTime) return; // same sample fetched again: no new point
  lastSampleTime = t;
  for (const { key } of metrics) {
    const points = (history.get(key) || []).filter(point => point.t < t && point.t > t - HISTORY_MS);
    if (Number.isFinite(readings?.[key])) points.push({ t, v: readings[key] });
    history.set(key, points);
  }
}

function resetHistory() {
  history = new Map();
  lastSampleTime = null;
}

// ---- small helpers -------------------------------------------------------

function withUnit(value, unit) {
  return [value, unit].join(' ').trim();
}

// 1596 -> "1.6k" for light; other metrics keep up to one decimal.
function formatValue(key, value) {
  if (key === 'light_lux' && Math.abs(value) >= 1000) return (Math.round(value / 100) / 10) + 'k';
  return String(Math.round(value * 10) / 10);
}

function element(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text !== undefined) el.textContent = text;
  return el;
}

function svgElement(tag, attributes) {
  const el = document.createElementNS(SVG, tag);
  for (const [name, value] of Object.entries(attributes)) el.setAttribute(name, value);
  return el;
}

function bounds(key) {
  const low = thresholds?.[key]?.low;
  const high = thresholds?.[key]?.high;
  return [Number.isFinite(low) ? low : null, Number.isFinite(high) ? high : null];
}

function hasBounds(key) {
  return bounds(key).some(v => v !== null);
}

function percent(value, [min, max]) {
  return Math.round(Math.min(100, Math.max(0, (value - min) / (max - min) * 100)) * 100) / 100;
}

function idealText(key) {
  const { unit, note = '' } = metricByKey.get(key);
  if (!thresholds) return '';
  const [low, high] = bounds(key);
  if (low !== null && high !== null) return 'Ideal ' + withUnit(low + '–' + high, unit) + note;
  if (low !== null) return 'Ideal ≥ ' + withUnit(low, unit) + note;
  if (high !== null) return 'Ideal ≤ ' + withUnit(high, unit) + note;
  return key === 'soil_pct' ? 'Not calibrated yet' : 'Threshold not set';
}

// Status pill: [text, tone] where tone is good, warn or muted.
function status(key, value) {
  const metric = metricByKey.get(key);
  if (key === 'soil_pct' && thresholds && !hasBounds(key)) return ['Not calibrated', 'muted'];
  if (!Number.isFinite(value)) return ['No data', 'muted'];
  const [low, high] = bounds(key);
  if (low !== null && value < low) return [metric.below, 'warn'];
  if (high !== null && value > high) return [metric.above, 'warn'];
  return hasBounds(key) ? ['Good', 'good'] : ['No range', 'muted'];
}

function shortTime(t) {
  const date = new Date(t);
  return (date.getHours() % 12 || 12) + ':' + String(date.getMinutes()).padStart(2, '0') + (date.getHours() < 12 ? ' AM' : ' PM');
}

// Widen [min, max] to round numbers and return about four evenly spaced ticks.
// The first and last tick are the axis minimum and maximum, so both ends are always labelled.
function niceAxis(min, max, [floor, ceiling]) {
  const raw = (max - min) / 3;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map(m => m * magnitude).find(s => s >= raw);
  const low = Math.max(floor, Math.floor(min / step + 1e-9) * step);
  const high = Math.min(ceiling, Math.ceil(max / step - 1e-9) * step);
  const values = [];
  for (let v = low; v <= high + step * 1e-9; v += step) values.push(Math.round(v * 1000) / 1000);
  if (values.at(-1) < high) values.push(high);
  return { min: low, max: high, ticks: values };
}

// y-range fitted to the readings and thresholds, clamped to the metric's scale.
function valueRange(points, key) {
  const { scale } = metricByKey.get(key);
  const values = points.map(point => point.v).concat(bounds(key).filter(v => v !== null));
  let min = Math.max(scale[0], Math.min(...values));
  let max = Math.min(scale[1], Math.max(...values));
  const spread = Math.max(max - min, (scale[1] - scale[0]) * 0.05);
  min = Math.max(scale[0], min - spread * 0.15);
  max = Math.min(scale[1], max + spread * 0.15);
  return max > min ? [min, max] : [min, min + 1];
}

// ---- pieces of a card ----------------------------------------------------

function iconTile(icon) {
  const tile = element('span', 'icon-tile', icon);
  tile.setAttribute('aria-hidden', 'true');
  return tile;
}

function pill(key, value) {
  const [text, tone] = status(key, value);
  const el = element('span', 'pill', text);
  el.dataset.tone = tone;
  return el;
}

function valueLine(key, value) {
  const { unit } = metricByKey.get(key);
  const el = element('span', 'value');
  if (Number.isFinite(value)) {
    el.append(element('span', 'number', formatValue(key, value)), element('span', 'unit', unit));
  } else {
    el.classList.add('missing');
    el.append(element('span', 'number', '—'));
    el.setAttribute('aria-label', 'Unavailable');
  }
  return el;
}

// Bar: green ideal zone, a marker line at the current value, and "0 · Ideal … · max" labels.
function renderBar(key, value) {
  const { unit, scale } = metricByKey.get(key);
  const [low, high] = bounds(key);
  const bar = element('span', 'bar');
  const track = element('span', 'bar-track');
  if (low !== null || high !== null) {
    const zone = element('span', 'bar-zone');
    const from = percent(low ?? scale[0], scale);
    const width = Math.round((percent(high ?? scale[1], scale) - from) * 100) / 100;
    zone.style.left = from + '%';
    zone.style.width = width + '%';
    zone.title = 'Ideal range';
    track.append(zone);
  }
  if (Number.isFinite(value)) {
    const marker = element('span', 'bar-marker');
    marker.style.left = percent(value, scale) + '%';
    marker.dataset.outside = String(status(key, value)[1] === 'warn');
    track.append(marker);
  }
  const labels = element('span', 'bar-scale');
  const unitSuffix = unit.startsWith('%') ? '%' : '';
  labels.append(
    element('span', 'end', scale[0] + unitSuffix),
    element('span', 'ideal', idealText(key).replace(' (daytime only)', '')),
    element('span', 'end', formatValue(key, scale[1]) + unitSuffix),
  );
  bar.append(track, labels);
  return bar;
}

// Small trend line in a shaded box, with dotted lines at the ideal limits.
function sparkline(key) {
  const points = history.get(key) || [];
  const width = 200;
  const height = 40;
  const svg = svgElement('svg', { class: 'sparkline', viewBox: `0 0 ${width} ${height}`, preserveAspectRatio: 'none' });
  svg.setAttribute('aria-hidden', 'true');
  for (const gy of [3, height / 2, height - 3]) {
    svg.append(svgElement('line', { class: 'spark-grid', x1: 0, x2: width, y1: gy, y2: gy }));
  }
  if (points.length < 2) {
    svg.append(svgElement('line', { class: 'spark-empty', x1: 0, x2: width, y1: height / 2, y2: height / 2 }));
    return svg;
  }
  // Range covers the readings and the thresholds, so the limit lines are always in view.
  const [min, max] = valueRange(points, key);
  const y = v => (3 + (1 - (v - min) / (max - min)) * (height - 6)).toFixed(1);
  for (const threshold of bounds(key)) {
    if (threshold === null || threshold < min || threshold > max) continue;
    svg.append(svgElement('line', { class: 'spark-threshold', x1: 0, x2: width, y1: y(threshold), y2: y(threshold) }));
  }
  const t0 = points[0].t;
  const span = Math.max(points.at(-1).t - t0, 1);
  const coords = points.map(p => ((p.t - t0) / span * width).toFixed(1) + ',' + y(p.v));
  svg.append(svgElement('polyline', { class: 'spark-line', points: coords.join(' ') }));
  return svg;
}

// ---- large chart for the detail panel ------------------------------------

function renderChart(key) {
  const { name, unit } = metricByKey.get(key);
  const width = 640;
  const height = 260;
  const pad = { left: 52, right: 44, top: 28, bottom: 28 };
  const points = history.get(key) || [];
  const [low, high] = bounds(key);
  const svg = svgElement('svg', { class: 'chart', viewBox: `0 0 ${width} ${height}`, role: 'img' });
  svg.setAttribute('aria-label', name + ': ' + points.length + ' readings in the last 30 minutes');
  const text = (className, content, attributes) => {
    const el = svgElement('text', { class: className, ...attributes });
    el.textContent = content;
    svg.append(el);
  };
  if (points.length === 0) {
    const message = key === 'soil_pct' && thresholds && !hasBounds(key) ? 'Waiting for soil calibration' : 'Collecting data…';
    text('chart-empty', message, { x: width / 2, y: height / 2, 'text-anchor': 'middle' });
    return svg;
  }
  const axis = niceAxis(...valueRange(points, key), metricByKey.get(key).scale);
  const yMin = axis.min;
  const yMax = axis.max;
  const yTicks = axis.ticks;
  const tLast = points.at(-1).t;
  const tFirst = Math.min(points[0].t, tLast - 60 * 1000);
  const x = t => pad.left + (t - tFirst) / (tLast - tFirst) * (width - pad.left - pad.right);
  const y = v => pad.top + (1 - (Math.min(yMax, Math.max(yMin, v)) - yMin) / (yMax - yMin)) * (height - pad.top - pad.bottom);
  // Green band for the ideal range.
  if (low !== null || high !== null) {
    const top = y(Math.min(high ?? yMax, yMax));
    const bottom = y(Math.max(low ?? yMin, yMin));
    if (bottom > top) svg.append(svgElement('rect', { class: 'chart-zone', x: pad.left, y: top, width: width - pad.left - pad.right, height: bottom - top }));
  }
  // Value axis: gridlines with numbers on the left; the top and bottom labels are the axis max and min.
  for (const tick of yTicks) {
    svg.append(svgElement('line', { class: 'chart-grid', x1: pad.left, x2: width - pad.right, y1: y(tick), y2: y(tick) }));
    const end = tick === yMin || tick === yMax;
    text(end ? 'chart-axis chart-axis-end' : 'chart-axis', tick.toLocaleString(), { x: pad.left - 8, y: y(tick) + 4, 'text-anchor': 'end' });
  }
  text('chart-axis chart-unit', unit, { x: pad.left - 8, y: pad.top - 12, 'text-anchor': 'end' });
  // Time axis: start, middle and latest sample times.
  const baseline = height - pad.bottom;
  svg.append(svgElement('line', { class: 'chart-baseline', x1: pad.left, x2: width - pad.right, y1: baseline, y2: baseline }));
  for (const [t, anchor] of [[tFirst, 'start'], [(tFirst + tLast) / 2, 'middle'], [tLast, 'end']]) {
    text('chart-axis', shortTime(t), { x: x(t), y: height - 8, 'text-anchor': anchor });
  }
  // Ideal limits: dashed lines labelled on the right.
  for (const threshold of [low, high]) {
    if (threshold === null || threshold < yMin || threshold > yMax) continue;
    svg.append(svgElement('line', { class: 'chart-threshold', x1: pad.left, x2: width - pad.right, y1: y(threshold), y2: y(threshold) }));
    text('chart-label', threshold.toLocaleString(), { x: width - pad.right + 6, y: y(threshold) + 4 });
  }
  const coords = points.map(point => x(point.t).toFixed(1) + ',' + y(point.v).toFixed(1));
  if (points.length > 1) svg.append(svgElement('polyline', { class: 'chart-line', points: coords.join(' ') }));
  const lastPoint = points.at(-1);
  svg.append(svgElement('circle', { class: 'chart-dot', cx: x(lastPoint.t), cy: y(lastPoint.v), r: 4 }));
  return svg;
}

// Current, average, lowest, highest and time in the ideal range over the window.
function stats(key, value) {
  const { unit } = metricByKey.get(key);
  const values = (history.get(key) || []).map(point => point.v);
  const show = v => (Number.isFinite(v) ? withUnit(formatValue(key, v), unit) : '—');
  const [low, high] = bounds(key);
  const inRange = v => (low === null || v >= low) && (high === null || v <= high);
  const share = values.length && hasBounds(key)
    ? Math.round(values.filter(inRange).length / values.length * 100) + '%'
    : '—';
  return [
    ['Current', show(value)],
    ['Average', show(values.length ? values.reduce((a, b) => a + b, 0) / values.length : NaN)],
    ['Lowest', show(values.length ? Math.min(...values) : NaN)],
    ['Highest', show(values.length ? Math.max(...values) : NaN)],
    ['Time in ideal range', share],
    ['Ideal range', idealText(key).replace(/^Ideal /, '') || '—'],
  ];
}

function renderDetail(readings) {
  const metric = metricByKey.get(selected);
  const value = readings?.[selected];
  const panel = byId('detail');
  panel.dataset.metric = selected;
  panel.setAttribute('aria-labelledby', 'card-' + selected);

  const head = element('div', 'detail-head');
  head.append(iconTile(metric.icon), element('h3', 'detail-title', metric.name), pill(selected, value));

  const list = element('dl', 'stats');
  for (const [term, description] of stats(selected, value)) {
    const row = element('div', 'stat');
    row.append(element('dt', '', term), element('dd', '', description));
    list.append(row);
  }

  const legend = element('div', 'chart-legend');
  legend.append(element('span', 'legend-line', 'Reading (' + metric.unit + ')'));
  if (hasBounds(selected)) legend.append(element('span', 'legend-limit', 'Ideal range'));
  legend.append(element('span', 'legend-window', 'Last 30 min'));

  const chart = element('div', 'detail-chart');
  chart.append(renderChart(selected), legend);
  const body = element('div', 'detail-body');
  body.append(chart, list);
  panel.replaceChildren(head, body);
}

// ---- cards ---------------------------------------------------------------

// Card buttons are created once so keyboard focus survives the 2-second refresh.
function createCards() {
  const row = byId('metrics');
  for (const metric of metrics) {
    const card = element('button', 'metric');
    card.type = 'button';
    card.id = 'card-' + metric.key;
    card.dataset.metric = metric.key;
    card.setAttribute('role', 'tab');
    card.setAttribute('aria-controls', 'detail');
    card.addEventListener('click', () => selectMetric(metric.key));
    row.append(card);
  }
}

function selectMetric(key) {
  if (!metricByKey.has(key)) return;
  selected = key;
  renderReadings(lastReadings);
}

function renderReadings(readings) {
  lastReadings = readings;
  for (const metric of metrics) {
    const card = byId('card-' + metric.key);
    const value = readings?.[metric.key];
    const head = element('span', 'metric-head');
    head.append(iconTile(metric.icon), element('span', 'label', metric.name), pill(metric.key, value));
    card.replaceChildren(head, valueLine(metric.key, value), renderBar(metric.key, value), sparkline(metric.key));
    card.setAttribute('aria-selected', String(metric.key === selected));
    card.tabIndex = metric.key === selected ? 0 : -1;
  }
  renderDetail(readings);
}

// Arrow keys move between cards, as in a tab list.
byId('metrics').addEventListener('keydown', event => {
  const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[event.key];
  if (!step) return;
  event.preventDefault();
  const index = metrics.findIndex(metric => metric.key === selected);
  const next = metrics[(index + step + metrics.length) % metrics.length].key;
  selectMetric(next);
  byId('card-' + next).focus();
});

function renderCondition(code) {
  const [icon, label, advice] = conditions.get(code) || unknownCondition;
  // Hero colour: good when healthy, attention when the plant needs something, unknown without data.
  document.body.dataset.health = code === 'happy' ? 'good' : conditions.has(code) ? 'attention' : 'unknown';
  byId('stateIcon').textContent = icon;
  byId('state').textContent = label;
  byId('advice').textContent = advice;
}

function setConnection(kind) {
  const [label, detail] = badges[kind];
  byId('connection').textContent = label;
  byId('connection').title = detail || modes.get(mode).ok;
  byId('connection').dataset.status = kind;
}

// e.g. "2026-11-20 7:39:15 PM" in the viewer's local time.
function formatTime(date) {
  const pad = n => String(n).padStart(2, '0');
  const hours = date.getHours() % 12 || 12;
  return date.getFullYear() + '-' + pad(date.getMonth() + 1) + '-' + pad(date.getDate()) + ' '
    + hours + ':' + pad(date.getMinutes()) + ':' + pad(date.getSeconds()) + ' '
    + (date.getHours() < 12 ? 'AM' : 'PM');
}

function clearReadings(kind) {
  expiresAt = 0;
  renderCondition('unknown');
  setConnection(kind);
  byId('sample').hidden = true;
  renderReadings(null);
}

function expireReadings() {
  if (expiresAt && performance.now() >= expiresAt) {
    clearReadings('stale');
  }
}

async function poll() {
  if (inFlight) return;
  const current = generation;
  const requestedMode = mode;
  const controller = new AbortController();
  inFlight = controller;
  const startedAt = performance.now();
  const timeout = setTimeout(() => controller.abort(), 5000);
  try {
    const response = await fetch('/api/demo/telemetry?mode=' + requestedMode, {
      method: 'GET',
      credentials: 'omit',
      cache: 'no-store',
      signal: controller.signal,
    });
    if (!response.ok) throw new Error('Telemetry unavailable');
    const telemetry = await response.json();
    // Drop anything that arrives after a mode switch or is labelled for another mode.
    if (current !== generation) return;
    if (telemetry.mode !== requestedMode) throw new Error('Mode mismatch');
    thresholds = telemetry.thresholds && typeof telemetry.thresholds === 'object' ? telemetry.thresholds : null;
    expiresAt = startedAt + telemetry.fresh_for_s * 1000;
    const kind = statuses.get(telemetry.status);
    const sampleTime = new Date(telemetry.sample_time);
    if (!kind || Number.isNaN(sampleTime.getTime()) || !Number.isFinite(expiresAt) || performance.now() >= expiresAt) {
      clearReadings('stale');
      return;
    }
    setConnection(kind);
    renderCondition(telemetry.condition);
    byId('sample').textContent = 'Last updated: ' + formatTime(sampleTime);
    byId('sample').hidden = false;
    recordSample(sampleTime, telemetry.readings);
    renderReadings(telemetry.readings);
  } catch {
    if (current === generation) clearReadings('error');
  } finally {
    clearTimeout(timeout);
    if (inFlight === controller) inFlight = null;
  }
}

function setMode(next) {
  if (!modes.has(next) || next === mode) return;
  mode = next;
  generation += 1;
  thresholds = null;
  resetHistory();
  if (inFlight) {
    inFlight.abort();
    inFlight = null;
  }
  for (const button of byId('modeToggle').querySelectorAll('button')) {
    button.setAttribute('aria-pressed', String(button.dataset.mode === mode));
  }
  byId('modeBanner').textContent = modes.get(mode).banner;
  document.body.dataset.mode = mode;
  byId('simBadge').hidden = mode !== 'simulated';
  clearReadings('waiting');
  poll();
}

for (const button of byId('modeToggle').querySelectorAll('button')) {
  button.addEventListener('click', () => setMode(button.dataset.mode));
}
createCards();
renderReadings(null);
poll();
setInterval(poll, 2000);
setInterval(expireReadings, 500);
