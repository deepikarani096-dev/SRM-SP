const express = require('express');
const router = express.Router();

const { getHomepageStats } = require('../controllers/homeController');
const { attachUser } = require('../middleware/authMiddleware');

// GET /api/homepage-stats with department filtering
router.get('/homepage-stats', attachUser, getHomepageStats);

module.exports = router;
