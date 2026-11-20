'use strict';

const byId = id => document.getElementById(id);
const metrics = [
  ['temperature_c', 'Temperature', '°C'],
  ['humidity_pct', 'Humidity', '% RH'],
  ['light_lux', 'Light', 'lux'],
  ['soil_pct', 'Soil moisture', '%'],
  ['soil_raw', 'Soil sensor', ''],
];
const conditions = new Map([
  ['happy', 'Happy'],
  ['thirsty', 'Thirsty'],
  ['too_wet', 'Too wet'],
  ['too_hot', 'Too hot'],
  ['too_cold', 'Too cold'],
  ['low_light', 'Low light'],
  ['low_humidity', 'Low humidity'],
]);
const statuses = new Map([
  ['ok', 'Receiving live measurements'],
  ['invalid', 'Some measurements are unavailable'],
  ['uncalibrated', 'Soil moisture calibration is pending'],
]);
let polling = false;
let expiresAt = 0;

function renderReadings(readings) {
  const cards = metrics.map(([key, label, unit]) => {
    const card = document.createElement('p');
    const value = readings?.[key];
    card.textContent = label + ': ' + (Number.isFinite(value) ? [value, unit].join(' ').trim() : 'Unavailable');
    return card;
  });
  byId('metrics').replaceChildren(...cards);
}

function clearReadings(message) {
  expiresAt = 0;
  byId('state').textContent = 'Unknown';
  byId('connection').textContent = message;
  byId('sample').hidden = true;
  renderReadings(null);
}

function expireReadings() {
  if (expiresAt && performance.now() >= expiresAt) {
    clearReadings('No fresh measurements');
  }
}

async function poll() {
  if (polling) return;
  polling = true;
  const startedAt = performance.now();
  try {
    const response = await fetch('/api/demo/telemetry', {
      method: 'GET',
      credentials: 'omit',
      cache: 'no-store',
      signal: AbortSignal.timeout(5000),
    });
    if (!response.ok) throw new Error('Telemetry unavailable');
    const telemetry = await response.json();
    expiresAt = startedAt + telemetry.fresh_for_s * 1000;
    if (!statuses.has(telemetry.status) || !Number.isFinite(expiresAt) || performance.now() >= expiresAt) {
      clearReadings('No fresh measurements');
      return;
    }
    byId('connection').textContent = statuses.get(telemetry.status);
    byId('state').textContent = conditions.get(telemetry.condition) || 'Unknown';
    byId('sample').textContent = 'Sample taken ' + new Date(telemetry.sample_time).toLocaleString();
    byId('sample').hidden = false;
    renderReadings(telemetry.readings);
  } catch {
    clearReadings('Telemetry connection unavailable');
  } finally {
    polling = false;
  }
}

renderReadings(null);
poll();
setInterval(poll, 2000);
setInterval(expireReadings, 500);
