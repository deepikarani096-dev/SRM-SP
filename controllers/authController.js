const db = require('../config/db.js');
const bcrypt = require('bcryptjs');

const DEFAULT_USERNAME = 'admin';
const DEFAULT_PASSWORD = 'Admin';
const ADMIN_ACCESS_LEVEL = 1;

exports.login = (req, res) => {

    const { username, password } = req.body;

    console.log("🔐 Login attempt:", username);

    if (!username || !password) {
        return res.status(400).json({
            success: false,
            message: "Username and password are required"
        });
    }

    // Default admin login
    if (username === DEFAULT_USERNAME && password === DEFAULT_PASSWORD) {

        console.log("✅ Default admin login");

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

    console.log("📡 Running DB query for faculty_id:", username);

    const startTime = Date.now();

    db.query(usersQuery, [username], (err, results) => {

        console.log("📡 DB query finished in", Date.now() - startTime, "ms");

        if (err) {
            console.error("❌ Database error:", err);
            return res.status(500).json({
                success: false,
                message: "Database error"
            });
        }

        console.log("📦 DB results:", results);

        if (!results || results.length === 0) {
            console.log("❌ No user found");
            return res.json({
                success: false,
                message: "Invalid credentials"
            });
        }

        const user = results[0];

        console.log("🔑 Comparing password...");
        console.log("Input password:", password);
        console.log("Stored hash:", user.password);

        const bcryptStart = Date.now();

        bcrypt.compare(password, user.password, (err, isMatch) => {

            console.log("🔑 bcrypt finished in", Date.now() - bcryptStart, "ms");

            if (err) {
                console.error("❌ Bcrypt error:", err);
                return res.status(500).json({
                    success: false,
                    message: "Server error"
                });
            }

            console.log("🔑 bcrypt result:", isMatch);

            if (!isMatch) {
                return res.json({
                    success: false,
                    message: "Invalid credentials"
                });
            }

            console.log("✅ Login successful for:", user.faculty_id);

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
