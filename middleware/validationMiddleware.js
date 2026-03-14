const validator = require('validator');

/**
 * Validate email format
 */
exports.validateEmail = (email) => {
    return validator.isEmail(email);
};

/**
 * Validate faculty ID format (alphanumeric, 3-20 chars)
 */
exports.validateFacultyId = (facultyId) => {
    return validator.isAlphanumeric(facultyId) && facultyId.length >= 3 && facultyId.length <= 20;
};

/**
 * Validate password strength
 * At least 6 characters
 */
exports.validatePassword = (password) => {
    return password && password.length >= 6;
};

/**
 * Validate Scopus ID (numeric only)
 */
exports.validateScopusId = (scopusId) => {
    return validator.isNumeric(scopusId.toString());
};

/**
 * Validate date range
 */
exports.validateDateRange = (startDate, endDate) => {
    const start = new Date(startDate);
    const end = new Date(endDate);
    
    if (isNaN(start) || isNaN(end)) return false;
    return start <= end;
};

/**
 * Validate year (1900-2100)
 */
exports.validateYear = (year) => {
    const yearNum = parseInt(year);
    return !isNaN(yearNum) && yearNum >= 1900 && yearNum <= 2100;
};

/**
 * Validate DOI format
 */
exports.validateDOI = (doi) => {
    return /^10\.\d{4,}\/\S+/.test(doi);
};

/**
 * Sanitize string input (prevent XSS)
 */
exports.sanitizeString = (str) => {
    if (!str) return '';
    return validator.escape(str).trim();
};

/**
 * Validation middleware for login endpoint
 */
exports.validateLoginInput = (req, res, next) => {
    const { username, password } = req.body;
    
    if (!username || !password) {
        return res.status(400).json({ 
            success: false, 
            message: 'Username and password are required' 
        });
    }
    
    if (!exports.validateFacultyId(username) && username !== 'admin') {
        return res.status(400).json({ 
            success: false, 
            message: 'Invalid faculty ID format' 
        });
    }
    
    // For login, just check password exists (don't enforce length)
    // Length enforcement is only for signup/password reset
    
    next();
};

/**
 * Validation middleware for faculty signup
 */
exports.validateSignupInput = (req, res, next) => {
    const { faculty_id, email, faculty_name, scopus_id } = req.body;
    
    if (!faculty_id || !email || !faculty_name || !scopus_id) {
        return res.status(400).json({ 
            success: false, 
            message: 'All required fields must be provided' 
        });
    }
    
    if (!exports.validateFacultyId(faculty_id)) {
        return res.status(400).json({ 
            success: false, 
            message: 'Invalid faculty ID format' 
        });
    }
    
    if (!exports.validateEmail(email)) {
        return res.status(400).json({ 
            success: false, 
            message: 'Invalid email format' 
        });
    }
    
    if (!exports.validateScopusId(scopus_id)) {
        return res.status(400).json({ 
            success: false, 
            message: 'Invalid Scopus ID format (must be numeric)' 
        });
    }
    
    next();
};

/**
 * Query parameter validation middleware
 */
exports.validateQueryParams = (req, res, next) => {
    const { year, start, end, quartileYear } = req.query;
    
    if (year && !exports.validateYear(year)) {
        return res.status(400).json({ 
            success: false, 
            message: 'Invalid year parameter' 
        });
    }
    
    if (start && end && !exports.validateDateRange(start, end)) {
        return res.status(400).json({ 
            success: false, 
            message: 'Start date must be before end date' 
        });
    }
    
    if (quartileYear && !exports.validateYear(quartileYear)) {
        return res.status(400).json({ 
            success: false, 
            message: 'Invalid quartile year' 
        });
    }
    
    next();
};
