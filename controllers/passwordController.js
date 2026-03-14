const db = require('../config/db.js');
const bcrypt = require('bcryptjs');
const crypto = require('crypto');
const { auditLog, adminActionLog } = require('../middleware/loggingMiddleware');

/**
 * Request password reset
 * Generates a reset token and stores it with expiration
 */
exports.requestPasswordReset = (req, res) => {
    const { email } = req.body;
    
    if (!email) {
        return res.status(400).json({ 
            success: false, 
            message: 'Email is required' 
        });
    }
    
    const userQuery = 'SELECT id, faculty_id FROM users WHERE email = ?';
    db.query(userQuery, [email], (err, results) => {
        if (err) {
            return res.status(500).json({ success: false, message: 'Server error' });
        }
        
        // Don't reveal if email exists (security best practice)
        if (results.length === 0) {
            return res.json({ 
                success: true, 
                message: 'If email exists, password reset link has been sent' 
            });
        }
        
        const user = results[0];
        
        // Generate reset token
        const resetToken = crypto.randomBytes(32).toString('hex');
        const resetTokenHash = bcrypt.hashSync(resetToken, 10);
        const expiresAt = new Date(Date.now() + 60 * 60 * 1000); // 1 hour expiry
        
        // Store reset token
        const updateQuery = `
            UPDATE users 
            SET reset_token = ?, reset_token_expires = ? 
            WHERE id = ?
        `;
        
        db.query(updateQuery, [resetTokenHash, expiresAt, user.id], (err) => {
            if (err) {
                return res.status(500).json({ success: false, message: 'Server error' });
            }
            
            auditLog('PASSWORD_RESET_REQUESTED', { 
                faculty_id: user.faculty_id, 
                email 
            });
            
            // In production, send email with reset link
            // For now, return token (ONLY for development!)
            res.json({
                success: true,
                message: 'Password reset link sent to email',
                // DEBUG ONLY - remove in production
                resetToken: process.env.NODE_ENV === 'development' ? resetToken : undefined
            });
        });
    });
};

/**
 * Reset password using token
 */
exports.resetPassword = (req, res) => {
    const { token, newPassword } = req.body;
    
    if (!token || !newPassword) {
        return res.status(400).json({ 
            success: false, 
            message: 'Token and new password are required' 
        });
    }
    
    if (newPassword.length < 6) {
        return res.status(400).json({ 
            success: false, 
            message: 'Password must be at least 6 characters' 
        });
    }
    
    // Find user with valid reset token
    const selectQuery = `
        SELECT id, faculty_id, reset_token, reset_token_expires 
        FROM users 
        WHERE reset_token IS NOT NULL 
        AND reset_token_expires > NOW()
    `;
    
    db.query(selectQuery, (err, results) => {
        if (err) {
            return res.status(500).json({ success: false, message: 'Server error' });
        }
        
        if (results.length === 0) {
            return res.status(400).json({ 
                success: false, 
                message: 'Invalid or expired reset token' 
            });
        }
        
        // Find matching user by comparing token hash
        let user = null;
        for (let u of results) {
            if (bcrypt.compareSync(token, u.reset_token)) {
                user = u;
                break;
            }
        }
        
        if (!user) {
            return res.status(400).json({ 
                success: false, 
                message: 'Invalid or expired reset token' 
            });
        }
        
        // Hash new password
        const hashedPassword = bcrypt.hashSync(newPassword, 10);
        
        // Update password and clear reset token
        const updateQuery = `
            UPDATE users 
            SET password = ?, reset_token = NULL, reset_token_expires = NULL 
            WHERE id = ?
        `;
        
        db.query(updateQuery, [hashedPassword, user.id], (err) => {
            if (err) {
                return res.status(500).json({ success: false, message: 'Server error' });
            }
            
            auditLog('PASSWORD_RESET_COMPLETED', { 
                faculty_id: user.faculty_id 
            });
            
            res.json({
                success: true,
                message: 'Password reset successfully'
            });
        });
    });
};

/**
 * Change password (for logged-in users)
 */
exports.changePassword = (req, res) => {
    const { currentPassword, newPassword } = req.body;
    const userId = req.user?.id || req.headers['user-id']; // Get from auth middleware or headers
    
    if (!currentPassword || !newPassword) {
        return res.status(400).json({ 
            success: false, 
            message: 'Current and new passwords are required' 
        });
    }
    
    if (newPassword.length < 6) {
        return res.status(400).json({ 
            success: false, 
            message: 'New password must be at least 6 characters' 
        });
    }
    
    if (currentPassword === newPassword) {
        return res.status(400).json({ 
            success: false, 
            message: 'New password must be different from current password' 
        });
    }

    if (!userId) {
        return res.status(401).json({ 
            success: false, 
            message: 'User not authenticated' 
        });
    }
    
    // Get user and verify current password
    const userQuery = 'SELECT id, password, faculty_id, last_password_change FROM users WHERE id = ?';
    db.query(userQuery, [userId], (err, results) => {
        if (err) {
            return res.status(500).json({ success: false, message: 'Server error' });
        }
        
        if (results.length === 0) {
            return res.status(401).json({ 
                success: false, 
                message: 'User not found' 
            });
        }
        
        const user = results[0];

        // Check if user can change password (rate limiting - once per day)
        if (user.last_password_change) {
            const lastChange = new Date(user.last_password_change);
            const now = new Date();
            const hoursSinceLastChange = (now - lastChange) / (1000 * 60 * 60);

            if (hoursSinceLastChange < 24) {
                const hoursUntilNext = Math.ceil(24 - hoursSinceLastChange);
                return res.status(429).json({
                    success: false,
                    message: `You can only change your password once per day. Please try again in ${hoursUntilNext} hour(s).`,
                    retryAfter: hoursUntilNext * 60 * 60, // in seconds
                });
            }
        }
        
        // Verify current password
        bcrypt.compare(currentPassword, user.password, (err, isMatch) => {
            if (err || !isMatch) {
                auditLog('PASSWORD_CHANGE_FAILED', { 
                    faculty_id: user.faculty_id,
                    reason: 'Invalid current password'
                });
                return res.status(401).json({ 
                    success: false, 
                    message: 'Current password is incorrect' 
                });
            }
            
            // Hash new password
            const hashedPassword = bcrypt.hashSync(newPassword, 10);
            
            // Update password and last_password_change timestamp
            const updateQuery = `
                UPDATE users 
                SET password = ?, last_password_change = NOW() 
                WHERE id = ?
            `;
            db.query(updateQuery, [hashedPassword, userId], (err) => {
                if (err) {
                    return res.status(500).json({ success: false, message: 'Server error' });
                }
                
                auditLog('PASSWORD_CHANGED', { 
                    faculty_id: user.faculty_id 
                });
                
                res.json({
                    success: true,
                    message: 'Password changed successfully'
                });
            });
        });
    });
};
