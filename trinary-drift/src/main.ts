import {
  DEAD_BAND_HOLD,
  classifyTernary,
  dampingStep,
  type DampingMode,
  type StepResult,
  type Ternary,
} from "./damping";

const DT = 1 / 30;
const HISTORY = 360;
const TRIT_CELLS = 48;
const INITIAL_POSITION = 2.2;
const SEED = 20261023;

interface LaneView {
  mode: DampingMode;
  color: string;
  position: number;
  velocity: number;
  history: number[];
  trits: Ternary[];
  last: StepResult | null;
  canvas: HTMLCanvasElement;
  posEl: HTMLElement;
  tritEl: HTMLElement;
  tritWordEl: HTMLElement;
  rubberEl: HTMLElement;
  sandEl: HTMLElement;
  velEl: HTMLElement;
  offEl: HTMLElement;
  cells: HTMLSpanElement[];
}

const LANES: { mode: DampingMode; color: string; id: string }[] = [
  { mode: "none", color: "#243f3c", id: "none" },
  { mode: "rubber", color: "#c23b22", id: "rubber" },
  { mode: "both", color: "#8a5a28", id: "both" },
];

function must<T extends Element>(selector: string): T {
  const element = document.querySelector<T>(selector);
  if (!element) throw new Error(`Missing ${selector}`);
  return element;
}

