// controllers/monthlyReportController.js

const db = require('../config/db');
const { getDepartmentFilterForRequest } = require('../middleware/authMiddleware');

// Helper to compute default year/month (previous month)
function getDefaultYearMonth(year, month) {
  if (year && year !== 'all' && month && month !== 'all') {
    return { joinYear: year, joinMonth: month };
  }
  const now = new Date();
  const prev = new Date(now.getFullYear(), now.getMonth() - 1, 1);
  return { joinYear: prev.getFullYear().toString(), joinMonth: (prev.getMonth() + 1).toString() };
}

const getAllMonthlyReports = (req, res) => {
  const { year, month } = req.query;
  const { joinYear, joinMonth } = getDefaultYearMonth(year, month);
  // Restrict access: Faculty (level 3) should not access the list endpoints
  if (req.user && req.user.access_level === 3) {
    return res.status(403).json({ success: false, error: 'Access denied' });
  }

  // Apply department filter for HoD (level 2) or allow Admin optional department param
  let deptJoin = '';
  let params = [parseInt(joinYear), parseInt(joinMonth)];
  try {
    const { conditions, params: filterParams } = getDepartmentFilterForRequest(req, 'u');
    if (conditions && conditions.length) {
      deptJoin = 'WHERE u.scopus_id IS NOT NULL AND ' + conditions.join(' AND ');
      params = [...filterParams, ...params];
    }
  } catch (err) {
    console.error('Department filter error:', err);
    return res.status(403).json({ success: false, error: 'Access denied: ' + err.message });
  }

  // Admin optional department parameter
  if (req.user && req.user.access_level === 1 && req.query && req.query.department) {
    if (deptJoin) {
      deptJoin += ' AND u.department = ?';
    } else {
      deptJoin = 'WHERE u.scopus_id IS NOT NULL AND u.department = ?';
    }
    params = [req.query.department, ...params];
  } else if (!deptJoin) {
    deptJoin = 'WHERE u.scopus_id IS NOT NULL';
  }

  const query = `
    SELECT 
      u.faculty_id,
      u.faculty_name as faculty_name,
      u.scopus_id,
      u.department,
      COALESCE(mar.docs_added, 0) as docs_added,
      COALESCE(mar.citations_added, 0) as citations_added,
      COALESCE(mar.total_docs, u.docs_count) as total_docs,
      COALESCE(mar.total_citations, u.citations) as total_citations,
      mar.report_year,
      mar.report_month,
      mar.created_at
    FROM users u
    LEFT JOIN monthly_author_report mar ON u.scopus_id = mar.scopus_id AND mar.report_year = ? AND mar.report_month = ?
    ${deptJoin}
    ORDER BY u.faculty_name ASC
  `;

  db.query(query, params, (err, results) => {
    if (err) {
      console.error('Error fetching monthly reports:', err);
      return res.status(500).json({ success: false, error: 'Failed to fetch monthly report data', message: err.message });
    }
    res.status(200).json(results);
  });
};

const getMonthlyReportByAuthor = (req, res) => {
  const { scopus_id } = req.params;
  const { year, month } = req.query;

  let query = `
    SELECT 
      mar.id,
      mar.scopus_id,
      mar.faculty_id,
      mar.report_year,
      mar.report_month,
      mar.docs_added,
      mar.citations_added,
      mar.total_docs,
      mar.total_citations,
      mar.created_at,
      u.faculty_name,
      u.department
    FROM monthly_author_report mar
    LEFT JOIN users u ON mar.faculty_id = u.faculty_id
    WHERE mar.scopus_id = ?
  `;

  const params = [scopus_id];
  if (year && year !== 'all') { query += ' AND mar.report_year = ?'; params.push(parseInt(year)); }
  if (month && month !== 'all') { query += ' AND mar.report_month = ?'; params.push(parseInt(month)); }
  query += ' ORDER BY mar.report_year DESC, mar.report_month DESC';

  db.query(query, params, (err, results) => {
    if (err) {
      console.error('Error fetching author monthly report:', err);
      return res.status(500).json({ success: false, error: 'Failed to fetch author monthly report', message: err.message });
    }
    if (results.length === 0) return res.status(404).json({ success: false, message: 'No reports found for this author' });
    res.status(200).json(results);
  });
};

