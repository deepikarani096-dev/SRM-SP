const nodemailer = require('nodemailer');
require('dotenv').config();

// For production, use environment variables or a more secure method
const transporter = nodemailer.createTransport({
    service: 'gmail',
    auth: {
        user: process.env.EMAIL_USER || 'your-email@gmail.com',
        pass: process.env.EMAIL_PASSWORD || 'your-app-password'
    }
});

// Verify transporter configuration
transporter.verify((error, success) => {
    if (error) {
        console.warn('Email transporter verification failed:', error.message);
        console.warn('Email notifications may not work. Configure EMAIL_USER and EMAIL_PASSWORD in .env');
    } else {
        console.log('Email service is ready');
    }
});

/**
 * Send approval acceptance email to faculty
 * @param {string} recipientEmail - Faculty email address
 * @param {string} facultyName - Faculty member's full name
 * @returns {Promise<boolean>} - Returns true if email sent successfully
 */
const sendApprovalEmail = async (recipientEmail, facultyName) => {
    try {
        const mailOptions = {
            from: process.env.EMAIL_USER || 'noreply@srmsp.edu.in',
            to: recipientEmail,
            subject: '✅ Your Registration Has Been Approved - SRM Scopus Portal',
            html: `
                <!DOCTYPE html>
                <html lang="en">
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <style>
                        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; }
                        .container { max-width: 600px; margin: 0 auto; padding: 20px; background: #f9fafb; border-radius: 8px; }
                        .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 8px 8px 0 0; text-align: center; }
                        .header h1 { margin: 0; font-size: 28px; }
                        .content { background: white; padding: 30px; border-radius: 0 0 8px 8px; }
                        .success-icon { font-size: 48px; margin: 20px 0; text-align: center; }
                        .message { font-size: 16px; margin: 20px 0; }
                        .details { background: #f0f4ff; padding: 15px; border-left: 4px solid #667eea; margin: 20px 0; border-radius: 4px; }
                        .details p { margin: 8px 0; font-size: 15px; }
                        .details .label { color: #4338ca; font-weight: 600; }
                        .password-box { background: #fefce8; border: 2px dashed #ca8a04; padding: 18px 20px; border-radius: 6px; margin: 22px 0; text-align: center; }
                        .password-box p { margin: 6px 0; }
                        .password-box .pwd-label { font-size: 13px; color: #854d0e; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }
                        .password-box .pwd-value { font-size: 22px; font-weight: 800; color: #1e1b4b; letter-spacing: 3px; font-family: 'Courier New', Courier, monospace; margin: 8px 0; }
                        .warning-box { background: #fff7ed; border-left: 4px solid #ea580c; padding: 14px 18px; border-radius: 4px; margin: 18px 0; }
                        .warning-box p { margin: 4px 0; font-size: 14px; color: #9a3412; }
                        .warning-box .warning-title { font-weight: 700; color: #c2410c; font-size: 15px; }
                        .cta-button { display: inline-block; background: #667eea; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; margin: 20px 0; font-weight: 600; font-size: 15px; }
                        .footer { background: #f9fafb; padding: 20px; text-align: center; font-size: 12px; color: #666; border-top: 1px solid #e5e7eb; margin-top: 20px; border-radius: 0 0 8px 8px; }
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="header">
                            <h1>Welcome to SRM Scopus Portal</h1>
                        </div>
                        <div class="content">
                            <div class="success-icon">✅</div>
                            <h2 style="color: #16a34a; text-align: center; margin-top: 10px;">Registration Approved!</h2>
                            <p>Dear ${facultyName},</p>
                            <p class="message">Congratulations! Your registration request has been <strong>approved</strong> by the administrator. Your account has been fully activated.</p>

                            <div class="details">
                                <p><span class="label">Status:</span> &nbsp; ✅ Approved</p>
                                <p><span class="label">Date:</span> &nbsp; ${new Date().toLocaleDateString('en-IN', { year: 'numeric', month: 'long', day: 'numeric' })}</p>
                            </div>

                            <div class="password-box">
                                <p class="pwd-label">⌨️ Your Temporary Password</p>
                                <p class="pwd-value">facultypwd</p>
                            </div>

                            <div class="warning-box">
                                <p class="warning-title">⚠️ Important — Please Read</p>
                                <p>The password above is a <strong>temporary password</strong> assigned to your account. You <strong>must change it immediately</strong> after your first login to keep your account secure.</p>
                                <p>Go to <strong>Profile Settings → Change Password</strong> after logging in.</p>
                            </div>

                            <p style="font-size: 15px;">You can now access the SRM Scopus Research Portal using your Faculty ID and the temporary password provided above.</p>
                            <center>
                                <a href="${process.env.PORTAL_URL || 'http://localhost:3000'}" class="cta-button">Access Portal</a>
                            </center>
                            <p style="margin-top: 30px; font-size: 14px; color: #666;">If you have any questions, please contact the administration team.</p>
                        </div>
                        <div class="footer">
                            <p>SRM Scopus Research Portal &copy; 2026. All rights reserved.</p>
                        </div>
                    </div>
                </body>
                </html>
            `
        };

        const info = await transporter.sendMail(mailOptions);
        console.log('Approval email sent:', info.messageId);
        return true;
    } catch (error) {
        console.error('Error sending approval email:', error);
        return false;
    }
};

