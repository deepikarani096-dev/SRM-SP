const db = require('../config/db');
const { getDepartmentFilterForRequest } = require('../middleware/authMiddleware');

exports.getAllFaculty = (req, res) => {
    const { sdg, domain, year, department } = req.query;

    let deptConditions = [];
    let deptParams = [];
    let userDepartment = null;
    try {
        if (req.user && req.user.access_level) {
            const filter = getDepartmentFilterForRequest(req, 'u');
            deptConditions = filter.conditions;
            deptParams = filter.params;
            // For HOD users, capture their department
            if (req.user.access_level === 2 && req.user.department) {
                userDepartment = req.user.department;
            }
        }
    } catch (err) {
        console.error('Department filter error:', err);
        return res.status(403).json({ success: false, message: 'Access denied: ' + err.message });
    }

    // Add additional department filter from query parameter if provided and user is admin
    if (department && department !== 'all' && req.user && req.user.access_level === 1) {
        deptConditions.push('u.department = ?');
        deptParams.push(department);
    }

    const filters = [];
    const params = [];

    if (sdg) {
        filters.push(`REPLACE(LOWER(pi.sustainable_development_goals), ' ', '') LIKE ?`);
        params.push(`%${sdg.toLowerCase().replace(/\s+/g, '')}%`);
    }
    if (domain) {
        // For C.Tech: use paper_domain table; For others: use paper_insights.asjc_field_name
        // Check passed department parameter first, then fall back to user's department for HOD
        const targetDept = department || userDepartment;
        const isCTech = targetDept === 'C.Tech';
        if (isCTech) {
            filters.push(`REPLACE(LOWER(pd.domain), ' ', '') LIKE ?`);
        } else {
            filters.push(`REPLACE(LOWER(pi.asjc_field_name), ' ', '') LIKE ?`);
        }
        params.push(`%${domain.toLowerCase().replace(/\s+/g, '')}%`);
    }
    if (year) {
        const yearNum = parseInt(year);
        if (isNaN(yearNum) || yearNum < 1900 || yearNum > 2100) {
            return res.status(400).json({ error: "Invalid year parameter" });
        }
        filters.push(`YEAR(p.date) = ?`);
        params.push(yearNum);
    }

    const whereClause = filters.length ? `AND ${filters.join(" AND ")}` : "";
    const deptWhereClause = deptConditions.length ? `AND ${deptConditions.join(" AND ")}` : "";

    // Determine which domain column to use based on passed department or user's department
    const targetDept = department || userDepartment;
    const isCTech = targetDept === 'C.Tech';
    const domainColumn = isCTech ? 'COALESCE(pd.domain, pi.asjc_field_name)' : 'COALESCE(pi.asjc_field_name, pd.domain)';

    const query = `
        SELECT
            u.faculty_id,
            u.faculty_name,
            u.department,
            MAX(u.docs_count) AS docs_count,
            MAX(u.access_level) AS access_level,
            MAX(u.h_index) AS h_index,
            MAX(u.fwci) AS fwci,
            GROUP_CONCAT(DISTINCT u.scopus_id SEPARATOR '|') AS scopus_ids,
            GROUP_CONCAT(DISTINCT pi.sustainable_development_goals SEPARATOR '|') AS all_sdgs,
            GROUP_CONCAT(DISTINCT ${domainColumn} SEPARATOR '|') AS all_domains,
            COUNT(DISTINCT p.doi) AS filtered_docs
        FROM users u
        LEFT JOIN papers p ON u.scopus_id = p.scopus_id
        LEFT JOIN paper_insights pi ON p.doi = pi.doi
        LEFT JOIN paper_domain pd ON p.doi = pd.doi
        WHERE u.faculty_id IS NOT NULL
        ${deptWhereClause}
        ${whereClause}
        GROUP BY u.faculty_id, u.faculty_name, u.department
        ORDER BY u.faculty_name;
    `;

    const allParams = [...deptParams, ...params];

    db.query(query, allParams, (err, results) => {
        if (err) {
            console.error(err);
            return res.status(500).json({ error: "Failed to fetch faculty data" });
        }
        const enriched = results.map(row => ({
            faculty_id: row.faculty_id,
            name: row.faculty_name,
            department: row.department,
            docs_count: row.docs_count,
            access_level: row.access_level,
            h_index: row.h_index,
            fwci: row.fwci !== null && row.fwci !== undefined ? parseFloat(row.fwci) : null,
            sdg: row.all_sdgs,
            domain: row.all_domains,
            docs_in_timeframe: row.filtered_docs,
            scopus_ids: row.scopus_ids ? row.scopus_ids.split('|').filter(Boolean) : []
        }));
        res.json(enriched);
    });
};

exports.getFacultyPaperStats = (req, res) => {
    const { timeframe } = req.query;

    let deptConditions = [];
    let deptParams = [];
    try {
        if (req.user && req.user.access_level) {
            const filter = getDepartmentFilterForRequest(req, 'u');
            deptConditions = filter.conditions;
            deptParams = filter.params;
        }
    } catch (err) {
        console.error('Department filter error:', err);
        return res.status(403).json({ success: false, message: 'Access denied: ' + err.message });
    }

    const currentYear = new Date().getFullYear();
    const previousYear = currentYear - 1;

    if (![currentYear.toString(), previousYear.toString()].includes(timeframe)) {
        return res.status(400).json({
            error: `Invalid timeframe. Only ${previousYear} and ${currentYear} are supported.`
        });
    }

    const startDate = `${timeframe}-01-01`;
    const endDate = `${timeframe}-12-31`;
    const deptWhereClause = deptConditions.length ? `AND ${deptConditions.join(" AND ")}` : "";

    const query = `
        SELECT
            u.faculty_id,
            u.faculty_name,
            u.department,
            GROUP_CONCAT(DISTINCT u.scopus_id SEPARATOR '|') AS scopus_ids,
            COUNT(DISTINCT p_all.doi) AS total_docs,
            COUNT(DISTINCT p_time.doi) AS timeframe_docs
        FROM users u
        LEFT JOIN papers p_all ON u.scopus_id = p_all.scopus_id
        LEFT JOIN papers p_time
            ON u.scopus_id = p_time.scopus_id
            AND p_time.date BETWEEN ? AND ?
        WHERE u.faculty_id IS NOT NULL
        ${deptWhereClause}
        GROUP BY u.faculty_id, u.faculty_name, u.department
        ORDER BY u.faculty_name;
    `;

    const allParams = [...deptParams, startDate, endDate];

    db.query(query, allParams, (err, results) => {
        if (err) {
            console.error(err);
            return res.status(500).json({ error: 'Failed to fetch data' });
        }
        const enriched = results.map(row => ({
            ...row,
            scopus_ids: row.scopus_ids ? row.scopus_ids.split('|').filter(Boolean) : []
        }));
        res.json(enriched);
    });
};

