const express = require('express');
const router = express.Router();
const { attachUser } = require('../middleware/authMiddleware');
const { getPaperFacultyRatio, getDepartments } = require('../controllers/paperFacultyRatioController');

router.get('/paper-faculty-ratio/departments', attachUser, getDepartments);
router.get('/paper-faculty-ratio', attachUser, getPaperFacultyRatio);

module.exports = router;
