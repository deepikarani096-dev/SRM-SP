// Auth Middleware for role-based access control
const db = require('../config/db');

// Verify JWT-like token (for now using session/stored token)
exports.verifyToken = (req, res, next) => {
  const token = req.headers.authorization?.split(' ')[1] || req.body.token || req.query.token;
  
  if (!token) {
    return res.status(401).json({ success: false, message: 'No token provided' });
  }

  // Store token in request for later use
  req.token = token;
  next();
};

// Check if user is authenticated
exports.isAuthenticated = (req, res, next) => {
  const userId = req.body.userId || req.query.userId || req.headers['user-id'];
  const username = req.body.username || req.query.username || req.headers['username'];
  
  if (!userId && !username) {
    return res.status(401).json({ success: false, message: 'User not authenticated' });
  }

  req.userId = userId;
  req.username = username;
  next();
};

// NEW: Attach user info to req.user based on headers sent by frontend
// This middleware should be used on routes that need department-based filtering
exports.attachUser = (req, res, next) => {
  // Get user info from headers (sent by frontend)
  const userId = req.headers['user-id'] || req.body.userId || req.query.userId;
  const accessLevel = parseInt(req.headers['access-level'] || req.body.accessLevel || req.query.accessLevel || 0);
  const department = req.headers['department'] || req.body.department || req.query.department;
  const scopusId = req.headers['scopus-id'] || req.body.scopusId || req.query.scopusId;
  const username = req.headers['username'] || req.body.username || req.query.username;
  const facultyId = req.headers['faculty-id'] || req.body.facultyId || req.query.facultyId;

  // Attach user info to request
  req.user = {
    id: userId,
    username: username,
    access_level: accessLevel,
    department: department,
    facultyId: facultyId,
    scopus_id: scopusId
  };

  next();
};

// Check role-based access (access_level)
// access_level: 1 = Admin, 2 = Faculty (full access), 3 = Faculty (restricted - own data only)
exports.checkAccessLevel = (allowedLevels) => {
  return (req, res, next) => {
    const accessLevel = req.body.accessLevel || req.query.accessLevel || req.headers['access-level'];
    const username = req.body.username || req.query.username || req.headers['username'];
    
    if (!accessLevel) {
      return res.status(403).json({ success: false, message: 'Access level not provided' });
    }

    const level = parseInt(accessLevel);
    
    if (!allowedLevels.includes(level)) {
      return res.status(403).json({ 
        success: false, 
        message: `Access denied. Required level: ${allowedLevels}, Your level: ${level}` 
      });
    }

    req.accessLevel = level;
    req.username = username;
    next();
  };
};

// Admin only (access_level = 1)
exports.adminOnly = (req, res, next) => {
  const accessLevel = parseInt(req.body.accessLevel || req.query.accessLevel || req.headers['access-level'] || 0);
  
  if (accessLevel !== 1) {
    return res.status(403).json({ 
      success: false, 
      message: 'Admin access required' 
    });
  }
  
  next();
};

// Faculty only (access_level = 2 or 3)
exports.facultyOnly = (req, res, next) => {
  const accessLevel = parseInt(req.body.accessLevel || req.query.accessLevel || req.headers['access-level'] || 0);
  
  if (accessLevel !== 2 && accessLevel !== 3) {
    return res.status(403).json({ 
      success: false, 
      message: 'Faculty access required' 
    });
  }
  
  next();
};

// Restricted faculty (access_level = 3) - can only view own data
exports.restrictedFacultyOnly = (req, res, next) => {
  const accessLevel = parseInt(req.body.accessLevel || req.query.accessLevel || req.headers['access-level'] || 0);
  const facultyId = req.body.facultyId || req.query.facultyId || req.headers['faculty-id'];
  
  if (accessLevel !== 3) {
    return res.status(403).json({ 
      success: false, 
      message: 'Restricted faculty access required' 
    });
  }
  
  req.facultyId = facultyId;
  next();
};

// Verify user owns the resource (for restricted faculty)
exports.verifyOwnership = (resourceFacultyId) => {
  return (req, res, next) => {
    const accessLevel = parseInt(req.body.accessLevel || req.query.accessLevel || req.headers['access-level'] || 0);
    const userFacultyId = req.body.facultyId || req.query.facultyId || req.headers['faculty-id'];
    
    // Admin (level 1) and full access faculty (level 2) can access any resource
    if (accessLevel === 1 || accessLevel === 2) {
      return next();
    }
    
    // Restricted faculty (level 3) can only access their own resources
    if (accessLevel === 3) {
      if (userFacultyId !== resourceFacultyId) {
        return res.status(403).json({ 
          success: false, 
          message: 'You can only access your own faculty data' 
        });
      }
      return next();
    }
    
    return res.status(403).json({ 
      success: false, 
      message: 'Access denied' 
    });
  };
};

// ============================================================================
// DEPARTMENT-BASED FILTERING HELPER
// ============================================================================
// This function builds SQL WHERE clause fragments based on access_level & department
// Used by all controllers to enforce department-level RBAC

/**
 * Get department filter SQL conditions
 * @param {number} accessLevel - User's access level (1=Admin, 2=HoD, 3=Faculty)
 * @param {string} department - User's department
 * @param {string} userFacultyId - User's faculty ID (for level 3)
 * @param {string} tableAlias - Table alias for users table (default: 'u')
 * @returns {Object} { conditions: string[], params: array }
 *   conditions: Array of SQL WHERE clause segments
 *   params: Bind parameters in order
 */
exports.getDepartmentFilterConditions = (accessLevel, department, userFacultyId, tableAlias = 'u') => {
  const conditions = [];
  const params = [];

  if (accessLevel === 1) {
    // Admin (level 1): No department filter - can see all
    return { conditions, params };
  } else if (accessLevel === 2) {
    // HoD (level 2): Must see only their department
    if (!department) {
      throw new Error('Department required for access level 2 (HoD)');
    }
    conditions.push(`${tableAlias}.department = ?`);
    params.push(department);
  } else if (accessLevel === 3) {
    // Faculty (level 3): Must see only their own data
    if (!userFacultyId) {
      throw new Error('Faculty ID required for access level 3');
    }
    conditions.push(`${tableAlias}.faculty_id = ?`);
    params.push(userFacultyId);
  }

  return { conditions, params };
};

/**
 * Attach to req.user for easy access in controllers
 * Helper method to get department filter for current request
 */
exports.getDepartmentFilterForRequest = (req, tableAlias = 'u') => {
  if (!req.user) {
    throw new Error('req.user not populated. Use attachUser middleware first.');
  }
  
  const { access_level, department, facultyId } = req.user;
  // Allow Admin (level 1) to optionally filter by department via query param
  if (access_level === 1 && req.query && req.query.department) {
    return { conditions: [`${tableAlias}.department = ?`], params: [req.query.department] };
  }

  return exports.getDepartmentFilterConditions(access_level, department, facultyId, tableAlias);
};