exports.getCriteriaFilteredFaculty = (req, res) => {
    const { start, end, papers, department } = req.query;

    let deptConditions = [];
    let deptParams = [];
    try {
        if (req.user && req.user.access_level) {
            const filter = getDepartmentFilterForRequest(req, 'u');
            deptConditions = filter.conditions;
            deptParams = filter.params;
        }
    } catch (err) {
        console.error('Department filter error:', err);
        return res.status(403).json({ success: false, message: 'Access denied: ' + err.message });
    }

    // Add additional department filter from query parameter if provided and user is admin
    if (department && department !== 'all' && req.user && req.user.access_level === 1) {
        deptConditions.push('u.department = ?');
        deptParams.push(department);
    }

    const conditions = [];
    const params = [];

    if (start && end) {
        conditions.push(`p.date BETWEEN ? AND ?`);
        params.push(start, end);
    }

    const whereClause = conditions.length ? `WHERE ${conditions.join(" AND ")}` : "";
    const deptWhereClause = deptConditions.length ? ` AND ${deptConditions.join(" AND ")}` : "";

    let query = `
        SELECT
            u.faculty_id,
            u.faculty_name,
            u.department,
            GROUP_CONCAT(DISTINCT u.scopus_id SEPARATOR '|') AS scopus_ids,
            COUNT(DISTINCT p.doi) AS timeframe_docs
        FROM users u
        LEFT JOIN papers p ON u.scopus_id = p.scopus_id
        ${whereClause}
        ${deptWhereClause}
        GROUP BY u.faculty_id, u.faculty_name, u.department
    `;

    const allParams = [...params, ...deptParams];

    if (papers) {
        query += ` HAVING timeframe_docs <= ?`;
        allParams.push(parseInt(papers));
    }
    query += ` ORDER BY u.faculty_name;`;

    db.query(query, allParams, (err, results) => {
        if (err) {
            console.error("DB Error:", err);
            return res.status(500).json({ error: "Failed to fetch data" });
        }
        const enriched = results.map(row => ({
            ...row,
            scopus_ids: row.scopus_ids ? row.scopus_ids.split('|').filter(Boolean) : []
        }));
        res.json(enriched);
    });
};

