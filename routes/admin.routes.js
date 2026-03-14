const express = require("express");
const router = express.Router();
const path = require("path");
const { spawn } = require("child_process");
const multer = require("multer");
const fs = require("fs");
const db = require('../config/db');
const { sendApprovalEmail, sendRejectionEmail } = require('../utils/emailService');

const upload = multer({ dest: "uploads/" });

router.get("/run-refresh-stream", (req, res) => {
    res.setHeader("Content-Type", "text/event-stream");
    res.setHeader("Cache-Control", "no-cache");
    res.setHeader("Connection", "keep-alive");
    res.flushHeaders();

    const scriptPath = path.join(__dirname, "../db_thingies/new_scoups_sync.py");
    const pythonProcess = spawn("python3", [scriptPath]);

    pythonProcess.stdout.on("data", (data) => {
        const lines = data.toString().trim().split("\n");
        for (const line of lines) {
            try {
                const parsed = JSON.parse(line);
                res.write(`data: ${JSON.stringify(parsed)}\n\n`);
            } catch {
                res.write(`data: ${JSON.stringify({ status: line })}\n\n`);
            }
        }
    });

    pythonProcess.stderr.on("data", (data) => {
        res.write(`data: ${JSON.stringify({ status: "ERROR", message: data.toString().trim() })}\n\n`);
    });

    pythonProcess.on("close", (code) => {
        res.write(`data: ${JSON.stringify({ status: "COMPLETE", code })}\n\n`);
        res.end();
    });

    req.on("close", () => {
        pythonProcess.kill();
    });
});

router.get("/run-scopus-scraper", (req, res) => {
    res.setHeader("Content-Type", "text/event-stream");
    res.setHeader("Cache-Control", "no-cache");
    res.setHeader("Connection", "keep-alive");
    res.flushHeaders();

    // Use combined scraper that updates both total metrics and chart data in one pass
    const scriptPath = path.join(__dirname, "../db_thingies/scopus_sync_combined.py");
    const pythonProcess = spawn("python3", [scriptPath]);

    let processedCount = 0;
    let totalCount = 0;
    let successCount = 0;
    let failedCount = 0;
    let chartRowsCount = 0;

    pythonProcess.stdout.on("data", (data) => {
        const lines = data.toString().trim().split("\n");
        for (const line of lines) {
            try {
                const parsed = JSON.parse(line);
                res.write(`data: ${JSON.stringify(parsed)}\n\n`);
                if (parsed.processed !== undefined) processedCount = parsed.processed;
                if (parsed.total !== undefined) totalCount = parsed.total;
                if (parsed.success !== undefined) successCount = parsed.success;
                if (parsed.failed !== undefined) failedCount = parsed.failed;
                if (parsed.chart_rows !== undefined) chartRowsCount += parsed.chart_rows;
            } catch {
                res.write(`data: ${JSON.stringify({ 
                    status: "INFO", 
                    message: line,
                    processed: processedCount,
                    total: totalCount
                })}\n\n`);
            }
        }
    });

    pythonProcess.stderr.on("data", (data) => {
        res.write(`data: ${JSON.stringify({ 
            status: "ERROR", 
            message: data.toString().trim(),
            processed: processedCount,
            total: totalCount
        })}\n\n`);
    });

    pythonProcess.on("close", (code) => {
        const finalStatus = {
            status: code === 0 ? "COMPLETE" : "FAILED",
            message: code === 0 ? "Scopus sync completed successfully! Updated metrics and chart data." : "Scopus sync failed",
            processed: processedCount,
            total: totalCount,
            success: successCount,
            failed: failedCount,
            chart_rows_updated: chartRowsCount,
            progress: 100,
            code
        };
        res.write(`data: ${JSON.stringify(finalStatus)}\n\n`);
        res.end();
    });

    req.on("close", () => {
        pythonProcess.kill();
    });
});

