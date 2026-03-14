const fs = require('fs');
const path = require('path');

// Ensure logs directory exists
const logsDir = path.join(__dirname, '../logs');
if (!fs.existsSync(logsDir)) {
    fs.mkdirSync(logsDir, { recursive: true });
}

/**
 * Audit logging for sensitive operations
 */
exports.auditLog = (action, details) => {
    const timestamp = new Date().toISOString();
    const logEntry = {
        timestamp,
        action,
        details,
    };
    
    const auditLogPath = path.join(logsDir, 'audit.log');
    fs.appendFileSync(auditLogPath, JSON.stringify(logEntry) + '\n', 'utf8');
};

/**
 * Error logging
 */
exports.errorLog = (error, context = {}) => {
    const timestamp = new Date().toISOString();
    const logEntry = {
        timestamp,
        error: error.message,
        stack: error.stack,
        context,
    };
    
    const errorLogPath = path.join(logsDir, 'error.log');
    fs.appendFileSync(errorLogPath, JSON.stringify(logEntry) + '\n', 'utf8');
    
    console.error(`[${timestamp}] Error:`, error.message);
};

/**
 * Login attempt logging
 */
exports.loginLog = (username, success, ip) => {
    const timestamp = new Date().toISOString();
    const logEntry = {
        timestamp,
        type: 'LOGIN_ATTEMPT',
        username,
        success,
        ip,
    };
    
    const loginLogPath = path.join(logsDir, 'auth.log');
    fs.appendFileSync(loginLogPath, JSON.stringify(logEntry) + '\n', 'utf8');
};

/**
 * Admin action logging
 */
exports.adminActionLog = (admin, action, target, details = {}) => {
    const timestamp = new Date().toISOString();
    const logEntry = {
        timestamp,
        type: 'ADMIN_ACTION',
        admin,
        action,
        target,
        details,
    };
    
    exports.auditLog('ADMIN_ACTION', logEntry);
};

/**
 * Data access logging
 */
exports.dataAccessLog = (user, resource, action, ip) => {
    const timestamp = new Date().toISOString();
    const logEntry = {
        timestamp,
        type: 'DATA_ACCESS',
        user,
        resource,
        action,
        ip,
    };
    
    exports.auditLog('DATA_ACCESS', logEntry);
};

/**
 * Express middleware for request logging
 */
exports.requestLogger = (req, res, next) => {
    const start = Date.now();
    
    res.on('finish', () => {
        const duration = Date.now() - start;
        const timestamp = new Date().toISOString();
        const logEntry = {
            timestamp,
            method: req.method,
            path: req.path,
            status: res.statusCode,
            duration: `${duration}ms`,
            ip: req.ip,
        };
        
        const requestLogPath = path.join(logsDir, 'requests.log');
        fs.appendFileSync(requestLogPath, JSON.stringify(logEntry) + '\n', 'utf8');
    });
    
    next();
};
