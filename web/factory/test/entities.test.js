import { describe, it, expect, beforeEach, vi } from 'vitest';
import { EntityManager } from '../entities.js';
import { StateManager } from '../state.js';

function makeApp() {
  return new PIXI.Application({ width: 800, height: 600 });
}

function makeRenderer() {
  const standard = new PIXI.Container();
  const full = new PIXI.Container();
  return {
    lodLayers: { standard, full },
    _camera: {
      focusEntity: vi.fn(),
    },
  };
}

describe('EntityManager', () => {
  let app, state, renderer, entities;

  beforeEach(() => {
    app = makeApp();
    state = new StateManager();
    // StateManager.attach expects agentManager/jobManager; null is fine here.
    state.attach({});
    renderer = makeRenderer();
    entities = new EntityManager(app, state, renderer);
  });

  it('constructs and attaches entityContainer to renderer LOD layers', () => {
    expect(entities).toBeTruthy();
    expect(entities.entityContainer).toBeTruthy();
    expect(renderer.lodLayers['standard'].children).toContain(entities.entityContainer);
    expect(renderer.lodLayers['full'].children).toContain(entities.entityContainer);
  });

  it('constructs even without a renderer (falls back to app.stage)', () => {
    const em = new EntityManager(app, state);
    expect(em).toBeTruthy();
    expect(app.stage.children).toContain(em.entityContainer);
  });

  it('creates agent entities after state_sync and returns hit targets', () => {
    state.applyStateSync({
      pipeline_state: {},
      agent_states: {
        'scout-falcon': { status: 'active', task: 'scan' },
        'tailor-owl':   { status: 'busy',   task: 'resume' },
      },
      job_queue: { discovered: [], evaluation: [], tailored: [], applied: [] },
    });

    const targets = entities.getHitTargets();
    const agentTargets = targets.filter((t) => t.kind === 'agent');
    expect(agentTargets.length).toBe(2);
    for (const t of agentTargets) {
      expect(t).toHaveProperty('id');
      expect(t).toHaveProperty('worldX');
      expect(t).toHaveProperty('worldY');
      expect(t).toHaveProperty('width');
      expect(t).toHaveProperty('height');
      expect(t.kind).toBe('agent');
    }
    const ids = agentTargets.map((t) => t.id).sort();
    expect(ids).toEqual(['scout-falcon', 'tailor-owl']);
  });

  it('creates job entities from all queue buckets', () => {
    state.applyStateSync({
      agent_states: {},
      job_queue: {
        discovered: [{ id: 'j1', company: 'Acme', title: 'SWE' }],
        evaluation: [{ id: 'j2', company: 'Globex' }],
        tailored:   [],
        applied:    [{ id: 'j3', company: 'Initech' }],
      },
    });

    const targets = entities.getHitTargets();
    const jobTargets = targets.filter((t) => t.kind === 'job');
    expect(jobTargets.length).toBe(3);
    const jobIds = jobTargets.map((t) => t.id).sort();
    expect(jobIds).toEqual(['j1', 'j2', 'j3']);
  });

  it('update() advances without throwing and removes completed jobs', () => {
    state.applyStateSync({
      agent_states: { 'a1': { status: 'active' } },
      job_queue: { discovered: [{ id: 'j1' }], evaluation: [], tailored: [], applied: [] },
    });

    expect(() => entities.update(16)).not.toThrow();
    // Force a job to complete; it should be removed.
    const rec = entities.jobs.get('j1');
    rec.token.fadeOut();
    // Advance past fadeDuration (5000ms)
    entities.update(5001);
    expect(entities.jobs.has('j1')).toBe(false);
    expect(entities.getHitTargets().find((t) => t.id === 'j1')).toBeUndefined();
  });

  it('focusOn does not throw for unknown id (no-op)', () => {
    expect(() => entities.focusOn('does-not-exist')).not.toThrow();
  });

  it('focusOn calls camera.focusEntity with world coords for a known agent', () => {
    state.applyStateSync({
      agent_states: { 'a1': { status: 'active' } },
      job_queue: {},
    });
    entities.focusOn('a1');
    expect(renderer._camera.focusEntity).toHaveBeenCalled();
    const arg = renderer._camera.focusEntity.mock.calls[0][0];
    expect(arg).toHaveProperty('x');
    expect(arg).toHaveProperty('y');
  });

  it('focusOn dispatches factory:focus-entity when no camera present', () => {
    const em = new EntityManager(app, state); // no renderer/camera
    state.applyStateSync({
      agent_states: { 'a2': { status: 'busy' } },
      job_queue: {},
    });
    const spy = vi.fn();
    window.addEventListener('factory:focus-entity', spy);
    em.focusOn('a2');
    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy.mock.calls[0][0].detail.id).toBe('a2');
    window.removeEventListener('factory:focus-entity', spy);
  });

  it('dispose removes PIXI children and unsubscribes', () => {
    state.applyStateSync({
      agent_states: { 'a1': { status: 'active' } },
      job_queue: { discovered: [{ id: 'j1' }], evaluation: [], tailored: [], applied: [] },
    });
    expect(entities.agents.size).toBe(1);
    expect(entities.jobs.size).toBe(1);
    entities.dispose();
    expect(entities.agents.size).toBe(0);
    expect(entities.jobs.size).toBe(0);
  });
});
