/**
 * Job token sprite showing company icon, score, and progress
 * 24x24px with bezier curve path animation
 */
export class JobToken {
  constructor() {
    this.jobId = null;
    this.company = '';
    this.title = '';
    this.score = 0;
    this.alpha = 1.0;
    this.scale = 1.0;
    this.fadeTimer = 0;
    this.isFading = false;
    this.fadeDuration = 5000; // 5 seconds
  }

  /**
   * Set job data from SSE event
   * @param {Object} jobData - Job data { id, company, title, score }
   */
  setJob(jobData) {
    this.jobId = jobData.id;
    this.company = jobData.company || '';
    this.title = jobData.title || '';
    this.score = jobData.score || 0;
    this.alpha = 1.0;
    this.isFading = false;
    this.fadeTimer = 0;
  }

  /**
   * Start fade out animation (called when job completes)
   */
  fadeOut() {
    this.isFading = true;
    this.fadeTimer = 0;
  }

  /**
   * Update fade animation
   * @param {number} deltaTime - Time since last frame in ms
   */
  update(deltaTime) {
    if (this.isFading) {
      this.fadeTimer += deltaTime;
      this.alpha = Math.max(0, 1 - (this.fadeTimer / this.fadeDuration));
    }
  }

  /**
   * Get render data for PixiJS
   * @returns {Object} { jobId, company, score, alpha, scale }
   */
  getRenderData() {
    return {
      jobId: this.jobId,
      company: this.company,
      score: this.score,
      alpha: this.alpha,
      scale: this.scale,
    };
  }

  /**
   * Check if token is fully faded (should be removed)
   * @returns {boolean} True if alpha <= 0
   */
  isComplete() {
    return this.alpha <= 0;
  }
}