exports.getFacultyDetails = (req, res) => {
    const { facultyId } = req.params;
    const { sdg, domain, year, quartileYear, start, end } = req.query;

    let safeQuartileYear = "2024";
    if (quartileYear && /^\d{4}$/.test(quartileYear)) {
        const yearNum = parseInt(quartileYear);
        if (yearNum >= 2022 && yearNum <= 2030) {
            safeQuartileYear = quartileYear;
        }
    }

    const facultyQuery = `SELECT * FROM users WHERE faculty_id = ? OR scopus_id = ? LIMIT 1`;

    db.query(facultyQuery, [facultyId, facultyId], (err, facultyResults) => {
        if (err) return res.status(500).json({ error: "Failed to fetch faculty details" });
        if (!facultyResults.length) return res.status(404).json({ error: "Faculty not found" });

        const foundFacultyRecord = facultyResults[0];
        const foundFacultyId = foundFacultyRecord.faculty_id;
        const foundFacultyDept = foundFacultyRecord.department;

        if (req.user && req.user.access_level) {
            if (req.user.access_level === 2) {
                if (foundFacultyDept !== req.user.department) {
                    return res.status(403).json({ error: "You can only view faculty from your department" });
                }
            } else if (req.user.access_level === 3) {
                if (foundFacultyId !== req.user.facultyId) {
                    return res.status(403).json({ error: "You can only view your own faculty data" });
                }
            }
        }

        db.query(
            `SELECT
                GROUP_CONCAT(DISTINCT scopus_id SEPARATOR '|') AS scopus_ids,
                SUM(COALESCE(citations, 0)) AS citation_count,
                SUM(COALESCE(docs_count, 0)) AS docs_count,
                MAX(COALESCE(h_index, 0)) AS h_index,
                MAX(fwci) AS fwci
            FROM users WHERE faculty_id = ?`,
            [foundFacultyId],
            (err2, idRows) => {
                if (err2) console.warn('Failed to aggregate scopus_ids and metrics:', err2);

                const scopusArr = idRows?.[0]?.scopus_ids
                    ? idRows[0].scopus_ids.split('|').filter(Boolean)
                    : [];

                const faculty = {
                    name: foundFacultyRecord.faculty_name,
                    ...foundFacultyRecord,
                    scopus_ids: scopusArr,
                    citation_count: idRows?.[0]?.citation_count || foundFacultyRecord.citations || 0,
                    docs_count: idRows?.[0]?.docs_count || foundFacultyRecord.docs_count || 0,
                    h_index: idRows?.[0]?.h_index || foundFacultyRecord.h_index || null,
                    fwci: idRows?.[0]?.fwci !== null && idRows?.[0]?.fwci !== undefined
                        ? parseFloat(idRows[0].fwci)
                        : (foundFacultyRecord.fwci !== null ? parseFloat(foundFacultyRecord.fwci) : null)
                };

                // Get domain with max count for C.Tech faculty
                const getDomainQuery = () => {
                    if (foundFacultyDept !== 'C.Tech') {
                        return Promise.resolve(null);
                    }

                    return new Promise((resolve, reject) => {
                        const domainQuery = `
                            SELECT pd.domain, COUNT(*) as count
                            FROM users u
                            JOIN papers p ON u.scopus_id = p.scopus_id
                            LEFT JOIN paper_domain pd ON p.doi = pd.doi
                            WHERE u.faculty_id = ? AND pd.domain IS NOT NULL AND pd.domain != '' AND LOWER(pd.domain) != 'other'
                            GROUP BY pd.domain
                            ORDER BY count DESC
                            LIMIT 1
                        `;

                        db.query(domainQuery, [foundFacultyId], (err, domainResults) => {
                            if (err) {
                                console.warn('Failed to fetch domain info:', err);
                                resolve(null);
                            } else {
                                resolve(domainResults.length > 0 ? domainResults[0].domain : null);
                            }
                        });
                    });
                };

                const queryParams = [foundFacultyId];

                // Determine correct domain column based on department
                const isCTechDept = foundFacultyDept === 'C.Tech';
                const domainColumn = isCTechDept 
                    ? 'COALESCE(pd.domain, pi.asjc_field_name)' 
                    : 'COALESCE(pi.asjc_field_name, pd.domain)';

                let baseQuery = `
                    SELECT
                        p.*,
                        pi.sustainable_development_goals AS sdg,
                        ${domainColumn} AS domain,
                        fqs.quartile_2022,
                        fqs.quartile_2023,
                        fqs.quartile_2024,
                        fqs.quartile_${safeQuartileYear} AS quartile_value,
                        pm.impact_factor_2025,
                        pm.impact_factor_5year
                    FROM users u
                    JOIN papers p ON u.scopus_id = p.scopus_id
                    LEFT JOIN paper_insights pi ON p.doi = pi.doi
                    LEFT JOIN paper_domain pd ON p.doi = pd.doi
                    LEFT JOIN faculty_quartile_summary fqs
                        ON p.doi = fqs.doi AND p.scopus_id = fqs.scopus_id
                    LEFT JOIN publication_metrics pm
                        ON p.publication_name COLLATE utf8mb4_general_ci = pm.publication_name COLLATE utf8mb4_general_ci
                `;

                const conditions = [`u.faculty_id = ?`];

                if (start && end) {
                    conditions.push("p.date BETWEEN ? AND ?");
                    queryParams.push(start, end);
                }
                if (!start || !end) {
                    if (sdg) {
                        conditions.push("REPLACE(LOWER(pi.sustainable_development_goals), ' ', '') LIKE ?");
                        queryParams.push(`%${sdg.toLowerCase().replace(/\s+/g, "")}%`);
                    }
                    if (domain) {
                        // For C.Tech: filter on paper_domain.domain; For others: filter on paper_insights.asjc_field_name
                        const domainFilterCol = isCTechDept 
                            ? 'REPLACE(LOWER(COALESCE(pd.domain, pi.asjc_field_name)), \' \', \'\')'
                            : 'REPLACE(LOWER(COALESCE(pi.asjc_field_name, pd.domain)), \' \', \'\')';
                        conditions.push(`${domainFilterCol} LIKE ?`);
                        queryParams.push(`%${domain.toLowerCase().replace(/\s+/g, "")}%`);
                    }
                    if (year) {
                        const yearNum = parseInt(year);
                        if (isNaN(yearNum)) {
                            return res.status(400).json({ error: "Invalid year parameter" });
                        }
                        conditions.push("YEAR(p.date) = ?");
                        queryParams.push(yearNum);
                    }
                }

                baseQuery += ` WHERE ${conditions.join(" AND ")}`;
                baseQuery += ` ORDER BY p.date DESC`;

                // Execute domain query and papers query
                Promise.all([
                    getDomainQuery(),
                    new Promise((resolve, reject) => {
                        db.query(baseQuery, queryParams, (err, papersResults) => {
                            if (err) {
                                reject(err);
                            } else {
                                resolve(papersResults);
                            }
                        });
                    })
                ]).then(([domain, papersResults]) => {
                    // Add domain to faculty object if it's C.Tech
                    if (foundFacultyDept === 'C.Tech') {
                        faculty.domain = domain;
                    }

                    papersResults.forEach(paper => {
                        paper.quartile = paper.quartile_value || paper.quartile || null;
                        paper.quartile_year = safeQuartileYear;
                        paper.quartiles = {};
                        Object.keys(paper).forEach(key => {
                            const match = key.match(/^quartile_(\d{4})$/);
                            if (match && paper[key]) {
                                paper.quartiles[match[1]] = paper[key];
                            }
                        });
                    });

                    res.json({ faculty, papers: papersResults });
                }).catch(err => {
                    console.error("❌ Query Error:", err);
                    return res.status(500).json({ error: "Failed to fetch faculty papers" });
                });
            }
        );
    });
};

exports.getFacultyQuartileSummary = (req, res) => {
    const { facultyId } = req.params;

    db.query(
        `SELECT faculty_id, department FROM users WHERE faculty_id = ? LIMIT 1`,
        [facultyId],
        (err, facultyCheck) => {
            if (err) {
                console.error("Faculty check error:", err);
                return res.status(500).json({ error: "Failed to check faculty access" });
            }
            if (!facultyCheck.length) {
                return res.status(404).json({ error: "Faculty not found" });
            }

            const foundFacultyDept = facultyCheck[0].department;

            if (req.user && req.user.access_level) {
                if (req.user.access_level === 2) {
                    if (foundFacultyDept !== req.user.department) {
                        return res.status(403).json({ error: "You can only view faculty from your department" });
                    }
                } else if (req.user.access_level === 3) {
                    if (facultyId !== req.user.facultyId) {
                        return res.status(403).json({ error: "You can only view your own faculty data" });
                    }
                }
            }

            db.query(
                `SELECT DISTINCT scopus_id FROM users WHERE faculty_id = ?`,
                [facultyId],
                (err, scopusRows) => {
                    if (err) {
                        console.error("Scopus ID fetch error:", err);
                        return res.status(500).json({ error: "Failed to fetch faculty scopus IDs" });
                    }

                    const scopusIds = scopusRows.map(r => r.scopus_id);

                    db.query(
                        `SELECT * FROM faculty_quartile_summary WHERE scopus_id IN (?)`,
                        [scopusIds],
                        (err2, rows) => {
                            if (err2) {
                                console.error("Quartile summary error:", err2);
                                return res.status(500).json({ error: "Failed to fetch quartile summary" });
                            }

                            const summaryByYear = {};
                            for (const row of rows) {
                                for (const key of Object.keys(row)) {
                                    const match = key.match(/^quartile_(\d{4})$/);
                                    if (!match) continue;
                                    const year = match[1];
                                    const quartile = row[key];
                                    if (!summaryByYear[year]) {
                                        summaryByYear[year] = { q1_count: 0, q2_count: 0, q3_count: 0, q4_count: 0 };
                                    }
                                    switch (quartile) {
                                        case "Q1": summaryByYear[year].q1_count++; break;
                                        case "Q2": summaryByYear[year].q2_count++; break;
                                        case "Q3": summaryByYear[year].q3_count++; break;
                                        case "Q4": summaryByYear[year].q4_count++; break;
                                    }
                                }
                            }
                            res.json(summaryByYear);
                        }
                    );
                }
            );
        }
    );
};