/**
 * Get monthly report by faculty ID
 * Params: faculty_id
 * Query params: year, month
 */
const getMonthlyReportByFacultyId = (req, res) => {
    const { faculty_id } = req.params;
    const { year, month } = req.query;

    let query = `
      SELECT 
        mar.id,
        mar.scopus_id,
        mar.faculty_id,
        mar.report_year,
        mar.report_month,
        mar.docs_added,
        mar.citations_added,
        mar.total_docs,
        mar.total_citations,
        mar.created_at,
        u.faculty_name,
        u.department
      FROM monthly_author_report mar
      LEFT JOIN users u ON mar.faculty_id = u.faculty_id
      WHERE mar.faculty_id = ?
    `;

    const queryParams = [faculty_id];

    if (year && year !== 'all') {
        query += ' AND mar.report_year = ?';
        queryParams.push(parseInt(year));
    }

    if (month && month !== 'all') {
        query += ' AND mar.report_month = ?';
        queryParams.push(parseInt(month));
    }

    query += ' ORDER BY mar.report_year DESC, mar.report_month DESC';

    db.query(query, queryParams, (err, results) => {
        if (err) {
            console.error('Error fetching faculty monthly report:', err);
            return res.status(500).json({
                success: false,
                error: 'Failed to fetch faculty monthly report',
                message: err.message
            });
        }

        if (results.length === 0) {
            return res.status(404).json({
                success: false,
                message: 'No reports found for this faculty member'
            });
        }

        res.status(200).json(results);
    });
};

/**
 * Get summary statistics for monthly reports
 * Query params: year, month
 */
const getMonthlyReportSummary = (req, res) => {
    const { year, month } = req.query;
  // Restrict level 3 users from summary endpoint
  if (req.user && req.user.access_level === 3) {
    return res.status(403).json({ success: false, error: 'Access denied' });
  }

  // Apply department filter for HoD (level 2)
  const { conditions, params: filterParams } = getDepartmentFilterForRequest(req, 'u');

  let query = `
    SELECT 
    COUNT(DISTINCT scopus_id) as total_authors,
    COUNT(*) as total_records,
    SUM(docs_added) as total_docs_added,
    SUM(citations_added) as total_citations_added,
    AVG(docs_added) as avg_docs_per_author,
    AVG(citations_added) as avg_citations_per_author,
    MAX(docs_added) as max_docs_added,
    MAX(citations_added) as max_citations_added
    FROM monthly_author_report mar
    LEFT JOIN users u ON mar.scopus_id = u.scopus_id
    WHERE 1=1
  `;

  const queryParams = [...(filterParams || [])];

  if (conditions && conditions.length) {
    query += ' AND ' + conditions.join(' AND ');
  }

  if (year && year !== 'all') {
    query += ' AND report_year = ?';
    queryParams.push(parseInt(year));
  }

  if (month && month !== 'all') {
    query += ' AND report_month = ?';
    queryParams.push(parseInt(month));
  }

  db.query(query, queryParams, (err, results) => {
    if (err) {
      console.error('Error fetching summary stats:', err);
      return res.status(500).json({
        success: false,
        error: 'Failed to fetch summary statistics',
        message: err.message
      });
    }

    res.status(200).json(results[0] || {});
  });
};

/**
 * Get top performing authors for a specific period
 * Query params: year, month, limit (default: 10), sortBy (docs_added or citations_added)
 */
