import { describe, expect, it } from "vitest";
import {
  DEAD_BAND_HOLD,
  classifyTernary,
  dampingStep,
  type DampingMode,
  type StepInput,
} from "./damping";

function step(overrides: Partial<StepInput> = {}) {
  return dampingStep({
    position: 0,
    velocity: 0,
    target: 0,
    deadBand: 0.25,
    stiffness: 4,
    thickness: 2,
    noise: 0,
    dt: 0.1,
    mode: "both",
    ...overrides,
  });
}

describe("classifyTernary", () => {
  it("labels below, inside, and above", () => {
    expect(classifyTernary(-1, 0.25)).toBe(-1);
    expect(classifyTernary(0, 0.25)).toBe(0);
    expect(classifyTernary(0.1, 0.25)).toBe(0);
    expect(classifyTernary(1, 0.25)).toBe(1);
  });

  it("counts the edge of the dead band as inside", () => {
    expect(classifyTernary(0.25, 0.25)).toBe(0);
    expect(classifyTernary(-0.25, 0.25)).toBe(0);
    expect(classifyTernary(0.2500001, 0.25)).toBe(1);
    expect(classifyTernary(-0.2500001, 0.25)).toBe(-1);
  });

  it("treats a negative or non-finite band as closed", () => {
    expect(classifyTernary(0.01, -2)).toBe(1);
    expect(classifyTernary(-0.01, Number.NaN)).toBe(-1);
    expect(classifyTernary(Number.NaN, 0.2)).toBe(0);
  });
});

