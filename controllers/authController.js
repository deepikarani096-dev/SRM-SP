const db = require('../config/db.js');
const bcrypt = require('bcryptjs');

const DEFAULT_USERNAME = 'admin';
const DEFAULT_PASSWORD = 'Admin';
const ADMIN_ACCESS_LEVEL = 1;

exports.login = (req, res) => {

    const { username, password } = req.body;


    if (!username || !password) {
        return res.status(400).json({
            success: false,
            message: "Username and password are required"
        });
    }

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

    const usersQuery = `
        SELECT 
            id,
            faculty_id,
            faculty_name,
            scopus_id,
            access_level,
            email,
            department,
            password
        FROM users
        WHERE faculty_id = ?
    `;


    const startTime = Date.now();

    db.query(usersQuery, [username], (err, results) => {


        if (err) {
            console.error("❌ Database error:", err);
            return res.status(500).json({
                success: false,
                message: "Database error"
            });
        }


        if (!results || results.length === 0) {
            console.log("❌ No user found");
            return res.json({
                success: false,
                message: "Invalid credentials"
            });
        }

        const user = results[0];

        
        const bcryptStart = Date.now();

        bcrypt.compare(password, user.password, (err, isMatch) => {


            if (err) {
                console.error("❌ Bcrypt error:", err);
                return res.status(500).json({
                    success: false,
                    message: "Server error"
                });
            }


            if (!isMatch) {
                return res.json({
                    success: false,
                    message: "Invalid credentials"
                });
            }


            res.json({
                success: true,
                message: "Login successful",
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

        });

    });

};