function mulberry32(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function fmt(value: number): string {
  if (!Number.isFinite(value)) return "—";
  const body = Math.abs(value).toFixed(2);
  if (value > 0) return `+${body}`;
  if (value < 0) return `−${body}`;
  return body;
}

function tritText(trit: Ternary): string {
  if (trit < 0) return "−1";
  if (trit > 0) return "+1";
  return "0";
}

function tritWord(trit: Ternary): string {
  if (trit < 0) return "below";
  if (trit > 0) return "above";
  return "in band";
}

function tritClass(trit: Ternary): string {
  if (trit < 0) return "is-below";
  if (trit > 0) return "is-above";
  return "is-band";
}

const stiffnessInput = must<HTMLInputElement>("#stiffness");
const thicknessInput = must<HTMLInputElement>("#thickness");
const deadBandInput = must<HTMLInputElement>("#dead-band");
const noiseInput = must<HTMLInputElement>("#noise");
const tickEl = must<HTMLElement>("#tick");
const kickEl = must<HTMLElement>("#kick");
const summaryEl = must<HTMLElement>("#live-summary");
const pauseButton = must<HTMLButtonElement>("#pause");
const resetButton = must<HTMLButtonElement>("#reset");

must<HTMLElement>("#hold-factor").textContent = String(DEAD_BAND_HOLD);
const pastLabel = `${Math.round(HISTORY * DT)}s ago`;
for (const element of document.querySelectorAll<HTMLElement>(".axis-past")) {
  element.textContent = pastLabel;
}

function readParams() {
  return {
    stiffness: Number(stiffnessInput.value),
    thickness: Number(thicknessInput.value),
    deadBand: Number(deadBandInput.value),
    noise: Number(noiseInput.value),
  };
}

function syncSliderLabels(): void {
  must<HTMLOutputElement>("#stiffness-value").textContent = Number(stiffnessInput.value).toFixed(1);
  must<HTMLOutputElement>("#thickness-value").textContent = Number(thicknessInput.value).toFixed(1);
  must<HTMLOutputElement>("#dead-band-value").textContent = Number(deadBandInput.value).toFixed(2);
  must<HTMLOutputElement>("#noise-value").textContent = Number(noiseInput.value).toFixed(2);
}

function windowHalf(deadBand: number): number {
  return Math.max(3.4, deadBand * 2.6);
}

const lanes: LaneView[] = LANES.map((spec) => {
  const row = must<HTMLElement>(`#trits-${spec.id}`);
  const cells: HTMLSpanElement[] = [];
  for (let i = 0; i < TRIT_CELLS; i += 1) {
    const cell = document.createElement("span");
    cell.className = "trit-cell is-empty";
    row.appendChild(cell);
    cells.push(cell);
  }
  return {
    mode: spec.mode,
    color: spec.color,
    position: INITIAL_POSITION,
    velocity: 0,
    history: [],
    trits: [],
    last: null,
    canvas: must<HTMLCanvasElement>(`#chart-${spec.id}`),
    posEl: must<HTMLElement>(`#pos-${spec.id}`),
    tritEl: must<HTMLElement>(`#trit-${spec.id}`),
    tritWordEl: must<HTMLElement>(`#trit-word-${spec.id}`),
    rubberEl: must<HTMLElement>(`#rubber-${spec.id}`),
    sandEl: must<HTMLElement>(`#sand-${spec.id}`),
    velEl: must<HTMLElement>(`#vel-${spec.id}`),
    offEl: must<HTMLElement>(`#off-${spec.id}`),
    cells,
  };
});

let rng = mulberry32(SEED);
let tick = 0;
let lastKick = 0;
let paused = false;
let accumulator = 0;
let lastTime = performance.now();

function currentTrit(lane: LaneView): Ternary {
  if (lane.last) return lane.last.ternary;
  return classifyTernary(lane.position - 0, readParams().deadBand);
}

function reset(): void {
  rng = mulberry32(SEED);
  tick = 0;
  lastKick = 0;
  accumulator = 0;
  const deadBand = readParams().deadBand;
  const trit = classifyTernary(INITIAL_POSITION, deadBand);
  for (const lane of lanes) {
    lane.position = INITIAL_POSITION;
    lane.velocity = 0;
    lane.history = [INITIAL_POSITION];
    lane.trits = [trit];
    lane.last = null;
  }
}

function stepAll(): void {
  const params = readParams();
  lastKick = (rng() * 2 - 1) * params.noise;
  for (const lane of lanes) {
    const result = dampingStep({
      position: lane.position,
      velocity: lane.velocity,
      target: 0,
      deadBand: params.deadBand,
      stiffness: params.stiffness,
      thickness: params.thickness,
      noise: lastKick,
      dt: DT,
      mode: lane.mode,
    });
    lane.position = result.position;
    lane.velocity = result.velocity;
    lane.last = result;
    lane.history.push(result.position);
    if (lane.history.length > HISTORY) lane.history.shift();
    lane.trits.push(result.ternary);
    if (lane.trits.length > TRIT_CELLS) lane.trits.shift();
  }
  tick += 1;
  if (tick % 30 === 0) {
    summaryEl.textContent = lanes
      .map((lane) => {
        const trit = currentTrit(lane);
        return `${lane.mode} position ${fmt(lane.position)}, trit ${tritText(trit)} ${tritWord(trit)}`;
      })
      .join(". ");
  }
}

function paintTrits(lane: LaneView): void {
  const offset = TRIT_CELLS - lane.trits.length;
  for (let i = 0; i < TRIT_CELLS; i += 1) {
    const cell = lane.cells[i];
    const trit = lane.trits[i - offset];
    cell.className = "trit-cell";
    if (trit === undefined) {
      cell.classList.add("is-empty");
      cell.removeAttribute("title");
      continue;
    }
    cell.classList.add(tritClass(trit));
    cell.title = `${tritText(trit)} ${tritWord(trit)}`;
  }
}

function paintReadout(lane: LaneView, half: number): void {
  const trit = currentTrit(lane);
  lane.posEl.textContent = fmt(lane.position);
  lane.tritEl.textContent = tritText(trit);
  lane.tritEl.className = `trit-pill ${tritClass(trit)}`;
  lane.tritWordEl.textContent = tritWord(trit);
  lane.rubberEl.textContent = fmt(lane.last?.rubberForce ?? 0);
  lane.sandEl.textContent = fmt(lane.last?.quicksandForce ?? 0);
  lane.velEl.textContent = fmt(lane.velocity);
  lane.offEl.textContent = Math.abs(lane.position) > half ? "Off the scale" : "";
}

function drawChart(lane: LaneView, yMin: number, yMax: number, deadBand: number): void {
  const canvas = lane.canvas;
  const rect = canvas.getBoundingClientRect();
  if (rect.width < 2 || rect.height < 2) return;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const width = Math.max(1, Math.round(rect.width * dpr));
  const height = Math.max(1, Math.round(rect.height * dpr));
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  const padLeft = 38 * dpr;
  const padRight = 10 * dpr;
  const padTop = 12 * dpr;
  const padBottom = 12 * dpr;
  const plotWidth = width - padLeft - padRight;
  const plotHeight = height - padTop - padBottom;
  const yOf = (value: number) => {
    const t = (value - yMin) / (yMax - yMin);
    return padTop + (1 - t) * plotHeight;
  };
  const xOf = (index: number, count: number) => {
    const slots = Math.max(1, HISTORY - 1);
    const oldest = HISTORY - count;
    return padLeft + ((oldest + index) / slots) * plotWidth;
  };

  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#fbf7f0";
  ctx.fillRect(0, 0, width, height);

  const bandTop = yOf(Math.min(deadBand, yMax));
  const bandBottom = yOf(Math.max(-deadBand, yMin));
  ctx.fillStyle = "rgba(228, 199, 138, 0.72)";
  ctx.fillRect(padLeft, bandTop, plotWidth, Math.max(1, bandBottom - bandTop));

  ctx.save();
  ctx.beginPath();
  ctx.rect(padLeft, padTop, plotWidth, plotHeight);
  ctx.clip();
  ctx.strokeStyle = "rgba(28, 22, 18, 0.08)";
  ctx.lineWidth = dpr;
  for (let sample = 60; sample < HISTORY; sample += 60) {
    const x = padLeft + (sample / (HISTORY - 1)) * plotWidth;
    ctx.beginPath();
    ctx.moveTo(x, padTop);
    ctx.lineTo(x, padTop + plotHeight);
    ctx.stroke();
  }

  const count = lane.history.length;
  ctx.beginPath();
  ctx.strokeStyle = lane.color;
  ctx.lineWidth = 2.25 * dpr;
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  for (let i = 0; i < count; i += 1) {
    const x = xOf(i, count);
    const y = yOf(lane.history[i]);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.stroke();
  if (count > 0) {
    ctx.fillStyle = lane.color;
    ctx.beginPath();
    ctx.arc(xOf(count - 1, count), yOf(lane.history[count - 1]), 4 * dpr, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.restore();

  ctx.save();
  ctx.strokeStyle = "#1c1612";
  ctx.setLineDash([4 * dpr, 4 * dpr]);
  ctx.lineWidth = dpr;
  ctx.beginPath();
  ctx.moveTo(padLeft, yOf(0));
  ctx.lineTo(padLeft + plotWidth, yOf(0));
  ctx.stroke();
  ctx.restore();

  ctx.strokeStyle = "#1c1612";
  ctx.lineWidth = dpr;
  ctx.strokeRect(padLeft + 0.5, padTop + 0.5, plotWidth - 1, plotHeight - 1);

  ctx.fillStyle = "#5e564c";
  ctx.font = `${11 * dpr}px "JetBrains Mono", "Liberation Mono", ui-monospace, monospace`;
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  ctx.fillText(yMax.toFixed(1), padLeft - 6 * dpr, yOf(yMax));
  ctx.fillText("0", padLeft - 6 * dpr, yOf(0));
  ctx.fillText(yMin.toFixed(1), padLeft - 6 * dpr, yOf(yMin));
}

function draw(): void {
  const params = readParams();
  const half = windowHalf(params.deadBand);
  tickEl.textContent = String(tick);
  kickEl.textContent = fmt(lastKick);
  for (const lane of lanes) {
    paintReadout(lane, half);
    paintTrits(lane);
    drawChart(lane, -half, half, params.deadBand);
  }
}

function frame(now: number): void {
  const elapsed = Math.min(0.25, (now - lastTime) / 1000);
  lastTime = now;
  if (!paused) {
    accumulator += elapsed;
    let steps = 0;
    while (accumulator >= DT && steps < 3) {
      stepAll();
      accumulator -= DT;
      steps += 1;
    }
    if (accumulator > DT) accumulator = DT;
  }
  draw();
  requestAnimationFrame(frame);
}

for (const input of [stiffnessInput, thicknessInput, deadBandInput, noiseInput]) {
  input.addEventListener("input", () => {
    syncSliderLabels();
    if (paused) draw();
  });
}

pauseButton.addEventListener("click", () => {
  paused = !paused;
  pauseButton.setAttribute("aria-pressed", String(paused));
  pauseButton.textContent = paused ? "Resume" : "Pause";
  if (!paused) {
    accumulator = 0;
    lastTime = performance.now();
  }
});

resetButton.addEventListener("click", () => {
  reset();
  draw();
});

syncSliderLabels();
reset();
requestAnimationFrame(frame);