describe("dampingStep", () => {
  it("matches a hand-worked tick outside the band", () => {
    const result = step({
      position: 2,
      velocity: 0.5,
      noise: 0.5,
      mode: "both",
    });

    expect(result.ternary).toBe(1);
    expect(result.error).toBe(2);
    expect(result.rubberForce).toBe(-8);
    expect(result.quicksandForce).toBeCloseTo(0.625);
    expect(result.velocity).toBeCloseTo(-0.1875);
    expect(result.position).toBeCloseTo(1.98125);
  });

  it("turns the rubber band off inside the dead band and in the undamped lane", () => {
    expect(step({ position: 0.1, mode: "both" }).rubberForce).toBe(0);
    expect(step({ position: 2, mode: "none" }).rubberForce).toBe(0);
    expect(step({ position: 2, mode: "none" }).quicksandForce).toBe(0);
    expect(step({ position: 2, mode: "rubber" }).quicksandForce).toBe(0);
  });

  it("pulls harder the further the band is stretched, and always toward the target", () => {
    const near = step({ position: 1, stiffness: 5, mode: "rubber" });
    const far = step({ position: 3, stiffness: 5, mode: "rubber" });
    expect(near.rubberForce).toBeLessThan(0);
    expect(far.rubberForce).toBeCloseTo(near.rubberForce * 3);
    expect(step({ position: -2, stiffness: 5, mode: "rubber" }).rubberForce).toBeGreaterThan(0);
  });

  it("uses the same trit for every mode", () => {
    const modes: DampingMode[] = ["none", "rubber", "both"];
    const trits = modes.map((mode) => step({ position: -2, mode }).ternary);
    expect(trits).toEqual([-1, -1, -1]);
  });

  it("grows the quicksand force with speed", () => {
    const slow = step({
      position: 1,
      velocity: 1,
      deadBand: 0,
      stiffness: 0,
      thickness: 2,
      dt: 0.05,
    });
    const fast = step({
      position: 1,
      velocity: 2,
      deadBand: 0,
      stiffness: 0,
      thickness: 2,
      dt: 0.05,
    });
    expect(slow.quicksandForce).toBeCloseTo(-4);
    expect(fast.quicksandForce).toBeCloseTo(-12);
    expect(Math.abs(fast.quicksandForce)).toBeGreaterThan(Math.abs(slow.quicksandForce) * 2);
  });

  it("is thicker inside the dead band and can stop a tick without reversing it", () => {
    const outside = step({
      position: 1,
      velocity: 1,
      deadBand: 0.2,
      stiffness: 0,
      dt: 0.05,
    });
    const inside = step({
      position: 0,
      velocity: 1,
      deadBand: 0.2,
      stiffness: 0,
      dt: 0.05,
    });
    expect(Math.abs(inside.quicksandForce)).toBeCloseTo(
      Math.abs(outside.quicksandForce) * DEAD_BAND_HOLD,
    );

    const stuck = step({
      position: 0.1,
      velocity: 0.4,
      noise: 0,
      mode: "both",
    });
    expect(stuck.ternary).toBe(0);
    expect(stuck.quicksandForce).toBeCloseTo(-4);
    expect(stuck.velocity).toBe(0);
    expect(stuck.position).toBeCloseTo(0.1);

    const slammed = step({
      position: 1,
      velocity: 3,
      thickness: 1000,
      stiffness: 0,
      deadBand: 0,
      dt: 0.2,
    });
    expect(slammed.velocity).toBe(0);
    expect(Math.sign(slammed.quicksandForce)).toBe(-1);
  });

  it("does not move when dt is zero, and ignores negative stiffness", () => {
    const frozen = step({ position: 1.5, velocity: 0.4, dt: 0, noise: 4 });
    expect(frozen.position).toBe(1.5);
    expect(frozen.velocity).toBe(0.4);
    expect(step({ position: 2, stiffness: -10, mode: "rubber" }).rubberForce).toBe(0);
  });

  it("lets an undamped offset sit still while the rubber band overshoots and quicksand settles", () => {
    const deadBand = 0.3;
    const dt = 1 / 30;
    const steps = 360;
    const start = 2.2;

    function release(mode: DampingMode) {
      let position = start;
      let velocity = 0;
      const samples: number[] = [];
      for (let i = 0; i < steps; i += 1) {
        const result = dampingStep({
          position,
          velocity,
          target: 0,
          deadBand,
          stiffness: 9,
          thickness: 6.5,
          noise: 0,
          dt,
          mode,
        });
        position = result.position;
        velocity = result.velocity;
        samples.push(position);
      }
      return { position, velocity, samples };
    }

    function signChanges(samples: number[]): number {
      let changes = 0;
      let previous = 0;
      for (const value of samples) {
        const sign = Math.sign(value);
        if (sign === 0) continue;
        if (previous !== 0 && sign !== previous) changes += 1;
        previous = sign;
      }
      return changes;
    }

    const undamped = release("none");
    const rubber = release("rubber");
    const both = release("both");

    expect(undamped.position).toBeCloseTo(start);
    expect(undamped.velocity).toBe(0);

    expect(signChanges(rubber.samples)).toBeGreaterThanOrEqual(4);
    expect(Math.min(...rubber.samples)).toBeLessThan(-deadBand);

    const entered = both.samples.findIndex((value) => Math.abs(value) <= deadBand);
    expect(entered).toBeGreaterThan(0);
    expect(entered).toBeLessThan(150);
    expect(Math.min(...both.samples)).toBeGreaterThan(-deadBand - 1e-9);
    for (const value of both.samples.slice(entered)) {
      expect(value).toBeGreaterThan(-deadBand - 1e-9);
      expect(value).toBeLessThanOrEqual(deadBand + 0.05);
    }
    expect(Math.abs(both.position)).toBeLessThanOrEqual(deadBand);
    expect(Math.abs(both.velocity)).toBeLessThan(0.05);
  });

  it("holds inside the band under a steady drift that walks the undamped lane away", () => {
    function walk(mode: DampingMode) {
      let position = 0;
      let velocity = 0;
      for (let i = 0; i < 90; i += 1) {
        const result = dampingStep({
          position,
          velocity,
          target: 0,
          deadBand: 0.35,
          stiffness: 9,
          thickness: 6.5,
          noise: 1,
          dt: 0.1,
          mode,
        });
        position = result.position;
        velocity = result.velocity;
      }
      return position;
    }

    expect(walk("none")).toBeGreaterThan(5);
    expect(Math.abs(walk("both"))).toBeLessThan(0.35);
  });
});
