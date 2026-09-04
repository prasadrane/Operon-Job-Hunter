import { JobToken } from './job-token.js';
import { JobPath } from './job-path.js';
import { QueueBadge } from './queue-badge.js';

/**
 * Manages job lifecycle: active jobs, queued jobs, completion fade-out
 * Integrates with SSE events to update job states
 */
export class JobManager {
  constructor() {
    this.tokens = new Map(); // jobId → JobToken
    this.queues = new Map(); // zone → QueueBadge
    this.paths = new Map(); // jobId → JobPath
    this.jobStages = new Map(); // jobId → zone (for per-zone queue counting)

    // Initialize queue badges for all zones
    const zones = ['discovery', 'evaluation', 'tailoring', 'submission', 'lifecycle'];
    for (const zone of zones) {
      this.queues.set(zone, new QueueBadge(zone));
    }
  }

  /**
   * Update job state from SSE event
   * @param {Object} jobData - Job data { id, company, stage, status, score }
   */
  updateJob(jobData) {
    const { id, status, stage } = jobData;

    // Create or update token
    if (!this.tokens.has(id)) {
      this.tokens.set(id, new JobToken());
    }

    const token = this.tokens.get(id);
    token.setJob(jobData);

    // Track stage for queue counting
    if (stage) {
      this.jobStages.set(id, stage);
    }

    // Handle status transitions
    if (status === 'completed') {
      token.fadeOut();
    } else if (status === 'queued') {
      // Update queue count for this zone
      const zone = stage;
      if (zone && this.queues.has(zone)) {
        this.queues.get(zone).setCount(
          this.getQueueCount(zone)
        );
      }
    }
  }

  /**
   * Get count of queued jobs in a specific zone
   * @param {string} zone - Zone name
   * @returns {number} Queue count
   */
  getQueueCount(zone) {
    let count = 0;
    for (const [jobId, jobStage] of this.jobStages.entries()) {
      if (jobStage === zone && this.tokens.has(jobId)) {
        count++;
      }
    }
    return count;
  }

  /**
   * Get token by job ID
   * @param {string} jobId - Job identifier
   * @returns {JobToken|null} Job token
   */
  getToken(jobId) {
    return this.tokens.get(jobId) || null;
  }

  /**
   * Get all active (non-faded) jobs
   * @returns {Array} Array of active job tokens
   */
  getActiveJobs() {
    const active = [];
    for (const [jobId, token] of this.tokens.entries()) {
      if (!token.isComplete()) {
        active.push(token.getRenderData());
      }
    }
    return active;
  }

  /**
   * Get queue counts for all zones
   * @returns {Object} { zone: count }
   */
  getQueueCounts() {
    const counts = {};
    for (const [zone, badge] of this.queues.entries()) {
      counts[zone] = badge.count;
    }
    return counts;
  }

  /**
   * Update all tokens and badges (called each frame)
   * @param {number} deltaTime - Time since last frame in ms
   */
  update(deltaTime) {
    // Update tokens (fade out completed jobs)
    for (const [jobId, token] of this.tokens.entries()) {
      token.update(deltaTime);

      // Remove fully faded tokens
      if (token.isComplete()) {
        this.tokens.delete(jobId);
        this.jobStages.delete(jobId);
      }
    }

    // Update queue badges (pulse animation)
    for (const badge of this.queues.values()) {
      badge.update(deltaTime);
    }
  }

  /**
   * Get all queue badges for rendering
   * @returns {Array} Array of queue badge render data
   */
  getQueueBadges() {
    return Array.from(this.queues.values()).map(badge => badge.getRenderData());
  }
}
