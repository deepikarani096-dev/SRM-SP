const express = require('express');
const router = express.Router();
const { login } = require('../controllers/authController');
const validation = require('../middleware/validationMiddleware');
const rateLimit = require('../middleware/rateLimitMiddleware');

/**
 * POST /api/login
 * Login with faculty ID and password
 */
router.post(
    '/login',
    rateLimit.loginLimiter,
    validation.validateLoginInput,
    login
);

module.exports = router;
