const mysql = require('mysql2');
const dotenv = require('dotenv');

dotenv.config();

const db = mysql.createPool({
    uri: process.env.DATABASE_URL,
    connectionLimit: 10,
    waitForConnections: true,
    queueLimit: 0
});

db.getConnection((err, connection) => {
    if (err) {
        console.error('❌ Error connecting to Railway MySQL database:', err);
        return;
    }

    console.log('✅ Connected to Railway MySQL database');
    connection.release();
});

module.exports = db;
