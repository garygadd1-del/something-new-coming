/**
 * One tick of trinary drift damping.
 *
 * Balanced ternary classifies error = position − target against a dead band:
 *   +1 above, 0 inside (including the edge), −1 below.
 *
 * Rubber band: Hooke's law, and only when the trit is not 0.
 * The pull is −stiffness × error, so it grows with stretch and switches off
 * inside the band.
 *
 * Quicksand: viscous drag that grows with speed,
 *   F = −c × velocity × (1 + |velocity|)
 * where c = thickness outside the band and c = thickness × DEAD_BAND_HOLD
 * inside it. The extra thickness is what holds a settled value nearly still.
 * Drag is clamped so one tick can stop the motion but cannot reverse it.
 *
 * Modes:
 *   none   — noise only
 *   rubber — rubber band, no quicksand (a released offset overshoots)
 *   both   — rubber band plus quicksand (glides home and sticks)
 */

/** How many times thicker the mud is while the trit is 0. */
export const DEAD_BAND_HOLD = 4;

export type Ternary = -1 | 0 | 1;
export type DampingMode = "none" | "rubber" | "both";

export interface StepInput {
  position: number;
  velocity: number;
  target: number;
  /** Half-width of the dead band. The edge counts as inside. */
  deadBand: number;
  /** Spring stiffness. Ignored when mode is "none" or the trit is 0. */
  stiffness: number;
  /** Quicksand viscosity. Ignored unless mode is "both". */
  thickness: number;
  /** Disturbance acceleration for this tick. Pass the same sample to every lane. */
  noise: number;
  dt: number;
  mode: DampingMode;
}

export interface StepResult {
  position: number;
  velocity: number;
  /** Trit of the position at the start of the tick — the class that picked the forces. */
  ternary: Ternary;
  error: number;
  rubberForce: number;
  quicksandForce: number;
}

function finite(value: number, fallback = 0): number {
  return Number.isFinite(value) ? value : fallback;
}

export function classifyTernary(error: number, deadBand: number): Ternary {
  if (!Number.isFinite(error)) return 0;
  const band = Number.isFinite(deadBand) ? Math.max(0, deadBand) : 0;
  if (error > band) return 1;
  if (error < -band) return -1;
  return 0;
}

export function dampingStep(input: StepInput): StepResult {
  const dt = Math.max(0, finite(input.dt));
  const position = finite(input.position);
  const velocityIn = finite(input.velocity);
  const target = finite(input.target);
  const stiffness = Math.max(0, finite(input.stiffness));
  const thickness = Math.max(0, finite(input.thickness));
  const noise = finite(input.noise);
  const error = position - target;
  const ternary = classifyTernary(error, input.deadBand);

  const rubberForce =
    input.mode !== "none" && ternary !== 0 && stiffness > 0 ? -stiffness * error : 0;

  let velocity = velocityIn + (rubberForce + noise) * dt;
  let quicksandForce = 0;

  if (input.mode === "both" && dt > 0 && velocity !== 0 && thickness > 0) {
    const speed = Math.abs(velocity);
    const viscosity = thickness * (ternary === 0 ? DEAD_BAND_HOLD : 1);
    const dragMagnitude = viscosity * speed * (1 + speed);
    const stopMagnitude = speed / dt;
    const applied = Math.min(dragMagnitude, stopMagnitude);
    quicksandForce = -Math.sign(velocity) * applied;
    velocity += quicksandForce * dt;
    if (Math.abs(velocity) < 1e-12) velocity = 0;
  }

  return {
    position: position + velocity * dt,
    velocity,
    ternary,
    error,
    rubberForce,
    quicksandForce,
  };
}
