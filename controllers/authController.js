const db = require('../config/db.js');
const bcrypt = require('bcryptjs');

const DEFAULT_USERNAME = 'admin';
const DEFAULT_PASSWORD = 'Admin';
const ADMIN_ACCESS_LEVEL = 1;

exports.login = (req, res) => {
    const { username, password } = req.body;

    // Default admin login
    if (username === DEFAULT_USERNAME && password === DEFAULT_PASSWORD) {
        return res.json({ 
            success: true, 
            message: 'Login successful (Default Admin)',
            user: {
                username: 'admin',
                accessLevel: ADMIN_ACCESS_LEVEL,
                isAdmin: true,
                facultyId: null,
                scopusId: null
            }
        });
    }

    // Try login from agents table (if exists)
    const agentsQuery = 'SELECT * FROM agents WHERE username = ? AND password = ?';
    db.query(agentsQuery, [username, password], (err, agentResults) => {
        if (!err && agentResults.length > 0) {
            return res.json({ 
                success: true, 
                message: 'Login successful',
                user: {
                    username: agentResults[0].username,
                    accessLevel: agentResults[0].access_level || 2,
                    facultyId: null,
                    scopusId: null
                }
            });
        }

        // Try login from users table with actual password field
        const usersQuery = 'SELECT id, faculty_id, faculty_name, scopus_id, access_level, email, department, password FROM users WHERE faculty_id = ?';
        
        db.query(usersQuery, [username], (err, userResults) => {
            if (err) return res.status(500).json({ success: false, message: 'Server error' });

            if (userResults.length > 0) {
                const user = userResults[0];
                
                // Compare password with hashed password using bcrypt
                bcrypt.compare(password, user.password, (err, isMatch) => {
                    if (err) {
                        console.error('Bcrypt error:', err);
                        return res.status(500).json({ success: false, message: 'Server error' });
                    }

                    if (isMatch) {
                        res.json({ 
                            success: true, 
                            message: 'Login successful',
                            user: {
                                id: user.id,
                                username: user.faculty_id,
                                facultyId: user.faculty_id,
                                facultyName: user.faculty_name,
                                scopusId: user.scopus_id,
                                accessLevel: user.access_level,
                                email: user.email,
                                department: user.department,
                                isAdmin: false
                            }
                        });
                    } else {
                        res.json({ success: false, message: 'Invalid credentials' });
                    }
                });
            } else {
                res.json({ success: false, message: 'Invalid credentials' });
            }
        });
    });
};