router.post("/run-quartile-upload", upload.single("file"), (req, res) => {
    if (!req.file) {
        return res.status(400).json({ error: "No file uploaded" });
    }

    res.setHeader("Content-Type", "text/event-stream");
    res.setHeader("Cache-Control", "no-cache");
    res.setHeader("Connection", "keep-alive");
    res.flushHeaders();

    const scriptPath = path.join(__dirname, "../python_files/quartiles_update.py");
    const pythonProcess = spawn("python3", [scriptPath, req.file.path]);

    pythonProcess.stdout.on("data", (data) => {
        const lines = data.toString().trim().split("\n");
        for (const line of lines) {
            try {
                const parsed = JSON.parse(line);
                res.write(`data: ${JSON.stringify(parsed)}\n\n`);
            } catch {
                res.write(`data: ${JSON.stringify({ status: "INFO", message: line })}\n\n`);
            }
        }
    });

    pythonProcess.stderr.on("data", (data) => {
        res.write(`data: ${JSON.stringify({ status: "ERROR", message: data.toString().trim() })}\n\n`);
    });

    pythonProcess.on("close", (code) => {
        res.write(`data: ${JSON.stringify({ 
            status: code === 0 ? "COMPLETE" : "FAILED", 
            message: code === 0 ? "Quartile upload finished successfully!" : "Quartile upload failed", 
            code 
        })}\n\n`);
        res.end();
        fs.unlink(req.file.path, () => {});
    });

    req.on("close", () => {
        pythonProcess.kill();
    });
});

router.post("/run-scival-upload", upload.single("file"), (req, res) => {
    if (!req.file) {
        return res.status(400).json({ error: "No file uploaded" });
    }

    res.setHeader("Content-Type", "text/event-stream");
    res.setHeader("Cache-Control", "no-cache");
    res.setHeader("Connection", "keep-alive");
    res.flushHeaders();

    const scriptPath = path.join(__dirname, "../python_files/scival_data_to_db.py");
    const pythonProcess = spawn("python3", [scriptPath, req.file.path]);

    pythonProcess.stdout.on("data", (data) => {
        const lines = data.toString().trim().split("\n");
        for (const line of lines) {
            res.write(`data: ${JSON.stringify({ status: "INFO", message: line })}\n\n`);
        }
    });

    pythonProcess.stderr.on("data", (data) => {
        res.write(`data: ${JSON.stringify({ status: "ERROR", message: data.toString().trim() })}\n\n`);
    });

    pythonProcess.on("close", (code) => {
        res.write(`data: ${JSON.stringify({ 
            status: code === 0 ? "COMPLETE" : "FAILED", 
            message: code === 0 ? "Scival upload finished successfully!" : "Scival upload failed", 
            code 
        })}\n\n`);
        res.end();
        fs.unlink(req.file.path, () => {});
    });

    req.on("close", () => {
        pythonProcess.kill();
    });
});