/**
 * Send rejection email to faculty
 * @param {string} recipientEmail - Faculty email address
 * @param {string} facultyName - Faculty member's full name
 * @param {string} rejectionReason - Reason for rejection
 * @returns {Promise<boolean>} - Returns true if email sent successfully
 */
const sendRejectionEmail = async (recipientEmail, facultyName, rejectionReason) => {
    try {
        const mailOptions = {
            from: process.env.EMAIL_USER || 'noreply@srmsp.edu.in',
            to: recipientEmail,
            subject: '❌ Registration Request Update - SRM Scopus Portal',
            html: `
                <!DOCTYPE html>
                <html lang="en">
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <style>
                        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; }
                        .container { max-width: 600px; margin: 0 auto; padding: 20px; background: #f9fafb; border-radius: 8px; }
                        .header { background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%); color: white; padding: 30px; border-radius: 8px 8px 0 0; text-align: center; }
                        .header h1 { margin: 0; font-size: 28px; }
                        .content { background: white; padding: 30px; border-radius: 0 0 8px 8px; }
                        .rejection-icon { font-size: 48px; margin: 20px 0; text-align: center; }
                        .message { font-size: 16px; margin: 20px 0; }
                        .reason-box { background: #fef2f2; padding: 20px; border-left: 4px solid #ef4444; margin: 20px 0; border-radius: 4px; }
                        .reason-box h3 { margin-top: 0; color: #991b1b; }
                        .reason-box p { margin: 0; color: #7f1d1d; }
                        .reapply { background: #f0f4ff; padding: 15px; border-left: 4px solid #667eea; margin: 20px 0; border-radius: 4px; }
                        .cta-button { display: inline-block; background: #667eea; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; margin: 20px 0; }
                        .footer { background: #f9fafb; padding: 20px; text-align: center; font-size: 12px; color: #666; border-top: 1px solid #e5e7eb; margin-top: 20px; }
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="header">
                            <h1>Registration Status Update</h1>
                        </div>
                        <div class="content">
                            <div class="rejection-icon">❌</div>
                            <h2 style="color: #dc2626; text-align: center;">Request Not Approved</h2>
                            <p>Dear ${facultyName},</p>
                            <p class="message">Thank you for your interest in joining the SRM Scopus Research Portal. Unfortunately, your registration request has been <strong>declined</strong> at this time.</p>
                            <div class="reason-box">
                                <h3>Reason for Rejection:</h3>
                                <p>${rejectionReason || 'No specific reason provided'}</p>
                            </div>
                            <div class="reapply">
                                <strong>Next Steps:</strong>
                                <p>You may resubmit your registration after addressing the concerns mentioned above. Please ensure all information is accurate and complete before reapplying.</p>
                            </div>
                            <center>
                                <a href="${process.env.PORTAL_URL || 'http://localhost:3000'}" class="cta-button">Try Again</a>
                            </center>
                            <p style="margin-top: 30px; font-size: 14px; color: #666;">If you believe this decision was made in error or have questions, please contact the administration team.</p>
                        </div>
                        <div class="footer">
                            <p>SRM Scopus Research Portal &copy; 2026. All rights reserved.</p>
                        </div>
                    </div>
                </body>
                </html>
            `
        };

        const info = await transporter.sendMail(mailOptions);
        console.log('Rejection email sent:', info.messageId);
        return true;
    } catch (error) {
        console.error('Error sending rejection email:', error);
        return false;
    }
};

module.exports = {
    sendApprovalEmail,
    sendRejectionEmail
};