exports.getAuthorList = (req, res) => {
    const { search, h_index_filter } = req.query;

    let deptConditions = [];
    let deptParams = [];
    try {
        if (req.user && req.user.access_level) {
            const filter = getDepartmentFilterForRequest(req, 'u');
            deptConditions = filter.conditions;
            deptParams = filter.params;
        }
    } catch (err) {
        console.error('Department filter error:', err);
        return res.status(403).json({ success: false, message: 'Access denied: ' + err.message });
    }

    const whereClauses = ['u.scopus_id IS NOT NULL'];
    const params = [];

    if (search && search.trim()) {
        whereClauses.push(`(LOWER(u.faculty_name) LIKE ? OR u.scopus_id LIKE ?)`);
        params.push(`%${search.toLowerCase()}%`, `%${search}%`);
    }

    whereClauses.push(...deptConditions);
    params.push(...deptParams);

    // ── faculty_id added to SELECT and GROUP BY ──────────────────────────
    let query = `
        SELECT
            u.faculty_id   AS faculty_id,
            u.scopus_id    AS scopus_id,
            u.faculty_name AS name,
            u.department,
            MAX(u.h_index) AS h_index
        FROM users u
        WHERE ${whereClauses.join(" AND ")}
        GROUP BY u.faculty_id, u.scopus_id, u.faculty_name, u.department
    `;

    if (h_index_filter && h_index_filter !== "none") {
        let hIndexCondition = null;
        switch (h_index_filter) {
            case "1-3":   hIndexCondition = `MAX(u.h_index) BETWEEN 1 AND 3`;   break;
            case "4-6":   hIndexCondition = `MAX(u.h_index) BETWEEN 4 AND 6`;   break;
            case "7-9":   hIndexCondition = `MAX(u.h_index) BETWEEN 7 AND 9`;   break;
            case "10-12": hIndexCondition = `MAX(u.h_index) BETWEEN 10 AND 12`; break;
            case "12+":   hIndexCondition = `MAX(u.h_index) > 12`;              break;
        }
        if (hIndexCondition) query += ` HAVING ${hIndexCondition}`;
    }

    query += ` ORDER BY h_index DESC, name ASC`;

    db.query(query, params, (err, results) => {
        if (err) {
            console.error("DB Error:", err);
            return res.status(500).json({ error: "Failed to fetch authors" });
        }
        res.json(results.map(r => ({
            faculty_id: r.faculty_id,
            scopus_id:  r.scopus_id,
            name:       r.name,
            department: r.department,
            h_index:    r.h_index,
        })));
    });
};