// 🆕 New Route: Add Author to Database
router.post("/add-author", express.json(), async (req, res) => {
    try {
        const { name, scopus_id, faculty_id, email, designation, mobile_no, doj } = req.body;

        console.log("=== ADD AUTHOR REQUEST ===");
        console.log("Name:", name);
        console.log("Scopus ID:", scopus_id);
        console.log("Faculty ID:", faculty_id);
        console.log("Email:", email);
        console.log("Designation:", designation);
        console.log("Mobile No:", mobile_no);
        console.log("DOJ:", doj);

        // Validate input
        if (!name || !scopus_id || !faculty_id) {
            return res.status(400).json({ 
                error: "Missing required fields: name, scopus_id, and faculty_id are required" 
            });
        }

        // Validate Scopus ID format (should be numeric)
        if (!/^\d+$/.test(scopus_id)) {
            return res.status(400).json({ 
                error: "Invalid Scopus ID format. Must contain only numbers." 
            });
        }

        // Call Python script to add author to database
        const scriptPath = path.join(__dirname, "../db_thingies/add_author.py");
        console.log("Script path:", scriptPath);
        console.log("Script exists:", fs.existsSync(scriptPath));
        
        return new Promise((resolve, reject) => {
            const pythonProcess = spawn("python3", [
                scriptPath,
                name.trim(),
                scopus_id.trim(),
                faculty_id.trim(),
                email ? email.trim() : "",
                designation ? designation.trim() : "",
                mobile_no ? mobile_no.trim() : "",
                doj ? doj.trim() : ""
            ]);

            let stdout = "";
            let stderr = "";

            pythonProcess.stdout.on("data", (data) => {
                const output = data.toString();
                console.log("Python stdout:", output);
                stdout += output;
            });

            pythonProcess.stderr.on("data", (data) => {
                const error = data.toString();
                console.log("Python stderr:", error);
                stderr += error;
            });

            pythonProcess.on("close", (code) => {
                console.log("Python process exited with code:", code);
                console.log("Full stdout:", stdout);
                console.log("Full stderr:", stderr);

                if (code === 0) {
                    try {
                        // Try to parse JSON response from Python script
                        const result = JSON.parse(stdout.trim());
                        res.status(200).json({
                            success: true,
                            message: `Author "${name}" added successfully`,
                            data: result
                        });
                        resolve();
                    } catch (parseError) {
                        console.log("JSON parse error:", parseError);
                        // If not JSON, return raw output
                        res.status(200).json({
                            success: true,
                            message: `Author "${name}" added successfully`,
                            output: stdout.trim()
                        });
                        resolve();
                    }
                } else {
                    // Parse error details
                    let errorDetails = stderr.trim() || stdout.trim() || `Process exited with code ${code}`;
                    let parsedError = null;
                    
                    try {
                        // Try to parse JSON error from Python
                        parsedError = JSON.parse(stderr.trim() || stdout.trim());
                    } catch (e) {
                        // Not JSON, use raw text
                    }

                    // Check if author already exists
                    if (stderr.includes("already exists") || stdout.includes("already exists")) {
                        res.status(409).json({
                            error: `Author with Scopus ID ${scopus_id} already exists in the database`,
                            details: parsedError
                        });
                    } else {
                        res.status(500).json({
                            error: parsedError?.message || "Failed to add author to database",
                            exitCode: code,
                            stdout: stdout.trim(),
                            stderr: stderr.trim(),
                            details: parsedError || errorDetails
                        });
                    }
                    resolve();
                }
            });

            pythonProcess.on("error", (error) => {
                console.error("Python process error:", error);
                res.status(500).json({
                    error: "Failed to execute Python script",
                    details: error.message,
                    scriptPath: scriptPath
                });
                reject(error);
            });
        });

    } catch (error) {
        console.error("Add author error:", error);
        res.status(500).json({
            error: "Internal server error",
            details: error.message
        });
    }
});

// =====================================================
// NEW ENDPOINTS FOR PENDING AUTHOR APPROVALS
// =====================================================

