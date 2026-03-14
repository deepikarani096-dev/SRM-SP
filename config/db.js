const mysql = require('mysql2');
const dotenv = require('dotenv');

dotenv.config();

// Create MySQL connection pool using Railway DATABASE_URL
const db = mysql.createPool(process.env.DATABASE_URL);

// Test connection
db.getConnection((err, connection) => {
    if (err) {
        console.error('Error connecting to Railway MySQL database:', err);
        return;
    }
    console.log('Connected to Railway MySQL database');

    // release the connection back to pool
    connection.release();
});

module.exports = db.promise();