exports.getAuthorPerformance = (req, res) => {
    const facultyId = req.params.facultyId;
    const scopusId = req.params.scopus_id;
    const id = facultyId || scopusId;

    if (!id) return res.status(400).json({ error: "id (facultyId or scopus_id) is required" });

    const isScopus = Boolean(scopusId);

    const identityQuery = isScopus
        ? `SELECT faculty_name, MAX(h_index) AS h_index, MAX(department) AS department
           FROM users WHERE scopus_id = ? GROUP BY scopus_id, faculty_name`
        : `SELECT faculty_name, MAX(h_index) AS h_index, MAX(department) AS department
           FROM users WHERE faculty_id = ? GROUP BY faculty_id, faculty_name`;

    db.query(identityQuery, [id], (err, facultyResults) => {
        if (err) return res.status(500).json({ error: "Failed to fetch identity" });
        if (!facultyResults.length) return res.status(404).json({ error: "Author not found" });

        const { faculty_name: facultyName, h_index: facultyHIndex, department: facultyDept } = facultyResults[0];

        if (req.user && req.user.access_level) {
            if (req.user.access_level === 2) {
                if (facultyDept !== req.user.department) {
                    return res.status(403).json({ error: 'You can only view faculty from your department' });
                }
            } else if (req.user.access_level === 3) {
                const ownFacultyId = req.user.facultyId;
                const ownScopusId = req.user.scopus_id || req.user.scopusId || null;
                if (!(ownFacultyId === facultyId || ownFacultyId === scopusId || ownScopusId === scopusId || ownFacultyId === id)) {
                    return res.status(403).json({ error: 'You can only view your own faculty data' });
                }
            }
        }

        const currentYear = new Date().getFullYear();
        const last5Years = Array.from({ length: 5 }, (_, i) => currentYear - i);

        const chartQuery = isScopus
            ? `SELECT sc.year, sc.documents, sc.citations, sc.fwci
               FROM scopus_chart_data sc WHERE sc.scopus_id = ? ORDER BY sc.year ASC`
            : `SELECT sc.year,
                      SUM(sc.documents) AS documents,
                      SUM(sc.citations) AS citations,
                      AVG(CASE WHEN sc.fwci IS NOT NULL THEN sc.fwci END) AS fwci
               FROM scopus_chart_data sc JOIN users u ON sc.scopus_id = u.scopus_id
               WHERE u.faculty_id = ? GROUP BY sc.year ORDER BY sc.year ASC`;

        const academicYears = Array.from({ length: 3 }, (_, i) => {
            const start = currentYear - i - 1;
            const end = currentYear - i;
            return `${start}-${String(end).slice(-2)}`;
        }).reverse();

        const caseConditions = academicYears.map(ay => {
            const [startYear, endYearShort] = ay.split("-");
            const endYear = `20${endYearShort}`;
            return `WHEN p.date >= '${startYear}-07-01' AND p.date <= '${endYear}-06-30' THEN '${ay}'`;
        }).join("\n");

        const academicYearQuery = isScopus
            ? `SELECT CASE ${caseConditions} END AS academic_year, COUNT(DISTINCT p.doi) AS document_count
               FROM users u JOIN papers p ON u.scopus_id = p.scopus_id
               WHERE u.scopus_id = ?
                 AND p.date >= '${academicYears[0].split("-")[0]}-07-01'
                 AND p.date <= '${currentYear}-06-30'
               GROUP BY academic_year HAVING academic_year IS NOT NULL ORDER BY academic_year ASC`
            : `SELECT CASE ${caseConditions} END AS academic_year, COUNT(DISTINCT p.doi) AS document_count
               FROM users u JOIN papers p ON u.scopus_id = p.scopus_id
               WHERE u.faculty_id = ?
                 AND p.date >= '${academicYears[0].split("-")[0]}-07-01'
                 AND p.date <= '${currentYear}-06-30'
               GROUP BY academic_year HAVING academic_year IS NOT NULL ORDER BY academic_year ASC`;

        db.query(chartQuery, [id], (err, chartResults) => {
            if (err) return res.status(500).json({ error: "Failed to fetch chart data" });

            const full = req.query?.full === 'true';
            let normalized;

            if (full && chartResults?.length) {
                const years = chartResults.map(r => Number(r.year));
                const minYear = Math.min(...years);
                const maxYear = Math.max(...years);
                normalized = [];
                for (let y = minYear; y <= maxYear; y++) {
                    const found = chartResults.find(r => Number(r.year) === y);
                    normalized.push({
                        year: y,
                        documents: found ? Number(found.documents) : 0,
                        citations: found ? Number(found.citations) : 0,
                        fwci: found && found.fwci !== null && found.fwci !== undefined
                            ? parseFloat(Number(found.fwci).toFixed(4))
                            : null
                    });
                }
            } else {
                normalized = last5Years.map(y => {
                    const found = chartResults.find(r => Number(r.year) === y);
                    return {
                        year: y,
                        documents: found ? Number(found.documents) : 0,
                        citations: found ? Number(found.citations) : 0,
                        fwci: found && found.fwci !== null && found.fwci !== undefined
                            ? parseFloat(Number(found.fwci).toFixed(4))
                            : null
                    };
                });
            }

            db.query(academicYearQuery, [id], (err, academicResults) => {
                if (err) return res.status(500).json({ error: "Failed to fetch academic year data" });

                const processedAcademicData = academicYears.map(year => {
                    const found = academicResults.find(r => r.academic_year === year);
                    return { academic_year: year, document_count: found ? found.document_count : 0 };
                });

                const consistentYears = processedAcademicData.filter(y => y.document_count >= 2).length;
                const consistencyStatus = consistentYears === 3 ? "green" : consistentYears === 2 ? "orange" : "red";

                res.json({
                    id,
                    scopus_id: isScopus ? id : null,
                    name: facultyName,
                    h_index: facultyHIndex,
                    chart_data: normalized,
                    academic_year_data: processedAcademicData,
                    consistency_status: consistencyStatus
                });
            });
        });
    });
};

exports.getScopusChart = (req, res) => {
    const { scopus_id } = req.params;
    if (!scopus_id) return res.status(400).json({ error: 'scopus_id is required' });

    db.query(
        `SELECT year, documents, citations, fwci FROM scopus_chart_data WHERE scopus_id = ? ORDER BY year ASC`,
        [scopus_id],
        (err, rows) => {
            if (err) return res.status(500).json({ error: 'Failed to fetch scopus chart data' });
            res.json(rows.map(r => ({
                ...r,
                fwci: r.fwci !== null && r.fwci !== undefined ? parseFloat(r.fwci) : null
            })));
        }
    );
};

exports.getScopusChartForFaculty = (req, res) => {
    const { facultyId } = req.params;
    if (!facultyId) return res.status(400).json({ error: 'facultyId is required' });

    db.query(
        `SELECT sc.year,
                SUM(sc.documents) AS documents,
                SUM(sc.citations) AS citations,
                AVG(CASE WHEN sc.fwci IS NOT NULL THEN sc.fwci END) AS fwci
         FROM scopus_chart_data sc
         JOIN users u ON sc.scopus_id = u.scopus_id
         WHERE u.faculty_id = ?
         GROUP BY sc.year ORDER BY sc.year ASC`,
        [facultyId],
        (err, rows) => {
            if (err) return res.status(500).json({ error: 'Failed to fetch scopus chart data for faculty' });
            res.json(rows.map(r => ({
                ...r,
                fwci: r.fwci !== null && r.fwci !== undefined ? parseFloat(r.fwci) : null
            })));
        }
    );
};