// Submit author for approval (from sign-up page)
router.post("/submit-author-for-approval", express.json(), (req, res) => {
    try {
        const { faculty_name, email, scopus_id, faculty_id, designation, mobile_no, doj } = req.body;

        console.log("=== SUBMIT AUTHOR FOR APPROVAL REQUEST ===");
        console.log("Faculty Name:", faculty_name);
        console.log("Email:", email);
        console.log("Scopus ID:", scopus_id);
        console.log("Faculty ID:", faculty_id);

        // Validate required fields
        if (!faculty_name || !email || !scopus_id || !faculty_id) {
            console.log("Validation failed: Missing required fields");
            return res.status(400).json({ 
                error: "Missing required fields: faculty_name, email, scopus_id, and faculty_id are required" 
            });
        }

        // First check if scopus_id exists with 'rejected' status
        const checkRejectedQuery = `
            SELECT id, status FROM pending_faculty_approvals 
            WHERE scopus_id = ? AND status = 'rejected'
        `;

        db.query(checkRejectedQuery, [scopus_id], (err, results) => {
            if (err) {
                console.error("Database error during check:", err);
                return res.status(500).json({ 
                    error: "Failed to process request",
                    details: err.message 
                });
            }

            // If rejected record exists, update it to pending instead of inserting
            if (results && results.length > 0) {
                const rejectedId = results[0].id;
                const updateQuery = `
                    UPDATE pending_faculty_approvals 
                    SET faculty_name = ?, email = ?, faculty_id = ?, designation = ?, mobile_no = ?, doj = ?, 
                        status = 'pending', created_at = NOW(), rejection_reason = NULL, reviewed_at = NULL
                    WHERE id = ?
                `;

                db.query(
                    updateQuery,
                    [faculty_name, email, faculty_id, designation || null, mobile_no || null, doj || null, rejectedId],
                    (err, result) => {
                        if (err) {
                            console.error("Database error during update:", err);
                            return res.status(500).json({ 
                                error: "Failed to update request",
                                details: err.message 
                            });
                        }

                        console.log("Successfully updated rejected request to pending with ID:", rejectedId);
                        res.status(201).json({
                            success: true,
                            message: "Your profile has been resubmitted for admin approval",
                            requestId: rejectedId
                        });
                    }
                );
            } else {
                // No rejected record, proceed with normal insert
                const insertQuery = `
                    INSERT INTO pending_faculty_approvals 
                    (faculty_name, email, scopus_id, faculty_id, designation, mobile_no, doj, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
                `;

                db.query(
                    insertQuery,
                    [faculty_name, email, scopus_id, faculty_id, designation || null, mobile_no || null, doj || null],
                    (err, result) => {
                        if (err) {
                            console.error("Database error during insert:", err);
                            console.error("Error code:", err.code);
                            console.error("Error message:", err.message);
                            
                            if (err.code === 'ER_DUP_ENTRY') {
                                return res.status(400).json({ 
                                    error: "Scopus ID already exists in pending requests or system" 
                                });
                            }
                            return res.status(500).json({ 
                                error: "Failed to submit request",
                                details: err.message 
                            });
                        }

                        console.log("Successfully inserted approval request with ID:", result.insertId);
                        res.status(201).json({
                            success: true,
                            message: "Your profile has been submitted for admin approval",
                            requestId: result.insertId
                        });
                    }
                );
            }
        });

    } catch (error) {
        console.error("Submit author error:", error);
        res.status(500).json({ 
            error: "Internal server error",
            details: error.message 
        });
    }
});

// Get all pending author approvals
router.get("/pending-authors", (req, res) => {
    const query = `
        SELECT id, email, faculty_name, scopus_id, faculty_id, designation, mobile_no, doj, status, created_at, rejection_reason
        FROM pending_faculty_approvals
        WHERE status = 'pending'
        ORDER BY created_at DESC
    `;

    db.query(query, (err, results) => {
        if (err) {
            console.error("Database error:", err);
            return res.status(500).json({ error: "Failed to fetch pending approvals" });
        }

        res.json({
            success: true,
            count: results ? results.length : 0,
            data: results || []
        });
    });
});