const getTopPerformers = (req, res) => {
    const { year, month, limit = 10, sortBy = 'docs_added' } = req.query;

    // Validate sortBy parameter
    const validSortFields = ['docs_added', 'citations_added', 'total_docs', 'total_citations'];
    const sortField = validSortFields.includes(sortBy) ? sortBy : 'docs_added';

    // Restrict level 3 users
    if (req.user && req.user.access_level === 3) {
        return res.status(403).json({ success: false, error: 'Access denied' });
    }

    // Apply department filter for HoD (level 2)
    const { conditions, params: filterParams } = getDepartmentFilterForRequest(req, 'u');

    let query = `
      SELECT 
        mar.scopus_id,
        mar.faculty_id,
        u.faculty_name,
        u.department,
        SUM(mar.docs_added) as total_docs_added,
        SUM(mar.citations_added) as total_citations_added,
        AVG(mar.total_docs) as avg_total_docs,
        AVG(mar.total_citations) as avg_total_citations,
        COUNT(*) as report_count
      FROM monthly_author_report mar
      LEFT JOIN users u ON mar.faculty_id = u.faculty_id
      WHERE 1=1
    `;

    const queryParams = [...(filterParams || [])];

    if (conditions && conditions.length) {
      query += ' AND ' + conditions.join(' AND ');
    }

    if (year && year !== 'all') {
        query += ' AND mar.report_year = ?';
        queryParams.push(parseInt(year));
    }

    if (month && month !== 'all') {
        query += ' AND mar.report_month = ?';
        queryParams.push(parseInt(month));
    }

    query += ` 
      GROUP BY mar.scopus_id, mar.faculty_id, u.faculty_name, u.department
      ORDER BY total_${sortField.replace('docs_added', 'docs_added').replace('citations_added', 'citations_added')} DESC
      LIMIT ?
    `;

    queryParams.push(parseInt(limit));

    db.query(query, queryParams, (err, results) => {
        if (err) {
            console.error('Error fetching top performers:', err);
            return res.status(500).json({
                success: false,
                error: 'Failed to fetch top performers',
                message: err.message
            });
        }

        res.status(200).json(results);
    });
};

/**
 * Get available years from the database
 */
const getAvailableYears = (req, res) => {
    const query = `
      SELECT DISTINCT report_year as year
      FROM monthly_author_report
      ORDER BY report_year DESC
    `;

    db.query(query, (err, results) => {
        if (err) {
            console.error('Error fetching available years:', err);
            return res.status(500).json({
                success: false,
                error: 'Failed to fetch available years',
                message: err.message
            });
        }

        res.status(200).json(results.map(row => row.year));
    });
};

/**
 * Get monthly trends (aggregated by month)
 * Query params: year
 */
const getMonthlyTrends = (req, res) => {
    const { year } = req.query;

    let query = `
      SELECT 
        report_year,
        report_month,
        COUNT(DISTINCT scopus_id) as author_count,
        SUM(docs_added) as total_docs,
        SUM(citations_added) as total_citations,
        AVG(docs_added) as avg_docs,
        AVG(citations_added) as avg_citations
      FROM monthly_author_report
      WHERE 1=1
    `;

    const queryParams = [];

    if (year && year !== 'all') {
        query += ' AND report_year = ?';
        queryParams.push(parseInt(year));
    }

    query += `
      GROUP BY report_year, report_month
      ORDER BY report_year DESC, report_month DESC
    `;

    db.query(query, queryParams, (err, results) => {
        if (err) {
            console.error('Error fetching monthly trends:', err);
            return res.status(500).json({
                success: false,
                error: 'Failed to fetch monthly trends',
                message: error.message
            });
        }

        res.status(200).json(results);
    });
};

/**
 * Get monthly reports with newly added papers for each faculty
 * Query params: year, month
 * UPDATED: Now includes all 6 author columns
 */