exports.getFacultyTypeCount = (req, res) => {
    const { facultyId } = req.params;
    const { sdg, domain, year, start, end } = req.query;

    db.query(
        `SELECT DISTINCT scopus_id FROM users WHERE faculty_id = ? OR scopus_id = ?`,
        [facultyId, facultyId],
        (err, scopusRows) => {
            if (err) {
                console.error("Scopus ID fetch error:", err);
                return res.status(500).json({ error: "Failed to fetch faculty scopus IDs" });
            }
            if (!scopusRows.length) return res.status(404).json({ error: "Faculty not found" });

            const scopusIds = scopusRows.map(r => r.scopus_id).filter(id => id !== null);

            if (!scopusIds.length) {
                return res.json({ Journal: 0, "Conference Proceeding": 0, Book: 0 });
            }

            const placeholders = scopusIds.map(() => '?').join(',');
            let query = `
                SELECT COALESCE(p.type, 'Journal') as type, COUNT(DISTINCT p.id) as count
                FROM papers p
                WHERE p.scopus_id IN (${placeholders})
            `;
            const params = [...scopusIds];

            if (start && end) {
                query += ` AND p.date BETWEEN ? AND ?`;
                params.push(start, end);
            } else if (year) {
                const yearNum = parseInt(year);
                if (!isNaN(yearNum)) {
                    query += ` AND YEAR(p.date) = ?`;
                    params.push(yearNum);
                }
            }

            if (sdg || domain) {
                query += ` AND EXISTS (SELECT 1 FROM paper_insights pi WHERE pi.doi = p.doi`;
                if (sdg) {
                    query += ` AND REPLACE(LOWER(pi.sustainable_development_goals), ' ', '') LIKE ?`;
                    params.push(`%${sdg.toLowerCase().replace(/\s+/g, '')}%`);
                }
                if (domain) {
                    query += ` AND REPLACE(LOWER(pi.qs_subject_field_name), ' ', '') LIKE ?`;
                    params.push(`%${domain.toLowerCase().replace(/\s+/g, '')}%`);
                }
                query += `)`;
            }

            query += ` GROUP BY p.type ORDER BY count DESC`;

            db.query(query, params, (err, results) => {
                if (err) {
                    console.error("Type count fetch error:", err);
                    return res.status(500).json({ error: "Failed to fetch type counts" });
                }
                const typeMap = { 'Journal': 0, 'Conference Proceeding': 0, 'Book': 0 };
                results.forEach(row => {
                    if (typeMap.hasOwnProperty(row.type)) typeMap[row.type] = row.count;
                });
                return res.json(typeMap);
            });
        }
    );
};

exports.getFacultyCountryStats = (req, res) => {
    const { facultyId } = req.params;
    const { year } = req.query;

    db.query(
        `SELECT DISTINCT scopus_id FROM users WHERE faculty_id = ? OR scopus_id = ?`,
        [facultyId, facultyId],
        (err, scopusRows) => {
            if (err) return res.status(500).json({ error: "Failed to fetch scopus IDs" });
            if (!scopusRows.length) return res.status(404).json({ error: "Faculty not found" });

            const scopusIds = scopusRows.map(r => r.scopus_id).filter(Boolean);
            if (!scopusIds.length) return res.json([]);

            const placeholders = scopusIds.map(() => '?').join(',');

            let yearClause = '';
            const queryParams = [...scopusIds];

            if (year && year !== 'all') {
                yearClause = 'AND YEAR(p.date) = ?';
                queryParams.push(year);
            }

            const query = `
                SELECT pi.country_list,
                       p.title,
                       p.date,
                       p.doi,
                       pi.sustainable_development_goals,
                       pi.qs_subject_field_name,
                       pi.asjc_field_name,
                       pi.total_authors
                FROM papers p
                JOIN paper_insights pi ON p.doi = pi.doi
                WHERE p.scopus_id IN (${placeholders})
                  AND pi.country_list IS NOT NULL
                  AND TRIM(pi.country_list) != ''
                  ${yearClause}
            `;

            db.query(query, queryParams, (err, rows) => {
                if (err) return res.status(500).json({ error: "Failed to fetch country stats" });

                const countMap = {};
                const papersByCountry = {};

                for (const row of rows) {
                    row.country_list
                        .split(/[;|,]/)
                        .map(s => s.trim())
                        .filter(Boolean)
                        .filter(c => c.toLowerCase() !== 'india')
                        .forEach(c => {
                            countMap[c] = (countMap[c] || 0) + 1;
                            if (!papersByCountry[c]) papersByCountry[c] = [];
                            papersByCountry[c].push({
                                title: row.title || 'N/A',
                                date: row.date ? row.date.toISOString().split('T')[0] : 'N/A',
                                doi: row.doi,
                                sdgs: row.sustainable_development_goals || 'N/A',
                                subjects: row.qs_subject_field_name || 'N/A',
                                asjc: row.asjc_field_name || 'N/A',
                                authors: row.total_authors || 0
                            });
                        });
                }

                const result = Object.entries(countMap)
                    .map(([country, count]) => ({
                        country,
                        count,
                        papers: papersByCountry[country] || []
                    }))
                    .sort((a, b) => b.count - a.count)
                    .slice(0, 15);

                res.json(result);
            });
        }
    );
};

exports.getFacultyCountryStatsByYear = exports.getFacultyCountryStats;

/**
 * Export unique papers in IEEE format for a specific department.
 * Uses FULL author names (e.g. "John A. Smith") instead of abbreviated initials.
 * Query params: department (optional), year (optional)
 */
