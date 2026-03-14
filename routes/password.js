const express = require('express');
const router = express.Router();
const passwordController = require('../controllers/passwordController');
const validation = require('../middleware/validationMiddleware');
const rateLimit = require('../middleware/rateLimitMiddleware');
const authMiddleware = require('../middleware/authMiddleware');

/**
 * POST /api/password/reset-request
 * Request password reset
 */
router.post(
    '/reset-request',
    rateLimit.passwordResetLimiter,
    passwordController.requestPasswordReset
);

/**
 * POST /api/password/reset
 * Reset password with token
 */
router.post(
    '/reset',
    rateLimit.passwordResetLimiter,
    passwordController.resetPassword
);

/**
 * POST /api/password/change
 * Change password (requires authentication)
 */
router.post(
    '/change',
    authMiddleware.isAuthenticated,
    rateLimit.passwordChangeLimiter,
    passwordController.changePassword
);

module.exports = router;
