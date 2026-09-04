import { AgentSprite } from './agent-sprite.js';
import { AnimationController } from './animations.js';
import { StatusOrb } from './status-orb.js';
import { ANIM_STATES } from './art-style.js';

/**
 * Manages agent lifecycle, state mapping, and SSE event handling
 */
export class AgentManager {
  constructor() {
    this.agents = new Map();
  }

  /**
   * Update agent state from SSE event
   * @param {string} agentId - Agent identifier
   * @param {Object} state - Agent state from SSE
   */
  updateAgentState(agentId, state) {
    // Create agent if it doesn't exist
    if (!this.agents.has(agentId)) {
      this.agents.set(agentId, {
        sprite: new AgentSprite(),
        animation: new AnimationController(),
        orb: new StatusOrb(),
      });
    }

    const agent = this.agents.get(agentId);

    // Map backend state to visual behavior
    const backendStatus = state.status;

    // Update animation state
    const animState = this.mapStatusToAnimation(backendStatus);
    agent.animation.play(animState);

    // Update status orb
    const orbStatus = this.mapStatusToOrb(backendStatus);
    agent.orb.setStatus(orbStatus);

    // Update sprite direction if provided
    if (state.direction) {
      agent.sprite.setDirection(state.direction);
    }
  }

  /**
   * Map backend status to animation state
   * @param {string} status - Backend status ('active', 'sleeping', 'error', 'busy')
   * @returns {string} Animation state
   */
  mapStatusToAnimation(status) {
    const mapping = {
      'active': ANIM_STATES.WORK,
      'running': ANIM_STATES.WORK,
      'sleeping': ANIM_STATES.IDLE,
      'dormant': ANIM_STATES.IDLE,
      'error': ANIM_STATES.DISTRESSED,
      'busy': ANIM_STATES.WALK,
    };

    return mapping[status] || ANIM_STATES.IDLE;
  }

  /**
   * Map backend status to orb status
   * @param {string} status - Backend status
   * @returns {string} Orb status ('active', 'sleeping', 'error', 'busy')
   */
  mapStatusToOrb(status) {
    const mapping = {
      'active': 'active',
      'running': 'active',
      'sleeping': 'sleeping',
      'dormant': 'sleeping',
      'error': 'error',
      'busy': 'busy',
    };

    return mapping[status] || 'sleeping';
  }

  /**
   * Get agent by ID
   * @param {string} agentId - Agent identifier
   * @returns {Object} Agent object with sprite, animation, orb
   */
  getAgent(agentId) {
    return this.agents.get(agentId);
  }

  /**
   * Update all agents (called each frame)
   * @param {number} deltaTime - Time since last frame in ms
   */
  update(deltaTime) {
    for (const agent of this.agents.values()) {
      agent.animation.update(deltaTime);
      agent.orb.update(deltaTime);
    }
  }

  /**
   * Get all agents for rendering
   * @returns {Array} Array of agent objects
   */
  getAllAgents() {
    return Array.from(this.agents.entries()).map(([id, agent]) => ({
      id,
      ...agent,
    }));
  }
}