const getAllMonthlyReportsWithPapers = (req, res) => {
    const { year, month } = req.query;

    // Calculate previous month if no filters
    let defaultYear = year;
    let defaultMonth = month;
    if (!year || year === 'all') {
        const now = new Date();
        defaultYear = now.getMonth() === 0 ? (now.getFullYear() - 1).toString() : now.getFullYear().toString();
        defaultMonth = now.getMonth() === 0 ? '12' : (now.getMonth()).toString();
    }

    // Use provided or default for join
    const joinYear = year && year !== 'all' ? year : defaultYear;
    const joinMonth = month && month !== 'all' ? month : defaultMonth;

    // Restrict access: Faculty (level 3) should not access the list endpoints
    if (req.user && req.user.access_level === 3) {
      return res.status(403).json({ success: false, error: 'Access denied' });
    }

    // Build base query and params (place joinYear/joinMonth first so params align)
    let query = `
      SELECT 
        u.faculty_id,
        u.faculty_name as faculty_name,
        u.scopus_id,
        u.department,
        COALESCE(mar.docs_added, 0) as docs_added,
        COALESCE(mar.citations_added, 0) as citations_added,
        COALESCE(mar.total_docs, u.docs_count) as total_docs,
        COALESCE(mar.total_citations, u.citations) as total_citations,
        mar.report_year,
        mar.report_month,
        mar.created_at
      FROM users u
      LEFT JOIN monthly_author_report mar ON u.scopus_id = mar.scopus_id AND mar.report_year = ? AND mar.report_month = ?
      WHERE u.scopus_id IS NOT NULL
    `;

    const queryParams = [parseInt(joinYear), parseInt(joinMonth)];

    // Apply department filter for HoD (level 2) or Admin optional department param
    try {
      const { conditions, params: filterParams } = getDepartmentFilterForRequest(req, 'u');
      if (conditions && conditions.length) {
        // append conditions to WHERE and push params after the join year/month params
        query += ' AND ' + conditions.join(' AND ');
        queryParams.push(...(filterParams || []));
      }
    } catch (err) {
      console.error('Department filter error:', err);
      return res.status(403).json({ success: false, error: 'Access denied: ' + err.message });
    }

    query += '\n      ORDER BY u.faculty_name ASC\n    ';

    db.query(query, queryParams, (err, results) => {
        if (err) {
            console.error('Error fetching monthly reports:', err);
            return res.status(500).json({
                success: false,
                error: 'Failed to fetch monthly report data',
                message: err.message
            });
        }

        // For each faculty, get newly added papers in the same month
        if (results.length === 0) {
            return res.status(200).json([]);
        }

        let completedCount = 0;
        const enrichedResults = results.map((item, idx) => ({ ...item, papers: [], index: idx }));

        results.forEach((faculty, idx) => {
            // UPDATED: Now fetches all 6 author columns
            const paperQuery = `
                SELECT 
                    p.doi,
                    p.title,
                    p.type,
                    p.publication_name,
                    p.date,
                    p.scopus_id as paper_scopus_id,
                    p.quartile,
                    p.author1,
                    p.author2,
                    p.author3,
                    p.author4,
                    p.author5,
                    p.author6,
                    YEAR(p.date) as paper_year,
                    MONTH(p.date) as paper_month
                FROM papers p
                WHERE p.scopus_id = ?
                    AND YEAR(p.date) = ?
                    AND MONTH(p.date) = ?
                ORDER BY p.date DESC
            `;

            db.query(paperQuery, [faculty.scopus_id, parseInt(joinYear), parseInt(joinMonth)], (err, paperResults) => {
                if (!err && paperResults) {
                    enrichedResults[idx].papers = paperResults;
                }
                
                completedCount++;
                
                // Send response when all paper queries are complete
                if (completedCount === results.length) {
                    res.status(200).json(enrichedResults);
                }
            });
        });
    });
};

module.exports = {
    getAllMonthlyReports,
    getMonthlyReportByAuthor,
    getMonthlyReportByFacultyId,
    getMonthlyReportSummary,
    getTopPerformers,
    getAvailableYears,
    getMonthlyTrends,
    getAllMonthlyReportsWithPapers
};