// Approve author request
router.post("/approve-author/:id", express.json(), async (req, res) => {
    try {
        const { id } = req.params;

        // Get pending author details
        const getAuthorQuery = `
            SELECT * FROM pending_faculty_approvals WHERE id = ? AND status = 'pending'
        `;

        db.query(getAuthorQuery, [id], (err, results) => {
            if (err) {
                console.error("Database error:", err);
                return res.status(500).json({ error: "Database error" });
            }

            if (!results || results.length === 0) {
                return res.status(404).json({ error: "Pending author not found or already processed" });
            }

            const author = results[0];

            // Start transaction
            db.beginTransaction((err) => {
                if (err) {
                    console.error("Transaction error:", err);
                    return res.status(500).json({ error: "Transaction error" });
                }

                // Insert into users table
                const insertUserQuery = `
                    INSERT INTO users 
                    (faculty_id, faculty_name, designation, mobile_no, email, doj, scopus_id, access_level, docs_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 3, 0)
                `;

                db.query(
                    insertUserQuery,
                    [author.faculty_id, author.faculty_name, author.designation, author.mobile_no, author.email, author.doj, author.scopus_id],
                    (err) => {
                        if (err) {
                            console.error("Error inserting user:", err);
                            return db.rollback(() => {
                                if (err.code === 'ER_DUP_ENTRY') {
                                    return res.status(400).json({ error: "User already exists" });
                                }
                                res.status(500).json({ error: "Failed to add user" });
                            });
                        }

                        // Update pending_faculty_approvals status
                        const updateStatusQuery = `
                            UPDATE pending_faculty_approvals 
                            SET status = 'approved', reviewed_at = NOW()
                            WHERE id = ?
                        `;

                        db.query(updateStatusQuery, [id], (err) => {
                            if (err) {
                                console.error("Error updating status:", err);
                                return db.rollback(() => {
                                    res.status(500).json({ error: "Failed to update status" });
                                });
                            }

                            // Commit transaction
                            db.commit(async (err) => {
                                if (err) {
                                    console.error("Commit error:", err);
                                    return db.rollback(() => {
                                        res.status(500).json({ error: "Failed to commit changes" });
                                    });
                                }

                                // Send approval email
                                const emailSent = await sendApprovalEmail(author.email, author.faculty_name);

                                res.json({
                                    success: true,
                                    message: `Author ${author.faculty_name} approved and added to database`,
                                    approvedAuthor: {
                                        faculty_id: author.faculty_id,
                                        faculty_name: author.faculty_name,
                                        scopus_id: author.scopus_id,
                                        email: author.email
                                    },
                                    emailSent: emailSent
                                });
                            });
                        });
                    }
                );
            });
        });

    } catch (error) {
        console.error("Approve author error:", error);
        res.status(500).json({ error: "Internal server error" });
    }
});

// Reject author request
router.post("/reject-author/:id", express.json(), async (req, res) => {
    try {
        const { id } = req.params;
        const { rejection_reason } = req.body;

        // Validate rejection reason is provided and not empty
        if (!rejection_reason || rejection_reason.trim().length === 0) {
            return res.status(400).json({ 
                error: "Rejection reason is required" 
            });
        }

        // First get the author details before updating
        const getAuthorQuery = `
            SELECT id, email, faculty_name FROM pending_faculty_approvals WHERE id = ? AND status = 'pending'
        `;

        db.query(getAuthorQuery, [id], async (err, results) => {
            if (err) {
                console.error("Database error:", err);
                return res.status(500).json({ error: "Failed to reject request" });
            }

            if (!results || results.length === 0) {
                return res.status(404).json({ error: "Pending author not found" });
            }

            const author = results[0];

            const updateQuery = `
                UPDATE pending_faculty_approvals
                SET status = 'rejected', rejection_reason = ?, reviewed_at = NOW()
                WHERE id = ? AND status = 'pending'
            `;

            db.query(updateQuery, [rejection_reason.trim(), id], async (err, result) => {
                if (err) {
                    console.error("Database error:", err);
                    return res.status(500).json({ error: "Failed to reject request" });
                }

                if (result.affectedRows === 0) {
                    return res.status(404).json({ error: "Pending author not found" });
                }

                // Send rejection email
                const emailSent = await sendRejectionEmail(author.email, author.faculty_name, rejection_reason.trim());

                res.json({
                    success: true,
                    message: "Author request rejected",
                    emailSent: emailSent
                });
            });
        });

    } catch (error) {
        console.error("Reject author error:", error);
        res.status(500).json({ error: "Internal server error" });
    }
});

module.exports = router;