exports.exportFacultyPapersIEEE = (req, res) => {
    const { department, year } = req.query;

    const finalParams = [];
    if (department && department !== 'all') finalParams.push(department);
    if (year && year !== 'all') finalParams.push(parseInt(year));

    const finalQuery = `
        SELECT DISTINCT
            p.doi,
            p.title,
            p.type,
            p.publication_name,
            p.date,
            p.author1,
            p.author2,
            p.author3,
            p.author4,
            p.author5,
            p.author6
        FROM papers p
        WHERE p.scopus_id IN (
            SELECT DISTINCT u.scopus_id
            FROM users u
            ${department && department !== 'all' ? 'WHERE u.department = ?' : ''}
        )
        ${year && year !== 'all' ? 'AND YEAR(p.date) = ?' : ''}
        ORDER BY p.date DESC
    `;

    db.query(finalQuery, finalParams, (err, results) => {
        if (err) {
            console.error('Error fetching papers for export:', err);
            return res.status(500).json({ success: false, error: 'Failed to fetch papers', message: err.message });
        }

        if (!results || results.length === 0) {
            return res.status(200).json({
                success: true,
                papers: [],
                message: 'No papers found for the selected criteria'
            });
        }

        const ieeeFormattedPapers = results.map(paper => {
            // Collect non-null, non-empty authors
            const rawAuthors = [
                paper.author1,
                paper.author2,
                paper.author3,
                paper.author4,
                paper.author5,
                paper.author6,
            ].filter(a => a && a.trim());

            // ── FULL NAME format for IEEE ─────────────────────────────────
            // Standard IEEE uses "First M. Last" or "First Last".
            // We keep the full name exactly as stored, since the DB already
            // holds names as "First [Middle] Last".
            // We only reorder to "Last, First Middle" for the citation string
            // so it reads: Smith, John A., Doe, Jane B., ...
            const formattedAuthors = rawAuthors.map(author => {
                const parts = author.trim().split(/\s+/);
                if (parts.length === 1) return parts[0]; // only one token — use as-is
                // Last name is the final token; everything before is the first/middle name(s)
                const lastName  = parts[parts.length - 1];
                const firstPart = parts.slice(0, -1).join(' ');
                return `${lastName}, ${firstPart}`;
            });

            // Join authors with " and " between last two, commas for the rest
            let authorsStr = "Unknown Author";
            if (formattedAuthors.length === 1) {
                authorsStr = formattedAuthors[0];
            } else if (formattedAuthors.length === 2) {
                authorsStr = `${formattedAuthors[0]} and ${formattedAuthors[1]}`;
            } else {
                authorsStr =
                    formattedAuthors.slice(0, -1).join(', ') +
                    ', and ' +
                    formattedAuthors[formattedAuthors.length - 1];
            }

            const date      = paper.date ? new Date(paper.date) : null;
            const paperYear = date ? date.getFullYear() : 'n.d.';
            const title     = paper.title     || 'Untitled';
            const pub       = paper.publication_name || 'Unknown Publication';
            const type      = (paper.type || 'Journal').toLowerCase();

            // ── Build IEEE citation string ────────────────────────────────
            // Journal:  Author(s), "Title," Journal Name, year.
            // Conf:     Author(s), "Title," in Proc. Conference Name, year.
            // Book:     Author(s), Title. Publisher, year.
            let ieee_format = '';
            if (type.includes('conference')) {
                ieee_format = `${authorsStr}, "${title}," in Proc. ${pub}, ${paperYear}.`;
            } else if (type.includes('book')) {
                ieee_format = `${authorsStr}, ${title}. ${pub}, ${paperYear}.`;
            } else {
                // Default: journal
                ieee_format = `${authorsStr}, "${title}," ${pub}, ${paperYear}.`;
            }

            return {
                doi:         paper.doi,
                title,
                publication: pub,
                type:        paper.type || 'Journal',
                year:        paperYear,
                ieee_format,
            };
        });

        res.json({
            success: true,
            papers:  ieeeFormattedPapers,
            count:   ieeeFormattedPapers.length,
        });
    });
};

// ── Quartile Report Data ────────────────────────────────────────────────────
exports.getQuartileReport = (req, res) => {
    const { year, quartile, department } = req.query;

    let deptConditions = [];
    let deptParams = [];
    
    try {
        if (req.user && req.user.access_level) {
            const filter = getDepartmentFilterForRequest(req, 'u');
            deptConditions = filter.conditions;
            deptParams = filter.params;
        }
    } catch (err) {
        console.error('Department filter error:', err);
        return res.status(403).json({ success: false, message: 'Access denied: ' + err.message });
    }

    // Validate year
    const validYears = ['2022', '2023', '2024'];
    if (!year || !validYears.includes(year.toString())) {
        return res.status(400).json({ error: 'Invalid year. Must be 2022, 2023, or 2024' });
    }

    // Validate quartile
    const validQuartiles = ['Q1', 'Q2', 'Q3', 'Q4'];
    if (!quartile || !validQuartiles.includes(quartile.toString().toUpperCase())) {
        return res.status(400).json({ error: 'Invalid quartile. Must be Q1, Q2, Q3, or Q4' });
    }

    const quartileCol = `quartile_${year}`;

    const deptWhereClause = deptConditions.length ? `AND ${deptConditions.join(" AND ")}` : "";

    const query = `
        SELECT
            u.faculty_id,
            u.faculty_name,
            u.scopus_id,
            u.department,
            COUNT(DISTINCT fqs.doi) AS paper_count,
            GROUP_CONCAT(DISTINCT p.doi ORDER BY p.doi SEPARATOR '|') AS doi_list,
            GROUP_CONCAT(DISTINCT p.title ORDER BY p.doi SEPARATOR '||') AS title_list,
            GROUP_CONCAT(DISTINCT p.type ORDER BY p.doi SEPARATOR '||') AS type_list,
            GROUP_CONCAT(DISTINCT p.publication_name ORDER BY p.doi SEPARATOR '||') AS pub_list,
            GROUP_CONCAT(DISTINCT p.date ORDER BY p.doi SEPARATOR '||') AS date_list
        FROM users u
        INNER JOIN faculty_quartile_summary fqs ON u.scopus_id = fqs.scopus_id
        INNER JOIN papers p ON fqs.doi = p.doi
        WHERE fqs.${quartileCol} IS NOT NULL 
        AND fqs.${quartileCol} = ?
        ${deptWhereClause}
        GROUP BY u.faculty_id, u.faculty_name, u.scopus_id, u.department
        ORDER BY paper_count DESC, u.faculty_name ASC
    `;

    const params = [quartile, ...deptParams];

    db.query(query, params, (err, results) => {
        if (err) {
            console.error('Quartile report error:', err);
            return res.status(500).json({ error: 'Failed to fetch quartile report data' });
        }

        // Transform results
        const transformedResults = results.map(row => {
            const dois = row.doi_list ? row.doi_list.split('|') : [];
            const titles = row.title_list ? row.title_list.split('||') : [];
            const types = row.type_list ? row.type_list.split('||') : [];
            const pubs = row.pub_list ? row.pub_list.split('||') : [];
            const dates = row.date_list ? row.date_list.split('||') : [];

            const papers = dois.map((doi, idx) => ({
                doi: doi,
                title: titles[idx] || 'Unknown Title',
                type: types[idx] || 'Journal',
                publication_name: pubs[idx] || 'Unknown Publication',
                date: dates[idx] ? dates[idx].trim() : 'Date Not Available'
            }));

            return {
                faculty_id: row.faculty_id,
                faculty_name: row.faculty_name,
                scopus_id: row.scopus_id,
                department: row.department,
                paper_count: row.paper_count,
                papers: papers
            };
        });

        res.json({
            success: true,
            data: transformedResults,
            filters: { year, quartile }
        });
    });
};

