const rateLimit = require('express-rate-limit');

/**
 * General API rate limiter
 */
exports.generalLimiter = rateLimit({
    windowMs: 15 * 60 * 1000, // 15 minutes
    max: 100, // limit each IP to 100 requests per windowMs
    message: 'Too many requests from this IP, please try again later',
    standardHeaders: true,
    legacyHeaders: false,
});

/**
 * Strict rate limiter for login attempts
 */
exports.loginLimiter = rateLimit({
    windowMs: 15 * 60 * 1000, // 15 minutes
    max: 5, // limit each IP to 5 login attempts per windowMs
    message: 'Too many login attempts, please try again after 15 minutes',
    skipSuccessfulRequests: true, // don't count successful login attempts
    standardHeaders: true,
    legacyHeaders: false,
});

/**
 * Password reset rate limiter
 */
exports.passwordResetLimiter = rateLimit({
    windowMs: 60 * 60 * 1000, // 1 hour
    max: 3, // limit each IP to 3 password reset requests per hour
    message: 'Too many password reset attempts, please try again later',
    standardHeaders: true,
    legacyHeaders: false,
});

/**
 * Password change rate limiter (for authenticated users)
 */
exports.passwordChangeLimiter = rateLimit({
    windowMs: 60 * 60 * 1000, // 1 hour
    max: 5, // limit each IP to 5 password change attempts per hour
    message: 'Too many password change attempts, please try again later',
    standardHeaders: true,
    legacyHeaders: false,
    keyGenerator: (req, res) => {
        // Use user ID if authenticated, otherwise use IP
        return req.headers['user-id'] || req.headers['x-forwarded-for'] || req.connection.remoteAddress;
    },
});

/**
 * Signup rate limiter
 */
exports.signupLimiter = rateLimit({
    windowMs: 60 * 60 * 1000, // 1 hour
    max: 10, // limit each IP to 10 signup attempts per hour
    message: 'Too many signup attempts, please try again later',
    standardHeaders: true,
    legacyHeaders: false,
});

/**
 * API endpoint rate limiter
 */
exports.apiLimiter = rateLimit({
    windowMs: 15 * 60 * 1000, // 15 minutes
    max: 1000, // limit each IP to 1000 requests per 15 minutes
    message: 'Too many API requests, please try again later',
    standardHeaders: true,
    legacyHeaders: false,
});
