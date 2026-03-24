const db = require('../config/db');
const { getDepartmentFilterConditions } = require('../middleware/authMiddleware');

exports.getHomepageStats = async (req, res) => {
  try {
    const con = db.promise();

    // Get department filter conditions
    let deptCondition = "";
    let deptParams = [];
    try {
      if (req.user && req.user.access_level) {
        const filter = getDepartmentFilterConditions(
          req.user.access_level,
          req.user.department,
          req.user.facultyId,
          'u'
        );
        if (filter.conditions.length > 0) {
          deptCondition = ` AND ${filter.conditions.join(" AND ")}`;
          deptParams = filter.params;
        }
      }
    } catch (err) {
      console.error('Department filter error:', err);
      return res.status(403).json({ success: false, message: 'Access denied: ' + err.message });
    }

    // Build a dept-only condition (excludes faculty-level filter for aggregate queries)
    let deptOnlyCondition = "";
    let deptOnlyParams = [];
    if (req.user) {
      if (req.user.access_level === 2 && req.user.department) {
        deptOnlyCondition = ` AND u.department = ?`;
        deptOnlyParams = [req.user.department];
      } else if (req.user.access_level === 3 && req.user.department) {
        deptOnlyCondition = ` AND u.department = ?`;
        deptOnlyParams = [req.user.department];
      }
      // access_level === 1 (admin): no dept filter → all departments considered
    }

    /* -------- DISCOVER ACTUAL NAME COLUMN IN users TABLE -------- */
    const [columns] = await con.query(`SHOW COLUMNS FROM users`);
    const colNames = columns.map(c => c.Field);
    const nameCol =
      colNames.find(c => c === 'faculty_name') ||
      colNames.find(c => c === 'name') ||
      colNames.find(c => c === 'full_name') ||
      colNames.find(c => c === 'fname') ||
      colNames.find(c => c.toLowerCase().includes('name')) ||
      'faculty_id';

    /* -------- TOTAL CITATIONS -------- */
    const [citations] = await con.query(`
      SELECT SUM(u.citations) AS total
      FROM users u
      WHERE u.faculty_id IS NOT NULL
      ${deptOnlyCondition}
    `, deptOnlyParams);

    /* -------- TOP CITED FACULTY -------- */
    const [topCitedRows] = await con.query(`
      SELECT ${nameCol} AS faculty_name, citations, department
      FROM users u
      WHERE u.faculty_id IS NOT NULL
        AND u.citations IS NOT NULL
      ${deptOnlyCondition}
      ORDER BY u.citations DESC
      LIMIT 1
    `, deptOnlyParams);

    const topCitedFaculty = topCitedRows[0] || null;

    /* -------- ACTUAL PAPER COUNT (DEDUPLICATED) -------- */
    const [actualPapers] = await con.query(`
      SELECT COUNT(DISTINCT p.doi) AS total
      FROM papers p
      JOIN users u ON p.scopus_id = u.scopus_id
      WHERE 1=1
      ${deptCondition}
    `, deptParams);

    /* -------- TOP 3 SDGs -------- */
    const [sdgRaw] = await con.query(`
      SELECT pi.sustainable_development_goals
      FROM paper_insights pi
      JOIN papers p ON pi.doi = p.doi
      JOIN users u ON p.scopus_id = u.scopus_id
      WHERE pi.sustainable_development_goals IS NOT NULL
        AND pi.sustainable_development_goals != ''
        AND pi.sustainable_development_goals != '-'
      ${deptCondition}
    `, deptParams);

    const sdgCount = {};
    for (const row of sdgRaw) {
      const sdgs = row.sustainable_development_goals.split('|').map(s => s.trim());
      sdgs.forEach(sdg => {
        if (sdg && sdg !== '-' && sdg !== 'none' && sdg !== 'N/A' && sdg.trim() !== '') {
          sdgCount[sdg] = (sdgCount[sdg] || 0) + 1;
        }
      });
    }

    const topSDGs = Object.entries(sdgCount)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3)
      .map(([sdg, count]) => ({ sdg, count }));

    /* -------- TOP 3 COLLAB COUNTRIES (EXCLUDING INDIA) -------- */
    const [countryRaw] = await con.query(`
      SELECT pi.country_list
      FROM paper_insights pi
      JOIN papers p ON pi.doi = p.doi
      JOIN users u ON p.scopus_id = u.scopus_id
      WHERE pi.country_list IS NOT NULL
      ${deptCondition}
    `, deptParams);

    const countryCount = {};
    for (const row of countryRaw) {
      const countries = row.country_list.split('|').map(c => c.trim());
      countries.forEach(c => {
        if (c && c.toLowerCase() !== 'india') {
          countryCount[c] = (countryCount[c] || 0) + 1;
        }
      });
    }

    const topCountries = Object.entries(countryCount)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3)
      .map(([country, count]) => ({ country, count }));

    /* -------- Q1 PAPERS (AS OF 2024) -------- */
    const [q1Data] = await con.query(`
      SELECT COUNT(*) AS total
      FROM faculty_quartile_summary fqs
      JOIN users u ON fqs.scopus_id = u.scopus_id
      WHERE fqs.quartile_2024 = 'Q1'
      ${deptCondition}
    `, deptParams);

    /* -------- TOTAL PUBLICATIONS (LAST 1 YEAR) -------- */
    const [recentPapers] = await con.query(`
      SELECT COUNT(*) AS total
      FROM papers p
      JOIN users u ON p.scopus_id = u.scopus_id
      WHERE p.date >= CURDATE() - INTERVAL 1 YEAR
      ${deptCondition}
    `, deptParams);

    /* -------- TOP FACULTY IN LAST 1 YEAR -------- */
    const [topRecentFacultyRows] = await con.query(`
      SELECT u.${nameCol} AS faculty_name, COUNT(*) AS paper_count
      FROM papers p
      JOIN users u ON p.scopus_id = u.scopus_id
      WHERE p.date >= CURDATE() - INTERVAL 1 YEAR
      ${deptCondition}
      GROUP BY u.scopus_id, u.${nameCol}
      ORDER BY paper_count DESC
      LIMIT 1
    `, deptParams);

    const topRecentFaculty = topRecentFacultyRows[0] || null;

    /* -------- TOP JOURNAL (by publication count) -------- */
    const [topJournalRow] = await con.query(`
  SELECT 
    pm.publication_name,
    pm.impact_factor_2025 AS impact_factor,
    COUNT(DISTINCT p.doi) AS paper_count

  FROM publication_metrics pm

  JOIN papers p 
    ON TRIM(LOWER(p.publication_name)) COLLATE utf8mb4_unicode_ci 
       = TRIM(LOWER(pm.publication_name))

  JOIN users u 
    ON p.scopus_id = u.scopus_id

  WHERE pm.impact_factor_2025 IS NOT NULL
    AND pm.scrape_status = 'success'

    -- ✅ ensure it's a real journal (not conference)
    AND LOWER(pm.publication_name) NOT LIKE '%conference%'
    AND LOWER(pm.publication_name) NOT LIKE '%proceeding%'
    AND LOWER(pm.publication_name) NOT LIKE '%symposium%'
    AND LOWER(pm.publication_name) NOT LIKE '%workshop%'

    ${deptCondition}

  GROUP BY pm.publication_name, pm.impact_factor_2025

  ORDER BY pm.impact_factor_2025 DESC

  LIMIT 1
`, deptParams);

    const topJournal = topJournalRow[0]
      ? {
        publication_name: topJournalRow[0].publication_name,
        impact_factor: parseFloat(topJournalRow[0].impact_factor),
        count: topJournalRow[0].paper_count
      }
      : { publication_name: 'N/A', impact_factor: 0, count: 0 };

    /* -------- TOP IMPACT FACTOR JOURNAL WITH FACULTY NAMES --------
       Logic:
       - Join papers → publication_metrics on publication_name to find journals
         that actually have papers authored by faculty in scope.
       - Filter: impact_factor_2025 must be non-null and scrape_status = 'success'
         so we only show journals with verified IF data.
       - access_level 1 (admin) → no department filter → all departments.
       - access_level 2/3 → deptCondition restricts to their department.
       - Order by impact_factor_2025 DESC, take the top 1 journal.
       - Collect all distinct faculty names who published in that journal
         using GROUP_CONCAT, then split on '|' in the response.
    ------------------------------------------------------------ */
    const [topIFJournalRows] = await con.query(`
  SELECT 
    u.scopus_id,
    u.${nameCol} AS faculty_name,

    COUNT(DISTINCT pm.publication_name) AS matched_journals,

    GROUP_CONCAT(
      DISTINCT CONCAT(
        pm.publication_name, 
        ' (IF: ', pm.impact_factor_2025, ')'
      )
      ORDER BY pm.impact_factor_2025 DESC
      SEPARATOR '|'
    ) AS journals_with_if

  FROM users u

  JOIN papers p 
    ON u.scopus_id = p.scopus_id

  JOIN publication_metrics pm 
    ON TRIM(LOWER(p.publication_name)) COLLATE utf8mb4_unicode_ci 
       = TRIM(LOWER(pm.publication_name))

  -- 🔥 Top 7 journals WITH papers
  JOIN (
      SELECT pm2.publication_name
      FROM publication_metrics pm2
      JOIN papers p2 
        ON TRIM(LOWER(p2.publication_name)) COLLATE utf8mb4_unicode_ci 
           = TRIM(LOWER(pm2.publication_name))
      WHERE pm2.impact_factor_2025 IS NOT NULL
        AND pm2.scrape_status = 'success'
      GROUP BY pm2.publication_name, pm2.impact_factor_2025
      ORDER BY pm2.impact_factor_2025 DESC
      LIMIT 7
  ) top_journals
    ON pm.publication_name = top_journals.publication_name

  WHERE 1=1
  ${deptCondition}

  GROUP BY u.scopus_id, u.${nameCol}

  HAVING COUNT(DISTINCT pm.publication_name) >= 2

  ORDER BY matched_journals DESC

  LIMIT 10
`, deptParams);

    let topIFJournal = [];

    if (topIFJournalRows.length > 0) {
      topIFJournal = topIFJournalRows.map(row => ({
        scopus_id: row.scopus_id,
        faculty_name: row.faculty_name,
        matched_journals: row.matched_journals,
        journals: row.journals_with_if
          ? row.journals_with_if.split('|').map(j => j.trim()).filter(Boolean)
          : []
      }));
    }

    /* -------- DEPARTMENT-WISE STATS -------- */
    let deptStatQuery = `
      SELECT 
        department,
        COUNT(faculty_id) AS faculty_count,
        SUM(docs_count)   AS total_papers,
        SUM(citations)    AS total_citations
      FROM users
      WHERE department IS NOT NULL 
        AND faculty_id IS NOT NULL
    `;
    let deptStatParams = [];

    if (req.user && req.user.access_level === 2 && req.user.department) {
      deptStatQuery += ` AND department = ?`;
      deptStatParams = [req.user.department];
    } else if (req.user && req.user.access_level === 3) {
      deptStatQuery += ` AND faculty_id = ?`;
      deptStatParams = [req.user.facultyId];
    }
    // access_level === 1: no extra filter

    deptStatQuery += ` GROUP BY department ORDER BY department`;

    const [deptStats] = await con.query(deptStatQuery, deptStatParams);

    /* -------- Q1/Q2 PER DEPARTMENT (2024) -------- */
    let quartileQuery = `
      SELECT 
        u.department,
        SUM(CASE WHEN fqs.quartile_2024 = 'Q1' THEN 1 ELSE 0 END) AS q1_count,
        SUM(CASE WHEN fqs.quartile_2024 = 'Q2' THEN 1 ELSE 0 END) AS q2_count
      FROM faculty_quartile_summary fqs
      JOIN users u ON fqs.scopus_id = u.scopus_id
      WHERE u.department IS NOT NULL
        AND u.faculty_id IS NOT NULL
    `;
    let quartileParams = [];

    if (req.user && req.user.access_level === 2 && req.user.department) {
      quartileQuery += ` AND u.department = ?`;
      quartileParams = [req.user.department];
    } else if (req.user && req.user.access_level === 3) {
      quartileQuery += ` AND u.faculty_id = ?`;
      quartileParams = [req.user.facultyId];
    }

    quartileQuery += ` GROUP BY u.department`;

    const [quartileStats] = await con.query(quartileQuery, quartileParams);

    const quartileMap = {};
    for (const row of quartileStats) {
      quartileMap[row.department] = {
        q1_count: Number(row.q1_count) || 0,
        q2_count: Number(row.q2_count) || 0,
      };
    }

    const enrichedDeptStats = deptStats.map(dept => ({
      ...dept,
      q1_count: quartileMap[dept.department]?.q1_count || 0,
      q2_count: quartileMap[dept.department]?.q2_count || 0,
    }));

    /* -------- RESPONSE -------- */
    res.json({
      totalCitations: citations[0].total || 0,
      topCitedFaculty: topCitedFaculty,
      totalPapers: actualPapers[0].total || 0,
      topRecentFaculty: topRecentFaculty,
      topSDGs,
      topCountries,
      recentQ1Papers: q1Data[0].total || 0,
      recentPublications: recentPapers[0].total || 0,
      topJournal,
      topIFJournal,          // ← NEW: highest impact factor journal + faculty names
      departmentStats: enrichedDeptStats,
    });

  } catch (err) {
    console.error('Error fetching homepage stats:', err);
    res.status(500).json({ error: 'Failed to fetch homepage stats' });
  }
};

exports.getDepartmentStats = async (req, res) => {
  try {
    const con = db.promise();

    const [deptStats] = await con.query(`
      SELECT 
        u.department,
        COUNT(DISTINCT u.faculty_id) AS faculty_count,
        SUM(u.docs_count)            AS total_papers,
        SUM(u.citations)             AS total_citations,
        COUNT(DISTINCT p.doi)        AS total_publications
      FROM users u
      LEFT JOIN papers p ON u.scopus_id = p.scopus_id
      WHERE u.department IS NOT NULL 
        AND u.faculty_id IS NOT NULL
      GROUP BY u.department
      ORDER BY total_papers DESC
    `);

    res.json(deptStats);

  } catch (err) {
    console.error('Error fetching department stats:', err);
    res.status(500).json({ error: 'Failed to fetch department stats' });
  }
};