// ── Quartile Summary Statistics ─────────────────────────────────────────────
exports.getQuartileSummaryStats = (req, res) => {
    const { department } = req.query;

    let deptConditions = [];
    let deptParams = [];
    
    try {
        if (req.user && req.user.access_level) {
            const filter = getDepartmentFilterForRequest(req, 'u');
            deptConditions = filter.conditions;
            deptParams = filter.params;
        }
    } catch (err) {
        console.error('Department filter error:', err);
        return res.status(403).json({ success: false, message: 'Access denied: ' + err.message });
    }

    const deptJoin = deptConditions.length ? `INNER JOIN users u ON fqs.scopus_id = u.scopus_id AND ${deptConditions.join(" AND ")}` : `LEFT JOIN users u ON fqs.scopus_id = u.scopus_id`;

    const query = `
        SELECT
            COUNT(DISTINCT CASE WHEN fqs.quartile_2024 = 'Q1' THEN fqs.doi END) AS q1_2024,
            COUNT(DISTINCT CASE WHEN fqs.quartile_2024 = 'Q2' THEN fqs.doi END) AS q2_2024,
            COUNT(DISTINCT CASE WHEN fqs.quartile_2024 = 'Q3' THEN fqs.doi END) AS q3_2024,
            COUNT(DISTINCT CASE WHEN fqs.quartile_2024 = 'Q4' THEN fqs.doi END) AS q4_2024,
            COUNT(DISTINCT CASE WHEN fqs.quartile_2023 = 'Q1' THEN fqs.doi END) AS q1_2023,
            COUNT(DISTINCT CASE WHEN fqs.quartile_2023 = 'Q2' THEN fqs.doi END) AS q2_2023,
            COUNT(DISTINCT CASE WHEN fqs.quartile_2023 = 'Q3' THEN fqs.doi END) AS q3_2023,
            COUNT(DISTINCT CASE WHEN fqs.quartile_2023 = 'Q4' THEN fqs.doi END) AS q4_2023,
            COUNT(DISTINCT CASE WHEN fqs.quartile_2022 = 'Q1' THEN fqs.doi END) AS q1_2022,
            COUNT(DISTINCT CASE WHEN fqs.quartile_2022 = 'Q2' THEN fqs.doi END) AS q2_2022,
            COUNT(DISTINCT CASE WHEN fqs.quartile_2022 = 'Q3' THEN fqs.doi END) AS q3_2022,
            COUNT(DISTINCT CASE WHEN fqs.quartile_2022 = 'Q4' THEN fqs.doi END) AS q4_2022
        FROM faculty_quartile_summary fqs
        ${deptJoin}
    `;

    const params = deptParams;

    db.query(query, params, (err, results) => {
        if (err) {
            console.error('Quartile summary stats error:', err);
            return res.status(500).json({ error: 'Failed to fetch quartile summary statistics' });
        }

        const data = results[0] || {};

        const stats = {
            2024: {
                Q1: parseInt(data.q1_2024) || 0,
                Q2: parseInt(data.q2_2024) || 0,
                Q3: parseInt(data.q3_2024) || 0,
                Q4: parseInt(data.q4_2024) || 0
            },
            2023: {
                Q1: parseInt(data.q1_2023) || 0,
                Q2: parseInt(data.q2_2023) || 0,
                Q3: parseInt(data.q3_2023) || 0,
                Q4: parseInt(data.q4_2023) || 0
            },
            2022: {
                Q1: parseInt(data.q1_2022) || 0,
                Q2: parseInt(data.q2_2022) || 0,
                Q3: parseInt(data.q3_2022) || 0,
                Q4: parseInt(data.q4_2022) || 0
            }
        };

        res.json({
            success: true,
            data: stats
        });
    });
};

// ── Get Available Domains by Department ─────────────────────────────────────
exports.getAvailableDomains = (req, res) => {
    const { department } = req.query;

    // Security: HOD (access_level 2) users can only fetch domains for their own department
    if (req.user && req.user.access_level === 2 && req.user.department) {
        if (department !== req.user.department) {
            return res.status(403).json({ error: 'You can only access domains for your own department' });
        }
    }

    // Static domain list for C.Tech department
    const cTechDomains = [
        'Other',
        'Visual Computing',
        'Theoretical Computing',
        'Fintech',
        'Computer Networks',
        'Green Computing',
        'Quantum Computing',
        'Advanced Multilingual Computing',
        'Sustainable Computing',
        'Accelerated Computing',
        'Geospatial Computing'
    ];

    // If C.Tech is selected, return C.Tech domains
    if (department === 'C.Tech') {
        return res.json({
            success: true,
            data: cTechDomains
        });
    }

    // For other departments, fetch unique asjc_field_name from paper_insights table
    try {
        if (req.user && req.user.access_level && department && department !== 'all') {
            // Query paper_insights.asjc_field_name for other departments
            const subquery = `
                SELECT DISTINCT pi.asjc_field_name
                FROM paper_insights pi
                INNER JOIN papers p ON pi.doi = p.doi
                INNER JOIN users u ON p.scopus_id = u.scopus_id
                WHERE u.department = ?
                  AND pi.asjc_field_name IS NOT NULL
                  AND TRIM(pi.asjc_field_name) != ''
                ORDER BY pi.asjc_field_name ASC
            `;
            
            db.query(subquery, [department], (err, results) => {
                if (err) {
                    console.error('Error fetching available domains:', err);
                    return res.status(500).json({ error: 'Failed to fetch domains' });
                }
                
                const domains = results.map(row => row.asjc_field_name).filter(Boolean);
                res.json({
                    success: true,
                    data: domains
                });
            });
        } else {
            // If no department/user, return empty
            res.json({
                success: true,
                data: []
            });
        }
    } catch (err) {
        console.error('Error in getAvailableDomains:', err);
        res.status(500).json({ error: 'Internal server error' });
    }
};
