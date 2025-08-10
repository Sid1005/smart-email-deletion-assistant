import sqlite3
import json
from datetime import datetime
import os

class EmailDatabase:
    def __init__(self, db_path):
        self.db_path = db_path
        self._ensure_db_directory()
        self._init_database()
    
    def _ensure_db_directory(self):
        """Create database directory if it doesn't exist"""
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)
    
    def _init_database(self):
        """Initialize database tables"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS analysis_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_date TEXT NOT NULL,
                    total_emails INTEGER,
                    recommended_deletions INTEGER,
                    needs_review INTEGER,
                    keep_emails INTEGER,
                    status TEXT DEFAULT 'pending',
                    current_page_token TEXT DEFAULT NULL,
                    next_page_token TEXT DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS email_analysis (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER,
                    email_id TEXT NOT NULL,
                    subject TEXT,
                    sender TEXT,
                    date TEXT,
                    snippet TEXT,
                    is_unread BOOLEAN,
                    recommended_action TEXT,
                    category TEXT,
                    confidence REAL,
                    reason TEXT,
                    user_decision TEXT DEFAULT NULL,
                    processed_at TIMESTAMP DEFAULT NULL,
                    FOREIGN KEY (run_id) REFERENCES analysis_runs (id)
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS deleted_emails (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email_id TEXT NOT NULL,
                    subject TEXT,
                    sender TEXT,
                    deleted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    can_restore BOOLEAN DEFAULT TRUE
                )
            ''')
            
            conn.commit()
        
        print("✅ Database initialized")
    
    def save_analysis_run(self, emails, analysis):
        """Save a complete analysis run"""
        with sqlite3.connect(self.db_path) as conn:
            # Save run summary
            summary = analysis.get('summary', {})
            cursor = conn.execute('''
                INSERT INTO analysis_runs 
                (run_date, total_emails, recommended_deletions, needs_review, keep_emails)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                datetime.now().strftime('%Y-%m-%d'),
                summary.get('total_emails', 0),
                summary.get('recommended_deletions', 0),
                summary.get('needs_review', 0),
                summary.get('keep', 0)
            ))
            
            run_id = cursor.lastrowid
            
            # Save individual email analysis
            email_data = []
            for email in emails:
                email_analysis = analysis['analysis'].get(email['id'], {})
                email_data.append((
                    run_id,
                    email['id'],
                    email['subject'],
                    email['sender'],
                    email['date'],
                    email['snippet'],
                    email['is_unread'],
                    email_analysis.get('action', 'review'),
                    email_analysis.get('category', 'other'),
                    email_analysis.get('confidence', 0.5),
                    email_analysis.get('reason', 'No analysis available')
                ))
            
            conn.executemany('''
                INSERT INTO email_analysis 
                (run_id, email_id, subject, sender, date, snippet, is_unread, 
                 recommended_action, category, confidence, reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', email_data)
            
            conn.commit()
            print(f"💾 Saved analysis run {run_id} with {len(emails)} emails")
            return run_id
    
    def get_pending_run(self):
        """Get the most recent pending analysis run"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT * FROM analysis_runs 
                WHERE status = 'pending' 
                ORDER BY created_at DESC 
                LIMIT 1
            ''')
            
            run = cursor.fetchone()
            if run:
                # Get emails for this run
                emails_cursor = conn.execute('''
                    SELECT * FROM email_analysis WHERE run_id = ?
                ''', (run[0],))
                
                emails = emails_cursor.fetchall()
                return {
                    'run': run,
                    'emails': emails
                }
            
            return None

    def get_unprocessed_emails_for_run(self, run_id):
        """Get emails that still need user decisions"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT * FROM email_analysis 
                WHERE run_id = ? AND user_decision IS NULL
            ''', (run_id,))
            return cursor.fetchall()

    def get_processed_emails_for_run(self, run_id):
        """Get emails that already have user decisions"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT * FROM email_analysis 
                WHERE run_id = ? AND user_decision IS NOT NULL
            ''', (run_id,))
            return cursor.fetchall()

    def get_incomplete_run_info(self):
        """Get incomplete run with unprocessed emails for re-analysis"""
        with sqlite3.connect(self.db_path) as conn:
            # Get the most recent pending run
            cursor = conn.execute('''
                SELECT * FROM analysis_runs 
                WHERE status = 'pending' 
                ORDER BY created_at DESC 
                LIMIT 1
            ''')
            
            run = cursor.fetchone()
            if run:
                run_id = run[0]
                
                # Get counts
                total_emails = conn.execute('''
                    SELECT COUNT(*) FROM email_analysis WHERE run_id = ?
                ''', (run_id,)).fetchone()[0]
                
                processed_count = conn.execute('''
                    SELECT COUNT(*) FROM email_analysis 
                    WHERE run_id = ? AND user_decision IS NOT NULL
                ''', (run_id,)).fetchone()[0]
                
                # Get unprocessed emails with their original email data for re-analysis
                unprocessed = self.get_unprocessed_emails_for_run(run_id)
                
                return {
                    'run_id': run_id,
                    'run': run,
                    'unprocessed_emails': unprocessed,
                    'current_page_token': run[7],  # current_page_token column
                    'next_page_token': run[8],     # next_page_token column
                    'total_emails_in_run': total_emails,
                    'processed_count': processed_count,
                    'remaining_count': len(unprocessed),
                    'progress_percentage': round((processed_count / total_emails) * 100, 1) if total_emails > 0 else 0,
                    'needs_reanalysis': len(unprocessed) > 0
                }
            return None

    def get_emails_for_reanalysis(self, run_id):
        """Get unprocessed emails formatted for AI re-analysis"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT email_id, subject, sender, date, snippet, is_unread
                FROM email_analysis 
                WHERE run_id = ? AND user_decision IS NULL
            ''', (run_id,))
            
            emails = cursor.fetchall()
            
            # Convert to format expected by AI analyzer
            formatted_emails = []
            for email in emails:
                formatted_emails.append({
                    'id': email[0],
                    'subject': email[1],
                    'sender': email[2], 
                    'date': email[3],
                    'snippet': email[4],
                    'is_unread': bool(email[5])
                })
            
            return formatted_emails

    def merge_reanalysis_with_new_page(self, reanalyzed_emails, new_analysis, new_emails, current_token, next_token):
        """Merge re-analyzed emails with new page analysis and save as new run"""
        with sqlite3.connect(self.db_path) as conn:
            # Combine summaries
            reanalyzed_count = len(reanalyzed_emails)
            new_count = len(new_emails)
            total_count = reanalyzed_count + new_count
            
            # Calculate combined summary from both analyses
            reanalyzed_summary = {
                'total_emails': reanalyzed_count,
                'recommended_deletions': sum(1 for e in reanalyzed_emails if e.get('action') == 'delete'),
                'needs_review': sum(1 for e in reanalyzed_emails if e.get('action') == 'review'),
                'keep': sum(1 for e in reanalyzed_emails if e.get('action') == 'keep')
            }
            
            new_summary = new_analysis.get('summary', {})
            
            combined_summary = {
                'total_emails': total_count,
                'recommended_deletions': reanalyzed_summary['recommended_deletions'] + new_summary.get('recommended_deletions', 0),
                'needs_review': reanalyzed_summary['needs_review'] + new_summary.get('needs_review', 0),
                'keep': reanalyzed_summary['keep'] + new_summary.get('keep', 0)
            }
            
            # Create new analysis run
            cursor = conn.execute('''
                INSERT INTO analysis_runs 
                (run_date, total_emails, recommended_deletions, needs_review, keep_emails, status, current_page_token, next_page_token)
                VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
            ''', (
                datetime.now().strftime('%Y-%m-%d'),
                combined_summary['total_emails'],
                combined_summary['recommended_deletions'],
                combined_summary['needs_review'],
                combined_summary['keep'],
                current_token,
                next_token
            ))
            
            run_id = cursor.lastrowid
            
            # Save re-analyzed emails
            reanalyzed_data = []
            for email_data in reanalyzed_emails:
                reanalyzed_data.append((
                    run_id,
                    email_data['id'],
                    email_data['subject'],
                    email_data['sender'],
                    email_data['date'],
                    email_data['snippet'],
                    email_data['is_unread'],
                    email_data.get('action', 'review'),
                    email_data.get('category', 'other'),
                    email_data.get('confidence', 0.5),
                    email_data.get('reason', 'Re-analyzed after crash recovery')
                ))
            
            # Save new emails
            new_email_data = []
            for email in new_emails:
                email_analysis = new_analysis['analysis'].get(email['id'], {})
                new_email_data.append((
                    run_id,
                    email['id'],
                    email['subject'],
                    email['sender'],
                    email['date'],
                    email['snippet'],
                    email['is_unread'],
                    email_analysis.get('action', 'review'),
                    email_analysis.get('category', 'other'),
                    email_analysis.get('confidence', 0.5),
                    email_analysis.get('reason', 'No analysis available')
                ))
            
            # Insert all emails
            all_email_data = reanalyzed_data + new_email_data
            conn.executemany('''
                INSERT INTO email_analysis 
                (run_id, email_id, subject, sender, date, snippet, is_unread, 
                 recommended_action, category, confidence, reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', all_email_data)
            
            conn.commit()
            print(f"📦 Merged analysis: {reanalyzed_count} recovered + {new_count} new = {total_count} total emails in run {run_id}")
            return run_id

    def mark_old_run_superseded(self, old_run_id):
        """Mark an old incomplete run as superseded by a new merged run"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                UPDATE analysis_runs 
                SET status = 'superseded'
                WHERE id = ?
            ''', (old_run_id,))
            conn.commit()
            print(f"📝 Marked old run {old_run_id} as superseded")

    def get_run_progress(self, run_id):
        """Get detailed progress information for a specific run"""
        with sqlite3.connect(self.db_path) as conn:
            # Get run info
            run_cursor = conn.execute('''
                SELECT * FROM analysis_runs WHERE id = ?
            ''', (run_id,))
            run = run_cursor.fetchone()
            
            if not run:
                return None
                
            # Get email counts
            total_emails = conn.execute('''
                SELECT COUNT(*) FROM email_analysis WHERE run_id = ?
            ''', (run_id,)).fetchone()[0]
            
            processed_count = conn.execute('''
                SELECT COUNT(*) FROM email_analysis 
                WHERE run_id = ? AND user_decision IS NOT NULL
            ''', (run_id,)).fetchone()[0]
            
            delete_decisions = conn.execute('''
                SELECT COUNT(*) FROM email_analysis 
                WHERE run_id = ? AND user_decision = 'delete'
            ''', (run_id,)).fetchone()[0]
            
            keep_decisions = conn.execute('''
                SELECT COUNT(*) FROM email_analysis 
                WHERE run_id = ? AND user_decision = 'keep'
            ''', (run_id,)).fetchone()[0]
            
            return {
                'run_id': run_id,
                'status': run[6],  # status column
                'total_emails': total_emails,
                'processed_count': processed_count,
                'remaining_count': total_emails - processed_count,
                'delete_decisions': delete_decisions,
                'keep_decisions': keep_decisions,
                'progress_percentage': round((processed_count / total_emails) * 100, 1) if total_emails > 0 else 0,
                'is_complete': processed_count == total_emails
            }
    
    def update_user_decisions(self, run_id, decisions):
        """Update user decisions for emails"""
        with sqlite3.connect(self.db_path) as conn:
            for email_id, decision in decisions.items():
                conn.execute('''
                    UPDATE email_analysis 
                    SET user_decision = ?, processed_at = CURRENT_TIMESTAMP
                    WHERE run_id = ? AND email_id = ?
                ''', (decision, run_id, email_id))
            
            conn.commit()
            print(f"✅ Updated user decisions for run {run_id}")
    
    def mark_run_completed(self, run_id):
        """Mark an analysis run as completed"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                UPDATE analysis_runs 
                SET status = 'completed' 
                WHERE id = ?
            ''', (run_id,))
            conn.commit()
    
    def log_deleted_emails(self, deleted_emails):
        """Log emails that were deleted"""
        with sqlite3.connect(self.db_path) as conn:
            email_data = []
            for email_id, subject, sender in deleted_emails:
                email_data.append((email_id, subject, sender))
            
            conn.executemany('''
                INSERT INTO deleted_emails (email_id, subject, sender)
                VALUES (?, ?, ?)
            ''', email_data)
            
            conn.commit()
            print(f"📝 Logged {len(deleted_emails)} deleted emails")
    
    def get_deletion_history(self, days=30):
        """Get deletion history"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT * FROM deleted_emails 
                WHERE deleted_at > datetime('now', '-{} days')
                ORDER BY deleted_at DESC
            '''.format(days))
            
            return cursor.fetchall()
    
    def get_stats(self):
        """Get overall statistics"""
        with sqlite3.connect(self.db_path) as conn:
            # Total runs
            total_runs = conn.execute('SELECT COUNT(*) FROM analysis_runs').fetchone()[0]
            
            # Total emails processed
            total_emails = conn.execute('SELECT COUNT(*) FROM email_analysis').fetchone()[0]
            
            # Total deletions
            total_deletions = conn.execute('SELECT COUNT(*) FROM deleted_emails').fetchone()[0]
            
            # Recent activity
            recent_runs = conn.execute('''
                SELECT COUNT(*) FROM analysis_runs 
                WHERE created_at > datetime('now', '-7 days')
            ''').fetchone()[0]
            
            # Emails with user decisions (actually processed)
            processed_emails = conn.execute('''
                SELECT COUNT(*) FROM email_analysis 
                WHERE user_decision IS NOT NULL
            ''').fetchone()[0]
            
            # Average emails per run (only completed runs)
            avg_emails_per_run = conn.execute('''
                SELECT AVG(email_count) FROM (
                    SELECT COUNT(*) as email_count 
                    FROM email_analysis ea
                    JOIN analysis_runs ar ON ea.run_id = ar.id
                    WHERE ar.status = 'completed'
                    GROUP BY ea.run_id
                )
            ''').fetchone()[0] or 0
            
            return {
                'total_runs': total_runs,
                'total_emails': total_emails,
                'processed_emails': processed_emails,
                'pending_emails': total_emails - processed_emails,
                'total_deletions': total_deletions,
                'recent_runs': recent_runs,
                'avg_emails_per_run': round(avg_emails_per_run, 1),
                'processing_rate': round((processed_emails / total_emails) * 100, 1) if total_emails > 0 else 0
            }

    def save_page_analysis(self, emails, analysis, current_token, next_token):
        """Save analysis for one page with pagination info"""
        with sqlite3.connect(self.db_path) as conn:
            summary = analysis.get('summary', {})
            cursor = conn.execute('''
                INSERT INTO analysis_runs 
                (run_date, total_emails, recommended_deletions, needs_review, keep_emails, status, current_page_token, next_page_token)
                VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
            ''', (
                datetime.now().strftime('%Y-%m-%d'),
                summary.get('total_emails', 0),
                summary.get('recommended_deletions', 0),
                summary.get('needs_review', 0),
                summary.get('keep', 0),
                current_token,
                next_token
            ))
            
            run_id = cursor.lastrowid
            
            # Save individual email analysis (existing code)
            email_data = []
            for email in emails:
                email_analysis = analysis['analysis'].get(email['id'], {})
                email_data.append((
                    run_id,
                    email['id'],
                    email['subject'],
                    email['sender'],
                    email['date'],
                    email['snippet'],
                    email['is_unread'],
                    email_analysis.get('action', 'review'),
                    email_analysis.get('category', 'other'),
                    email_analysis.get('confidence', 0.5),
                    email_analysis.get('reason', 'No analysis available')
                ))
            
            conn.executemany('''
                INSERT INTO email_analysis 
                (run_id, email_id, subject, sender, date, snippet, is_unread, 
                 recommended_action, category, confidence, reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', email_data)
            
            conn.commit()
            print(f"Saved page analysis run {run_id} with {len(emails)} emails")
            return run_id

    def get_last_page_token(self):
        """Get the token to continue from last unfinished page"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT next_page_token FROM analysis_runs 
                WHERE status = 'pending' AND next_page_token IS NOT NULL
                ORDER BY created_at DESC 
                LIMIT 1
            ''')
            
            result = cursor.fetchone()
            return result[0] if result else None

    def get_pagination_stats(self):
        """Get pagination statistics"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT COUNT(*) as total_pages,
                       COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_pages,
                       COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending_pages
                FROM analysis_runs
            ''')
            
            result = cursor.fetchone()
            
            # Get total emails across all runs
            total_emails_all_runs = conn.execute('''
                SELECT COUNT(*) FROM email_analysis
            ''').fetchone()[0]
            
            # Get emails processed (with decisions) across all runs
            total_processed_emails = conn.execute('''
                SELECT COUNT(*) FROM email_analysis 
                WHERE user_decision IS NOT NULL
            ''').fetchone()[0]
            
            return {
                'total_pages': result[0],
                'completed_pages': result[1], 
                'pending_pages': result[2],
                'total_emails_all_runs': total_emails_all_runs,
                'total_processed_emails': total_processed_emails,
                'emails_pending_review': total_emails_all_runs - total_processed_emails,
                'overall_progress_percentage': round((total_processed_emails / total_emails_all_runs) * 100, 1) if total_emails_all_runs > 0 else 0
            }