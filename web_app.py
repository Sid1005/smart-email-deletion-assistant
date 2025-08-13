from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
import os
import sys
from datetime import datetime

# Add src to path so we can import your existing classes
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.email_processor import EmailProcessor

# Create Flask app
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'your-secret-key-change-this-in-production')

# Initialize email processor (will be None if setup fails)
try:
    email_processor = EmailProcessor("config/config.yaml")
    print("✅ EmailProcessor loaded successfully")
except Exception as e:
    print(f"❌ Failed to load EmailProcessor: {e}")
    email_processor = None

# Route 1: Dashboard (main page)
@app.route('/')
def dashboard():
    """Simple dashboard - shows stats and two main buttons"""
    
    if not email_processor:
        return render_template('error.html', 
                             error="Email processor not available. Check your configuration.")
    
    try:
        # Get simple statistics
        stats = email_processor.get_statistics()
        
        # Calculate pages analyzed (multiples of 50)
        pages_analyzed = stats['total_emails'] // 50
        
        # Get latest run ID for review button
        latest_run_id = None
        pending_run = email_processor.get_pending_review()
        if pending_run:
            latest_run_id = pending_run['run'][0]
        
        # Prepare simplified stats for template
        simplified_stats = {
            'pages_analyzed': pages_analyzed,
            'total_deleted': stats['total_deletions']
        }
        
        return render_template('dashboard.html',
                             stats=simplified_stats,
                             latest_run_id=latest_run_id)
        
    except Exception as e:
        flash(f'Error loading dashboard: {str(e)}', 'error')
        return render_template('error.html', error=str(e))

# Route 2: Analyze next 50 emails
@app.route('/analyze', methods=['POST'])
def start_analysis():
    """Analyze next 50 emails"""
    
    if not email_processor:
        flash('Email processor not available', 'error')
        return redirect(url_for('dashboard'))
    
    try:
        # Check if we should continue or start fresh
        pagination_status = email_processor.get_pagination_status()
        
        if pagination_status['can_continue']:
            result = email_processor.continue_from_last_page()
        else:
            result = email_processor.run_paginated_analysis()
        
        if result:
            session['current_run_id'] = result['run_id']
            flash(f'Successfully analyzed {len(result["emails"])} emails!', 'success')
            return redirect(url_for('review_emails', run_id=result['run_id']))
        else:
            flash('Failed to analyze emails - please try again', 'error')
            return redirect(url_for('dashboard'))
            
    except Exception as e:
        flash(f'Error during analysis: {str(e)}', 'error')
        return redirect(url_for('dashboard'))

# Route 3: Continue from last page (removed - now handled in analyze)
# Route 3 is now just for reviewing existing analysis

# Route 4: Review emails
@app.route('/review/<int:run_id>')
def review_emails(run_id):
    """Show emails for review with checkboxes"""
    
    if not email_processor:
        return render_template('error.html', error="Email processor not available")
    
    try:
        # Get the pending run data (your existing method)
        pending_run = email_processor.get_pending_review()
        
        # Verify this is the correct run
        if not pending_run or pending_run['run'][0] != run_id:
            flash('No pending analysis found for this run', 'error')
            return redirect(url_for('dashboard'))
        
        # Get run info and emails
        run_info = pending_run['run']
        emails = pending_run['emails']
        
        # Convert email tuples to dictionaries for easier template use
        email_list = []
        for email_data in emails:
            email_dict = {
                'id': email_data[2],           # email_id
                'subject': email_data[3],      # subject
                'sender': email_data[4],       # sender
                'date': email_data[5],         # date
                'snippet': email_data[6],      # snippet
                'is_unread': email_data[7],    # is_unread
                'recommended_action': email_data[8],  # recommended_action
                'category': email_data[9],     # category
                'confidence': email_data[10],  # confidence
                'reason': email_data[11]       # reason
            }
            email_list.append(email_dict)
        
        # Count recommendations
        delete_count = sum(1 for email in email_list if email['recommended_action'] == 'delete')
        review_count = sum(1 for email in email_list if email['recommended_action'] == 'review')
        keep_count = sum(1 for email in email_list if email['recommended_action'] == 'keep')
        
        return render_template('review.html',
                             run_id=run_id,
                             emails=email_list,
                             total_emails=len(email_list),
                             delete_count=delete_count,
                             review_count=review_count,
                             keep_count=keep_count)
        
    except Exception as e:
        flash(f'Error loading emails for review: {str(e)}', 'error')
        return redirect(url_for('dashboard'))

# Route 5: Execute deletions
@app.route('/delete/<int:run_id>', methods=['POST'])
def execute_deletions(run_id):
    """Execute email deletions based on user selections"""
    
    if not email_processor:
        flash('Email processor not available', 'error')
        return redirect(url_for('dashboard'))
    
    try:
        # Get selected email IDs from form
        # The form will send email IDs as checkboxes
        selected_emails = request.form.getlist('selected_emails')
        
        if not selected_emails:
            flash('No emails selected for deletion', 'warning')
            return redirect(url_for('review_emails', run_id=run_id))
        
        # Create decisions dictionary
        # We need to get all emails for this run to set their decisions
        pending_run = email_processor.get_pending_review()
        if not pending_run or pending_run['run'][0] != run_id:
            flash('Run not found', 'error')
            return redirect(url_for('dashboard'))
        
        # Build decisions dict: delete selected emails, keep the rest
        decisions = {}
        for email_data in pending_run['emails']:
            email_id = email_data[2]  # email_id column
            if email_id in selected_emails:
                decisions[email_id] = 'delete'
            else:
                decisions[email_id] = 'keep'
        
        # Execute using your existing method
        success = email_processor.execute_user_decisions(run_id, decisions)
        
        if success:
            flash(f'Successfully deleted {len(selected_emails)} emails!', 'success')
            
            # Clear the current run from session
            session.pop('current_run_id', None)
            
            return redirect(url_for('dashboard'))
        else:
            flash('Failed to delete emails', 'error')
            return redirect(url_for('review_emails', run_id=run_id))
            
    except Exception as e:
        flash(f'Error executing deletions: {str(e)}', 'error')
        return redirect(url_for('review_emails', run_id=run_id))

# Route 6: Test connections (utility)
@app.route('/test', methods=['POST'])
def test_connections():
    """Test API connections"""
    
    if not email_processor:
        flash('Email processor not available', 'error')
        return redirect(url_for('dashboard'))
    
    try:
        success = email_processor.test_connections()
        if success:
            flash('All API connections working correctly!', 'success')
        else:
            flash('Some API connections failed. Check logs.', 'error')
            
    except Exception as e:
        flash(f'Connection test failed: {str(e)}', 'error')
    
    return redirect(url_for('dashboard'))

# Run the app
if __name__ == '__main__':
    print("\n🚀 Starting Email Management Web Interface")
    print("📧 Dashboard: http://localhost:5000")
    print("⚡ Debug mode: ON")
    print("=" * 50)
    
    app.run(host='localhost', port=5000, debug=True)