/**
 * Database Migration: Add last_password_change column to users table
 * This ensures users can only change their password once per day
 */

const db = require('../config/db');

const addLastPasswordChangeColumn = () => {
  const query = `
    ALTER TABLE users 
    ADD COLUMN IF NOT EXISTS last_password_change TIMESTAMP NULL DEFAULT NULL;
  `;

  db.query(query, (err) => {
    if (err) {
      console.error('Error adding last_password_change column:', err);
      return;
    }
    console.log('Successfully added last_password_change column to users table');
  });
};

// Run migration
addLastPasswordChangeColumn();

module.exports = { addLastPasswordChangeColumn };
